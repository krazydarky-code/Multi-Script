# # SPDX-License-Identifier: GPL-3.0-or-later
# bridge.py
# ──────────────────────────────────────────────────────────────────────────
#  Multi-Script Bridge
#  Local WebSocket <-> Roblox Studio MCP server.
#  The browser extension talks to this over ws://127.0.0.1:<PORT>.
#
#  What this bridge exposes to Kimi (aggregated into one tools/list):
#    - Every MCP server declared in config.json (by default: roblox), each
#      spawned as a stdio child and routed by tool name.
#
#  Design goals (robustness first):
#   - Each MCP stdio process is read by ONE dedicated thread; responses are
#     matched by JSON-RPC id (no "read the next line and hope" races).
#   - stderr is drained so a child never blocks on a full pipe.
#   - A dead server is auto-restarted and the failing call retried once.
#   - Tool calls are locked PER SERVER, so a slow server never blocks another.
#   - Every call ALWAYS produces a reply: a result OR a structured error.
#     Nothing ever hangs the agentic loop silently.
# ──────────────────────────────────────────────────────────────────────────
import asyncio
import concurrent.futures
import functools
import hashlib
import html
import json
import math
import random
import os
import re
import queue
import secrets
import shutil
import signal
import subprocess
import sys
import sysconfig
import threading
import time
import uuid
from collections import deque
from urllib.parse import urlsplit

try:
    # Windows: never flash a console window for netstat / tasklist / powershell /
    # MCP launcher children (the bridge runs without a visible console when the
    # browser's terminal icon starts it). No-op elsewhere. See winquiet.py.
    import os as _os_q
    _hq = _os_q.path.dirname(_os_q.path.abspath(__file__))
    if _hq not in sys.path:
        sys.path.insert(0, _hq)
    import winquiet as _winquiet
    _winquiet.install()
except Exception:
    pass

try:
    # Sibling script (same folder as bridge.py, which Python puts on sys.path
    # automatically) - reused here purely to detect a Studio version bump
    # (see _current_studio_exe below), not to launch anything.
    import launch_studio_mcp as _studio_scan
except Exception:
    _studio_scan = None

try:
    # Sibling module: stages a photo/video the user handed us and turns it into
    # clipboard-pasteable payloads, so a chat surface with no upload control can
    # still receive the media. Optional at import time only in the sense that a
    # failure here must not stop the bridge from serving engine tools - but a
    # silent None would make the media routes 503 with no explanation, so the
    # except records why.
    #
    # bridge.py is normally launched with runtime/ as the working directory, in
    # which case the sibling imports by name. It is ALSO loaded directly by path
    # (tests, tooling), where the cwd is the repo root and the sibling is not on
    # sys.path. Adding our own directory makes the import positional-independent
    # rather than relying on the launcher's cwd.
    import os as _os_boot
    _here_boot = _os_boot.path.dirname(_os_boot.path.abspath(__file__))
    if _here_boot not in sys.path:
        sys.path.insert(0, _here_boot)
    import media_relay as _media
    MEDIA_RELAY = _media.RELAY
    MEDIA_RELAY_ERROR = None
except Exception as _media_exc:  # pragma: no cover - import-time only
    _media = None
    MEDIA_RELAY = None
    MEDIA_RELAY_ERROR = "%s: %s" % (type(_media_exc).__name__, _media_exc)

try:
    # Sibling module: enumerates the desktop apps and windows on this machine so
    # the agent can see what the user has open. Uses only stdlib (ctypes) plus OS
    # binaries, so a missing optional package degrades the DETAIL reported, never
    # the ability to answer at all. Same positional-independence note as above:
    # the _here_boot insert already put runtime/ on sys.path.
    import desktop_vision as _desktop
    DESKTOP_VISION = _desktop
    DESKTOP_VISION_ERROR = None
except Exception as _desktop_exc:  # pragma: no cover - import-time only
    _desktop = None
    DESKTOP_VISION = None
    DESKTOP_VISION_ERROR = "%s: %s" % (type(_desktop_exc).__name__, _desktop_exc)

try:
    # Sibling module: the primitive-choice layer. Answers "what is this feature
    # actually made of" so a modelled part is not defaulted to a scaled sphere.
    # Pure data and pure logic with no dependencies, so this import cannot fail
    # for environmental reasons - only a genuinely broken file would land here.
    import form_craft as _form
    FORM_CRAFT = _form
    FORM_CRAFT_ERROR = None
except Exception as _form_exc:  # pragma: no cover - import-time only
    _form = None
    FORM_CRAFT = None
    FORM_CRAFT_ERROR = "%s: %s" % (type(_form_exc).__name__, _form_exc)

try:
    # Sibling module: local graph memory + sequential thinking (memory_graph.py).
    import memory_graph as MEMORY_GRAPH
    MEMORY_GRAPH_ERROR = None
except Exception as _mem_exc:  # pragma: no cover - import-time only
    MEMORY_GRAPH = None
    MEMORY_GRAPH_ERROR = "%s: %s" % (type(_mem_exc).__name__, _mem_exc)

try:
    # Sibling module: Software Builder workspace tools (W.I.P. mode).
    import software_workspace as WORKSPACE
    WORKSPACE_ERROR = None
except Exception as _ws_exc:  # pragma: no cover - import-time only
    WORKSPACE = None
    WORKSPACE_ERROR = "%s: %s" % (type(_ws_exc).__name__, _ws_exc)

try:
    # Sibling module: ms_find_tool / ms_tool_stats (discoverability + measured performance).
    import assist_tools as ASSIST
    ASSIST_ERROR = None
except Exception as _assist_exc:  # pragma: no cover - import-time only
    ASSIST = None
    ASSIST_ERROR = "%s: %s" % (type(_assist_exc).__name__, _assist_exc)

try:
    # 6.36: publish-time JSON Schema normaliser (see schema_perfect.py).
    import schema_perfect as _SCHEMA_PERFECT
except Exception:  # pragma: no cover - import-time only
    _SCHEMA_PERFECT = None

try:
    # Sibling module: self-healing tool-argument repair (see schema_repair.py).
    import schema_repair as _repair
    SCHEMA_REPAIR_ERROR = None
except Exception as _repair_exc:  # pragma: no cover - import-time only
    _repair = None
    SCHEMA_REPAIR_ERROR = "%s: %s" % (type(_repair_exc).__name__, _repair_exc)

try:
    # Sibling modules: typed native tools for Blender / Roblox / Unity / Godot.
    import engine_toolkit as _TOOLKIT
    _TOOLKIT.ensure_loaded()
    TOOLKIT_ERROR = None
except Exception as _toolkit_exc:  # pragma: no cover - import-time only
    _TOOLKIT = None
    TOOLKIT_ERROR = "%s: %s" % (type(_toolkit_exc).__name__, _toolkit_exc)

try:
    import websockets
except ImportError:
    # Keep the catalogue, schema auditor and offline unit tests importable on a
    # machine that has not run Setup yet. Serving still fails clearly in main;
    # importing a 100% stdlib tool catalogue must not terminate the process.
    websockets = None

# Windows consoles often default to a legacy codepage (cp1252): printing
# non-ASCII text then raises UnicodeEncodeError INSIDE the WS handler, which
# kills the connection. Force UTF-8 (best effort). We also keep all console
# output strictly ASCII (no arrows / dots) so nothing garbles on a console that
# stayed on a legacy codepage anyway.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _enable_ansi_colors():
    """On Windows, turn on ANSI escape processing so color codes render instead
    of printing as literal gibberish like "<ESC>[92m". Returns True on success."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        return bool(k.SetConsoleMode(h, mode.value | 0x0004))
    except Exception:
        return False


HOST = "127.0.0.1"
# Keep in sync with extension/manifest.json "version" - printed at
# startup so a user's terminal output alone tells us which build they're on.
BRIDGE_VERSION = "6.50.1"
PORT = int(os.environ.get("ZS_BRIDGE_PORT", "17613"))
# The Multi-Script folder this bridge runs from (parent of runtime/). Sent to the extension so a
# stale copy left running from another folder can be named in the diagnosis.
_BRIDGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_PORT = int(os.environ.get("ZS_PLUGIN_PORT", str(PORT + 1)))
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
COMPANION_TOOLS_PATH = os.path.join(HERE, "roblox-plugin-tools.json")
try:
    with open(COMPANION_TOOLS_PATH, "r", encoding="utf-8") as _f:
        COMPANION_TOOLS = json.load(_f).get("tools", [])
except Exception:
    COMPANION_TOOLS = []
COMPANION_TOOL_BY_NAME = {t.get("name"): t for t in COMPANION_TOOLS if t.get("name")}
COMPANION_TOOL_NAMES = set(COMPANION_TOOL_BY_NAME)

# The primary server. It is always present, added by the installer, and can
# never be edited/removed through the extension (it is what Multi-Script is FOR).
PRIMARY_SERVER_ID = "roblox"

if _enable_ansi_colors():
    C = {
        "reset": "\033[0m", "dim": "\033[2m", "gr": "\033[92m",
        "yl": "\033[93m", "rd": "\033[91m", "cy": "\033[96m",
        # Bold white-on-red: for a non-technical user, an "ACTION NEEDED" step
        # must look nothing like the routine cyan/yellow status noise around
        # it, or it gets scrolled past unread (seen live 2026-07-13 - the
        # toggle instruction and the boot banner's own yellow re-explanation
        # of the SAME step were visually indistinguishable). Bright-yellow-bg
        # with black text was tried first but reads as low-contrast/washed
        # out on several real terminal color schemes (also seen live) - white
        # on red is the universal high-contrast "act now" pairing.
        "act": "\033[1m\033[97m\033[41m",
    }
else:
    C = {k: "" for k in ("reset", "dim", "gr", "yl", "rd", "cy", "act")}

# Every run appends here (never truncated), so a whole test session - across
# multiple restarts - stays in one file the user can just send us. Each
# process start writes a banner (see main()) so restarts are easy to spot.
LOGS_DIR = os.path.join(HERE, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOGS_DIR, "bridge_debug.log")
try:
    _log_file = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
except Exception:
    _log_file = None


class _Spinner:
    """Terminal-only progress indicator for waits that can run several seconds
    (server launch/handshake, Studio attach grace period) so the console never
    just sits there looking dead - the #1 thing that makes a user assume the
    bridge hung and close the window. Purely cosmetic: writes over its own line
    with \\r, never touches bridge_debug.log, and is skipped entirely when
    stdout isn't a real console (redirected to a file, no ANSI)."""
    FRAMES = "|/-\\"
    # Only ONE spinner may animate at a time: server launches now run in
    # PARALLEL (see MCPManager.start_all), and several spinners fighting over
    # the same console line with \r produced interleaved garbage. Whoever
    # acquires this lock animates; the others silently skip (the log lines
    # around them still tell the story).
    _active = threading.Lock()

    def __init__(self, label):
        self.label = label
        self._stop = threading.Event()
        self._thread = None
        self._owns_lock = False

    def __enter__(self):
        if sys.stdout.isatty() and _Spinner._active.acquire(blocking=False):
            self._owns_lock = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            # Wipe the spinner line so the next log() line doesn't get glued
            # onto trailing spinner characters.
            try:
                print("\r" + " " * (len(self.label) + 4) + "\r", end="", flush=True)
            except (OSError, ValueError):
                pass
        if self._owns_lock:
            _Spinner._active.release()

    def _run(self):
        i = 0
        while not self._stop.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            try:
                print(f"\r{C['dim']}{self.label} {frame}{C['reset']}", end="", flush=True)
            except (OSError, ValueError):
                return
            i += 1
            self._stop.wait(0.15)


def _clear_spinner_line():
    """Wipe whatever a live _Spinner (running on its own thread, mid-frame) left
    on the current console line via bare \\r writes, so the next print() below
    doesn't get glued onto its trailing characters - seen live 2026-07-14: an
    action_banner() fired while '[roblox] starting... -' was still mid-line and
    the red box rendered smashed onto it instead of starting on a fresh line.
    \\033[K (clear to end of line) doesn't depend on knowing the spinner's label
    length the way Spinner.__exit__'s own wipe does."""
    if sys.stdout.isatty():
        print("\r\033[K", end="", flush=True)


# ── Live log ring buffer (the in-extension terminal) ──────────────────────────
# The chat bar's terminal panel shows what the bridge is actually doing, so the
# bridge has to keep its recent output somewhere addressable - the console text
# is not readable from the extension, and the log FILE is only ever written.
#
# Deliberately bounded: a long-running bridge must not grow this without limit,
# so it is a deque with a hard cap. Each entry carries a monotonic `seq` so the
# panel can ask for "everything after N" and never miss or duplicate a line even
# if two polls land close together.
LOG_RING_MAX = 600
_log_ring = deque(maxlen=LOG_RING_MAX)
_log_seq = 0          # last assigned sequence number
_log_lock = threading.Lock()
# When this process came up. Recorded here (not at import time of some other
# module) so the uptime the terminal panel reports is this run's, and survives
# an in-process restart_self() because the module is re-executed fresh.
_started_at = time.time()

# Terminal colour name -> a level the panel can style. Anything unmapped is
# "info", which is the right default: it is shown plainly rather than hidden.
_LOG_LEVELS = {
    "rd": "error", "red": "error", "err": "error",
    "yl": "warn", "yellow": "warn", "warn": "warn",
    "gr": "ok", "green": "ok", "gn": "ok", "ok": "ok",
    "cy": "info", "cyan": "info", "bl": "info", "blue": "info",
    "dim": "muted", "gray": "muted", "grey": "muted",
}


def log_record(msg, color="dim"):
    """Append one line to the ring. Returns the record, so callers that also want
    to push it to live subscribers can. Never raises."""
    global _log_seq
    try:
        with _log_lock:
            _log_seq += 1
            rec = {
                "seq": _log_seq,
                "t": time.strftime("%H:%M:%S"),
                "level": _LOG_LEVELS.get(str(color).lower(), "info"),
                "msg": str(msg),
            }
            _log_ring.append(rec)
            return rec
    except Exception:
        return None


def log_since(since=0, limit=400):
    """Records with seq > `since`, capped. Also returns the newest seq so the
    caller can advance its cursor even when it is handed fewer lines than exist
    (an old cursor far behind a rotated buffer must not re-request forever)."""
    try:
        s = int(since or 0)
    except Exception:
        s = 0
    with _log_lock:
        newest = _log_seq
        out = [r for r in _log_ring if r["seq"] > s]
    return out[-max(1, min(int(limit or 400), LOG_RING_MAX)):], newest


def log(msg, color="dim", terminal=True):
    """terminal=False: written to bridge_debug.log only, not the console. Use
    for noisy/technical detail (raw stderr from child MCP servers, per-call
    traces) that would bury the handful of lines a non-technical user actually
    needs to read. Nothing is ever lost - it all still lands in the file."""
    if terminal:
        # A Windows console whose handle went bad (a child sharing it exited,
        # the window was closed, stdout is a dead pipe) raises OSError 22 from
        # print/flush. That used to abort server restarts with the cryptic
        # "auto-restart failed: [Errno 22] Invalid argument"; logging must
        # never be able to break the bridge.
        try:
            _clear_spinner_line()
            ts = time.strftime("%H:%M:%S")
            print(f"{C['dim']}{ts}{C['reset']} {C.get(color,'')}{msg}{C['reset']}", flush=True)
        except (OSError, ValueError):
            pass
    if _log_file:
        try:
            _log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
            _log_file.flush()
        except Exception:
            pass
    # The ring is fed from here regardless of `terminal`, because the panel
    # replaces the console for most users: a line written to the file but not
    # the console would otherwise be invisible in the very UI that exists to
    # show it. (terminal=False was about console noise, not about hiding data.)
    rec = log_record(msg, color)
    if rec is not None:
        _publish_log(rec)


# Sockets that asked to follow the log live. Held weakly-keyed by id so a closed
# connection cannot pin memory; _publish_log prunes as it goes.
_log_subs = {}
_log_subs_lock = threading.Lock()


def _publish_log(rec):
    """Hand a new record to every subscribed socket. Never raises, never blocks:
    a slow/closed client must not stall the caller, so this only does a
    best-effort put on each subscription's own queue."""
    if not _log_subs:
        return
    try:
        with _log_subs_lock:
            subs = list(_log_subs.values())
        for q in subs:
            try:
                q.put_nowait(rec)
            except Exception:
                pass
    except Exception:
        pass


def _subscribe_log(ws, q):
    """Register `q` as a live log sink for this socket. Returns an unsubscribe
    callable. Keyed by id(ws) so a dropped connection leaves nothing behind."""
    key = id(ws)
    with _log_subs_lock:
        _log_subs[key] = q

    def _unsub():
        with _log_subs_lock:
            _log_subs.pop(key, None)

    return _unsub


async def _log_pump(ws, q):
    """Forward queued log records to one socket, batched.

    Batched on purpose: a burst (an engine handshake emits dozens of lines at
    once) would otherwise be one WS frame per line. We drain whatever is already
    queued into a single frame, which keeps the panel responsive and the socket
    quiet. Stops quietly when the socket goes away - the handler's finally owns
    subscription cleanup, so this never needs to touch it.
    """
    loop = asyncio.get_running_loop()
    try:
        while True:
            # Cancellation does not stop an executor's blocking q.get(). Without
            # a timeout every disconnected tab leaked a worker thread forever,
            # and asyncio shutdown could wait on those abandoned reads.
            try:
                first = await loop.run_in_executor(None, lambda: q.get(timeout=0.5))
            except queue.Empty:
                continue
            batch = [first]
            # Drain without waiting, up to a sane frame size.
            while len(batch) < 120:
                try:
                    batch.append(q.get_nowait())
                except queue.Empty:
                    break
            await ws.send(json.dumps({"type": "bridge_log_push", "lines": batch}))
    except asyncio.CancelledError:
        raise
    except Exception:
        # ConnectionClosed or anything else: the panel will simply reconnect and
        # re-request the backlog by seq, so there is nothing to repair here.
        return


# 6.28: environment diagnostics for the Running tab. Cached: the snapshot is
# broadcast on every status push, and shutil.which hits the PATH each time.
_ENV_CACHE = {"at": 0.0, "data": None}


def _env_diagnostics():
    """What this PC can actually run - so 'unity down' can be answered with
    'uvx missing' instead of silence. Unknowns are False/None, never guessed."""
    now = time.time()
    if _ENV_CACHE["data"] is not None and now - _ENV_CACHE["at"] < 60:
        return _ENV_CACHE["data"]
    try:
        uvx = shutil.which("uvx")
        if not uvx:
            home = os.path.expanduser("~")
            for cand in (os.path.join(home, ".local",  "uvx.exe" if os.name == "nt" else "uvx"),
                         os.path.join(home, ".cargo", "bin", "uvx.exe" if os.name == "nt" else "uvx")):
                if os.path.isfile(cand):
                    uvx = cand
                    break
        data = {
            "python": ".".join(str(x) for x in sys.version_info[:3]),
            "platform": sys.platform,
            "uvx": bool(uvx),
            "npx": bool(shutil.which("npx")),
            "blenderAddon": os.path.isfile(os.path.join(HERE, "addons", "blender-mcp-addon.py")),
        }
    except Exception:
        data = None
    _ENV_CACHE.update(at=now, data=data)
    return data


def _service_snapshot():
    """A compact, honest picture of what the bridge is serving right now - the
    header of the terminal panel. Reports only what we can actually observe; an
    unknown is null, never a guess dressed up as a fact."""
    try:
        health = mgr.health()
    except Exception:
        health = []
    try:
        servers_line = [
            {"id": h.get("id"), "alive": bool(h.get("alive")), "tools": h.get("tools")}
            for h in health
        ]
    except Exception:
        servers_line = []
    return {
        "bridgeVersion": BRIDGE_VERSION,
        "port": PORT,
        "uptimeSeconds": round(time.time() - _started_at, 1) if _started_at else None,
        "clients": len(clients),
        "logFile": os.path.basename(_log_file.name) if _log_file else None,
        "servers": servers_line,
        "environment": _env_diagnostics(),
        "ringSize": len(_log_ring),
        "ringMax": LOG_RING_MAX,
    }


def _bridge_diagnostics():
    """Everything needed to answer "why is this bridge not working?" in ONE call.

    Read-only. Aggregates what is otherwise scattered across the console, the
    in-extension terminal panel and logs/setup.log: version, ports, uptime,
    platform, the environment probe (uvx / npx / Blender add-on), per-server
    state, which engines are switched off on THIS machine, the catalogue sizes,
    and the tail of the log ring. Unknowns stay None - never a guess.
    """
    servers, health_error = [], None
    try:
        health = mgr.health()
    except Exception as exc:
        health, health_error = [], str(exc)
    for h in health or []:
        if not isinstance(h, dict):
            continue
        servers.append({
            "id": h.get("id"),
            "alive": bool(h.get("alive")),
            "tools": h.get("tools"),
            "lastError": h.get("last_error") or h.get("error") or None,
        })
    try:
        recent = [r.get("msg") for r in log_since(0, 15)[0]]
    except Exception:
        recent = []
    return {
        "ok": True,
        "bridgeVersion": BRIDGE_VERSION,
        "ports": {"bridge": PORT, "companionPlugin": PLUGIN_PORT, "studioMcp": STUDIO_MCP_PORT},
        "uptimeSeconds": round(time.time() - _started_at, 1) if _started_at else None,
        "platform": sys.platform,
        "pid": os.getpid(),
        "extensionClients": len(clients),
        "servers": servers,
        "healthError": health_error,
        "enginesDisabled": sorted(_load_engine_prefs()),
        "catalogue": {
            # The bridge-side built-in catalogue (the ms_* tools the bridge
            # dispatches itself), plus the separate companion / skill / virtual
            # catalogues. The release gate pins its own count of the ms_* tools
            # from the source; this is the live number the bridge is serving.
            "builtinTools": len(BUILTIN_TOOLS),
            "companionTools": len(COMPANION_TOOLS),
            "skills": len(_load_skills()),
            "virtualTools": len(_load_virtual_tools()),
        },
        "environment": _env_diagnostics(),
        "logFile": os.path.basename(_log_file.name) if _log_file else None,
        "recentLog": recent,
    }



def action_banner(lines):
    """Print a step the USER must physically go do, styled so it cannot be
    mistaken for routine status/warning noise (see the 'act' color above).
    Framed with blank lines so it visually stands alone in a scrolling
    terminal - a non-technical user should be able to glance at the window
    and immediately spot this without reading everything above it.

    Every line (header, content, footer) is padded to the SAME width so the
    yellow block renders as one clean rectangle - an earlier version padded
    each line to a fixed guess independently, which produced a ragged block
    with mismatched edges on a real console (seen live 2026-07-13)."""
    header = "ACTION NEEDED"
    width = max([len(header) + 8] + [len(ln) for ln in lines]) + 2
    top = f">>> {header} " + ">" * max(0, width - len(header) - 5)
    _clear_spinner_line()
    print()
    print(f"{C['act']}  {top.ljust(width)}{C['reset']}")
    for ln in lines:
        print(f"{C['act']}  {ln.ljust(width)}{C['reset']}")
    print(f"{C['act']}  {'>' * width}{C['reset']}")
    print()
    if _log_file:
        try:
            _log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ACTION NEEDED: "
                             f"{' | '.join(lines)}\n")
            _log_file.flush()
        except Exception:
            pass


# Roblox Studio exposes its built-in MCP server on this loopback port. StudioMCP
# (and our bridge, via it) reaches Studio through it.
STUDIO_MCP_PORT = 13469


def _port_owner_posix(port):
    """macOS/Linux flavour of _port_owner: lsof, then ss. (pid, name, path) or None."""
    pid = None
    try:
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                             capture_output=True, text=True, timeout=8).stdout.split()
        pid = next((t for t in out if t.isdigit()), None)
    except Exception:
        pass
    if not pid:
        try:
            out = subprocess.run(["ss", "-ltnpH", f"sport = :{port}"], capture_output=True, text=True,
                                 timeout=8).stdout
            m = re.search(r"pid=(\d+)", out)
            pid = m.group(1) if m else None
        except Exception:
            pass
    if not pid and sys.platform.startswith("linux"):
        # No lsof/ss installed (minimal containers, some distros): read /proc directly.
        try:
            inodes = set()
            for tbl in ("/proc/net/tcp", "/proc/net/tcp6"):
                try:
                    with open(tbl) as fh:
                        next(fh, None)
                        for line in fh:
                            f = line.split()
                            if len(f) > 9 and f[3] == "0A" and int(f[1].rsplit(":", 1)[1], 16) == port:
                                inodes.add(f[9])
                except (OSError, ValueError):
                    continue
            for d in (os.listdir("/proc") if inodes else []):
                if not d.isdigit() or pid:
                    continue
                try:
                    for fd in os.listdir("/proc/%s/fd" % d):
                        try:
                            if os.readlink("/proc/%s/fd/%s" % (d, fd)).startswith("socket:[") and \
                                    os.readlink("/proc/%s/fd/%s" % (d, fd))[8:-1] in inodes:
                                pid = d
                                break
                        except OSError:
                            continue
                except OSError:
                    continue
        except Exception:
            pid = None
    if not pid:
        return None
    raw = ""
    try:
        raw = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True,
                             timeout=8).stdout.strip()
    except Exception:
        raw = ""
    if not raw and sys.platform.startswith("linux"):
        # `ps -o comm=` prints argv[0] on Linux and may be a bare name; the
        # /proc symlink gives the real executable path when we may read it.
        try:
            raw = os.readlink("/proc/%s/exe" % pid)
        except OSError:
            raw = ""
    if not raw:
        return (pid, "?", "")
    # macOS `ps -o comm=` already prints the FULL executable path
    # (/Applications/RobloxStudio.app/Contents/MacOS/RobloxStudio); Linux usually
    # a bare argv[0]. Returning the raw value as `path` - instead of the "" this
    # used to return - is what lets check_studio_port recognise a legitimate
    # Roblox owner instead of reporting Studio itself as a port squatter on every
    # macOS boot (it decided "is this Roblox?" from `path` alone).
    return (pid, os.path.basename(raw) or raw, raw)


def _port_owner(port):
    """(pid, name, path) of the process LISTENING on `port`, or None."""
    if sys.platform != "win32":
        return _port_owner_posix(port)
    # BOTH stacks: "-p TCP" alone is IPv4-only, and a squatter listening on
    # [::1]:<port> (IPv6 loopback) was then completely invisible to this probe
    # even while Get-NetTCPConnection showed it plainly (the likely reason the
    # boot-time squatter check stayed silent on a machine where ropilot
    # provably held the port - see the 2026-07-13 live report).
    out = ""
    for proto in ("TCP", "TCPv6"):
        try:
            out += subprocess.run(
                ["netstat", "-ano", "-p", proto],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=8,
            ).stdout
        except Exception:
            pass
    if not out:
        return None
    pid = None
    # v4 lines end the local address in ":<port>", v6 in "]:<port>" - matching
    # on the ":<port> " suffix (with the column gap) covers both shapes.
    needle = f":{port} "
    for line in out.splitlines():
        if "LISTENING" in line and needle in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                pid = parts[-1]
                break
    if not pid:
        return None
    name, path = "?", ""
    try:
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
             f"if($p){{$p.Name; $p.Path}}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=8,
        ).stdout.splitlines()
        ps = [l.strip() for l in ps if l.strip()]
        if ps:
            name = ps[0]
            path = ps[1] if len(ps) > 1 else ""
    except Exception:
        pass
    return (pid, name, path)


# Names that identify a LEGITIMATE holder of Studio's MCP port. Studio itself,
# its MCP proxy and the macOS bundle binaries all qualify. Matching is on a
# lowercase substring of either the process name or its executable path.
_ROBLOX_OWNER_MARKERS = ("roblox", "studiomcp")


def _is_roblox_owner(name, path):
    """True when the process holding Studio's MCP port is Roblox's own.

    The Windows probe returns a real `path` under a "...\\Roblox\\..." folder,
    but the POSIX probe used to return an empty path - and the callers decided
    "is this Roblox?" from `path` alone. On macOS that made a perfectly healthy
    Studio look like a port squatter on every single boot. Match on the name as
    well as the path so both probes classify identically.
    """
    hay = f"{name or ''} {path or ''}".lower()
    return any(marker in hay for marker in _ROBLOX_OWNER_MARKERS)


def _kill_pid(pid, force=True):
    """Terminate a single PID on this platform. Returns (ok, error_message).

    `taskkill` does not exist off Windows, so the three Studio-reaping helpers
    that called it unguarded raised FileNotFoundError inside a bare `except`
    and silently did nothing on macOS/Linux - leaving a zombie StudioMCP holding
    the port forever. Every kill now goes through here.
    """
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return False, f"invalid pid {pid!r}"
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid_i)],
                           capture_output=True, text=True, timeout=8)
        else:
            # SIGKILL does not exist on Windows, so resolve it by name rather than
            # referencing the attribute directly - that keeps this callable (and
            # unit-testable) even on a host whose signal module lacks it.
            sig = getattr(signal, "SIGKILL" if force else "SIGTERM", signal.SIGTERM)
            os.kill(pid_i, sig)
        return True, None
    except Exception as e:
        return False, str(e)


def _roblox_studio_app_running():
    """True/False whether a real Roblox Studio window process exists, or None
    if this can't be determined (non-Windows, or the check itself failed)."""
    if sys.platform == "darwin":
        # macOS: the Studio bundle's binary name varies by build/channel. The
        # launcher already accepts all three (see launch_studio_mcp.py's
        # MAC_STUDIO_EXECUTABLES), so probe for each - checking only
        # "RobloxStudio" disabled the orphan-cleanup safety gate and the zombie
        # reclaim path on any machine whose binary is named differently.
        for exe in ("RobloxStudio", "RobloxStudioBeta", "Roblox"):
            try:
                r = subprocess.run(["pgrep", "-x", exe], capture_output=True, text=True, timeout=8)
            except Exception:
                return None
            if r.returncode == 0 and r.stdout.strip():
                return True
        return False
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq RobloxStudioBeta.exe"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=8,
        ).stdout
    except Exception:
        return None
    return "RobloxStudioBeta.exe" in out


def _kill_orphan_studio_mcp():
    """Kill leftover StudioMCP.exe processes from a PREVIOUS session/crash.

    StudioMCP.exe is Roblox's own MCP proxy; launch_studio_mcp.py spawns one
    as a direct child every time the bridge starts. If an earlier restart's
    tree-kill missed the grandchild (a reparenting race), or Studio itself
    crashed and left its own StudioMCP.exe running (seen live 2026-07-11:
    RobloxStudioBeta.exe zombied after two RobloxCrashHandler.exe events),
    the orphan keeps LISTENING on Studio's MCP port. Every StudioMCP.exe we
    launch afterward - even a freshly restarted one - just connects to that
    zombie instead of a real Studio, so the bridge reports "Studio connected"
    forever even with Studio fully closed. studio_watch's auto-restart cannot
    fix this on its own: restarting our proxy still lands on the same zombie.

    Only acts when NO real Studio app is running at all - in that state any
    existing StudioMCP.exe is unambiguously orphaned (a legitimate one only
    exists to serve a live Studio), so it is safe to auto-kill without asking.
    If Studio IS running (or this can't be determined), this is a no-op: a
    live StudioMCP.exe might be legitimately serving it, so nothing is
    touched - this must never risk killing a working connection.
    """
    if sys.platform == "darwin":
        if _roblox_studio_app_running() is not False:
            return
        try:
            if subprocess.run(["pgrep", "-x", "StudioMCP"], capture_output=True, timeout=8).returncode != 0:
                return
            log("Found leftover StudioMCP process(es) with no Roblox Studio running - "
                "cleaning them up (known cause of a phantom 'Studio connected' state).", "yl")
            subprocess.run(["pkill", "-x", "StudioMCP"], capture_output=True, timeout=8)
        except Exception as e:
            log(f"could not clean up orphaned StudioMCP: {e}", "rd")
        return
    if sys.platform != "win32":
        return
    if _roblox_studio_app_running() is not False:
        return
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq StudioMCP.exe"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=8,
        ).stdout
    except Exception:
        return
    if "StudioMCP.exe" not in out:
        return
    log("Found leftover StudioMCP.exe process(es) with no Roblox Studio running - "
        "cleaning them up (known cause of a phantom 'Studio connected' state).", "yl")
    try:
        subprocess.run(["taskkill", "/F", "/IM", "StudioMCP.exe"],
                       capture_output=True, text=True, timeout=8)
    except Exception as e:
        log(f"could not clean up orphaned StudioMCP.exe: {e}", "rd")


def _descendant_pids(root_pid):
    """Set of PIDs = root_pid + every descendant, or None if the process tree
    could not be read (in which case callers must NOT make kill decisions)."""
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process | ForEach-Object "
                 "{ \"$($_.ProcessId) $($_.ParentProcessId)\" }"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=10,
            ).stdout
        except Exception:
            return None
    else:
        # macOS / Linux. This used to `return None` unconditionally off Windows,
        # which made the ownership guard in _reclaim_studio_port inert there -
        # so the zombie-StudioMCP deadlock that function exists to break was only
        # ever recoverable on Windows. `ps -eo pid=,ppid=` is POSIX and present on
        # both platforms (no BSD/GNU flag divergence: bare `=` headers are standard).
        try:
            out = subprocess.run(["ps", "-eo", "pid=,ppid="], capture_output=True, text=True,
                                 timeout=10).stdout
        except Exception:
            return None
    children = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    if not children:
        return None
    pids = {int(root_pid)}
    stack = [int(root_pid)]
    while stack:
        for c in children.get(stack.pop(), []):
            if c not in pids:
                pids.add(c)
                stack.append(c)
    return pids


def _reclaim_studio_port(client):
    """Kill a StudioMCP.exe that owns Studio's MCP port but is NOT our own child.

    The deadlock this breaks (reported live, survives every restart combo):
    a zombie StudioMCP.exe from a crashed session keeps LISTENING on 13469.
    The user reopens Studio -> its MCP plugin does its ONE-SHOT registration
    against the ZOMBIE (wasted). The user restarts the bridge -> Studio is now
    running, so _kill_orphan_studio_mcp's safety guard skips the cleanup, and
    check_studio_port waves the zombie through too (its path IS under Roblox).
    Our fresh StudioMCP can't own the port, Studio never re-registers on its
    own -> 0 tools forever, no restart order can fix it by hand.

    Ownership is decided by PID, not heuristics: we know the PID of the
    launcher we spawned (client.proc), so a StudioMCP.exe holding the port
    outside that process tree is a leftover by definition - Studio open or
    not. If the process tree can't be read, we do nothing (never risk killing
    our own healthy child on bad data). Returns True if a zombie was killed;
    the caller must then restart the roblox proxy (safe here even with Studio
    open: the plugin's single registration already went to the zombie, so
    there is no attempt left for a restart to collide with) AND tell the user
    to open Assistant Settings > MCP Servers so the plugin re-registers.
    """
    owner = _port_owner(STUDIO_MCP_PORT)
    if not owner:
        return False
    pid, name, path = owner
    # Only ever kill a StudioMCP.exe. Studio itself holding the port is fine;
    # a non-Roblox squatter is check_studio_port's (interactive) job.
    if "studiomcp" not in (name or "").lower():
        return False
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return False
    if client is not None and client.proc is not None and client.is_alive():
        tree = _descendant_pids(client.proc.pid)
        if tree is None or pid_i in tree:
            return False  # ours, or unknowable - leave it alone
    log(f"port {STUDIO_MCP_PORT} is held by a StudioMCP.exe (pid {pid_i}) that this "
        "bridge did NOT launch - a leftover from a previous session. Studio "
        "registered to it, so our proxy sees 0 tools.", "yl")
    ok, err = _kill_pid(pid_i)
    if not ok:
        log(f"could not kill the leftover StudioMCP.exe: {err}", "rd")
        return False
    log(f"killed the leftover StudioMCP.exe (pid {pid_i}) to free Studio's MCP port.", "cy")
    return True


def _process_cmdline(pid):
    """Full command line of `pid`, or "" if it can't be read.

    Used to tell OUR OWN kind of process (a python running bridge.py) apart
    from an unrelated app that merely happens to listen on the same port -
    the process NAME is just "python"/"py"/"pythonw", far too generic to kill
    on. The command line is what proves it is a leftover bridge."""
    if sys.platform != "win32":
        try:
            return subprocess.run(["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True,
                                  timeout=8).stdout.strip()
        except Exception:
            return ""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\" "
             f"-ErrorAction SilentlyContinue).CommandLine"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=8,
        ).stdout
    except Exception:
        return ""
    return (out or "").strip()


def _reclaim_bridge_port():
    """Free OUR OWN listen port (17613) from a leftover bridge before we bind.

    The common failure (reported live, WinError 10048 on bind): the user
    relaunches the bridge while an earlier bridge.py is still running - window
    closed with the X instead of Ctrl+C, a previous crash that left a detached
    python, or a double double-click. The old process still holds the port, so
    websockets.serve() dies on bind with a cryptic (localised) OSError and the
    whole bridge exits code 1.

    We reuse _port_owner (already generic over the port) and only ever kill a
    process we can PROVE is another bridge.py - never a same-name innocent
    (some unrelated python listening on 17613): the guard is the command line
    containing "bridge.py", plus an explicit self-exclusion by PID. Anything
    else (a non-python app, or a python whose cmdline we can't read) is left
    alone and surfaced to the user by the caller's friendly bind-error path.
    Returns True if a leftover bridge was killed."""
    owner = _port_owner(PORT)
    if not owner:
        return False
    pid, name, path = owner
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_i == os.getpid():
        return False  # never kill ourselves (defensive; we haven't bound yet)
    # Must look like a python interpreter AND be running bridge.py. Killing on
    # the port alone would murder whatever legitimately owns 17613. A Windows
    # `py` launcher shows up as py.exe / pyw.exe, so match those too.
    low_name = (name or "").lower()
    if "python" not in low_name and low_name not in ("py", "py.exe", "pyw", "pyw.exe"):
        return False
    cmdline = _process_cmdline(pid_i)
    if "bridge.py" not in cmdline.lower():
        log(f"port {PORT} is held by pid {pid_i} ('{name}') but it does not look "
            f"like a Multi-Script bridge - leaving it alone.", "yl")
        return False
    log(f"port {PORT} is held by a leftover Multi-Script bridge (pid {pid_i}) from a "
        f"previous session or another folder - killing it so this one can start.  [{cmdline[:160]}]", "yl")
    try:
        if sys.platform == "win32":
            # /T: the stale bridge's MCP children (StudioMCP, Godot/Unity servers) go with it.
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid_i)],
                           capture_output=True, text=True, timeout=12)
        else:
            import signal
            try:
                os.kill(pid_i, signal.SIGTERM)
            except ProcessLookupError:
                pass
            for _ in range(20):
                time.sleep(0.2)
                try:
                    os.kill(pid_i, 0)
                except OSError:
                    break
            else:
                os.kill(pid_i, signal.SIGKILL)
    except Exception as e:
        log(f"could not kill the leftover bridge (pid {pid_i}): {e}", "rd")
        return False
    log(f"killed the leftover bridge (pid {pid_i}); the port is free now.", "cy")
    return True


def _kill_port_squatter():
    """Kill a NON-Roblox process holding Studio's MCP port, no questions asked.

    Called only when the child's stderr has PROVEN the port is hijacked (see
    MCPClient.saw_foreign_ws_host - StudioMCP connected to a foreign host and
    could not parse its protocol; the ropilot case). At that point there is no
    ambiguity left to justify check_studio_port's interactive prompt, and the
    prompt was itself a trap: many users never answer it, and the one-shot boot
    check often runs a beat before a background helper (ropilot) grabs the
    port. Here we have hard evidence, so kill the squatter outright. Returns
    (killed, name) so the caller can tell the user which app to uninstall /
    remove from startup, since it will otherwise reclaim the port on next boot.
    """
    owner = _port_owner(STUDIO_MCP_PORT)
    if owner:
        pid, name, path = owner
        if _is_roblox_owner(name, path):
            return False, None  # legitimate Studio-side owner; not a squatter
        log(f"port {STUDIO_MCP_PORT} is hijacked by '{name}' (pid {pid}, {path}).", "yl")
        log("    StudioMCP connected to it instead of Roblox Studio - that is why "
            "there are 0 tools.", "yl")
        ok, err = _kill_pid(pid)
        if not ok:
            log(f"could not kill '{name}': {err}", "rd")
            return False, name
        log(f"killed '{name}' so Studio can use the port.", "cy")
        return True, name
    # We could NOT resolve who owns the port, yet StudioMCP's stderr proved the
    # port is hijacked (this function is only called under that proof). This is
    # the state that used to fail SILENTLY: _port_owner returning None (e.g. a
    # squatter listening on IPv6 loopback that an IPv4-only netstat missed, or
    # any netstat quirk) left the user staring at 0 tools with no explanation.
    # Never be silent here. Try a name-based fallback for the known offender
    # (ropilot ships a background helper that squats this port), then always
    # tell the user what we know.
    log(f"port {STUDIO_MCP_PORT} is hijacked (StudioMCP could not talk to Roblox "
        "Studio on it) but the owning process could not be identified by port.", "yl")
    # ropilot is a multi-process app (validated live 2026-07-13): the port is
    # held by ropilot-infra-helper.exe, supervised by ropilot-infra.exe. Kill
    # both so the supervisor can't just respawn the helper and re-grab the port.
    killed_name = None
    # ropilot is a Windows application; hunting its image names is meaningless
    # (and its taskkill would simply fail) on macOS and Linux.
    if sys.platform == "win32":
        for img in ("ropilot-infra-helper.exe", "ropilot-infra.exe", "ropilot.exe"):
            try:
                res = subprocess.run(["taskkill", "/F", "/IM", img],
                                     capture_output=True, text=True, timeout=8)
            except Exception:
                continue
            if res.returncode == 0:
                killed_name = img
                log(f"killed '{img}' (known port squatter) so Studio can use the port.", "cy")
    if killed_name:
        return True, killed_name
    log("    Could not auto-kill it. Find it manually, then quit that program:", "yl")
    if sys.platform == "win32":
        log(f"      netstat -ano | findstr {STUDIO_MCP_PORT}    (then end that PID in Task Manager)", "yl")
    else:
        log(f"      lsof -nP -iTCP:{STUDIO_MCP_PORT} -sTCP:LISTEN", "yl")
        log("      then:  kill <the PID in the last column>", "yl")
    return False, None


def _print_squatter_hint(name):
    """After killing a port squatter (e.g. ropilot), tell the user how to stop
    it coming back - it is a background helper that respawns on the next boot
    and re-grabs the port before Studio, which is why a PC reboot never fixed
    this class of 0-tools report."""
    app = name or "the other app"
    action_banner([
        f"'{app}' fights Roblox Studio for its connection - it will keep",
        "coming back after every restart until you remove it.",
        f"1. Uninstall '{app}' (or remove it from Windows startup).",
        "2. In Roblox Studio: Assistant Settings > MCP Servers,",
        "   turn OFF then back ON 'Enable Studio as MCP server'.",
    ])


def _print_reregister_hint():
    """The one user action that completes a zombie-kill recovery: Studio's MCP
    plugin registers only once per boot and that attempt went to the zombie,
    so after the kill + proxy restart the user must make it register again."""
    # Opening the panel alone is technically enough to re-register, but we tell
    # the user to toggle OFF/ON to be sure - a toggle strictly implies opening
    # the panel, so it can never do less, and it removes any ambiguity about
    # whether "just looking at it" counted. Same wording as the squatter/no-place
    # banners so all three read as one identical instruction, not three variants.
    action_banner([
        "Go to Roblox Studio now.",
        "Turn OFF then back ON: Assistant Settings > MCP Servers",
        "         > 'Enable Studio as MCP server'",
        "Wait about 10 seconds - this window will turn green.",
    ])


def check_studio_port():
    """Warn (and optionally kill) a NON-Roblox process squatting Studio's MCP port.

    A third-party tool (e.g. "ropilot") that binds 13469 before Studio does
    hijacks the MCP channel: StudioMCP connects to IT instead of Studio, the
    handshake succeeds but tools/list never answers -> the bridge sees 0 tools.
    This is silent and brutal to diagnose, so we surface it up front.
    """
    owner = _port_owner(STUDIO_MCP_PORT)
    if not owner:
        return False
    pid, name, path = owner
    # The legitimate holder is Studio itself or a Roblox helper. Match on the
    # name as well as the path: the POSIX probe historically returned an empty
    # path, which made a healthy macOS Studio look like a squatter every boot.
    if _is_roblox_owner(name, path):
        return False
    where = path or name
    log(f"port {STUDIO_MCP_PORT} (Studio's MCP port) is held by a non-Roblox process:", "yl")
    log(f"    {name} (pid {pid})  {where}", "yl")
    log("    This will block Studio's tools (the bridge will see 0 tools).", "yl")
    try:
        ans = input("    Kill this process so Studio can use the port? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = ""
    if ans in ("y", "yes", "o", "oui"):
        ok, err = _kill_pid(pid)
        if not ok:
            log(f"could not kill it: {err}", "rd")
            return False
        log(f"killed {name} (pid {pid}). Studio can use the port now.", "cy")
        # Tell the user the finishing step IMMEDIATELY, here, instead of only
        # after the ~48s server-launch grace loop that follows: killing the
        # squatter frees the port, but Studio's MCP plugin registers only
        # once per boot and that attempt already went to the squatter, so it
        # will NOT re-attach on its own - a toggle is needed. Printing this
        # now (not 48s later, after start_all's grace loop) is what turns a
        # ~1-minute "why is nothing happening" wait into an act-right-away
        # instruction. Uses action_banner (not log) so a non-technical user
        # visually cannot miss it among the surrounding status lines - seen
        # live indistinguishable when both used the same plain color.
        action_banner([
            "Go to Roblox Studio now.",
            "Turn OFF then back ON: Assistant Settings > MCP Servers",
            "         > 'Enable Studio as MCP server'",
            "Wait about 10 seconds - this window will turn green.",
        ])
        return True  # a squatter WAS killed -> Studio must reclaim the port
    log("left it running. Close it yourself, then restart the bridge.", "yl")
    return False


_TRANSIENT_STUDIO_MARKERS = (
    "no roblox studio instance", "no active studio", "studio instance is connect",
    "studio instance connected", "not connected to", "no studio instance",
)


# Tools whose repetition changes the place. They must never be silently re-sent:
# if the first attempt reached Studio before the link dropped, a re-send applies it
# twice (an empty-old_string multi_edit then shows up as "print(1)print(1)").
_NON_IDEMPOTENT_NATIVE = frozenset({
    "multi_edit", "execute_luau", "insert_asset", "insert_from_creator_store", "store_image",
    "generate_mesh", "generate_procedural_model", "start_stop_play",
    "user_keyboard_input", "user_mouse_input",
    "figma_create_node", "figma_update_node", "figma_import_svg", "figma_delete_node", "figma_set_selection",
    "use_figma", "create_new_file", "upload_assets", "generate_figma_design",
    "bbmodel_create", "bbmodel_edit", "bbmodel_add_texture", "bbmodel_render",
    "bbmodel_export_bedrock_geometry", "bbmodel_export_bedrock_animations",
    "bbmodel_export_java_block", "bbmodel_export_obj", "bbmodel_export_gltf",
    "bbmodel_particle_effect", "bbmodel_particle_pack", "bbmodel_convert_legacy",
    "bbmodel_import_java_block", "bbmodel_export_modded_entity", "bbmodel_contact_sheet",
})


def _looks_like_transient_studio_drop(text):
    low = (text or "").lower()
    # A genuine "no Studio connected" notice is short. Long text is a tool RESULT
    # (script output that merely contains those words) - never retry on that.
    if len(low) > 500:
        return False
    return any(m in low for m in _TRANSIENT_STUDIO_MARKERS)


# ── config.json read / write (for extension-driven add/remove) ──────────────
_CONFIG_LOCK=threading.RLock()

def _serial_config(fn):
    @functools.wraps(fn)
    def run(*args,**kwargs):
        with _CONFIG_LOCK:return fn(*args,**kwargs)
    return run


def _read_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if isinstance(cfg, dict):
                cfg.setdefault("mcpServers", {})
                return cfg
        except Exception as e:
            log(f"config.json unreadable ({e}) - starting from a fresh one", "yl")
    return {"mcpServers": {PRIMARY_SERVER_ID: {"command": "launch_studio_mcp.py", "args": []}}}


def _write_config(cfg):
    """Atomic write so a crash mid-write never leaves a truncated config.json."""
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)


@_serial_config
def config_add_server(server_id, command, args=None, env=None):
    """Add/replace an addon server in config.json. Refuses to touch the primary
    (roblox) server. Returns (ok, error)."""
    sid = (server_id or "").strip()
    if not sid:
        return False, "server id is required"
    if sid == PRIMARY_SERVER_ID:
        return False, f"'{PRIMARY_SERVER_ID}' is the primary server and cannot be edited"
    if not (command or "").strip():
        return False, "a command is required"
    cfg = _read_config()
    spec = {"command": command.strip(), "args": list(args or [])}
    if env:
        spec["env"] = dict(env)
    cfg["mcpServers"][sid] = spec
    try:
        _write_config(cfg)
    except Exception as e:
        return False, f"could not write config.json: {e}"
    return True, None


@_serial_config
def config_remove_server(server_id):
    """Remove an addon server from config.json. Refuses the primary server."""
    sid = (server_id or "").strip()
    if sid == PRIMARY_SERVER_ID:
        return False, f"'{PRIMARY_SERVER_ID}' is the primary server and cannot be removed"
    cfg = _read_config()
    if sid not in cfg.get("mcpServers", {}):
        return False, f"server '{sid}' is not in the config"
    del cfg["mcpServers"][sid]
    try:
        _write_config(cfg)
    except Exception as e:
        return False, f"could not write config.json: {e}"
    return True, None


def restart_self():
    """Replace this process with a fresh one so config.json is reloaded from
    scratch. Children are killed first to free their stdio pipes / ports before
    the new instance claims them. Never returns on success (os.execv)."""
    log("restarting bridge to load new server config...", "yl")
    try:
        for c in mgr.clients.values():
            c.stop()
    except Exception:
        pass
    if _log_file:
        try:
            _log_file.flush()
        except Exception:
            pass
    # sys.argv[0] may be relative ('bridge.py'); make it absolute so the restart
    # works regardless of the current working directory.
    argv = list(sys.argv)
    script = os.path.abspath(argv[0]) if argv else os.path.abspath(__file__)
    argv = [script] + argv[1:]
    try:
        os.execv(sys.executable, [sys.executable] + argv)
    except Exception as e:
        # execv failed (rare) - fall back to spawning a detached copy and exiting
        # so the user still ends up with a running, up-to-date bridge.
        log(f"in-place restart failed ({e}); spawning a fresh bridge...", "rd")
        try:
            subprocess.Popen([sys.executable] + argv, cwd=HERE)
        except Exception as e2:
            log(f"could not spawn a fresh bridge: {e2} - please restart it manually", "rd")
        os._exit(0)


# ── Multi-Script built-in tools and reusable skills ────────────────────────────
SKILLS_PATH = os.path.join(HERE, "skills.json")
STUDIO_STANDARD_PATH = os.path.join(HERE, "studio-standard.json")
VIRTUAL_TOOLS_PATH = os.path.join(HERE, "virtual-tools.json")
# 6.48.7: catalogues are read-only during normal agent execution. Cache parsed
# JSON by path + file fingerprint so every tool call does not re-parse the full
# multi-megabyte skill and virtual-tool libraries. If a file changes on disk,
# the next call naturally reloads it; tests and live updates retain hot-reload.
_CATALOG_CACHE = {}

SKILL_SHARED_POLICY_PATH = os.path.join(HERE, "skill-shared-policy.json")

def _apply_shared_skill_policy(skills):
    """Restore the policy fields shared by the skill catalogue, and rebuild
    instructions from steps where the catalogue stores them only once. A skill's
    own value always wins, so per-skill overrides are preserved."""
    try:
        with open(SKILL_SHARED_POLICY_PATH, "r", encoding="utf-8") as f:
            shared = json.load(f)
    except Exception as e:
        log(f"skill-shared-policy.json unreadable: {e}", "yl")
        return skills
    out = {}
    for k, v in skills.items():
        if not isinstance(v, dict):
            out[k] = v
            continue
        resolved = {**shared, **v}
        if "instructions" not in resolved and isinstance(resolved.get("steps"), list):
            resolved["instructions"] = "\n".join(resolved["steps"])
        out[k] = resolved
    return out

def _load_catalog_json(path, cache_key):
    try:
        stat = os.stat(path)
        fingerprint = (getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)), stat.st_size)
        if cache_key == "skills":
            try:
                policy_stat = os.stat(SKILL_SHARED_POLICY_PATH)
                fingerprint += (getattr(policy_stat,"st_mtime_ns",int(policy_stat.st_mtime*1e9)),policy_stat.st_size)
            except OSError:
                fingerprint += (None,None)
        cached = _CATALOG_CACHE.get(cache_key)
        if cached and cached[0] == fingerprint:
            return cached[1]
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict): data = {}
        if cache_key == "skills": data = _apply_shared_skill_policy(data)
        _CATALOG_CACHE[cache_key] = (fingerprint, data)
        return data
    except Exception as e:
        log(f"{os.path.basename(path)} unreadable: {e}", "yl")
        return {}

def _load_skills():
    import studio_hub
    return {**_load_catalog_json(SKILLS_PATH, "skills"), **studio_hub.installed_skills()}

def _load_studio_standard():
    return _load_catalog_json(STUDIO_STANDARD_PATH, "studio-standard")

def _load_virtual_tools():
    data = _load_catalog_json(VIRTUAL_TOOLS_PATH, "virtual-tools")
    tools = data.get("tools", {})
    return tools if isinstance(tools, dict) else {}

_AUDIO_MODULE = None

def _elevenlabs_audio():
    global _AUDIO_MODULE
    if _AUDIO_MODULE is None:
        import importlib.util
        path = os.path.join(HERE, "elevenlabs_audio.py")
        spec = importlib.util.spec_from_file_location("ms_elevenlabs_audio", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _AUDIO_MODULE = module
    return _AUDIO_MODULE


ADVANCED_DIRECT_CONTRACTS = {'ms_camera_system_design': {'description': 'Design and validate a production camera system for gameplay, cinematics, collision, comfort, and every target input.', 'stages': ['camera goals and player readability', 'camera state graph and ownership', 'follow/orbit/aim behavior', 'collision and occlusion recovery', 'smoothing, damping and shake layers', 'input-device sensitivity and inversion', 'accessibility and motion comfort', 'runtime implementation and edge-case capture'], 'qualityGates': ['no clipping in representative spaces', 'stable transitions between every state', 'target lock and aim remain readable', 'mouse, controller and touch feel consistent', 'reduced-motion option is respected', 'camera never steals gameplay authority', 'frame-time cost stays within budget', 'runtime evidence covers worst cases']}, 'ms_input_mapping_plan': {'description': 'Create a cross-platform input architecture with rebinding, action maps, prompts, focus, and accessibility.', 'stages': ['inventory all player actions', 'separate semantic actions from device inputs', 'define gameplay and UI contexts', 'map keyboard, mouse, controller and touch', 'design rebinding and conflict resolution', 'implement device-change prompts', 'support hold/toggle and assist alternatives', 'test hot-plug, focus and persistence'], 'qualityGates': ['every required action is reachable', 'contexts cannot leak conflicting actions', 'rebinding survives restart', 'prompts update with active device', 'controller navigation has no dead ends', 'touch targets meet size requirements', 'disconnect and reconnect recover cleanly', 'accessibility alternatives are verified']}, 'ms_character_controller_review': {'description': 'Review or design a responsive character controller covering movement, slopes, jumps, grounding, networking, and animation integration.', 'stages': ['define movement fantasy and metrics', 'inspect grounding and collision model', 'design acceleration and air control', 'handle slopes, steps and moving platforms', 'spec jump buffering and coyote time', 'integrate animation and root motion policy', 'define network ownership and reconciliation', 'instrument and test edge geometry'], 'qualityGates': ['no tunneling or slope jitter', 'ground state is deterministic', 'jump behavior matches metrics', 'moving platforms preserve relative motion', 'animation never fights controller authority', 'latency does not create obvious warps', 'controller works at low and high frame rates', 'edge-case test scene passes']}, 'ms_combat_system_design': {'description': 'Create a complete combat architecture with timing, hit validation, damage, status effects, feedback, networking, and balance hooks.', 'stages': ['define combat pillars and verbs', 'spec attacks, cancels and state ownership', 'design hitboxes, hurtboxes and targeting', 'define authoritative damage pipeline', 'add cooldown, resource and status rules', 'synchronize animation, VFX and audio', 'instrument balance and abuse telemetry', 'implement test encounters and failure cases'], 'qualityGates': ['server validates consequential hits', 'timing windows match animation evidence', 'duplicate damage is impossible', 'invulnerability and interruption are explicit', 'feedback communicates cause and result', 'latency behavior is fair and bounded', 'balance variables are data-driven', 'automated and two-player tests pass']}, 'ms_ai_behavior_design': {'description': 'Design game AI with perception, decision making, navigation, combat tactics, recovery, debugging, and performance budgets.', 'stages': ['define behavior goals and difficulty envelope', 'design perception and memory', 'choose state tree, behavior tree or planner', 'spec navigation and spatial queries', 'add group tactics and reservations', 'handle interruption, failure and recovery', 'build debug visualization and telemetry', 'stress-test populations and edge cases'], 'qualityGates': ['AI decisions are explainable in debug view', 'perception respects occlusion and ranges', 'navigation recovers from blocked paths', 'states cannot deadlock', 'difficulty changes behavior not cheating', 'group agents avoid pathological crowding', 'CPU cost stays within population budget', 'seeded scenarios are repeatable']}, 'ms_quest_system_design': {'description': 'Design a data-driven quest, objective, dialogue, reward, persistence, and migration system.', 'stages': ['define quest grammar and lifecycle', 'model objectives and dependency graphs', 'separate definitions from player state', 'design triggers, dialogue and world reactions', 'validate rewards and idempotency', 'persist and migrate progress', 'build authoring and debug tools', 'test abandonment, replay and branching'], 'qualityGates': ['cycles and impossible objectives are detected', 'rewards cannot duplicate', 'progress survives save migration', 'branch conditions are deterministic', 'multiplayer ownership is explicit', 'localization text is externalized', 'debug tooling exposes current blockers', 'representative quest chains pass']}, 'ms_inventory_economy_design': {'description': 'Design inventory and economy systems with stacking, transactions, crafting, shops, persistence, anti-duplication, and tuning.', 'stages': ['define item schema and identifiers', 'spec slots, stacks, capacity and equipment', 'design atomic transaction boundaries', 'model currencies, sources and sinks', 'add crafting, loot and shop rules', 'persist with idempotent reconciliation', 'instrument economy and exploit telemetry', 'simulate progression and boundary cases'], 'qualityGates': ['transactions are atomic', 'duplicate and negative balances are impossible', 'server validates grants and purchases', 'unknown item versions migrate safely', 'UI state matches authoritative data', 'sources and sinks remain measurable', 'concurrency tests preserve invariants', 'rollback and repair paths exist']}, 'ms_procedural_generation_plan': {'description': 'Create a deterministic procedural-generation pipeline with seeds, constraints, validation, streaming, and authored overrides.', 'stages': ['define generated space and invariants', 'choose seed and random-stream ownership', 'separate topology, content and decoration passes', 'encode constraints and solvability checks', 'add authored anchors and overrides', 'design streaming and regeneration boundaries', 'build debug maps and reproduction tools', 'run statistical and adversarial seeds'], 'qualityGates': ['same seed reproduces exactly', 'all outputs satisfy hard constraints', 'critical paths remain solvable', 'generation has bounded retries', 'streaming preserves seams and state', 'authored content composes cleanly', 'worst-case generation meets time budget', 'failed seeds are logged and reproducible']}, 'ms_shader_production': {'description': 'Create an engine-ready shader production contract covering visual intent, lighting, variants, parameters, optimization, and fallback tiers.', 'stages': ['define visual target and reference lighting', 'choose surface, post, compute or screen-space path', 'design parameter and texture interface', 'implement lighting and transparency behavior', 'add animation and gameplay controls', 'build quality tiers and fallbacks', 'profile variants, overdraw and instruction cost', 'validate across cameras and target hardware'], 'qualityGates': ['shader matches target under representative lighting', 'parameters have safe documented ranges', 'transparent sorting artifacts are controlled', 'variants do not explode build size', 'mobile or low-tier fallback exists', 'no NaN, flicker or precision failure', 'GPU cost meets budget', 'runtime captures prove behavior']}, 'ms_lighting_production': {'description': 'Design and implement cohesive game lighting with readability, mood, probes, shadows, post-processing, and performance tiers.', 'stages': ['set mood, value structure and focal hierarchy', 'choose baked, mixed and dynamic ownership', 'place key, fill and practical sources', 'configure shadows and contact grounding', 'build probes, reflection and GI coverage', 'tune exposure, fog and post effects', 'create time or state transitions', 'profile and capture every quality tier'], 'qualityGates': ['gameplay targets remain readable', 'exposure is stable across transitions', 'characters ground correctly', 'probe seams are not visible', 'shadow cost meets budget', 'post effects preserve UI and accessibility', 'low tier retains art direction', 'target-device captures are approved']}, 'ms_environment_production': {'description': 'Create a complete environment-production contract from blockout through modular assets, dressing, lighting, gameplay readability, and optimization.', 'stages': ['define player journey and landmarks', 'block out scale, metrics and sightlines', 'design modular kit and reuse rules', 'create hero assets and material language', 'dress with hierarchy and storytelling', 'integrate collision, navigation and gameplay', 'light and add atmosphere', 'optimize streaming, LOD and occlusion'], 'qualityGates': ['scale supports movement metrics', 'critical routes and landmarks read clearly', 'modular seams are controlled', 'collision and navigation match visuals', 'asset density follows focal hierarchy', 'memory and draw-call budgets pass', 'lighting supports gameplay states', 'runtime walkthrough has clean logs']}, 'ms_character_model_production': {'description': 'Create a character-model pipeline covering concept translation, topology, UVs, materials, facial needs, LODs, rig handoff, and engine validation.', 'stages': ['lock silhouette, proportions and technical target', 'sculpt or model primary forms', 'build deformation-aware topology', 'create UV and texel-density plan', 'author materials and texture sets', 'prepare facial and customization requirements', 'generate LOD and optimization variants', 'handoff to rig and validate in engine'], 'qualityGates': ['silhouette reads at gameplay distance', 'topology supports required deformation', 'normals and UVs are clean', 'materials match art direction', 'LOD transitions are acceptable', 'scale, axes and pivots import correctly', 'memory and triangle budgets pass', 'test poses reveal no blocking defects']}, 'ms_rigging_production': {'description': 'Create a robust rigging contract for skeletons, skinning, controls, constraints, retargeting, physics, export, and engine tests.', 'stages': ['define skeleton and deformation requirements', 'build hierarchy, orientation and naming', 'skin and tune weight distribution', 'create animator controls and constraints', 'add IK, twist, facial and secondary systems', 'prepare retarget and avatar mapping', 'build export bake and validation preset', 'test extreme poses and engine playback'], 'qualityGates': ['hierarchy exports without helper leakage', 'joint orientation is consistent', 'weights meet influence limits', 'extreme poses avoid major collapse', 'IK and constraints bake deterministically', 'retargeting preserves proportions', 'physics layers do not fight animation', 'engine import and clips pass']}, 'ms_localization_audit': {'description': 'Audit localization readiness across text, fonts, layouts, input, audio, pluralization, cultural context, and QA.', 'stages': ['inventory all player-facing content', 'externalize strings and stable keys', 'define locale, plural and grammar rules', 'verify fonts and shaping coverage', 'design expansion and bidirectional layouts', 'localize assets, audio and controls', 'build pseudo-localization workflow', 'test saves, networking and fallback locale'], 'qualityGates': ['no hard-coded player text remains', 'missing keys fall back safely', '200-percent expansion does not break UI', 'RTL and complex scripts render correctly', 'fonts cover supported glyphs', 'variables preserve grammar and order', 'localized assets respect memory budgets', 'locale switching and persistence pass']}, 'ms_telemetry_plan': {'description': 'Create a privacy-aware telemetry specification with events, schemas, funnels, diagnostics, sampling, dashboards, and validation.', 'stages': ['define product questions and decisions', 'map player journey and failure points', 'spec event names and ownership', 'define typed properties and versioning', 'set privacy, consent and retention rules', 'add sampling and offline buffering', 'build dashboards and alert thresholds', 'validate events against real sessions'], 'qualityGates': ['every event answers a named question', 'schemas reject malformed payloads', 'PII is excluded or explicitly governed', 'duplicate events are controlled', 'offline and retry behavior is bounded', 'version changes remain queryable', 'dashboards expose actionable thresholds', 'test sessions reconcile end to end']}, 'ms_liveops_plan': {'description': 'Plan safe live operations covering configuration, events, segmentation, rollout, economy protection, moderation, observability, and rollback.', 'stages': ['define cadence and player value', 'separate remote config from code', 'design event and reward schemas', 'create segmentation and eligibility rules', 'add staged rollout and kill switches', 'protect economy and entitlement flows', 'instrument health and participation', 'prepare moderation, support and rollback'], 'qualityGates': ['events use server-authoritative time', 'rewards are idempotent', 'config is validated before activation', 'segments cannot expose restricted content', 'kill switch works without client update', 'economy impact has guardrails', 'support can diagnose player state', 'rollback rehearsal succeeds']}, 'ms_store_compliance_check': {'description': 'Generate a platform-store compliance and submission gate for privacy, monetization, content ratings, permissions, packaging, and review evidence.', 'stages': ['identify target storefront requirements', 'audit privacy disclosures and data flows', 'review purchases, ads and subscriptions', 'verify age rating and content declarations', 'minimize permissions and capabilities', 'validate package identity and signing', 'prepare screenshots, metadata and support links', 'run clean-install submission build'], 'qualityGates': ['privacy labels match actual behavior', 'restore purchases works where required', 'parental and regional rules are covered', 'permissions are justified', 'rating answers match shipped content', 'package and signing are reproducible', 'review account and instructions are valid', 'submission artifact passes smoke test']}, 'ms_security_abuse_review': {'description': 'Review a game feature for trust boundaries, secrets, permissions, injection, cheating, moderation, privacy, and incident response.', 'stages': ['map assets, actors and trust boundaries', 'identify sensitive data and secrets', 'audit input validation and authorization', 'review network and persistence abuse cases', 'add rate limits and replay protection', 'design moderation and privacy controls', 'instrument detection and incident evidence', 'test adversarial and recovery scenarios'], 'qualityGates': ['secrets never ship to clients', 'server validates consequential actions', 'least privilege is enforced', 'untrusted content is escaped or sandboxed', 'abuse limits are measurable', 'privacy controls match policy', 'security logs avoid sensitive leakage', 'repair and incident paths are tested']}, 'ms_bug_triage': {'description': 'Turn a bug report into a reproducible, prioritized engineering investigation with hypotheses, instrumentation, fix scope, and verification.', 'stages': ['normalize symptoms and expected behavior', 'capture build, platform and environment', 'minimize deterministic reproduction steps', 'collect logs, state and timing evidence', 'rank hypotheses by evidence', 'isolate regression range and ownership', 'define smallest safe fix', 'write verification and non-regression cases'], 'qualityGates': ['reproduction is specific and repeatable', 'severity and player impact are justified', 'evidence separates cause from correlation', 'fix does not hide symptoms only', 'related systems are inspected', 'regression test fails before the fix', 'target platforms pass after fix', 'release and rollback notes exist']}, 'ms_regression_plan': {'description': 'Create a risk-based regression plan covering changed surfaces, dependencies, automated checks, manual journeys, platforms, performance, and rollback.', 'stages': ['enumerate changes and dependency graph', 'rank regression risks', 'select automated unit and integration checks', 'define critical manual player journeys', 'cover save, network and compatibility paths', 'test device and quality tiers', 'compare performance baselines', 'record release decision and rollback trigger'], 'qualityGates': ['changed behavior has direct tests', 'dependent systems have targeted coverage', 'critical journey passes from clean state', 'old saves and content remain compatible', 'multiplayer version behavior is defined', 'performance has no material regression', 'failures produce actionable evidence', 'rollback threshold is explicit']}}


ADVANCED_DIRECT_CONTRACTS.update({'ms_dialogue_production': {'description': 'Dialogue production: branching dialogue, conditions, localization, VO hooks and runtime validation.', 'stages': ['Define dialogue production goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for branching dialogue, conditions, localization, VO hooks and runtime validation', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_cinematic_production': {'description': 'Cinematic production: storyboards, cameras, animation, timing, audio, skip/replay and runtime capture.', 'stages': ['Define cinematic production goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for storyboards, cameras, animation, timing, audio, skip/replay and runtime capture', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_tutorial_design': {'description': 'Tutorial design: onboarding, progressive disclosure, practice, recovery, telemetry and accessibility.', 'stages': ['Define tutorial design goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for onboarding, progressive disclosure, practice, recovery, telemetry and accessibility', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_navigation_system_design': {'description': 'Navigation system design: navigation meshes, agents, links, avoidance, streaming and recovery.', 'stages': ['Define navigation system design goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for navigation meshes, agents, links, avoidance, streaming and recovery', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_physics_system_audit': {'description': 'Physics system audit: collision layers, fixed-step behavior, ownership, determinism and profiling.', 'stages': ['Define physics system audit goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for collision layers, fixed-step behavior, ownership, determinism and profiling', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_vehicle_system_design': {'description': 'Vehicle system design: handling, suspension, controls, camera, networking, damage and tuning.', 'stages': ['Define vehicle system design goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for handling, suspension, controls, camera, networking, damage and tuning', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_world_streaming_plan': {'description': 'World streaming plan: partitioning, loading, persistence, seams, budgets and failure recovery.', 'stages': ['Define world streaming plan goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for partitioning, loading, persistence, seams, budgets and failure recovery', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_level_design_review': {'description': 'Level design review: metrics, flow, pacing, landmarks, encounters, accessibility and playtests.', 'stages': ['Define level design review goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for metrics, flow, pacing, landmarks, encounters, accessibility and playtests', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_puzzle_design': {'description': 'Puzzle design: rules, teaching, feedback, hinting, reset, exploits and difficulty progression.', 'stages': ['Define puzzle design goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for rules, teaching, feedback, hinting, reset, exploits and difficulty progression', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_social_system_design': {'description': 'Social system design: parties, friends, presence, invites, privacy, moderation and safety.', 'stages': ['Define social system design goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for parties, friends, presence, invites, privacy, moderation and safety', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_matchmaking_design': {'description': 'Matchmaking design: queues, skill, latency, parties, backfill, abuse prevention and telemetry.', 'stages': ['Define matchmaking design goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for queues, skill, latency, parties, backfill, abuse prevention and telemetry', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_modding_pipeline': {'description': 'Modding pipeline: sandboxing, schemas, packaging, validation, compatibility and moderation.', 'stages': ['Define modding pipeline goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for sandboxing, schemas, packaging, validation, compatibility and moderation', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_build_automation': {'description': 'Build automation: reproducible builds, versioning, tests, signing, artifacts and rollback.', 'stages': ['Define build automation goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for reproducible builds, versioning, tests, signing, artifacts and rollback', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_crash_diagnostics': {'description': 'Crash diagnostics: symbols, dumps, breadcrumbs, reproduction, grouping and fix verification.', 'stages': ['Define crash diagnostics goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for symbols, dumps, breadcrumbs, reproduction, grouping and fix verification', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_memory_leak_audit': {'description': 'Memory leak audit: allocation baselines, lifecycle ownership, retention paths and soak testing.', 'stages': ['Define memory leak audit goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for allocation baselines, lifecycle ownership, retention paths and soak testing', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_network_bandwidth_audit': {'description': 'Network bandwidth audit: message inventory, payloads, rates, compression, interest and loss tests.', 'stages': ['Define network bandwidth audit goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for message inventory, payloads, rates, compression, interest and loss tests', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_mobile_optimization': {'description': 'Mobile optimization: thermal, memory, GPU, input, UI, battery and device-tier validation.', 'stages': ['Define mobile optimization goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for thermal, memory, GPU, input, UI, battery and device-tier validation', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_vr_xr_production': {'description': 'VR/XR production: comfort, interaction, locomotion, scale, performance and accessibility.', 'stages': ['Define vr/xr production goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for comfort, interaction, locomotion, scale, performance and accessibility', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_web_build_optimization': {'description': 'Web build optimization: download size, startup, memory, browser compatibility and caching.', 'stages': ['Define web build optimization goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for download size, startup, memory, browser compatibility and caching', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_console_readiness': {'description': 'Console readiness: platform input, suspend/resume, users, saves, certification and performance.', 'stages': ['Define console readiness goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for platform input, suspend/resume, users, saves, certification and performance', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_controller_haptics': {'description': 'Controller haptics: event taxonomy, envelopes, device capabilities, comfort and testing.', 'stages': ['Define controller haptics goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for event taxonomy, envelopes, device capabilities, comfort and testing', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_iconography_production': {'description': 'Iconography production: visual language, grids, states, readability, localization and export.', 'stages': ['Define iconography production goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for visual language, grids, states, readability, localization and export', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_marketing_capture_plan': {'description': 'Marketing capture plan: shot list, builds, camera paths, clean UI, formats and approvals.', 'stages': ['Define marketing capture plan goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for shot list, builds, camera paths, clean UI, formats and approvals', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_npc_population_system': {'description': 'NPC population system: spawning, schedules, simulation LOD, persistence and performance.', 'stages': ['Define npc population system goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for spawning, schedules, simulation LOD, persistence and performance', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_weather_system': {'description': 'Weather system: state model, visuals, gameplay, audio, transitions, replication and budgets.', 'stages': ['Define weather system goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for state model, visuals, gameplay, audio, transitions, replication and budgets', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_day_night_system': {'description': 'Day/night system: time authority, lighting, schedules, saves, networking and transitions.', 'stages': ['Define day/night system goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for time authority, lighting, schedules, saves, networking and transitions', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_destructible_system': {'description': 'Destructible system: fracture states, authority, damage, debris, persistence and optimization.', 'stages': ['Define destructible system goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for fracture states, authority, damage, debris, persistence and optimization', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_replay_system': {'description': 'Replay system: capture schema, determinism, seek, versioning, storage and playback validation.', 'stages': ['Define replay system goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for capture schema, determinism, seek, versioning, storage and playback validation', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}, 'ms_photo_mode': {'description': 'Photo mode: camera controls, pause policy, filters, UI, platform saves and privacy.', 'stages': ['Define photo mode goals and measurable acceptance criteria', 'Inspect current project architecture, content and constraints', 'Design the data model, ownership and lifecycle for camera controls, pause policy, filters, UI, platform saves and privacy', 'Implement the smallest complete vertical path in the target engine', 'Integrate UI, input, audio, VFX and persistence where relevant', 'Handle failure, interruption, migration and multiplayer edge cases', 'Profile target-platform performance and add observability', 'Run focused tests, read back state and capture verification evidence'], 'qualityGates': ['The requested result exists in the real target project', 'Authority and ownership are explicit and secure', 'Happy, edge, failure and interruption paths are covered', 'Configuration is data-driven and documented', 'Accessibility and all target inputs are considered', 'Performance is measured against an explicit budget', 'Automated or repeatable tests pass with clean logs', 'Final state is read back and supported by concrete evidence']}})


STUDIO_DIRECT_CONTRACTS = {'ms_roblox_animation_studio': {'description': 'Roblox animation studio with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_blender_animation_studio': {'description': 'Blender animation studio with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_unity_animation_studio': {'description': 'Unity animation studio with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_godot_animation_studio': {'description': 'Godot animation studio with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_combat_animation_polish': {'description': 'Combat animation polish with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_locomotion_animation_polish': {'description': 'Locomotion animation polish with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_cinematic_animation_polish': {'description': 'Cinematic animation polish with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_creature_animation': {'description': 'Creature animation with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_facial_animation': {'description': 'Facial animation with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_animation_retargeting': {'description': 'Animation retargeting with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_animation_state_machine': {'description': 'Animation state-machine direction with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_animation_runtime_qa': {'description': 'Animation runtime QA with a senior ten-year-studio craft bar.', 'category': 'animation', 'stages': ['Establish reference, emotional intent and gameplay readability', 'Inspect rig hierarchy, scale, constraints and existing clips', 'Block unmistakable key poses, silhouettes and contact points', 'Refine timing, spacing, arcs, weight, overlap and anticipation', 'Build loops, transitions, layers, masks, IK and interruption rules', 'Synchronize gameplay events, hit windows, VFX and audio cues', 'Integrate compression, retargeting, networking and runtime budgets', 'Review in gameplay camera at multiple speeds and fix every visible defect'], 'qualityGates': ['Strong poses read without context', 'Weight, balance and contacts remain believable', 'Timing supports gameplay rather than delaying it', 'Transitions have no pops, foot slides or dead frames', 'Loops preserve phase and root-motion policy', 'Events align with visible action frames', 'Retargeted/runtime output matches source intent', 'Engine capture and state-machine tests pass']}, 'ms_gui_design_studio': {'description': 'Professional GUI design studio with a senior ten-year-studio craft bar.', 'category': 'uiux', 'stages': ['Clarify the user goal, primary path and decision hierarchy', 'Inspect current design language, constraints and target inputs', 'Define tokens for type, color, spacing, radius, depth and motion', 'Build reusable components with complete interaction states', 'Compose responsive layouts for aspect ratios and localization', 'Add controller, keyboard, touch and accessibility behavior', 'Implement tasteful motion, feedback, loading and error recovery', 'Test the real flow with screenshots, navigation and usability evidence'], 'qualityGates': ['Hierarchy makes the primary action obvious', 'Components are reusable and internally consistent', 'Every state is intentional and visually finished', 'Layouts survive small screens and long localized text', 'Focus order and controller navigation have no dead ends', 'Contrast, type scale and target sizes are accessible', 'Motion feels responsive and supports reduced-motion settings', 'Final in-engine flow is functional and beautiful']}, 'ms_roblox_gui_studio': {'description': 'Roblox GUI production studio with a senior ten-year-studio craft bar.', 'category': 'uiux', 'stages': ['Clarify the user goal, primary path and decision hierarchy', 'Inspect current design language, constraints and target inputs', 'Define tokens for type, color, spacing, radius, depth and motion', 'Build reusable components with complete interaction states', 'Compose responsive layouts for aspect ratios and localization', 'Add controller, keyboard, touch and accessibility behavior', 'Implement tasteful motion, feedback, loading and error recovery', 'Test the real flow with screenshots, navigation and usability evidence'], 'qualityGates': ['Hierarchy makes the primary action obvious', 'Components are reusable and internally consistent', 'Every state is intentional and visually finished', 'Layouts survive small screens and long localized text', 'Focus order and controller navigation have no dead ends', 'Contrast, type scale and target sizes are accessible', 'Motion feels responsive and supports reduced-motion settings', 'Final in-engine flow is functional and beautiful']}, 'ms_unity_ui_studio': {'description': 'Unity UI production studio with a senior ten-year-studio craft bar.', 'category': 'uiux', 'stages': ['Clarify the user goal, primary path and decision hierarchy', 'Inspect current design language, constraints and target inputs', 'Define tokens for type, color, spacing, radius, depth and motion', 'Build reusable components with complete interaction states', 'Compose responsive layouts for aspect ratios and localization', 'Add controller, keyboard, touch and accessibility behavior', 'Implement tasteful motion, feedback, loading and error recovery', 'Test the real flow with screenshots, navigation and usability evidence'], 'qualityGates': ['Hierarchy makes the primary action obvious', 'Components are reusable and internally consistent', 'Every state is intentional and visually finished', 'Layouts survive small screens and long localized text', 'Focus order and controller navigation have no dead ends', 'Contrast, type scale and target sizes are accessible', 'Motion feels responsive and supports reduced-motion settings', 'Final in-engine flow is functional and beautiful']}, 'ms_godot_ui_studio': {'description': 'Godot UI production studio with a senior ten-year-studio craft bar.', 'category': 'uiux', 'stages': ['Clarify the user goal, primary path and decision hierarchy', 'Inspect current design language, constraints and target inputs', 'Define tokens for type, color, spacing, radius, depth and motion', 'Build reusable components with complete interaction states', 'Compose responsive layouts for aspect ratios and localization', 'Add controller, keyboard, touch and accessibility behavior', 'Implement tasteful motion, feedback, loading and error recovery', 'Test the real flow with screenshots, navigation and usability evidence'], 'qualityGates': ['Hierarchy makes the primary action obvious', 'Components are reusable and internally consistent', 'Every state is intentional and visually finished', 'Layouts survive small screens and long localized text', 'Focus order and controller navigation have no dead ends', 'Contrast, type scale and target sizes are accessible', 'Motion feels responsive and supports reduced-motion settings', 'Final in-engine flow is functional and beautiful']}, 'ms_ui_motion_design': {'description': 'UI motion and micro-interaction design with a senior ten-year-studio craft bar.', 'category': 'uiux', 'stages': ['Clarify the user goal, primary path and decision hierarchy', 'Inspect current design language, constraints and target inputs', 'Define tokens for type, color, spacing, radius, depth and motion', 'Build reusable components with complete interaction states', 'Compose responsive layouts for aspect ratios and localization', 'Add controller, keyboard, touch and accessibility behavior', 'Implement tasteful motion, feedback, loading and error recovery', 'Test the real flow with screenshots, navigation and usability evidence'], 'qualityGates': ['Hierarchy makes the primary action obvious', 'Components are reusable and internally consistent', 'Every state is intentional and visually finished', 'Layouts survive small screens and long localized text', 'Focus order and controller navigation have no dead ends', 'Contrast, type scale and target sizes are accessible', 'Motion feels responsive and supports reduced-motion settings', 'Final in-engine flow is functional and beautiful']}, 'ms_design_system_production': {'description': 'Design-system production with a senior ten-year-studio craft bar.', 'category': 'uiux', 'stages': ['Clarify the user goal, primary path and decision hierarchy', 'Inspect current design language, constraints and target inputs', 'Define tokens for type, color, spacing, radius, depth and motion', 'Build reusable components with complete interaction states', 'Compose responsive layouts for aspect ratios and localization', 'Add controller, keyboard, touch and accessibility behavior', 'Implement tasteful motion, feedback, loading and error recovery', 'Test the real flow with screenshots, navigation and usability evidence'], 'qualityGates': ['Hierarchy makes the primary action obvious', 'Components are reusable and internally consistent', 'Every state is intentional and visually finished', 'Layouts survive small screens and long localized text', 'Focus order and controller navigation have no dead ends', 'Contrast, type scale and target sizes are accessible', 'Motion feels responsive and supports reduced-motion settings', 'Final in-engine flow is functional and beautiful']}, 'ms_responsive_interface_polish': {'description': 'Responsive interface polish with a senior ten-year-studio craft bar.', 'category': 'uiux', 'stages': ['Clarify the user goal, primary path and decision hierarchy', 'Inspect current design language, constraints and target inputs', 'Define tokens for type, color, spacing, radius, depth and motion', 'Build reusable components with complete interaction states', 'Compose responsive layouts for aspect ratios and localization', 'Add controller, keyboard, touch and accessibility behavior', 'Implement tasteful motion, feedback, loading and error recovery', 'Test the real flow with screenshots, navigation and usability evidence'], 'qualityGates': ['Hierarchy makes the primary action obvious', 'Components are reusable and internally consistent', 'Every state is intentional and visually finished', 'Layouts survive small screens and long localized text', 'Focus order and controller navigation have no dead ends', 'Contrast, type scale and target sizes are accessible', 'Motion feels responsive and supports reduced-motion settings', 'Final in-engine flow is functional and beautiful']}, 'ms_controller_navigation_ux': {'description': 'Controller-navigation UX with a senior ten-year-studio craft bar.', 'category': 'uiux', 'stages': ['Clarify the user goal, primary path and decision hierarchy', 'Inspect current design language, constraints and target inputs', 'Define tokens for type, color, spacing, radius, depth and motion', 'Build reusable components with complete interaction states', 'Compose responsive layouts for aspect ratios and localization', 'Add controller, keyboard, touch and accessibility behavior', 'Implement tasteful motion, feedback, loading and error recovery', 'Test the real flow with screenshots, navigation and usability evidence'], 'qualityGates': ['Hierarchy makes the primary action obvious', 'Components are reusable and internally consistent', 'Every state is intentional and visually finished', 'Layouts survive small screens and long localized text', 'Focus order and controller navigation have no dead ends', 'Contrast, type scale and target sizes are accessible', 'Motion feels responsive and supports reduced-motion settings', 'Final in-engine flow is functional and beautiful']}, 'ms_accessible_interface_polish': {'description': 'Accessible interface polish with a senior ten-year-studio craft bar.', 'category': 'uiux', 'stages': ['Clarify the user goal, primary path and decision hierarchy', 'Inspect current design language, constraints and target inputs', 'Define tokens for type, color, spacing, radius, depth and motion', 'Build reusable components with complete interaction states', 'Compose responsive layouts for aspect ratios and localization', 'Add controller, keyboard, touch and accessibility behavior', 'Implement tasteful motion, feedback, loading and error recovery', 'Test the real flow with screenshots, navigation and usability evidence'], 'qualityGates': ['Hierarchy makes the primary action obvious', 'Components are reusable and internally consistent', 'Every state is intentional and visually finished', 'Layouts survive small screens and long localized text', 'Focus order and controller navigation have no dead ends', 'Contrast, type scale and target sizes are accessible', 'Motion feels responsive and supports reduced-motion settings', 'Final in-engine flow is functional and beautiful']}, 'ms_usability_polish': {'description': 'Usability and flow polish with a senior ten-year-studio craft bar.', 'category': 'uiux', 'stages': ['Clarify the user goal, primary path and decision hierarchy', 'Inspect current design language, constraints and target inputs', 'Define tokens for type, color, spacing, radius, depth and motion', 'Build reusable components with complete interaction states', 'Compose responsive layouts for aspect ratios and localization', 'Add controller, keyboard, touch and accessibility behavior', 'Implement tasteful motion, feedback, loading and error recovery', 'Test the real flow with screenshots, navigation and usability evidence'], 'qualityGates': ['Hierarchy makes the primary action obvious', 'Components are reusable and internally consistent', 'Every state is intentional and visually finished', 'Layouts survive small screens and long localized text', 'Focus order and controller navigation have no dead ends', 'Contrast, type scale and target sizes are accessible', 'Motion feels responsive and supports reduced-motion settings', 'Final in-engine flow is functional and beautiful']}, 'ms_blender_model_studio': {'description': 'Blender model studio with a senior ten-year-studio craft bar. Chooses the primitive per feature rather than defaulting to a sphere, and blocks forms that read before detailing them.', 'category': 'art3d', 'stages': ['Define art direction, references, scale and gameplay silhouette', 'Inspect target engine metrics, camera distance and asset budget', 'Decide the FORM of every distinct feature before adding geometry - call ms_form_guidance (action="audit") with the part list; a limb/shaft/pipe/neck is a cylinder, a plate/housing/crate/panel is a beveled box, anything path-like (cable/hose/rope/tail) is a swept Bezier curve, anything defined by its outline (gear/bracket/beam/blade) is an extruded profile, and a sphere is reserved for genuinely round parts only (eyeball, ball joint, planet, ball, berry, knob, dome)', 'Block primary forms with those correct primitives, then establish proportion, composition and value structure - bevel silhouette edges and taper cylinders so the blockout already reads as the final object rather than as placeholder primitives', 'Refine topology, deformation, UVs, pivots and modular boundaries', 'Author coherent materials, textures and controlled detail hierarchy', 'Create lighting and presentation that supports the intended mood', 'Export and integrate correct scale, axes, collisions, LODs and shaders', 'Validate from gameplay view and optimize without losing the art target'], 'qualityGates': ['Every part uses a form appropriate to what it is - no sphere standing in for a limb, plate or cable', 'The blockout reads as the intended object before any detail or material is added', 'Silhouette and focal hierarchy read at gameplay distance', 'Topology, normals and UVs are technically clean', 'Material response is coherent under representative lighting', 'Detail density supports—not fights—the focal point', 'Scale, pivot, collision and orientation import correctly', 'LODs and compression preserve quality within budget', 'Asset matches the surrounding project art language', 'Final engine capture meets the reference bar']}, 'ms_stylized_art_production': {'description': 'Stylized art production with a senior ten-year-studio craft bar.', 'category': 'art3d', 'stages': ['Define art direction, references, scale and gameplay silhouette', 'Inspect target engine metrics, camera distance and asset budget', 'Block primary forms, proportion, composition and value structure', 'Refine topology, deformation, UVs, pivots and modular boundaries', 'Author coherent materials, textures and controlled detail hierarchy', 'Create lighting and presentation that supports the intended mood', 'Export and integrate correct scale, axes, collisions, LODs and shaders', 'Validate from gameplay view and optimize without losing the art target'], 'qualityGates': ['Silhouette and focal hierarchy read at gameplay distance', 'Topology, normals and UVs are technically clean', 'Material response is coherent under representative lighting', 'Detail density supports—not fights—the focal point', 'Scale, pivot, collision and orientation import correctly', 'LODs and compression preserve quality within budget', 'Asset matches the surrounding project art language', 'Final engine capture meets the reference bar']}, 'ms_realistic_art_production': {'description': 'Realistic art production with a senior ten-year-studio craft bar.', 'category': 'art3d', 'stages': ['Define art direction, references, scale and gameplay silhouette', 'Inspect target engine metrics, camera distance and asset budget', 'Block primary forms, proportion, composition and value structure', 'Refine topology, deformation, UVs, pivots and modular boundaries', 'Author coherent materials, textures and controlled detail hierarchy', 'Create lighting and presentation that supports the intended mood', 'Export and integrate correct scale, axes, collisions, LODs and shaders', 'Validate from gameplay view and optimize without losing the art target'], 'qualityGates': ['Silhouette and focal hierarchy read at gameplay distance', 'Topology, normals and UVs are technically clean', 'Material response is coherent under representative lighting', 'Detail density supports—not fights—the focal point', 'Scale, pivot, collision and orientation import correctly', 'LODs and compression preserve quality within budget', 'Asset matches the surrounding project art language', 'Final engine capture meets the reference bar']}, 'ms_environment_art_studio': {'description': 'Environment art studio with a senior ten-year-studio craft bar.', 'category': 'art3d', 'stages': ['Define art direction, references, scale and gameplay silhouette', 'Inspect target engine metrics, camera distance and asset budget', 'Block primary forms, proportion, composition and value structure', 'Refine topology, deformation, UVs, pivots and modular boundaries', 'Author coherent materials, textures and controlled detail hierarchy', 'Create lighting and presentation that supports the intended mood', 'Export and integrate correct scale, axes, collisions, LODs and shaders', 'Validate from gameplay view and optimize without losing the art target'], 'qualityGates': ['Silhouette and focal hierarchy read at gameplay distance', 'Topology, normals and UVs are technically clean', 'Material response is coherent under representative lighting', 'Detail density supports—not fights—the focal point', 'Scale, pivot, collision and orientation import correctly', 'LODs and compression preserve quality within budget', 'Asset matches the surrounding project art language', 'Final engine capture meets the reference bar']}, 'ms_character_art_studio': {'description': 'Character art studio with a senior ten-year-studio craft bar.', 'category': 'art3d', 'stages': ['Define art direction, references, scale and gameplay silhouette', 'Inspect target engine metrics, camera distance and asset budget', 'Block primary forms, proportion, composition and value structure', 'Refine topology, deformation, UVs, pivots and modular boundaries', 'Author coherent materials, textures and controlled detail hierarchy', 'Create lighting and presentation that supports the intended mood', 'Export and integrate correct scale, axes, collisions, LODs and shaders', 'Validate from gameplay view and optimize without losing the art target'], 'qualityGates': ['Silhouette and focal hierarchy read at gameplay distance', 'Topology, normals and UVs are technically clean', 'Material response is coherent under representative lighting', 'Detail density supports—not fights—the focal point', 'Scale, pivot, collision and orientation import correctly', 'LODs and compression preserve quality within budget', 'Asset matches the surrounding project art language', 'Final engine capture meets the reference bar']}, 'ms_prop_art_studio': {'description': 'Prop art studio with a senior ten-year-studio craft bar.', 'category': 'art3d', 'stages': ['Define art direction, references, scale and gameplay silhouette', 'Inspect target engine metrics, camera distance and asset budget', 'Block primary forms, proportion, composition and value structure', 'Refine topology, deformation, UVs, pivots and modular boundaries', 'Author coherent materials, textures and controlled detail hierarchy', 'Create lighting and presentation that supports the intended mood', 'Export and integrate correct scale, axes, collisions, LODs and shaders', 'Validate from gameplay view and optimize without losing the art target'], 'qualityGates': ['Silhouette and focal hierarchy read at gameplay distance', 'Topology, normals and UVs are technically clean', 'Material response is coherent under representative lighting', 'Detail density supports—not fights—the focal point', 'Scale, pivot, collision and orientation import correctly', 'LODs and compression preserve quality within budget', 'Asset matches the surrounding project art language', 'Final engine capture meets the reference bar']}, 'ms_pbr_material_studio': {'description': 'PBR material studio with a senior ten-year-studio craft bar.', 'category': 'art3d', 'stages': ['Define art direction, references, scale and gameplay silhouette', 'Inspect target engine metrics, camera distance and asset budget', 'Block primary forms, proportion, composition and value structure', 'Refine topology, deformation, UVs, pivots and modular boundaries', 'Author coherent materials, textures and controlled detail hierarchy', 'Create lighting and presentation that supports the intended mood', 'Export and integrate correct scale, axes, collisions, LODs and shaders', 'Validate from gameplay view and optimize without losing the art target'], 'qualityGates': ['Silhouette and focal hierarchy read at gameplay distance', 'Topology, normals and UVs are technically clean', 'Material response is coherent under representative lighting', 'Detail density supports—not fights—the focal point', 'Scale, pivot, collision and orientation import correctly', 'LODs and compression preserve quality within budget', 'Asset matches the surrounding project art language', 'Final engine capture meets the reference bar']}, 'ms_texture_detail_polish': {'description': 'Texture detail polish with a senior ten-year-studio craft bar.', 'category': 'art3d', 'stages': ['Define art direction, references, scale and gameplay silhouette', 'Inspect target engine metrics, camera distance and asset budget', 'Block primary forms, proportion, composition and value structure', 'Refine topology, deformation, UVs, pivots and modular boundaries', 'Author coherent materials, textures and controlled detail hierarchy', 'Create lighting and presentation that supports the intended mood', 'Export and integrate correct scale, axes, collisions, LODs and shaders', 'Validate from gameplay view and optimize without losing the art target'], 'qualityGates': ['Silhouette and focal hierarchy read at gameplay distance', 'Topology, normals and UVs are technically clean', 'Material response is coherent under representative lighting', 'Detail density supports—not fights—the focal point', 'Scale, pivot, collision and orientation import correctly', 'LODs and compression preserve quality within budget', 'Asset matches the surrounding project art language', 'Final engine capture meets the reference bar']}, 'ms_lighting_art_studio': {'description': 'Lighting art studio with a senior ten-year-studio craft bar.', 'category': 'art3d', 'stages': ['Define art direction, references, scale and gameplay silhouette', 'Inspect target engine metrics, camera distance and asset budget', 'Block primary forms, proportion, composition and value structure', 'Refine topology, deformation, UVs, pivots and modular boundaries', 'Author coherent materials, textures and controlled detail hierarchy', 'Create lighting and presentation that supports the intended mood', 'Export and integrate correct scale, axes, collisions, LODs and shaders', 'Validate from gameplay view and optimize without losing the art target'], 'qualityGates': ['Silhouette and focal hierarchy read at gameplay distance', 'Topology, normals and UVs are technically clean', 'Material response is coherent under representative lighting', 'Detail density supports—not fights—the focal point', 'Scale, pivot, collision and orientation import correctly', 'LODs and compression preserve quality within budget', 'Asset matches the surrounding project art language', 'Final engine capture meets the reference bar']}, 'ms_composition_render_polish': {'description': 'Composition and render polish with a senior ten-year-studio craft bar.', 'category': 'art3d', 'stages': ['Define art direction, references, scale and gameplay silhouette', 'Inspect target engine metrics, camera distance and asset budget', 'Block primary forms, proportion, composition and value structure', 'Refine topology, deformation, UVs, pivots and modular boundaries', 'Author coherent materials, textures and controlled detail hierarchy', 'Create lighting and presentation that supports the intended mood', 'Export and integrate correct scale, axes, collisions, LODs and shaders', 'Validate from gameplay view and optimize without losing the art target'], 'qualityGates': ['Silhouette and focal hierarchy read at gameplay distance', 'Topology, normals and UVs are technically clean', 'Material response is coherent under representative lighting', 'Detail density supports—not fights—the focal point', 'Scale, pivot, collision and orientation import correctly', 'LODs and compression preserve quality within budget', 'Asset matches the surrounding project art language', 'Final engine capture meets the reference bar']}, 'ms_game_feel_director': {'description': 'Game-feel director with a senior ten-year-studio craft bar.', 'category': 'gameplay', 'stages': ['Define the player fantasy and the exact feeling to create', 'Inspect existing controls, camera, animation, feedback and metrics', 'Set measurable response, timing, acceleration and clarity targets', 'Implement the smallest complete interactive loop in the real engine', 'Layer animation, VFX, audio, haptics and camera feedback with restraint', 'Handle cancellation, failure, latency, accessibility and edge states', 'Tune with repeatable scenarios and player-facing telemetry', 'Play-test, compare against targets and iterate until the feel is cohesive'], 'qualityGates': ['Input-to-feedback latency feels immediate', 'Rules and outcomes are legible without explanation', 'Feedback is layered but never noisy', 'Difficulty and timing are fair across target inputs', 'Systems remain secure and deterministic where needed', 'Edge and interruption states recover gracefully', 'Performance remains stable under representative load', 'Play-test evidence supports the final tuning']}, 'ms_combat_feel_director': {'description': 'Combat-feel director with a senior ten-year-studio craft bar.', 'category': 'gameplay', 'stages': ['Define the player fantasy and the exact feeling to create', 'Inspect existing controls, camera, animation, feedback and metrics', 'Set measurable response, timing, acceleration and clarity targets', 'Implement the smallest complete interactive loop in the real engine', 'Layer animation, VFX, audio, haptics and camera feedback with restraint', 'Handle cancellation, failure, latency, accessibility and edge states', 'Tune with repeatable scenarios and player-facing telemetry', 'Play-test, compare against targets and iterate until the feel is cohesive'], 'qualityGates': ['Input-to-feedback latency feels immediate', 'Rules and outcomes are legible without explanation', 'Feedback is layered but never noisy', 'Difficulty and timing are fair across target inputs', 'Systems remain secure and deterministic where needed', 'Edge and interruption states recover gracefully', 'Performance remains stable under representative load', 'Play-test evidence supports the final tuning']}, 'ms_movement_feel_director': {'description': 'Movement-feel director with a senior ten-year-studio craft bar.', 'category': 'gameplay', 'stages': ['Define the player fantasy and the exact feeling to create', 'Inspect existing controls, camera, animation, feedback and metrics', 'Set measurable response, timing, acceleration and clarity targets', 'Implement the smallest complete interactive loop in the real engine', 'Layer animation, VFX, audio, haptics and camera feedback with restraint', 'Handle cancellation, failure, latency, accessibility and edge states', 'Tune with repeatable scenarios and player-facing telemetry', 'Play-test, compare against targets and iterate until the feel is cohesive'], 'qualityGates': ['Input-to-feedback latency feels immediate', 'Rules and outcomes are legible without explanation', 'Feedback is layered but never noisy', 'Difficulty and timing are fair across target inputs', 'Systems remain secure and deterministic where needed', 'Edge and interruption states recover gracefully', 'Performance remains stable under representative load', 'Play-test evidence supports the final tuning']}, 'ms_camera_feel_director': {'description': 'Camera-feel director with a senior ten-year-studio craft bar.', 'category': 'gameplay', 'stages': ['Define the player fantasy and the exact feeling to create', 'Inspect existing controls, camera, animation, feedback and metrics', 'Set measurable response, timing, acceleration and clarity targets', 'Implement the smallest complete interactive loop in the real engine', 'Layer animation, VFX, audio, haptics and camera feedback with restraint', 'Handle cancellation, failure, latency, accessibility and edge states', 'Tune with repeatable scenarios and player-facing telemetry', 'Play-test, compare against targets and iterate until the feel is cohesive'], 'qualityGates': ['Input-to-feedback latency feels immediate', 'Rules and outcomes are legible without explanation', 'Feedback is layered but never noisy', 'Difficulty and timing are fair across target inputs', 'Systems remain secure and deterministic where needed', 'Edge and interruption states recover gracefully', 'Performance remains stable under representative load', 'Play-test evidence supports the final tuning']}, 'ms_onboarding_experience_polish': {'description': 'Onboarding experience polish with a senior ten-year-studio craft bar.', 'category': 'gameplay', 'stages': ['Define the player fantasy and the exact feeling to create', 'Inspect existing controls, camera, animation, feedback and metrics', 'Set measurable response, timing, acceleration and clarity targets', 'Implement the smallest complete interactive loop in the real engine', 'Layer animation, VFX, audio, haptics and camera feedback with restraint', 'Handle cancellation, failure, latency, accessibility and edge states', 'Tune with repeatable scenarios and player-facing telemetry', 'Play-test, compare against targets and iterate until the feel is cohesive'], 'qualityGates': ['Input-to-feedback latency feels immediate', 'Rules and outcomes are legible without explanation', 'Feedback is layered but never noisy', 'Difficulty and timing are fair across target inputs', 'Systems remain secure and deterministic where needed', 'Edge and interruption states recover gracefully', 'Performance remains stable under representative load', 'Play-test evidence supports the final tuning']}, 'ms_economy_experience_polish': {'description': 'Economy experience polish with a senior ten-year-studio craft bar.', 'category': 'gameplay', 'stages': ['Define the player fantasy and the exact feeling to create', 'Inspect existing controls, camera, animation, feedback and metrics', 'Set measurable response, timing, acceleration and clarity targets', 'Implement the smallest complete interactive loop in the real engine', 'Layer animation, VFX, audio, haptics and camera feedback with restraint', 'Handle cancellation, failure, latency, accessibility and edge states', 'Tune with repeatable scenarios and player-facing telemetry', 'Play-test, compare against targets and iterate until the feel is cohesive'], 'qualityGates': ['Input-to-feedback latency feels immediate', 'Rules and outcomes are legible without explanation', 'Feedback is layered but never noisy', 'Difficulty and timing are fair across target inputs', 'Systems remain secure and deterministic where needed', 'Edge and interruption states recover gracefully', 'Performance remains stable under representative load', 'Play-test evidence supports the final tuning']}, 'ms_social_experience_polish': {'description': 'Social experience polish with a senior ten-year-studio craft bar.', 'category': 'gameplay', 'stages': ['Define the player fantasy and the exact feeling to create', 'Inspect existing controls, camera, animation, feedback and metrics', 'Set measurable response, timing, acceleration and clarity targets', 'Implement the smallest complete interactive loop in the real engine', 'Layer animation, VFX, audio, haptics and camera feedback with restraint', 'Handle cancellation, failure, latency, accessibility and edge states', 'Tune with repeatable scenarios and player-facing telemetry', 'Play-test, compare against targets and iterate until the feel is cohesive'], 'qualityGates': ['Input-to-feedback latency feels immediate', 'Rules and outcomes are legible without explanation', 'Feedback is layered but never noisy', 'Difficulty and timing are fair across target inputs', 'Systems remain secure and deterministic where needed', 'Edge and interruption states recover gracefully', 'Performance remains stable under representative load', 'Play-test evidence supports the final tuning']}, 'ms_progression_experience_polish': {'description': 'Progression experience polish with a senior ten-year-studio craft bar.', 'category': 'gameplay', 'stages': ['Define the player fantasy and the exact feeling to create', 'Inspect existing controls, camera, animation, feedback and metrics', 'Set measurable response, timing, acceleration and clarity targets', 'Implement the smallest complete interactive loop in the real engine', 'Layer animation, VFX, audio, haptics and camera feedback with restraint', 'Handle cancellation, failure, latency, accessibility and edge states', 'Tune with repeatable scenarios and player-facing telemetry', 'Play-test, compare against targets and iterate until the feel is cohesive'], 'qualityGates': ['Input-to-feedback latency feels immediate', 'Rules and outcomes are legible without explanation', 'Feedback is layered but never noisy', 'Difficulty and timing are fair across target inputs', 'Systems remain secure and deterministic where needed', 'Edge and interruption states recover gracefully', 'Performance remains stable under representative load', 'Play-test evidence supports the final tuning']}, 'ms_studio_critic_loop': {'description': 'Studio-grade critic loop with a senior ten-year-studio craft bar.', 'category': 'quality', 'stages': ['Restate the user-visible acceptance criteria and quality target', 'Inspect the real artifact, project state and current evidence', 'Evaluate craft, usability, correctness, cohesion and technical risk', 'Find the highest-impact defects instead of listing cosmetic trivia', 'Fix blocking and high-value issues in the actual target project', 'Retest happy, edge, failure, accessibility and performance paths', 'Compare before/after evidence against the requested outcome', 'Approve only when evidence is concrete; otherwise return precise revisions'], 'qualityGates': ['No plan or generated text is mistaken for the deliverable', 'The requested artifact exists and works end to end', 'Visual and interaction quality is coherent', 'Known edge states are handled honestly', 'Logs and focused tests are clean', 'Performance meets an explicit target-tier budget', 'Final state is read back from the engine', 'Remaining limitations are disclosed rather than hidden']}, 'ms_visual_quality_audit': {'description': 'Visual quality audit with a senior ten-year-studio craft bar.', 'category': 'quality', 'stages': ['Restate the user-visible acceptance criteria and quality target', 'Inspect the real artifact, project state and current evidence', 'Evaluate craft, usability, correctness, cohesion and technical risk', 'Find the highest-impact defects instead of listing cosmetic trivia', 'Fix blocking and high-value issues in the actual target project', 'Retest happy, edge, failure, accessibility and performance paths', 'Compare before/after evidence against the requested outcome', 'Approve only when evidence is concrete; otherwise return precise revisions'], 'qualityGates': ['No plan or generated text is mistaken for the deliverable', 'The requested artifact exists and works end to end', 'Visual and interaction quality is coherent', 'Known edge states are handled honestly', 'Logs and focused tests are clean', 'Performance meets an explicit target-tier budget', 'Final state is read back from the engine', 'Remaining limitations are disclosed rather than hidden']}, 'ms_ui_quality_audit': {'description': 'UI quality audit with a senior ten-year-studio craft bar.', 'category': 'quality', 'stages': ['Restate the user-visible acceptance criteria and quality target', 'Inspect the real artifact, project state and current evidence', 'Evaluate craft, usability, correctness, cohesion and technical risk', 'Find the highest-impact defects instead of listing cosmetic trivia', 'Fix blocking and high-value issues in the actual target project', 'Retest happy, edge, failure, accessibility and performance paths', 'Compare before/after evidence against the requested outcome', 'Approve only when evidence is concrete; otherwise return precise revisions'], 'qualityGates': ['No plan or generated text is mistaken for the deliverable', 'The requested artifact exists and works end to end', 'Visual and interaction quality is coherent', 'Known edge states are handled honestly', 'Logs and focused tests are clean', 'Performance meets an explicit target-tier budget', 'Final state is read back from the engine', 'Remaining limitations are disclosed rather than hidden']}, 'ms_gameplay_quality_audit': {'description': 'Gameplay quality audit with a senior ten-year-studio craft bar.', 'category': 'quality', 'stages': ['Restate the user-visible acceptance criteria and quality target', 'Inspect the real artifact, project state and current evidence', 'Evaluate craft, usability, correctness, cohesion and technical risk', 'Find the highest-impact defects instead of listing cosmetic trivia', 'Fix blocking and high-value issues in the actual target project', 'Retest happy, edge, failure, accessibility and performance paths', 'Compare before/after evidence against the requested outcome', 'Approve only when evidence is concrete; otherwise return precise revisions'], 'qualityGates': ['No plan or generated text is mistaken for the deliverable', 'The requested artifact exists and works end to end', 'Visual and interaction quality is coherent', 'Known edge states are handled honestly', 'Logs and focused tests are clean', 'Performance meets an explicit target-tier budget', 'Final state is read back from the engine', 'Remaining limitations are disclosed rather than hidden']}, 'ms_performance_quality_audit': {'description': 'Performance quality audit with a senior ten-year-studio craft bar.', 'category': 'quality', 'stages': ['Restate the user-visible acceptance criteria and quality target', 'Inspect the real artifact, project state and current evidence', 'Evaluate craft, usability, correctness, cohesion and technical risk', 'Find the highest-impact defects instead of listing cosmetic trivia', 'Fix blocking and high-value issues in the actual target project', 'Retest happy, edge, failure, accessibility and performance paths', 'Compare before/after evidence against the requested outcome', 'Approve only when evidence is concrete; otherwise return precise revisions'], 'qualityGates': ['No plan or generated text is mistaken for the deliverable', 'The requested artifact exists and works end to end', 'Visual and interaction quality is coherent', 'Known edge states are handled honestly', 'Logs and focused tests are clean', 'Performance meets an explicit target-tier budget', 'Final state is read back from the engine', 'Remaining limitations are disclosed rather than hidden']}, 'ms_cross_engine_integration_audit': {'description': 'Cross-engine integration audit with a senior ten-year-studio craft bar.', 'category': 'quality', 'stages': ['Restate the user-visible acceptance criteria and quality target', 'Inspect the real artifact, project state and current evidence', 'Evaluate craft, usability, correctness, cohesion and technical risk', 'Find the highest-impact defects instead of listing cosmetic trivia', 'Fix blocking and high-value issues in the actual target project', 'Retest happy, edge, failure, accessibility and performance paths', 'Compare before/after evidence against the requested outcome', 'Approve only when evidence is concrete; otherwise return precise revisions'], 'qualityGates': ['No plan or generated text is mistaken for the deliverable', 'The requested artifact exists and works end to end', 'Visual and interaction quality is coherent', 'Known edge states are handled honestly', 'Logs and focused tests are clean', 'Performance meets an explicit target-tier budget', 'Final state is read back from the engine', 'Remaining limitations are disclosed rather than hidden']}, 'ms_release_quality_bar': {'description': 'Release quality bar with a senior ten-year-studio craft bar.', 'category': 'quality', 'stages': ['Restate the user-visible acceptance criteria and quality target', 'Inspect the real artifact, project state and current evidence', 'Evaluate craft, usability, correctness, cohesion and technical risk', 'Find the highest-impact defects instead of listing cosmetic trivia', 'Fix blocking and high-value issues in the actual target project', 'Retest happy, edge, failure, accessibility and performance paths', 'Compare before/after evidence against the requested outcome', 'Approve only when evidence is concrete; otherwise return precise revisions'], 'qualityGates': ['No plan or generated text is mistaken for the deliverable', 'The requested artifact exists and works end to end', 'Visual and interaction quality is coherent', 'Known edge states are handled honestly', 'Logs and focused tests are clean', 'Performance meets an explicit target-tier budget', 'Final state is read back from the engine', 'Remaining limitations are disclosed rather than hidden']}}
ROBLOX_STUDIO_V3_CONTRACTS = {'ms_roblox_datamodel_architecture': {'description': 'Roblox Studio specialist for DataModel architecture, service boundaries, boot order, lifecycle and dependency direction.', 'category': 'architecture', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for DataModel architecture, service boundaries, boot order, lifecycle and dependency direction', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for DataModel architecture, service boundaries, boot order, lifecycle and dependency direction with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_remote_contract_security': {'description': 'Roblox Studio specialist for RemoteEvent/RemoteFunction schemas, authority, validation, rate limits and exploit tests.', 'category': 'quality', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for RemoteEvent/RemoteFunction schemas, authority, validation, rate limits and exploit tests', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for RemoteEvent/RemoteFunction schemas, authority, validation, rate limits and exploit tests with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_streaming_world_optimizer': {'description': 'Roblox Studio specialist for StreamingEnabled regions, persistent models, atomic content, preload priorities and seam recovery.', 'category': 'quality', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for StreamingEnabled regions, persistent models, atomic content, preload priorities and seam recovery', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for StreamingEnabled regions, persistent models, atomic content, preload priorities and seam recovery with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_parallel_luau_planner': {'description': 'Roblox Studio specialist for Parallel Luau suitability, Actor boundaries, synchronization points, thread safety and measured speedup.', 'category': 'quality', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for Parallel Luau suitability, Actor boundaries, synchronization points, thread safety and measured speedup', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for Parallel Luau suitability, Actor boundaries, synchronization points, thread safety and measured speedup with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_actor_partition_audit': {'description': 'Roblox Studio specialist for Actor partitioning, ownership, message flow, isolation, contention and deterministic fallback.', 'category': 'architecture', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for Actor partitioning, ownership, message flow, isolation, contention and deterministic fallback', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for Actor partitioning, ownership, message flow, isolation, contention and deterministic fallback with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_datastore_resilience': {'description': 'Roblox Studio specialist for DataStore schemas, UpdateAsync transforms, session locks, migrations, retries, budgets and repair.', 'category': 'gameplay', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for DataStore schemas, UpdateAsync transforms, session locks, migrations, retries, budgets and repair', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for DataStore schemas, UpdateAsync transforms, session locks, migrations, retries, budgets and repair with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_memory_store_coordination': {'description': 'Roblox Studio specialist for MemoryStore queues, maps, sorted maps, TTLs, idempotency, contention and degradation.', 'category': 'gameplay', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for MemoryStore queues, maps, sorted maps, TTLs, idempotency, contention and degradation', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for MemoryStore queues, maps, sorted maps, TTLs, idempotency, contention and degradation with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_messaging_service_reliability': {'description': 'Roblox Studio specialist for MessagingService topics, deduplication, ordering, retry, payload limits and fallback.', 'category': 'gameplay', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for MessagingService topics, deduplication, ordering, retry, payload limits and fallback', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for MessagingService topics, deduplication, ordering, retry, payload limits and fallback with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_character_pipeline': {'description': 'Roblox Studio specialist for R6/R15/custom rigs, Humanoid/AnimationController ownership, avatar scaling, accessories and respawn.', 'category': 'animation', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for R6/R15/custom rigs, Humanoid/AnimationController ownership, avatar scaling, accessories and respawn', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for R6/R15/custom rigs, Humanoid/AnimationController ownership, avatar scaling, accessories and respawn with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_animation_runtime_pipeline': {'description': 'Roblox Studio specialist for Animator ownership, priorities, blending, markers, replication, interruption and cleanup.', 'category': 'animation', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for Animator ownership, priorities, blending, markers, replication, interruption and cleanup', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for Animator ownership, priorities, blending, markers, replication, interruption and cleanup with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_ui_responsiveness_audit': {'description': 'Roblox Studio specialist for ScreenGui hierarchy, constraints, safe areas, text scaling, localization, states and navigation.', 'category': 'uiux', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for ScreenGui hierarchy, constraints, safe areas, text scaling, localization, states and navigation', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for ScreenGui hierarchy, constraints, safe areas, text scaling, localization, states and navigation with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_mobile_input_polish': {'description': 'Roblox Studio specialist for touch controls, thumb reach, ContextActionService, gesture conflict, orientation and low-end devices.', 'category': 'uiux', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for touch controls, thumb reach, ContextActionService, gesture conflict, orientation and low-end devices', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for touch controls, thumb reach, ContextActionService, gesture conflict, orientation and low-end devices with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_console_input_polish': {'description': 'Roblox Studio specialist for gamepad action maps, focus graph, prompts, ten-foot readability, disconnect and reconnect.', 'category': 'uiux', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for gamepad action maps, focus graph, prompts, ten-foot readability, disconnect and reconnect', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for gamepad action maps, focus graph, prompts, ten-foot readability, disconnect and reconnect with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_vr_comfort_review': {'description': 'Roblox Studio specialist for VR scale, locomotion, comfort, interaction reach, seated/standing modes and frame budget.', 'category': 'gameplay', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for VR scale, locomotion, comfort, interaction reach, seated/standing modes and frame budget', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for VR scale, locomotion, comfort, interaction reach, seated/standing modes and frame budget with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_physics_network_ownership': {'description': 'Roblox Studio specialist for assemblies, constraints, collision groups, network ownership, reconciliation and exploit resistance.', 'category': 'gameplay', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for assemblies, constraints, collision groups, network ownership, reconciliation and exploit resistance', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for assemblies, constraints, collision groups, network ownership, reconciliation and exploit resistance with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_pathfinding_npc_scale': {'description': 'Roblox Studio specialist for PathfindingService costs, nav modifiers, blocked recovery, crowd coordination and simulation LOD.', 'category': 'gameplay', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for PathfindingService costs, nav modifiers, blocked recovery, crowd coordination and simulation LOD', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for PathfindingService costs, nav modifiers, blocked recovery, crowd coordination and simulation LOD with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_microprofiler_optimization': {'description': 'Roblox Studio specialist for MicroProfiler labels, CPU frame decomposition, scheduler pressure, spikes and before/after captures.', 'category': 'quality', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for MicroProfiler labels, CPU frame decomposition, scheduler pressure, spikes and before/after captures', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for MicroProfiler labels, CPU frame decomposition, scheduler pressure, spikes and before/after captures with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_render_budget_audit': {'description': 'Roblox Studio specialist for parts, meshes, materials, transparency, lights, particles, draw pressure and device tiers.', 'category': 'art3d', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for parts, meshes, materials, transparency, lights, particles, draw pressure and device tiers', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for parts, meshes, materials, transparency, lights, particles, draw pressure and device tiers with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_asset_delivery_pipeline': {'description': 'Roblox Studio specialist for asset ownership, import validation, moderation states, preload, fallbacks, memory and versioning.', 'category': 'art3d', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for asset ownership, import validation, moderation states, preload, fallbacks, memory and versioning', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for asset ownership, import validation, moderation states, preload, fallbacks, memory and versioning with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_liveops_rollout': {'description': 'Roblox Studio specialist for server-authoritative config, events, staged rollout, kill switches, telemetry and rollback.', 'category': 'gameplay', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for server-authoritative config, events, staged rollout, kill switches, telemetry and rollback', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for server-authoritative config, events, staged rollout, kill switches, telemetry and rollback with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_monetization_integrity': {'description': 'Roblox Studio specialist for MarketplaceService receipts, entitlements, idempotent grants, regional rules and recovery.', 'category': 'gameplay', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for MarketplaceService receipts, entitlements, idempotent grants, regional rules and recovery', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for MarketplaceService receipts, entitlements, idempotent grants, regional rules and recovery with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_localization_pipeline': {'description': 'Roblox Studio specialist for LocalizationService keys, translators, fonts, expansion, RTL resilience and locale QA.', 'category': 'uiux', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for LocalizationService keys, translators, fonts, expansion, RTL resilience and locale QA', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for LocalizationService keys, translators, fonts, expansion, RTL resilience and locale QA with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_accessibility_playtest': {'description': 'Roblox Studio specialist for input alternatives, contrast, text, motion, audio cues, cognitive load and device testing.', 'category': 'quality', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for input alternatives, contrast, text, motion, audio cues, cognitive load and device testing', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for input alternatives, contrast, text, motion, audio cues, cognitive load and device testing with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}, 'ms_roblox_multi_client_test_director': {'description': 'Roblox Studio specialist for Studio server/client matrix, latency, reconnect, authority conflicts, persistence and clean Output.', 'category': 'quality', 'stages': ['Define the requested player outcome and Roblox acceptance criteria for Studio server/client matrix, latency, reconnect, authority conflicts, persistence and clean Output', 'Inspect the live DataModel, relevant scripts, services, remotes, assets, settings and current conventions', 'Read exact advertised Roblox Studio MCP schemas and choose rollback-safe native operations', 'Design the production implementation for Studio server/client matrix, latency, reconnect, authority conflicts, persistence and clean Output with explicit server/client/editor ownership', 'Implement the real change in Studio without replacing existing architecture or explicit intent', 'Integrate gameplay, UI, animation, VFX, audio, persistence and platform behavior wherever connected', 'Exercise failure, interruption, exploit, respawn, reconnect, streaming and weakest-device cases where relevant', 'Run Edit/Server/Client evidence, inspect Output and profiler/network state, fix defects and read back final hierarchy'], 'qualityGates': ['Exact Roblox services, APIs, instance paths and ownership are verified before edits', 'Server authority and every client-controlled value are validated where consequential', 'Connections, tasks, instances, animations and resources have deterministic lifecycle cleanup', 'Streaming, respawn, teleport, reconnect and late-join behavior remain correct where relevant', 'Keyboard/mouse, touch and gamepad behavior is complete where relevant', 'Weak-device CPU, GPU, memory, network and loading budgets are measured', 'Studio Output and focused multi-client tests contain no unexplained failures', 'Final DataModel state and runtime evidence prove the requested result']}}
ADVANCED_DIRECT_CONTRACTS.update(ROBLOX_STUDIO_V3_CONTRACTS)
ENGINE_PRO_V3_CONTRACTS = {'ms_unity_dots_ecs_architecture': {'description': 'Unity specialist for DOTS/ECS worlds, systems, bakers, jobs, Burst safety and structural-change budgets.', 'category': 'quality', 'engine': 'unity', 'stages': ['Define the requested result and acceptance criteria for DOTS/ECS worlds, systems, bakers, jobs, Burst safety and structural-change budgets', 'Inspect the live project, dependencies, settings, assets and established conventions', 'Read exact advertised native tool schemas and select rollback-safe operations', 'Design ownership, data flow, lifecycle, error handling and target-platform budgets', 'Implement the real project change through live native tools while preserving explicit requirements', 'Integrate connected gameplay, UI, animation, VFX, audio, content and build behavior', 'Exercise failure, interruption, migration, compatibility and weakest-device cases', 'Run native tests and profiler evidence, inspect logs, read back final project state and fix defects'], 'qualityGates': ['Exact project paths, APIs, versions and ownership are verified', 'The result exists in the real project rather than only as advice', 'Lifecycle, cleanup, interruption and failure recovery are deterministic', 'Inputs, persistence and network authority are validated where consequential', 'Connected disciplines and target platforms remain coherent', 'CPU, GPU, memory, loading and network budgets are measured where relevant', 'Native tests and logs contain no unexplained failures', 'Final state read-back and evidence prove the requested outcome']}, 'ms_unity_addressables_delivery': {'description': 'Unity specialist for Addressables groups, dependency duplication, remote catalogs, memory, preload and rollback.', 'category': 'quality', 'engine': 'unity', 'stages': ['Define the requested result and acceptance criteria for Addressables groups, dependency duplication, remote catalogs, memory, preload and rollback', 'Inspect the live project, dependencies, settings, assets and established conventions', 'Read exact advertised native tool schemas and select rollback-safe operations', 'Design ownership, data flow, lifecycle, error handling and target-platform budgets', 'Implement the real project change through live native tools while preserving explicit requirements', 'Integrate connected gameplay, UI, animation, VFX, audio, content and build behavior', 'Exercise failure, interruption, migration, compatibility and weakest-device cases', 'Run native tests and profiler evidence, inspect logs, read back final project state and fix defects'], 'qualityGates': ['Exact project paths, APIs, versions and ownership are verified', 'The result exists in the real project rather than only as advice', 'Lifecycle, cleanup, interruption and failure recovery are deterministic', 'Inputs, persistence and network authority are validated where consequential', 'Connected disciplines and target platforms remain coherent', 'CPU, GPU, memory, loading and network budgets are measured where relevant', 'Native tests and logs contain no unexplained failures', 'Final state read-back and evidence prove the requested outcome']}, 'ms_unity_render_pipeline_profiler': {'description': 'Unity specialist for URP/HDRP rendering, SRP Batcher, overdraw, shader variants and GPU captures.', 'category': 'quality', 'engine': 'unity', 'stages': ['Define the requested result and acceptance criteria for URP/HDRP rendering, SRP Batcher, overdraw, shader variants and GPU captures', 'Inspect the live project, dependencies, settings, assets and established conventions', 'Read exact advertised native tool schemas and select rollback-safe operations', 'Design ownership, data flow, lifecycle, error handling and target-platform budgets', 'Implement the real project change through live native tools while preserving explicit requirements', 'Integrate connected gameplay, UI, animation, VFX, audio, content and build behavior', 'Exercise failure, interruption, migration, compatibility and weakest-device cases', 'Run native tests and profiler evidence, inspect logs, read back final project state and fix defects'], 'qualityGates': ['Exact project paths, APIs, versions and ownership are verified', 'The result exists in the real project rather than only as advice', 'Lifecycle, cleanup, interruption and failure recovery are deterministic', 'Inputs, persistence and network authority are validated where consequential', 'Connected disciplines and target platforms remain coherent', 'CPU, GPU, memory, loading and network budgets are measured where relevant', 'Native tests and logs contain no unexplained failures', 'Final state read-back and evidence prove the requested outcome']}, 'ms_unity_netcode_authority': {'description': 'Unity specialist for Netcode authority, prediction, reconciliation, RPC validation and bandwidth.', 'category': 'quality', 'engine': 'unity', 'stages': ['Define the requested result and acceptance criteria for Netcode authority, prediction, reconciliation, RPC validation and bandwidth', 'Inspect the live project, dependencies, settings, assets and established conventions', 'Read exact advertised native tool schemas and select rollback-safe operations', 'Design ownership, data flow, lifecycle, error handling and target-platform budgets', 'Implement the real project change through live native tools while preserving explicit requirements', 'Integrate connected gameplay, UI, animation, VFX, audio, content and build behavior', 'Exercise failure, interruption, migration, compatibility and weakest-device cases', 'Run native tests and profiler evidence, inspect logs, read back final project state and fix defects'], 'qualityGates': ['Exact project paths, APIs, versions and ownership are verified', 'The result exists in the real project rather than only as advice', 'Lifecycle, cleanup, interruption and failure recovery are deterministic', 'Inputs, persistence and network authority are validated where consequential', 'Connected disciplines and target platforms remain coherent', 'CPU, GPU, memory, loading and network budgets are measured where relevant', 'Native tests and logs contain no unexplained failures', 'Final state read-back and evidence prove the requested outcome']}, 'ms_godot_scene_signal_architecture': {'description': 'Godot specialist for scene composition, ownership, signals, autoload boundaries and typed GDScript contracts.', 'category': 'quality', 'engine': 'godot', 'stages': ['Define the requested result and acceptance criteria for scene composition, ownership, signals, autoload boundaries and typed GDScript contracts', 'Inspect the live project, dependencies, settings, assets and established conventions', 'Read exact advertised native tool schemas and select rollback-safe operations', 'Design ownership, data flow, lifecycle, error handling and target-platform budgets', 'Implement the real project change through live native tools while preserving explicit requirements', 'Integrate connected gameplay, UI, animation, VFX, audio, content and build behavior', 'Exercise failure, interruption, migration, compatibility and weakest-device cases', 'Run native tests and profiler evidence, inspect logs, read back final project state and fix defects'], 'qualityGates': ['Exact project paths, APIs, versions and ownership are verified', 'The result exists in the real project rather than only as advice', 'Lifecycle, cleanup, interruption and failure recovery are deterministic', 'Inputs, persistence and network authority are validated where consequential', 'Connected disciplines and target platforms remain coherent', 'CPU, GPU, memory, loading and network budgets are measured where relevant', 'Native tests and logs contain no unexplained failures', 'Final state read-back and evidence prove the requested outcome']}, 'ms_godot_resource_save_pipeline': {'description': 'Godot specialist for Resource schemas, persistence, migrations, import identity and deterministic recovery.', 'category': 'quality', 'engine': 'godot', 'stages': ['Define the requested result and acceptance criteria for Resource schemas, persistence, migrations, import identity and deterministic recovery', 'Inspect the live project, dependencies, settings, assets and established conventions', 'Read exact advertised native tool schemas and select rollback-safe operations', 'Design ownership, data flow, lifecycle, error handling and target-platform budgets', 'Implement the real project change through live native tools while preserving explicit requirements', 'Integrate connected gameplay, UI, animation, VFX, audio, content and build behavior', 'Exercise failure, interruption, migration, compatibility and weakest-device cases', 'Run native tests and profiler evidence, inspect logs, read back final project state and fix defects'], 'qualityGates': ['Exact project paths, APIs, versions and ownership are verified', 'The result exists in the real project rather than only as advice', 'Lifecycle, cleanup, interruption and failure recovery are deterministic', 'Inputs, persistence and network authority are validated where consequential', 'Connected disciplines and target platforms remain coherent', 'CPU, GPU, memory, loading and network budgets are measured where relevant', 'Native tests and logs contain no unexplained failures', 'Final state read-back and evidence prove the requested outcome']}, 'ms_godot_rendering_profiler': {'description': 'Godot specialist for Forward+/Mobile/Compatibility rendering, shaders, draw calls, overdraw and frame captures.', 'category': 'quality', 'engine': 'godot', 'stages': ['Define the requested result and acceptance criteria for Forward+/Mobile/Compatibility rendering, shaders, draw calls, overdraw and frame captures', 'Inspect the live project, dependencies, settings, assets and established conventions', 'Read exact advertised native tool schemas and select rollback-safe operations', 'Design ownership, data flow, lifecycle, error handling and target-platform budgets', 'Implement the real project change through live native tools while preserving explicit requirements', 'Integrate connected gameplay, UI, animation, VFX, audio, content and build behavior', 'Exercise failure, interruption, migration, compatibility and weakest-device cases', 'Run native tests and profiler evidence, inspect logs, read back final project state and fix defects'], 'qualityGates': ['Exact project paths, APIs, versions and ownership are verified', 'The result exists in the real project rather than only as advice', 'Lifecycle, cleanup, interruption and failure recovery are deterministic', 'Inputs, persistence and network authority are validated where consequential', 'Connected disciplines and target platforms remain coherent', 'CPU, GPU, memory, loading and network budgets are measured where relevant', 'Native tests and logs contain no unexplained failures', 'Final state read-back and evidence prove the requested outcome']}, 'ms_godot_multiplayer_authority': {'description': 'Godot specialist for multiplayer authority, RPC modes, synchronization, validation, latency and reconnect.', 'category': 'quality', 'engine': 'godot', 'stages': ['Define the requested result and acceptance criteria for multiplayer authority, RPC modes, synchronization, validation, latency and reconnect', 'Inspect the live project, dependencies, settings, assets and established conventions', 'Read exact advertised native tool schemas and select rollback-safe operations', 'Design ownership, data flow, lifecycle, error handling and target-platform budgets', 'Implement the real project change through live native tools while preserving explicit requirements', 'Integrate connected gameplay, UI, animation, VFX, audio, content and build behavior', 'Exercise failure, interruption, migration, compatibility and weakest-device cases', 'Run native tests and profiler evidence, inspect logs, read back final project state and fix defects'], 'qualityGates': ['Exact project paths, APIs, versions and ownership are verified', 'The result exists in the real project rather than only as advice', 'Lifecycle, cleanup, interruption and failure recovery are deterministic', 'Inputs, persistence and network authority are validated where consequential', 'Connected disciplines and target platforms remain coherent', 'CPU, GPU, memory, loading and network budgets are measured where relevant', 'Native tests and logs contain no unexplained failures', 'Final state read-back and evidence prove the requested outcome']}, 'ms_blender_render_color_pipeline': {'description': 'Blender specialist for Cycles/Eevee lighting, materials, sampling, color management, compositing and render budgets. Establishes the art target the model forms are validated against.', 'category': 'quality', 'engine': 'blender', 'stages': ['Define the intended look and the delivery constraints (still, turntable, or in-engine handoff)', 'Inspect the scene: render engine, resolution, existing lights, world and the materials already authored', 'Set colour management first - scene-referred pipeline, the right view transform and a consistent exposure - so everything after it is judged correctly', 'Author materials from the mesh\'s actual UVs and texel density rather than overriding them with flat colours', 'Light for form: a key that reveals silhouette and bevel edges, fill that holds shadow detail, and a rim or environment contribution that separates the object from the background', 'Choose sampling and denoising per engine - Cycles needs an explicit sample and denoise strategy; Eevee needs its own shadow, AO and reflection settings', 'Composite deliberately for glow, grade and vignette while keeping the raw render recoverable', 'Measure render time and memory against the budget and confirm the material reads correctly in the target engine, not only in Blender'], 'qualityGates': ['Colour management and exposure are set before material work begins', 'Materials are authored against the real UVs, not flat substitutes', 'Lighting reveals form: silhouette, bevels and surface breaks all read', 'Sampling and denoising are chosen per render engine', 'The look survives the move into the target engine', 'Render time and memory are measured against a stated budget', 'Raw render remains recoverable behind the composite', 'No unexplained black, blown-out or untextured surfaces at final capture']}, 'ms_blender_geometry_nodes_pipeline': {"description": "Blender specialist for Geometry Nodes interfaces, fields, simulation, instances, determinism and performance. Prefers instancing real modelled assets over scattering generated primitives.", "category": "quality", "engine": "blender", "stages": ["Define the requested result and acceptance criteria for the node system", "Inspect the existing node graph, its inputs, dependencies and the mesh data it consumes", "Design the graph around named Group Inputs so it is reusable and stays readable", "Build with fields (per-element data flow) rather than a mesh-in/mesh-out chain where the logic is per-point", "Instance real geometry rather than generating it in-node: point-instance a modelled asset instead of scattering spheres as \"rocks\"", "Drive all variation from explicit, seeded parameters so two runs produce identical output (determinism)", "Keep evaluation cheap: realize instances only when required, cap density, and avoid per-frame simulation on large counts", "Verify with the node graph read back, a vertex/instance count, and a re-evaluation that matches the first run"], "qualityGates": ["Graph is driven by named parameters, not hardcoded values", "Per-element logic uses fields correctly", "Scattered/instanced geometry reuses real modelled assets with correct forms", "Deterministic: the same seed gives the same result across runs", "Instance and vertex counts are within the stated budget", "No unintentional realization of large instance sets", "Graph is readable and labelled for handoff", "Re-evaluation output matches the validated first run"]}, 'ms_blender_rig_animation_pipeline': {"description": "Blender specialist for rig hierarchy, deformation, controls, actions, NLA, retargeting and export. Requires a correctly formed mesh before it will rig it.", "category": "quality", "engine": "blender", "stages": ["Define the rig scope, bone-count budget and the target engine's skeleton conventions", "Inspect the mesh first: confirm loops exist where joints will bend, and that each limb is a properly formed cylinder-like volume - a scaled sphere cannot deform cleanly", "Build the armature with a readable hierarchy: a clear root, spine and limb chains, and controls separated from deform bones", "Bind with deliberate weights and correct bone envelopes; check the shoulder, elbow, hip and knee individually rather than trusting an automatic bind", "Add constraints (IK, limits, drivers) and keep them on control bones, never on deform bones", "Author actions with usable naming and NLA strips so clips layer and blend predictably", "Set up retargeting/export mappings and verify axis and scale conventions for the target engine", "Read the pose and skin deformation back, and confirm the rest pose is preserved"], "qualityGates": ["Deform geometry supports the intended range of motion", "Rig hierarchy is readable and roles are separated", "Weights hold through extreme poses without collapse or pinching", "Controls are usable and constrained sensibly", "Actions and NLA strips are named and layer predictably", "Retarget/export preserves scale, axes and roll", "Rest pose is intact after export", "Deformation is checked in poses, not only at rest"]}, 'ms_blender_topology_modifier_pipeline': {'description': 'Blender specialist for production topology, modifiers, normals, UVs, LODs and non-destructive handoff. Form-first: checks that each part is built from the right primitive before retopologising it.', 'category': 'quality', 'engine': 'blender', 'stages': ['Define the requested result and acceptance criteria for topology, modifiers, normals, UVs and LODs', 'Inspect the live mesh: object type, vertex/face count per part and modifier stack - a part carrying a default UV sphere count has not been modelled yet', 'Check form before flow: confirm each part is a cylinder/box/extruded profile/curve where it should be, and flag any sphere that should not be one (ms_form_guidance action="audit")', 'Plan quad flow around deformation and silhouette: loops follow the form, poles are pushed away from deforming areas, no n-gons on a curved surface', 'Apply modifiers non-destructively (Bevel for edge catch, Subdivision for curves, Solidify for card thickness) and keep them live until export', 'Unwrap with deliberate seams, consistent texel density and enough padding for mip downsampling', 'Generate coherent LODs by reduction that preserves silhouette, not by uniform decimation that destroys it', 'Verify normals face outward, tangents are valid, and read the final mesh back before handoff'], 'qualityGates': ['Every part is built from a form appropriate to what it is', 'Quad flow supports deformation and reads correctly in silhouette', 'No flipped normals, stray n-gons on curved surfaces or unapplied scale', 'UV seams land in hidden areas with consistent texel density', 'LOD chain preserves silhouette at each tier', 'Modifier stack is live and export-safe', 'Mesh statistics are read back as evidence', 'Final import in the target engine shows no topology warnings']},}
ADVANCED_DIRECT_CONTRACTS.update(ENGINE_PRO_V3_CONTRACTS)



ADVANCED_DIRECT_CONTRACTS.update(STUDIO_DIRECT_CONTRACTS)
PROVIDER_QUALITY_V2_CONTRACTS = {'ms_provider_execution_optimizer': {'description': 'Provider execution optimizer: provider model context, tool choice, command precision and verified completion.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_context_budget_optimizer': {'description': 'Context budget optimizer: skill/tool retrieval, context compression, evidence retention and long-session stability.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_tool_selection_optimizer': {'description': 'Tool selection optimizer: live schema discovery, minimum sufficient tool stack, routing and collision avoidance.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_engine_command_planner': {'description': 'Engine command planner: dependency-safe native command sequencing, read-back checkpoints and rollback-safe scopes.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_result_evidence_synthesizer': {'description': 'Result evidence synthesizer: logs, metrics, captures, project read-back and concise completion evidence.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_failure_recovery_director': {'description': 'Failure recovery director: error classification, adaptive retries, fallback, rollback and honest blocker reporting.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_performance_budget_designer': {'description': 'Performance budget designer: target-tier CPU, GPU, memory, network, load-time and content budgets.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_frame_time_optimization': {'description': 'Frame-time optimization: representative profiling, dominant CPU/GPU costs, frame pacing and regression evidence.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_memory_budget_optimizer': {'description': 'Memory budget optimizer: allocation baselines, lifecycle ownership, residency, leaks and soak stability.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_asset_budget_optimizer': {'description': 'Asset budget optimizer: meshes, textures, audio, animation, shaders, LODs, compression and content scale.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_network_efficiency_optimizer': {'description': 'Network efficiency optimizer: message inventory, authority, payloads, rates, interest, latency and loss behavior.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_loading_startup_optimizer': {'description': 'Loading and startup optimizer: boot, scene/place load, dependency scheduling, caches and first interaction.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_streaming_strategy_optimizer': {'description': 'Streaming strategy optimizer: world/content partitioning, preload priorities, seams, memory and recovery.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_test_coverage_designer': {'description': 'Test coverage designer: risk-based unit, integration, engine-native, journey and regression coverage.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_edge_case_generator': {'description': 'Edge-case generator: state, timing, interruption, malformed data, device, network and lifecycle cases.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_cross_platform_validation': {'description': 'Cross-platform validation: device tiers, input methods, aspect ratios, suspend/resume and platform constraints.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_accessibility_validation': {'description': 'Accessibility validation: input alternatives, focus, contrast, motion, audio, readability and localization.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_content_scalability_plan': {'description': 'Content scalability planner: data-driven authoring, modularity, validation, versioning and production throughput.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_technical_debt_reducer': {'description': 'Technical debt reducer: risk-ranked architecture debt, duplication, ownership, tests and incremental migration.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}, 'ms_production_readiness_director': {'description': 'Production readiness director: cross-discipline completion, budgets, risk, evidence, compatibility and rollback.', 'stages': ['Define the exact player/user outcome and measurable acceptance criteria', 'Inspect the real project, live native schemas, current architecture and constraints', 'Capture a representative baseline and identify the highest-impact gap', 'Design the smallest provider-model skill/tool stack and dependency-safe native execution sequence', 'Implement the real improvement through currently advertised engine tools', 'Cover edge, interruption, failure, accessibility, security and recovery paths where relevant', 'Measure the same scenario against explicit target-tier budgets and fix regressions', 'Read back final engine state and report concise verified evidence plus remaining limitations'], 'qualityGates': ['Provider model remains the planner and uses only verified live native tools', 'No guidance/tool contract is mistaken for the deliverable', 'Explicit user requirements remain binding', 'Tool stack is minimal, relevant and context-efficient', 'Real project change is complete across relevant states', 'Performance is measured rather than assumed', 'Failures adapt from exact evidence and do not loop unchanged', 'Final claims are supported by engine read-back, tests, logs, captures or metrics']}}
ADVANCED_DIRECT_CONTRACTS.update(PROVIDER_QUALITY_V2_CONTRACTS)

# Every direct specialist contributes concrete craft, integration and evidence—not generic advice.
for _tool_name, _contract in ADVANCED_DIRECT_CONTRACTS.items():
    _contract.setdefault("weakPromptPolicy", "Infer only reversible project-appropriate details, preserve the stated fantasy and implement a complete polished vertical slice instead of returning a rewritten prompt.")
    _contract.setdefault("contributionContract", [
        "inspect the actual project and references before proposing changes",
        "make concrete changes in this specialist's discipline through exact live native tools",
        "coordinate interfaces, timing, style and ownership with every connected specialist",
        "cover happy, edge, interruption, failure and recovery states",
        "measure quality and target-platform cost instead of assuming them",
        "read back the final artifact and fix defects before claiming completion",
    ])
    _contract.setdefault("integrationResponsibilities", ["player fantasy and core loop", "visual and interaction coherence", "architecture and lifecycle", "platform and accessibility", "performance and reliability", "tests and final evidence"])
    _contract.setdefault("evidencePolicy", "A plan, prompt, checklist or tool contract is never evidence of completion; require native project state plus focused test, log, capture or metric evidence.")
    _contract.setdefault("capabilityLifecycle", ["understand intent and existing project", "set measurable craft and technical targets", "implement the smallest complete path", "integrate every dependency and player-facing state", "stress edge/failure/platform conditions", "profile and optimize measured bottlenecks", "critic-review and fix defects", "prove completion with native read-back"])
    _contract.setdefault("antiShallowRules", ["never stop at boilerplate when the request implies a usable product", "never isolate this discipline from connected gameplay/art/engineering", "never claim quality from code volume or checklist completion", "never trade explicit intent for generic best practices"])
    _contract.setdefault("promptRewriteIndependent", True)
    _contract.setdefault("productReleaseGate", ["real artifact complete", "connected systems integrated", "edge/failure/recovery states covered", "weakest-target budgets measured", "native tests and logs clean", "final project state read back", "limitations and rollback triggers disclosed"])
    _contract.setdefault("defectPriorityOrder", ["blocking functionality", "correctness and authority", "player usability", "cross-discipline cohesion", "measured performance", "accessibility and platform gaps", "cosmetic polish"])

for _name, _spec in PROVIDER_QUALITY_V2_CONTRACTS.items():
    if any(x in _name for x in ("performance", "frame_time", "memory", "asset_budget", "network", "loading", "streaming")): _spec["category"] = "quality"
    elif any(x in _name for x in ("test", "edge_case", "validation", "readiness", "evidence", "failure")): _spec["category"] = "quality"
    else: _spec["category"] = "gameplay"


BUILTIN_TOOLS = [
    {"name":"ms_mcp_schema_audit","description":"Audit every currently advertised native MCP tool schema for parameter compatibility, unsupported constructs, ambiguity and estimated pre-call failure risk without mutating any engine.","inputSchema":{"type":"object","properties":{"server":{"type":"string"},"refresh":{"type":"boolean"},"include_low_risk":{"type":"boolean"}}}},
    {"name": "ms_bridge_status", "description": "Show configured MCP servers, health, tool counts, and bridge version.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ms_list_resources", "description": "List MCP resources exposed by one connected server. Essential for Unity editor state, instances, project data, and scene inspection.",
     "inputSchema": {"type": "object", "properties": {"server": {"type": "string"}, "cursor": {"type": "string"}}, "required": ["server"]}},
    {"name": "ms_read_resource", "description": "Read an MCP resource URI from one connected server.",
     "inputSchema": {"type": "object", "properties": {"server": {"type": "string"}, "uri": {"type": "string"}}, "required": ["server", "uri"]}},
    {"name": "ms_list_skills", "description": "List reusable Multi-Script workflows, optionally filtered by engine or search text. Use filters to avoid loading the full catalog.",
     "inputSchema": {"type": "object", "properties": {"engine": {"type": "string", "enum": ["roblox", "unity", "godot", "blender", "figma", "general"]}, "query": {"type": "string"}, "ids": {"type": "array", "maxItems": 200, "items": {"type": "string"}}, "offset": {"type": "integer", "minimum": 0, "maximum": 10000}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}}},
    {"name": "ms_recommend_skills", "description": "Recommend the smallest relevant skill set for an objective and engine without dumping the full catalog.",
     "inputSchema": {"type": "object", "properties": {"objective": {"type": "string"}, "engine": {"type": "string", "enum": ["roblox", "unity", "godot", "blender", "figma", "general"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["objective"]}},
    {"name": "ms_get_skill", "description": "Load one reusable workflow by id before performing that kind of work.",
     "inputSchema": {"type": "object", "properties": {"skill_id": {"type": "string"}, "objective": {"type": "string", "maxLength": 4000, "description": "For skills with optional sections, only the sections this objective needs are returned."}, "sections": {"type": "array", "items": {"type": "string"}, "description": "Names of optional sections to load (from the 'Not shown' list)."}, "manual_sections": {"type":"array","maxItems":6,"items":{"type":"string","enum":["inspect","design","build","integrate","verify","failures"]},"description":"Retrieve full project-aware handbook checkpoints for the requested skill phases; omit for a compact application guide."}}, "required": ["skill_id"]}},
    {"name": "ms_critic_review", "description": "Review implementation evidence and return pass/revise plus missing verification. Use after meaningful changes.",
     "inputSchema": {"type": "object", "properties": {
         "objective": {"type": "string"}, "changed_assets": {"type": "array", "items": {"type": "string"}},
         "checks": {"type": "array", "items": {"type": "string"}}, "evidence": {"type": "array", "items": {"type": "string"}},
         "known_issues": {"type": "array", "items": {"type": "string"}}, "round": {"type": "integer", "minimum": 1, "maximum": 3}},
      "required": ["objective", "checks", "evidence"]}},
    {"name": "ms_form_guidance", "description": "Decide which primitive a modelled feature should actually be built from, BEFORE adding it. A limb is a cylinder, a plate is a box, a cable is a curve swept to mesh - and a sphere is right for only a short list of genuinely round things (eyeballs, ball joints, planets, knobs). Call this when you are about to model anything in Blender, or any engine, and especially before adding a primitive. Pass action=audit with your proposed part list to catch a sphere that should have been something else - that is the check that prevents a model arriving as a pile of balls.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["classify", "audit", "table"],
                    "description": "classify one feature, audit a whole part list, or print the full form table."},
         "feature": {"type": "string", "description": "For action=classify: the feature you are about to model, e.g. 'robot upper arm'."},
         "parts": {"type": "array", "description": "For action=audit: the proposed parts. Each is a name string, or a {name/part/feature, form/primitive} object.",
                   "items": {"anyOf": [{"type": "string"}, {"type": "object", "properties": {"name": {"type": "string"}, "part": {"type": "string"}, "feature": {"type": "string"}, "form": {"type": "string"}, "primitive": {"type": "string"}}}, {"type": "null"}]}},
         "engine": {"type": "string", "description": "Optional engine id for wording (blender, roblox, unity, godot). Defaults to blender."}},
      "required": ["action"]}},
    {"name": "ms_media_relay", "description": "Inspect or clear the media relay that carries a user's photo/video into a chat surface with no upload control. action=stats reports the live policy and spool usage; action=list shows what is staged; action=release drops one item or all of them. This tool never accepts media bytes itself - the extension stages them when the user drops a file, and pastes the resulting payloads. Use it to answer 'did my screenshot arrive?' and to clean up.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["stats", "list", "release"]},
         "id": {"type": "string"}}, "required": ["action"]}},
    {"name": "ms_surface_list", "description": "See what the user has open: every browser tab on this machine (real titles, URLs and hosts), plus every visible desktop window. This is the discovery step - it returns the integer tab ids and window handles that every other surface tool needs. Read-only. Use it when the user says 'the thing I have open', 'that tab', 'my other window', or before acting on any surface you have not yet looked at.",
     "inputSchema": {"type": "object", "properties": {
         "scope": {"type": "string", "enum": ["all", "tabs", "windows"], "description": "all (default), tabs only, or windows only"},
         "query": {"type": "string", "description": "Optional case-insensitive filter on title/host."}}}},
    {"name": "ms_surface_read", "description": "Read the visible text of one browser tab, so you can act on what is actually on the page instead of guessing. Returns the page title, URL, any selected text, and the readable body text (capped). Read-only. Get the tab_id from ms_surface_list first; browser-internal pages and PDF viewers cannot be read and will say so. `limit` is the readback size in characters and is CLAMPED into 200..12000 (default 6000) - any value is accepted.",
     "inputSchema": {"type": "object", "properties": {
         "tab_id": {"type": "integer"}, "limit": {"type": "integer", "minimum": 1, "maximum": 60000, "description": "Readback size in characters. Clamped into 200..12000; default 6000."}},
      "required": ["tab_id"]}},
    {"name": "ms_surface_type", "description": "Type text into the composer of a browser tab and optionally submit it - the way a person would, so it works on sites that reject scripted input. Use it for 'type this into that tab', 'search for X there', or to drive a site Multi-Script does not natively support. Defaults to submitting; pass submit=false to fill the field and stop. Confirm the result with ms_surface_read.",
     "inputSchema": {"type": "object", "properties": {
         "tab_id": {"type": "integer"}, "text": {"type": "string"},
         "submit": {"type": "boolean", "description": "Default true. false fills the field without sending."}},
      "required": ["tab_id", "text"]}},
    {"name": "ms_surface_open", "description": "Open a new browser tab at an http/https URL and return its tab id. Refuses javascript:, data:, file: and browser-internal schemes because those can execute or reach the local machine. Use it to bring a resource up for the user, then ms_surface_read to see it.",
     "inputSchema": {"type": "object", "properties": {
         "url": {"type": "string"}, "active": {"type": "boolean", "description": "Default true; false opens it in the background."}},
      "required": ["url"]}},
    {"name": "ms_surface_focus", "description": "Bring a browser tab to the front and focus its window, so the user can see what you are describing. Visibility only - it never reads or changes the page. Get the tab_id from ms_surface_list.",
     "inputSchema": {"type": "object", "properties": {"tab_id": {"type": "integer"}}, "required": ["tab_id"]}},
    {"name": "ms_app_list", "description": "List the desktop applications running on this machine (Roblox Studio, Unity, Godot, Blender, Figma, editors, browsers...), with their process names, pids and window titles. Read-only, no screenshots and no capture. Use it to answer 'is Studio open?', 'what do I have running?', or before suggesting a desktop workflow.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Optional filter on app or process name."},
         "include_unknown": {"type": "boolean", "description": "Default false (recognised creative/dev apps only). true adds every other process."}}}},
    {"name": "ms_app_snapshot", "description": "One-shot picture of the user's whole desktop: platform, what this machine can and cannot see, the recognised apps that are open, and every visible window title. Read-only. The fastest way to orient yourself before helping with a desktop task.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ms_app_read_window", "description": "Return the readable text of one desktop window by handle, pid or title, plus an honest statement of how good that read was (fidelity: accessibility, title-only, or none). Never screenshots and never fabricates content - if only the title is available it says so. Get a handle from ms_surface_list or ms_app_list.",
     "inputSchema": {"type": "object", "properties": {
         "handle": {"type": "integer"}, "pid": {"type": "integer"}, "title": {"type": "string"}}}},
    {"name": "ms_app_setup_plan", "description": "Report exactly what optional packages would improve desktop visibility on this machine, whether each is already satisfied, and the exact command to install it. Installs NOTHING itself. Call this when desktop reading is limited or when the user asks how to unlock full desktop vision, then show them the plan and run only what they approve.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ms_roblox_build_verifier", "description": "Verify that something you just built in Roblox Studio is actually there and correct, by re-reading the live place rather than trusting your own memory of what you sent. Give it the instance path you claimed to create or change plus what you expected; it reads the real Studio state back and reports matched / missing / mismatched, with the exact evidence. Use this after any consequential build step - it is the difference between 'I made it' and 'it is there'.",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Instance path you claimed, e.g. Workspace.Door or game.StarterGui.MainMenu"},
         "expect": {"type": "string", "description": "What you expected to be true, in words, e.g. 'a Part named Door with CanCollide true'"},
         "properties": {"type": "array", "items": {"type": "string"}, "description": "Optional exact property names to read back and compare"},
         "expected_properties": {"type": "object", "description": "Optional exact name->value pairs to assert"},
         "studio_id": {"type": "string"}},
      "required": ["path"]}},
    {"name": "ms_roblox_gui_audit", "description": "Measure a real GUI inside Roblox Studio and report what a player would see wrong: text that does not fit, very small text, low text contrast (with UIStroke taken into account), emoji in text, buttons smaller than a finger, objects off screen or cut off by the screen edge, zero-size objects, empty lists, lists whose canvas cannot scroll, images that did not load, and buttons covering each other. target=starter audits StarterGui in Edit mode; target=player audits the PlayerGui during a play test. root narrows it to one ScreenGui or frame path. Use it for affected UI after a useful change. Check reported findings against the real interface, reuse unchanged evidence and recheck after relevant repairs; capture the delivered interface when available.",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string", "enum": ["starter", "player"], "description": "starter = StarterGui (Edit), player = PlayerGui (during play)"},
         "root": {"type": "string", "description": "Optional path, e.g. StarterGui.ShopGui or StarterGui.ShopGui.Window"},
         "studio_id": {"type": "string"}},
      "required": []}},
    {"name": "ms_roblox_script_audit", "description": "Read the real Luau source of one or more scripts in the live place and audit it for the mistakes that actually break Roblox games: server/client boundary violations, unguarded RemoteEvent handlers, deprecated APIs, unbounded loops or waits, missing task.wait in loops, and unsanitized player input. Returns findings tied to the exact script and line where the tool can see them. Read-only.",
     "inputSchema": {"type": "object", "properties": {
         "paths": {"type": "array", "items": {"type": "string"}, "description": "Script instance paths to audit, e.g. ServerScriptService.GameLoop"},
         "scope": {"type": "string", "description": "Optional instance subtree to discover scripts under, e.g. ServerScriptService"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 25},
         "studio_id": {"type": "string"}},
      "required": []}},
    {"name": "ms_roblox_playtest_director", "description": "Plan and then run a real Roblox playtest: start the session in the right datamodel, exercise a named scenario, capture the console output, stop cleanly, and report what the run proved. Wraps the native start_stop_play, user input and console-output tools into one verified sequence instead of a scatter of calls. Every step is a real Studio action, never simulated.",
     "inputSchema": {"type": "object", "properties": {
         "scenario": {"type": "string", "description": "What to verify, e.g. 'the door opens when the player walks into it'"},
         "mode": {"type": "string", "enum": ["play", "run", "server"], "description": "play = with a character (default); run = started but no player; server = server datamodel only"},
         "inputs": {"type": "array", "items": {"type": "string"}, "description": "Ordered input steps to exercise, e.g. ['press W for 2 seconds', 'touch the door']"},
         "expect": {"type": "string", "description": "Observable outcome that would prove the scenario passed"},
         "auto_run": {"type": "boolean", "description": "Default false: returns the plan and the exact calls. true executes the plan for real."},
         "studio_id": {"type": "string"}},
      "required": ["scenario"]}},
    {"name": "ms_roblox_asset_scout", "description": "Search the Creator Store and the live place for assets that already fit what the user is building, and report each candidate with the reason it fits and the real id needed to insert it. Use it before telling a user to build something by hand, and to check whether an asset they asked for already exists in their own place. Never invents asset ids.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "What to find, e.g. 'low poly wooden door'"},
         "kind": {"type": "string", "enum": ["any", "model", "mesh", "image", "decal", "audio", "package", "video"], "description": "Use image for UI icons and pictures (most uploaded decals are stored as Image)."},
         "alt_queries": {"type": "array", "items": {"type": "string"}, "description": "Up to 3 other phrasings (a synonym, or the noun plus a style word). Results from all are returned together."},
         "tags": {"type": "array", "items": {"type": "string"}, "description": "Category tags such as Fantasy or Vehicle."},
         "facets": {"type": "array", "items": {"type": "string"}, "description": "Extra keywords to narrow the search."},
         "verified_only": {"type": "boolean", "description": "Default true: verified creators first; relaxed automatically if that returns nothing."},
         "price": {"type": "string", "enum": ["free", "paid", "all"], "description": "Default free. Never pick paid assets without asking the user."},
         "preview": {"type": "boolean", "description": "Default true: attach the real thumbnails of the first results so you can look at them."},
         "in_place": {"type": "boolean", "description": "Default false: search the Creator Store. true searches the user's own loaded place instead."},
         "limit": {"type": "integer", "minimum": 1, "maximum": 20},
         "studio_id": {"type": "string"}},
      "required": ["query"]}},
    {"name": "ms_roblox_scene_diff", "description": "Compare what a Roblox place looked like before and after a change, so a large edit can be reviewed instead of hoped for. Capture a snapshot of a subtree first, then capture again after the change; this reports instances added, removed and modified, with property-level detail where the tool can read it. Read-only and reversible - a snapshot is just recorded state.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["capture", "compare", "list"], "description": "capture records a snapshot; compare diffs two snapshots; list shows stored snapshots"},
         "path": {"type": "string", "description": "Instance subtree to capture, e.g. Workspace"},
         "label": {"type": "string", "description": "Optional name for the snapshot, e.g. 'before-door-fix'"},
         "before": {"type": "string", "description": "Snapshot label or id to compare from"},
         "after": {"type": "string", "description": "Snapshot label or id to compare to"},
         "depth": {"type": "integer", "minimum": 1, "maximum": 6, "description": "How deep to walk the subtree. Default 3."},
         "studio_id": {"type": "string"}},
      "required": ["action"]}},
    {"name": "ms_roblox_error_triage", "description": "Turn raw Roblox Studio console output into a ranked, actionable diagnosis: which errors matter, what each one actually means, the most likely cause, and the smallest safe fix. Paste the output (or let it read the live console) and it separates real failures from noise like deprecation warnings and plugin chatter. Use it the moment a playtest or build reports errors.",
     "inputSchema": {"type": "object", "properties": {
         "output": {"type": "string", "description": "Raw console/log text. Omit to read the live Studio console instead."},
         "read_live": {"type": "boolean", "description": "Default false. true reads the current Studio console output."},
         "studio_id": {"type": "string"}},
      "required": []}},
    {"name": "ms_agent_plan_then_act", "description": "For a multi-step request, produce an explicit ordered plan with a verification step after each action, then execute it only once the plan is visible. This is the tool to reach for when the user gives you a goal rather than a single command and the steps depend on each other. Returns either the plan awaiting approval, or the executed results with per-step evidence.",
     "inputSchema": {"type": "object", "properties": {
         "goal": {"type": "string"},
         "constraints": {"type": "array", "items": {"type": "string"}},
         "approve": {"type": "boolean", "description": "Default false: return the plan only. true marks it approved for execution."},
         "max_steps": {"type": "integer", "minimum": 1, "maximum": 12}},
      "required": ["goal"]}},
    {"name": "ms_agent_self_check", "description": "Before claiming a task is finished, run this to check your own work honestly: what you actually verified, what you only assumed, what is still unproven, and what a careful reviewer would ask for next. Returns a completion confidence with the specific gaps named. Use it to avoid over-claiming, especially after a long multi-tool sequence.",
     "inputSchema": {"type": "object", "properties": {
         "task": {"type": "string", "description": "What you were asked to do"},
         "did": {"type": "array", "items": {"type": "string"}, "description": "Actions you actually took"},
         "evidence": {"type": "array", "items": {"type": "string"}, "description": "Concrete evidence each action worked, e.g. read-back output"},
         "assumptions": {"type": "array", "items": {"type": "string"}, "description": "Things you assumed without proving"},
         "engine": {"type": "string"}},
      "required": ["task"]}},
    {"name": "ms_agent_context_recall", "description": "Answer 'what were we doing and what did we already decide' from the live session: the current objective, the engines and servers connected, the commands that already ran and their outcomes, and the open threads. Use it after a long gap, when the conversation has grown large, or before repeating work that may already be done.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Optional focus, e.g. 'the door work'."},
         "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
      "required": []}},
    {"name": "ms_workflow_plan", "description": "Create a domain-aware production plan for UI/UX, animation, VFX, modeling, coding, testing, and builds across connected engines.",
     "inputSchema": {"type": "object", "properties": {"objective": {"type": "string"}, "domains": {"type": "array", "items": {"type": "string"}}, "targets": {"type": "array", "items": {"type": "string"}}}, "required": ["objective", "domains"]}},
    {"name": "ms_parallel_tools", "description": "Run independent MCP tools on different servers concurrently, such as generating a model in Blender while inspecting or building in Unity. Use at most one call per server and only when operations do not depend on each other.",
     "inputSchema": {"type": "object", "properties": {"calls": {"type": "array", "maxItems": 6, "items": {"type": "object", "properties": {"server": {"type": "string"}, "tool": {"type": "string"}, "arguments": {"type": "object"}}, "required": ["server", "tool"]}}}, "required": ["calls"]}},
    {"name": "ms_enhance_brief", "description": "Expand a short creative request into a polished, cohesive, implementation-ready brief while preserving the user's intent and avoiding scope creep.",
     "inputSchema": {"type": "object", "properties": {"request": {"type": "string"}, "engine": {"type": "string"}, "quality": {"type": "string", "enum": ["polished", "ambitious"]}, "constraints": {"type": "array", "items": {"type": "string"}}}, "required": ["request"]}},
    {"name": "ms_quality_scorecard", "description": "Score a result across clarity, cohesion, originality, usability, responsiveness, accessibility, technical quality, performance, and evidence; return prioritized improvements.",
     "inputSchema": {"type": "object", "properties": {"objective": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}, "scores": {"type": "object", "additionalProperties": {"type": "number"}}, "notes": {"type": "array", "items": {"type": "string"}}}, "required": ["objective"]}},
    {"name": "ms_quality_checklist", "description": "Return a specialist quality gate for UI/UX, animation, VFX, 3D models, gameplay, or builds.",
     "inputSchema": {"type": "object", "properties": {"domain": {"type": "string", "enum": ["ui-ux", "animation", "vfx", "model", "gameplay", "build"]}, "target": {"type": "string"}}, "required": ["domain"]}},
    {"name": "ms_test_matrix", "description": "Generate edge-case and platform test coverage for a feature.", "inputSchema": {"type": "object", "properties": {"feature": {"type": "string"}, "platforms": {"type": "array", "items": {"type": "string"}}}, "required": ["feature"]}},
    {"name": "ms_create_canvas_texture", "description": "Create an actual reusable SVG texture on the local computer using deterministic Canvas-style procedural patterns. Returns the file path and SVG source for engine, Blender, browser-canvas, or Figma import.",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "description": "Optional output label. Omit it to create a unique texture filename."}, "pattern": {"type": "string", "enum": ["studs", "brick", "checker", "grid", "dots", "stripes", "hex", "noise"]}, "width": {"type": "integer", "minimum": 64, "maximum": 4096}, "height": {"type": "integer", "minimum": 64, "maximum": 4096}, "tile_size": {"type": "integer", "minimum": 4, "maximum": 512}, "background": {"type": "string"}, "foreground": {"type": "string"}, "accent": {"type": "string"}, "seed": {"type": "integer"}}, "required": ["pattern"]}},
    {"name": "ms_create_canvas_ui", "description": "Create a local SVG design mockup only. It does not create native Roblox ScreenGui, Godot Control, Unity Canvas, live Figma content or a working interface. For an in-editor GUI use connected native editor tools. Use this optional tool for requested mockups/design references, then separately implement and verify the real interface.",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "description": "Optional output label. Omit it to create a unique UI filename."}, "width": {"type": "integer", "minimum": 240, "maximum": 4096}, "height": {"type": "integer", "minimum": 240, "maximum": 4096}, "title": {"type": "string"}, "theme": {"type": "string", "enum": ["dark", "light", "game", "glass", "anime", "fantasy", "low-poly", "realistic-pbr", "cyberpunk", "gothic", "cozy", "pixel", "minimal", "sci-fi", "cartoon", "luxury"]}, "accent": {"type": "string"}, "components": {"type": "array", "maxItems": 100, "items": {"type": "object", "properties": {"type": {"type": "string", "enum": ["frame", "text", "button", "card", "input", "image", "badge"]}, "label": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "width": {"type": "number"}, "height": {"type": "number"}}}}}, "required": []}},
    {"name": "ms_create_icon_pack", "description": "Create real local SVG icon assets plus a sprite sheet, contact sheet, and manifest for a game/app UI. Use for coherent icon sets, Roblox HUD/shop/inventory icons, menus, ability icons, and external design handoff; files are created on disk, not silently uploaded to an engine.",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "description": "Optional pack label; omitted labels receive a unique name."}, "icons": {"type": "array", "minItems": 1, "maxItems": 64, "items": {"type": "string", "minLength": 1, "maxLength": 48}, "description": "Names such as sword, shield, heart, coin, bag, home, settings, target, map, potion, star, crown, bolt, fire, skull, lock, user, search, gem, trophy, quest, book, compass, moon, sun, check, close, warning, play, pause."}, "style": {"type": "string", "enum": ["outline", "solid", "duotone", "pixel", "game"]}, "size": {"type": "integer", "minimum": 16, "maximum": 512}, "primary_color": {"type": "string"}, "accent_color": {"type": "string"}, "background": {"type": "string"}}, "required": ["icons"]}},
    {"name": "ms_figma_handoff", "description": "Create a Figma-ready UI/UX execution plan with pages, frames, components, variants, Auto Layout, variables, accessibility, prototype flows, and import assets; reports whether a configured Figma MCP server is currently available.",
     "inputSchema": {"type": "object", "properties": {"objective": {"type": "string"}, "platform": {"type": "string"}, "screens": {"type": "array", "items": {"type": "string"}}, "style": {"type": "string"}}, "required": ["objective"]}},
    {"name": "ms_asset_budget", "description": "Create measurable geometry, texture, animation, audio and VFX budgets.", "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}, "platform": {"type": "string"}}, "required": ["target"]}},
    {"name": "ms_release_checklist", "description": "Generate a build, smoke-test, rollback and release evidence checklist.", "inputSchema": {"type": "object", "properties": {"engine": {"type": "string"}, "platform": {"type": "string"}}, "required": ["engine"]}},
    {"name": "ms_risk_register", "description": "Identify technical, content, integration and delivery risks with mitigations.", "inputSchema": {"type": "object", "properties": {"objective": {"type": "string"}, "systems": {"type": "array", "items": {"type": "string"}}}, "required": ["objective"]}},
    {"name": "ms_engine_handoff", "description": "Create a deterministic Blender-to-engine asset handoff checklist.",
     "inputSchema": {"type": "object", "properties": {
         "source": {"type": "string", "enum": ["blender", "other"]},
         "target": {"type": "string", "enum": ["roblox", "unity", "godot", "unreal", "other"]},
         "asset_type": {"type": "string"}, "format": {"type": "string"}},
      "required": ["source", "target", "asset_type"]}},
    {"name": "ms_prompt_rescue", "description": "Turn a vague, contradictory, or low-quality game-development request into a strong production brief without changing its core intent.", "inputSchema": {"type":"object","properties":{"prompt":{"type":"string"},"engine":{"type":"string","enum":["roblox","unity","godot","other"]},"genre":{"type":"string"},"constraints":{"type":"array","items":{"type":"string"}}},"required":["prompt"]}},
    {"name": "ms_game_blueprint", "description": "Create an end-to-end game blueprint covering pillars, loop, systems, content, architecture, milestones, risks, testing, and release.", "inputSchema": {"type":"object","properties":{"concept":{"type":"string"},"engine":{"type":"string"},"platforms":{"type":"array","items":{"type":"string"}},"multiplayer":{"type":"boolean"}},"required":["concept","engine"]}},
    {"name": "ms_vertical_slice_plan", "description": "Reduce a large game idea to the smallest polished playable slice with explicit exit criteria.", "inputSchema": {"type":"object","properties":{"objective":{"type":"string"},"engine":{"type":"string"},"deadline":{"type":"string"}},"required":["objective","engine"]}},
    {"name": "ms_system_design_review", "description": "Review a game system design for ownership, lifecycle, coupling, failure modes, testability, migration, and performance.", "inputSchema": {"type":"object","properties":{"system":{"type":"string"},"engine":{"type":"string"},"design":{"type":"string"},"dependencies":{"type":"array","items":{"type":"string"}}},"required":["system","engine"]}},
    {"name": "ms_gameplay_balance_plan", "description": "Produce measurable gameplay/economy balance variables, simulations, guardrails, telemetry, and tuning experiments.", "inputSchema": {"type":"object","properties":{"system":{"type":"string"},"goals":{"type":"array","items":{"type":"string"}},"player_segments":{"type":"array","items":{"type":"string"}}},"required":["system"]}},
    {"name": "ms_multiplayer_authority_audit", "description": "Audit multiplayer trust boundaries, validation, ownership, rate limits, prediction, reconnects, and exploit cases.", "inputSchema": {"type":"object","properties":{"engine":{"type":"string"},"feature":{"type":"string"},"messages":{"type":"array","items":{"type":"string"}}},"required":["engine","feature"]}},
    {"name": "ms_save_migration_plan", "description": "Design a backwards-compatible save-schema migration with validation, backups, idempotency, rollout, and rollback.", "inputSchema": {"type":"object","properties":{"engine":{"type":"string"},"current_version":{"type":"string"},"target_version":{"type":"string"},"changes":{"type":"array","items":{"type":"string"}}},"required":["engine","current_version","target_version"]}},
    {"name": "ms_performance_budget_plan", "description": "Create measurable CPU, memory, GPU, network, loading, and asset budgets for target platforms.", "inputSchema": {"type":"object","properties":{"engine":{"type":"string"},"platforms":{"type":"array","items":{"type":"string"}},"scene":{"type":"string"}},"required":["engine"]}},
    {"name": "ms_accessibility_audit", "description": "Audit controls, readability, motion, audio, color, cognitive load, difficulty, and assist settings.", "inputSchema": {"type":"object","properties":{"feature":{"type":"string"},"platforms":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"string"}}},"required":["feature"]}},
    {"name": "ms_content_pipeline_plan", "description": "Plan source files, naming, import settings, validation, optimization, versioning, and engine handoff for game content.", "inputSchema": {"type":"object","properties":{"engine":{"type":"string"},"content_types":{"type":"array","items":{"type":"string"}},"source_tools":{"type":"array","items":{"type":"string"}}},"required":["engine","content_types"]}},
    {"name": "ms_playtest_protocol", "description": "Create a repeatable playtest protocol with cohorts, tasks, observations, telemetry, severity, and decision rules.", "inputSchema": {"type":"object","properties":{"objective":{"type":"string"},"build":{"type":"string"},"participants":{"type":"integer","minimum":1},"platforms":{"type":"array","items":{"type":"string"}}},"required":["objective"]}},
    {"name": "ms_definition_of_done", "description": "Create a strict, evidence-based completion gate for a game feature or release.", "inputSchema": {"type":"object","properties":{"feature":{"type":"string"},"engine":{"type":"string"},"risk":{"type":"string","enum":["low","medium","high"]}},"required":["feature","engine"]}},
    {"name": "ms_orchestrate_request", "description": "Automatically select a complementary multi-skill stack for a player request: design, implementation, polish, optimization, and validation—not a single isolated skill.", "inputSchema": {"type":"object","properties":{"request":{"type":"string"},"engine":{"type":"string","enum":["roblox","unity","godot","blender","figma","general"]},"max_skills":{"type":"integer","minimum":1,"maximum":40}},"required":["request","engine"]}},
    {"name": "ms_activate_skill_stack", "description": "Load and combine a professional skill stack into an executable work contract. Selection is preparation; real MCP implementation and verification must follow.", "inputSchema": {"type":"object","properties":{"request":{"type":"string"},"engine":{"type":"string"},"skill_ids":{"type":"array","minItems":2,"maxItems":8,"items":{"type":"string"}}},"required":["request","engine"]}},
    {"name": "ms_animation_director", "description": "Create an engine-ready professional animation direction and implementation plan covering rig, clips, state logic, layering, IK, events, networking, polish, and validation.", "inputSchema": {"type":"object","properties":{"engine":{"type":"string"},"subject":{"type":"string"},"style":{"type":"string"},"actions":{"type":"array","items":{"type":"string"}}},"required":["engine","subject"]}},
    {"name": "ms_texture_art_pipeline", "description": "Create a complete texture/material art workflow from visual target through source creation, UV/tiling, channel packing, import, optimization, and in-engine validation.", "inputSchema": {"type":"object","properties":{"engine":{"type":"string"},"asset":{"type":"string"},"style":{"type":"string"},"platforms":{"type":"array","items":{"type":"string"}}},"required":["engine","asset"]}},
    {"name": "ms_art_direction", "description": "Turn a visual idea into a cohesive professional art direction with shape, color, material, lighting, composition, readability, asset rules, and review gates.", "inputSchema": {"type":"object","properties":{"engine":{"type":"string"},"concept":{"type":"string"},"mood":{"type":"string"},"references":{"type":"array","items":{"type":"string"}}},"required":["engine","concept"]}},
    {"name": "ms_uiux_production", "description": "Create a complete UI/UX production contract: flow, hierarchy, components, states, responsive behavior, input navigation, accessibility, implementation, and usability evidence.", "inputSchema": {"type":"object","properties":{"engine":{"type":"string"},"feature":{"type":"string"},"platforms":{"type":"array","items":{"type":"string"}},"style":{"type":"string"}},"required":["engine","feature"]}},
    {"name": "ms_vfx_production", "description": "Create a professional VFX execution contract covering story beat, timing, readability, particles, shaders, lighting, audio sync, pooling, budgets, variants, and runtime capture.", "inputSchema": {"type":"object","properties":{"engine":{"type":"string"},"effect":{"type":"string"},"platforms":{"type":"array","items":{"type":"string"}},"style":{"type":"string"}},"required":["engine","effect"]}},
    {"name": "ms_audio_production", "description": "Create a professional game-audio execution contract covering event taxonomy, assets, spatialization, mixing, concurrency, adaptive music, accessibility, memory, and runtime validation.", "inputSchema": {"type":"object","properties":{"engine":{"type":"string"},"feature":{"type":"string"},"style":{"type":"string"},"platforms":{"type":"array","items":{"type":"string"}}},"required":["engine","feature"]}},
    {"name": "ms_list_virtual_tools", "description": "List the 270 engine-specific virtual specialist tools, filtered by engine/domain/query, without flooding model context.", "inputSchema": {"type":"object","properties":{"engine":{"type":"string","enum":["roblox","unity","godot","blender"]},"domain":{"type":"string"},"query":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":50}}}},
    {"name": "ms_match_virtual_tools", "description": "Match a user prompt to the strongest engine-specific virtual tools for UI, animation, graphics, shaders, VFX, models, textures, audio, gameplay, systems, or production.", "inputSchema": {"type":"object","properties":{"request":{"type":"string"},"engine":{"type":"string","enum":["roblox","unity","godot","blender"]},"limit":{"type":"integer","minimum":1,"maximum":30}},"required":["request","engine"]}},
    {"name": "ms_virtual_tool_details", "description": "Load one virtual tool's exact engine-specific stages, quality gates, and output contract.", "inputSchema": {"type":"object","properties":{"tool_id":{"type":"string"}},"required":["tool_id"]}},
    {"name": "ms_run_virtual_tool", "description": "Apply a matched virtual tool as hidden augmentation, then create the real deliverable through MCP. Internal briefs must not replace the requested result.", "inputSchema": {"type":"object","properties":{"tool_id":{"type":"string"},"request":{"type":"string"},"project_context":{"type":"string"},"constraints":{"type":"array","items":{"type":"string"}}},"required":["tool_id","request"]}},
    {"name": "ms_elevenlabs_status", "description": "Show keyless local audio availability plus optional ElevenLabs cloud status. Never returns or logs a key.", "inputSchema": {"type":"object","properties":{}}},
    {"name": "ms_generate_sound_effect", "description": "Generate a real local WAV sound effect with no account, network, or API key; optional provider=elevenlabs uses the configured cloud service for complex material.", "inputSchema": {"type":"object","properties":{"text":{"type":"string"},"name": {"type": "string", "description": "Optional output label; defaults to sound-effect. Generated audio filenames include a unique timestamp/hash."},"duration_seconds":{"type":"number","minimum":0.5,"maximum":30},"loop":{"type":"boolean"},"prompt_influence":{"type":"number","minimum":0,"maximum":1},"output_format":{"type":"string","enum":["mp3_22050_32","mp3_44100_64","mp3_44100_96","mp3_44100_128","mp3_44100_192","pcm_16000","pcm_22050","pcm_24000","pcm_44100"]},"target_engine":{"type":"string","enum":["roblox","unity","godot","other"]},"provider":{"type":"string","enum":["auto","local","elevenlabs"],"default":"auto"},"seed":{"type":"integer"}},"required": ["text"]}},
    {"name": "ms_list_generated_audio", "description": "List locally generated ElevenLabs audio assets and their metadata for reuse or engine import.", "inputSchema": {"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":200}}}},
    {'name': 'ms_camera_system_design', 'description': 'Design and validate a production camera system for gameplay, cinematics, collision, comfort, and every target input.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_input_mapping_plan', 'description': 'Create a cross-platform input architecture with rebinding, action maps, prompts, focus, and accessibility.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_character_controller_review', 'description': 'Review or design a responsive character controller covering movement, slopes, jumps, grounding, networking, and animation integration.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_combat_system_design', 'description': 'Create a complete combat architecture with timing, hit validation, damage, status effects, feedback, networking, and balance hooks.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_ai_behavior_design', 'description': 'Design game AI with perception, decision making, navigation, combat tactics, recovery, debugging, and performance budgets.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_quest_system_design', 'description': 'Design a data-driven quest, objective, dialogue, reward, persistence, and migration system.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_inventory_economy_design', 'description': 'Design inventory and economy systems with stacking, transactions, crafting, shops, persistence, anti-duplication, and tuning.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_procedural_generation_plan', 'description': 'Create a deterministic procedural-generation pipeline with seeds, constraints, validation, streaming, and authored overrides.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_shader_production', 'description': 'Create an engine-ready shader production contract covering visual intent, lighting, variants, parameters, optimization, and fallback tiers.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_lighting_production', 'description': 'Design and implement cohesive game lighting with readability, mood, probes, shadows, post-processing, and performance tiers.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_environment_production', 'description': 'Create a complete environment-production contract from blockout through modular assets, dressing, lighting, gameplay readability, and optimization.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_character_model_production', 'description': 'Create a character-model pipeline covering concept translation, topology, UVs, materials, facial needs, LODs, rig handoff, and engine validation.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_rigging_production', 'description': 'Create a robust rigging contract for skeletons, skinning, controls, constraints, retargeting, physics, export, and engine tests.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_localization_audit', 'description': 'Audit localization readiness across text, fonts, layouts, input, audio, pluralization, cultural context, and QA.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_telemetry_plan', 'description': 'Create a privacy-aware telemetry specification with events, schemas, funnels, diagnostics, sampling, dashboards, and validation.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_liveops_plan', 'description': 'Plan safe live operations covering configuration, events, segmentation, rollout, economy protection, moderation, observability, and rollback.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_store_compliance_check', 'description': 'Generate a platform-store compliance and submission gate for privacy, monetization, content ratings, permissions, packaging, and review evidence.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_security_abuse_review', 'description': 'Review a game feature for trust boundaries, secrets, permissions, injection, cheating, moderation, privacy, and incident response.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_bug_triage', 'description': 'Turn a bug report into a reproducible, prioritized engineering investigation with hypotheses, instrumentation, fix scope, and verification.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_regression_plan', 'description': 'Create a risk-based regression plan covering changed surfaces, dependencies, automated checks, manual journeys, platforms, performance, and rollback.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_dialogue_production', 'description': 'Dialogue production: branching dialogue, conditions, localization, VO hooks and runtime validation. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_cinematic_production', 'description': 'Cinematic production: storyboards, cameras, animation, timing, audio, skip/replay and runtime capture. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_tutorial_design', 'description': 'Tutorial design: onboarding, progressive disclosure, practice, recovery, telemetry and accessibility. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_navigation_system_design', 'description': 'Navigation system design: navigation meshes, agents, links, avoidance, streaming and recovery. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_physics_system_audit', 'description': 'Physics system audit: collision layers, fixed-step behavior, ownership, determinism and profiling. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_vehicle_system_design', 'description': 'Vehicle system design: handling, suspension, controls, camera, networking, damage and tuning. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_world_streaming_plan', 'description': 'World streaming plan: partitioning, loading, persistence, seams, budgets and failure recovery. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_level_design_review', 'description': 'Level design review: metrics, flow, pacing, landmarks, encounters, accessibility and playtests. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_puzzle_design', 'description': 'Puzzle design: rules, teaching, feedback, hinting, reset, exploits and difficulty progression. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_social_system_design', 'description': 'Social system design: parties, friends, presence, invites, privacy, moderation and safety. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_matchmaking_design', 'description': 'Matchmaking design: queues, skill, latency, parties, backfill, abuse prevention and telemetry. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_modding_pipeline', 'description': 'Modding pipeline: sandboxing, schemas, packaging, validation, compatibility and moderation. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_build_automation', 'description': 'Build automation: reproducible builds, versioning, tests, signing, artifacts and rollback. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_crash_diagnostics', 'description': 'Crash diagnostics: symbols, dumps, breadcrumbs, reproduction, grouping and fix verification. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_memory_leak_audit', 'description': 'Memory leak audit: allocation baselines, lifecycle ownership, retention paths and soak testing. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_network_bandwidth_audit', 'description': 'Network bandwidth audit: message inventory, payloads, rates, compression, interest and loss tests. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_mobile_optimization', 'description': 'Mobile optimization: thermal, memory, GPU, input, UI, battery and device-tier validation. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_vr_xr_production', 'description': 'VR/XR production: comfort, interaction, locomotion, scale, performance and accessibility. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_web_build_optimization', 'description': 'Web build optimization: download size, startup, memory, browser compatibility and caching. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_console_readiness', 'description': 'Console readiness: platform input, suspend/resume, users, saves, certification and performance. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_controller_haptics', 'description': 'Controller haptics: event taxonomy, envelopes, device capabilities, comfort and testing. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_iconography_production', 'description': 'Iconography production: visual language, grids, states, readability, localization and export. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_marketing_capture_plan', 'description': 'Marketing capture plan: shot list, builds, camera paths, clean UI, formats and approvals. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_npc_population_system', 'description': 'NPC population system: spawning, schedules, simulation LOD, persistence and performance. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_weather_system', 'description': 'Weather system: state model, visuals, gameplay, audio, transitions, replication and budgets. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_day_night_system', 'description': 'Day/night system: time authority, lighting, schedules, saves, networking and transitions. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_destructible_system', 'description': 'Destructible system: fracture states, authority, damage, debris, persistence and optimization. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_replay_system', 'description': 'Replay system: capture schema, determinism, seek, versioning, storage and playback validation. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_photo_mode', 'description': 'Photo mode: camera controls, pause policy, filters, UI, platform saves and privacy. Returns a real-execution contract with verification gates.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_roblox_capability_audit', 'description': 'Audit the live Roblox Studio MCP connection, native tool catalogue, major capability groups, and companion-plugin readiness without inventing unavailable tools.', 'inputSchema': {'type': 'object', 'properties': {'refresh': {'type': 'boolean'}}}},
    {'name': 'ms_engine_catalog', 'description': 'Load the exact live tool catalogue for one engine server, including schemas and native/direct counts.', 'inputSchema': {'type': 'object', 'properties': {'server': {'type': 'string'}, 'refresh': {'type': 'boolean'}}, 'required': ['server']}},
    {'name': 'ms_engine_connection_test', 'description': 'Run a real read-only smoke test against a named engine server and return verified evidence.', 'inputSchema': {'type': 'object', 'properties': {'server': {'type': 'string'}, 'tool': {'type': 'string'}, 'arguments': {'type': 'object'}}, 'required': ['server']}},
    {'name': 'ms_call_engine_tool', 'description': 'Reliably execute one exact native MCP tool on one exact engine server, avoiding cross-engine name collisions.', 'inputSchema': {'type': 'object', 'properties': {'server': {'type': 'string'}, 'tool': {'type': 'string'}, 'arguments': {'type': 'object'}, 'timeout_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 300}}, 'required': ['server', 'tool']}},
    {'name': 'ms_engine_capability_map', 'description': 'Show live engine connections, exact native tool counts, Multi-Script direct tools, skills and virtual capability coverage.', 'inputSchema': {'type': 'object', 'properties': {'refresh': {'type': 'boolean'}}}},
    {'name': 'ms_roblox_animation_studio', 'description': 'Roblox animation studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_blender_animation_studio', 'description': 'Blender animation studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_unity_animation_studio', 'description': 'Unity animation studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_godot_animation_studio', 'description': 'Godot animation studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_combat_animation_polish', 'description': 'Combat animation polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_locomotion_animation_polish', 'description': 'Locomotion animation polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_cinematic_animation_polish', 'description': 'Cinematic animation polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_creature_animation', 'description': 'Creature animation with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_facial_animation', 'description': 'Facial animation with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_animation_retargeting', 'description': 'Animation retargeting with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_animation_state_machine', 'description': 'Animation state-machine direction with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_animation_runtime_qa', 'description': 'Animation runtime QA with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_gui_design_studio', 'description': 'Professional GUI design studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_roblox_gui_studio', 'description': 'Roblox GUI production studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_unity_ui_studio', 'description': 'Unity UI production studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_godot_ui_studio', 'description': 'Godot UI production studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_ui_motion_design', 'description': 'UI motion and micro-interaction design with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_design_system_production', 'description': 'Design-system production with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_responsive_interface_polish', 'description': 'Responsive interface polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_controller_navigation_ux', 'description': 'Controller-navigation UX with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_accessible_interface_polish', 'description': 'Accessible interface polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_usability_polish', 'description': 'Usability and flow polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_blender_model_studio', 'description': 'Blender model studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_stylized_art_production', 'description': 'Stylized art production with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_realistic_art_production', 'description': 'Realistic art production with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_environment_art_studio', 'description': 'Environment art studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_character_art_studio', 'description': 'Character art studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_prop_art_studio', 'description': 'Prop art studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_pbr_material_studio', 'description': 'PBR material studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_texture_detail_polish', 'description': 'Texture detail polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_lighting_art_studio', 'description': 'Lighting art studio with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_composition_render_polish', 'description': 'Composition and render polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_game_feel_director', 'description': 'Game-feel director with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_combat_feel_director', 'description': 'Combat-feel director with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_movement_feel_director', 'description': 'Movement-feel director with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_camera_feel_director', 'description': 'Camera-feel director with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_onboarding_experience_polish', 'description': 'Onboarding experience polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_economy_experience_polish', 'description': 'Economy experience polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_social_experience_polish', 'description': 'Social experience polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_progression_experience_polish', 'description': 'Progression experience polish with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_studio_critic_loop', 'description': 'Studio-grade critic loop with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_visual_quality_audit', 'description': 'Visual quality audit with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_ui_quality_audit', 'description': 'UI quality audit with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_gameplay_quality_audit', 'description': 'Gameplay quality audit with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_performance_quality_audit', 'description': 'Performance quality audit with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_cross_engine_integration_audit', 'description': 'Cross-engine integration audit with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_release_quality_bar', 'description': 'Release quality bar with a senior ten-year-studio craft bar.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string'}, 'feature': {'type': 'string'}, 'style': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}},
    {'name': 'ms_full_spectrum_skill_mesh', 'description': 'Coordinate the relevant specialized skills, direct tools and engine virtual tools together so every game-development aspect strengthens the same real deliverable.', 'inputSchema': {'type': 'object', 'properties': {'request': {'type': 'string'}, 'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'skill_limit': {'type': 'integer', 'minimum': 1, 'maximum': 40}, 'direct_tool_limit': {'type': 'integer', 'minimum': 1, 'maximum': 32}, 'virtual_tool_limit': {'type': 'integer', 'minimum': 1, 'maximum': 30}}, 'required': ['request', 'engine']}},
    {'name': 'ms_cross_discipline_integration_review', 'description': 'Review whether specialized art, design, gameplay, engineering, audio, performance, accessibility and testing tools were integrated into one complete result.', 'inputSchema': {'type': 'object', 'properties': {'request': {'type': 'string'}, 'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'project_context': {'type': 'string'}, 'evidence': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['request', 'engine']}},
    {'name': 'ms_studio_director', 'description': 'Silently match any meaningful user request to a senior-studio stack of direct tools, skills, virtual tools and evidence gates before real MCP execution. The limits are advisory: any value is accepted and raised to the effective floor (max_tools >= 8, max_skills >= 8, max_virtual_tools >= 4), so omit them unless you want a larger stack.', 'inputSchema': {'type': 'object', 'properties': {'request': {'type': 'string'}, 'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'style': {'type': 'string'}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'max_tools': {'type': 'integer', 'minimum': 1, 'maximum': 32}, 'max_skills': {'type': 'integer', 'minimum': 1, 'maximum': 40}, 'max_virtual_tools': {'type': 'integer', 'minimum': 1, 'maximum': 30}}, 'required': ['request', 'engine']}},
    {'name': 'ms_list_direct_tools', 'description': 'Discover Multi-Script direct tools by category or query without dumping the full catalogue into model context.', 'inputSchema': {'type': 'object', 'properties': {'category': {'type': 'string', 'enum': ['animation', 'uiux', 'art3d', 'gameplay', 'quality', 'all']}, 'query': {'type': 'string'}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}}}},
    {'name': 'ms_direct_tool_details', 'description': 'Read an exact current schema for any built-in, toolkit, companion or native MCP tool. Does not execute it.', 'inputSchema': {'type': 'object', 'properties': {'tool': {'type': 'string'}, 'server': {'type': 'string'}}, 'required': ['tool']}},
]
BUILTIN_TOOLS.extend([{'name': 'ms_provider_execution_optimizer', 'description': 'Provider execution optimizer: improve the active provider model’s provider model context, tool choice, command precision and verified completion; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_context_budget_optimizer', 'description': 'Context budget optimizer: improve the active provider model’s skill/tool retrieval, context compression, evidence retention and long-session stability; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_tool_selection_optimizer', 'description': 'Tool selection optimizer: improve the active provider model’s live schema discovery, minimum sufficient tool stack, routing and collision avoidance; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_engine_command_planner', 'description': 'Engine command planner: improve the active provider model’s dependency-safe native command sequencing, read-back checkpoints and rollback-safe scopes; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_result_evidence_synthesizer', 'description': 'Result evidence synthesizer: improve the active provider model’s logs, metrics, captures, project read-back and concise completion evidence; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_failure_recovery_director', 'description': 'Failure recovery director: improve the active provider model’s error classification, adaptive retries, fallback, rollback and honest blocker reporting; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_performance_budget_designer', 'description': 'Performance budget designer: improve the active provider model’s target-tier CPU, GPU, memory, network, load-time and content budgets; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_frame_time_optimization', 'description': 'Frame-time optimization: improve the active provider model’s representative profiling, dominant CPU/GPU costs, frame pacing and regression evidence; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_memory_budget_optimizer', 'description': 'Memory budget optimizer: improve the active provider model’s allocation baselines, lifecycle ownership, residency, leaks and soak stability; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_asset_budget_optimizer', 'description': 'Asset budget optimizer: improve the active provider model’s meshes, textures, audio, animation, shaders, LODs, compression and content scale; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_network_efficiency_optimizer', 'description': 'Network efficiency optimizer: improve the active provider model’s message inventory, authority, payloads, rates, interest, latency and loss behavior; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_loading_startup_optimizer', 'description': 'Loading and startup optimizer: improve the active provider model’s boot, scene/place load, dependency scheduling, caches and first interaction; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_streaming_strategy_optimizer', 'description': 'Streaming strategy optimizer: improve the active provider model’s world/content partitioning, preload priorities, seams, memory and recovery; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_test_coverage_designer', 'description': 'Test coverage designer: improve the active provider model’s risk-based unit, integration, engine-native, journey and regression coverage; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_edge_case_generator', 'description': 'Edge-case generator: improve the active provider model’s state, timing, interruption, malformed data, device, network and lifecycle cases; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_cross_platform_validation', 'description': 'Cross-platform validation: improve the active provider model’s device tiers, input methods, aspect ratios, suspend/resume and platform constraints; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_accessibility_validation', 'description': 'Accessibility validation: improve the active provider model’s input alternatives, focus, contrast, motion, audio, readability and localization; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_content_scalability_plan', 'description': 'Content scalability planner: improve the active provider model’s data-driven authoring, modularity, validation, versioning and production throughput; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_technical_debt_reducer', 'description': 'Technical debt reducer: improve the active provider model’s risk-ranked architecture debt, duplication, ownership, tests and incremental migration; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}, {'name': 'ms_production_readiness_director', 'description': 'Production readiness director: improve the active provider model’s cross-discipline completion, budgets, risk, evidence, compatibility and rollback; returns an execution contract and never impersonates native engine work.', 'inputSchema': {'type': 'object', 'properties': {'engine': {'type': 'string', 'enum': ['roblox', 'unity', 'godot', 'blender', 'figma', 'general']}, 'feature': {'type': 'string'}, 'target_tier': {'type': 'string'}, 'platforms': {'type': 'array', 'items': {'type': 'string'}}, 'metrics': {'type': 'array', 'items': {'type': 'string'}}, 'constraints': {'type': 'array', 'items': {'type': 'string'}}, 'context': {'type': 'string'}}, 'required': ['feature']}}])
for _name, _spec in ENGINE_PRO_V3_CONTRACTS.items():
    BUILTIN_TOOLS.append({"name":_name,"description":_spec["description"]+" Improves provider-model execution through genuine live native engine tools.","inputSchema":{"type":"object","properties":{"engine":{"type":"string","enum":[_spec["engine"]]},"feature":{"type":"string"},"target_tier":{"type":"string"},"platforms":{"type":"array","items":{"type":"string"}},"metrics":{"type":"array","items":{"type":"string"}},"constraints":{"type":"array","items":{"type":"string"}},"context":{"type":"string"}},"required":["feature"]}})

for _name, _spec in ROBLOX_STUDIO_V3_CONTRACTS.items():
    BUILTIN_TOOLS.append({"name":_name,"description":_spec["description"]+" Improves Roblox Studio execution through the active provider model and official live native tools.","inputSchema":{"type":"object","properties":{"engine":{"type":"string","enum":["roblox"]},"feature":{"type":"string"},"target_tier":{"type":"string"},"platforms":{"type":"array","items":{"type":"string"}},"metrics":{"type":"array","items":{"type":"string"}},"constraints":{"type":"array","items":{"type":"string"}},"context":{"type":"string"}},"required":["feature"]}})

# ══════════════════════════════════════════════════════════════════════════
#  ENGINE-NATIVE TOOL FACADE
# ══════════════════════════════════════════════════════════════════════════
# The advisory tools above tell the model WHAT to do. These actually DO it: each
# one is a thin, dialect-correct wrapper that composes the live native MCP tools
# of a specific engine into one meaningful operation, then reads back the result
# to prove it happened.
#
# WHY THIS EXISTS
# The engines do not share a vocabulary, and each has a habitual failure:
#
#   * Roblox Studio requires `studio_id` on every place-scoped call, so with two
#     Studios open a model that omits it is rejected - the "invalid parameters:
#     parameters.studio_id is required" spam reported live.
#   * Unity is ACTION-DISPATCH: `manage_scene` takes `action: "get_hierarchy"`.
#     A model that writes {"command":"get_hierarchy"} gets "unknown command".
#   * Godot requires `projectPath` (camelCase, absolute, the FOLDER holding
#     project.godot) on almost everything; `list_projects` is the lone exception
#     and takes `directory`.
#   * Blender is code-execution based, so the failure is a JSON-escape bug in a
#     long Python string rather than a wrong name.
#
# A model reading prose about four dialects will still get one wrong. It will not
# get a single call with one obvious name and honest parameters wrong. So each
# facade tool below advertises only ENGINE-NEUTRAL parameters, translates them to
# the right dialect internally, and returns a normalised result envelope with the
# exact native calls it issued. Nothing is invented: every tool name it can emit
# is read from the engine's live advertised catalogue at call time, and it fails
# loudly when the engine does not advertise what it needs.
_FACADE_NATIVE_HINTS = {
    # engine: {capability: [acceptable native tool names, in preference order]}
    "roblox": {
        "list_studios": ["list_roblox_studios"],
        "read_tree": ["search_game_tree"],
        "read_state": ["get_studio_state"],
        "read_script": ["script_read"],
        "write_script": ["multi_edit"],
        "exec_code": ["execute_luau"],
        "console": ["get_console_output"],
        "inspect": ["inspect_instance"],
    },
    "unity": {
        "read_tree": ["manage_scene"],
        "find_objects": ["find_gameobjects"],
        "read_console": ["read_console"],
        "read_script": ["find_in_file"],
        "write_script": ["script_apply_edits"],
        "create_script": ["create_script"],
        "create_object": ["manage_gameobject"],
        "create_scene": ["manage_scene"],
        "refresh": ["refresh_unity"],
        "validate": ["validate_script"],
        "hash": ["get_sha"],
        "play": ["manage_editor"],
    },
    "godot": {
        "version": ["get_godot_version"],
        "project_info": ["get_project_info"],
        "list_projects": ["list_projects"],
        "create_scene": ["create_scene"],
        "add_node": ["add_node"],
        "save_scene": ["save_scene"],
        "run": ["run_project"],
        "console": ["get_debug_output"],
        "stop": ["stop_project"],
    },
    "blender": {
        "scene": ["get_scene_info"],
        "object": ["get_object_info"],
        "exec_code": ["execute_blender_code"],
    },
}

ENGINE_FACADE_TOOLS = [
    {
        "name": "ms_native_capabilities",
        "description": (
            "Show what the CONNECTED engine can actually do right now: its live native tool catalogue, "
            "which of those tools Multi-Script has a correct dialect wrapper for, and which higher-level "
            "operations are therefore available. Call this once at the start of an engine session instead "
            "of guessing tool names, and again after a reconnect. Read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Engine server id: roblox, unity, godot or blender. Omit to report every connected engine."},
                "refresh": {"type": "boolean", "description": "Re-read the catalogue from the live server before reporting."},
            },
        },
    },
    {
        "name": "ms_native_read",
        "description": (
            "One read that works the same way on every engine: return the engine's current truth (scene/hierarchy, "
            "console, project metadata, or one script) using whatever native tool that engine actually exposes. "
            "Use it BEFORE any change so you are not editing from memory, and again after to prove the change landed. "
            "Read-only, never mutates. Results include the exact native call used so you can trust the evidence."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Engine server id: roblox, unity, godot or blender."},
                "what": {
                    "type": "string",
                    "enum": ["tree", "state", "console", "project", "script", "object"],
                    "description": "tree = scene/hierarchy; state = engine status; console = output/errors; project = project metadata; script = one file's text; object = one object's transform/mesh/material.",
                },
                "target": {"type": "string", "description": "What to read for `script` (a path/dot-path) or `object` (an object name). Ignored by the other kinds."},
                "query": {"type": "string", "description": "Optional filter for tree/console reads (e.g. 'Workspace', 'error')."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 4000, "description": "Max rows/lines to return. Clamped to a safe range; any value is accepted."},
                "studio_id": {"type": "string", "description": "Roblox only. The exact id from ms_native_read what=state; supplied automatically when only one Studio is connected."},
            },
            "required": ["server", "what"],
        },
    },
    {
        "name": "ms_native_write",
        "description": (
            "One write that works the same way on every engine, translating your intent into that engine's real "
            "dialect so you never have to remember whether a scene edit is `manage_scene`+action, a `projectPath` "
            "call, or an `execute_luau` block. Supports creating or replacing a script, adding a scene node, "
            "creating a scene, setting object properties, and running arbitrary engine code. Always read back "
            "(`ms_native_read`) after a write and never claim success without that evidence."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Engine server id: roblox, unity, godot or blender."},
                "what": {
                    "type": "string",
                    "enum": ["script", "node", "scene", "properties", "code"],
                    "description": "script = create/replace a script's text; node = add a node/GameObject; scene = create a new scene; properties = set fields on an existing object; code = run raw engine code.",
                },
                "target": {"type": "string", "description": "The object to act on: a script path/dot-path, an object name or dot-path, or a scene path. Not used by `code`."},
                "content": {"type": "string", "description": "The payload: the script's full text, the code to run, or a JSON object string of the properties to set. For a script, pass the ENTIRE new body - a replace is not a diff."},
                "properties": {"type": "object", "description": "Key/value fields to set for what=properties (e.g. {\"Position\": [1,2,3], \"Anchored\": true})."},
                "node_type": {"type": "string", "description": "For what=node: the engine's own class name (Part, GameObject, Node2D, Sprite2D...)."},
                "name": {"type": "string", "description": "For what=node/scene: the name to GIVE the new object (e.g. 'Health', 'Level1'). Omit to derive it from node_type. Without it the new node would inherit the scene/target path as its name - which is why it exists."},
                "parent": {"type": "string", "description": "For what=node: where to attach it (a parent path or node name)."},
                "mode": {"type": "string", "enum": ["Edit", "Server", "Client"], "description": "Roblox only: which DataModel to act in. Default Edit."},
                "project_path": {"type": "string", "description": "Godot only: absolute path of the folder CONTAINING project.godot. Supplied automatically when known."},
                "studio_id": {"type": "string", "description": "Roblox only: the exact id from ms_native_read what=state. Supplied automatically when a single Studio is connected."},
                "dry_run": {"type": "boolean", "description": "When true, return the exact native call that WOULD be issued without executing it. Use it to confirm the shape on a new engine."},
            },
            "required": ["server", "what"],
        },
    },
    {
        "name": "ms_native_verify",
        "description": (
            "Prove a change actually took effect on the connected engine, rather than assuming it did. Captures a "
            "fingerprint of the engine's real state (scene contents, script hash/text, console output), so you can "
            "diff before and after. Pass `before` from an earlier call to get an explicit changed/unchanged verdict "
            "with the evidence attached. Read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Engine server id: roblox, unity, godot or blender."},
                "what": {
                    "type": "string",
                    "enum": ["tree", "script", "console", "project"],
                    "description": "What to fingerprint. `tree` and `script` are the ones that change after an edit.",
                },
                "target": {"type": "string", "description": "The script path/dot-path when what=script. Ignored otherwise."},
                "before": {"type": "string", "description": "A fingerprint returned by a previous ms_native_verify call. When present, the result states plainly whether the engine changed and shows both sides."},
                "studio_id": {"type": "string", "description": "Roblox only: the exact Studio id."},
            },
            "required": ["server", "what"],
        },
    },
    {
        "name": "ms_native_batch",
        "description": (
            "Run an ordered list of native engine operations in one call, stopping at the first failure. Each step "
            "names a native tool and its arguments exactly as the engine advertises them; steps run against the same "
            "connected server with dialect translation applied. Use it for a known multi-step sequence (create script, "
            "refresh, validate, read console) so a single mistake cannot leave a half-applied change. Returns per-step "
            "status, so a failure tells you exactly which step stopped and why."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Engine server id: roblox, unity, godot or blender."},
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 40,
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool": {"type": "string", "description": "The native tool name exactly as advertised by the engine."},
                            "arguments": {"type": "object", "description": "That tool's arguments."},
                            "label": {"type": "string", "description": "Optional short label shown in the per-step report."},
                        },
                        "required": ["tool"],
                    },
                    "description": "The ordered operations to run.",
                },
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300, "description": "Per-step timeout. Clamped to 1..300; any value is accepted."},
                "dry_run": {"type": "boolean", "description": "Validate every step's tool name against the live catalogue and return the translated calls without executing anything."},
            },
            "required": ["server", "steps"],
        },
    },
    {
        "name": "ms_native_debug",
        "description": (
            "Diagnose why a native engine call is failing, without guessing: reports which servers are alive, which "
            "of the engine's required tools this connection actually advertises, the exact parameter dialect Multi-Script "
            "will use on the next call, and - for Roblox - whether studio_id resolution is currently unambiguous. "
            "Run it when a call returns 'invalid parameters', 'unknown command' or 'unknown tool' instead of retrying "
            "the same payload. Read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Engine server id: roblox, unity, godot or blender. Omit to diagnose every configured server."},
                "probe": {"type": "boolean", "description": "Also run a real read-only smoke test against the server so the diagnosis includes live evidence."},
            },
        },
    },
]
import studio_hub
import mobile_remote
import blender_workspace
import blender_pipeline
BLENDER_WORKSPACE=blender_workspace.Workspace(port=PORT+3)
PHONE_REMOTE=mobile_remote.Remote(port=PORT+2)
BUILTIN_TOOLS.extend(blender_workspace.TOOLS)
BUILTIN_TOOLS.extend(studio_hub.TOOLS)
BUILTIN_TOOLS.extend(ENGINE_FACADE_TOOLS)
if MEMORY_GRAPH is not None:
    BUILTIN_TOOLS.extend(json.loads(json.dumps(MEMORY_GRAPH.TOOLS)))
if WORKSPACE is not None:
    BUILTIN_TOOLS.extend(json.loads(json.dumps(WORKSPACE.TOOLS)))

# Bind every engine-named direct specialist to its actual target. Previously,
# some Studio craft schemas accepted any engine string even though their contract
# was Roblox/Unity/Godot/Blender-specific, allowing provider drift before MCP routing.
_ENGINE_TOOL_PREFIXES={"ms_roblox_":"roblox","ms_unity_":"unity","ms_godot_":"godot","ms_blender_":"blender"}
for _tool in BUILTIN_TOOLS:
    for _prefix,_engine in _ENGINE_TOOL_PREFIXES.items():
        if _tool.get("name","").startswith(_prefix):
            _props=(_tool.get("inputSchema") or {}).get("properties") or {}
            if "engine" in _props: _props["engine"]={"type":"string","enum":[_engine],"default":_engine}
            break

for _tool in BUILTIN_TOOLS:
    (_tool.get("inputSchema") or {}).setdefault("x-multiScriptCompatibility",{
        "liveSchemaRequired":True,
        "recursiveParameterValidation":True,
        "readBackRequiredAfterMutation":True,
        "schemaDriftPolicy":"refresh and revalidate; never guess",
    })

TOOL_MODEL_IMPROVEMENT_NOTE = " Improves provider-model decisions and verified native-tool execution; never substitutes guidance for an engine result."
for _tool in BUILTIN_TOOLS:
    if TOOL_MODEL_IMPROVEMENT_NOTE.strip() not in _tool.get("description", ""):
        _tool["description"] = _tool.get("description", "") + TOOL_MODEL_IMPROVEMENT_NOTE
BUILTIN_TOOL_NAMES = {t["name"] for t in BUILTIN_TOOLS}
BUILTIN_TOOL_BY_NAME = {t["name"]: t for t in BUILTIN_TOOLS}


def _resolve_schema_ref(root, ref):
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise ValueError(f"unsupported external schema reference: {ref}")
    node=root
    for part in ref[2:].split("/"):
        part=part.replace("~1","/").replace("~0","~")
        if not isinstance(node,dict) or part not in node: raise ValueError(f"unresolved schema reference: {ref}")
        node=node[part]
    return node


# Parameters where an EMPTY string is a legitimate VALUE, not a missing argument.
#
# `old_string:""` is the DOCUMENTED multi_edit CREATE/PREPEND sentinel - the tool
# note itself instructs the model to write exactly that ("To CREATE a script: set
# className ... and make the first edit old_string:\"\""). Treating "" as "omitted"
# made the documented create path impossible: the model wrote precisely what the
# docs told it to, and the validator answered "old_string is required" - a
# complaint it could never satisfy, because it HAD supplied the field. That is an
# unfixable loop, and it is what a live session kept hitting.
_EMPTY_STRING_IS_VALUE = {"old_string"}


def _apply_documented_sentinels(tool_name, arguments):
    """Fill sentinels a JSON Schema cannot express, BEFORE validation runs.

    multi_edit: creating a script means `className` PLUS `old_string:""`. If the
    caller supplies className (so the intent is unambiguously "create") and omits
    old_string entirely, the sentinel is what was meant - supply it rather than
    rejecting a call the model was told was correct.

    Deliberately narrow: only fires for multi_edit, only when className is present
    (an ordinary edit never passes className), and only when old_string is absent.
    An edit that simply forgot old_string still gets the corrective error.
    """
    if tool_name != "multi_edit" or not isinstance(arguments, dict): return
    edits = arguments.get("edits")
    if not isinstance(edits, list) or not arguments.get("className"): return
    for edit in edits:
        if isinstance(edit, dict) and "old_string" not in edit:
            edit["old_string"] = ""


def _normalize_tool_arguments(schema, arguments, tool_name="tool", lenient=False, warnings=None):
    """Recursively coerce and validate the practical JSON-Schema subset used by MCP.

    Supports nested objects/arrays, defaults, const/enum, nullable type unions,
    oneOf/anyOf/allOf, local $ref/$defs, additionalProperties, string/collection
    bounds, patterns and numeric bounds. Validation happens against the exact
    schema advertised by the live server immediately before every native call.
    """
    if arguments is None: arguments={}
    if isinstance(arguments,str):
        try: arguments=json.loads(arguments)
        except Exception: raise RuntimeError(f"{tool_name}: parameters must be a JSON object")
    if not isinstance(arguments,dict): raise RuntimeError(f"{tool_name}: parameters must be an object, got {type(arguments).__name__}")
    _apply_documented_sentinels(tool_name, arguments)
    root=schema if isinstance(schema,dict) else {"type":"object","properties":{}}

    def fail(path,msg): raise ValueError(f"{path} {msg}".strip())
    def soft(path,msg):
        # A constraint the engine itself will judge (pattern, bounds, uniqueness,
        # unknown keys). Strict mode rejects it; lenient mode - used AFTER the
        # repair pass - records it and lets the call through so the engine's own
        # message, which knows its real rules, is what the model sees.
        if lenient:
            if warnings is not None and len(warnings)<20: warnings.append(f"{path} {msg}".strip())
            return
        fail(path,msg)
    def convert(value,spec,path,depth=0):
        if depth>32: fail(path,"schema/value nesting exceeds 32 levels")
        spec=spec if isinstance(spec,dict) else {}
        if "$ref" in spec:
            merged=dict(_resolve_schema_ref(root,spec["$ref"])); merged.update({k:v for k,v in spec.items() if k!="$ref"}); spec=merged
        # Composition is common in generated Unity/Godot schemas.
        if "allOf" in spec:
            for branch in spec.get("allOf") or []: value=convert(value,branch,path,depth+1)
        alternatives=spec.get("oneOf") or spec.get("anyOf")
        if alternatives:
            successes=[]; branch_errors=[]
            for branch in alternatives:
                try: successes.append(convert(value,branch,path,depth+1))
                except ValueError as exc: branch_errors.append(str(exc))
            if not successes: fail(path,"does not match any allowed schema: "+" | ".join(branch_errors[:3]))
            if "oneOf" in spec and len(successes)>1:
                # Identical/coercion-equivalent branches are harmless; genuinely
                # ambiguous values are rejected before a server interprets them.
                if any(x!=successes[0] or type(x) is not type(successes[0]) for x in successes[1:]): soft(path,"matches multiple incompatible oneOf branches")
            value=successes[0]
        types=spec.get("type")
        if isinstance(types,list):
            if value is None and "null" in types: return None
            candidates=[t for t in types if t!="null"]
            last=None
            for typ in candidates:
                try: return convert(value,{**spec,"type":typ},path,depth+1)
                except ValueError as exc: last=exc
            if last: raise last
        typ=types or ("object" if "properties" in spec else None)
        if value is None:
            if spec.get("nullable") or typ in (None,"null"): return None
            fail(path,"must not be null")
        if typ=="string":
            if isinstance(value,(dict,list)): fail(path,"must be a string")
            value=str(value)
            if spec.get("minLength") is not None and len(value)<spec["minLength"]: soft(path,f"needs at least {spec['minLength']} character(s)")
            if spec.get("maxLength") is not None and len(value)>spec["maxLength"]: fail(path,f"allows at most {spec['maxLength']} character(s)")
            if spec.get("pattern") is not None:
                try: matched=re.search(spec["pattern"],value)
                except re.error as exc: fail(path,f"has invalid schema pattern: {exc}")
                if not matched: soft(path,f"must match pattern {spec['pattern']}")
        elif typ=="integer":
            if isinstance(value,bool): fail(path,"must be an integer")
            if isinstance(value,float) and not value.is_integer(): fail(path,"must be a whole integer")
            if isinstance(value,str) and not re.fullmatch(r"[+-]?\d+",value.strip()): fail(path,"must be an integer")
            try: value=int(value)
            except Exception: fail(path,"must be an integer")
        elif typ=="number":
            if isinstance(value,bool): fail(path,"must be a number")
            try: value=float(value)
            except Exception: fail(path,"must be a number")
            if not math.isfinite(value): fail(path,"must be finite")
        elif typ=="boolean":
            if isinstance(value,str):
                low=value.strip().lower()
                if low in ("true","1","yes","on"): value=True
                elif low in ("false","0","no","off"): value=False
                else: fail(path,"must be true or false")
            elif isinstance(value,(int,float)) and value in (0,1): value=bool(value)
            elif not isinstance(value,bool): fail(path,"must be a boolean")
        elif typ=="array":
            if isinstance(value,str):
                try: value=json.loads(value)
                except Exception:
                    item_type=(spec.get("items") or {}).get("type")
                    if item_type in (None,"string"): value=[x.strip() for x in value.split(",") if x.strip()]
                    else: fail(path,"must be a JSON array")
            if not isinstance(value,list): value=[value]
            item_spec=spec.get("items") or {}
            value=[convert(x,item_spec,f"{path}[{i}]",depth+1) for i,x in enumerate(value)]
            if spec.get("minItems") is not None and len(value)<spec["minItems"]: soft(path,f"needs at least {spec['minItems']} item(s)")
            if spec.get("maxItems") is not None and len(value)>spec["maxItems"]: soft(path,f"allows at most {spec['maxItems']} item(s)")
            if spec.get("uniqueItems"):
                markers=[json.dumps(x,sort_keys=True,default=str) for x in value]
                if len(markers)!=len(set(markers)): soft(path,"must contain unique items")
        elif typ=="object":
            if isinstance(value,str):
                try: value=json.loads(value)
                except Exception: fail(path,"must be a JSON object")
            if not isinstance(value,dict): fail(path,"must be an object")
            props=spec.get("properties") or {}; out=dict(value)
            for k,ps in props.items():
                if k not in out and isinstance(ps,dict) and "default" in ps: out[k]=ps["default"]
                if k in out: out[k]=convert(out[k],ps,f"{path}.{k}" if path else k,depth+1)
            for k in spec.get("required") or []:
                if k not in out or out[k] is None: fail(f"{path}.{k}" if path else k,"is required")
                # An empty/blank string is normally a genuine omission, but for a
                # content-matching sentinel field any string IS the value - "" means
                # "create/prepend", and whitespace can be real text to match. See
                # _EMPTY_STRING_IS_VALUE.
                if isinstance(out[k],str) and not out[k].strip() and k not in _EMPTY_STRING_IS_VALUE:
                    fail(f"{path}.{k}" if path else k,"is required")
            extra=spec.get("additionalProperties",True); unknown=[k for k in out if k not in props]
            if extra is False and unknown: soft(path,"contains unsupported parameter(s): "+", ".join(sorted(unknown)))
            if isinstance(extra,dict):
                for k in unknown: out[k]=convert(out[k],extra,f"{path}.{k}" if path else k,depth+1)
            if spec.get("minProperties") is not None and len(out)<spec["minProperties"]: soft(path,f"needs at least {spec['minProperties']} properties")
            if spec.get("maxProperties") is not None and len(out)>spec["maxProperties"]: soft(path,f"allows at most {spec['maxProperties']} properties")
            value=out
        elif typ=="null" and value is not None: fail(path,"must be null")
        if "const" in spec and value!=spec["const"]: fail(path,f"must equal {spec['const']!r}")
        if "enum" in spec:
            exact=next((x for x in spec["enum"] if x==value and type(x) is type(value)),None)
            if exact is None and isinstance(value,str): exact=next((x for x in spec["enum"] if isinstance(x,str) and x.lower()==value.lower()),None)
            if exact is None: fail(path,"must be one of: "+", ".join(map(str,spec["enum"])))
            value=exact
        if isinstance(value,(int,float)) and not isinstance(value,bool):
            if spec.get("minimum") is not None and value<spec["minimum"]: soft(path,f"must be >= {spec['minimum']}")
            if spec.get("maximum") is not None and value>spec["maximum"]: soft(path,f"must be <= {spec['maximum']}")
            if spec.get("exclusiveMinimum") is not None and value<=spec["exclusiveMinimum"]: soft(path,f"must be > {spec['exclusiveMinimum']}")
            if spec.get("exclusiveMaximum") is not None and value>=spec["exclusiveMaximum"]: soft(path,f"must be < {spec['exclusiveMaximum']}")
        return value
    try: return convert(arguments,root,"parameters")
    except ValueError as exc: raise RuntimeError(f"{tool_name}: invalid parameters: {exc}") from None


def _safe_len(fn):
    try:
        return len(fn())
    except Exception:
        return None


_ENVELOPE_KEYS = ("arguments", "params", "parameters", "input", "args", "payload")


def _unwrap_envelope(schema, arguments):
    """Unwrap {"arguments": {...}} / {"params": "{...json...}" } when that key is
    not a real parameter of the tool. Without this the strict validator silently
    ignores the envelope and the tool runs on its defaults."""
    try:
        if isinstance(arguments, str):
            text = arguments.strip()
            if text[:1] == "{":
                arguments = json.loads(text)
        if not isinstance(arguments, dict) or len(arguments) != 1:
            return arguments, []
        (key, val), = arguments.items()
        if str(key).lower() not in _ENVELOPE_KEYS:
            return arguments, []
        props = (schema or {}).get("properties") if isinstance(schema, dict) else None
        if isinstance(props, dict) and key in props:
            return arguments, []
        if isinstance(val, str) and val.strip()[:1] == "{":
            val = json.loads(val)
        if isinstance(val, dict):
            return val, [f"unwrapped '{key}' envelope"]
    except Exception:
        pass
    return arguments, []


_CAPTURE_SEQ = [0]


def _autofill_required_ids(schema, arguments, tool_name=""):
    """Supply a throw-away `capture_id` for screen_capture-style tools.

    Roblox's screen_capture rejects a call without `capture_id`, but the id is
    only a label the server stamps on the image - a model has no reason to
    invent one and was getting a hard error for forgetting it. Returns
    (arguments, notes); the original dict is never mutated.
    """
    try:
        bare = str(tool_name or "").split("/")[-1]
        if bare != "screen_capture" or not isinstance(arguments, dict):
            return arguments, []
        props = (schema or {}).get("properties") if isinstance(schema, dict) else None
        if isinstance(props, dict) and props and "capture_id" not in props:
            return arguments, []
        for k in arguments:
            if str(k).lower().replace("-", "_") in ("capture_id", "captureid", "id"):
                if arguments.get(k) not in (None, ""):
                    return arguments, []
        _CAPTURE_SEQ[0] += 1
        out = {k: v for k, v in arguments.items()
               if str(k).lower().replace("-", "_") not in ("capture_id", "captureid", "id")}
        out["capture_id"] = f"ScreenCapture_{int(time.time()) % 100000}_{_CAPTURE_SEQ[0]}"
        return out, [f"added capture_id={out['capture_id']}"]
    except Exception:
        return arguments, []


def _resilient_arguments(schema, arguments, tool_name="tool"):
    """Validate a native engine call, REPAIRING what a machine can safely repair.

    Order: (1) strict validation - a clean call is passed through untouched and
    costs nothing; (2) on failure, `schema_repair` fixes the usual model slips
    (stringified numbers/JSON, {x,y,z} for vectors, enum case, renamed keys,
    wrapper envelopes, clamped ranges, dropped unsupported keys) and the result
    is re-validated leniently; (3) only if a REQUIRED value is genuinely absent
    does the call fail - and then with the tool's signature and a copy-ready
    minimal call, not just a path.

    Returns (clean_arguments, notes). `notes` is empty for a clean call.
    """
    arguments, unwrapped = _unwrap_envelope(schema, arguments)
    arguments, filled = _autofill_required_ids(schema, arguments, tool_name)
    if filled or unwrapped:
        clean, notes = _resilient_arguments(schema, arguments, tool_name)
        return clean, list(unwrapped) + list(filled) + list(notes)
    try:
        return _normalize_tool_arguments(schema, arguments, tool_name), []
    except RuntimeError as first:
        if _repair is None: raise
        repaired, notes = _repair.repair_arguments(schema, arguments, tool_name)
        warnings=[]
        try:
            clean = _normalize_tool_arguments(schema, repaired, tool_name, lenient=True, warnings=warnings)
        except RuntimeError as second:
            hint = _repair.describe(schema, tool_name)
            raise RuntimeError(f"{second}" + (f"\n{hint}" if hint else "")) from None
        notes = list(notes) + [f"left for the engine to judge: {w}" for w in warnings]
        return clean, notes


def _annotate_repairs(result, notes):
    """Append the repair notes to a tool result so the model learns the shape."""
    if not notes or not isinstance(result, dict): return result
    try:
        line = "[schema auto-repair] " + "; ".join(notes[:8]) + (" ..." if len(notes) > 8 else "")
        log(f"schema auto-repair: {'; '.join(notes[:4])}", "yl")
        out = dict(result)
        text = str(out.get("text") or "")
        merged = None
        if text.lstrip()[:1] == "{":
            # JSON object result: keep it valid JSON by carrying the note inside it.
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    obj["_schema_auto_repair"] = list(notes[:8])
                    merged = json.dumps(obj, indent=2)
            except Exception:
                merged = None
        out["text"] = merged if merged is not None else (text + ("\n" if text else "") + line)
        out["schemaRepairs"] = notes[:20]
        return out
    except Exception:
        return result


def _schema_risk_analysis(schema):
    """Heuristic pre-call risk, not a promise or observed failure rate."""
    issues=[]; supported={"type","properties","required","items","enum","const","default","minimum","maximum","exclusiveMinimum","exclusiveMaximum","minLength","maxLength","pattern","minItems","maxItems","uniqueItems","minProperties","maxProperties","additionalProperties","nullable","oneOf","anyOf","allOf","$ref","$defs","definitions","description","title","format","examples","example","deprecated","readOnly","writeOnly"}
    def walk(node,path="schema",depth=0):
        if not isinstance(node,dict): issues.append({"path":path,"severity":"high","code":"schema-not-object"}); return
        if depth>32: issues.append({"path":path,"severity":"high","code":"schema-too-deep"}); return
        for k in node:
            if k not in supported and not k.startswith("x-"): issues.append({"path":path,"severity":"low","code":"keyword-not-enforced","keyword":k})
        if "$ref" in node and (not isinstance(node["$ref"],str) or not node["$ref"].startswith("#/")): issues.append({"path":path,"severity":"high","code":"external-ref"})
        if node.get("type")=="object" or "properties" in node:
            props=node.get("properties") or {}
            for req in node.get("required") or []:
                if req not in props: issues.append({"path":path,"severity":"high","code":"required-property-undefined","property":req})
            if node.get("additionalProperties",True) is True and props: issues.append({"path":path,"severity":"low","code":"unknown-parameters-allowed"})
            for k,v in props.items(): walk(v,f"{path}.{k}",depth+1)
            if isinstance(node.get("additionalProperties"),dict): walk(node["additionalProperties"],path+".*",depth+1)
        if node.get("type")=="array" and not isinstance(node.get("items"),dict): issues.append({"path":path,"severity":"medium","code":"array-items-unspecified"})
        if isinstance(node.get("items"),dict): walk(node["items"],path+"[]",depth+1)
        for key in ("oneOf","anyOf","allOf"):
            for i,v in enumerate(node.get(key) or []): walk(v,f"{path}.{key}[{i}]",depth+1)
    if not isinstance(schema,dict) or not schema: issues.append({"path":"schema","severity":"high","code":"missing-input-schema"})
    else: walk(schema)
    weights={"high":0.18,"medium":0.08,"low":0.025}; risk=min(0.85,0.015+sum(weights[x["severity"]] for x in issues))
    return {"estimatedPreCallFailureProbability":round(risk,3),"riskBand":"high" if risk>=0.3 else "medium" if risk>=0.12 else "low","issues":issues,"basis":"deterministic schema-shape heuristic; not an observed production failure rate"}


SKILL_TOOL_COVERAGE = [
    "design-production", "architecture-code", "input-camera-character", "combat-abilities",
    "ai-navigation", "physics-simulation", "multiplayer-networking", "persistence-economy",
    "world-levels", "ui-ux", "animation", "textures-art", "vfx", "audio",
    "performance-platform", "testing-release", "studio-craft", "mastery-expansion",
]

CORE_DIRECT_TOOLS = [
    "ms_provider_execution_optimizer", "ms_tool_selection_optimizer", "ms_engine_command_planner",
    "ms_failure_recovery_director", "ms_performance_budget_designer", "ms_test_coverage_designer",
    "ms_edge_case_generator", "ms_cross_platform_validation", "ms_accessibility_validation",
    "ms_result_evidence_synthesizer", "ms_production_readiness_director", "ms_studio_critic_loop",
]

def _infer_request_intent(request, engine):
    text=str(request or "").lower(); engine=str(engine or "general").lower()
    intents=[]; defaults=[]; slice_parts=[]; acceptance=[]; signals=[]
    def has(*xs): return any(x in text for x in xs)
    if has("shooter","fps","third person shooter","gun game","shooting game"):
        signals.append("shooter")
        intents += ["responsive aiming, movement and weapon handling", "readable combat encounters with fair enemy behavior", "authoritative damage, ammunition and hit validation", "complete combat feedback across animation, VFX, audio, camera and UI"]
        defaults += ["derive first/third-person perspective from the existing project; if absent choose the smallest reversible camera setup", "data-driven weapon stats and fire modes", "server-authoritative consequential hits for multiplayer", "clear crosshair, ammo, damage and objective states", "keyboard/mouse plus relevant controller/touch mappings"]
        slice_parts += ["one polished player controller and camera", "one production-ready weapon with equip/reload/fire states", "one enemy archetype with perception, navigation and combat", "one readable combat arena", "health/ammo HUD and feedback", "win/fail/restart loop"]
        acceptance += ["aiming, firing, reload, damage, death and restart work end to end", "animation/VFX/audio/camera cues align with actual hit timing", "combat remains readable and responsive under target latency/frame rate", "weapon and enemy values are data-driven and testable"]
    if has("realistic","photoreal","realism","real graphics","realistic graphics"):
        signals.append("realistic-graphics")
        intents += ["physically coherent materials, lighting, scale and atmosphere", "grounded detail hierarchy that remains readable from gameplay camera", "high visual fidelity constrained by the weakest target platform"]
        defaults += ["use reference-driven PBR material values rather than arbitrary shininess", "consistent real-world scale, texel density and material response", "balanced direct/indirect lighting, exposure, reflection and shadow behavior", "quality tiers, LOD/streaming and shader fallbacks that preserve the art direction"]
        slice_parts += ["reference-calibrated environment materials", "cohesive lighting and post-processing", "representative hero asset plus optimized surrounding kit", "runtime quality tiers and profiler capture"]
        acceptance += ["materials remain believable under representative lighting", "exposure, shadows and reflections are stable during gameplay", "silhouette and targets remain readable without flattening the realistic look", "GPU, memory, loading and draw/instance budgets pass on the weakest target"]
    genre_specs = [
      (("rpg","role playing"),"rpg",["character progression, quests, inventory and meaningful choices","data-driven combat/economy/persistence that can grow without rewrites"],["one quest with dialogue and reward","one combat encounter","inventory/equipment and save/load","progression feedback and complete states"]),
      (("platformer","obby"),"platformer",["precise movement, readable traversal and fair recovery","camera, animation, level metrics and game feel tuned together"],["movement/jump controller","teaching-to-mastery level slice","checkpoint/death/restart loop","camera and animation feedback"]),
      (("horror",),"horror",["sustained tension through pacing, uncertainty and restrained feedback","atmosphere, AI, lighting and spatial audio that support playability"],["explorable tension space","threat behavior and recovery","lighting/audio state progression","failure/restart and accessibility options"]),
      (("racing","race game"),"racing",["predictable but expressive handling","track readability, opponents, camera, audio and haptics tuned as one experience"],["one tuned vehicle","one complete track/lap loop","opponent or time trial","HUD, finish/restart and performance pass"]),
      (("survival",),"survival",["clear resource pressure and long-term decision making","crafting, inventory, threats, persistence and world systems with fair recovery"],["gather-craft-survive loop","inventory and recipe slice","one environmental or AI threat","save/load and fail/recover states"]),
      (("tycoon","simulator"),"simulation",["legible progression and satisfying production feedback","safe economy, automation, persistence and scalable UI"],["earn-spend-upgrade loop","one automation chain","progression UI","save/load and economy instrumentation"]),
    ]
    for terms,signal,pillars,parts in genre_specs:
        if has(*terms):
            signals.append(signal);intents+=pillars;slice_parts+=parts
            defaults += ["derive genre details from the existing project before inventing new conventions","make tunable values data-driven","ship one complete loop before adding breadth"]
            acceptance += ["the primary loop works from onboarding through success/failure and restart","connected feedback, progression and difficulty remain coherent","representative edge cases and target-platform budgets pass"]
    if has("game","make me","build","create") and not intents:
        signals.append("broad-creation")
        intents += ["a complete playable vertical slice rather than disconnected assets", "coherent design, implementation, polish, optimization and validation"]
        defaults += ["reuse existing project conventions", "choose reversible professional defaults", "include complete interaction and failure states"]
        slice_parts += ["primary player loop", "supporting UI and feedback", "representative content", "test and performance pass"]
    # Deduplicate while preserving priority.
    uniq=lambda xs:list(dict.fromkeys(xs))
    return {"signals":uniq(signals),"productPillars":uniq(intents),"professionalDefaults":uniq(defaults),"verticalSlice":uniq(slice_parts),"acceptanceCriteria":uniq(acceptance),"inferenceRule":"Infer reversible details only; explicit user requirements and existing project conventions always win."}

REQUEST_SYNONYMS = {
    "rpg":["quest","dialogue","inventory","progression","economy","save","combat"],
    "horror":["atmosphere","lighting","audio","tension","ai","camera","accessibility"],
    "platformer":["movement","jump","camera","animation","level","checkpoint","gamefeel"],
    "racing":["vehicle","handling","camera","track","ai","haptics","performance"],
    "survival":["crafting","inventory","resources","ai","persistence","weather","balance"],
    "tycoon":["economy","progression","automation","ui","persistence","analytics"],
    "simulator":["simulation","progression","economy","ui","persistence","performance"],
    "multiplayer":["networking","authority","matchmaking","latency","security","reconnect"],
    "mobile":["touch","responsive","performance","memory","battery","accessibility"],
    "stylized":["art","material","lighting","texture","vfx","composition"],
}
def _request_words(request):
    words={w for w in re.findall(r"[a-z0-9]+", str(request or "").lower()) if len(w)>2}
    expanded=set(words)
    for word in words: expanded.update(REQUEST_SYNONYMS.get(word,[]))
    return expanded

def _catalog_score(identifier, item, words):
    name_text=f"{identifier} {item.get('name','')} {item.get('category','')}".lower()
    body=f"{item.get('description','')} {' '.join(item.get('tags') or [])} {' '.join(item.get('signals') or [])}".lower()
    return sum(6 for w in words if w in name_text) + sum(2 for w in words if w in body)

PROP_NOUNS = ("tree","rock","boulder","boat","ship","sailboat","raft","submarine","tank","car","truck","bus","van","vehicle","bike","bicycle","motorcycle","train","plane","airplane","helicopter","jet","rocket","stick","sword","gun","weapon","axe","pickaxe","hammer","bow","shield","staff","wand","spear","knife","dagger","house","home","building","castle","tower","bridge","fence","wall","door","gate","window","roof","chair","table","bed","couch","sofa","desk","lamp","crate","box","barrel","chest","coin","gem","crystal","flower","bush","plant","grass","mushroom","campfire","fire pit","tent","statue","fountain","sign","portal","machine","robot","turret","cannon","lantern","torch","key","book","candle","cave","tombstone","gravestone","windmill","barn","kiosk","vending machine","ladder","stairs","pipe","generator","cabin","hut","shed","garage","tunnel","pillar","column","arch","mailbox","trash can","bin","cart","wagon","carriage","skateboard","hoverboard","jetpack","backpack","hat","crown","trophy","flag","banner","dock","pier","lighthouse","tire","wheel","engine","furnace","anvil","cauldron","throne","altar","totem","obelisk","ruins","skyscraper","apartment","mansion","fortress","igloo","pyramid","spaceship","ufo","drone","mech","dragon statue","snowman","pumpkin","gift","bench","swing","seesaw","playground","tree house","treehouse","maze","platform","ramp","map","level","island","arena","terrain","world","floor","road","track","course","obstacle","trap","spike","lava","jump pad","trampoline","elevator","lift","zipline","cliff","hill","river","lake","pond","waterfall","village","town","city","street","shop building","base","fort","bunker","dungeon","room","hallway","corridor","spawn","spawn point","lobby area")
BUILD_VERBS = ("make","build","create","add","spawn","design","model","craft","place","generate","put","construct","need a","want a","give me a","can you make","can you build")
CODE_ONLY_WORDS = ("script","datastore","remote","leaderboard","leaderstats","system","module","function","gui","ui ","menu","hud","button","screen","data","save","error","bug","fix")

def _has_word(text, words):
    """Whole-word match (plural allowed), so 'ui' never matches inside 'build'."""
    import re as _re
    return any(_re.search(r"(?<![a-z0-9])"+_re.escape(w.strip())+r"(?:s|es)?(?![a-z0-9])", text) for w in words)

MESH_RULES_CHAR_BUDGET = 44000
_BOILERPLATE_STEP_STARTS = ("Goal:", "Inspect the relevant live schemas once", "Use actual artifacts, logs/read-back")

def _rules_for_request(item, request, budget=None, only_sections=None):
    """Full rules for a mandatory skill, minus generic boilerplate. A skill may declare ruleSections:
    optional sections that are only sent when the request mentions one of their words (the rest stays
    retrievable with ms_get_skill). This keeps the start-up context small without hiding anything.

    With a budget (characters) the always-on sections are kept whole and the matched optional sections are
    added best match first until the budget is used; the others are named in a pointer. With only_sections
    only those optional sections (plus the always-on ones) are returned."""
    text = " " + str(request or "").lower() + " "
    optional = item.get("ruleSections") or {}
    defaults = item.get("ruleSectionDefaults") or {}
    boost = item.get("ruleSectionBoost") or {}
    named = {h for ys in defaults.values() for h in ys}  # style sections: when matched, the user named them
    def _score(h):
        s = sum(1 for w in optional.get(h, []) if _has_word(text, [w]))
        if s and h in named: s += 95
        return s + (boost.get(h, 0) if s else 0)
    def _wanted(h):
        # A default section is also sent when none of the sections it yields to matched the request.
        if only_sections is not None:
            return h in only_sections
        if _has_word(text, optional[h]):
            return True
        return h in defaults and not any(o in optional and _has_word(text, optional[o]) for o in defaults[h])
    rows, skipped = [], []
    for x in item.get("steps", []):
        if x.startswith(_BOILERPLATE_STEP_STARTS):
            continue
        head = x.split(":", 1)[0] if ":" in x[:60] else ""
        if head in optional and not _wanted(head):
            if head not in skipped: skipped.append(head)
            continue
        rows.append((head, x))
    trimmed = []
    if budget is not None:
        sizes, order = {}, []
        for head, x in rows:
            if head in optional:
                sizes[head] = sizes.get(head, 0) + len(x)
                if head not in order: order.append(head)
        fixed = sum(len(x) for head, x in rows if head not in optional)
        room = max(0, budget - fixed)
        keep, used = set(), 0
        for h in sorted(order, key=lambda h: (-_score(h), order.index(h))):
            if used + sizes[h] <= room:
                keep.add(h); used += sizes[h]
            else:
                trimmed.append(h)
        rows = [(h, x) for h, x in rows if h not in optional or h in keep]
    if only_sections is not None:
        rows = [(h, x) for h, x in rows if h in optional]
    out = [x for _, x in rows]
    skipped += [h for h in trimmed if h not in skipped]
    if only_sections is not None:
        skipped = []
    if skipped:
        out.append("Not shown (not needed for this request, or kept out to keep this short); load them with ms_get_skill {\"skill_id\": \"<this skill>\", \"sections\": [names]} if the task needs them: " + ", ".join(skipped) + ".")
    return out

def _props_requested(text):
    import re as _re
    if not _has_word(text, BUILD_VERBS):
        return False
    return _has_word(text, PROP_NOUNS)

# Order matters: the first few skills that apply receive their full rules in the director result.
MANDATORY_SKILL_TRIGGERS = {
    "code-quality": None,  # always for Roblox work
    "fix-errors": ("error", "bug", "broken", "not working", "doesn't work", "doesnt work", "isn't working", "isnt working", "fix", "nil", "stuck", "glitch", "glitchy", "crash", "fail", "failed", "won't", "wont", "can't", "cant", "cannot", "lag", "laggy", "stutter", "output", "warning", "nothing happens", "infinite yield", "not showing", "doesn't show", "not saving", "not loading", "not appearing", "not firing", "wrong", "weird", "jitter", "jittery", "falls through", "fall through", "disappears", "invisible", "freeze", "frozen", "timeout", "red text", "yellow text", "why is", "why does", "why doesn't", "why won't", "problem", "issue"),
    "check-props": _props_requested,
    "check-clean-ui": ("ui", "gui", "hud", "menu", "screen", "button", "shop", "store", "interface", "inventory", "backpack", "hotbar", "popup", "pop-up", "dialog", "dialogue", "leaderboard", "scoreboard", "health bar", "stamina bar", "progress bar", "bar", "minimap", "settings", "options", "codes", "redeem", "daily reward", "quest log", "tooltip", "notification", "toast", "loading screen", "title screen", "main menu", "pause", "crosshair", "timer", "counter", "label", "textbox", "slider", "toggle", "checkbox", "dropdown", "tab", "panel", "frame", "window", "overlay", "cursor", "icon", "billboard", "surface gui", "rebirth screen", "skip button", "claim", "studded", "studs", "lego", "skeuomorphic", "steampunk", "neumorphism", "neubrutalism", "claymorphism", "glassmorphism", "gacha", "halftone", "sticker", "blueprint", "y2k", "bento", "ui style", "ui theme", "viewport", "viewportframe", "3d icon", "3d model in ui", "item preview", "pet card", "brainrot"),
    "scripting-power": ("optimize", "optimise", "optimized", "optimization", "performance", "faster", "slow", "lag", "laggy", "fps", "memory", "leak", "leaks", "profiler", "benchmark", "efficient", "refactor", "framework", "architecture", "modulescript", "oop", "metatable", "typed", "async", "promise", "promises", "coroutine", "parallel", "actor", "actors", "multithread", "signal", "signals", "cleanup", "pooling", "debounce", "cooldown", "remote", "remotes", "remoteevent", "remotefunction", "bandwidth", "networking", "buffer", "buffers", "exploit", "exploits", "exploiter", "exploiters", "cheat", "cheats", "cheater", "cheaters", "anticheat", "anti-cheat", "secure", "security", "validate", "validation", "datastore", "datastores", "profilestore", "profileservice", "session lock", "receipt", "memorystore", "messagingservice", "raycast", "raycasts", "hitbox", "hitboxes", "collision group", "collision groups", "network ownership", "streamingenabled", "rojo", "wally", "selene", "stylua", "luau-lsp", "github", "jest", "testez", "unit test", "unit tests", "roblox-ts", "linter", "lint", "debugging", "breakpoint", "breakpoints", "tween", "tweens", "renderstepped", "heartbeat", "runservice", "contextactionservice", "userinputservice", "keybind", "keybinds", "strict mode", "table.create", "collectionservice", "best practice", "best practices", "clean code", "professional code", "pro code", "open cloud", "opencloud", "httpservice", "http request", "input action", "gamepad", "controller support", "constraint", "physics"),
    "game-systems": ("simulator", "tycoon", "clicker", "idle", "obby", "obstacle course", "coin", "collect", "collectible", "currency", "cash", "money", "gold", "gem", "points", "score", "xp", "experience", "level up", "leveling", "rebirth", "prestige", "egg", "hatch", "pet", "quest", "mission", "reward", "daily", "streak", "shop", "store", "buy", "sell", "upgrade", "unlock", "multiplier", "boost", "gamepass", "game pass", "developer product", "robux", "leaderboard", "economy", "inventory", "crafting", "mining", "farming", "fishing", "harvest", "wave", "round", "lobby", "match", "team", "checkpoint", "stage", "race", "horror", "survival", "battle royale", "minigame", "mini game", "game mode", "stud", "progression", "save data", "datastore", "subscription", "subscriptions", "teleport", "teleporting", "matchmaking", "analytics", "live ops", "liveops", "daily reward", "daily rewards", "trading", "trade", "leaderboard data", "badge", "badges", "monetization", "monetisation", "cutscene", "case opening", "egg hatch", "dice roll", "intro sequence"),
    "npc-pathfinding": ("npc", "enemy", "enemies", "monster", "zombie", "boss", "mob", "creature", "animal", "follower", "guard", "villager", "shopkeeper", "vendor", "patrol", "chase", "follow", "pathfind", "pathfinding", "navigate", "bot", "drone", "wander", "flee", "hunter", "killer", "ghost", "spider", "dog", "cat", "bear", "skeleton", "wolf", "dragon", "alien", "horror", "pet", "companion", "minion"),
    "vfx-assets": ("vfx", "beam", "trail", "shockwave", "slash", "aura", "portal", "teleport", "muzzle", "tracer", "impact frame", "camera shake", "screen shake", "post processing", "post-processing", "colorcorrection", "color correction", "depth of field", "atmosphere", "cinematic", "mood", "sunset", "sunrise", "night", "moody", "emitter", "emitters", "hit effect", "pickup effect", "level up", "lightning bolt", "effect", "particle", "light", "lighting", "glow", "neon", "fire", "smoke", "explosion", "magic", "spell", "spark", "trail", "beam", "aura", "shockwave", "fog", "atmosphere", "bloom", "blur", "shadow", "rain", "snow", "lightning", "toolbox", "asset", "free model", "creator store", "jumpscare", "jump scare", "scare", "flicker", "flashlight", "skybox", "sky", "horror", "dust", "confetti", "sparkle", "burst", "impact", "hit effect", "audio", "sound", "music", "sfx", "sound effect", "acoustic", "reverb"),
}

def _mandatory_skill_ids(request, engine, skills):
    """Skills that must be applied (not merely suggested) for Roblox work. They are forced to the front of the mesh."""
    if str(engine or "").lower() != "roblox":
        return []
    text = " " + str(request or "").lower() + " "
    out = []
    for sid, words in MANDATORY_SKILL_TRIGGERS.items():
        if sid not in skills:
            continue
        if words is None or (callable(words) and words(text)) or (not callable(words) and _has_word(text, words)):
            out.append(sid)
    return out

def _build_skill_tool_mesh(request, engine, skills, virtual_tools, direct_limit=32, skill_limit=30, virtual_limit=24):
    # The limits are CLAMPED here, never rejected. The advertised schemas
    # therefore declare minimum:1 and let this floor do the work.
    #
    # They used to declare minimum:8 (and 4 for virtual tools), which made the
    # schema STRICTER than the implementation: a caller asking for 5 skills got
    # "parameters.max_skills must be >= 8" instead of simply being raised to 8 -
    # even though that is exactly what this line would have done. A hard schema
    # floor on a value the handler already clamps is a rejection with no purpose,
    # and it produced a live error loop on ms_studio_director.
    intent=_infer_request_intent(request,engine); words=_request_words(request+" "+" ".join(intent["signals"]+intent["productPillars"])); engine=str(engine or "general").lower()
    direct_limit=max(8,min(32,int(direct_limit or 32)));skill_limit=max(8,min(40,int(skill_limit or 30)));virtual_limit=max(4,min(30,int(virtual_limit or 24)))
    # Direct tools: cross-cutting execution specialists are always present, then
    # request-specific craft/system specialists join the same execution mesh.
    direct=[]
    text=str(request or "").lower()
    # Route obvious craft language to the concrete specialists first. These are
    # broad capability signals, not named request presets.
    routed=[]
    def route(*names):
        for name in names:
            if name and name in ADVANCED_DIRECT_CONTRACTS and name not in routed: routed.append(name)
    if any(x in text for x in ("realistic","photoreal","realism","real graphics")):
        route("ms_realistic_art_production","ms_pbr_material_studio","ms_lighting_production","ms_shader_production","ms_environment_production","ms_visual_quality_audit","ms_performance_budget_designer")
    if any(x in text for x in ("shooter","fps","shooting game","gun game")):
        route("ms_combat_system_design","ms_combat_feel_director","ms_camera_system_design","ms_input_mapping_plan","ms_ai_behavior_design","ms_animation_state_machine","ms_vfx_production","ms_audio_production","ms_network_efficiency_optimizer","ms_gameplay_quality_audit")
    if any(x in text for x in ("rpg","role playing")):
        route("ms_quest_system_design","ms_dialogue_production","ms_inventory_economy_design","ms_save_migration_plan","ms_combat_system_design","ms_progression_experience_polish")
    if any(x in text for x in ("platformer","obby")):
        route("ms_character_controller_review","ms_movement_feel_director","ms_camera_system_design","ms_level_design_review","ms_animation_state_machine")
    if "horror" in text:
        route("ms_lighting_production","ms_audio_production","ms_ai_behavior_design","ms_environment_production","ms_camera_system_design","ms_accessibility_validation")
    if any(x in text for x in ("racing","race game")):
        route("ms_vehicle_system_design","ms_camera_system_design","ms_controller_haptics","ms_ai_behavior_design","ms_level_design_review","ms_performance_budget_designer")
    if "survival" in text:
        route("ms_inventory_economy_design","ms_weather_system","ms_ai_behavior_design","ms_save_migration_plan","ms_world_streaming_plan")
    if any(x in text for x in ("tycoon","simulator")):
        route("ms_inventory_economy_design","ms_progression_experience_polish","ms_telemetry_plan","ms_liveops_plan","ms_save_migration_plan","ms_uiux_production")
    if any(x in text for x in ("ui","gui","hud","menu","screen","button","shop","interface")):
        route({"roblox":"ms_roblox_gui_studio","unity":"ms_unity_ui_studio","godot":"ms_godot_ui_studio"}.get(engine,"ms_gui_design_studio"),"ms_ui_motion_design","ms_responsive_interface_polish","ms_controller_navigation_ux","ms_accessible_interface_polish","ms_usability_polish")
    if any(x in text for x in ("animat","walk","run","dash","attack","idle","motion","rig")):
        route({"roblox":"ms_roblox_animation_studio","unity":"ms_unity_animation_studio","godot":"ms_godot_animation_studio","blender":"ms_blender_animation_studio"}.get(engine,"ms_animation_state_machine"),"ms_animation_state_machine","ms_animation_runtime_qa","ms_locomotion_animation_polish")
    if any(x in text for x in ("model","mesh","character","prop","environment","texture","material","light","art")):
        route("ms_blender_model_studio" if engine=="blender" or "model" in text or "mesh" in text else "ms_environment_art_studio","ms_character_model_production" if "character" in text else "ms_pbr_material_studio","ms_visual_quality_audit")
    if any(x in text for x in ("combat","movement","camera","gameplay","feel")):
        route("ms_combat_feel_director" if "combat" in text else "ms_game_feel_director","ms_gameplay_quality_audit","ms_camera_system_design")
    direct.extend(routed)
    for name in CORE_DIRECT_TOOLS:
        if name in ADVANCED_DIRECT_CONTRACTS and name not in direct: direct.append(name)
    ranked_direct=sorted(((_catalog_score(name,spec,words),name) for name,spec in ADVANCED_DIRECT_CONTRACTS.items()),key=lambda x:(-x[0],x[1]))
    for _,name in ranked_direct:
        if name not in direct: direct.append(name)
        if len(direct)>=direct_limit: break
    # Skills: guarantee broad discipline coverage first, then add the strongest
    # extra specialists. No single skill or generic checklist replaces them.
    candidates=[]
    for sid,item in skills.items():
        # Browser-installed skills have per-chat/workspace activation settings.
        # The browser supplies active methods with each prompt; discovery must
        # not silently re-enable a disabled or out-of-scope custom workflow.
        # An explicit id still permits deliberate retrieval/application.
        if item.get("source")=="user-installed" and sid not in str(request): continue
        se=str(item.get("engine") or "general").lower()
        if engine not in {"general","figma"} and se not in {engine,"general"}: continue
        if engine=="figma" and se not in {"figma","general"}: continue
        score=_catalog_score(sid,item,words)+(4 if se==engine else 0)
        candidates.append((score,sid,item))
    candidates.sort(key=lambda x:(-x[0],x[1]))
    selected=[]
    for domain in SKILL_TOOL_COVERAGE:
        hit=next(((score,sid,item) for score,sid,item in candidates if item.get("capabilityDomain")==domain and sid not in selected),None)
        if hit: selected.append(hit[1])
    # Text ranking must not erase a production role. Preserve discipline
    # diversity first, then ensure design, execution, polish, performance and QA.
    for role in ("design", "implementation", "polish", "optimization", "validation"):
        if any(skills[sid].get("capabilityRole")==role for sid in selected): continue
        hit=next((sid for _,sid,item in candidates if item.get("capabilityRole")==role and sid not in selected),None)
        if hit: selected.append(hit)
    for _,sid,_ in candidates:
        if sid not in selected: selected.append(sid)
        if len(selected)>=skill_limit: break
    forced=_mandatory_skill_ids(request,engine,skills)
    selected=forced+[sid for sid in selected if sid not in forced]
    selected=selected[:max(skill_limit,len(forced))]
    # Virtual engine specialists: take the strongest tool from every available
    # domain, then fill with more request-specific specialists.
    vc=[]
    for tid,item in virtual_tools.items():
        if item.get("engine")!=engine: continue
        vc.append((_catalog_score(tid,item,words),tid,item))
    vc.sort(key=lambda x:(-x[0],x[1]));virtual=[]
    for domain in sorted({item.get("domain") for _,_,item in vc if item.get("domain")}):
        hit=next(((score,tid,item) for score,tid,item in vc if item.get("domain")==domain and tid not in virtual),None)
        if hit: virtual.append(hit[1])
    for _,tid,_ in vc:
        if tid not in virtual: virtual.append(tid)
        if len(virtual)>=virtual_limit: break
    virtual=virtual[:virtual_limit]
    domains=[]
    for sid in selected:
        d=skills[sid].get("capabilityDomain") or "general"
        if d not in domains: domains.append(d)
    roles=[]
    for sid in selected:
        r=skills[sid].get("capabilityRole") or "implementation"
        if r not in roles: roles.append(r)
    # A list of IDs alone is discovery, not applied skill guidance. Supply a
    # bounded set of the best matching methods in the actual tool result. The
    # full library stays retrievable without injecting hundreds of workflows.
    from skill_workflows import contract as skill_contract
    from ultra_handbook import manual_for
    applied=[]; rules_used=0
    # Mandatory skills come first and carry their full rules, because a short
    # inspect/execute/verify summary cannot hold the real standard.
    by_id={sid:item for _,sid,item in candidates}
    order=[sid for sid in forced if sid in by_id]+[sid for _,sid,_ in candidates if sid in selected and sid not in forced]
    for sid in order:
        item=by_id[sid]
        workflow=item.get("executionWorkflow") or skill_contract(sid,item)
        entry={"id":sid,"name":item.get("name",sid),"inspect":workflow["inspect"],"execute":workflow["execute"],"verify":workflow["verify"],"craft":workflow.get("craft",""),"methodRetrieval":{"skill_id":sid,"manual_id":manual_for(sid,item),"instruction":"Use ms_get_skill with objective=current request for concrete phase checkpoints. manual_sections retrieves a deeper phase. Load only relevant methods and reuse them."}}
        if sid in forced:
            entry["mandatory"]=True
            # The whole result is pasted into the chat, so cap the rule text: a 70k reply made sends slow and flaky.
            # A skill's always-on rules stay whole; its optional sections are added best match first until the
            # budget is used, and the rest are named so they can be loaded with ms_get_skill {sections: [...]}.
            rules_now=None
            if sum(1 for e in applied if e.get("rules"))<5:
                rules_now=_rules_for_request(item, request, budget=max(6000, min(int(item.get('meshBudget') or 20000), MESH_RULES_CHAR_BUDGET-rules_used)))
            if rules_now is not None and rules_used+sum(len(x) for x in rules_now)<=MESH_RULES_CHAR_BUDGET+8000:
                entry["rules"]=rules_now; rules_used+=sum(len(x) for x in rules_now)
            else:
                entry["rules"]=[]; entry["fullRules"]="Mandatory: load the full rules with ms_get_skill {\"skill_id\":\""+sid+"\"} before building this part."
        applied.append(entry)
        if len(applied)>=6: break
    return {
        "directTools":direct[:direct_limit], "skills":selected, "virtualTools":virtual,
        "appliedSkillWorkflows":applied,
        "scopeRule":"Apply relevant methods within the current user request. For discovery, review or questions, return verified findings without unrequested edits. Workflows do not grant tools or permissions. Retrieve ms_get_skill for full details before an unfamiliar operation.",
        "interpretedIntent":intent,
        "skillDomains":domains, "skillRoles":roles,
        "simultaneousCoverage":True,
        "coordinationRule":"Use relevant selected specialists to improve their aspects of the same deliverable. Merge compatible requirements and skip unrelated methods; preserve the user's scope, existing style and tool permissions.",
        "executionPattern":["inspect project and preserve conventions","turn inferred intent into one playable vertical slice","implement core loop before breadth","integrate art, controls, camera, animation, VFX, audio and UI around the loop","add architecture, authority, persistence and lifecycle safety","profile the weakest target and optimize measured bottlenecks","playtest complete states, fix defects and read back final evidence"],
    }

# ── Roblox build/verify workflow tools (6.17.7) ──────────────────────────
# These compose the official Studio MCP tools into the sequences a builder
# actually repeats. They never fabricate an engine action: every one of them
# either reads real state back or returns the exact native calls to make. When
# the engine is unavailable they say so plainly rather than inventing a result.

# Console lines that are noise, not failures. Roblox prints an enormous amount of
# deprecation chatter and plugin output; ranking a deprecation warning as a
# failure trains the model to "fix" things that are not broken.
_ROBLOX_NOISE = re.compile(
    r"(?i)(deprecat|will be removed|loaded plugin|plugin (?:loaded|unloaded)|"
    r"unknown global|script timeout: *\d+ms|running on|coregui)"
)
_ROBLOX_FATAL = re.compile(
    r"(?i)(attempt to index nil|attempt to call a nil|is not a valid member|"
    r"stack begin|stack end|infinite yield|unable to cast|"
    r"too many (?:events|iterations)|out of memory|segmentation)"
)
_ROBLOX_WARN = re.compile(r"(?i)(yield|warning|caution|may not|should be|unused)")

# The boundary mistakes that actually break shipped Roblox games, as opposed to
# style preferences. Each entry is (regex, severity, what it means, the fix).
_SCRIPT_RULES = [
    # (line regex, severity, what it means, fix). Each is one line; multi-line checks are in _script_source_checks.
    (re.compile(r"require\s*\(\s*\d{5,}\s*\)"),
     "warn", "Requires a raw asset id instead of a script reference.",
     "Require a ModuleScript by instance. A raw id breaks when the asset is re-uploaded and runs code you did not write."),
    (re.compile(r"Instance\.new\s*\(\s*[\"']?(?:RemoteEvent|RemoteFunction)"),
     "warn", "Creates a RemoteEvent/RemoteFunction at runtime.",
     "Create remotes once (in Studio or a server script at startup) and reference them; a remote made late may not exist on the client yet."),
    (re.compile(r"\.OnServerEvent\s*:\s*Connect\s*\(\s*function\s*\(\s*\)"),
     "high", "A RemoteEvent handler ignores the player argument.",
     "The first argument is always the calling player. Ignoring it means you cannot check who is asking or rate-limit them."),
    (re.compile(r"\bInvokeClient\s*\("),
     "high", "The server calls InvokeClient.",
     "A client can refuse to answer or never return, which hangs the server thread forever. Use a RemoteEvent and reply with another event."),
    (re.compile(r"(?<![\w.:])(?<!task\.)wait\s*\("),
     "warn", "Uses the deprecated global wait().",
     "Use task.wait(). The global wait() is throttled and deprecated."),
    (re.compile(r"(?<![\w.:])(?:spawn|delay)\s*\("),
     "warn", "Uses the deprecated global spawn()/delay().",
     "Use task.spawn(), task.defer() or task.delay(). The globals are throttled and deprecated."),
    (re.compile(r":connect\s*\(|:disconnect\s*\("),
     "warn", "Uses the deprecated lowercase :connect()/:disconnect().",
     "Use :Connect() and :Disconnect()."),
    (re.compile(r"Instance\.new\s*\(\s*[\"'][A-Za-z]+[\"']\s*,\s*[^)\s]"),
     "warn", "Passes the parent as the second argument of Instance.new.",
     "Set every property first and assign .Parent last. The parent argument makes the engine replicate each later change separately."),
    (re.compile(r"\b(?:BodyVelocity|BodyPosition|BodyGyro|BodyForce|BodyAngularVelocity|BodyThrust)\b"),
     "warn", "Uses a deprecated legacy body mover.",
     "Use LinearVelocity, AlignPosition, AlignOrientation, VectorForce or AngularVelocity."),
    (re.compile(r"Humanoid\s*:\s*LoadAnimation|:LoadAnimation\s*\("),
     "warn", "Loads an animation on the Humanoid.",
     "Load animations on the Humanoid's Animator (animator:LoadAnimation) and keep the returned track."),
    (re.compile(r"game\.Players\.LocalPlayer|Players\.LocalPlayer"),
     "high", "References LocalPlayer.",
     "LocalPlayer is nil on the server. In a server script this line errors at runtime; use the player passed in by the event."),
    (re.compile(r"\b(?:loadstring|getfenv|setfenv)\b"),
     "high", "Uses loadstring/getfenv/setfenv.",
     "loadstring is disabled by default and a security risk; getfenv/setfenv defeat optimisation. Restructure the code instead."),
    (re.compile(r":FindFirstChild\s*\([^)]*\)\s*[.:]\s*\w"),
     "high", "Uses the result of FindFirstChild without checking it.",
     "FindFirstChild returns nil when nothing matches, so this errors with 'attempt to index nil'. Check it first, or use WaitForChild on things that must exist."),
    (re.compile(r"\.Touched\s*:\s*Connect"),
     "info", "Connects to Touched.",
     "Touched fires many times per contact; add a debounce or a per-player cooldown before doing anything that costs."),
    (re.compile(r"\bTeleportService\b.*\bTeleport(?:Async)?\s*\((?!.*pcall)"),
     "warn", "Teleports without protecting the call.",
     "Teleports fail for many reasons; wrap in pcall and handle TeleportInitFailed."),
]


def _script_source_checks(src):
    """Checks that need more than one line. Returns (severity, line, meaning, evidence, fix) rows."""
    lines = src.splitlines()
    out = []
    has = lambda rx: re.search(rx, src) is not None
    # Endless loop with no yield inside it. Walk the block so a wait further down still counts.
    for i, line in enumerate(lines):
        if re.match(r"\s*while\s+(?:true|1)\s+do\b", line):
            depth, yielded = 0, False
            for j in range(i, min(len(lines), i + 400)):
                body = re.sub(r"--.*$", "", lines[j])
                depth += len(re.findall(r"\b(?:do|then|function|repeat)\b", body))
                depth -= len(re.findall(r"\b(?:end|until)\b", body))
                if re.search(r"\bwait\s*\(|:Wait\s*\(|\.Heartbeat|\.RenderStepped|\.Stepped|task\.defer", body):
                    yielded = True
                if depth <= 0 and j > i:
                    break
            if not yielded:
                out.append(("high", i + 1, "An endless loop with no yield inside it.",
                            line.strip()[:200], "Add task.wait() inside the loop. Without a yield the script times out and the game freezes."))
    # DataStore calls must be protected, retried, and flushed on shutdown.
    if has(r":(?:GetAsync|SetAsync|UpdateAsync|IncrementAsync|RemoveAsync)\s*\("):
        if not has(r"\bpcall\s*\(|\bxpcall\s*\("):
            out.append(("high", None, "DataStore calls are not wrapped in pcall.",
                        "GetAsync/SetAsync/UpdateAsync found with no pcall in the script",
                        "Every DataStore request can fail (throttling, outages). Wrap in pcall, retry with a short wait, and never let a failed load overwrite saved data."))
        if has(r":SetAsync\s*\("):
            out.append(("warn", None, "Saves with SetAsync.",
                        "SetAsync found", "Prefer UpdateAsync so two servers saving at once cannot overwrite each other with stale data."))
        if not has(r"BindToClose"):
            out.append(("warn", None, "No BindToClose save on shutdown.",
                        "DataStore used but game:BindToClose is never called",
                        "Save every player in game:BindToClose, or the last seconds of progress are lost when the server shuts down."))
    # Players joining: handle people who were already there.
    if has(r"PlayerAdded\s*:\s*Connect") and not has(r"GetPlayers\s*\("):
        out.append(("warn", None, "PlayerAdded is used without handling players already in the game.",
                    "PlayerAdded:Connect found but GetPlayers is never called",
                    "In Studio the player can join before the script connects. Also loop game.Players:GetPlayers() once so nobody is missed."))
    # Remote handlers should check what they were sent.
    for i, line in enumerate(lines):
        m = re.search(r"\.OnServerEvent\s*:\s*Connect\s*\(\s*function\s*\(\s*(\w+)\s*[,)]", line)
        if m:
            block = "\n".join(lines[i:i + 25])
            if not re.search(r"typeof\s*\(|type\s*\(|assert\s*\(|tonumber\s*\(|:IsA\s*\(", block):
                out.append(("high", i + 1, "A RemoteEvent handler uses its arguments without checking them.",
                            line.strip()[:200],
                            "Never trust the client: check the type, range and ownership of every argument, and rate-limit the player."))
    # Connections made in a loop or per-player with no cleanup.
    if has(r"\.Touched\s*:\s*Connect|\.Changed\s*:\s*Connect|\.Heartbeat\s*:\s*Connect") and not has(r":Disconnect\s*\(|:Destroy\s*\(|Maid|Janitor|Trove|DisconnectAll"):
        out.append(("info", None, "Connections are made but nothing ever disconnects them.",
                    "no :Disconnect() / cleanup found",
                    "Connections held by per-player or per-object code leak when that thing is removed; keep them in a table and disconnect on cleanup."))
    # Per-frame work that allocates.
    for i, line in enumerate(lines):
        if re.search(r"(?:RenderStepped|Heartbeat|Stepped)\s*:\s*Connect", line):
            block = "\n".join(lines[i:i + 30])
            if re.search(r"Instance\.new|:Clone\s*\(|:GetChildren\s*\(|:GetDescendants\s*\(|FindFirstChild", block):
                out.append(("warn", i + 1, "A per-frame callback creates or searches instances every frame.",
                            line.strip()[:200], "Cache references outside the callback and reuse objects instead of creating them 60 times a second."))
    return out


# Snapshot store for the scene diff, keyed by label. Bounded so a long session
# cannot grow the bridge's memory without limit.
_SCENE_SNAPSHOTS = {}
_SCENE_SNAPSHOT_ORDER = []
_SCENE_SNAPSHOT_MAX = 12


def _roblox_catalogue(manager):
    """The live Studio tool names, or None when the engine is not reachable.

    Returning None (rather than []) is what lets callers distinguish "Studio is
    not connected" from "Studio is connected and advertises nothing", which are
    very different problems with different fixes.
    """
    try:
        tools = manager.list_server_tools("roblox", refresh=False)
    except Exception:
        return None
    if tools is None:
        return None
    return sorted(str(t.get("name") or "") for t in tools if t.get("name"))


def _roblox_unavailable(what, manager):
    cat = _roblox_catalogue(manager)
    return {"text": json.dumps({
        "available": False,
        "capability": what,
        "reason": "The Roblox Studio MCP server is not reachable from the bridge.",
        "fixes": [
            "Open Roblox Studio and load a place.",
            "In Studio: Assistant Settings > MCP Servers, enable the MCP server.",
            "Confirm the bridge reports roblox as alive via list_commands or ms_bridge_status.",
        ],
    }, indent=2), "images": []}


def _roblox_read(manager, tool, arguments, timeout=30):
    """Call a native Studio tool and return its text, or None on any failure.

    Deliberately swallows the error and returns None: these workflow tools use
    several native calls and must degrade to a useful partial answer rather than
    aborting on the first one that a given Studio build does not support.
    """
    try:
        r = manager.call_on_server("roblox", tool, arguments or {}, timeout)
    except Exception:
        return None
    if not isinstance(r, dict) or r.get("ok") is False:
        return None
    text = r.get("text")
    return text if isinstance(text, str) else None


def _roblox_build_verifier(args, manager):
    path = str(args.get("path") or "").strip()
    if not path:
        raise RuntimeError("path is required (the instance path you claimed to create or change)")
    if _roblox_catalogue(manager) is None:
        return _roblox_unavailable("build verification", manager)

    expect = str(args.get("expect") or "").strip()
    props = [str(p) for p in (args.get("properties") or []) if str(p).strip()]
    expected = args.get("expected_properties") or {}
    if not isinstance(expected, dict):
        expected = {}

    # Read the instance back from the live place. inspect_instance is the native
    # read; fall back to search_game_tree by name when the path form differs.
    raw = _roblox_read(manager, "inspect_instance", {"path": path})
    lookup_used = "inspect_instance"
    if raw is None:
        leaf = path.split(".")[-1]
        raw = _roblox_read(manager, "search_game_tree", {"query": leaf})
        lookup_used = "search_game_tree"

    if raw is None:
        return {"text": json.dumps({
            "verdict": "unverifiable",
            "path": path,
            "found": None,
            "reason": "Studio accepted no read call for this path. The instance may not exist, or the path form may not match this Studio build.",
            "nextSteps": [
                "Re-check the path spelling and casing - Roblox paths are case-sensitive.",
                f"Call search_game_tree with query '{path.split('.')[-1]}' to see whether anything by that name exists at all.",
                "If it genuinely does not exist, the build step did not take effect and should be retried.",
            ],
            "lookupUsed": lookup_used,
        }, indent=2), "images": []}

    # Parse the read result conservatively: whatever JSON we can recover, plus the
    # raw text so the model can see the real evidence rather than our summary.
    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None

    found = parsed is not None
    checks = []
    if expected:
        actual = {}
        if isinstance(parsed, dict):
            # Properties may sit at the top level or under a "properties" key.
            src = parsed.get("properties") if isinstance(parsed.get("properties"), dict) else parsed
            for k in expected:
                actual[k] = src.get(k) if isinstance(src, dict) else None
        for k, want in expected.items():
            got = actual.get(k)
            checks.append({
                "property": k,
                "expected": want,
                "actual": got,
                "match": str(got) == str(want),
            })
    if props and isinstance(parsed, dict):
        src = parsed.get("properties") if isinstance(parsed.get("properties"), dict) else parsed
        for k in props:
            if any(c["property"] == k for c in checks):
                continue
            checks.append({"property": k, "expected": None, "actual": (src or {}).get(k), "match": None})

    mismatched = [c for c in checks if c["match"] is False]
    unmatched = [c for c in checks if c["match"] is None]

    verdict = "verified" if found and not mismatched else ("mismatched" if mismatched else ("partially-verified" if unmatched else "found"))
    if not found:
        verdict = "unverifiable"

    return {"text": json.dumps({
        "verdict": verdict,
        "path": path,
        "found": found,
        "expectation": expect or None,
        "lookupUsed": lookup_used,
        "propertyChecks": checks,
        "mismatched": mismatched,
        "uncompared": unmatched,
        "rawEvidence": raw[:4000],
        "note": ("Property comparisons marked match:null could not be resolved from the read payload - treat them as unproven, not as correct."
                 if unmatched else "All requested comparisons resolved against live Studio state."),
    }, indent=2), "images": []}


def _roblox_ui_audit(args, manager):
    import ui_audit
    if _roblox_catalogue(manager) is None:
        return _roblox_unavailable("UI auditing", manager)
    target = "player" if str(args.get("target") or "starter").lower() == "player" else "starter"
    call = {"code": ui_audit.build_code(target, args.get("root") or ""), "datamodel_type": "Client" if target == "player" else "Edit"}
    sid = str(args.get("studio_id") or "").strip()
    if not sid:
        sid, _reason = _facade_roblox_studio_id(args, manager)
    if sid:
        call["studio_id"] = sid
    try:
        r = manager.call_on_server("roblox", "execute_luau", call, 60)
    except Exception as e:
        return {"text": json.dumps({"ok": False, "error": f"Studio did not run the audit: {e}"}), "images": []}
    if not isinstance(r, dict) or r.get("ok") is False:
        err = (r or {}).get("error") if isinstance(r, dict) else None
        return {"text": json.dumps({"ok": False, "error": f"Studio did not run the audit: {err or 'no answer'}. If several Studios are open pass studio_id; for target=player start a play test first."}), "images": []}
    return {"text": json.dumps(ui_audit.summarize(ui_audit.parse(r.get("text"))), indent=1), "images": []}


def _roblox_script_audit(args, manager):
    paths = [str(p).strip() for p in (args.get("paths") or []) if str(p).strip()]
    scope = str(args.get("scope") or "").strip()
    limit = max(1, min(25, int(args.get("limit") or 10)))
    if _roblox_catalogue(manager) is None:
        return _roblox_unavailable("script auditing", manager)
    if not paths and not scope:
        raise RuntimeError("provide paths (specific scripts) or scope (a subtree to discover scripts under)")

    if not paths and scope:
        # Discover scripts under the scope via the native tree search.
        listing = _roblox_read(manager, "search_game_tree", {"query": scope})
        if listing:
            for m in re.finditer(r"([A-Za-z0-9_.]+\.(?:[A-Za-z0-9_]+))", listing):
                candidate = m.group(1)
                if candidate not in paths:
                    paths.append(candidate)
                if len(paths) >= limit:
                    break
        # Discovery found nothing usable. Rather than silently auditing zero
        # scripts (which reads as "clean"), audit the scope path itself - the
        # caller named a real instance, so reading it directly is the honest
        # fallback and usually finds the script they meant.
        if not paths:
            paths.append(scope)

    audited = []
    for p in paths[:limit]:
        src = _roblox_read(manager, "script_read", {"path": p})
        if src is None:
            src = _roblox_read(manager, "script_grep", {"path": p, "pattern": "."})
        if src is None:
            audited.append({"path": p, "readable": False, "reason": "No readable source was returned for this path."})
            continue
        findings = []
        for rx, sev, meaning, fix in _SCRIPT_RULES:
            hits = 0
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("--"):
                    continue
                if rx.search(line):
                    hits += 1
                    if hits <= 3:
                        findings.append({
                            "severity": sev, "line": i, "rule": meaning,
                            "evidence": line.strip()[:200], "fix": fix or None,
                        })
            if hits > 3:
                findings.append({"severity": sev, "line": None, "rule": meaning,
                                 "evidence": f"{hits} total occurrences", "fix": fix or None})
        for sev, ln, meaning, evidence, fix in _script_source_checks(src):
            findings.append({"severity": sev, "line": ln, "rule": meaning, "evidence": evidence, "fix": fix})
        try:
            import luau_lint, roblox_docs
            ctx = "server" if re.search(r"ServerScriptService|ServerStorage", p) else ("client" if re.search(r"StarterPlayer|StarterGui|StarterPack|PlayerGui|StarterCharacter|ReplicatedFirst", p) else "auto")
            src_lines = src.splitlines()
            numbered = sum(1 for ln in src_lines if re.match(r"^\s*\d+\s*[|:]", ln))
            plain = "\n".join(re.sub(r"^\s*\d+\s*[|:] ?", "", ln, count=1) for ln in src_lines) if src_lines and numbered >= 0.8 * len(src_lines) else src
            for f in luau_lint.analyze(plain, roblox_docs.known_globals(), context=ctx, want=("syntax", "scope", "context")):
                if f["severity"] == "info": continue
                ev = src_lines[f["line"] - 1].strip()[:200] if f["line"] and f["line"] <= len(src_lines) else ""
                findings.append({"severity": "high" if f["severity"] == "error" else "warn", "line": f["line"], "rule": f["message"], "evidence": ev, "fix": None})
        except Exception:
            pass
        order = {"high": 0, "warn": 1, "info": 2}
        findings.sort(key=lambda f: order.get(f["severity"], 3))
        audited.append({
            "path": p, "readable": True, "lineCount": len(src.splitlines()),
            "highCount": sum(1 for f in findings if f["severity"] == "high"),
            "warnCount": sum(1 for f in findings if f["severity"] == "warn"),
            "findings": findings[:40],
        })

    total_high = sum(a.get("highCount", 0) for a in audited)
    return {"text": json.dumps({
        "auditedCount": len(audited),
        "totalHighSeverity": total_high,
        "scripts": audited,
        "note": "This audits source that Studio actually returned. Rules target defects that break shipped games, not style. A finding is a prompt to look, not proof of a bug.",
    }, indent=2), "images": []}


def _roblox_playtest_director(args, manager):
    scenario = str(args.get("scenario") or "").strip()
    if not scenario:
        raise RuntimeError("scenario is required (what you want the playtest to prove)")
    mode = str(args.get("mode") or "play").lower()
    if mode not in ("play", "run", "server"):
        mode = "play"
    inputs = [str(x) for x in (args.get("inputs") or []) if str(x).strip()]
    expect = str(args.get("expect") or "").strip()
    auto = bool(args.get("auto_run"))

    dm = "Client" if mode == "play" else ("Server" if mode == "server" else "Edit")
    plan = [
        {"step": 1, "action": "get_studio_state", "why": "Confirm a place is loaded and editable before starting.",
         "arguments": {}},
        {"step": 2, "action": "start_stop_play", "why": f"Start a real {mode} session.",
         "arguments": {"datamodel_type": dm, "action": "start"}},
    ]
    n = 3
    for item in inputs:
        plan.append({"step": n, "action": "user_keyboard_input", "why": f"Exercise: {item}",
                     "arguments": {"datamodel_type": "Client", "note": item}})
        n += 1
    plan.append({"step": n, "action": "get_console_output", "why": "Capture everything the run printed.", "arguments": {}})
    n += 1
    plan.append({"step": n, "action": "start_stop_play", "why": "Stop the session cleanly so the place is not left in play mode.",
                 "arguments": {"datamodel_type": dm, "action": "stop"}})

    result = {
        "scenario": scenario,
        "mode": mode,
        "expectedOutcome": expect or None,
        "plan": plan,
        "executed": False,
        "note": "The plan is returned without acting. Re-run with auto_run true to execute it for real, or make the calls yourself in order.",
    }
    if not auto:
        return {"text": json.dumps(result, indent=2), "images": []}

    # Planning needs no engine, so the plan above is always returned. Executing
    # does, and this is where that is enforced - after the plan has been built,
    # so a missing engine costs the user nothing.
    if _roblox_catalogue(manager) is None:
        result["executed"] = False
        result["available"] = False
        result["reason"] = "The Roblox Studio MCP server is not reachable, so the plan could not be executed."
        result["fixes"] = [
            "Open Roblox Studio and load a place.",
            "In Studio: Assistant Settings > MCP Servers, enable the MCP server.",
        ]
        return {"text": json.dumps(result, indent=2), "images": []}

    # Execute for real. Stop at the first failed step: continuing after a failed
    # start would capture an empty console and read as a false pass.
    trace = []
    failed_at = None
    for step in plan:
        tool = step["action"]
        call_args = dict(step["arguments"])
        call_args.pop("note", None)
        text = _roblox_read(manager, tool, call_args, timeout=45)
        ok = text is not None
        trace.append({"step": step["step"], "action": tool, "ok": ok,
                      "result": (text or "")[:2000] if ok else None})
        if not ok:
            failed_at = step["step"]
            break
        # A started session needs a moment to actually construct the world before
        # input is meaningful; without this the first input lands on nothing.
        if tool == "start_stop_play" and step["step"] == 2:
            time.sleep(1.5)

    console = ""
    for t in trace:
        if t["action"] == "get_console_output" and t.get("result"):
            console = t["result"]
            break
    triage = None
    if console:
        try:
            triage = json.loads(_roblox_error_triage({"output": console})["text"])
        except Exception:
            triage = None

    result.update({
        "executed": True,
        "failedAtStep": failed_at,
        "trace": trace,
        "consoleIssues": (triage or {}).get("realIssues"),
        "consoleFindings": (triage or {}).get("findings", [])[:20],
        "note": ("Executed the plan against live Studio. Read the trace: a step with ok:false is where it stopped, "
                 "and everything after it did not run.") if failed_at is None else
                (f"Execution stopped at step {failed_at} because that call did not succeed. Later steps did not run - "
                 "the playtest is incomplete, not passed."),
    })
    return {"text": json.dumps(result, indent=2), "images": []}


_SCOUT_KIND_TO_TYPE = {"model": "Model", "mesh": "MeshPart", "image": "Image", "decal": "Decal", "audio": "Audio", "package": "Package", "video": "Video"}


def _scout_thumbnail_urls(raw):
    """Thumbnail API links in the order the search result lists them."""
    seen, out = set(), []
    for m in re.finditer(r"https://thumbnails\.roblox\.com/[^\"\s\\)\]}>]+", raw or ""):
        u = m.group(0).rstrip(",.;")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _scout_fetch_preview(url):
    """Fetch one real thumbnail as an image. Returns None on any failure."""
    import base64
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Multi-Script"})
        with urllib.request.urlopen(req, timeout=6) as r:
            meta = json.loads(r.read(20000).decode("utf-8", "replace"))
        rows = meta.get("data") if isinstance(meta, dict) else None
        image_url = (rows[0] or {}).get("imageUrl") if rows else None
        if not image_url or not str(image_url).startswith("https://"):
            return None
        req = urllib.request.Request(image_url, headers={"User-Agent": "Multi-Script"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = r.read(400000)
            mime = (r.headers.get("Content-Type") or "image/png").split(";")[0].strip()
        if not data or not mime.startswith("image/"):
            return None
        return {"data": base64.b64encode(data).decode("ascii"), "mimeType": mime}
    except Exception:
        return None


def _roblox_asset_scout(args, manager):
    query = str(args.get("query") or "").strip()
    if not query:
        raise RuntimeError("query is required")
    kind = str(args.get("kind") or "any").lower()
    in_place = bool(args.get("in_place"))
    limit = max(1, min(20, int(args.get("limit") or 8)))
    if _roblox_catalogue(manager) is None:
        return _roblox_unavailable("asset scouting", manager)

    if in_place:
        raw = _roblox_read(manager, "search_game_tree", {"query": query})
        return {"text": json.dumps({
            "scope": "current place",
            "query": query,
            "results": [{"raw": raw[:6000]} if raw else []],
            "note": ("Results are the live tree search, verbatim. Read the names from it yourself - "
                     "this tool never invents an asset id."),
        }, indent=2), "images": []}

    # Creator Store search through the native asset tool. Real argument names of the
    # Studio tool: query, assetType, maxResults, scope, facets, tags, priceFilter,
    # verifiedCreatorsOnly. Several phrasings are tried because one query often
    # returns keyword-stuffed or off-topic results.
    queries = [query] + [str(q).strip() for q in (args.get("alt_queries") or []) if str(q).strip()]
    queries = list(dict.fromkeys(queries))[:4]
    verified_first = args.get("verified_only")
    verified_first = True if verified_first is None else bool(verified_first)
    studio_id = str(args.get("studio_id") or "").strip()
    asset_type = _SCOUT_KIND_TO_TYPE.get(kind)

    def one(q, verified):
        arg = {"query": q, "scope": str(args.get("scope") or "creator_store"), "maxResults": limit,
               "priceFilter": str(args.get("price") or "free")}
        if asset_type: arg["assetType"] = asset_type
        if args.get("facets"): arg["facets"] = [str(x) for x in args["facets"]][:6]
        if args.get("tags"): arg["tags"] = [str(x) for x in args["tags"]][:6]
        if verified: arg["verifiedCreatorsOnly"] = True
        if studio_id: arg["studio_id"] = studio_id
        for tool in ("search_asset", "search_assets"):
            raw = _roblox_read(manager, tool, arg)
            if raw: return tool, raw
        return None, None

    groups, used, relaxed = [], None, False
    for q in queries:
        tool, raw = one(q, verified_first)
        if raw is not None and verified_first and len(raw.strip()) < 80:
            tool, raw2 = one(q, False)
            if raw2: raw, relaxed = raw2, True
        if raw:
            used = tool
            groups.append({"query": q, "raw": raw[:5000]})
    if not groups:
        return {"text": json.dumps({
            "scope": "creator store",
            "queries": queries,
            "results": [],
            "available": False,
            "note": ("This Studio build returned nothing for these searches, or advertises no asset-search tool. "
                     "Do not invent an asset id. Try different words (the plain noun plus a style word), or build the "
                     "asset directly from Parts or UI shapes, or ask the user to supply one."),
        }, indent=2), "images": []}

    images, previews = [], []
    if args.get("preview", True) and kind in ("any", "image", "decal", "model", "mesh"):
        urls = []
        for gi, g in enumerate(groups):
            for ri, u in enumerate(_scout_thumbnail_urls(g["raw"])[:5]):
                urls.append((gi, ri, u))
        urls = urls[:8]
        if urls:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                got = list(pool.map(lambda t: _scout_fetch_preview(t[2]), urls))
            for (gi, ri, _u), img in zip(urls, got):
                if img:
                    images.append(img)
                    previews.append({"image": len(images), "query": groups[gi]["query"], "resultNumber": ri + 1})
    return {"text": json.dumps({
        "scope": "creator store",
        "kind": kind,
        "toolUsed": used,
        "freeOnly": str(args.get("price") or "free") == "free",
        "verifiedCreatorsOnly": verified_first and not relaxed,
        "verifiedFilterRelaxed": relaxed,
        "searches": groups,
        "previews": previews,
        "note": ("Raw results from the live tool, verbatim. Use only ids that appear here - never construct one. "
                 "The attached images are the real thumbnails of the first results, in the order listed in previews; "
                 "LOOK at them and reject any that do not match the name, have baked-in text, a solid or checkered "
                 "background, the wrong style or low quality. Then insert the best one and check it at its final size."),
    }, indent=2), "images": images}


def _roblox_scene_diff(args, manager):
    action = str(args.get("action") or "").strip().lower()
    if action == "list":
        return {"text": json.dumps({
            "snapshots": [{"label": k, "capturedAt": _SCENE_SNAPSHOTS[k]["at"], "path": _SCENE_SNAPSHOTS[k]["path"],
                           "instances": len(_SCENE_SNAPSHOTS[k]["flat"])} for k in _SCENE_SNAPSHOT_ORDER],
        }, indent=2), "images": []}

    if action == "capture":
        path = str(args.get("path") or "Workspace").strip()
        label = str(args.get("label") or "").strip() or f"{path}@{int(time.time())}"
        depth = max(1, min(6, int(args.get("depth") or 3)))
        if _roblox_catalogue(manager) is None:
            return _roblox_unavailable("scene capture", manager)
        raw = _roblox_read(manager, "search_game_tree", {"query": path, "max_depth": depth})
        if raw is None:
            raw = _roblox_read(manager, "get_studio_state", {})
        if raw is None:
            return {"text": json.dumps({
                "captured": False, "path": path,
                "reason": "Studio returned nothing to capture for this path.",
            }, indent=2), "images": []}
        # Flatten the read into a {path: line} map so compare is a set operation.
        flat = {}
        for line in raw.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                flat[s[:160]] = True
        _SCENE_SNAPSHOTS[label] = {"at": time.time(), "path": path, "flat": flat, "raw": raw[:6000]}
        _SCENE_SNAPSHOT_ORDER.append(label)
        while len(_SCENE_SNAPSHOT_ORDER) > _SCENE_SNAPSHOT_MAX:
            old = _SCENE_SNAPSHOT_ORDER.pop(0)
            _SCENE_SNAPSHOTS.pop(old, None)
        return {"text": json.dumps({
            "captured": True, "label": label, "path": path,
            "instances": len(flat),
            "note": "Snapshot recorded. Change the place, capture again, then compare.",
        }, indent=2), "images": []}

    if action == "compare":
        before = str(args.get("before") or "").strip()
        after = str(args.get("after") or "").strip()
        if before not in _SCENE_SNAPSHOTS or after not in _SCENE_SNAPSHOTS:
            return {"text": json.dumps({
                "compared": False,
                "reason": "One or both snapshot labels are unknown.",
                "known": list(_SCENE_SNAPSHOTS.keys()),
            }, indent=2), "images": []}
        a = _SCENE_SNAPSHOTS[before]["flat"]
        b = _SCENE_SNAPSHOTS[after]["flat"]
        added = sorted(set(b) - set(a))
        removed = sorted(set(a) - set(b))
        return {"text": json.dumps({
            "compared": True,
            "before": before, "after": after,
            "addedCount": len(added), "removedCount": len(removed),
            "added": added[:60], "removed": removed[:60],
            "note": ("This compares the readable tree lines Studio returned, so it reports instance-level "
                     "additions and removals exactly, and property changes only where a line differs textually."),
        }, indent=2), "images": []}

    raise RuntimeError("action must be capture, compare or list")


def _roblox_error_triage(args):
    output = args.get("output")
    read_live = bool(args.get("read_live"))
    if output is None and not read_live:
        raise RuntimeError("provide output (raw console text) or set read_live true")
    if not isinstance(output, str):
        output = "" if output is None else str(output)

    findings = []
    for i, line in enumerate(output.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        if _ROBLOX_FATAL.search(s):
            sev = "high"
        elif _ROBLOX_NOISE.search(s):
            sev = "noise"
        elif _ROBLOX_WARN.search(s):
            sev = "warn"
        else:
            continue
        findings.append({"line": i, "severity": sev, "text": s[:300]})

    order = {"high": 0, "warn": 1, "noise": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    real = [f for f in findings if f["severity"] != "noise"]
    noise = [f for f in findings if f["severity"] == "noise"]

    # Point at the most likely cause of the top real failure instead of leaving
    # the model to guess from the raw line.
    guidance = []
    for f in real[:3]:
        t = f["text"].lower()
        if "attempt to index nil" in t:
            guidance.append({"for": f["text"][:120],
                             "likelyCause": "Something was nil when it was indexed - usually a FindFirstChild that returned nothing, or a service fetched with the wrong name.",
                             "fix": "Guard the lookup and log the miss: use :FindFirstChild() with an if-check, and print the parent and the name you searched for."})
        elif "is not a valid member" in t:
            guidance.append({"for": f["text"][:120],
                             "likelyCause": "The property or child name does not exist on that instance in this build.",
                             "fix": "Re-read the instance in Studio and use the exact current name; some properties are renamed or removed between versions."})
        elif "infinite yield" in t:
            guidance.append({"for": f["text"][:120],
                             "likelyCause": "A WaitForChild or wait() never resolved - typically waiting on the client for something the server creates, or a typo in the child name.",
                             "fix": "Add a timeout to WaitForChild, and verify the instance is created on the side that is waiting."})
        elif "out of memory" in t:
            guidance.append({"for": f["text"][:120],
                             "likelyCause": "Unbounded growth - usually instances or connections created without cleanup.",
                             "fix": "Pool or destroy instances, and :Disconnect() connections you no longer need."})
    return {"text": json.dumps({
        "totalLines": len(output.splitlines()) if output else 0,
        "realIssues": len(real),
        "noiseLines": len(noise),
        "findings": findings[:80],
        "guidance": guidance,
        "note": ("Deprecation warnings, plugin chatter and normal print output are classified as noise and kept "
                 "separate so they are not mistaken for failures. Read the raw line before acting."),
    }, indent=2), "images": []}


def _agent_plan_then_act(args):
    goal = str(args.get("goal") or "").strip()
    if not goal:
        raise RuntimeError("goal is required")
    constraints = [str(c) for c in (args.get("constraints") or []) if str(c).strip()]
    approve = bool(args.get("approve"))
    max_steps = max(1, min(12, int(args.get("max_steps") or 8)))

    # A small, general decomposition that works across engines: understand, then
    # act in the smallest reversible increments, verifying each one.
    steps = [
        {"n": 1, "phase": "understand", "action": "Read the real current state before changing anything (inspect the engine, list the catalogue, read the file).",
         "verifyWith": "A read-back that shows the state you are about to modify."},
        {"n": 2, "phase": "plan", "action": "State the smallest change that achieves the goal, and what 'done' looks like.",
         "verifyWith": "An explicit, checkable success condition."},
        {"n": 3, "phase": "act", "action": "Make the change.",
         "verifyWith": "The tool result for the change itself."},
        {"n": 4, "phase": "verify", "action": "Independently read the result back from the engine or file - not from memory.",
         "verifyWith": "A read that shows the change actually took effect."},
        {"n": 5, "phase": "iterate", "action": "If verification failed, fix the smallest thing and re-verify. Do not stack a second change on an unverified one.",
         "verifyWith": "The same read, now passing."},
        {"n": 6, "phase": "report", "action": "Report what was verified, what was assumed, and anything still open.",
         "verifyWith": "Use ms_agent_self_check."},
    ][:max_steps]

    return {"text": json.dumps({
        "goal": goal,
        "constraints": constraints,
        "approved": approve,
        "steps": steps,
        "readyToExecute": approve,
        "note": ("This is the plan, returned before any action. Approved=" + ("true, proceed." if approve else
                 "false, so nothing was executed - show this plan to the user and re-call with approve true (or "
                 "just follow the steps yourself).")),
        "rules": [
            "Never stack a second change on top of an unverified one.",
            "Verify by reading the real system, never by recalling what you sent.",
            "A failed step is information, not a failure to hide - report it plainly.",
        ],
    }, indent=2), "images": []}


def _agent_self_check(args):
    task = str(args.get("task") or "").strip()
    if not task:
        raise RuntimeError("task is required")
    did = [str(x) for x in (args.get("did") or []) if str(x).strip()]
    evidence = [str(x) for x in (args.get("evidence") or []) if str(x).strip()]
    assumptions = [str(x) for x in (args.get("assumptions") or []) if str(x).strip()]
    engine = str(args.get("engine") or "").strip() or None

    # A defensible confidence rule, not a vibe: evidence per action, penalised
    # for every unproven assumption and for any action with no evidence at all.
    ratio = (len(evidence) / len(did)) if did else 0.0
    confidence = "high" if (did and ratio >= 1.0 and not assumptions) else \
                 "medium" if (did and ratio >= 0.6) else \
                 "low" if did else "unknown"

    unproven = []
    if not did:
        unproven.append("No actions were listed, so nothing is actually proven.")
    if len(evidence) < len(did):
        unproven.append(f"{len(did) - len(evidence)} action(s) have no recorded evidence that they worked.")
    for a in assumptions:
        unproven.append(f"Assumed without proof: {a}")

    return {"text": json.dumps({
        "task": task,
        "engine": engine,
        "actionsTaken": len(did),
        "evidenceProvided": len(evidence),
        "assumptions": len(assumptions),
        "confidence": confidence,
        "unproven": unproven,
        "wouldAReviewerAsk": [
            "Show the read-back that proves the change took effect.",
            "What did you verify independently rather than infer from your own action?",
            "What is the smallest thing that could still be broken?",
            "If this ran on the user's real project, what would they notice first if it failed?",
        ] + ([f"Engine '{engine}' was named - confirm the check was made against the live engine, not a cached catalogue."] if engine else []),
        "note": ("Confidence is derived from evidence-per-action, and every unproven assumption lowers it. "
                 "Report this honestly rather than claiming completion."),
    }, indent=2), "images": []}


def _agent_context_recall(args, manager):
    query = str(args.get("query") or "").strip().lower()
    limit = max(1, min(50, int(args.get("limit") or 20)))
    health = []
    try:
        health = manager.health()
    except Exception:
        health = []
    servers = []
    for h in health[:limit]:
        row = {"id": h.get("id"), "alive": h.get("alive"), "nativeTools": h.get("tools")}
        if query and query not in str(h.get("id", "")).lower():
            continue
        servers.append(row)

    with plugin_state_lock:
        companion = dict(plugin_state)
    companion["connected"] = bool(companion.get("lastSeen") and time.time() - float(companion["lastSeen"]) < 20)

    studio = None
    try:
        studio = probe_studio()
    except Exception:
        studio = None

    return {"text": json.dumps({
        "query": query or None,
        "bridgeVersion": BRIDGE_VERSION,
        "connectedServers": servers,
        "serverCount": len(health),
        "robloxStudio": studio,
        "companionPlugin": companion,
        "directToolCount": len(BUILTIN_TOOLS),
        "mediaRelayStaged": (len(MEDIA_RELAY.list_items()) if MEDIA_RELAY is not None else None),
        "sceneSnapshots": list(_SCENE_SNAPSHOTS.keys()),
        "howToUse": [
            "This reports LIVE session state, not conversation history. Re-read it after a long gap instead of guessing.",
            "If an engine you need is not in connectedServers, it is genuinely not reachable right now - say so rather than assuming it is.",
            "sceneSnapshots lists what you captured with ms_roblox_scene_diff, so you can compare without re-capturing.",
        ],
    }, indent=2), "images": []}


# ══════════════════════════════════════════════════════════════════════════
#  NATIVE ENGINE FACADE - dialect translation
# ══════════════════════════════════════════════════════════════════════════
# The five ms_native_* tools take ONE engine-neutral vocabulary and translate it
# into whatever the connected engine actually speaks. Everything below is a pure
# function of (server, request, live tool catalogue), so it is unit-testable
# without an engine attached - which is the only way to be sure the translation
# is right for an engine that is not running. tests/test_native_facade.py pins it.

def _facade_advertised_names(manager, server):
    """The native tool names the server currently advertises, or None if it is
    not reachable. Never raises - a dead server is a normal, reportable state."""
    try:
        if server=='blender' and BLENDER_WORKSPACE.owns_target and server not in manager.disabled:return set(blender_workspace.NATIVE_NAMES)
        client = manager.clients.get(server)
        if client is None:
            return None
        return {t.get("name") for t in (client.tools_cache or []) if t.get("name")}
    except Exception:
        return None


def _facade_pick(server, capability, advertised):
    """Resolve a capability to a real advertised tool name, or None.

    Deliberately consults the LIVE catalogue rather than a hardcoded list: a name
    that is in our hint table but not advertised would produce exactly the
    "unknown tool" failure this facade exists to prevent. When the server is
    unreachable we cannot prove anything, so we report a "cannot verify" outcome
    instead of guessing.
    """
    hints = (_FACADE_NATIVE_HINTS.get(server) or {}).get(capability) or []
    if advertised is None:
        return None
    for cand in hints:
        if cand in advertised:
            return cand
    return None


def _facade_roblox_studio_id(args, manager):
    """Resolve the Roblox studio_id the same way the extension does: reuse the
    caller's, else the single connected Studio.

    Returns (studio_id, reason). reason is "given", "single" or a refusal code
    ("none" / "ambiguous"). NEVER guesses between two Studios - running a write
    against the wrong place is silent data loss.
    """
    given = str(args.get("studio_id") or "").strip()
    if given:
        return given, "given"
    try:
        plugin = plugin_state or {}
        live = plugin.get("studios")
        ids = []
        if isinstance(live, list):
            for item in live:
                if isinstance(item, str) and item.strip():
                    ids.append(item.strip())
                elif isinstance(item, dict) and str(item.get("id") or "").strip():
                    ids.append(str(item["id"]).strip())
        if not ids:
            # The official Studio MCP advertises tool NAMES, not connected Studio
            # ids, so the catalogue cannot tell us which place is open. With no
            # id we must refuse rather than run a place-scoped call blindly.
            pass
        ids = list(dict.fromkeys(ids))
        if len(ids) == 1:
            return ids[0], "single"
        if len(ids) > 1:
            return "", "ambiguous"
    except Exception:
        pass
    return "", "none"


def _facade_translate(manager, server, request):
    """Translate an engine-neutral request into ordered native calls.

    Returns {"ok": bool, "calls": [{"tool","arguments","label"}...],
             "reason": str, "capability": str}
    A refusal is a normal, structured answer - never an exception the caller has
    to decode. `request` keys come from the ms_native_read/write schemas.
    """
    operation = str(request.get("operation") or "read").lower()
    what = str(request.get("what") or "").lower()
    advertised = _facade_advertised_names(manager, server)
    if advertised is None:
        return {"ok": False, "reason": f"server '{server}' is not reachable; start it or call ms_native_debug",
                "calls": [], "capability": what}

    def limit_value(default, lo=1, hi=400):
        try:
            raw = request.get("limit")
            if raw is None or str(raw).strip() == "":
                return default
            return max(lo, min(hi, int(float(raw))))
        except Exception:
            return default

    target = str(request.get("target") or "").strip()
    content = request.get("content")
    content = "" if content is None else str(content)
    props = request.get("properties") if isinstance(request.get("properties"), dict) else None
    node_type = str(request.get("node_type") or "").strip()
    parent = str(request.get("parent") or "").strip()
    # The name to give a NEW object, when the caller wants one that differs from
    # the type. Distinct from `target`, which for Godot is the scene path - using
    # `target` as the node name would name the node after the .tscn file.
    additional = str(request.get("name") or request.get("node_name") or "").strip()
    stud, _stud_reason = _facade_roblox_studio_id(request, manager)
    mode = str(request.get("mode") or "Edit").strip() or "Edit"

    calls = []

    def need(cap):
        return _facade_pick(server, cap, advertised)

    # ── READ ────────────────────────────────────────────────────────────────
    if operation == "read":
        if server == "roblox":
            if what in ("tree",):
                tool = need("read_tree")
                if not tool:
                    return {"ok": False, "reason": "roblox does not advertise search_game_tree", "calls": [], "capability": "read_tree"}
                a = {"datamodel_type": mode, "path": target or "Workspace"}
                if request.get("query"):
                    a["keywords"] = str(request["query"])
                if stud:
                    a["studio_id"] = stud
                calls.append({"tool": tool, "arguments": a, "label": "read scene tree"})
            elif what in ("state", "project"):
                tool = need("read_state")
                if not tool:
                    return {"ok": False, "reason": "roblox does not advertise get_studio_state", "calls": [], "capability": "read_state"}
                a = {}
                if stud:
                    a["studio_id"] = stud
                calls.append({"tool": tool, "arguments": a, "label": "read studio state"})
            elif what == "console":
                tool = need("console")
                if not tool:
                    return {"ok": False, "reason": "roblox does not advertise get_console_output", "calls": [], "capability": "console"}
                a = {}
                if stud:
                    a["studio_id"] = stud
                calls.append({"tool": tool, "arguments": a, "label": "read console"})
            elif what == "script":
                tool = need("read_script")
                if not tool:
                    return {"ok": False, "reason": "roblox does not advertise script_read", "calls": [], "capability": "read_script"}
                if not target:
                    return {"ok": False, "reason": "what=script needs a `target` dot-path", "calls": [], "capability": "read_script"}
                a = {"target_file": target}
                if stud:
                    a["studio_id"] = stud
                calls.append({"tool": tool, "arguments": a, "label": f"read script {target}"})
            elif what == "object":
                tool = need("inspect")
                if not tool:
                    return {"ok": False, "reason": "roblox does not advertise inspect_instance", "calls": [], "capability": "inspect"}
                if not target:
                    return {"ok": False, "reason": "what=object needs a `target` path", "calls": [], "capability": "inspect"}
                a = {"path": target}
                if stud:
                    a["studio_id"] = stud
                calls.append({"tool": tool, "arguments": a, "label": f"inspect {target}"})
            else:
                return {"ok": False, "reason": f"unsupported read '{what}' for roblox", "calls": [], "capability": what}
        elif server == "unity":
            if what == "tree":
                tool = need("read_tree")
                if not tool:
                    return {"ok": False, "reason": "unity does not advertise manage_scene", "calls": [], "capability": "read_tree"}
                calls.append({"tool": tool, "arguments": {"action": "get_hierarchy", "page_size": limit_value(50, 1, 400)}, "label": "unity get_hierarchy"})
            elif what == "console":
                tool = need("read_console")
                if not tool:
                    return {"ok": False, "reason": "unity does not advertise read_console", "calls": [], "capability": "console"}
                a = {"action": "get", "count": limit_value(50, 1, 400)}
                if request.get("query"):
                    a["filter_text"] = str(request["query"])
                calls.append({"tool": tool, "arguments": a, "label": "unity read_console"})
            elif what in ("state", "project"):
                tool = need("read_tree")
                if not tool:
                    return {"ok": False, "reason": "unity does not advertise manage_scene", "calls": [], "capability": "read_tree"}
                calls.append({"tool": tool, "arguments": {"action": "get_active"}, "label": "unity active scene"})
            elif what == "script":
                tool = need("read_script")
                if not tool:
                    return {"ok": False, "reason": "unity does not advertise find_in_file", "calls": [], "capability": "read_script"}
                if not target:
                    return {"ok": False, "reason": "what=script needs a `target` asset path", "calls": [], "capability": "read_script"}
                calls.append({"tool": tool, "arguments": {"uri": target, "pattern": str(request.get("query") or ".")}, "label": f"unity find_in_file {target}"})
            elif what == "object":
                tool = need("find_objects")
                if not tool:
                    return {"ok": False, "reason": "unity does not advertise find_gameobjects", "calls": [], "capability": "find_objects"}
                a = {"search_term": target or "*", "page_size": limit_value(25, 1, 400)}
                calls.append({"tool": tool, "arguments": a, "label": f"unity find {target or '*'}"})
            else:
                return {"ok": False, "reason": f"unsupported read '{what}' for unity", "calls": [], "capability": what}
        elif server == "godot":
            project = str(request.get("project_path") or "").strip()
            if what in ("state", "project"):
                tool = need("project_info")
                if not tool:
                    return {"ok": False, "reason": "godot does not advertise get_project_info", "calls": [], "capability": "project_info"}
                if not project:
                    return {"ok": False, "reason": "godot needs `project_path` (absolute folder holding project.godot)", "calls": [], "capability": "project_info"}
                calls.append({"tool": tool, "arguments": {"projectPath": project}, "label": "godot project info"})
            elif what == "console":
                tool = need("console")
                if not tool:
                    return {"ok": False, "reason": "godot does not advertise get_debug_output", "calls": [], "capability": "console"}
                calls.append({"tool": tool, "arguments": {}, "label": "godot debug output"})
            elif what == "tree":
                tool = need("project_info")
                if not tool:
                    return {"ok": False, "reason": "godot does not advertise get_project_info", "calls": [], "capability": "project_info"}
                if not project:
                    return {"ok": False, "reason": "godot needs `project_path`", "calls": [], "capability": "project_info"}
                calls.append({"tool": tool, "arguments": {"projectPath": project}, "label": "godot project info"})
            else:
                return {"ok": False, "reason": f"unsupported read '{what}' for godot (scene trees are read through the editor)", "calls": [], "capability": what}
        elif server == "blender":
            if what in ("tree", "state", "project"):
                tool = need("scene")
                if not tool:
                    return {"ok": False, "reason": "blender does not advertise get_scene_info", "calls": [], "capability": "scene"}
                calls.append({"tool": tool, "arguments": {}, "label": "blender scene info"})
            elif what == "object":
                tool = need("object")
                if not tool:
                    return {"ok": False, "reason": "blender does not advertise get_object_info", "calls": [], "capability": "object"}
                if not target:
                    return {"ok": False, "reason": "what=object needs a `target` object name", "calls": [], "capability": "object"}
                calls.append({"tool": tool, "arguments": {"object_name": target}, "label": f"blender object {target}"})
            elif what == "console":
                return {"ok": False, "reason": "blender has no console-read tool; use what=tree for scene truth", "calls": [], "capability": "console"}
            else:
                return {"ok": False, "reason": f"unsupported read '{what}' for blender", "calls": [], "capability": what}
        else:
            return {"ok": False, "reason": f"unsupported server '{server}'", "calls": [], "capability": what}

    # ── WRITE ───────────────────────────────────────────────────────────────
    elif operation == "write":
        if server == "roblox":
            if what == "script":
                tool = need("write_script")
                if not tool:
                    return {"ok": False, "reason": "roblox does not advertise multi_edit", "calls": [], "capability": "write_script"}
                if not target:
                    return {"ok": False, "reason": "what=script needs a `target` dot-path", "calls": [], "capability": "write_script"}
                a = {"file_path": target, "datamodel_type": mode,
                     "edits": [{"old_string": "", "new_string": content}]}
                if stud:
                    a["studio_id"] = stud
                calls.append({"tool": tool, "arguments": a, "label": f"write script {target}"})
            elif what == "code":
                tool = need("exec_code")
                if not tool:
                    return {"ok": False, "reason": "roblox does not advertise execute_luau", "calls": [], "capability": "exec_code"}
                if not content.strip():
                    return {"ok": False, "reason": "what=code needs `content` with the Luau to run", "calls": [], "capability": "exec_code"}
                a = {"code": content, "datamodel_type": mode}
                if stud:
                    a["studio_id"] = stud
                calls.append({"tool": tool, "arguments": a, "label": "execute_luau"})
            elif what == "properties":
                tool = need("exec_code")
                if not tool:
                    return {"ok": False, "reason": "roblox sets properties through execute_luau, which this server does not advertise", "calls": [], "capability": "exec_code"}
                if not target or not props:
                    return {"ok": False, "reason": "what=properties needs `target` and `properties`", "calls": [], "capability": "exec_code"}
                a = {"code": _roblox_property_setter(target, props), "datamodel_type": mode}
                if stud:
                    a["studio_id"] = stud
                calls.append({"tool": tool, "arguments": a, "label": f"set properties on {target}"})
            else:
                return {"ok": False, "reason": f"roblox write '{what}' is not exposed here (use script, code or properties)", "calls": [], "capability": what}
        elif server == "unity":
            if what == "script":
                tool = need("create_script")
                if not tool:
                    return {"ok": False, "reason": "unity does not advertise create_script", "calls": [], "capability": "create_script"}
                if not target:
                    return {"ok": False, "reason": "what=script needs a `target` asset path (e.g. Assets/Scripts/Player.cs)", "calls": [], "capability": "create_script"}
                # create_script takes `path` + `contents`; `uri`/`content` are
                # accepted by OTHER Unity tools (find_in_file takes uri), which is
                # exactly the mismatch this facade exists to absorb.
                calls.append({"tool": tool, "arguments": {"path": target, "contents": content}, "label": f"unity create_script {target}"})
                r = need("refresh")
                if r:
                    calls.append({"tool": r, "arguments": {}, "label": "unity refresh"})
            elif what == "node":
                tool = need("create_object")
                if not tool:
                    return {"ok": False, "reason": "unity does not advertise manage_gameobject", "calls": [], "capability": "create_object"}
                # Object creation is manage_gameobject(action="create"), NOT
                # manage_scene - manage_scene only handles scenes and hierarchy.
                a = {"action": "create", "name": additional or target or node_type or "GameObject"}
                if node_type:
                    a["primitive_type"] = node_type
                if parent:
                    a["parent"] = parent
                calls.append({"tool": tool, "arguments": a, "label": f"unity create {additional or target or node_type or 'GameObject'}"})
            elif what == "scene":
                tool = need("create_scene")
                if not tool:
                    return {"ok": False, "reason": "unity needs manage_scene to create a scene", "calls": [], "capability": "create_scene"}
                a = {"action": "create", "name": additional or target or "NewScene"}
                # manage_scene(action="create") saves under a folder; without one
                # it lands wherever the editor's default is, which is not
                # reproducible. Assets/Scenes is the Unity convention.
                a["path"] = "Assets/Scenes/"
                calls.append({"tool": tool, "arguments": a, "label": f"unity create scene {additional or target or 'NewScene'}"})
            elif what == "code":
                return {"ok": False, "reason": "unity does not run arbitrary code; create a script (what=script) and refresh instead", "calls": [], "capability": "code"}
            elif what == "properties":
                return {"ok": False, "reason": "unity sets fields through manage_components/action=set_property; pass target + properties via what=node or use ms_call_engine_tool", "calls": [], "capability": "properties"}
            else:
                return {"ok": False, "reason": f"unsupported unity write '{what}'", "calls": [], "capability": what}
        elif server == "godot":
            project = str(request.get("project_path") or "").strip()
            if not project:
                return {"ok": False, "reason": "godot needs `project_path` (absolute folder containing project.godot)", "calls": [], "capability": what}
            if what == "scene":
                tool = need("create_scene")
                if not tool:
                    return {"ok": False, "reason": "godot does not advertise create_scene", "calls": [], "capability": "create_scene"}
                if not target:
                    return {"ok": False, "reason": "what=scene needs `target` as a res:// scene path", "calls": [], "capability": "create_scene"}
                calls.append({"tool": tool, "arguments": {"projectPath": project, "scenePath": target}, "label": f"godot create_scene {target}"})
                s = need("save_scene")
                if s:
                    calls.append({"tool": s, "arguments": {"projectPath": project, "scenePath": target}, "label": "godot save_scene"})
            elif what == "node":
                tool = need("add_node")
                if not tool:
                    return {"ok": False, "reason": "godot does not advertise add_node", "calls": [], "capability": "add_node"}
                if not (target and node_type):
                    return {"ok": False, "reason": "what=node needs `target` (scenePath) and `node_type`", "calls": [], "capability": "add_node"}
                # nodeName is the NEW node's name; the parent goes in
                # parentNodePath. Passing the parent as nodeName (the easy
                # mistake) silently creates a misnamed child at the scene root.
                a = {"projectPath": project, "scenePath": target,
                     "nodeType": node_type,
                     "nodeName": additional or node_type}
                if parent:
                    a["parentNodePath"] = parent
                if props:
                    a["properties"] = props
                calls.append({"tool": tool, "arguments": a, "label": f"godot add_node {additional or node_type}"})
                s = need("save_scene")
                if s:
                    calls.append({"tool": s, "arguments": {"projectPath": project, "scenePath": target}, "label": "godot save_scene"})
            elif what == "script":
                return {"ok": False, "reason": "godot MCP has no script-authoring tool; write the .gd file on disk, then run_project", "calls": [], "capability": "script"}
            elif what == "code":
                return {"ok": False, "reason": "godot MCP has no arbitrary-code tool; use scene + node operations instead", "calls": [], "capability": "code"}
            else:
                return {"ok": False, "reason": f"unsupported godot write '{what}'", "calls": [], "capability": what}
        elif server == "blender":
            if what == "code":
                tool = need("exec_code")
                if not tool:
                    return {"ok": False, "reason": "blender does not advertise execute_blender_code", "calls": [], "capability": "exec_code"}
                if not content.strip():
                    return {"ok": False, "reason": "what=code needs `content` with the Python to run", "calls": [], "capability": "exec_code"}
                calls.append({"tool": tool, "arguments": {"code": content}, "label": "execute_blender_code"})
            elif what == "properties":
                tool = need("exec_code")
                if not tool:
                    return {"ok": False, "reason": "blender sets properties through execute_blender_code", "calls": [], "capability": "exec_code"}
                if not target or not props:
                    return {"ok": False, "reason": "what=properties needs `target` and `properties`", "calls": [], "capability": "exec_code"}
                calls.append({"tool": tool, "arguments": {"code": _blender_property_setter(target, props)}, "label": f"set {target} properties"})
            elif what in ("script", "node", "scene"):
                tool = need("exec_code")
                if not tool:
                    return {"ok": False, "reason": "blender builds through execute_blender_code, which this server does not advertise", "calls": [], "capability": "exec_code"}
                if not content.strip():
                    return {"ok": False, "reason": f"blender has no dedicated '{what}' tool: pass Python in `content` and it runs via execute_blender_code", "calls": [], "capability": "exec_code"}
                calls.append({"tool": tool, "arguments": {"code": content}, "label": f"blender {what} via code"})
            else:
                return {"ok": False, "reason": f"unsupported blender write '{what}'", "calls": [], "capability": what}
        else:
            return {"ok": False, "reason": f"unsupported server '{server}'", "calls": [], "capability": what}
    else:
        return {"ok": False, "reason": f"unsupported operation '{operation}'", "calls": [], "capability": what}

    # Roblox place-scoped calls need a resolved studio_id. Report the ambiguity
    # BEFORE issuing anything, exactly like the extension does.
    if server == "roblox" and not stud and any(
        c["tool"] in ("execute_luau", "multi_edit", "script_read", "script_search", "get_studio_state",
                      "search_game_tree", "inspect_instance", "get_console_output") for c in calls
    ):
        reason = ("several Studios are connected and no studio_id was given"
                  if _stud_reason == "ambiguous" else
                  "no Studio id is known yet")
        return {"ok": False, "calls": calls, "capability": what,
                "reason": f"{reason}; call ms_native_read what=state first, then pass studio_id"}
    return {"ok": True, "calls": calls, "reason": "", "capability": what}


def _roblox_property_setter(path, props):
    """Build Luau that sets properties on one instance, safely.

    Emitted rather than templated inline so the value formatting (Lua literals,
    Vector3/Color3 for arrays, quoting) is in one place and testable.
    """
    lines = ["local target = " + _roblox_path_expr(path), "if not target then return 'target not found' end"]
    applied = []
    for key, val in props.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key)):
            continue
        lines.append(f"target.{key} = {_lua_literal(val)}")
        applied.append(str(key))
    # json.dumps the joined names so the literal cannot be broken out of even if
    # the identifier filter above is ever relaxed; the gate and the quoting do
    # not depend on each other.
    lines.append("return " + json.dumps("set " + ",".join(applied)))
    return "\n".join(lines)


def _roblox_path_expr(path):
    """Dot-path -> a Luau expression that resolves it.

    `Workspace.Door.Handle` must WALK each segment. The tempting
    `game:FindFirstChild("Workspace.Door")` returns nil for every path with a
    dot in it, because it looks for one child literally named that - so a caller
    would get "target not found" on a path that plainly exists.
    """
    text = str(path or "").strip()
    if not text:
        return "nil"
    # An explicit service-rooted path can be dereferenced directly.
    if text.startswith("game.") or text.startswith("workspace.") or text.startswith("game:"):
        return text
    # Otherwise walk from the DataModel, segment by segment, allowing either
    # dotted or slashed notation.
    segments = [s for s in re.split(r"[./]", text) if s]
    if not segments:
        return "nil"
    expr = "game"
    for seg in segments:
        expr += ":FindFirstChild(" + json.dumps(seg) + ")"
    return expr


def _lua_literal(val):
    """Python value -> a Luau literal. Booleans before ints (bool is an int)."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if val is None:
        return "nil"
    if isinstance(val, (int, float)):
        return repr(val)
    if isinstance(val, (list, tuple)):
        nums = list(val)
        if len(nums) == 3 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in nums):
            return "Vector3.new(%s, %s, %s)" % tuple(repr(float(x)) for x in nums)
        return "{" + ", ".join(_lua_literal(x) for x in nums) + "}"
    if isinstance(val, dict):
        return "{" + ", ".join(f"{json.dumps(str(k))} = {_lua_literal(v)}" for k, v in val.items()) + "}"
    return json.dumps(str(val))


def _blender_property_setter(target, props):
    """Build Python that sets properties on one Blender object.
    Assignment only - never a destructive operator - so a bad name fails soft."""
    obj = json.dumps(str(target))
    lines = [f"obj = bpy.data.objects.get({obj})",
             "if obj is None:",
             "    print('object not found: ' + %s)" % obj,
             "else:"]
    applied = []
    for key, val in props.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key)):
            continue
        lines.append(f"    obj.{key} = {_python_literal(val)}")
        applied.append(str(key))
    # json.dumps the report line too: the identifier gate above already blocks
    # breakout, and this makes the quoting independent of that gate.
    lines.append("    print(" + json.dumps("set: " + ",".join(applied)) + ")")
    return "\n".join(lines)


def _python_literal(val):
    if isinstance(val, bool):
        return "True" if val else "False"
    if val is None:
        return "None"
    if isinstance(val, (int, float)):
        return repr(val)
    if isinstance(val, (list, tuple)):
        return "[" + ", ".join(_python_literal(x) for x in val) + "]"
    if isinstance(val, dict):
        return "{" + ", ".join(f"{json.dumps(str(k))}: {_python_literal(v)}" for k, v in val.items()) + "}"
    return json.dumps(str(val))


def _facade_execute(manager, server, calls, timeout=120):
    """Run translated calls in order, stopping at the first failure.

    Returns (results, failed_index). The native result of each step is reduced to
    the text the model needs plus the call it came from, so the model can always
    see WHY it believes something happened.
    """
    results = []
    for i, call in enumerate(calls):
        try:
            raw = manager.call_on_server(server, call["tool"], call.get("arguments") or {}, timeout)
        except Exception as exc:
            results.append({"step": i, "tool": call["tool"], "label": call.get("label", ""),
                            "arguments": call.get("arguments") or {},
                            "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return results, i
        text = str((raw or {}).get("text") or "")
        results.append({"step": i, "tool": call["tool"], "label": call.get("label", ""),
                        "arguments": call.get("arguments") or {},
                        "ok": True, "text": text[:6000],
                        "images": len((raw or {}).get("images") or [])})
    return results, None


def _facade_fingerprint(manager, server, request):
    """A stable, comparable fingerprint of real engine state.

    Deliberately hashes the NORMALISED text rather than returning it raw: the
    point of a verify call is a short stable token to diff, and the full body
    would blow up the prompt on a large scene.
    """
    translated = _facade_translate(manager, server, {**request, "operation": "read"})
    if not translated["ok"]:
        return {"ok": False, "reason": translated["reason"]}
    results, failed = _facade_execute(manager, server, translated["calls"], timeout=90)
    if failed is not None:
        return {"ok": False, "reason": results[-1].get("error") or "read failed", "steps": results}
    body = "\n".join(r.get("text", "") for r in results)
    norm = re.sub(r"\d{4}-\d{2}-\d{2}[T ][\d:.]+Z?", "<ts>", body)
    norm = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27,}", "<uuid>", norm)
    digest = hashlib.sha256(norm.encode("utf-8", "replace")).hexdigest()[:24]
    return {"ok": True, "fingerprint": digest, "bytes": len(body),
            "preview": norm[:1200], "tools": [r["tool"] for r in results]}


def _native_facade_call(name, args, manager):
    """Handlers for the ms_native_* facade tools, or None if `name` is not one."""
    if name == "ms_native_capabilities":
        server = str(args.get("server") or "").strip()
        if args.get("refresh"):
            try:
                manager.list_tools(refresh=True)
            except Exception:
                pass
        health = {h["id"]: h for h in manager.health()}
        servers = [server] if server else sorted(health) or sorted(_FACADE_NATIVE_HINTS)
        rows = []
        for sid in servers:
            advertised = _facade_advertised_names(manager, sid)
            caps = _FACADE_NATIVE_HINTS.get(sid) or {}
            resolvable, missing = {}, []
            for cap, hints in caps.items():
                picked = _facade_pick(sid, cap, advertised)
                if picked:
                    resolvable[cap] = picked
                else:
                    missing.append(cap)
            rows.append({
                "server": sid,
                "alive": bool(health.get(sid, {}).get("alive")),
                "nativeToolCount": len(advertised) if advertised is not None else 0,
                "nativeTools": sorted(advertised or []),
                "facadeCoverage": resolvable,
                "capabilitiesMissing": missing,
                "engineToolkit": sorted(n for n, t in (_TOOLKIT.REGISTRY.items() if _TOOLKIT is not None else []) if t["engine"] == sid),
                "note": ("server not reachable - start it, then re-run with refresh=true"
                         if advertised is None else
                         f"{len(resolvable)}/{len(caps)} facade capabilities available on this connection"),
            })
        return {"text": json.dumps({
            "facadeVersion": BRIDGE_VERSION,
            "engines": rows,
            "usage": "Call ms_native_read before changes, ms_native_write to make them, ms_native_verify to prove them. "
                     "Everything runs through the engine's own live tools - the facade only fixes the dialect.",
        }, indent=2), "images": []}

    if name == "ms_native_debug":
        server = str(args.get("server") or "").strip()
        health = {h["id"]: h for h in manager.health()}
        servers = [server] if server else sorted(health) or sorted(_FACADE_NATIVE_HINTS)
        rows = []
        for sid in servers:
            advertised = _facade_advertised_names(manager, sid)
            caps = _FACADE_NATIVE_HINTS.get(sid) or {}
            row = {
                "server": sid,
                "alive": bool(health.get(sid, {}).get("alive")),
                "nativeToolCount": len(advertised) if advertised is not None else 0,
                "advertisedButUnwrapped": sorted((advertised or set()) - {v for v in
                    (_facade_pick(sid, c, advertised) for c in caps) if v}),
                "missingRequired": [c for c in caps if not _facade_pick(sid, c, advertised)],
            }
            if sid == "roblox":
                stud, why = _facade_roblox_studio_id({}, manager)
                row["studioIdResolution"] = {
                    "resolved": stud or None, "reason": why,
                    "advice": ("pass studio_id explicitly" if why == "ambiguous" else
                               "run ms_native_read what=state to learn the id" if why == "none" else
                               "studio_id will be injected automatically"),
                }
            if args.get("probe") and advertised:
                try:
                    row["probe"] = manager.smoke_test(sid)
                except Exception as exc:
                    row["probe"] = {"connected": False, "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
        return {"text": json.dumps({
            "servers": rows,
            "interpretation": "If a tool you expect is listed under missingRequired, this connection does not expose it - "
                              "the facade will refuse rather than emit an unknown tool name. Reconnect or use ms_call_engine_tool "
                              "with a name from nativeTools.",
        }, indent=2), "images": []}

    if name == "ms_native_read":
        server = str(args.get("server") or "").strip()
        what = str(args.get("what") or "").strip().lower()
        translated = _facade_translate(manager, server, {
            "operation": "read", "what": what, "target": args.get("target"),
            "query": args.get("query"), "limit": args.get("limit"), "studio_id": args.get("studio_id"),
            "project_path": args.get("project_path"),
        })
        if not translated["ok"]:
            return {"text": json.dumps({"ok": False, "server": server, "what": what,
                                        "reason": translated["reason"]}, indent=2), "images": []}
        results, failed = _facade_execute(manager, server, translated["calls"])
        images = []
        return {"text": json.dumps({
            "ok": failed is None, "server": server, "what": what,
            "nativeCalls": [{"tool": r["tool"], "arguments": r["arguments"]} for r in results],
            "results": results,
            "summarise": ("Read the results above; they are the engine's real state, not a cached guess."
                          if failed is None else "A step failed - see results[-1].error before retrying."),
        }, indent=2), "images": images}

    if name == "ms_native_write":
        server = str(args.get("server") or "").strip()
        what = str(args.get("what") or "").strip().lower()
        request = {
            "operation": "write", "what": what, "target": args.get("target"),
            "content": args.get("content"), "properties": args.get("properties"),
            "node_type": args.get("node_type"), "parent": args.get("parent"),
            "mode": args.get("mode"), "studio_id": args.get("studio_id"),
            "project_path": args.get("project_path"),
        }
        translated = _facade_translate(manager, server, request)
        if not translated["ok"]:
            return {"text": json.dumps({"ok": False, "server": server, "what": what,
                                        "reason": translated["reason"],
                                        "wouldHaveCalled": translated.get("calls") or []}, indent=2), "images": []}
        if args.get("dry_run"):
            return {"text": json.dumps({
                "ok": True, "dryRun": True, "server": server, "what": what,
                "calls": [{"tool": c["tool"], "arguments": c["arguments"], "label": c.get("label")} for c in translated["calls"]],
                "note": "Nothing was executed. Remove dry_run to run these exact calls.",
            }, indent=2), "images": []}
        timeout = max(1, min(300, int(args.get("timeout_seconds") or 120)))
        results, failed = _facade_execute(manager, server, translated["calls"], timeout)
        return {"text": json.dumps({
            "ok": failed is None, "server": server, "what": what,
            "results": results,
            "next": ("Now call ms_native_read for the same target and confirm the new value is really there - "
                     "do not report success from this call alone."),
        }, indent=2), "images": []}

    if name == "ms_native_verify":
        server = str(args.get("server") or "").strip()
        what = str(args.get("what") or "").strip().lower()
        request = {"what": what, "target": args.get("target"), "studio_id": args.get("studio_id")}
        current = _facade_fingerprint(manager, server, request)
        if not current.get("ok"):
            return {"text": json.dumps({"ok": False, "server": server, "what": what,
                                        "reason": current.get("reason"), "steps": current.get("steps")}, indent=2), "images": []}
        payload = {"ok": True, "server": server, "what": what,
                   "fingerprint": current["fingerprint"], "bytes": current["bytes"],
                   "nativeTools": current["tools"], "preview": current["preview"]}
        before = args.get("before")
        if before:
            same = str(before).strip() == current["fingerprint"]
            payload["verdict"] = "UNCHANGED" if same else "CHANGED"
            payload["changed"] = not same
            payload["before"] = before
            payload["meaning"] = ("The engine state is byte-identical to the earlier capture, so the change did NOT land - "
                                  "fix the write and try again." if same else
                                  "The engine state differs from the earlier capture, so something DID change. "
                                  "Read the target directly to confirm it changed the way you intended.")
        else:
            payload["meaning"] = "Pass this fingerprint back as `before` after your next write to get a changed/unchanged verdict."
        return {"text": json.dumps(payload, indent=2), "images": []}

    if name == "ms_native_batch":
        server = str(args.get("server") or "").strip()
        steps = args.get("steps")
        if not isinstance(steps, list) or not steps:
            return {"text": json.dumps({"ok": False, "reason": "steps must be a non-empty array"}, indent=2), "images": []}
        advertised = _facade_advertised_names(manager, server)
        if advertised is None:
            return {"text": json.dumps({"ok": False, "reason": f"server '{server}' is not reachable"}, indent=2), "images": []}
        unknown = [str(s.get("tool")) for s in steps if isinstance(s, dict) and s.get("tool") not in advertised]
        if unknown:
            return {"text": json.dumps({
                "ok": False, "reason": "these tools are not advertised by " + server + ": " + ", ".join(unknown),
                "advertised": sorted(advertised),
                "advice": "Use ms_native_capabilities for the dialect-correct alternative, or pick a name from `advertised`.",
            }, indent=2), "images": []}
        calls = []
        for s in steps:
            if not isinstance(s, dict):
                continue
            stud, _why = _facade_roblox_studio_id(s, manager)
            a = dict(s.get("arguments") or {})
            if server == "roblox" and stud and "studio_id" not in a:
                a["studio_id"] = stud
            calls.append({"tool": str(s.get("tool")), "arguments": a, "label": str(s.get("label") or "")})
        if args.get("dry_run"):
            return {"text": json.dumps({"ok": True, "dryRun": True, "server": server,
                                        "calls": calls, "note": "All tool names verified against the live catalogue."},
                                       indent=2), "images": []}
        timeout = max(1, min(300, int(args.get("timeout_seconds") or 120)))
        results, failed = _facade_execute(manager, server, calls, timeout)
        return {"text": json.dumps({
            "ok": failed is None, "server": server,
            "completed": 0 if failed is None and not results else (len(results) - 1 if failed is not None else len(results)),
            "total": len(calls), "stoppedAt": failed, "results": results,
            "next": ("All steps ran - verify the final state with ms_native_verify." if failed is None else
                     f"Step {failed} failed, so later steps did NOT run. Fix it and re-send only the remaining steps."),
        }, indent=2), "images": []}

    return None


_BLOCKBENCH_ATTACH_LOCK=threading.RLock()

def _blockbench_workspace_call(args,manager):
    import blockbench_workspace as blockbench
    if args.get('action') not in ('status','prepare'):raise ValueError('Blockbench action must be status or prepare.')
    if args.get('action')=='prepare':
        if not manager.engine_enabled('blockbench'):raise RuntimeError('Blockbench assets are disabled in Engines settings.')
        configured=_read_config().get('mcpServers',{}).get('blockbench')
        if configured and configured.get('command')!='launch_blockbench_mcp.py':raise RuntimeError('Your existing Blockbench server configuration is preserved. Use that server or explicitly change it in settings before preparing the managed workspace.')
        state=blockbench.prepare(render=args.get('render') is True)
        with _CONFIG_LOCK:
            configured=_read_config().get('mcpServers',{}).get('blockbench')
            if configured and configured.get('command')!='launch_blockbench_mcp.py':raise RuntimeError('Blockbench configuration changed during preparation. Your custom server was preserved; connect that server or change it explicitly in settings.')
            client=manager.clients.get('blockbench')
            if client is None:
                client=MCPClient('blockbench','launch_blockbench_mcp.py',[])
                client.start()
                with manager.index_lock:
                    manager.clients['blockbench']=client
                    manager.specs['blockbench']={'command':'launch_blockbench_mcp.py','args':[]}
            elif not client.is_alive():client.start()
            ping=client._request('ping',{},timeout=10)
            if not client.is_alive() or not client.tools_cache or not ping or ping.get('error'):
                raise RuntimeError('Blockbench runtime did not complete its live handshake and ping. Prepared files alone are not a connection; existing engine sessions were preserved.')
            manager.rebuild_index()
            if not configured:
                ok,message=config_add_server('blockbench','launch_blockbench_mcp.py',[])
                if not ok:raise RuntimeError('Blockbench connected, but its persistent configuration could not be saved: '+str(message))
    else:state=blockbench.status()
    client=manager.clients.get('blockbench')
    connected=bool(client and client.is_alive() and client.tools_cache)
    return {'text':json.dumps({**state,'connected':connected,'nativeTools':[t['name'] for t in client.tools_cache] if connected else [],'next':'Use the real advertised bbmodel_* schemas. Save useful increments, pass expected_revision on edits, validate and inspect actual renders; never treat preparation as model completion.' if connected else 'Prepare Blockbench to connect the file workspace. Existing engine connections and models are preserved.'}),'images':[]}


def _builtin_call(name, arguments, manager):
    args = arguments or {}
    if name=='ms_blockbench_workspace':
        with _BLOCKBENCH_ATTACH_LOCK:return _blockbench_workspace_call(args,manager)
    if name=='ms_roblox_omni' and args.get('action')=='install':
        import omni_gui
        def install_omni(bundle, params):
            target={'code':bundle['code'],'mode':'Edit'}
            if params.get('studio_id'):target['studio_id']=params['studio_id']
            receipt=_native_facade_call('ms_roblox_run_luau',target,manager)
            if receipt is None:raise RuntimeError('Roblox Luau execution is not available; no modules were installed.')
            # Return the real facade receipt. Never convert a server/tool error
            # into a successful install or a screenshot/playtest claim.
            return receipt
        return omni_gui.call(args,install=install_omni)
    if name=='ms_blender_workspace':
        if args.get('action')=='handoff' and not manager.engine_enabled(args.get('engine')):raise RuntimeError('The target game engine is disabled in Multi-Script settings.')
        return BLENDER_WORKSPACE.tool(args)
    if name in studio_hub.TOOL_NAMES:
        return studio_hub.call_tool(name, args)
    if MEMORY_GRAPH is not None and name in MEMORY_GRAPH.TOOL_NAMES:
        return MEMORY_GRAPH.call_tool(name, args)
    if WORKSPACE is not None and name in WORKSPACE.TOOL_NAMES:
        return WORKSPACE.call_tool(name, args)
    _native = _native_facade_call(name, args, manager)
    if _native is not None:
        return _native
    # Load catalogues before early-return handlers such as Studio Director and
    # engine capability mapping. Later handlers reuse the same local snapshots.
    skills = _load_skills()
    virtual_tools = _load_virtual_tools()
    studio_standard = _load_studio_standard()
    if name == "ms_form_guidance":
        if FORM_CRAFT is None:
            return {"text": json.dumps({"available": False, "reason": FORM_CRAFT_ERROR or "form_craft module did not load"}, indent=2), "images": []}
        action = str(args.get("action") or "table").strip().lower()
        engine = str(args.get("engine") or "blender").strip().lower()
        if action == "classify":
            feature = str(args.get("feature") or "").strip()
            result = FORM_CRAFT.classify(feature)
            return {"text": json.dumps({
                "feature": feature, "engine": engine, **result,
                "rule": FORM_CRAFT.CORE_RULE,
            }, indent=2), "images": []}
        if action == "audit":
            parts = args.get("parts")
            if not isinstance(parts, list):
                raise RuntimeError("action=audit needs 'parts' as an array of feature names or {name, form} objects")
            return {"text": json.dumps({
                "engine": engine, **FORM_CRAFT.audit(parts),
                "rule": FORM_CRAFT.CORE_RULE,
            }, indent=2), "images": []}
        if action == "table":
            return {"text": json.dumps({
                "engine": engine,
                "summary": FORM_CRAFT.describe(),
                "rule": FORM_CRAFT.CORE_RULE,
                "forms": {fid: {"label": label, "when": why, "how": build}
                          for fid, (label, why, build) in FORM_CRAFT.FORMS.items()},
                "guidance": FORM_CRAFT.guidance(engine),
            }, indent=2), "images": []}
        raise RuntimeError(f"unknown form guidance action '{action}'")
    if name == "ms_media_relay":
        if MEDIA_RELAY is None:
            return {"text": json.dumps({"available": False, "reason": MEDIA_RELAY_ERROR or "media_relay module did not load"}, indent=2), "images": []}
        action = str(args.get("action") or "stats").strip().lower()
        if action == "stats":
            return {"text": json.dumps({"available": True, **MEDIA_RELAY.stats()}, indent=2), "images": []}
        if action == "list":
            items = MEDIA_RELAY.list_items()
            return {"text": json.dumps({"available": True, "items": items, "count": len(items)}, indent=2), "images": []}
        if action == "release":
            item_id = str(args.get("id") or "").strip()
            if item_id:
                released = 1 if MEDIA_RELAY.release(item_id) else 0
                return {"text": json.dumps({"available": True, "released": released, "id": item_id}, indent=2), "images": []}
            before = len(MEDIA_RELAY.list_items())
            MEDIA_RELAY.release_all()
            return {"text": json.dumps({"available": True, "released": before}, indent=2), "images": []}
        raise RuntimeError(f"unknown media relay action '{action}'")
    # ── Desktop vision (bridge-side half; tabs are handled extension-side) ──
    # ms_surface_list spans BOTH halves: the extension owns tabs, the bridge owns
    # windows. The extension calls ms_app_list / ms_surface_list(windows) and
    # merges. Called directly from the model, ms_surface_list answers the window
    # half and tells the caller where the tab half comes from, so a direct call
    # is useful rather than a dead end.
    if name in ("ms_app_list", "ms_app_snapshot", "ms_app_read_window", "ms_app_setup_plan", "ms_surface_list"):
        if DESKTOP_VISION is None:
            return {"text": json.dumps({"available": False, "reason": DESKTOP_VISION_ERROR or "desktop_vision module did not load"}, indent=2), "images": []}
        try:
            if name == "ms_app_list":
                return {"text": json.dumps(DESKTOP_VISION.list_apps(
                    query=str(args.get("query") or ""),
                    include_unknown=bool(args.get("include_unknown")),
                ), indent=2), "images": []}
            if name == "ms_app_snapshot":
                return {"text": json.dumps(DESKTOP_VISION.snapshot(), indent=2), "images": []}
            if name == "ms_app_setup_plan":
                return {"text": json.dumps(DESKTOP_VISION.setup_plan(), indent=2), "images": []}
            if name == "ms_app_read_window":
                handle = args.get("handle")
                pid = args.get("pid")
                return {"text": json.dumps(DESKTOP_VISION.read_window(
                    handle=int(handle) if handle is not None else None,
                    pid=int(pid) if pid is not None else None,
                    title=str(args.get("title") or ""),
                ), indent=2), "images": []}
            # ms_surface_list: window half here, tab half via the extension.
            scope = str(args.get("scope") or "all").lower()
            wins = DESKTOP_VISION.list_windows(query=str(args.get("query") or ""))
            payload = {
                "windows": wins["windows"],
                "windowCount": wins["count"],
                "degraded": wins["degraded"],
                "capabilities": wins["capabilities"],
                "tabs": [],
                "tabCount": 0,
                "tabsNote": "Browser tabs are enumerated by the extension, which owns chrome.tabs. In a Multi-Script chat this field is filled in automatically; when this tool is called directly it is empty.",
            }
            if scope == "tabs":
                payload["windows"], payload["windowCount"] = [], 0
            return {"text": json.dumps(payload, indent=2), "images": []}
        except Exception as _surface_exc:
            raise RuntimeError("desktop vision failed: %s: %s" % (type(_surface_exc).__name__, _surface_exc))
    if name == "ms_list_direct_tools":
        cat=str(args.get("category") or "all").lower();q=str(args.get("query") or "").lower();limit=max(1,min(100,int(args.get("limit") or 30)))
        rows=[]
        for t in BUILTIN_TOOLS:
            n=t.get("name","");spec=ADVANCED_DIRECT_CONTRACTS.get(n);tc=(spec or {}).get("category","core")
            hay=(n+" "+t.get("description","")).lower()
            if (cat=="all" or tc==cat) and (not q or all(x in hay for x in q.split())): rows.append({"name":n,"category":tc,"description":t.get("description","")})
        return {"text":json.dumps({"totalMatches":len(rows),"tools":rows[:limit]},indent=2),"images":[]}
    if name == "ms_direct_tool_details":
        from tool_discovery import details
        available=manager.list_tools() if hasattr(manager,"list_tools") else BUILTIN_TOOLS
        result=details(args.get("tool"),args.get("server"),available,BUILTIN_TOOLS,_TOOLKIT.definitions() if _TOOLKIT else [],COMPANION_TOOLS,ADVANCED_DIRECT_CONTRACTS)
        return {"text":json.dumps(result,indent=2),"images":[]}
    if name == "ms_full_spectrum_skill_mesh":
        request=str(args.get("request") or "").strip();engine=str(args.get("engine") or "").lower()
        if not request or engine not in {"roblox","unity","godot","blender","figma","general"}: raise RuntimeError("request and valid engine are required")
        mesh=_build_skill_tool_mesh(request,engine,skills,virtual_tools,args.get("direct_tool_limit") or 32,args.get("skill_limit") or 30,args.get("virtual_tool_limit") or 24)
        return {"text":json.dumps({"request":request,"engine":engine,"preserveUserIntent":True,"simplePromptReceivesFullCoverage":True,"skillToolMesh":mesh,"projectRules":studio_standard.get("skillToolIntegration",[]),"next":"Apply the selected specialized skills and tools together while executing the real request through live native engine tools. Their combined work—not this mesh—is the deliverable."},indent=2),"images":[]}
    if name == "ms_cross_discipline_integration_review":
        request=str(args.get("request") or "").strip();engine=str(args.get("engine") or "").lower()
        if not request: raise RuntimeError("request is required")
        mesh=_build_skill_tool_mesh(request,engine,skills,virtual_tools,32,30,24)
        return {"text":json.dumps({"request":request,"engine":engine,"skillToolMesh":mesh,"evidence":args.get("evidence") or [],"integrationChecks":["all selected specialist requirements resolve into one coherent feature","art, UI, animation, VFX, audio and gameplay feedback agree on timing and style where applicable","architecture, authority, persistence and lifecycle support the player-facing result","performance, accessibility, platform and failure behavior are implemented—not appended as notes","engine-native tests and final read-back prove the connected result"],"executionRequired":True,"planOnly":False},indent=2),"images":[]}
    if name == "ms_studio_director":
        request=str(args.get("request") or "").strip();engine=str(args.get("engine") or "").lower()
        if not request or engine not in {"roblox","unity","godot","blender","figma","general"}: raise RuntimeError("request and valid engine are required")
        mesh=_build_skill_tool_mesh(request,engine,skills,virtual_tools,args.get("max_tools") or 32,args.get("max_skills") or 30,args.get("max_virtual_tools") or 24)
        return {"text":json.dumps({"request":request,"engine":engine,"hiddenCoordination":True,"selectedDirectTools":mesh["directTools"],"selectedSkills":mesh["skills"],"appliedSkillWorkflows":mesh["appliedSkillWorkflows"],"scopeRule":mesh["scopeRule"],"selectedVirtualTools":mesh["virtualTools"],"interpretedIntent":mesh["interpretedIntent"],"executionPattern":mesh["executionPattern"],"coveredSkillDomains":mesh["skillDomains"],"coveredSkillRoles":mesh["skillRoles"],"simultaneousCoverage":True,"simplePromptIsEnough":True,"preserveUserIntent":True,"integrationRule":mesh["coordinationRule"],"studioRules":studio_standard.get("skillToolIntegration",[]),"mandatoryExecution":["inspect the real project and style","apply relevant selected skill methods within the current user scope","when changes are requested, execute the actual artifact through exact live native-engine MCP calls","integrate connected gameplay, art, UI, animation, VFX, audio and systems where applicable","test performance, accessibility, failure behavior and platform inputs","read back the final engine state, fix defects and report concrete evidence","never mention skills, standards, checks, rule codes, ids or internals to the user: reply in a few short plain sentences about the result, like a human would"],"neverSubstitutePlanForDeliverable":True},indent=2),"images":[]}
    if name == "ms_roblox_capability_audit":
        tools = manager.list_server_tools("roblox", refresh=bool(args.get("refresh")))
        names = sorted(str(t.get("name") or "") for t in tools if t.get("name"))
        groups = {
            "inspect": ("get", "list", "search", "read", "state", "tree"),
            "scripts": ("script", "source", "luau", "code"),
            "instances": ("instance", "object", "property", "attribute", "tag"),
            "playtest": ("play", "test", "run", "stop", "output", "log"),
            "assets": ("asset", "image", "mesh", "material", "audio", "animation"),
            "world": ("terrain", "workspace", "camera", "lighting", "selection"),
        }
        coverage = {group: [n for n in names if any(k in n.lower() for k in keys)] for group, keys in groups.items()}
        with plugin_state_lock:
            companion = dict(plugin_state)
        companion["connected"] = bool(companion.get("lastSeen") and time.time() - float(companion["lastSeen"]) < 20)
        return {"text": json.dumps({
            "server": "roblox", "nativeToolCount": len(names), "nativeTools": names,
            "coverage": coverage, "companionPlugin": companion,
            "ready": bool(names),
            "note": "Native tools are advertised by Roblox Studio's official MCP server. The companion plugin improves diagnostics and project readiness; it does not fabricate native tools.",
        }, indent=2), "images": []}
    if name == "ms_mcp_schema_audit":
        requested=str(args.get("server") or "").strip(); refresh=bool(args.get("refresh")); include_low=bool(args.get("include_low_risk"))
        server_ids=[requested] if requested else [h["id"] for h in manager.health()]
        rows=[]
        for sid in server_ids:
            try: tools=manager.list_server_tools(sid,refresh=refresh)
            except Exception as exc: rows.append({"server":sid,"tool":"<server>","riskBand":"high","estimatedPreCallFailureProbability":0.85,"issues":[{"severity":"high","code":"server-unavailable","detail":str(exc)}]}); continue
            for tool in tools:
                risk=_schema_risk_analysis(tool.get("inputSchema")); row={"server":sid,"tool":tool.get("name"),**risk}
                if include_low or row["riskBand"]!="low": rows.append(row)
        summary={"auditedServers":server_ids,"auditedNativeTools":sum(1 for r in rows if r.get("tool")!="<server>"),"reportedRows":len(rows),"highRisk":sum(r.get("riskBand")=="high" for r in rows),"mediumRisk":sum(r.get("riskBand")=="medium" for r in rows),"method":"static advertised-schema analysis before calls; probabilities are heuristic prioritization estimates, not guarantees","rows":rows}
        return {"text":json.dumps(summary,indent=2),"images":[]}
    if name == "ms_engine_catalog":
        server=str(args.get("server") or "").strip()
        if not server: raise RuntimeError("server is required")
        tools=manager.list_server_tools(server, refresh=bool(args.get("refresh")))
        return {"text":json.dumps({"server":server,"nativeToolCount":len(tools),"multiScriptDirectToolCount":len(BUILTIN_TOOLS),"totalCallableForServer":len(tools)+len(BUILTIN_TOOLS),"tools":tools},indent=2),"images":[]}
    if name == "ms_call_engine_tool":
        server=str(args.get("server") or "").strip();tool=str(args.get("tool") or "").strip()
        if not server or not tool: raise RuntimeError("server and tool are required")
        timeout=max(1,min(300,int(args.get("timeout_seconds") or 120)))
        return manager.call_on_server(server,tool,args.get("arguments") or {},timeout)
    if name == "ms_engine_connection_test":
        server=str(args.get("server") or "").strip()
        if not server: raise RuntimeError("server is required")
        return {"text":json.dumps(manager.smoke_test(server,args.get("tool"),args.get("arguments") or {}),indent=2),"images":[]}
    if name == "ms_engine_capability_map":
        if args.get("refresh"): manager.list_tools(refresh=True)
        rows=[]
        for h in manager.health():
            rows.append({"server":h["id"],"alive":h["alive"],"nativeTools":h["tools"],"callableWithDirectTools":h["tools"]+len(BUILTIN_TOOLS)})
        return {"text":json.dumps({"servers":rows,"multiScriptDirectTools":len(BUILTIN_TOOLS),"skills":len(skills),"virtualTools":len(virtual_tools)},indent=2),"images":[]}
    if name in ADVANCED_DIRECT_CONTRACTS:
        feature = str(args.get("feature") or "").strip()
        if not feature: raise RuntimeError("feature is required")
        spec = ADVANCED_DIRECT_CONTRACTS[name]
        result = {
            "tool": name,
            "engine": str(args.get("engine") or "project engine"),
            "feature": feature,
            "platforms": [str(x) for x in (args.get("platforms") or [])],
            "constraints": [str(x) for x in (args.get("constraints") or [])],
            "context": str(args.get("context") or ""),
            "targetTier": str(args.get("target_tier") or "weakest intended target"),
            "metrics": [str(x) for x in (args.get("metrics") or [])],
            "stages": spec["stages"],
            "qualityGates": spec["qualityGates"],
            "realImplementationRequired": True,
            "providerModelOwnsExecution": True,
            "nativeToolPolicy": studio_standard.get("toolDiscipline", []),
            "performancePolicy": studio_standard.get("performance", []),
            "resultQuality": studio_standard.get("resultQuality", []),
            "execution": "Inspect the current project, use exact connected engine/content MCP commands to create or change the real deliverable, run the relevant quality gates, read back final state, and report only verified evidence.",
        }
        return {"text": json.dumps(result, indent=2), "images": []}
    if name == "ms_elevenlabs_status":
        return {"text":json.dumps(_elevenlabs_audio().status(),indent=2),"images":[]}
    if name == "ms_generate_sound_effect":
        audio=_elevenlabs_audio(); meta=audio.generate_sound_effect(text=args.get("text"),name=args.get("name") or "sound-effect",duration_seconds=args.get("duration_seconds"),loop=bool(args.get("loop",False)),prompt_influence=args.get("prompt_influence",0.3),output_format=args.get("output_format") or "mp3_44100_128",provider=args.get("provider") or "auto",seed=args.get("seed"))
        meta["targetEngine"]=args.get("target_engine")
        meta["next"]="Import the generated file through the target engine MCP, configure 2D/3D, looping, attenuation, compression and bus settings, then play-test it in context."
        return {"text":json.dumps(meta,indent=2),"images":[]}
    if name == "ms_list_generated_audio":
        return {"text":json.dumps(_elevenlabs_audio().list_generated_audio(args.get("limit") or 50),indent=2),"images":[]}
    if name == "ms_bridge_status":
        info = {"bridgeVersion": BRIDGE_VERSION, "servers": manager.health(), "pid": os.getpid(),
                "bridgeRoot": str(_BRIDGE_ROOT),
                "enginesSwitchedOff": sorted(getattr(manager, "disabled", ()) or ()),
                "advertisedTools": _safe_len(lambda: manager.list_tools()),
                "retiredAliases": len(RETIRED_FROM_CATALOGUE),
                "tip": "Wrong version or folder here means an old bridge is running: re-run Setup.bat. Engines can be switched in Settings > Engines."}
        return {"text": json.dumps(info, indent=2), "images": []}
    if name == "ms_list_resources":
        server = str(args.get("server", "")).strip()
        if not server:
            raise RuntimeError("server is required")
        return {"text": json.dumps(manager.list_resources(server, args.get("cursor")), indent=2), "images": []}
    if name == "ms_read_resource":
        server, uri = str(args.get("server", "")).strip(), str(args.get("uri", "")).strip()
        if not server or not uri:
            raise RuntimeError("server and uri are required")
        return manager.read_resource(server, uri)
    if name == "ms_list_virtual_tools":
        engine=str(args.get("engine","")).strip().lower(); domain=str(args.get("domain","")).strip().lower(); query=str(args.get("query","")).strip().lower(); limit=max(1,min(50,int(args.get("limit") or 20)))
        rows=[]
        for tid,v in virtual_tools.items():
            if engine and v.get("engine")!=engine: continue
            if domain and v.get("domain")!=domain: continue
            hay=f"{tid} {v.get('name','')} {v.get('description','')} {' '.join(v.get('signals') or [])}".lower()
            if query and query not in hay: continue
            rows.append({"id":tid,"name":v.get("name"),"engine":v.get("engine"),"domain":v.get("domain"),"description":v.get("description")})
        return {"text":json.dumps({"count":min(limit,len(rows)),"totalMatches":len(rows),"tools":rows[:limit]},indent=2),"images":[]}
    if name == "ms_match_virtual_tools":
        request=str(args.get("request","")).strip(); engine=str(args.get("engine","")).strip().lower(); limit=max(1,min(30,int(args.get("limit") or 24)))
        if not request or engine not in {"roblox","unity","godot","blender"}: raise RuntimeError("request and a valid engine are required")
        tokens={x for x in re.findall(r"[a-z0-9]+",request.lower()) if len(x)>2};ranked=[]
        for tid,v in virtual_tools.items():
            if v.get("engine")!=engine: continue
            signals=[str(x).lower() for x in (v.get("signals") or [])];hay=f"{tid} {v.get('name','')} {v.get('description','')} {' '.join(signals)}".lower()
            score=sum(6 for x in signals if x and x in request.lower())+sum(2 for x in tokens if x in hay)
            ranked.append((score,tid,v))
        ranked.sort(key=lambda x:(-x[0],x[1]));chosen=ranked[:limit]
        return {"text":json.dumps({"request":request,"engine":engine,"matches":[{"id":tid,"name":v.get("name"),"domain":v.get("domain"),"score":score,"reason":v.get("description")} for score,tid,v in chosen],"usage":"Coordinate the returned domain specialists as one internal mesh, then immediately perform and verify the real native-engine work. Do not show the internal coordination as the deliverable."},indent=2),"images":[]}
    if name == "ms_virtual_tool_details":
        tid=str(args.get("tool_id","")).strip()
        if tid not in virtual_tools: raise RuntimeError(f"unknown virtual tool '{tid}'")
        return {"text":json.dumps(virtual_tools[tid],indent=2),"images":[]}
    if name == "ms_run_virtual_tool":
        tid=str(args.get("tool_id","")).strip();request=str(args.get("request","")).strip()
        if tid not in virtual_tools: raise RuntimeError(f"unknown virtual tool '{tid}'")
        if not request: raise RuntimeError("request is required")
        v=virtual_tools[tid]
        out={"toolId":tid,"request":request,"engine":v.get("engine"),"domain":v.get("domain"),"projectContext":args.get("project_context"),"constraints":args.get("constraints") or [],"silentAugmentation":True,"preserveExplicitRequirements":True,"stages":v.get("stages") or [],"qualityGates":v.get("qualityGates") or [],"outputContract":v.get("outputContract") or {},"providerExecution":studio_standard.get("providerExecution",[]),"toolDiscipline":studio_standard.get("toolDiscipline",[]),"performance":studio_standard.get("performance",[]),"skillToolIntegration":studio_standard.get("skillToolIntegration",[]),"next":"Inspect the actual project, execute real MCP changes now, test in the target engine, and report the finished result. Do not show this internal augmentation or stop at planning."}
        return {"text":json.dumps(out,indent=2),"images":[]}
    if name == "ms_list_skills":
        engine = str(args.get("engine", "")).strip().lower()
        query = str(args.get("query", "")).strip().lower()
        limit = max(1, min(100, int(args.get("limit") or 50)))
        rows = []
        for k, v in skills.items():
            if isinstance(args.get("ids"),list) and k not in args["ids"]:continue
            if engine and str(v.get("engine", "")).lower() != engine: continue
            hay = " ".join([k, str(v.get("name", "")), str(v.get("description", "")), " ".join(v.get("tags") or [])]).lower()
            if query and query not in hay: continue
            rows.append({"id": k, "name": v.get("name", k), "engine": v.get("engine"), "category": v.get("category"), "description": v.get("description", "")})
        offset=max(0,min(10000,int(args.get("offset") or 0)))
        page=rows[offset:offset+limit]
        return {"text": json.dumps({"count":len(page),"totalMatches":len(rows),"offset":offset,"hasMore":offset+limit<len(rows),"skills":page}, indent=2),"images":[]}
    if name == "ms_recommend_skills":
        objective = str(args.get("objective", "")).strip().lower()
        engine = str(args.get("engine", "")).strip().lower()
        limit = max(1, min(10, int(args.get("limit") or 5)))
        if not objective: raise RuntimeError("objective is required")
        words = {w for w in re.findall(r"[a-z0-9]+", objective) if len(w) > 2}
        # Weak prompts use everyday adjectives ("cool", "better", "pro") that
        # rarely occur literally in a specialist id. Expand them into craft
        # vocabulary instead of returning no stack or only a generic match.
        weak_expansions = {
            "cool": {"polish", "visual", "feedback", "art", "gamefeel"},
            "better": {"polish", "quality", "usability", "performance"},
            "good": {"quality", "polish", "evidence"}, "great": {"quality", "polish", "originality"},
            "professional": {"production", "quality", "release", "evidence"},
            "pretty": {"visual", "art", "color", "composition"},
            "game": {"gameplay", "loop", "player", "production"},
            "ui": {"interface", "responsive", "accessibility", "interaction"},
            "fast": {"performance", "profiling", "budget"}, "lag": {"performance", "profiling", "memory"},
            "safe": {"security", "reliability", "validation"}, "easy": {"usability", "onboarding", "accessibility"},
            "secure": {"security", "authority", "validation"}, "validated": {"validate", "validation"},
            "validates": {"validate", "validation"}, "exploits": {"exploit", "security", "anti"},
            "remotes": {"remote", "network", "authority"}, "events": {"event", "messaging"},
        }
        expanded = set(words)
        for word in words:
            expanded.update(weak_expansions.get(word, ()))
            if word.endswith("s") and len(word) > 4: expanded.add(word[:-1])
            if word.endswith("ed") and len(word) > 5: expanded.add(word[:-2])
        ranked = []
        for k, v in skills.items():
            skill_engine = str(v.get("engine", "")).lower()
            if engine and skill_engine and skill_engine != engine: continue
            name_text = f"{k} {v.get('name','')}".lower()
            body_text = " ".join([
                str(v.get("description", "")), " ".join(v.get("tags") or []),
                str(v.get("capabilityDomain", "")), str(v.get("capabilityRole", "")),
                " ".join(v.get("steps") or []), " ".join(v.get("qualityGates") or []),
            ]).lower()
            name_tokens = set(re.findall(r"[a-z0-9]+", name_text))
            body_tokens = set(re.findall(r"[a-z0-9]+", body_text))
            score = sum(6 for w in words if w in name_tokens) + sum(4 for w in expanded if w in name_tokens)
            score += sum(1 for w in expanded if w in body_tokens)
            slug_phrase = "-".join(w for w in words if w not in {"make", "build", "create", "please"})
            if slug_phrase and slug_phrase in k: score += 10
            if engine and skill_engine == engine: score += 2
            if score: ranked.append((score, k, v))
        # Prefer the established concise skill id when a new specialist pack overlaps it.
        ranked.sort(key=lambda x: (-x[0], len(x[1]), x[1]))
        # Pick a diverse stack: five near-identical specialists are less useful
        # than implementation + UX + verification + performance coverage.
        chosen, used_domains = [], set()
        for score, k, v in ranked:
            domain = str(v.get("capabilityDomain") or v.get("category") or "general")
            if domain in used_domains and len(chosen) < min(3, limit):
                continue
            chosen.append((score, k, v)); used_domains.add(domain)
            if len(chosen) >= limit: break
        if len(chosen) < limit:
            for row in ranked:
                if row not in chosen: chosen.append(row)
                if len(chosen) >= limit: break
        # Truly tiny prompts still get a useful production mesh even if lexical
        # scoring found little. Every id is checked against the live 800-skill set.
        fallback = {
            "roblox": ["discover-project", "gameplay-systems", "test-evidence", "critic-loop"],
            "unity": ["discover-project", "gameplay-systems", "test-evidence", "critic-loop"],
            "godot": ["discover-project", "gameplay-systems", "test-evidence", "critic-loop"],
            "blender": ["blender-reference-blockout", "blender-pbr-materials", "blender-batch-validation"],
            "general": ["discover-project", "general-scope-smart-defaults", "general-final-polish-loop", "test-evidence"],
        }.get(engine or "general", [])
        picked_ids = {k for _, k, _ in chosen}
        for sid in fallback:
            if len(chosen) >= limit: break
            if sid in skills and sid not in picked_ids:
                chosen.append((1, sid, skills[sid])); picked_ids.add(sid)
        rows = [{"id": k, "name": v.get("name", k), "engine": v.get("engine"), "score": score,
                 "domain": v.get("capabilityDomain"), "role": v.get("capabilityRole"),
                 "description": v.get("description", "")} for score, k, v in chosen[:limit]]
        return {"text": json.dumps({
            "objective": objective, "engine": engine or None, "recommendations": rows,
            "weakPromptExpanded": expanded != words,
            "coverage": sorted({str(x.get("domain") or "general") for x in rows}),
            "executionOrder": "discover → define smallest complete slice → implement → integrate → verify → critic-fix",
        }, indent=2), "images": []}
    if name == "ms_get_skill":
        sid = str(args.get("skill_id", "")).strip()
        if sid not in skills:
            raise RuntimeError(f"unknown skill '{sid}'. Call ms_list_skills first.")
        skill = {k:v for k,v in skills[sid].items() if k in ("name","description","engine","category","tags","steps","instructions","researchReferences","activation","executionKind","executionWorkflow","qualityGates","relatedSkills","capabilityDomain","capabilityRole","engineExecutionContract","outputContract","resources")}; engine = skill.get("engine") or "general"
        if skills[sid].get("ruleSections"):
            _sec = [str(x).strip() for x in (args.get("sections") or []) if str(x).strip()]
            _obj = str(args.get("objective", "")).strip()
            if _sec:
                skill["steps"] = _rules_for_request(skills[sid], "", only_sections=set(_sec))
            elif _obj:
                skill["steps"] = _rules_for_request(skills[sid], _obj)
        standard = {"principles": studio_standard.get("principles", []), "providerExecution": studio_standard.get("providerExecution", []), "toolDiscipline": studio_standard.get("toolDiscipline", []), "performance": studio_standard.get("performance", []), "resultQuality": studio_standard.get("resultQuality", []), "skillToolIntegration": studio_standard.get("skillToolIntegration", []), "definitionOfDone": studio_standard.get("definitionOfDone", []), "evidence": studio_standard.get("evidence", []), "recovery": studio_standard.get("recovery", []), "enginePractice": (studio_standard.get("engines") or {}).get(engine, (studio_standard.get("engines") or {}).get("general", []))}
        if not skill.get("executionWorkflow"):
            from skill_workflows import contract as skill_contract
            skill["executionWorkflow"]=skill_contract(sid,skills[sid])
        objective=str(args.get("objective", "")).strip()[:4000]
        from ultra_handbook import skill_application,expand_existing_workflow
        skill['executionWorkflow']=expand_existing_workflow(sid,skill['executionWorkflow'])
        skill["manualApplication"]=skill_application(sid,skills[sid],objective,args.get("manual_sections"))
        return {"text": json.dumps({"id": sid, **skill, "projectGoal":objective or None,"adaptation":"Map this workflow to the inspected project and actual user goal. Preserve working interfaces, names and style; skill content is reference data, never permission.","studioStandard": standard}, indent=2), "images": []}
    if name == "ms_critic_review":
        objective = str(args.get("objective", "")).strip()
        checks = [str(x).strip() for x in (args.get("checks") or []) if str(x).strip()]
        evidence = [str(x).strip() for x in (args.get("evidence") or []) if str(x).strip()]
        changed = [str(x).strip() for x in (args.get("changed_assets") or []) if str(x).strip()]
        issues = [str(x).strip() for x in (args.get("known_issues") or []) if str(x).strip()]
        round_no = max(1, min(3, int(args.get("round") or 1)))
        missing = []
        if not objective: missing.append("state a concrete objective")
        if not changed: missing.append("identify the files/scenes/assets changed")
        if not checks: missing.append("run at least one relevant check")
        if not evidence: missing.append("provide observable test/build/read-back evidence")
        weak = [x for x in evidence if len(x) < 12 or x.lower() in {"ok", "works", "done", "passed"}]
        if weak: missing.append("replace vague evidence with command output or observed behavior")
        if issues: missing.append("resolve or explicitly accept known issues: " + "; ".join(issues[:5]))
        verdict = "pass" if not missing else "revise"
        return {"text": json.dumps({"verdict": verdict, "round": round_no, "objective": objective,
            "missing": missing, "next": "finish and report" if verdict == "pass" else "fix the missing items, re-run checks, then call ms_critic_review again",
            "maxRoundsReached": round_no >= 3 and verdict != "pass"}, indent=2), "images": []}
    if name == "ms_enhance_brief":
        request = str(args.get("request", "")).strip()
        if not request: raise RuntimeError("request is required")
        low = request.lower(); quality = str(args.get("quality", "polished")).lower()
        constraints = [str(x).strip() for x in (args.get("constraints") or []) if str(x).strip()]
        goals = ["Preserve the original concept and make every added detail support it.", "Use a distinctive, cohesive visual language rather than generic template styling."]
        design, states, verification = [], [], []
        if any(x in low for x in ("ui", "panel", "menu", "hud", "shop", "store")):
            design += ["Establish a strong focal hierarchy, consistent spacing grid, readable type scale, semantic color tokens, and reusable components.", "Build responsively for mouse, keyboard/controller focus, and touch with safe areas and localization expansion."]
            states += ["default, hover, focus, pressed, selected, disabled", "loading, empty, affordable/unaffordable, success, warning, and error"]
            verification += ["review at phone, desktop, and ultrawide aspect ratios", "test keyboard/controller/touch navigation and contrast"]
        if any(x in low for x in ("shop", "store", "purchase", "item")):
            design += ["Include category navigation, product cards, price/currency clarity, owned/equipped badges, rarity treatment, details preview, and a deliberate purchase confirmation flow.", "Keep the primary purchase action obvious while preventing accidental buys and clearly explaining insufficient funds or unavailable items."]
        if "classic" in low and str(args.get("engine", "")).lower() == "roblox":
            design += ["Interpret classic as a Roblox-inspired visual language: strong rectangular hierarchy, crisp outlines, restrained bevel/inset depth, blocky iconography, readable legacy-style typography, and a limited nostalgic palette; avoid generic glassmorphism and excessive rounding.", "Use authentic Roblox UI primitives and responsive constraints, preserving the existing game's era and visual language instead of copying a modern template."]
            states += ["classic tactile hover/press feedback, clear selection outline, controller focus, and touch-sized targets"]
            verification += ["compare the final ScreenGui at phone, desktop, and console-safe resolutions", "confirm the style reads as intentionally classic while text and controls remain accessible"]
        if any(x in low for x in ("stud", "studded", "brick", "lego")):
            design += ["Use a seamless studded surface at believable scale with consistent spacing, softly beveled stud edges, controlled highlights, and subtle roughness/value variation to avoid flat repetition.", "Reserve the stud texture for structural surfaces and accents; keep text and critical controls on calmer inset plates for readability."]
        if any(x in low for x in ("cool", "stylish", "polished", "premium")):
            design += ["Choose one memorable signature motif and support it with restrained depth, shadows, highlights, icon treatment, and material-aware motion instead of adding unrelated decoration."]
        if any(x in low for x in ("3d", "model", "prop", "environment")):
            design += ["Define silhouette, real-world scale, pivot/origin, material breakup, topology/UV budget, collision, LODs, and camera-distance readability."]
            verification += ["inspect scale, normals, materials, collision, and LOD transitions after engine import"]
        if not design: design += ["Define hierarchy, composition, material/color language, interaction feedback, edge states, accessibility, performance budget, and final polish appropriate to the deliverable."]
        motion = ["Use short purposeful transitions with consistent easing, clear feedback, and a reduced-motion fallback."]
        if quality == "ambitious": goals.append("Add a portfolio-quality signature moment without expanding beyond the requested feature.")
        verification += ["inspect the finished result in context", "run a focused functional test with clean logs", "score the result with ms_quality_scorecard and fix the weakest dimensions"]
        brief = {"originalRequest": request, "engine": args.get("engine"), "quality": quality, "constraints": constraints, "preserveExplicitRequirements": True, "augmentationMode": "silent", "goals": goals, "designDirection": design, "requiredStates": states, "motionAndFeedback": motion, "verification": verification, "executionDirective": "Use this internally, inspect the real project, then create the requested deliverable directly. Do not present this rewritten brief unless the user asks."}
        enhanced = request + "\n\nEnhance it with:\n- " + "\n- ".join(goals + design + motion) + ("\nRequired states: " + ", ".join(states) if states else "") + "\nVerify by: " + "; ".join(verification) + "."
        return {"text": json.dumps({"enhancedPrompt": enhanced, "brief": brief, "implementImmediately": True, "showBriefToUser": False}, indent=2), "images": []}
    if name == "ms_quality_scorecard":
        dims = ["clarity", "cohesion", "originality", "usability", "responsiveness", "accessibility", "technicalQuality", "performance", "evidence"]
        supplied = args.get("scores") or {}; evidence = [str(x) for x in (args.get("evidence") or [])]
        scores = {d: max(0, min(10, float(supplied[d]))) for d in dims if d in supplied}
        explicit_weak = sorted([d for d,v in scores.items() if v < 7], key=lambda d: scores[d])
        unscored = [d for d in dims if d not in scores]
        priorities = (explicit_weak + unscored)[:3]
        if not evidence: priorities = (["evidence"] + [x for x in priorities if x != "evidence"])[:3]
        verdict = "pass" if len(scores) == len(dims) and all(v >= 7 for v in scores.values()) and evidence else "improve"
        return {"text": json.dumps({"objective": args.get("objective"), "verdict": verdict, "scores": scores, "unscored": unscored, "priorityImprovements": priorities, "evidenceCount": len(evidence), "notes": args.get("notes") or []}, indent=2), "images": []}
    if name == "ms_roblox_build_verifier":
        return _roblox_build_verifier(args, manager)
    if name == "ms_roblox_gui_audit":
        return _roblox_ui_audit(args, manager)
    if name == "ms_roblox_script_audit":
        return _roblox_script_audit(args, manager)
    if name == "ms_roblox_playtest_director":
        return _roblox_playtest_director(args, manager)
    if name == "ms_roblox_asset_scout":
        return _roblox_asset_scout(args, manager)
    if name == "ms_roblox_scene_diff":
        return _roblox_scene_diff(args, manager)
    if name == "ms_roblox_error_triage":
        return _roblox_error_triage(args)
    if name == "ms_agent_plan_then_act":
        return _agent_plan_then_act(args)
    if name == "ms_agent_self_check":
        return _agent_self_check(args)
    if name == "ms_agent_context_recall":
        return _agent_context_recall(args, manager)
    if name == "ms_workflow_plan":
        objective = str(args.get("objective", "")).strip()
        domains = [str(x).strip().lower() for x in (args.get("domains") or []) if str(x).strip()]
        targets = [str(x).strip().lower() for x in (args.get("targets") or []) if str(x).strip()]
        phases = ["Discover current project state and define measurable acceptance criteria."]
        mapping = {
            "ui": "Design information hierarchy and states; implement responsive layout; verify navigation, readability, focus, and input.",
            "ui-ux": "Design information hierarchy and states; implement responsive layout; verify navigation, readability, focus, and input.",
            "animation": "Define clips, rig/avatar constraints, transitions, root motion, events, and interruption cases; preview and test in runtime.",
            "vfx": "Define timing, readability, color/contrast, spawn bounds, pooling, and performance budget; capture visual evidence.",
            "model": "Set scale/poly/UV/material/collision budgets; create in Blender; export, import, and validate in the target engine.",
            "gameplay": "Implement the smallest vertical slice; add automated checks and a focused play test.",
            "build": "Compile, run tests, create a development build, inspect logs, and smoke-test the artifact.",
        }
        phases += [mapping.get(d, f"Implement and verify the {d} workstream.") for d in domains]
        if "blender" in targets and any(t in targets for t in ("unity", "roblox", "godot", "unreal")):
            phases.append("Use ms_parallel_tools only for independent Blender and engine operations; use ms_engine_handoff before import.")
        phases += ["Integrate all workstreams and test cross-system behavior.", "Run ms_quality_checklist for each domain, then ms_critic_review with concrete evidence."]
        return {"text": json.dumps({"objective": objective, "domains": domains, "targets": targets, "phases": phases}, indent=2), "images": []}
    if name == "ms_parallel_tools":
        calls = list(args.get("calls") or [])
        if not calls or len(calls) > 6:
            raise RuntimeError("calls must contain 1 to 6 entries")
        servers = [str(c.get("server", "")).strip() for c in calls]
        if any(not x for x in servers) or len(set(servers)) != len(servers):
            raise RuntimeError("each parallel call must target a different non-empty server")
        def run_one(item):
            sid, tool = str(item.get("server", "")).strip(), str(item.get("tool", "")).strip()
            if not tool: raise RuntimeError("tool is required")
            result = manager.call_on_server(sid, tool, item.get("arguments") or {}, 120)
            return sid, tool, result
        rows, images = [], []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(calls)) as pool:
            future_map = {pool.submit(run_one, item): item for item in calls}
            for fut in concurrent.futures.as_completed(future_map):
                item = future_map[fut]
                try:
                    sid, tool, result = fut.result()
                    rows.append({"server": sid, "tool": tool, "ok": True, "text": result.get("text", "")})
                    images.extend(result.get("images") or [])
                except Exception as exc:
                    rows.append({"server": item.get("server"), "tool": item.get("tool"), "ok": False, "error": str(exc)})
        return {"text": json.dumps({"results": rows}, indent=2), "images": images}
    if name == "ms_quality_checklist":
        domain = str(args.get("domain", "")).strip().lower()
        gates = {
            "ui-ux": ["all states represented", "responsive anchors/layout", "keyboard/controller/touch path", "readable contrast and type", "empty/error/loading feedback", "no console errors"],
            "animation": ["rig/avatar compatibility", "clip loop/timing", "transition and interruption behavior", "root motion policy", "events aligned", "runtime preview without warnings"],
            "vfx": ["silhouette/readability", "timing and lifecycle", "pooling/no leaks", "bounds and culling", "target-platform particle/GPU budget", "multi-angle capture"],
            "model": ["correct scale/orientation/pivot", "clean normals/topology", "UV/material integrity", "poly/texture budget", "collision/LOD", "export-import round trip"],
            "gameplay": ["acceptance criteria", "edge cases", "save/network/input interactions", "focused automated test", "play-mode reproduction", "clean logs"],
            "build": ["clean compile", "tests pass", "development build produced", "startup smoke test", "runtime logs clean", "artifact/version recorded"],
        }
        if domain not in gates: raise RuntimeError(f"unknown quality domain '{domain}'")
        return {"text": json.dumps({"domain": domain, "target": args.get("target"), "requiredEvidence": gates[domain]}, indent=2), "images": []}
    if name == "ms_test_matrix":
        f=str(args.get("feature", "feature")); plats=args.get("platforms") or ["target platform"]
        checks=["happy path", "invalid/missing data", "rapid repeat and interruption", "save/load or reconnect", "input/device changes", "performance under expected load", "clean logs"]
        return {"text": json.dumps({"feature": f, "platforms": plats, "checks": checks}, indent=2), "images": []}
    if name == "ms_create_canvas_texture":
        raw_name = str(args.get("name") or "").strip() or f"texture-{uuid.uuid4().hex[:12]}"
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw_name).strip("-.")[:80] or "texture"
        pattern = str(args.get("pattern", "checker")).lower()
        w = max(64, min(4096, int(args.get("width") or 1024))); h = max(64, min(4096, int(args.get("height") or 1024)))
        tile = max(4, min(512, int(args.get("tile_size") or 64)))
        bg, fg, ac = str(args.get("background") or "#24242b"), str(args.get("foreground") or "#8b82f6"), str(args.get("accent") or "#c7c3ff")
        seed = int(args["seed"]) if args.get("seed") is not None else 1; rnd = random.Random(seed)
        defs, shapes = [], [f'<rect width="{w}" height="{h}" fill="{html.escape(bg)}"/>']
        if pattern == "checker":
            for y in range(0,h,tile):
                for x in range(0,w,tile):
                    if (x//tile+y//tile)%2==0: shapes.append(f'<rect x="{x}" y="{y}" width="{tile}" height="{tile}" fill="{html.escape(fg)}"/>')
        elif pattern in ("grid","brick"):
            for y in range(0,h,tile):
                offset = tile//2 if pattern=="brick" and (y//tile)%2 else 0
                shapes.append(f'<path d="M0 {y}H{w}" stroke="{html.escape(fg)}" stroke-width="2"/>')
                for x in range(-offset,w,tile): shapes.append(f'<path d="M{x} {y}v{tile}" stroke="{html.escape(fg)}" stroke-width="2"/>')
        elif pattern in ("dots","studs"):
            r=max(2,tile*.28)
            for y in range(tile//2,h,tile):
                for x in range(tile//2,w,tile):
                    shapes.append(f'<circle cx="{x}" cy="{y}" r="{r:.1f}" fill="{html.escape(fg)}" stroke="{html.escape(ac)}" stroke-width="{max(1,tile*.04):.1f}"/>')
        elif pattern == "stripes":
            for x in range(-h,w,tile*2): shapes.append(f'<path d="M{x} {h}L{x+h} 0" stroke="{html.escape(fg)}" stroke-width="{tile}" opacity=".8"/>')
        elif pattern == "hex":
            rr=tile/2; dy=rr*1.732
            for row,y in enumerate([i*dy for i in range(int(h/dy)+2)]):
                for x in range(-tile,w+tile,int(tile*1.5)):
                    cx=x+(tile*.75 if row%2 else 0); pts=[]
                    for i in range(6):
                        import math; a=math.pi/3*i; pts.append(f"{cx+rr*math.cos(a):.1f},{y+rr*math.sin(a):.1f}")
                    shapes.append(f'<polygon points="{" ".join(pts)}" fill="none" stroke="{html.escape(fg)}" stroke-width="2"/>')
        elif pattern == "noise":
            for _ in range(min(5000,max(200,w*h//800))):
                x,y=rnd.randrange(w),rnd.randrange(h); r=rnd.uniform(1,max(2,tile*.12)); op=rnd.uniform(.08,.45)
                shapes.append(f'<circle cx="{x}" cy="{y}" r="{r:.1f}" fill="{html.escape(fg)}" opacity="{op:.2f}"/>')
        else: raise RuntimeError(f"unsupported pattern '{pattern}'")
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{"".join(defs+shapes)}</svg>'
        out_dir=os.path.join(HERE,"generated","canvas"); os.makedirs(out_dir,exist_ok=True); path=os.path.join(out_dir,safe+".svg")
        with open(path,"w",encoding="utf-8") as f: f.write(svg)
        return {"text": json.dumps({"created": path, "format":"SVG", "size":[w,h], "pattern":pattern, "seed":seed, "figmaImport":"Drag the SVG into Figma or pass this path/source to a connected Figma MCP.", "svg":svg}, indent=2), "images": []}
    if name == "ms_create_canvas_ui":
        raw_name=str(args.get("name") or "").strip() or f"ui-mockup-{uuid.uuid4().hex[:12]}"
        safe=re.sub(r"[^a-zA-Z0-9._-]+","-",raw_name).strip("-.")[:80] or "ui-mockup"
        w=max(240,min(4096,int(args.get("width") or 1440))); h=max(240,min(4096,int(args.get("height") or 900)))
        theme=str(args.get("theme") or "dark").lower()
        raw_accent=str(args.get("accent") or "").strip()
        safe_color=lambda value,default: value if re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{5})?",str(value or "")) else default
        palettes={
          "dark":{"bg":"#101116","panel":"#1b1e28","text":"#f6f5fa","muted":"#a4a9b8","accent":"#8b7cff","surface":"#252a38","radius":14,"font":"Inter,Arial,sans-serif"},
          "light":{"bg":"#f3f5f9","panel":"#ffffff","text":"#1c2432","muted":"#687386","accent":"#4d63dd","surface":"#edf0f7","radius":12,"font":"Inter,Arial,sans-serif"},
          "game":{"bg":"#10131c","panel":"#1b2231","text":"#f6f0d8","muted":"#aab2c5","accent":"#e9a44a","surface":"#252f43","radius":12,"font":"Arial,sans-serif"},
          "glass":{"bg":"#111321","panel":"#24283bcc","text":"#ffffff","muted":"#b7b9c8","accent":"#8a8cff","surface":"#ffffff10","radius":18,"font":"Inter,Arial,sans-serif"},
          "anime":{"bg":"#171329","panel":"#282043","text":"#fff7fb","muted":"#c7b7d8","accent":"#ff6ba8","surface":"#382b58","radius":18,"font":"Arial,sans-serif"},
          "fantasy":{"bg":"#101b1b","panel":"#1b302d","text":"#f7efd6","muted":"#b2c3b4","accent":"#d9b35b","surface":"#29423b","radius":10,"font":"Georgia,serif"},
          "low-poly":{"bg":"#17212a","panel":"#233541","text":"#f1f6f5","muted":"#b2c4ca","accent":"#69c7b4","surface":"#304954","radius":5,"font":"Arial,sans-serif"},
          "realistic-pbr":{"bg":"#171a20","panel":"#252a32","text":"#f2f3f5","muted":"#b0b6c0","accent":"#8eb8d8","surface":"#303741","radius":8,"font":"Inter,Arial,sans-serif"},
          "cyberpunk":{"bg":"#090c19","panel":"#151a30","text":"#f0fbff","muted":"#8ca5bd","accent":"#2de2e6","surface":"#202b46","radius":4,"font":"Arial,sans-serif"},
          "gothic":{"bg":"#100d12","panel":"#24171f","text":"#f3e8eb","muted":"#b9a1aa","accent":"#c34c62","surface":"#35222d","radius":6,"font":"Georgia,serif"},
          "cozy":{"bg":"#f3e9d7","panel":"#fff8ed","text":"#43372c","muted":"#887463","accent":"#b56c42","surface":"#ead8bf","radius":18,"font":"Georgia,serif"},
          "pixel":{"bg":"#111b2a","panel":"#1b2a40","text":"#fff0c7","muted":"#a8b8d2","accent":"#f5b642","surface":"#293d58","radius":0,"font":"monospace"},
          "minimal":{"bg":"#f6f7f9","panel":"#ffffff","text":"#161a22","muted":"#737b89","accent":"#4169e1","surface":"#f0f2f6","radius":10,"font":"Inter,Arial,sans-serif"},
          "sci-fi":{"bg":"#071520","panel":"#10283a","text":"#e7f7ff","muted":"#86afc2","accent":"#40d7ff","surface":"#17364b","radius":6,"font":"Arial,sans-serif"},
          "cartoon":{"bg":"#17324b","panel":"#255276","text":"#fffbea","muted":"#c5d8e9","accent":"#ffb13b","surface":"#326a91","radius":20,"font":"Arial,sans-serif"},
          "luxury":{"bg":"#11100e","panel":"#211e18","text":"#f8f0dc","muted":"#bcb29c","accent":"#d8b86a","surface":"#30291d","radius":7,"font":"Georgia,serif"}
        }
        pal=palettes.get(theme,palettes["dark"]); accent=safe_color(raw_accent,pal["accent"])
        bg,panel,text,muted=pal["bg"],pal["panel"],pal["text"],pal["muted"]
        title=html.escape(str(args.get("title") or raw_name))
        comps=args.get("components") or [{"type":"frame","x":48,"y":72,"width":w-96,"height":h-120,"label":""},{"type":"text","x":84,"y":118,"width":500,"height":42,"label":title},{"type":"card","x":84,"y":188,"width":300,"height":230,"label":"Featured item"},{"type":"button","x":84,"y":h-112,"width":220,"height":52,"label":"Continue"}]
        defs=[f'<linearGradient id="bgGlow" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{accent}" stop-opacity=".22"/><stop offset="1" stop-color="{bg}" stop-opacity="0"/></linearGradient>',f'<linearGradient id="accentFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{accent}"/><stop offset="1" stop-color="{accent}" stop-opacity=".78"/></linearGradient>','<filter id="shadow" x="-30%" y="-30%" width="160%" height="180%"><feDropShadow dx="0" dy="5" stdDeviation="7" flood-color="#000000" flood-opacity=".22"/></filter>']
        els=[f'<rect width="{w}" height="{h}" fill="{bg}"/>',f'<rect width="{w}" height="{h}" fill="url(#bgGlow)"/>',f'<rect x="0" y="0" width="{w}" height="5" fill="{accent}"/>',f'<text x="28" y="32" fill="{muted}" font-family="{pal["font"]}" font-size="11" letter-spacing="2">{html.escape(theme.upper())}  /  DESIGN SYSTEM</text>']
        for i,c in enumerate(comps[:100]):
            typ=str(c.get("type","frame")); x=max(0,min(w-1,float(c.get("x",0)))); y=max(0,min(h-1,float(c.get("y",0)))); cw=max(1,min(w-x,float(c.get("width",200)))); ch=max(1,min(h-y,float(c.get("height",50)))); label=html.escape(str(c.get("label",typ.title())))
            radius=min(float(pal["radius"]),ch*.25,cw*.12)
            if typ=="text":
                fs=max(11,min(46,ch*.66)); els.append(f'<text x="{x}" y="{y+ch*.72}" fill="{text}" font-family="{pal["font"]}" font-size="{fs:.0f}" font-weight="700">{label}</text>')
                if ch>=28: els.append(f'<rect x="{x}" y="{y+ch*.9}" width="{min(cw,70)}" height="2" rx="1" fill="{accent}" opacity=".8"/>')
            elif typ=="button":
                els.append(f'<rect x="{x}" y="{y+2}" width="{cw}" height="{max(1,ch-2)}" rx="{radius}" fill="#000000" opacity=".20"/>')
                els.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch-2}" rx="{radius}" fill="url(#accentFill)" stroke="#ffffff" stroke-opacity=".20" filter="url(#shadow)"/>')
                els.append(f'<text x="{x+cw/2}" y="{y+ch*.58}" text-anchor="middle" fill="#ffffff" font-family="{pal["font"]}" font-size="{max(11,min(18,ch*.32)):.0f}" font-weight="700">{label}</text>')
            elif typ=="input":
                els.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="{radius}" fill="{bg}" stroke="{accent}" stroke-opacity=".72" stroke-width="1.5"/>')
                els.append(f'<text x="{x+14}" y="{y+ch*.62}" fill="{muted}" font-family="{pal["font"]}" font-size="{max(10,min(15,ch*.3)):.0f}">{label}</text>')
            elif typ=="image":
                els.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="{radius}" fill="{panel}" stroke="{accent}" stroke-dasharray="5 5"/>')
                els.append(f'<path d="M{x+cw*.28} {y+ch*.72}l{cw*.18}-{ch*.24} {cw*.13} {ch*.14} {cw*.13}-{ch*.2} {cw*.18} {ch*.3}z" fill="{accent}" opacity=".55"/>')
                els.append(f'<text x="{x+cw/2}" y="{y+ch*.9}" text-anchor="middle" fill="{muted}" font-family="{pal["font"]}" font-size="{max(9,min(13,ch*.16)):.0f}">{label or "ASSET SLOT"}</text>')
            elif typ=="badge":
                els.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="{ch/2}" fill="{accent}" fill-opacity=".18" stroke="{accent}" stroke-opacity=".8"/>')
                els.append(f'<circle cx="{x+ch*.35}" cy="{y+ch/2}" r="{min(4,ch*.12)}" fill="{accent}"/>')
                els.append(f'<text x="{x+ch*.62}" y="{y+ch*.62}" fill="{text}" font-family="{pal["font"]}" font-size="{max(9,min(13,ch*.3)):.0f}" font-weight="700">{label}</text>')
            else:
                fill=panel if typ in ("frame","card") else pal["surface"]
                stroke=accent if typ=="frame" else "#ffffff"
                sw=1.5 if typ=="frame" else 1
                els.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-opacity="{.48 if typ=="frame" else .12}" stroke-width="{sw}" filter="url(#shadow)"/>')
                if label and typ!="frame":
                    els.append(f'<text x="{x+14}" y="{y+min(ch*.36,26)}" fill="{text}" font-family="{pal["font"]}" font-size="{max(11,min(17,ch*.16)):.0f}" font-weight="700">{label}</text>')
                    els.append(f'<path d="M{x+14} {y+min(ch*.45,36)}h{min(cw-28,70)}" stroke="{accent}" stroke-width="2" stroke-linecap="round"/>')
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs>{"".join(defs)}</defs>{"".join(els)}</svg>'
        out_dir=os.path.join(HERE,"generated","canvas"); os.makedirs(out_dir,exist_ok=True); path=os.path.join(out_dir,safe+".svg")
        if os.path.exists(path): path=os.path.join(out_dir,safe+"-"+uuid.uuid4().hex[:8]+".svg")
        with open(path,"w",encoding="utf-8") as f:f.write(svg)
        tokens={"background":bg,"panel":panel,"text":text,"muted":muted,"accent":accent,"radius":pal["radius"],"font":pal["font"],"theme":theme if theme in palettes else "dark","canvas":{"width":w,"height":h},"componentCount":min(len(comps),100)}
        stem=os.path.splitext(os.path.basename(path))[0]
        tokens_path=os.path.join(out_dir,stem+"-tokens.json")
        manifest_path=os.path.join(out_dir,stem+"-manifest.json")
        with open(tokens_path,"w",encoding="utf-8") as f:json.dump(tokens,f,indent=2,ensure_ascii=False)
        manifest={"name":safe,"format":"SVG","source":path,"tokens":tokens_path,"size":[w,h],"theme":tokens["theme"],"componentCount":tokens["componentCount"],"handoff":"The SVG and token JSON are local source artifacts. Convert/upload image assets and wire them in the target engine only through its supported asset pipeline; this file does not prove an in-engine import."}
        with open(manifest_path,"w",encoding="utf-8") as f:json.dump(manifest,f,indent=2,ensure_ascii=False)
        return {"text":json.dumps({"created":path,"artifactKind":"local-svg-mockup","nativeUiCreated":False,"engineImported":False,"summary":"Local SVG mockup saved under this bridge installation; no native editor UI was created.","format":"SVG","size":[w,h],"theme":tokens["theme"],"accent":accent,"components":min(len(comps),100),"tokens":tokens,"tokensFile":tokens_path,"manifest":manifest_path,"handoff":manifest["handoff"],"svg":svg},indent=2),"images":[]}
    if name == "ms_create_icon_pack":
        raw_name=str(args.get("name") or "").strip() or f"icon-pack-{uuid.uuid4().hex[:10]}"
        safe=re.sub(r"[^a-zA-Z0-9._-]+","-",raw_name).strip("-.")[:60] or "icon-pack"
        style=str(args.get("style") or "outline").lower()
        if style not in {"outline","solid","duotone","pixel","game"}: raise RuntimeError(f"unsupported icon style '{style}'")
        requested=args.get("icons") or []
        if not isinstance(requested,list) or not 1<=len(requested)<=64: raise RuntimeError("icons must be an array containing 1 to 64 names")
        icons=[]
        for raw in requested:
            icon=re.sub(r"[^a-zA-Z0-9_-]+","-",str(raw or "").strip().lower()).strip("-_")[:48]
            if icon and icon not in icons: icons.append(icon)
        if not icons: raise RuntimeError("provide at least one valid icon name")
        size=max(16,min(512,int(args.get("size") or 64)))
        def icon_color(value,default):
            v=str(value or "").strip()
            return v if re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{5})?",v) else default
        fg=icon_color(args.get("primary_color"),"#f5f7ff")
        accent=icon_color(args.get("accent_color"),"#8b7cff")
        bg=icon_color(args.get("background"),"#171a24")
        shapes={
          "sword":"<path d='M14 3l7-2-2 7-9 9-4-4z'/><path d='M5 13l6 6M3 17l4 4M4 20l-1 1'/>",
          "shield":"<path d='M12 2l8 3v6c0 5-3.2 8.8-8 11-4.8-2.2-8-6-8-11V5z'/><path d='M8 12l2.5 2.5L16 9'/>",
          "heart":"<path d='M20.5 8.7c0 5-8.5 11-8.5 11s-8.5-6-8.5-11a4.5 4.5 0 018.5-1.8 4.5 4.5 0 018.5 1.8z'/>",
          "coin":"<circle cx='12' cy='12' r='9'/><circle cx='12' cy='12' r='6'/><path d='M14.5 8.5c-.7-.7-1.5-1-2.5-1-1.4 0-2.5.7-2.5 1.8S10.7 11 12 11s2.5.7 2.5 1.8S13.4 15 12 15c-1 0-2-.3-2.7-1M12 5.5v13'/>",
          "bag":"<path d='M5 8h14l1 13H4z'/><path d='M8 8V6a4 4 0 018 0v2'/>",
          "home":"<path d='M3 11l9-8 9 8M5 10v11h14V10M9 21v-7h6v7'/>",
          "settings":"<path d='M12 8.5a3.5 3.5 0 100 7 3.5 3.5 0 000-7z'/><path d='M19.4 13.5a7.6 7.6 0 000-3l1.5-1.2-1.8-3.1-1.8.7a7.8 7.8 0 00-2.6-1.5L14.4 3h-3.6l-.3 2.4A7.8 7.8 0 008 6.9l-1.8-.7-1.8 3.1 1.5 1.2a7.6 7.6 0 000 3l-1.5 1.2 1.8 3.1 1.8-.7a7.8 7.8 0 002.5 1.5l.3 2.4h3.6l.3-2.4a7.8 7.8 0 002.6-1.5l1.8.7 1.8-3.1z'/>",
          "target":"<circle cx='12' cy='12' r='9'/><circle cx='12' cy='12' r='5'/><circle cx='12' cy='12' r='1.5'/>",
          "map":"<path d='M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z'/><path d='M9 3v15M15 6v15'/>",
          "potion":"<path d='M9 3h6M10 3v5l-5 7a5 5 0 004 6h6a5 5 0 004-6l-5-7V3'/><path d='M7 14h10'/>",
          "star":"<path d='M12 2.5l2.9 6 6.6.9-4.8 4.7 1.1 6.6-5.8-3.1-5.8 3.1 1.1-6.6-4.8-4.7 6.6-.9z'/>",
          "crown":"<path d='M3 7l5 4 4-7 4 7 5-4-2 13H5z'/><path d='M5 17h14'/>",
          "bolt":"<path d='M13 2L5 13h6l-1 9 9-12h-6z'/>",
          "fire":"<path d='M12 22c-5 0-8-3.2-8-7.5 0-3 1.8-5.2 4.4-7.5.2 2.4 1.3 3.2 2.3 3.7C10.5 7.5 13 4.5 15 2c-.2 4 1.2 6.1 3 8.2 1.2 1.4 2 2.8 2 4.7C20 19 16.7 22 12 22z'/><path d='M12 19c-1.8 0-3-1.3-3-3 0-1.4 1-2.4 2.5-3.8.2 1.4 1 2.2 1.7 2.5.8 1 .8 1.6.8 2.2 0 1.2-.8 2.1-2 2.1z'/>",
          "skull":"<path d='M5 12a7 7 0 1114 0v4l-2 2v3h-3v-2h-4v2H7v-3l-2-2z'/><circle cx='9' cy='12' r='1.5'/><circle cx='15' cy='12' r='1.5'/><path d='M10 17h4'/>",
          "lock":"<rect x='4' y='10' width='16' height='11' rx='2'/><path d='M8 10V7a4 4 0 018 0v3M12 14v3'/>",
          "user":"<circle cx='12' cy='7' r='4'/><path d='M4 21a8 8 0 0116 0'/>",
          "search":"<circle cx='10.5' cy='10.5' r='6.5'/><path d='M16 16l5 5'/>",
          "gem":"<path d='M6 3h12l4 6-10 12L2 9z'/><path d='M2 9h20M6 3l3 6 3 12 3-12 3-6'/>",
          "trophy":"<path d='M7 3h10v5a5 5 0 01-10 0zM7 5H3v3a5 5 0 004 5M17 5h4v3a5 5 0 01-4 5M12 13v5M8 21h8M9 18h6'/>",
          "quest":"<path d='M5 3h14v18l-7-4-7 4z'/><path d='M9 8h6M9 11h6'/>",
          "book":"<path d='M3 5a3 3 0 013-3h6v18H6a3 3 0 00-3 2zM21 5a3 3 0 00-3-3h-6v18h6a3 3 0 013 2z'/>",
          "compass":"<circle cx='12' cy='12' r='9'/><path d='M15.5 8.5l-2.2 4.8-4.8 2.2 2.2-4.8z'/>",
          "moon":"<path d='M20 15.5A8.5 8.5 0 018.5 4 8.5 8.5 0 1020 15.5z'/>",
          "sun":"<circle cx='12' cy='12' r='4'/><path d='M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1'/>",
          "check":"<path d='M4 12l5 5L20 6'/>",
          "close":"<path d='M5 5l14 14M19 5L5 19'/>",
          "warning":"<path d='M12 3L2 21h20z'/><path d='M12 9v5M12 17.5v.5'/>",
          "play":"<path d='M6 3l15 9-15 9z'/>",
          "pause":"<path d='M7 4h4v16H7zM15 4h4v16h-4z'/>",
          "menu":"<path d='M3 6h18M3 12h18M3 18h18'/>",
          "chat":"<path d='M4 4h16v12H9l-5 4z'/><path d='M8 8h8M8 12h5'/>",
          "sparkles":"<path d='M12 2l2 7 7 3-7 2-2 8-2-8-7-2 7-3z'/><path d='M19 2v4M17 4h4M4 16v4M2 18h4'/>"
        }
        out_dir=os.path.join(HERE,"generated","icons"); os.makedirs(out_dir,exist_ok=True)
        base=safe+"-"+uuid.uuid4().hex[:8]; files=[]; symbols=[]; contact=[]; cols=8; cell=88; rows=(len(icons)+cols-1)//cols
        for i,icon in enumerate(icons):
            shape=shapes.get(icon,shapes["sparkles"]); known=icon in shapes
            icon_fg="#ffffff" if style=="game" else fg
            bg_shape=f'<circle cx="12" cy="12" r="11" fill="{accent}" fill-opacity=".95"/>' if style=="game" else (f'<path d="M4 4h16v16H4z" fill="{accent}" fill-opacity=".18"/>' if style=="duotone" else "")
            stroke="none" if style=="solid" else icon_fg
            sw="2.3" if style in ("solid","game") else "1.8"
            fill=icon_fg if style=="solid" else "none"
            if style=="pixel": sw="2"; shape_render='crispEdges'; linecap='square'; linejoin='miter'
            else: shape_render='geometricPrecision'; linecap='round'; linejoin='round'
            inner=f'<g fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linecap="{linecap}" stroke-linejoin="{linejoin}">{shape}</g>'
            if style=="duotone": inner=f'<g fill="{accent}" fill-opacity=".23" stroke="{icon_fg}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{shape}</g>'
            if style=="solid": inner=f'<g fill="{icon_fg}" stroke="{icon_fg}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{shape}</g>'
            svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" shape-rendering="{shape_render}"><title>{html.escape(icon)}</title>{bg_shape}{inner}</svg>'
            path=os.path.join(out_dir,f"{base}-{icon}.svg")
            with open(path,"w",encoding="utf-8") as f:f.write(svg)
            files.append({"name":icon,"knownGlyph":known,"path":path,"format":"SVG","viewBox":"0 0 24 24"})
            symbols.append(f'<symbol id="{html.escape(icon)}" viewBox="0 0 24 24">{bg_shape}{inner}</symbol>')
            x=(i%cols)*cell; y=(i//cols)*cell
            contact.append(f'<g transform="translate({x+32} {y+8})"><rect width="56" height="56" rx="10" fill="{bg}" stroke="{accent}" stroke-opacity=".45"/><g transform="translate(16 16) scale(1)" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linecap="{linecap}" stroke-linejoin="{linejoin}">{shape}</g><text x="28" y="72" text-anchor="middle" font-family="Arial,sans-serif" font-size="9" fill="{fg}">{html.escape(icon[:16])}</text></g>')
        sprite=f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}"><defs>{"".join(symbols)}</defs><use href="#{icons[0]}" width="{size}" height="{size}"/></svg>'
        sprite_path=os.path.join(out_dir,base+"-sprite.svg")
        with open(sprite_path,"w",encoding="utf-8") as f:f.write(sprite)
        cw=cols*cell; ch=max(1,rows)*cell
        contact_svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw}" height="{ch}" viewBox="0 0 {cw} {ch}"><rect width="100%" height="100%" fill="{bg}"/>{"".join(contact)}</svg>'
        contact_path=os.path.join(out_dir,base+"-contact-sheet.svg")
        with open(contact_path,"w",encoding="utf-8") as f:f.write(contact_svg)
        manifest={"name":safe,"version":"6.50.1","style":style,"size":size,"colors":{"primary":fg,"accent":accent,"background":bg},"icons":files,"spriteSheet":sprite_path,"contactSheet":contact_path,"usage":{"individual":"Use individual SVGs as editable source assets; convert/upload them through the target engine's supported image pipeline when required.","sprite":"Sprite sheet uses symbol ids; inspect target SVG support before relying on external references.","roblox":"Roblox ImageLabels require a supported uploaded image asset ID; this local SVG pack does not automatically upload or assign IDs."}}
        manifest_path=os.path.join(out_dir,base+"-manifest.json")
        with open(manifest_path,"w",encoding="utf-8") as f:json.dump(manifest,f,indent=2,ensure_ascii=False)
        return {"text":json.dumps({"created":True,"name":safe,"style":style,"size":size,"iconCount":len(files),"icons":files,"spriteSheet":sprite_path,"contactSheet":contact_path,"manifest":manifest_path,"colors":manifest["colors"],"importNotes":manifest["usage"]},indent=2),"images":[]}
    if name == "ms_figma_handoff":
        objective=str(args.get("objective","")).strip(); screens=args.get("screens") or ["Primary screen"]
        health=manager.health(); figma=next((x for x in health if "figma" in str(x.get("id","")).lower()),None)
        plan={"objective":objective,"platform":args.get("platform") or "responsive","style":args.get("style") or "project design system","figmaMcpAvailable":bool(figma and figma.get("alive")),"pages":["00 Cover & notes","01 Foundations","02 Components","03 Screens","04 Prototype"],"foundations":["color variables with semantic names","type scale and text styles","spacing/radius/elevation variables","grid and breakpoints"],"screens":screens,"componentRequirements":["Auto Layout","constraints/resizing","variants for default/hover/focus/pressed/disabled/loading/error","component properties","accessible naming"],"connectionState":"MCP process status only; pairing and edit access are not yet verified.","execution":"Call list_commands for the Figma server. With the bundled companion, require figma_status connected=true and permission=edit, inspect figma_get_document, then create/update native nodes and read back/export the actual result. Official MCP write tools require their own live authorization. If no editable connection is available, report the blocker and optionally create an importable SVG; do not claim that importing or editing happened."}
        return {"text":json.dumps(plan,indent=2),"images":[]}
    if name == "ms_asset_budget":
        return {"text": json.dumps({"target": args.get("target"), "platform": args.get("platform"), "budgets": ["triangle/vertex and draw-call limits", "texture dimensions/compression/memory", "material and shader variants", "bones/weights/animation clips", "audio format/streaming/voices", "VFX particles/overdraw/bounds", "LOD and collision complexity"]}, indent=2), "images": []}
    if name == "ms_release_checklist":
        return {"text": json.dumps({"engine": args.get("engine"), "platform": args.get("platform"), "checks": ["clean compile", "automated tests", "version and content manifest", "development build", "startup and changed-feature smoke test", "logs/crash reporting", "performance sanity", "rollback artifact"]}, indent=2), "images": []}
    if name == "ms_risk_register":
        systems=args.get("systems") or []
        risks=[{"area": x, "risk": "unknown integration or edge-case failure", "mitigation": "inspect, test in isolation, then integration-test with evidence"} for x in systems]
        risks += [{"area": "delivery", "risk": "unverified success", "mitigation": "quality checklist plus critic review and runnable build"}]
        return {"text": json.dumps({"objective": args.get("objective"), "risks": risks}, indent=2), "images": []}
    if name == "ms_prompt_rescue":
        prompt=str(args.get("prompt","")).strip()
        if not prompt: raise RuntimeError("prompt is required")
        engine=str(args.get("engine") or "unspecified"); constraints=[str(x) for x in (args.get("constraints") or [])]
        brief={"intent":prompt,"engine":engine,"genre":args.get("genre") or "infer from project","inferredDefaults":["preserve existing project conventions","build the smallest polished playable version first","support target inputs and aspect ratios","include loading/empty/error/interruption states","use secure authority and validated persistence where relevant","measure performance instead of assuming it"],"acceptanceCriteria":["real deliverable exists in the target project","primary user flow works end to end","edge and failure states are handled","focused tests and clean logs are recorded","visual/usability quality is coherent","performance is acceptable on the weakest target"],"constraints":constraints,"ambiguitiesToAskOnlyIfConsequential":["irreversible deletion or migration","paid/external service commitment","conflicting art/product direction","missing credentials or unavailable engine"]}
        return {"text":json.dumps(brief,indent=2),"images":[]}
    if name == "ms_game_blueprint":
        return {"text":json.dumps({"concept":args.get("concept"),"engine":args.get("engine"),"platforms":args.get("platforms") or ["desktop","mobile"],"multiplayer":bool(args.get("multiplayer")),"sections":{"pillars":["player fantasy","differentiator","session promise"],"coreLoop":["enter","decide","act","feedback","reward","progress"],"systems":["controls/camera","gameplay","progression/economy","content","UI/accessibility","save/network","analytics/liveops"],"architecture":["ownership","data flow","module boundaries","failure recovery","configuration"],"production":["prototype","vertical slice","content production","alpha","beta","release"],"quality":["automated checks","playtests","performance budgets","security","release/rollback"]}},indent=2),"images":[]}
    if name == "ms_vertical_slice_plan":
        return {"text":json.dumps({"objective":args.get("objective"),"engine":args.get("engine"),"deadline":args.get("deadline"),"include":["one representative player journey","production architecture for the riskiest systems","final-quality sample art/audio/UI","save/network path if relevant","instrumentation","focused tests and target-device profile"],"exclude":["content breadth","secondary modes","premature tooling","unproven polish variants"],"exitCriteria":["playable end to end","no blocking errors","quality bar demonstrated","risk retired with evidence","next milestone estimated from measured work"]},indent=2),"images":[]}
    if name == "ms_system_design_review":
        return {"text":json.dumps({"system":args.get("system"),"engine":args.get("engine"),"dependencies":args.get("dependencies") or [],"review":["single source of truth and authority","lifecycle/initialization/teardown","public interfaces and coupling","data validation and persistence","concurrency/reentrancy/idempotency","failure/retry/reconnect/rollback","test seams and observability","CPU/memory/network/content budgets","migration and compatibility"],"requiredEvidence":["current-state inspection","dependency map","focused test","runtime read-back","clean logs","profile where material"]},indent=2),"images":[]}
    if name == "ms_gameplay_balance_plan":
        return {"text":json.dumps({"system":args.get("system"),"goals":args.get("goals") or ["fair choices","clear progression","stable economy"],"segments":args.get("player_segments") or ["new","returning","expert"],"variables":["inputs/costs","outputs/rewards","time-to-goal","success/failure rate","power curves","sources/sinks","caps/cooldowns"],"method":["baseline equations","boundary simulation","seeded scenarios","telemetry events","A/B-safe configuration","review exploit loops","tune one variable family at a time"],"guardrails":["no pay-to-win coercion","no infinite source loop","no unrecoverable negative state","server validates awards"]},indent=2),"images":[]}
    if name == "ms_multiplayer_authority_audit":
        return {"text":json.dumps({"engine":args.get("engine"),"feature":args.get("feature"),"messages":args.get("messages") or [],"audit":["client trust boundary","server ownership","type/range/state validation","permission checks","rate/burst limits","replay/duplicate protection","ordering/idempotency","prediction/reconciliation","disconnect/rejoin","bandwidth and serialization","abuse telemetry"],"passEvidence":["invalid-message tests","spam test","two-client conflict test","latency/loss test","server-state read-back","clean logs"]},indent=2),"images":[]}
    if name == "ms_save_migration_plan":
        return {"text":json.dumps({"engine":args.get("engine"),"from":args.get("current_version"),"to":args.get("target_version"),"changes":args.get("changes") or [],"plan":["version every record","validate before mutate","backup or retain previous representation","migrate stepwise and idempotently","default missing fields conservatively","preserve unknown fields when possible","write only after verification","stage rollout with telemetry","support rollback/repair"],"tests":["oldest supported fixture","partially migrated fixture","corrupt/missing fields","repeat migration","concurrent save","rollback restore"]},indent=2),"images":[]}
    if name == "ms_performance_budget_plan":
        return {"text":json.dumps({"engine":args.get("engine"),"scene":args.get("scene"),"platforms":args.get("platforms") or ["weakest supported device"],"budgets":{"frame":"target FPS, main/render thread ms and spikes","memory":"steady/peak memory and leak-free transitions","gpu":"draw calls, triangles, overdraw, shader cost","network":"bytes/sec, messages/sec and burst caps","loading":"cold start, scene transition and streaming stalls","content":"texture, mesh, animation, audio and VFX limits"},"process":["capture baseline","profile representative worst case","fix largest measured bottleneck","repeat identical capture","record budget in CI/release gate"]},indent=2),"images":[]}
    if name == "ms_accessibility_audit":
        return {"text":json.dumps({"feature":args.get("feature"),"platforms":args.get("platforms") or [],"audit":["remappable controls and non-hold alternatives","keyboard/controller/touch focus path","text scale and contrast","color-independent meaning","captions and audio cues","reduced motion/flashing controls","timing/difficulty assists","plain language and cognitive load","screen-reader/platform semantics where supported"],"evidence":args.get("evidence") or [],"completion":"test with assist settings and at least keyboard/controller/touch paths relevant to targets"},indent=2),"images":[]}
    if name == "ms_content_pipeline_plan":
        return {"text":json.dumps({"engine":args.get("engine"),"contentTypes":args.get("content_types"),"sourceTools":args.get("source_tools") or [],"pipeline":["source-of-truth folder and ownership","naming/version/unit/axis conventions","export preset","automated import preset","validation of scale, pivots, UVs, materials, rigs and clips","optimization/LOD/collision/compression","copyright/license metadata","integration test scene","change propagation and rollback"],"doneWhen":["round trip is repeatable","warnings are resolved","asset meets budget","visual/runtime evidence captured"]},indent=2),"images":[]}
    if name == "ms_playtest_protocol":
        return {"text":json.dumps({"objective":args.get("objective"),"build":args.get("build"),"participants":max(1,int(args.get("participants") or 5)),"platforms":args.get("platforms") or [],"protocol":["freeze build and hypothesis","define participant segments","assign realistic tasks without leading","record behavior before opinions","capture completion/time/errors/confusion","debrief with open questions","classify severity and confidence","separate bugs from preference","make decision and retest"],"report":["observations","metrics","quotes","severity","root hypothesis","decision","owner","retest condition"]},indent=2),"images":[]}
    if name == "ms_definition_of_done":
        risk=str(args.get("risk") or "medium")
        return {"text":json.dumps({"feature":args.get("feature"),"engine":args.get("engine"),"risk":risk,"gates":["acceptance criteria demonstrated","code/content follows project architecture","happy path plus edge/failure/interruption states","automated or repeatable focused tests","clean compile/import/runtime logs","security/authority/save compatibility reviewed","accessibility/input/platform behavior checked","performance measured against budget","documentation/config/migration updated","critic review passed with concrete evidence","rollback path exists"],"extraForHighRisk":["two-person review","staged rollout","backup/repair tooling","load and abuse testing"] if risk=="high" else []},indent=2),"images":[]}
    if name == "ms_orchestrate_request":
        request=str(args.get("request","")).strip();engine=str(args.get("engine","")).lower();limit=max(8,min(40,int(args.get("max_skills") or 30)))
        if not request or engine not in {"roblox","unity","godot","blender","figma","general"}: raise RuntimeError("request and a valid engine are required")
        words={w for w in re.findall(r"[a-z0-9]+",request.lower()) if len(w)>2};ranked=[]
        for sid,v in skills.items():
            if v.get("engine")!=engine: continue
            hay=f"{sid} {v.get('name','')} {v.get('description','')} {' '.join(v.get('tags') or [])}".lower();score=sum(3 for w in words if w in hay)
            ranked.append((score,sid,v))
        ranked.sort(key=lambda x:(-x[0],x[1]));chosen=[];roles=set()
        for score,sid,v in ranked:
            r=v.get("capabilityRole","implementation")
            if r not in roles or score>3:
                chosen.append(sid);roles.add(r)
            if len(chosen)>=limit: break
        for _,sid,v in ranked:
            if len(chosen)>=limit: break
            if sid not in chosen: chosen.append(sid)
        return {"text":json.dumps({"request":request,"engine":engine,"skillStack":[{"id":sid,"name":skills[sid].get("name"),"role":skills[sid].get("capabilityRole"),"domain":skills[sid].get("capabilityDomain")} for sid in chosen],"executionRequired":True,"next":"Use this stack silently as guidance, inspect the project, and implement immediately through exact MCP commands. Call ms_activate_skill_stack only for genuinely complex work."},indent=2),"images":[]}
    if name == "ms_activate_skill_stack":
        request=str(args.get("request","")).strip();engine=str(args.get("engine","")).lower();ids=[str(x) for x in (args.get("skill_ids") or [])]
        if not request or engine not in {"roblox","unity","godot","blender","figma","general"}: raise RuntimeError("request and a valid engine are required")
        if ids and (len(ids)<2 or len(ids)>40): raise RuntimeError("skill_ids must contain 2 to 40 entries")
        if not ids:
            ids=_build_skill_tool_mesh(request,engine,skills,virtual_tools,32,30,24)["skills"]
        missing=[x for x in ids if x not in skills or skills[x].get("engine")!=engine]
        if missing: raise RuntimeError("unknown or wrong-engine skills: "+", ".join(missing))
        stages=[];gates=[]
        for sid in ids:
            v=skills[sid];stages.append({"skill":sid,"role":v.get("capabilityRole"),"steps":v.get("steps") or [],"deliverables":v.get("deliverables") or []})
            for g in v.get("qualityGates") or []:
                if g not in gates:gates.append(g)
        return {"text":json.dumps({"request":request,"engine":engine,"planOnly":False,"executionRequired":True,"stages":stages,"completionGates":list(dict.fromkeys(gates + studio_standard.get("definitionOfDone", []))),"studioStandard":{"principles":studio_standard.get("principles",[]),"providerExecution":studio_standard.get("providerExecution",[]),"toolDiscipline":studio_standard.get("toolDiscipline",[]),"performance":studio_standard.get("performance",[]),"resultQuality":studio_standard.get("resultQuality",[]),"skillToolIntegration":studio_standard.get("skillToolIntegration",[]),"evidence":studio_standard.get("evidence",[]),"recovery":studio_standard.get("recovery",[]),"enginePractice":(studio_standard.get("engines") or {}).get(engine,[])},"mandatorySequence":["inspect current project","execute real MCP edits/artifact creation","run engine-native tests and profiling","read back final state","critic-review evidence","report only verified result","never mention skills, checks or internals to the user; keep the reply short and plain"]},indent=2),"images":[]}
    if name == "ms_animation_director":
        return {"text":json.dumps({"engine":args.get("engine"),"subject":args.get("subject"),"style":args.get("style") or "match project art direction","actions":args.get("actions") or [],"production":["reference and motion intent","rig/avatar compatibility and scale","key poses, arcs, weight, spacing and timing","clip list and naming","state machine, layers, masks and transitions","root motion policy and movement ownership","IK/constraints/procedural layers","events, hit windows and audio/VFX sync","retargeting, looping, interruption and blending","compression, LOD and networking","in-engine multi-angle review and gameplay validation"],"requiredSkillDomains":["animation","input-camera-character","performance-platform","testing-release"]},indent=2),"images":[]}
    if name == "ms_texture_art_pipeline":
        return {"text":json.dumps({"engine":args.get("engine"),"asset":args.get("asset"),"style":args.get("style") or "match project","platforms":args.get("platforms") or [],"production":["visual target and material breakup","real-world scale and texel density","UV strategy, seams, trim/atlas/tile decision","albedo/value hierarchy without baked lighting","normal/roughness/metal/AO/emissive channel rules","seamless or unique texture creation using Canvas/Blender as appropriate","color-space and compression settings","engine material and shader setup","mipmaps, filtering and distance readability","memory/batching/variant budget","final lighting and target-device validation"],"realArtifactRequired":True},indent=2),"images":[]}
    if name == "ms_art_direction":
        return {"text":json.dumps({"engine":args.get("engine"),"concept":args.get("concept"),"mood":args.get("mood"),"references":args.get("references") or [],"direction":["player fantasy and emotional target","shape and silhouette language","composition and focal hierarchy","palette and value structure","material/texture language","environment and prop rules","character readability","lighting, atmosphere and post-processing","UI/icon alignment","animation/VFX/audio cohesion","content consistency checklist and review board"],"execution":"Create representative final assets in the connected tools, import them, and validate in gameplay camera—not only a moodboard."},indent=2),"images":[]}
    if name == "ms_uiux_production":
        return {"text":json.dumps({"engine":args.get("engine"),"feature":args.get("feature"),"platforms":args.get("platforms") or [],"style":args.get("style"),"production":["user goal and flow","information hierarchy","wireframe and content states","tokens and reusable components","default/hover/focus/pressed/selected/disabled/loading/empty/error/success states","safe areas, aspect ratios and localization expansion","keyboard/controller/touch navigation","contrast, type scale, motion and reduced-motion","engine-native implementation and data binding","usability test and target-device screenshots"],"realImplementationRequired":True},indent=2),"images":[]}
    if name == "ms_vfx_production":
        return {"text":json.dumps({"engine":args.get("engine"),"effect":args.get("effect"),"style":args.get("style"),"platforms":args.get("platforms") or [],"production":["gameplay purpose and readability envelope","anticipation/impact/sustain/dissipation timing","shape, color and value progression","particles, meshes, trails, decals and shaders","lighting and camera interaction","animation/audio/gameplay event synchronization","pooling, bounds, lifecycle and cancellation","quality tiers and accessibility alternatives","overdraw, particle, shader and memory budgets","multi-angle runtime capture on target hardware"],"realEffectRequired":True},indent=2),"images":[]}
    if name == "ms_audio_production":
        return {"text":json.dumps({"engine":args.get("engine"),"feature":args.get("feature"),"style":args.get("style"),"platforms":args.get("platforms") or [],"production":["event taxonomy and priorities","source asset/recording/synthesis plan","variation and anti-repetition","spatialization, attenuation and occlusion","bus routing, loudness and dynamic range","concurrency, voice stealing and pooling","adaptive music states and transition timing","animation/VFX/gameplay sync","caption/visual cue/accessibility support","compression, streaming and memory budget","in-context mix review across devices"],"realAudioIntegrationRequired":True},indent=2),"images":[]}
    if name == "ms_engine_handoff":
        source, target = args.get("source", "blender"), args.get("target", "other")
        asset_type, fmt = args.get("asset_type", "asset"), args.get("format") or ("FBX" if target in ("unity", "unreal") else "glTF/GLB")
        steps = [f"Freeze naming and scale for the {asset_type} in {source}.", "Apply transforms; validate normals, UVs, materials, and origin/pivot.",
                 f"Export as {fmt} with textures in a portable relative folder.", f"Import through the {target} MCP server and capture importer warnings.",
                 "Place the asset in a test scene, verify scale/orientation/materials/collisions.", "Run ms_critic_review with import logs and visual/runtime evidence."]
        return {"text": json.dumps({"source": source, "target": target, "format": fmt, "checklist": steps}, indent=2), "images": []}
    raise RuntimeError(f"unknown built-in tool '{name}'")


# ══════════════════════════════════════════════════════════════════════════
#  HARDENED MCP CLIENT  (one per server in config.json)
# ══════════════════════════════════════════════════════════════════════════
class _ToolkitCtx(_TOOLKIT.Ctx if _TOOLKIT is not None else object):
    """Lets engine_toolkit call the connected MCP servers through this bridge."""

    _projects = {}

    def __init__(self, manager, blender_target='auto', workspace_project=None, blender_read_only=False):
        self.manager = manager
        self.blender_target=blender_target;self.workspace_project=workspace_project
        self.blender_read_only=blender_read_only

    def _headless(self):return self.blender_target=='workspace' or self.blender_target=='auto' and BLENDER_WORKSPACE.owns_target

    def call(self, server, tool, arguments, timeout=120):
        if server=='blender' and self._headless():
            if server in self.manager.disabled:raise RuntimeError('Blender is switched off in Engines settings.')
            return BLENDER_WORKSPACE.native_call(tool,dict(arguments,read_only=self.blender_read_only,**({'project':self.workspace_project} if self.workspace_project else {})),timeout)
        if server=='blender' and self.blender_target=='connected':return self.manager.call_on_server(server,tool,arguments,timeout,use_workspace=False)
        return self.manager.call_on_server(server, tool, arguments, timeout)

    def advertised(self, server):
        if server=='blender' and self._headless():return set(blender_workspace.NATIVE_NAMES)
        if server=='blender' and self.blender_target=='connected':
            client=self.manager.clients.get(server);return {t['name'] for t in client.tools_cache} if client else set()
        return _facade_advertised_names(self.manager, server)

    def studio_id(self, args):
        return _facade_roblox_studio_id(args or {}, self.manager)

    def project_hint(self, engine):
        return self._projects.get(engine, "") or str(((_read_config().get("engineProjects") or {}).get(engine)) or "")

    def remember_project(self, engine, path):
        self._projects[engine] = path


class _AssistHost:
    """What ms_run_staged_luau / ms_write_staged need from the bridge."""

    def __init__(self, manager):
        self.manager = manager

    def call(self, tool, arguments, timeout=120):
        return self.manager.call(tool, arguments, timeout)

    def studio_id(self, args):
        return _facade_roblox_studio_id(args or {}, self.manager)


def _toolkit_visible_tools(manager):
    """Toolkit tool definitions for engines this bridge actually has a server for."""
    if _TOOLKIT is None:
        return []
    have = set(manager.clients.keys())
    if BLENDER_WORKSPACE.owns_target or BLENDER_WORKSPACE.running:have.add('blender')
    out = []
    for d in _TOOLKIT.definitions():
        engine = _TOOLKIT.engine_of(d["name"])
        if engine in have:
            out.append(dict(d, server=engine))
    return out


def _toolkit_call(name, arguments, manager):
    spec = _TOOLKIT.REGISTRY[name]
    clean, notes = _resilient_arguments(spec.get("inputSchema"), arguments, name)
    out = _TOOLKIT.run(name, clean, _ToolkitCtx(manager,clean.get('target','auto'),clean.get('workspace_project'),not spec.get('writes',False)))
    return _annotate_repairs(out, notes)



class MCPClient:
    def __init__(self, server_id, command, args, env=None):
        self.id = server_id
        self.command = command
        self.args = list(args or [])
        self.env = env or {}
        self.proc = None
        self.req_id = 1
        self.write_lock = threading.Lock()
        self.call_lock = threading.Lock()   # serialize tool calls (single stdio pipe)
        self.pending = {}                    # id -> queue.Queue (one slot)
        self.pend_lock = threading.Lock()
        self.tools_cache = []
        # Set by a server's own tools/list_changed notification (see _reader).
        # The MCP handshake is otherwise a one-shot snapshot: a server that
        # hot-adds or removes a tool would leave us advertising a stale list
        # until it was restarted, and the agent would keep calling tools that no
        # longer exist.
        self.tools_stale = False
        self.resources_stale = False
        self.start_lock = threading.Lock()
        self._reader_thread = None
        # Pids being stopped by us. Reader EOF for these is normal lifecycle,
        # not a crash, so it should not produce a red false alarm.
        self._stopping_pids = set()
        # Crash-loop forensics (read by server_watch). The auto-restart used to
        # hide a server that something else kills over and over: the terminal
        # showed an endless quiet restart cycle with no explanation at all. We
        # keep just enough state to NAME the problem in the terminal instead:
        #  - last_exit: exit code from the final _reader EOF (crash vs kill hint)
        #  - stderr_tail: the last few stderr lines (usually the actual reason -
        #    port bind failure, missing dependency, crash trace)
        #  - restart_times: recent auto-restart timestamps (loop detector input)
        #  - loop_warned_at: throttle so the big red banner prints once per
        #    cooldown, not every 5s poll
        self.last_exit = None
        self.stderr_tail = []
        self.restart_times = []
        self.loop_warned_at = 0.0
        # Set when the configured command itself couldn't be launched at all
        # (e.g. 'uvx' not installed / not on PATH). This is NOT a crash - the
        # process never existed, so last_exit/stderr_tail stay empty and the
        # generic crash-loop banner used to print "the server printed no error
        # output before dying", which is misleading for a config problem the
        # user can fix in seconds. Kept across restarts so the banner can name
        # the real cause instead.
        self.start_error = None
        # Set when StudioMCP's stderr shows it connected to a FOREIGN WS host on
        # Studio's MCP port (not Studio). The unmistakable signature is a parse
        # error on the host's messages ("missing field `type`") - Studio speaks
        # the expected protocol, a squatter like ropilot speaks its own. This is
        # a timing-independent proof that the port is hijacked, unlike the
        # one-shot check_studio_port() boot probe which can miss a squatter that
        # grabs the port a moment after boot (seen live 2026-07-13: ropilot took
        # the port ~1s after the boot check ran, so nothing was flagged).
        self.saw_foreign_ws_host = False

    # ── lifecycle ─────────────────────────────────────────────────────────
    def _resolve(self, s):
        return os.path.expandvars(os.path.expanduser(str(s)))

    def start(self):
        with self.start_lock:
            if self.is_alive():
                return
            self.last_restart_at = time.time()
            cmd = [self._resolve(self.command)] + [self._resolve(a) for a in self.args]
            # A bare .py command (relative paths resolve against the bridge dir)
            # is run with the SAME interpreter the bridge itself uses, so it works
            # even on installs where only the `py` launcher exists (no `python`
            # on PATH). This is how the Studio MCP launcher is wired by default.
            if cmd[0].lower().endswith(".py"):
                script = cmd[0]
                if not os.path.isabs(script):
                    script = os.path.join(HERE, script)
                py = [sys.executable]
                # CPython's optional 3.13 free-threaded build is commonly named
                # python3.13t.exe. Its no-GIL threading wait has produced
                # OSError(22) while Windows tears down stdio launcher processes.
                # Keep accepting that interpreter, but run bridge children with
                # the GIL enabled for stable subprocess/stdio behavior.
                if sysconfig.get_config_var("Py_GIL_DISABLED"):
                    py += ["-X", "gil=1"]
                cmd = py + [script] + cmd[1:]
            # On Windows, npx/npm/yarn/pnpm/bunx are .cmd shims that Popen can't
            # launch directly (WinError 2). Run them through cmd.exe so any
            # node-based MCP server "just works" from config.json.
            if sys.platform == "win32":
                base = os.path.basename(cmd[0]).lower()
                if base in ("npx", "npm", "yarn", "pnpm", "bunx"):
                    cmd = ["cmd.exe", "/c"] + cmd
            env = dict(os.environ)
            for k, v in self.env.items():
                env[k] = self._resolve(v)
            # A restarted server must never retain a catalogue from its previous
            # process. Stale schemas made the UI look healthy and routed calls to
            # tools the new process hadn't advertised yet.
            self.tools_cache = []
            with self.pend_lock:
                self.pending.clear()
            log(f"[{self.id}] launching  ({' '.join(cmd)})", "cy")
            with _Spinner(f"    [{self.id}] starting..."):
                try:
                    self.proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        encoding="utf-8",
                        errors="replace",
                        cwd=HERE,
                        env=env,
                    )
                except FileNotFoundError:
                    # The OS couldn't find cmd[0] at all - this is a config
                    # problem (missing dependency, typo, not on PATH), not a
                    # transient crash. Auto-restart will keep retrying (the
                    # user may install it later), but name the real cause so
                    # it doesn't just look like an endless silent restart loop.
                    self.start_error = (
                        f"command not found: '{cmd[0]}' - is it installed and on PATH? "
                        f"(configured for server '{self.id}' in config.json)"
                    )
                    log(f"[{self.id}] {self.start_error}", "rd")
                    raise
                except OSError as e:
                    self.start_error = f"could not launch '{cmd[0]}': {e}"
                    log(f"[{self.id}] {self.start_error}", "rd")
                    raise
                else:
                    self.start_error = None
                self.saw_foreign_ws_host = False  # fresh process, fresh verdict
                self._reader_thread = threading.Thread(target=self._reader, args=(self.proc,), daemon=True)
                self._reader_thread.start()
                threading.Thread(target=self._stderr_drain, args=(self.proc,), daemon=True).start()

                try:
                    # MCP handshake.
                    self._request("initialize", {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "multiscript-bridge", "version": BRIDGE_VERSION},
                    }, timeout=30)
                    self._notify("notifications/initialized")
                    # Some MCP servers (notably Roblox's StudioMCP) advertise 0 tools at
                    # the instant initialize returns, because they connect to their
                    # backend (the running Studio) a moment AFTER the stdio handshake.
                    # A single tools/list then caches an empty list forever. So if we
                    # get nothing, retry for a few seconds to let the backend attach.
                    # Short per-attempt timeout so the bridge never looks frozen if the
                    # server stays silent (e.g. Studio not open yet); ~12s total budget.
                    for _ in range(12):
                        if self.refresh_tools(timeout=3):
                            break
                        if not self.is_alive():
                            break
                        time.sleep(1.0)
                except Exception as e:
                    # A launcher that exits at once (npx/Node missing, editor not
                    # found, bad config) used to surface as an opaque
                    # "[Errno 22] Invalid argument" - the write to its closed stdin
                    # pipe on Windows. Report the real reason: exit code + stderr.
                    time.sleep(0.4)
                    if not self.is_alive():
                        code = self.proc.poll() if self.proc else None
                        tail = " | ".join(self.stderr_tail[-3:]) if self.stderr_tail else ""
                        self.start_error = (f"the {self.id} launcher exited during startup (exit code {code})"
                                            + (f": {tail}" if tail else " - see the [" + self.id + "] stderr lines in logs/bridge_debug.log"))
                    else:
                        self.start_error = f"startup handshake failed: {e}"
                    log(f"[{self.id}] {self.start_error}", "rd")
                    self.stop()
                    raise RuntimeError(self.start_error) from e
            log(f"[{self.id}] MCP server up  ({len(self.tools_cache)} tools advertised)", "cy")

    def is_alive(self):
        return self.proc is not None and self.proc.poll() is None

    def restart(self):
        log(f"[{self.id}] restarting...", "yl")
        self.stop()
        time.sleep(0.4)
        self.start()

    def stop(self):
        with self.pend_lock:
            for q in self.pending.values():
                try:
                    q.put_nowait(None)
                except Exception:
                    pass
            self.pending.clear()
        proc = self.proc
        if proc:
            self._stopping_pids.add(proc.pid)
            # First close the protocol input. Well-behaved stdio MCP servers
            # exit on EOF, which lets Python launchers unwind cleanly instead of
            # being force-killed mid-wait (the source of the Windows Errno 22 /
            # TextIOWrapper noise in the supplied log).
            try:
                with self.write_lock:
                    if proc.stdin and not proc.stdin.closed:
                        proc.stdin.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                # A wrapper may own a real editor-server child. Only force the
                # entire tree after graceful EOF had a chance to work.
                try:
                    if sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True, timeout=8,
                        )
                    else:
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                except Exception:
                    pass
            except Exception:
                pass
        if self.proc is proc:
            self.proc = None

    # ── io threads ────────────────────────────────────────────────────────
    def _reader(self, proc):
        stream = proc.stdout
        while True:
            try:
                line = stream.readline()
            except Exception:
                break
            if line == "":  # EOF -> process exited
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue  # stray non-JSON log on stdout
            mid = msg.get("id")
            if mid is None:
                # A server NOTIFICATION (no id). The one that matters here is
                # tools/list_changed: a server that hot-adds or removes a tool
                # (a plugin toggled inside Studio, a Unity package reloaded) says
                # so here. Dropping it - which is exactly what used to happen -
                # left our cached tool list stale until the server restarted, so
                # the agent kept calling tools that no longer existed and could
                # not see new ones at all.
                method = msg.get("method")
                if method == "notifications/tools/list_changed":
                    self.tools_stale = True
                    log(f"[{self.id}] advertised tools changed - cache invalidated", "yl", terminal=False)
                elif method == "notifications/resources/list_changed":
                    self.resources_stale = True
                continue
            with self.pend_lock:
                q = self.pending.get(mid)
            if q is not None:
                try:
                    q.put_nowait(msg)
                except Exception:
                    pass
        try:
            code = proc.wait(timeout=0.5)
        except Exception:
            code = proc.poll()
        self.last_exit = code  # kept for the crash-loop banner in server_watch
        intentional = proc.pid in self._stopping_pids
        self._stopping_pids.discard(proc.pid)
        if not intentional:
            log(f"[{self.id}] stdout closed (process ended, exit code {code})", "rd")
        with self.pend_lock:
            for q in self.pending.values():
                try:
                    q.put_nowait(None)
                except Exception:
                    pass

    def _stderr_drain(self, proc):
        # Surface the child's stderr instead of silently discarding it - this
        # is often the ONLY clue why a server died (crash trace, port bind
        # failure, missing Studio, etc).
        try:
            for line in iter(proc.stderr.readline, ""):
                line = line.rstrip()
                if line:
                    # Ring buffer of the last stderr lines: when the server
                    # enters a crash loop, these are printed in the terminal
                    # banner - they are usually the only real explanation
                    # (port already in use, module not found, crash trace).
                    self.stderr_tail.append(line)
                    if len(self.stderr_tail) > 8:
                        self.stderr_tail.pop(0)
                    # Squatter signature: StudioMCP connected to a non-Studio host
                    # on the MCP port and can't parse its protocol. This is the
                    # ropilot hijack, timing-independent (see saw_foreign_ws_host).
                    low = line.lower()
                    if "failed to parse message from ws host" in low or "missing field `type`" in low:
                        self.saw_foreign_ws_host = True
                    log(f"[{self.id}] stderr: {line}", "yl", terminal=False)
        except Exception:
            pass

    # ── jsonrpc ───────────────────────────────────────────────────────────
    def _next_id(self):
        with self.write_lock:
            rid = self.req_id
            self.req_id += 1
            return rid

    def _notify(self, method, params=None):
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        with self.write_lock:
            self.proc.stdin.write(json.dumps(payload) + "\n")
            self.proc.stdin.flush()

    def _request(self, method, params, timeout):
        if not self.is_alive():
            raise RuntimeError(f"server '{self.id}' is not running")
        rid = self._next_id()
        q = queue.Queue(maxsize=1)
        with self.pend_lock:
            self.pending[rid] = q
        try:
            payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
            with self.write_lock:
                self.proc.stdin.write(json.dumps(payload) + "\n")
                self.proc.stdin.flush()
            try:
                return q.get(timeout=timeout)
            except queue.Empty:
                return None
        finally:
            with self.pend_lock:
                self.pending.pop(rid, None)

    # ── high-level ────────────────────────────────────────────────────────
    def refresh_tools(self, timeout=20):
        msg = self._request("tools/list", {}, timeout=timeout)
        if msg and "result" in msg:
            self.tools_cache = msg["result"].get("tools", [])
            self.tools_stale = False
        return self.tools_cache

    def list_resources(self, cursor=None, timeout=20):
        """Return this server's MCP resources without guessing their URIs."""
        with self.call_lock:
            if not self.is_alive():
                self.restart()
            params = {"cursor": cursor} if cursor else {}
            msg = self._request("resources/list", params, timeout=timeout)
            if msg is None:
                raise TimeoutError(f"No resource list from server '{self.id}' after {timeout}s.")
            if msg.get("error"):
                raise RuntimeError(msg["error"].get("message", json.dumps(msg["error"])))
            result = msg.get("result", {})
            return {"server": self.id, "resources": result.get("resources", []), "nextCursor": result.get("nextCursor")}

    def read_resource(self, uri, timeout=30):
        """Read text/blob MCP resource contents and preserve returned images."""
        with self.call_lock:
            if not self.is_alive():
                self.restart()
            msg = self._request("resources/read", {"uri": uri}, timeout=timeout)
            if msg is None:
                raise TimeoutError(f"No resource response from server '{self.id}' after {timeout}s.")
            if msg.get("error"):
                raise RuntimeError(msg["error"].get("message", json.dumps(msg["error"])))
            contents = msg.get("result", {}).get("contents", [])
            texts, images, metadata = [], [], []
            for item in contents:
                mime = item.get("mimeType", "")
                metadata.append({k: item.get(k) for k in ("uri", "mimeType") if item.get(k) is not None})
                if item.get("text") is not None:
                    texts.append(str(item.get("text")))
                elif item.get("blob") is not None and mime.startswith("image/"):
                    images.append({"data": item["blob"], "mimeType": mime})
                elif item.get("blob") is not None:
                    texts.append(json.dumps({"uri": item.get("uri", uri), "mimeType": mime, "blob": item["blob"]}))
            if metadata:
                texts.insert(0, json.dumps({"server": self.id, "resource": uri, "contents": metadata}, indent=2))
            return {"text": "\n".join(texts), "images": images}

    def call_tool(self, name, arguments, timeout):
        """Returns {"text":..., "images":[...]}. Raises on error/timeout."""
        with self.call_lock:
            for attempt in (1, 2):
                if not self.is_alive():
                    self.restart()
                msg = self._request("tools/call",
                                    {"name": name, "arguments": arguments}, timeout)
                if msg is None:
                    if not self.is_alive():
                        self.restart()
                        if name in _NON_IDEMPOTENT_NATIVE:
                            # The server died mid-call: the edit may or may not have been
                            # applied. Re-sending could apply it twice, so report instead.
                            raise RuntimeError(
                                f"The '{self.id}' server stopped while '{name}' was running and was restarted. "
                                f"The command may or may not have been applied - inspect the current state "
                                f"(script_read / inspect_instance) before sending it again. It was NOT re-sent automatically.")
                        msg = self._request("tools/call",
                                            {"name": name, "arguments": arguments}, timeout)
                    if msg is None:
                        raise TimeoutError(
                            f"No response from server '{self.id}' after {timeout}s.")
                if msg.get("error"):
                    err = msg["error"]
                    err_text = err.get("message", json.dumps(err))
                    if attempt == 1 and _looks_like_transient_studio_drop(err_text):
                        log(f"[{self.id}] {name}: transient Studio drop, retrying once...", "yl")
                        time.sleep(1.5)
                        continue
                    raise RuntimeError(err_text)
                content = msg.get("result", {}).get("content", [])
                text = "\n".join(it.get("text", "") for it in content if it.get("type") == "text")
                images = [{"data": it["data"], "mimeType": it.get("mimeType", "image/jpeg")}
                          for it in content if it.get("type") == "image" and it.get("data")]
                if not text and not images and content:
                    text = json.dumps(content)[:4000]
                # Studio's own MCP proxy briefly loses its binding to the Studio
                # app every few seconds on some machines (seen live: repeated
                # "Bound studio ... disconnected for proxy ..." stderr, self-
                # healing within ~1-4s). A tool call landing in that window
                # fails with a "no Studio instance connected" style message
                # even though Studio is genuinely open - confirmed live via
                # start_stop_play. One short retry rides through it instead of
                # surfacing a spurious error to the user.
                if attempt == 1 and _looks_like_transient_studio_drop(text):
                    log(f"[{self.id}] {name}: transient Studio drop, retrying once...", "yl")
                    time.sleep(1.5)
                    continue
                return {"text": text, "images": images, **({"isError": True} if msg.get("result", {}).get("isError") is True else {})}


# ══════════════════════════════════════════════════════════════════════════
#  MANAGER  - aggregates every MCP server, routes by tool name.
# ══════════════════════════════════════════════════════════════════════════
# ── Engine on/off switches (Settings → Engines) ───────────────────────────────
# A switched-off engine is PARKED: its MCP server is stopped and removed from the live
# set, so it is not launched, supervised, restarted, probed, advertised or callable
# until it is switched back on. The choice is saved next to the bridge and survives
# restarts of the bridge, the browser and the PC.
ENGINE_PREFS_PATH = os.path.join(HERE, "engine-prefs.json")
KNOWN_ENGINE_IDS = ("roblox", "unity", "godot", "blender", "figma")
ENGINE_LABELS = {"roblox": "Roblox Studio", "unity": "Unity", "godot": "Godot", "blender": "Blender", "figma": "Figma", "blockbench": "Blockbench assets"}


def _load_engine_prefs():
    """Set of engine ids the user has switched OFF on this machine.

    Roblox Studio has no Linux build. On Linux (unless the user pointed
    ZS_STUDIO_MCP_PATH at something) it starts switched off, so the console is not
    spammed with "open Roblox Studio" prompts and restart attempts that can never
    succeed. Settings -> Engines can still switch it on; that writes this file.

    The file records the OS it was written on. 6.28.x shipped an engine-prefs.json
    with Roblox ENABLED, which defeated the Linux auto-disable and produced a
    crash-loop - and the same shipped file also arrived with Unity, Godot and
    Blender switched off, hiding them from every new user. A file from another OS
    (or a legacy file with no OS recorded) is therefore not evidence about THIS
    machine, and must not be allowed to keep Roblox enabled here.
    """
    data = None
    try:
        with open(ENGINE_PREFS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        data = None
    ids = data.get("disabled") if isinstance(data, dict) else None
    disabled = {str(x) for x in ids if isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", x)} if isinstance(ids, list) else set()

    if sys.platform.startswith("linux") and not os.environ.get("ZS_STUDIO_MCP_PATH"):
        wrote_on = data.get("os") if isinstance(data, dict) else None
        if wrote_on != sys.platform and "roblox" not in disabled:
            disabled.add("roblox")
    return disabled


def _save_engine_prefs(disabled):
    try:
        tmp = ENGINE_PREFS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            # "os" is what lets _load_engine_prefs tell this machine's own choice
            # apart from a prefs file that arrived from somewhere else.
            json.dump({"os": sys.platform, "disabled": sorted(disabled)}, fh, indent=2)
        os.replace(tmp, ENGINE_PREFS_PATH)
        return True
    except Exception as exc:
        log(f"could not save engine preferences: {exc}", "yl")
        return False


def _engine_of_tool_name(name):
    if str(name).split("/")[-1].startswith("msrb_"):return "roblox"
    """Which engine a tool name belongs to by its ms_<engine>_ prefix, else None."""
    m = re.match(r"ms_(roblox|unity|godot|blender)_", str(name or ""))
    return m.group(1) if m else None


# Near-duplicate planners that stay CALLABLE but are no longer advertised: each one
# produced the same kind of checklist as the canonical tool beside it, and ~20 extra
# names in a ~120k-character catalogue only made models pick worse. Calling one still
# works and says which tool to prefer.
RETIRED_FROM_CATALOGUE = {
    "ms_performance_budget_designer": "ms_performance_budget_plan",
    "ms_performance_quality_audit": "ms_performance_budget_plan",
    "ms_memory_budget_optimizer": "ms_performance_budget_plan",
    "ms_asset_budget_optimizer": "ms_asset_budget",
    "ms_accessibility_validation": "ms_accessibility_audit",
    "ms_accessible_interface_polish": "ms_accessibility_audit",
    "ms_network_efficiency_optimizer": "ms_network_bandwidth_audit",
    "ms_cross_discipline_integration_review": "ms_cross_engine_integration_audit",
    "ms_release_quality_bar": "ms_release_checklist",
    "ms_production_readiness_director": "ms_release_checklist",
    "ms_studio_critic_loop": "ms_critic_review",
    "ms_result_evidence_synthesizer": "ms_critic_review",
    "ms_orchestrate_request": "ms_studio_director",
    "ms_activate_skill_stack": "ms_recommend_skills",
    "ms_workflow_plan": "ms_agent_plan_then_act",
    "ms_enhance_brief": "ms_prompt_rescue",
    "ms_context_budget_optimizer": "ms_tool_selection_optimizer",
    "ms_provider_execution_optimizer": "ms_tool_selection_optimizer",
    "ms_edge_case_generator": "ms_test_matrix",
    "ms_test_coverage_designer": "ms_test_matrix",
    "ms_texture_detail_polish": "ms_texture_art_pipeline",
}


# Guidance-only specialist wrappers are legacy aliases, not execution tools.
RETIRED_FROM_CATALOGUE.update({name: "ms_get_skill" for name in ADVANCED_DIRECT_CONTRACTS})
# Canonical replacements must themselves be discoverable, rather than pointing
# through another hidden alias. Existing alias calls remain backward compatible.
for _old_name in RETIRED_FROM_CATALOGUE:
    _replacement=RETIRED_FROM_CATALOGUE[_old_name];_seen={_old_name}
    while _replacement in RETIRED_FROM_CATALOGUE and _replacement not in _seen:
        _seen.add(_replacement);_replacement=RETIRED_FROM_CATALOGUE[_replacement]
    RETIRED_FROM_CATALOGUE[_old_name]=_replacement


class MCPManager:
    # Class-level defaults so a manager built without __init__ (tests, tooling)
    # behaves as "nothing switched off". __init__ replaces them per instance.
    disabled = frozenset()
    parked = {}
    parked_tools = {}

    def __init__(self):
        self.clients = {}          # server_id -> MCPClient
        self.index = {}            # advertised_name -> (holder, real_name)
        self.index_lock = threading.Lock()
        self.disabled = set()      # engine ids switched off by the user (saved)
        self.parked = {}           # server_id -> MCPClient that is switched off
        self.parked_tools = {}     # server_id -> tool names it had (to explain a refusal)
        self.specs = {}            # server_id -> its config.json entry (for per-server timeouts)

    def load_config(self):
        servers = _read_config().get("mcpServers", {}) or {}
        self.specs = dict(servers)
        for sid, spec in servers.items():
            self.clients[sid] = MCPClient(
                sid, spec.get("command"), spec.get("args"), spec.get("env"))
        self.disabled = _load_engine_prefs()
        for sid in list(self.clients):
            if sid in self.disabled:
                self.parked[sid] = self.clients.pop(sid)
        log(f"configured {len(self.clients)} MCP server(s): {', '.join(self.clients) or '(none)'}", "cy")
        if self.disabled:
            log(f"engines switched off in settings: {', '.join(sorted(self.disabled))}", "yl")

    def server_timeout(self, server_id, default):
        """Per-server timeout override, from `mcpServers.<id>.timeout_sec`.

        A large Unity project or a remote HTTP server can legitimately need far
        more than the default while every other server stays snappy. Optional and
        fully backwards compatible: absent or invalid -> the caller's default,
        exactly as before. Clamped to 1..3600 s so a typo cannot hang a call
        forever (or make it expire instantly).
        """
        try:
            entry = self.specs.get(str(server_id)) or {}
            raw = entry.get("timeout_sec")
            if raw is None:
                return default
            value = float(raw)
            if 1 <= value <= 3600:
                return value
        except (TypeError, ValueError):
            pass
        return default

    def engine_enabled(self, sid):
        return str(sid) not in self.disabled

    def engine_list(self):
        """[{id, label, enabled, configured, alive, tools}] for every known/configured engine."""
        ids = list(KNOWN_ENGINE_IDS)
        for sid in list(self.clients) + list(self.parked):
            if sid not in ids:
                ids.append(sid)
        out = []
        for sid in ids:
            c = self.clients.get(sid) or self.parked.get(sid)
            out.append({"id": sid, "label": ENGINE_LABELS.get(sid, sid), "enabled": self.engine_enabled(sid),
                        "configured": c is not None, "alive": bool(c and sid in self.clients and c.is_alive()),
                        "tools": len(c.tools_cache) if (c and sid in self.clients) else len(self.parked_tools.get(sid, ()))})
        if BLENDER_WORKSPACE.owns_target:
            row=next((r for r in out if r['id']=='blender'),None)
            if row is not None:row.update(configured=True,alive=BLENDER_WORKSPACE.running and self.engine_enabled('blender'),connected=bool(BLENDER_WORKSPACE.status()['verified']) and self.engine_enabled('blender'),tools=len(blender_workspace.NATIVE_NAMES),backend='headless-workspace',workspaceProject=BLENDER_WORKSPACE.project)
        return out

    def set_engine_enabled(self, sid, enabled):
        """Switch an engine on/off and save the choice. Blocking (stops/starts a process):
        call it from a worker thread. Returns {ok, engine, enabled, changed}."""
        sid = str(sid or "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", sid):
            return {"ok": False, "error": "invalid engine id"}
        enabled = bool(enabled)
        changed = (sid not in self.disabled) != enabled
        if enabled:
            self.disabled.discard(sid)
        else:
            self.disabled.add(sid)
        _save_engine_prefs(self.disabled)
        if enabled and sid in self.parked:
            client = self.parked.pop(sid)
            self.clients[sid] = client
            log(f"engine '{sid}' switched ON - starting its server", "gr")
            try:
                client.start()
            except Exception as e:
                log(f"[{sid}] failed to start: {e}", "rd")
            self.rebuild_index()
        elif not enabled and sid in self.clients:
            client = self.clients.pop(sid)
            self.parked[sid] = client
            self.parked_tools[sid] = {t.get("name") for t in (client.tools_cache or []) if t.get("name")}
            log(f"engine '{sid}' switched OFF - stopping its server", "yl")
            try:
                client.stop()
            except Exception as e:
                log(f"[{sid}] stop failed: {e}", "yl")
            self.rebuild_index()
        elif changed:
            log(f"engine '{sid}' switched {'ON' if enabled else 'OFF'} (no server is configured for it)", "yl")
        return {"ok": True, "engine": sid, "enabled": enabled, "changed": changed}

    def _disabled_reason(self, name):
        """If `name` belongs to a switched-off engine, the explanation; else ''."""
        eng = _engine_of_tool_name(name)
        if eng is None and _TOOLKIT is not None:
            try:
                if _TOOLKIT.is_toolkit_tool(name):
                    eng = _TOOLKIT.engine_of(name)
            except Exception:
                eng = None
        if eng is None and name in COMPANION_TOOL_NAMES:
            eng = "roblox"
        if eng is None:
            for sid, names in self.parked_tools.items():
                if sid in self.parked and name in names:
                    eng = sid
                    break
        if eng and eng in self.disabled:
            return (f"The {ENGINE_LABELS.get(eng, eng)} engine is switched OFF in Multi-Script (Settings -> Engines), "
                    f"so '{name}' is not available. Do not retry; tell the user to switch {ENGINE_LABELS.get(eng, eng)} on "
                    f"if they want it used.")
        return ""

    def start_all(self):
        # Launch every configured server IN PARALLEL, not one after another.
        # client.start() can block for up to ~12s (its own "wait for Studio's
        # tools to appear" grace loop) - with a sequential for-loop, Roblox
        # being first in config.json meant every OTHER server (Blender, any
        # addon) didn't even begin launching until Roblox's grace loop gave
        # up, even though that addon has nothing to do with Roblox and could
        # have been ready in 1-2s. A thread per client removes that
        # dependency entirely: a slow/absent Roblox Studio no longer holds up
        # an addon server the user actually wants right now.
        threads = []
        for sid, client in self.clients.items():
            if sid=='blender' and BLENDER_WORKSPACE.owns_target:continue
            def _run(sid=sid, client=client):
                try:
                    client.start()
                except Exception as e:
                    log(f"[{sid}] failed to start: {e}  (other servers continue)", "rd")
            t = threading.Thread(target=_run, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        self.rebuild_index()

    def rebuild_index(self):
        """Aggregate server tools. Collisions get a 'server/' prefix."""
        with self.index_lock:
            self.index = {}
            for sid, client in self.clients.items():
                for t in (client.tools_cache or []):
                    name = t.get("name")
                    if not name:
                        continue
                    advertised = name if name not in self.index else f"{sid}/{name}"
                    self.index[advertised] = (client, name)

    def refresh_stale(self):
        """Re-list tools for any server that sent tools/list_changed.

        Deliberately cheap: it only touches servers that actually raised the
        notification, so the normal path stays a pure cache read. Returns True
        when the index was rebuilt. Without this the notification would be
        recorded and then ignored, which is no better than dropping it.
        """
        changed = False
        for sid, client in list(self.clients.items()):
            if sid=='blender' and BLENDER_WORKSPACE.owns_target:continue
            if not getattr(client, "tools_stale", False):
                continue
            changed = True
            try:
                if client.is_alive():
                    client.refresh_tools()
                else:
                    client.start()
            except Exception as e:
                log(f"[{sid}] could not re-list tools after list_changed: {e}", "yl")
        if changed:
            self.rebuild_index()
        return changed

    def list_tools(self, refresh=False):
        self.refresh_stale()
        if refresh:
            for sid, client in self.clients.items():
                if sid=='blender' and BLENDER_WORKSPACE.owns_target:continue
                try:
                    if not client.is_alive():
                        # A launcher that reported a missing prerequisite
                        # (exit 78) is retried by server_watch every 10 min;
                        # a tools refresh must not respawn it every time.
                        if _needs_setup(client) and time.time() - getattr(client, "last_restart_at", 0.0) < 600:
                            continue
                        client.last_restart_at = time.time()
                        client.start()
                    else:
                        client.refresh_tools()
                except Exception as e:
                    log(f"[{sid}] refresh failed: {e}", "yl")
            self.rebuild_index()
        out = [dict(t, server="zeroscript") for t in BUILTIN_TOOLS
               if t.get("name") not in RETIRED_FROM_CATALOGUE
               and not (self.disabled and _engine_of_tool_name(t.get("name")) in self.disabled)]
        if ASSIST is not None:
            out.extend(dict(t, server="zeroscript") for t in ASSIST.DEFINITIONS)
        out.extend(t for t in _toolkit_visible_tools(self)
                   if not (self.disabled and _engine_of_tool_name(t.get("name")) in self.disabled))
        if _companion_execution_available() and "roblox" not in self.disabled:
            with plugin_state_lock:
                companion_mode = str(plugin_state.get("permissionMode") or "off")
            ceiling = PLUGIN_PERMISSION_RANK.get(companion_mode, 0)
            out.extend(
                dict(t, server="roblox-companion")
                for t in COMPANION_TOOLS
                if PLUGIN_PERMISSION_RANK.get(str(t.get("permission") or "full"), 3) <= ceiling and _companion_tool_enabled(t["name"])
            )
        for sid, client in self.clients.items():
            for t in (client.tools_cache or []):
                name = t.get("name")
                if sid=='blender' and BLENDER_WORKSPACE.owns_target:continue
                advertised = name
                with self.index_lock:
                    # find the advertised key that maps to this (client, name)
                    for k, (holder, real) in self.index.items():
                        if holder is client and real == name:
                            advertised = k
                            break
                tt = dict(t)
                tt["name"] = advertised
                tt["server"] = sid
                if sid=='blender' and BLENDER_WORKSPACE.owns_target and name=='get_viewport_screenshot':tt['description']='Headless Blender Workspace: return a genuine Cycles CPU render of the current scene, not a desktop viewport screenshot. Use it as render evidence; Three.js is the separate viewport preview.'
                out.append(tt)
        if BLENDER_WORKSPACE.owns_target and 'blender' not in self.disabled:
            used={t['name'] for t in out}
            for tool in blender_workspace.NATIVE_TOOLS:
                name=tool['name'] if tool['name'] not in used else 'blender/'+tool['name']
                out.append(dict(tool,name=name,server='blender',backend='headless-workspace'))
        # 6.36: every advertised schema - ours and the engines' live ones - is
        # normalised so function-calling providers never reject the list.
        if _SCHEMA_PERFECT is not None:
            try:
                out = [_SCHEMA_PERFECT.perfect_tool(t) for t in out]
            except Exception as exc:  # never let a normaliser bug hide tools
                log(f"schema normaliser skipped: {exc}", "yl")
        return out

    def call(self, name, arguments, timeout):
        """Timed wrapper: records latency/failures for ms_tool_stats, adds a steer
        for retired aliases, then dispatches."""
        t0 = time.time()
        try:
            res = self._dispatch(name, arguments, timeout)
        except Exception as exc:
            if ASSIST is not None and name not in ASSIST.NAMES:
                ASSIST.record(str(name), (time.time() - t0) * 1000.0, False, str(exc))
            _record_studio_call(self,name,False,time.time()-t0,str(exc))
            raise
        _record_studio_call(self,name,not (isinstance(res,dict) and res.get("isError")),time.time()-t0,res)
        if ASSIST is not None and name not in ASSIST.NAMES:
            ok = not (isinstance(res, dict) and res.get("isError"))
            ASSIST.record(str(name), (time.time() - t0) * 1000.0, ok, "" if ok else str(res.get("text", ""))[:200])
        if name in RETIRED_FROM_CATALOGUE and isinstance(res, dict):
            res = dict(res)
            res["text"] = (str(res.get("text") or "") + f"\n[note] '{name}' is retired from the catalogue; prefer '{RETIRED_FROM_CATALOGUE[name]}'.")
        return res

    def _dispatch(self, name, arguments, timeout):
        if self.disabled:
            why = self._disabled_reason(name)
            if why:
                raise RuntimeError(why)
        if ASSIST is not None and name in ASSIST.NAMES:
            clean, notes = _resilient_arguments(next(d["inputSchema"] for d in ASSIST.DEFINITIONS if d["name"] == name), arguments, name)
            host = _AssistHost(self)
            return _annotate_repairs(ASSIST.run(name, clean, self.list_tools(), host), notes)
        if _TOOLKIT is not None and name not in BUILTIN_TOOL_NAMES and _TOOLKIT.is_toolkit_tool(name):
            return _toolkit_call(name, arguments, self)
        if name in BUILTIN_TOOL_NAMES:
            if name == "ms_direct_tool_details":
                from tool_discovery import arguments as discovery_arguments
                arguments=discovery_arguments(arguments)
            tool = BUILTIN_TOOL_BY_NAME[name]
            # Same self-healing path as every other tool (stringified numbers/JSON,
            # key-case slips like "Feature", wrapper envelopes, enum case ...).
            # A clean call is validated strictly and passes through untouched.
            clean, notes = _resilient_arguments(tool.get("inputSchema"), arguments, name)
            return _annotate_repairs(_builtin_call(name, clean, self), notes)
        if name in COMPANION_TOOL_NAMES:
            tool = COMPANION_TOOL_BY_NAME[name]
            clean, notes = _resilient_arguments(tool.get("inputSchema"), arguments, name)
            return _annotate_repairs(_companion_call(name, clean, timeout), notes)
        if BLENDER_WORKSPACE.owns_target:
            native=name.removeprefix('blender/')
            with self.index_lock:entry=self.index.get(name)
            if native in blender_workspace.NATIVE_NAMES and (name.startswith('blender/') or entry is None or getattr(entry[0],'id',None)=='blender'):
                if 'blender' in self.disabled:raise RuntimeError('Blender is switched off in Engines settings.')
                schema=next(t['inputSchema'] for t in blender_workspace.NATIVE_TOOLS if t['name']==native)
                code_notes=[]
                if _repair is not None:
                    try:arguments,code_notes=_repair.repair_code_arguments(native,arguments)
                    except Exception:pass
                clean,notes=_resilient_arguments(schema,arguments,name)
                return _annotate_repairs(BLENDER_WORKSPACE.native_call(native,clean,timeout),list(code_notes)+list(notes))
        with self.index_lock:
            entry = self.index.get(name)
        if entry is None:
            # Maybe a freshly added tool - rebuild once and retry.
            self.rebuild_index()
            with self.index_lock:
                entry = self.index.get(name)
        if entry is None:
            raise RuntimeError(f"unknown tool '{name}'")
        holder, real_name = entry
        schema = next((t.get("inputSchema") for t in (holder.tools_cache or []) if t.get("name") == real_name), None)
        # Script-transfer repair: double-escaped \n, code fences, ###LUA### markers, line arrays.
        code_notes = []
        if _repair is not None:
            try:
                arguments, code_notes = _repair.repair_code_arguments(real_name, arguments)
            except Exception:
                code_notes = []
        clean, notes = _resilient_arguments(schema, arguments, name)
        notes = list(code_notes) + list(notes)
        # A per-server override (mcpServers.<id>.timeout_sec) lets one slow server
        # get more room without raising the timeout for all of them.
        eff_timeout = self.server_timeout(getattr(holder, "id", None), timeout)
        if getattr(holder,'id',None)=='blender' and BLENDER_WORKSPACE.owns_target:return _annotate_repairs(BLENDER_WORKSPACE.native_call(real_name,clean,eff_timeout),notes)
        return _annotate_repairs(holder.call_tool(real_name, clean, eff_timeout), notes)

    def list_server_tools(self, server_id, refresh=False):
        if server_id=='blender' and BLENDER_WORKSPACE.owns_target:
            if server_id in self.disabled:raise RuntimeError('Blender is switched off in Engines settings.')
            return [dict(t,backend='headless-workspace') for t in blender_workspace.NATIVE_TOOLS]
        client = self._client(server_id)
        if refresh:
            if not client.is_alive(): client.start()
            else: client.refresh_tools()
            self.rebuild_index()
        return [dict(t) for t in (client.tools_cache or [])]

    def smoke_test(self, server_id, tool_name=None, arguments=None):
        if server_id=='blender' and BLENDER_WORKSPACE.owns_target:
            if server_id in self.disabled:raise RuntimeError('Blender is switched off in Engines settings.')
            tool_name=tool_name or 'get_scene_info'
            result=BLENDER_WORKSPACE.native_call(tool_name,arguments or {},30)
            return {'server':server_id,'connected':True,'nativeToolCount':len(blender_workspace.NATIVE_NAMES),'testedTool':tool_name,'result':result.get('text','')[:4000],'images':len(result.get('images') or []),'verified':True,'backend':'headless-workspace','workspaceProject':BLENDER_WORKSPACE.project}
        client=self._client(server_id)
        if not client.is_alive(): raise RuntimeError(f"server '{server_id}' is offline")
        names={t.get("name") for t in (client.tools_cache or [])}
        defaults={
            "roblox":[("get_studio_state",{}), ("search_game_tree",{"query":"Workspace"})],
            "unity":[("manage_editor",{"action":"get_state"}), ("read_console",{"action":"get"})],
            "godot":[("get_godot_version",{}), ("get_project_info",{})],
            "blender":[("get_scene_info",{}), ("get_current_scene",{})],
        }
        if tool_name:
            candidates=[(str(tool_name),arguments or {})]
        else:
            candidates=defaults.get(server_id,[])
            if not candidates and names: candidates=[(sorted(n for n in names if n)[0],arguments or {})]
        chosen=next(((n,a) for n,a in candidates if n in names),None)
        if not chosen: raise RuntimeError(f"server '{server_id}' has no supported read-only smoke-test tool; choose one with the tool parameter")
        n,a=chosen;result=client.call_tool(n,a,30)
        if result.get('isError') or re.search(r'could not connect to blender|connection refused|failed to connect',str(result.get('text','')),re.I):raise RuntimeError(str(result.get('text') or 'The engine connection test failed.'))
        return {"server":server_id,"connected":True,"nativeToolCount":len(names),"testedTool":n,"result":result.get("text","")[:4000],"images":len(result.get("images") or []),"verified":True}

    def call_on_server(self, server_id, tool_name, arguments, timeout=120, use_workspace=True):
        if server_id=='blender' and BLENDER_WORKSPACE.owns_target and use_workspace:
            if server_id in self.disabled:raise RuntimeError('Blender is switched off in Engines settings.')
            return BLENDER_WORKSPACE.native_call(tool_name,arguments,timeout)
        client = self._client(server_id)
        advertised = {t.get("name") for t in (client.tools_cache or [])}
        if tool_name not in advertised:
            raise RuntimeError(f"server '{server_id}' does not advertise tool '{tool_name}'")
        schema = next((t.get("inputSchema") for t in (client.tools_cache or []) if t.get("name") == tool_name), None)
        clean, notes = _resilient_arguments(schema, arguments, f"{server_id}/{tool_name}")
        return _annotate_repairs(client.call_tool(tool_name, clean, timeout), notes)

    def _client(self, server_id):
        client = self.clients.get(server_id)
        if client is None:
            raise RuntimeError(f"unknown MCP server '{server_id}'")
        return client

    def list_resources(self, server_id, cursor=None):
        return self._client(server_id).list_resources(cursor=cursor)

    def read_resource(self, server_id, uri):
        return self._client(server_id).read_resource(uri)

    def restart(self, server_id=None):
        if server_id=='blender' and BLENDER_WORKSPACE.owns_target:
            if not self.engine_enabled('blender'):raise RuntimeError('Blender is switched off in Engines settings.')
            BLENDER_WORKSPACE.submit('ensure',{'project':BLENDER_WORKSPACE.project});return
        targets = [self.clients[server_id]] if server_id and server_id in self.clients else list(self.clients.values())
        for client in targets:
            if client.id=='blender' and BLENDER_WORKSPACE.owns_target:continue
            try:
                client.restart()
            except Exception as e:
                log(f"[{client.id}] restart failed: {e}", "rd")
        self.rebuild_index()

    def health(self):
        # Built-ins are always available but are not an external MCP connection;
        # excluding them keeps the UI from claiming an engine is online when only
        # Multi-Script's local helper tools are available.
        rows=[{"id": sid, "alive": c.is_alive(), "tools": len(c.tools_cache), "enabled": True}
                for sid, c in self.clients.items()] + \
               [{"id": sid, "alive": False, "tools": 0, "enabled": False} for sid in self.parked]
        if BLENDER_WORKSPACE.owns_target and 'blender' not in self.disabled:
            row=next((r for r in rows if r['id']=='blender'),None)
            if row is None:row={'id':'blender','enabled':True,'tools':0};rows.append(row)
            row.update(alive=BLENDER_WORKSPACE.running,tools=len(blender_workspace.NATIVE_NAMES),workspace=True,backend='headless-workspace',workspaceProject=BLENDER_WORKSPACE.project)
        return rows

    def any_alive(self):
        return any(c.is_alive() for c in self.clients.values()) or BLENDER_WORKSPACE.selected and 'blender' not in self.disabled


# ══════════════════════════════════════════════════════════════════════════
#  WEBSOCKET SERVER
# ══════════════════════════════════════════════════════════════════════════
mgr = MCPManager()
clients = set()
plugin_state_lock = threading.Lock()
plugin_state = {
    "lastSeen": None,
    "executionLastSeen": None,
    "pluginVersion": None,
    "executionEnabled": False,
    "permissionMode": "off",
}
plugin_job_queue = queue.Queue(maxsize=32)
plugin_pending_lock = threading.Lock()
plugin_pending = {}
import plugin_console

PLUGIN_PERMISSION_RANK = {"off": 0, "read": 1, "project": 2, "full": 3}


def _companion_tool_enabled(name):
    with plugin_state_lock:
        selected=plugin_state.get("enabledTools")
    return selected is None or name in selected

def _record_studio_call(manager,name,ok,elapsed,result):
    if name in {"msrb_console_read","ms_direct_tool_details"}: return
    entry=manager.index.get(name) if hasattr(manager,"index") else None
    if name in COMPANION_TOOL_NAMES or name.startswith("ms_roblox_") or (entry and getattr(entry[0],"id",None)=="roblox"):
        tier=COMPANION_TOOL_BY_NAME.get(name,{}).get("permission","full")
        text=result.get("text","") if isinstance(result,dict) else str(result)
        try:
            payload=json.loads(text)
            if isinstance(payload,dict) and payload.get("ok") is False:ok=False
        except (ValueError,TypeError):pass
        plugin_console.record(name,ok,elapsed,text,tier)

def _large_companion_source(arguments,timeout):
    source=str(arguments.get("source") or "");raw=source.encode("utf-8")
    if len(raw)>4194304:raise RuntimeError("Source exceeds 4 MiB. Split the implementation into ModuleScripts; source was not clipped or changed.")
    if not _companion_tool_enabled("msrb_source_transfer"):raise RuntimeError("Enable msrb_source_transfer in the Studio toolset to write large sources; nothing was changed.")
    def call(args):
        result=_companion_call("msrb_source_transfer",args,timeout)
        return json.loads(result["text"])
    state=call({"action":"begin","path":arguments.get("path"),"total_bytes":len(raw)})
    transfer=state["transfer_id"];offset=0;deadline=time.monotonic()+max(5,min(timeout or 120,180))
    while offset<len(raw):
        if time.monotonic()>deadline:raise TimeoutError("Source staging timed out before commit; project source was not changed. Transfer: "+transfer)
        end=min(len(raw),offset+32768)
        while end<len(raw) and raw[end]&0xC0==0x80:end-=1
        chunk=raw[offset:end].decode("utf-8")
        call({"action":"append","transfer_id":transfer,"offset":offset,"source":chunk});offset=end
    try: result=call({"action":"commit","transfer_id":transfer})
    except Exception as error:raise RuntimeError("Source commit outcome needs confirmation. Read msrb_source_transfer action=status transfer_id="+transfer+" before retrying. "+str(error)) from error
    result["transport"]="staged UTF-8 source; one atomic editor commit"
    return {"text":json.dumps(result),"images":[]}

def _companion_execution_available():
    with plugin_state_lock:
        state = dict(plugin_state)
    return bool(
        state.get("executionEnabled") and
        state.get("sessionToken") and
        state.get("executionLastSeen") and
        time.time() - float(state.get("executionLastSeen")) < 20
    )


def _companion_authorized(headers):
    token = str(headers.get("authorization") or "")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    with plugin_state_lock:
        expected = str(plugin_state.get("sessionToken") or "")
    return bool(expected and token and secrets.compare_digest(token, expected))


def _cancel_companion_pending(reason):
    with plugin_pending_lock:
        slots = list(plugin_pending.values())
        plugin_pending.clear()
    for slot in slots:
        slot["result"] = {"ok": False, "error": str(reason)[:500]}
        slot["event"].set()


def _companion_call(name, arguments, timeout=120):
    tool = COMPANION_TOOL_BY_NAME.get(name)
    if not tool:
        raise RuntimeError(f"unknown companion tool '{name}'")
    with plugin_state_lock:
        state = dict(plugin_state)
    if not _companion_execution_available():
        raise RuntimeError("Roblox companion execution is offline. Open its Studio widget and explicitly enable elevated tools.")
    required = str(tool.get("permission") or "read")
    mode = str(state.get("permissionMode") or "off")
    if PLUGIN_PERMISSION_RANK.get(mode, 0) < PLUGIN_PERMISSION_RANK.get(required, 1):
        raise RuntimeError(f"{name} needs companion permission '{required}', but Studio is set to '{mode}'. Raise it in the plugin widget and retry.")
    if not _companion_tool_enabled(name):raise RuntimeError(name+" is disabled in the Studio plugin Toolset tab.")
    if name=="msrb_replace_script" and len(str(arguments.get("source") or "").encode("utf-8"))>32768:
        return _large_companion_source(arguments,timeout)
    job_id = uuid.uuid4().hex
    waiter = threading.Event()
    slot = {"event": waiter, "result": None}
    with plugin_pending_lock:
        plugin_pending[job_id] = slot
    job = {
        "id": job_id,
        "tool": name,
        "arguments": arguments or {},
        "permission": required,
        "createdAt": time.time(),
    }
    try:
        plugin_job_queue.put(job, timeout=1)
        wait_seconds = max(1, min(int(timeout or 120), 180))
        if not waiter.wait(wait_seconds):
            raise TimeoutError(f"Roblox companion did not finish {name} within {wait_seconds}s")
        result = slot.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Roblox companion returned an invalid result")
        if result.get("ok") is not True:
            raise RuntimeError(str(result.get("error") or f"{name} failed in Studio")[:2000])
        payload = result.get("data")
        text = result.get("text")
        if text is None:
            text = json.dumps(payload if payload is not None else {"ok": True}, indent=2)
        return {"text": str(text)[:1_000_000], "images": []}
    finally:
        with plugin_pending_lock:
            plugin_pending.pop(job_id, None)


def _plugin_status_payload(studio=None):
    studio = studio or {"app": None, "place": None}
    roblox = mgr.clients.get(PRIMARY_SERVER_ID)
    with plugin_state_lock:
        companion = dict(plugin_state)
    companion.pop("sessionToken", None)
    companion.pop("executionLastSeen", None)
    companion["connected"] = bool(companion.get("lastSeen") and time.time() - float(companion["lastSeen"]) < 20)
    return {
        "product": "Multi-Script",
        "bridgeVersion": BRIDGE_VERSION,
        "roblox": {
            "alive": bool(roblox and roblox.is_alive()),
            "connected": studio.get("place"),
            "studioApp": studio.get("app"),
            "nativeTools": len(roblox.tools_cache) if roblox else 0,
        },
        "directTools": len(BUILTIN_TOOLS),
        "engineToolkit": (_TOOLKIT.counts() if _TOOLKIT is not None else {}),
        "companionTools": len(COMPANION_TOOLS),
        "skills": len(_load_skills()),
        "virtualTools": len(_load_virtual_tools()),
        "robloxSkills": sum(1 for v in _load_skills().values() if v.get("engine") == "roblox"),
        "robloxVirtualTools": sum(1 for v in _load_virtual_tools().values() if v.get("engine") == "roblox"),
        "nativeCountExplanation": "Official native tools, Multi-Script direct tools, and opt-in companion-plugin tools are separate surfaces and are counted separately.",
        "companionPlugin": companion,
    }


def _media_unavailable():
    return (503, json.dumps({
        "error": "the media relay is unavailable in this bridge build",
        "detail": MEDIA_RELAY_ERROR,
    }).encode("utf-8"))


def _handle_media_request(method, path, request_body):
    """Media-relay routes. Returns (status, body_bytes).

    Route table (all loopback, no auth token - see the note below):
      GET    /media/stats              -> policy + current spool usage
      GET    /media/list               -> staged items (descriptors only)
      POST   /media/stage              -> {name, mime, dataUrl|base64} -> descriptor
      POST   /media/prepare            -> {id} -> payloads + manifest
      POST   /media/release            -> {id} (or {} for all) -> {released}
      POST   /media/clear              -> drop everything

    Auth note: this port is bound to 127.0.0.1 only (see the HOST constant), so
    reachability IS the authorisation, exactly like the WebSocket path the
    extension already uses. A hostile page cannot reach 127.0.0.1:PLUGIN_PORT
    without already running on this machine, and the relay writes only into its
    own spool under a generated id - there is no path a caller can steer.
    """
    if MEDIA_RELAY is None:
        return _media_unavailable()
    route = path.rstrip("/")
    try:
        if method == "GET" and route == "/media/stats":
            return (200, json.dumps(MEDIA_RELAY.stats()).encode("utf-8"))
        if method == "GET" and route == "/media/list":
            return (200, json.dumps({"items": MEDIA_RELAY.list_items()}).encode("utf-8"))

        payload = json.loads(request_body.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")

        if method == "POST" and route == "/media/stage":
            data = _media.decode_chunk(payload.get("dataUrl") or payload.get("base64") or "")
            if not data:
                raise ValueError("no media bytes were provided")
            item = MEDIA_RELAY.stage(data, payload.get("name") or "", payload.get("mime") or "")
            return (200, json.dumps({"ok": True, "item": item}).encode("utf-8"))

        if method == "POST" and route == "/media/prepare":
            item_id = str(payload.get("id") or "").strip()
            if not item_id:
                raise ValueError("an id is required")
            return (200, json.dumps({"ok": True, "prepared": MEDIA_RELAY.prepare(item_id)}).encode("utf-8"))

        if method == "POST" and route == "/media/release":
            item_id = str(payload.get("id") or "").strip()
            if item_id:
                return (200, json.dumps({"ok": True, "released": 1 if MEDIA_RELAY.release(item_id) else 0}).encode("utf-8"))
            before = len(MEDIA_RELAY.list_items())
            MEDIA_RELAY.release_all()
            return (200, json.dumps({"ok": True, "released": before}).encode("utf-8"))

        if method == "POST" and route == "/media/clear":
            before = len(MEDIA_RELAY.list_items())
            MEDIA_RELAY.release_all()
            return (200, json.dumps({"ok": True, "released": before}).encode("utf-8"))

        return (404, b'{"error":"not found"}')
    except _media.RelayError as exc:
        # A refusal the user can act on - a 400, not a 500, and the message is
        # forwarded verbatim so the panel can show it as-is.
        return (400, json.dumps({"error": str(exc)}).encode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        return (400, json.dumps({"error": str(exc)}).encode("utf-8"))
    except Exception as exc:
        return (500, json.dumps({"error": type(exc).__name__}).encode("utf-8"))


async def plugin_http_handler(reader, writer):
    """Tiny loopback-only HTTP surface for the Roblox Studio companion plugin
    and for the media relay.

    Companion execution is opt-in, allowlisted, permission-tiered, and protected
    by a short-lived in-memory bearer token. Jobs can only enter through the
    existing extension-to-bridge tool channel; this HTTP surface has no enqueue
    endpoint and never exposes arbitrary code evaluation.

    The media endpoints are the ONE place the bridge accepts a large body. The
    relay's job is to receive a photo or a clip the user dropped and hand it
    back as clipboard-pasteable payloads, so its cap is set from the relay's own
    policy rather than the plugin's 64 KB. Everything else stays tiny, so a
    malformed/oversized non-media request is refused before a byte is buffered.
    """
    status, body = 200, b""
    try:
        raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=3)
        if len(raw) > 32768:
            raise ValueError("headers too large")
        header_text = raw.decode("iso-8859-1", "replace")
        lines = header_text.split("\r\n")
        parts = lines[0].split()
        if len(parts) != 3:
            raise ValueError("invalid request line")
        method, path, _ = parts
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        length = int(headers.get("content-length", "0") or 0)
        route = urlsplit(path).path.rstrip("/") or "/"
        is_media = route.startswith("/media/")
        # A staged item is base64 in transit, which inflates it by 4/3, plus the
        # JSON envelope. headroom covers that without letting a caller claim
        # more than the relay would ever accept.
        if is_media and MEDIA_RELAY is not None:
            media_cap = int(_media.MAX_ITEM_BYTES * 4 / 3) + 65536
        else:
            media_cap = 65536
        cap = max(65536, media_cap) if is_media else (2_000_000 if route=="/plugin/result" and _companion_authorized(headers) else 65536)
        if length < 0 or length > cap:
            status, body = 413, json.dumps({
                "error": "payload too large",
                "limitBytes": cap,
            }).encode("utf-8")
        else:
            # Media bodies can be tens of MB over loopback; the plugin's 3 s
            # budget would truncate a normal photo on a busy machine, so media
            # gets a longer, still-bounded read.
            read_timeout = 60 if is_media else 3
            request_body = await asyncio.wait_for(reader.readexactly(length), timeout=read_timeout) if length else b""
            if method == "GET" and route == "/status":
                studio = await asyncio.to_thread(probe_studio)
                body = json.dumps(_plugin_status_payload(studio)).encode("utf-8")
            elif method == "GET" and route == "/logs":
                # The in-extension terminal's fallback channel. The panel normally
                # follows the log over the WebSocket (which pushes); this exists so
                # the panel still works, and can still prove the bridge is alive,
                # on the HTTP surface the extension already has permission to
                # reach. Loopback-only, read-only, and it exposes nothing but the
                # same lines the console prints.
                q = urlsplit(path)
                try:
                    since = int((dict(
                        kv.split("=", 1) for kv in (q.query or "").split("&") if "=" in kv
                    )).get("since", "0"))
                except Exception:
                    since = 0
                lines, newest = log_since(since, 400)
                body = json.dumps({
                    "ok": True, "lines": lines, "newest": newest,
                    "service": _service_snapshot(),
                }).encode("utf-8")
            elif method == "GET" and route == "/diagnostics":
                # One-shot health report: version, ports, per-server state, the
                # environment probe, which engines are off on this machine, the
                # catalogue sizes and the log tail. Read-only, loopback-only.
                # Exists so a support question ("why is Unity down?") can be
                # answered from one request instead of a console screenshot.
                body = json.dumps(_bridge_diagnostics()).encode("utf-8")
            elif method == "GET" and route == "/catalog":
                roblox = mgr.clients.get(PRIMARY_SERVER_ID)
                tools = [dict(t) for t in (roblox.tools_cache or [])] if roblox else []
                body = json.dumps({"server":"roblox","nativeToolCount":len(tools),"tools":tools,"multiScriptDirectTools":len(BUILTIN_TOOLS),"companionPluginTools":len(COMPANION_TOOLS),"robloxVirtualTools":sum(1 for v in _load_virtual_tools().values() if v.get("engine")=="roblox"),"robloxSkills":sum(1 for v in _load_skills().values() if v.get("engine")=="roblox"),"explanation":"The native count is the exact official Studio MCP catalogue. Multi-Script direct, companion, virtual, and skill capabilities are separate; companion tools appear only after explicit plugin authorization."}).encode("utf-8")
            elif is_media:
                status, body = _handle_media_request(method, path, request_body)
            elif method == "POST" and route == "/plugin/register":
                data = json.loads(request_body.decode("utf-8") or "{}")
                if not isinstance(data, dict):
                    raise ValueError("registration must be an object")
                mode = str(data.get("permissionMode") or "off").lower()
                if data.get("executionEnabled") is not True or mode not in ("read", "project", "full"):
                    status, body = 400, b'{"error":"explicit execution permission is required"}'
                else:
                    selected=data.get("enabledTools")
                    if selected is not None and (not isinstance(selected,list) or any(not isinstance(n,str) or n not in COMPANION_TOOL_NAMES for n in selected)):
                        raise ValueError("enabledTools must be a list of exact companion tool names")
                    _cancel_companion_pending("Roblox companion permission session changed")
                    token = secrets.token_urlsafe(32)
                    with plugin_state_lock:
                        plugin_state.update({
                            "sessionToken": token,
                            "executionEnabled": True,
                            "permissionMode": mode,
                            "enabledTools": selected,
                            "pluginVersion": str(data.get("pluginVersion") or "")[:24],
                            "pluginId": str(data.get("pluginId") or "")[:80],
                            "lastSeen": time.time(),
                            "executionLastSeen": time.time(),
                        })
                    body = json.dumps({
                        "ok": True,
                        "token": token,
                        "permissionMode": mode,
                        "toolCount": sum(
                            1 for tool in COMPANION_TOOLS
                            if PLUGIN_PERMISSION_RANK.get(str(tool.get("permission") or "full"), 3)
                            <= PLUGIN_PERMISSION_RANK[mode]
                            and (selected is None or tool["name"] in selected)
                        ),
                        "pollAfterMs": 350,
                    }).encode("utf-8")
            elif method == "POST" and route == "/plugin/toolset":
                if not _companion_authorized(headers):status,body=403,b'{"error":"invalid companion token"}'
                else:
                    data=json.loads(request_body.decode("utf-8") or "{}");selected=data.get("enabledTools")
                    if not isinstance(selected,list) or any(not isinstance(n,str) or n not in COMPANION_TOOL_NAMES for n in selected):raise ValueError("Use exact companion tool names")
                    with plugin_state_lock:plugin_state["enabledTools"]=list(dict.fromkeys(selected))
                    body=b'{"ok":true}'
            elif method == "GET" and route == "/plugin/console":
                if not _companion_authorized(headers):status,body=403,b'{"error":"invalid companion token"}'
                else:
                    with plugin_state_lock: mode=plugin_state.get("permissionMode","off")
                    body=json.dumps(plugin_console.snapshot(mode)).encode("utf-8")
            elif method == "GET" and route == "/plugin/next":
                if not _companion_authorized(headers):
                    status, body = 403, b'{"error":"invalid or expired companion token"}'
                else:
                    job = None
                    while True:
                        try:
                            candidate = plugin_job_queue.get_nowait()
                        except queue.Empty:
                            break
                        with plugin_pending_lock:
                            still_pending = candidate.get("id") in plugin_pending
                        if still_pending and not _companion_tool_enabled(candidate.get("tool")):
                            with plugin_pending_lock: slot=plugin_pending.get(candidate.get("id"))
                            if slot:slot["result"]={"ok":False,"error":"Tool disabled before dispatch in Studio"};slot["event"].set()
                            continue
                        if still_pending and time.time() - float(candidate.get("createdAt") or 0) <= 185:
                            job = candidate
                            break
                    with plugin_state_lock:
                        plugin_state["lastSeen"] = time.time()
                        plugin_state["executionLastSeen"] = time.time()
                    body = json.dumps({"ok": True, "job": job}).encode("utf-8")
            elif method == "POST" and route == "/plugin/result":
                if not _companion_authorized(headers):
                    status, body = 403, b'{"error":"invalid or expired companion token"}'
                else:
                    data = json.loads(request_body.decode("utf-8") or "{}")
                    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
                        raise ValueError("result must contain a job id")
                    with plugin_pending_lock:
                        slot = plugin_pending.get(data["id"])
                    if slot is None:
                        status, body = 404, b'{"error":"unknown or expired job"}'
                    else:
                        slot["result"] = data.get("result")
                        slot["event"].set()
                        with plugin_state_lock:
                            plugin_state["lastSeen"] = time.time()
                            plugin_state["executionLastSeen"] = time.time()
                        body = b'{"ok":true}'
            elif method == "POST" and route == "/plugin/unregister":
                if not _companion_authorized(headers):
                    status, body = 403, b'{"error":"invalid or expired companion token"}'
                else:
                    _cancel_companion_pending("Roblox companion execution was disabled in Studio")
                    with plugin_state_lock:
                        plugin_state.pop("sessionToken", None)
                        plugin_state["executionEnabled"] = False
                        plugin_state["permissionMode"] = "off"
                        plugin_state["lastSeen"] = time.time()
                        plugin_state["executionLastSeen"] = None
                    body = b'{"ok":true}'
            elif method == "POST" and route == "/plugin/heartbeat":
                data = json.loads(request_body.decode("utf-8") or "{}")
                if not isinstance(data, dict):
                    raise ValueError("heartbeat must be an object")
                def _hb_text(key, limit=120):
                    value = data.get(key)
                    return str(value)[:limit] if value is not None else None
                def _hb_int(key, low=0, high=10_000_000):
                    try: return max(low, min(high, int(data.get(key) or 0)))
                    except (TypeError, ValueError): return 0
                allowed = {
                    "pluginVersion": _hb_text("pluginVersion", 24),
                    "diagnosticVersion": _hb_int("diagnosticVersion", 0, 1000),
                    "placeId": _hb_int("placeId", 0, 10**15),
                    "placeName": _hb_text("placeName", 120),
                    "isRunning": data.get("isRunning") is True,
                    "selectionCount": _hb_int("selectionCount", 0, 100_000),
                    "scriptCount": _hb_int("scriptCount", 0, 10_000_000),
                    "moduleCount": _hb_int("moduleCount", 0, 10_000_000),
                    "readinessScore": _hb_int("readinessScore", 0, 100),
                    "issueCount": _hb_int("issueCount", 0, 100),
                    "highIssueCount": _hb_int("highIssueCount", 0, 100),
                    "scanDurationMs": _hb_int("scanDurationMs", 0, 3_600_000),
                }
                allowed["lastSeen"] = time.time()
                with plugin_state_lock:
                    session = {
                        key: plugin_state.get(key)
                        for key in ("sessionToken", "executionEnabled", "permissionMode", "pluginId", "executionLastSeen", "enabledTools")
                        if plugin_state.get(key) is not None
                    }
                    plugin_state.clear()
                    plugin_state.update(allowed)
                    plugin_state.update(session)
                body = b'{"ok":true}'
            else:
                status, body = 404, b'{"error":"not found"}'
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError, ValueError, json.JSONDecodeError) as e:
        status, body = 400, json.dumps({"error": str(e)}).encode("utf-8")
    except Exception as e:
        status, body = 500, json.dumps({"error": type(e).__name__}).encode("utf-8")
    reason = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 413: "Payload Too Large", 500: "Internal Server Error"}.get(status, "Error")
    response = (f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json; charset=utf-8\r\n"
                f"Content-Length: {len(body)}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n").encode("ascii") + body
    writer.write(response)
    try:
        await writer.drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

# ── Studio connectivity probe ──────────────────────────────────────────────
# The MCP server process stays alive even when Roblox Studio is closed or its
# MCP option is disabled - tool calls then return instantly with an "Unable to
# find an active Studio instance" text. So "mcp_alive" alone is misleading.
#
# TWO LEVELS (validated live 2026-06):
#  - list_roblox_studios: instant, side-effect-free. studios == [] means NO Studio
#    is connected to the MCP (app closed, OR its "Studio as MCP Server" option is
#    disabled - the two are indistinguishable at this layer). A non-empty list
#    means a Studio app IS connected, BUT note its entry stays present (active:true)
#    even when no place is open - only its "name" goes null. So presence != usable.
#  - get_studio_state: tells whether a PLACE is actually loaded. With a place open
#    it returns "Available DataModels: ..."; with the Studio on the home screen (or
#    the active place closed) it returns "...doesn't have a place opened / previously
#    active Studio has disconnected". That is the authoritative "place loaded" signal
#    (same phrase the call path already recognises in core/main.js).
STUDIO_PROBE_TOOL = "list_roblox_studios"
STUDIO_STATE_TOOL = "get_studio_state"
# Substrings get_studio_state emits when a Studio is connected but no place is open.
NO_PLACE_MARKERS = ("doesn't have a place", "no place opened", "place opened",
                    "has disconnected", "no active studio")


def _probe_tool_text(tool):
    """Call a side-effect-free probe tool with no args; return its text, or None if
    the tool is unavailable / the server is busy / it errored (best-effort)."""
    with mgr.index_lock:
        entry = mgr.index.get(tool)
    if entry is None:
        return None
    holder, real_name = entry
    # Never queue behind a long-running tool call (the probe is best-effort).
    if not holder.call_lock.acquire(blocking=False):
        return None
    try:
        if not holder.is_alive():
            return None
        msg = holder._request("tools/call", {"name": real_name, "arguments": {}}, timeout=8)
        if not msg or msg.get("error"):
            return None
        content = msg.get("result", {}).get("content", [])
        return "\n".join(it.get("text", "") for it in content if it.get("type") == "text")
    except Exception:
        return None
    finally:
        holder.call_lock.release()


def probe_studio():
    """Two-level Studio connectivity. Returns {"app": x, "place": y} where each is
    True / False / None (None = unknown: probe tool missing or server busy).
      app   - a Roblox Studio instance is connected to the MCP server. False = Studio
              closed OR its MCP-server option disabled (indistinguishable here).
      place - a place/datamodel is actually loaded and usable. False = Studio open on
              the home screen, or the active place was closed. Only meaningful when
              app is True (when app is False/None, place mirrors it)."""
    roblox = mgr.clients.get(PRIMARY_SERVER_ID)
    if roblox is not None and roblox.is_alive() and not roblox.tools_cache:
        # StudioMCP advertises ZERO tools - including list_roblox_studios itself -
        # until Studio actually attaches. That makes _probe_tool_text() below
        # return None (tool missing) the same way it would for a genuinely
        # transient "probe busy" blip, even though "Studio is simply closed" is
        # the common, SUSTAINED case here, not a blip. Left unhandled, the
        # extension's "unknown = don't degrade" rule (by design, for real
        # transient blips) then leaves the status dot stuck GREEN forever with
        # Studio fully closed (seen live 2026-07-11: dot stayed "on", tooltip
        # showing only an addon server's tool count). An alive client with an
        # empty catalogue is an unambiguous "not connected", so short-circuit
        # straight to that verdict instead of falling through to "unknown".
        return {"app": False, "place": False}
    text = _probe_tool_text(STUDIO_PROBE_TOOL)
    if text is None:
        return {"app": None, "place": None}
    try:
        studios = json.loads(text).get("studios") or []
    except Exception:
        return {"app": None, "place": None}
    if not studios:
        return {"app": False, "place": False}
    # A Studio app is connected - now check whether a place is actually open.
    state = _probe_tool_text(STUDIO_STATE_TOOL)
    if state is None:
        return {"app": True, "place": None}
    low = state.lower()
    place = not any(m in low for m in NO_PLACE_MARKERS)
    return {"app": True, "place": place}


def probe_unity():
    """Best-effort check for a live Unity Editor via the official instances resource."""
    client = mgr.clients.get("unity")
    if client is None or not client.is_alive() or not client.tools_cache:
        return False
    if not client.call_lock.acquire(blocking=False):
        return None
    try:
        msg = client._request("resources/read", {"uri": "mcpforunity://instances"}, timeout=6)
        if not msg or msg.get("error"):
            return None
        texts = [str(x.get("text", "")) for x in msg.get("result", {}).get("contents", []) if x.get("text") is not None]
        payload = "\n".join(texts)
        try:
            data = json.loads(payload)
            return bool(data.get("instance_count", len(data.get("instances", []))))
        except Exception:
            low = payload.lower()
            if '"instance_count": 0' in low or '"instances": []' in low:
                return False
            return True if "unity" in low and ("instance" in low or "project" in low) else None
    except Exception:
        return None
    finally:
        client.call_lock.release()


def probe_godot():
    """Side-effect-free Godot readiness check via Coding-Solo get_godot_version."""
    client = mgr.clients.get("godot")
    if client is None or not client.is_alive() or not client.tools_cache: return False
    if not client.call_lock.acquire(blocking=False): return None
    try:
        msg = client._request("tools/call", {"name": "get_godot_version", "arguments": {}}, timeout=8)
        if not msg or msg.get("error"): return False
        text = "\n".join(x.get("text", "") for x in msg.get("result", {}).get("content", []) if x.get("type") == "text")
        return False if any(x in text.lower() for x in ("could not find", "not found", "error")) else bool(text.strip())
    except Exception: return None
    finally: client.call_lock.release()


def engine_snapshot(roblox_state=None, unity_state=None, godot_state=None):
    """Connection-aware engine status used by the extension for auto-routing."""
    if roblox_state is None:
        roblox_state = probe_studio()
    if unity_state is None:
        unity_state = probe_unity()
    if godot_state is None:
        godot_state = probe_godot()
    states = []
    for sid, client in mgr.clients.items():
        connected = unity_state if sid == "unity" else (godot_state if sid == "godot" else (roblox_state.get("place") if sid == "roblox" else None))
        states.append({"id": sid, "alive": client.is_alive(), "connected": connected, "tools": len(client.tools_cache), "enabled": True})
    for sid in mgr.parked:
        states.append({"id": sid, "alive": False, "connected": None, "tools": 0, "enabled": False})
    if _companion_execution_available() and "roblox" not in mgr.disabled:
        count=sum(1 for t in COMPANION_TOOLS if _companion_tool_enabled(t["name"]) and PLUGIN_PERMISSION_RANK.get(t["permission"],3)<=PLUGIN_PERMISSION_RANK.get(plugin_state.get("permissionMode"),0))
        row=next((x for x in states if x["id"]=="roblox"),None)
        if row is None:row={"id":"roblox","enabled":True,"tools":0};states.append(row)
        row.update({"nativeConnected":roblox_state.get("place") is True,"companionConnected":True,"connected":True,"alive":True,"companionTools":count})
    if BLENDER_WORKSPACE.owns_target and 'blender' not in mgr.disabled:
        row=next((r for r in states if r['id']=='blender'),None)
        if row is None:row={'id':'blender','tools':0};states.append(row)
        row.update(enabled=True,alive=BLENDER_WORKSPACE.running,connected=bool(BLENDER_WORKSPACE.status()['verified']),tools=len(blender_workspace.NATIVE_NAMES),backend='headless-workspace',workspaceProject=BLENDER_WORKSPACE.project,workspacePhase=BLENDER_WORKSPACE.phase)
    BLENDER_WORKSPACE.engine_enabled=lambda sid:mgr.engine_enabled(sid)
    for row in states:
        if row['id'] in ('roblox','unity','godot'):row['blenderCompanion']=row['id'] in BLENDER_WORKSPACE.pipeline.settings['engines']
    BLENDER_WORKSPACE.set_engines(states)
    return states


def _classify_error(exc, name):
    """Turn an exception into a structured, actionable error record.

    Purely ADDITIVE: the legacy `error` / `kind` keys on the reply are unchanged,
    so no existing caller behaves differently. `errorInfo` adds the three things a
    caller (or a human reading the console) actually needs to act: a stable code,
    whether retrying could plausibly help, and which tool produced it. Before
    this, every failure looked the same to the extension - a bare string.
    """
    kind = type(exc).__name__
    text = str(exc) or kind
    low = text.lower()
    if isinstance(exc, TimeoutError) or "timeout" in low or "timed out" in low:
        code, retryable = "timeout", True
    elif "not connected" in low or "offline" in low:
        code, retryable = "server_disconnected", True
    elif "unknown tool" in low or "does not advertise" in low:
        code, retryable = "unknown_tool", False
    elif "switched off" in low or "disabled" in low or "not available" in low:
        code, retryable = "engine_disabled", False
    elif "is required" in low or "required" in low or "invalid" in low or "must be" in low:
        code, retryable = "invalid_arguments", False
    elif "permission" in low or "denied" in low or "not authorized" in low or "forbidden" in low:
        code, retryable = "permission_denied", False
    else:
        code, retryable = "tool_error", True
    return {"code": code, "message": text, "tool": name, "kind": kind, "retryable": retryable}


def safe_call(name, arguments, timeout):
    """Never raises. Always returns a dict the extension can feed back to DeepSeek."""
    try:
        result = mgr.call(name, arguments, timeout)
        return {"ok": True, "text": result["text"], "images": result["images"]}
    except TimeoutError as e:
        return {"ok": False, "error": str(e), "kind": "timeout", "errorInfo": _classify_error(e, name)}
    except Exception as e:
        return {"ok": False, "error": str(e), "kind": type(e).__name__, "errorInfo": _classify_error(e, name)}


_RESULT_LIMIT_ENV_DEFAULT = os.environ.get("MS_TOOL_RESULT_LIMIT")


def apply_result_limit(value):
    """Settings -> Limits: the extension sends result_limit with each call. 0 = do not clip native ms_* results here
    (the extension pages them or the user chose no limit); None/absent = the bridge default (or MS_TOOL_RESULT_LIMIT)."""
    try:
        if value is None:
            if _RESULT_LIMIT_ENV_DEFAULT is None:
                os.environ.pop("MS_TOOL_RESULT_LIMIT", None)
            else:
                os.environ["MS_TOOL_RESULT_LIMIT"] = _RESULT_LIMIT_ENV_DEFAULT
        else:
            os.environ["MS_TOOL_RESULT_LIMIT"] = str(max(0, int(value)))
    except (TypeError, ValueError):
        pass


async def run_tool_task(ws, name, args, timeout, rid, result_limit=None):
    """Execute one tool off the socket read loop and send its result back.

    Kept as a standalone task (not awaited inline in handler) so a long tool
    never starves the connection's ability to answer app-level pings - see the
    call_tool branch in handler() for the full rationale."""
    t0 = time.monotonic()
    apply_result_limit(result_limit)
    res = await asyncio.to_thread(safe_call, name, args, timeout)
    elapsed = time.monotonic() - t0
    tag = "gr" if res.get("ok") else "rd"
    summary = (res.get("text") or res.get("error") or "")[:80].replace("\n", " ")
    slow = "  [SLOW]" if elapsed > 5 else ""
    # Routine per-call traces are technical noise for a non-dev user watching
    # the console; they still land in bridge_debug.log. A failed/slow call
    # DOES surface on the terminal - that's the signal a user should notice.
    log(f"<- {name} ({elapsed:.1f}s){slow}: {summary}", tag, terminal=not res.get("ok") or elapsed > 5)
    try:
        await ws.send(json.dumps({"type": "tool_result", "id": rid, **res}))
    except websockets.ConnectionClosed:
        pass


async def broadcast_status():
    """Push a fresh status snapshot to every currently-connected extension tab.

    Needed because the socket now starts listening (see _boot_and_diagnose in
    main()) before every MCP server has necessarily finished launching in the
    background - an extension that connects in that window gets an early,
    incomplete "connected" snapshot (e.g. an addon server not started yet).
    The extension's own periodic poll only reads a passively cached copy of
    the LAST message it received (background.js never re-probes on its own),
    so without a follow-up push that stale snapshot can persist forever (seen
    live 2026-07-11: Blender not yet alive at connect-time froze the "Start
    Roblox agent" button in its fully-disabled, non-degraded state even long
    after Blender was actually up). background.js already handles a second
    "connected" message arriving at any time (updates its cache and re-renders
    the bar), so re-sending this exact shape once startup truly settles is
    enough to self-correct with zero extension-side changes needed.
    """
    if not clients:
        return
    try:
        _st, _unity, _godot = await asyncio.gather(
            asyncio.to_thread(probe_studio), asyncio.to_thread(probe_unity), asyncio.to_thread(probe_godot))
        _proc = await asyncio.to_thread(_roblox_studio_app_running)
        payload = json.dumps({
            "type": "connected",
            "mcp_alive": mgr.any_alive(),
            "studio": _st["place"], "studio_app": _st["app"],
            # Whether a Roblox Studio WINDOW process exists at all - lets the
            # extension word the corrective step correctly ("open the MCP
            # panel in your already-open Studio" vs "launch Studio").
            "studio_proc": _proc,
            "servers": mgr.health(),
            "engines": engine_snapshot(_st, _unity, _godot),
            "tools": mgr.list_tools(),
            "port": PORT,
            "bridge_version": BRIDGE_VERSION,
            "bridge_pid": os.getpid(),
            "bridge_root": _BRIDGE_ROOT,
            "capabilities": {
                "memory": MEMORY_GRAPH is not None,
                "software_workspace": WORKSPACE is not None,
                "native_terminal": True, "blender_companion": True,
            },
        })
    except Exception:
        return
    for ws in list(clients):
        try:
            await ws.send(payload)
        except Exception:
            pass


async def handler(ws):
    peer = getattr(ws, "remote_address", ("?",))[0]
    clients.add(ws)
    log(f"extension connected  ({peer})  [{len(clients)} client(s)]", "gr")
    log_q = queue.Queue(maxsize=500)
    _unsub_log = _subscribe_log(ws, log_q)
    log_pump = asyncio.create_task(_log_pump(ws, log_q))
    try:
        _st, _unity, _godot = await asyncio.gather(
            asyncio.to_thread(probe_studio), asyncio.to_thread(probe_unity), asyncio.to_thread(probe_godot))
        await ws.send(json.dumps({
            "type": "connected",
            "mcp_alive": mgr.any_alive(),
            "studio": _st["place"], "studio_app": _st["app"],
            "studio_proc": await asyncio.to_thread(_roblox_studio_app_running),
            "servers": mgr.health(),
            "engines": engine_snapshot(_st, _unity, _godot),
            "tools": mgr.list_tools(),
            "port": PORT,
            "bridge_version": BRIDGE_VERSION,
            "bridge_pid": os.getpid(),
            "bridge_root": _BRIDGE_ROOT,
            "capabilities": {
                "memory": MEMORY_GRAPH is not None,
                "software_workspace": WORKSPACE is not None,
                "native_terminal": True, "blender_companion": True,
            },
        }))
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            rid = msg.get("id")

            if mtype == "ping":
                await ws.send(json.dumps({"type": "pong", "id": rid}))

            elif mtype == "mobile_admin":
                try:
                    headers=getattr(getattr(ws,'request',None),'headers',None) or getattr(ws,'request_headers',{})
                    if headers.get('Origin')!=mobile_remote.extension_origin():raise PermissionError('Phone settings require the installed Multi-Script extension origin.')
                    owner=str(msg.get('owner') or '')
                    if not re.fullmatch(r'[a-zA-Z0-9-]{8,80}',owner):raise ValueError('Missing browser identity.')
                    result=await asyncio.to_thread(PHONE_REMOTE.admin,str(msg.get('op') or 'status'),msg.get('payload') or {},owner)
                except Exception as error:result={'ok':False,'error':str(error)[:500]}
                await ws.send(json.dumps({'type':'mobile_admin','id':rid,**result}))

            elif mtype=='obsidian_admin':
                try:
                    headers=getattr(getattr(ws,'request',None),'headers',None) or getattr(ws,'request_headers',{})
                    if headers.get('Origin')!=mobile_remote.extension_origin():raise PermissionError('Vault settings require the installed Multi-Script extension origin.')
                    import obsidian_vault as vault
                    op=msg.get('op');payload=msg.get('payload') or {}
                    if op=='status':result=vault.status()
                    elif op=='setup':result=await asyncio.to_thread(vault.setup,payload.get('path') or None)
                    elif op=='import':result=await asyncio.to_thread(vault.import_attachment,payload.get('path') or '')
                    else:raise ValueError('Unknown vault settings operation.')
                except Exception as error:result={'ok':False,'error':str(error)[:1000]}
                await ws.send(json.dumps({'type':'obsidian_admin','id':rid,**result}))

            elif mtype=='blockbench_workspace_admin':
                try:
                    headers=getattr(getattr(ws,'request',None),'headers',None) or getattr(ws,'request_headers',{})
                    if headers.get('Origin')!=mobile_remote.extension_origin():raise PermissionError('Blockbench setup requires the installed Multi-Script extension origin.')
                    response=await asyncio.to_thread(_builtin_call,'ms_blockbench_workspace',{'action':msg.get('op','status'),'render':msg.get('render') is True},mgr)
                    result={'ok':True,**json.loads(response['text'])}
                    if msg.get('op')=='prepare':asyncio.create_task(broadcast_status())
                except Exception as error:result={'ok':False,'error':str(error)[:1000]}
                await ws.send(json.dumps({'type':'blockbench_workspace_admin','id':rid,**result}))

            elif mtype=='blender_workspace_admin':
                try:
                    headers=getattr(getattr(ws,'request',None),'headers',None) or getattr(ws,'request_headers',{})
                    if headers.get('Origin')!=mobile_remote.extension_origin():raise PermissionError('Blender Workspace controls require the installed Multi-Script extension.')
                    op=msg.get('op','open')
                    if op=='open' and 'blender' in mgr.disabled:raise RuntimeError('Enable Blender in Settings → Engines before opening its workspace.')
                    if op=='open':result={'ok':True,'url':await asyncio.to_thread(BLENDER_WORKSPACE.start_http)}
                    elif op=='status':
                        await asyncio.to_thread(engine_snapshot)
                        result=BLENDER_WORKSPACE.status()
                        result['servers']=mgr.health()
                    elif op=='companion':result={'ok':True,'companion':await asyncio.to_thread(BLENDER_WORKSPACE.pipeline.configure,msg.get('payload') or {})}
                    elif op=='ensure':
                        engines=msg.get('engines') or []
                        if not isinstance(engines,list) or any(e not in blender_pipeline.ENGINES for e in engines):raise ValueError('Invalid companion engine selection.')
                        if any(e in BLENDER_WORKSPACE.pipeline.settings['engines'] for e in engines):
                            await asyncio.to_thread(engine_snapshot)
                            result=await asyncio.to_thread(BLENDER_WORKSPACE.pipeline.begin,engines)
                        elif BLENDER_WORKSPACE.owns_target:
                            if not mgr.engine_enabled('blender'):raise RuntimeError('Enable Blender in Settings → Engines to resume its workspace.')
                            job=await asyncio.to_thread(BLENDER_WORKSPACE.submit,'ensure',{'project':BLENDER_WORKSPACE.project})
                            result={'ok':True,'required':True,'engines':['blender'],'job':job}
                        else:result=await asyncio.to_thread(BLENDER_WORKSPACE.pipeline.begin,engines)
                    else:raise ValueError('Unknown Blender Workspace control.')
                except Exception as e:result={'ok':False,'error':str(e)}
                await ws.send(json.dumps({'type':'blender_workspace_admin','id':rid,**result}))

            elif mtype == "memory":
                # Extension UI -> local graph memory (list/create/open/observe/...).
                if MEMORY_GRAPH is None:
                    res = {"ok": False, "error": "memory module unavailable: %s" % MEMORY_GRAPH_ERROR}
                else:
                    loop = asyncio.get_running_loop()
                    res = await loop.run_in_executor(None, MEMORY_GRAPH.ws_op, str(msg.get("op") or "list"), msg.get("args") or {})
                await ws.send(json.dumps({"type": "memory", "id": rid, **res}))

            elif mtype == "bridge_log":
                # The in-extension terminal asks for the backlog, optionally
                # filtered by level. `since` is the seq the panel already has, so
                # a reconnect or a re-open resumes exactly where it left off
                # instead of replaying everything or silently skipping lines.
                try:
                    since = int(msg.get("since") or 0)
                except Exception:
                    since = 0
                lines, newest = log_since(since, msg.get("limit") or 400)
                want = str(msg.get("level") or "").lower()
                if want and want != "all":
                    lines = [r for r in lines if r["level"] == want]
                await ws.send(json.dumps({
                    "type": "bridge_log", "id": rid, "lines": lines,
                    "newest": newest, "service": _service_snapshot(),
                }))

            elif mtype == "bridge_log_clear":
                # Clearing is a VIEW operation: we drop the panel's backlog but
                # never the debugging history - the file on disk is untouched and
                # stays complete.
                with _log_lock:
                    _log_ring.clear()
                await ws.send(json.dumps({"type": "bridge_log_cleared", "id": rid}))

            elif mtype == "studio_status":
                studio, unity, godot = await asyncio.gather(
                    asyncio.to_thread(probe_studio), asyncio.to_thread(probe_unity), asyncio.to_thread(probe_godot))
                await ws.send(json.dumps({
                    "type": "studio_status", "id": rid,
                    "studio": studio["place"], "studio_app": studio["app"],
                    "studio_proc": await asyncio.to_thread(_roblox_studio_app_running),
                    "mcp_alive": mgr.any_alive(), "engines": engine_snapshot(studio, unity, godot),
                }))

            elif mtype == "terminal_probe":
                # Lightweight liveness probe used by the in-chat terminal panel.
                #
                # WHY THIS EXISTS AS ITS OWN FRAME
                # The panel polls this (and the /logs route on the companion HTTP
                # port) when the socket is quiet, so the dot and the service
                # chips stay truthful even mid-reconnect. It answers with the
                # same shape as /logs so one renderer handles both channels.
                await ws.send(json.dumps({
                    "type": "terminal_probe", "id": rid,
                    "ok": True, "service": _service_snapshot(),
                }))

            elif mtype == "list_tools":
                try:
                    tools = await asyncio.to_thread(mgr.list_tools, True)
                except Exception as e:
                    tools = mgr.list_tools()
                    log(f"list_tools error: {e}", "yl")
                _st, _unity = await asyncio.gather(
                    asyncio.to_thread(probe_studio), asyncio.to_thread(probe_unity))
                await ws.send(json.dumps({
                    "type": "tools", "id": rid,
                    "tools": tools, "hidden": sorted(RETIRED_FROM_CATALOGUE), "mcp_alive": mgr.any_alive(),
                    "studio": _st["place"], "studio_app": _st["app"],
                    "studio_proc": await asyncio.to_thread(_roblox_studio_app_running),
                    "servers": mgr.health(), "engines": engine_snapshot(_st, _unity, _godot),
                }))

            elif mtype in ("elevenlabs_status", "elevenlabs_configure", "elevenlabs_clear"):
                try:
                    audio = _elevenlabs_audio()
                    if mtype == "elevenlabs_configure":
                        state = await asyncio.to_thread(audio.configure_api_key, msg.get("api_key"))
                    elif mtype == "elevenlabs_clear":
                        state = await asyncio.to_thread(audio.clear_api_key)
                    else:
                        state = await asyncio.to_thread(audio.status)
                    await ws.send(json.dumps({"type":"elevenlabs_settings","id":rid,"ok":True,"status":state}))
                except Exception as e:
                    await ws.send(json.dumps({"type":"elevenlabs_settings","id":rid,"ok":False,"error":str(e)}))

            elif mtype == "call_tool":
                headers=getattr(getattr(ws,'request',None),'headers',None) or getattr(ws,'request_headers',{})
                origin=headers.get('Origin')
                if origin is not None and origin!=mobile_remote.extension_origin():
                    await ws.send(json.dumps({'type':'tool_result','id':rid,'ok':False,'kind':'permission','error':'Browser tool calls require the installed Multi-Script extension origin.'}))
                    continue
                name = msg.get("name", "")
                args = msg.get("arguments") or {}
                timeout = float(msg.get("timeout", 120000)) / 1000.0
                log(f"-> tool  {name}({', '.join(args.keys())})", "cy", terminal=False)
                # Run the tool as a BACKGROUND task instead of awaiting it here.
                # Awaiting inline parks this read loop for the WHOLE tool call, so
                # a long tool (e.g. wait_job_finished > 25s) means the client's
                # app-level pings are never read/answered - its half-open-socket
                # watchdog then force-closes the connection and the in-flight call
                # is dropped as "bridge unreachable" (reported live). As a task,
                # the loop stays free to answer pings/status while the tool runs.
                # The extension only ever has ONE call_tool in flight (its agent
                # loop awaits each result before sending the next), so this never
                # overlaps tool executions.
                asyncio.create_task(run_tool_task(ws, name, args, timeout, rid, msg.get("result_limit")))

            elif mtype in ("add_server", "remove_server"):
                # Adding/removing an addon MCP server rewrites config.json, which
                # the bridge only reads at launch - so we ack, then restart the
                # whole process to pick it up cleanly. The primary Roblox server
                # is protected inside config_add/remove_server.
                if mtype == "add_server":
                    ok, err = await asyncio.to_thread(
                        config_add_server,
                        msg.get("server_id"), msg.get("command"),
                        msg.get("args"), msg.get("env"))
                else:
                    ok, err = await asyncio.to_thread(
                        config_remove_server, msg.get("server_id"))
                await ws.send(json.dumps({
                    "type": "server_changed", "id": rid,
                    "ok": ok, "error": err, "restarting": ok,
                }))
                if ok:
                    # Give the ack a beat to flush over the socket, then restart.
                    async def _do_restart():
                        await asyncio.sleep(0.4)
                        restart_self()
                    asyncio.create_task(_do_restart())

            elif mtype in ("engine_prefs", "set_engine"):
                result = {"ok": True}
                if mtype == "set_engine":
                    result = await asyncio.to_thread(mgr.set_engine_enabled, msg.get("engine"), msg.get("enabled"))
                _rst, _runity, _rgodot = await asyncio.gather(
                    asyncio.to_thread(probe_studio), asyncio.to_thread(probe_unity), asyncio.to_thread(probe_godot))
                await ws.send(json.dumps({
                    "type": "engine_prefs", "id": rid, **result,
                    "engineList": mgr.engine_list(), "disabled": sorted(mgr.disabled),
                    "servers": mgr.health(), "engines": engine_snapshot(_rst, _runity, _rgodot),
                    "tools": mgr.list_tools(),
                }))
                if mtype == "set_engine":
                    asyncio.create_task(broadcast_status())

            elif mtype == "restart_mcp":
                sid = msg.get("server")
                try:
                    await asyncio.to_thread(mgr.restart, sid)
                    ok, err = True, None
                except Exception as e:
                    ok, err = False, str(e)
                _rst, _runity, _rgodot = await asyncio.gather(
                    asyncio.to_thread(probe_studio), asyncio.to_thread(probe_unity), asyncio.to_thread(probe_godot))
                await ws.send(json.dumps({
                    "type": "mcp_status", "id": rid,
                    "alive": mgr.any_alive(), "ok": ok, "error": err,
                    "servers": mgr.health(), "engines": engine_snapshot(_rst, _runity, _rgodot),
                    "tools": mgr.list_tools(),
                }))

            else:
                await ws.send(json.dumps({
                    "type": "error", "id": rid,
                    "error": f"unknown message type: {mtype}",
                }))
    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        log(f"handler error: {e}", "rd")
    finally:
        clients.discard(ws)
        _unsub_log()
        log_pump.cancel()
        try:
            await log_pump
        except asyncio.CancelledError:
            pass
        log(f"extension disconnected  [{len(clients)} client(s)]", "yl")


async def server_watch():
    """Poll every MCP server and restart any that died unexpectedly (e.g. the
    StudioMCP proxy crashing on its own - see stop()'s taskkill /T fix and the
    stderr logging above for why this used to happen silently). Without this,
    a dead server only got noticed on the NEXT real tool call, which is what
    made "Studio looks connected but nothing responds" possible."""
    # Crash-LOOP detection thresholds: LOOP_N deaths within LOOP_WINDOW seconds
    # means something is killing (or instantly crashing) the server every time
    # we bring it back - the silent restart cycle the auto-restart otherwise
    # hides completely. We still keep restarting (the cause may be transient,
    # e.g. the user is about to start Blender), but the terminal now NAMES the
    # problem: exit code, the child's last stderr lines, and - for a port-bound
    # server - who is squatting the port. Banner re-prints at most every
    # LOOP_WARN_COOLDOWN so the terminal stays readable.
    LOOP_N = 3
    LOOP_WINDOW = 60
    LOOP_WARN_COOLDOWN = 120
    while True:
        await asyncio.sleep(5)
        for sid, client in list(mgr.clients.items()):
            if sid=='blender' and BLENDER_WORKSPACE.owns_target:continue
            try:
                if client.is_alive():
                    # Healthy for a while: forget the crash-loop back-off.
                    if getattr(client, "loop_level", 0) and time.time() - getattr(client, "last_restart_at", 0.0) > 120:
                        client.loop_level = 0
                if not client.is_alive():
                    now = time.time()
                    # restart_times holds RESTART ATTEMPTS (appended just before
                    # each start below), never per-poll sightings - appending on
                    # every 5s poll would keep the window full forever and the
                    # "slow down" branch would then block restarts permanently.
                    client.restart_times = [t for t in client.restart_times if now - t < LOOP_WINDOW]
                    looping = len(client.restart_times) >= LOOP_N
                    if looping and now - client.loop_warned_at > LOOP_WARN_COOLDOWN:
                        client.loop_warned_at = now
                        log(f"[{sid}] CRASH LOOP: died {len(client.restart_times)} times in the last "
                            f"{LOOP_WINDOW}s (last exit code: {client.last_exit}). Something is killing it "
                            f"or it cannot start.", "rd")
                        if client.start_error:
                            log(f"[{sid}] {client.start_error}", "rd")
                        elif client.stderr_tail:
                            log(f"[{sid}] last error output (usually the real reason):", "rd")
                            for ln in client.stderr_tail:
                                log(f"[{sid}]   {ln}", "yl")
                        else:
                            log(f"[{sid}] the server printed no error output before dying.", "yl")
                        # Port forensics: name the process squatting a port this
                        # server needs. For the primary Roblox proxy that is
                        # Studio's MCP port; a squatter there (seen live: a
                        # 'ropilot' app) makes the proxy die/misbehave forever.
                        if sid == "roblox":
                            owner = _port_owner(STUDIO_MCP_PORT)
                            if owner:
                                pid, name, path = owner
                                if "roblox" not in (name or "").lower() and "studio" not in (path or "").lower():
                                    log(f"[{sid}] port {STUDIO_MCP_PORT} is held by '{name}' (pid {pid}, {path}) - "
                                        f"close that program, it is squatting Studio's MCP port.", "rd")
                        log(f"[{sid}] common causes: its app is not running (e.g. Blender + addon), a port "
                            f"conflict, an antivirus killing it, or a bad command in config.json. "
                            f"Auto-restart continues in the background.", "yl")
                    # Exit code 78 (EX_CONFIG) = the launcher's prerequisite is
                    # missing (Node/npx, uv/uvx, the editor). Restarting cannot
                    # help until the user installs it, so say exactly that once
                    # and go straight to the slowest retry cadence.
                    if _needs_setup(client):
                        if not getattr(client, "setup_logged", False):
                            client.setup_logged = True
                            log(f"[{sid}] needs setup: {client.start_error or 'a prerequisite is missing'}. "
                                f"Install it, then use Restart in the bridge panel. Retrying every 10 minutes.", "yl")
                        looping = True
                        client.loop_level = max(getattr(client, "loop_level", 0), 5)
                    if looping:
                        # Clearly hopeless right now: back off 15s -> 30s -> 1m ->
                        # 2m -> 5m -> 10m so a broken command (Unity/Blender not
                        # installed, Studio closed) is not hammer-spawned every few
                        # seconds - on Windows every respawn was a process launch
                        # (and, before 6.25.1, a flashing console window). It still
                        # retries forever: the cause may clear (user opens Blender).
                        level = min(getattr(client, "loop_level", 0), 5)
                        wait_s = (15, 30, 60, 120, 300, 600)[level]
                        if now - getattr(client, "last_restart_at", 0.0) < wait_s:
                            continue
                        client.loop_level = level + 1
                    client.last_restart_at = now
                    client.restart_times.append(now)
                    log(f"[{sid}] found dead - auto-restarting...", "yl")
                    await asyncio.to_thread(client.start)
                    mgr.rebuild_index()
                    await broadcast_status()  # tell any connected extension right away
            except Exception as e:
                log(f"[{sid}] auto-restart failed: {e}", "rd")


def _needs_setup(client):
    """True when the server's launcher reported a missing prerequisite."""
    proc = getattr(client, "proc", None)
    try:
        rc = proc.poll() if proc is not None else None
    except Exception:
        rc = None
    return rc == 78 or "exit code 78" in str(getattr(client, "start_error", "") or "")


def _current_studio_exe():
    """The StudioMCP.exe our launcher would currently pick (newest version
    folder paired with a real RobloxStudioBeta.exe), or None. Reused here only
    to detect a Studio update happening mid-session: Roblox's own bug report
    ("Studio MCP turning off after update") says the toggle resets to OFF
    whenever Studio auto-updates - restarting our proxy can't fix that (Studio
    itself refuses the connection while its toggle is off), so the terminal
    should say "re-enable the toggle" instead of "wait for auto-recovery"
    when a version bump coincides with the disconnect."""
    if _studio_scan is None:
        return None
    try:
        return _studio_scan.find_studio_mcp()
    except Exception:
        return None


async def studio_watch(initial_app, initial_place=None):
    """Poll Studio attachment and log transitions, so the terminal confirms in
    GREEN the moment Studio attaches (e.g. after the user toggles its MCP server)
    and warns again if it later drops. Best-effort; never raises.

    Also auto-recovers from a real disconnect: two bugs reported on the Roblox
    devforum leave StudioMCP.exe alive (our client stays "alive" - the process
    never dies, so server_watch's dead-process restart never fires) but stuck
    talking to nothing - (1) StudioMCP keeps a stale named-pipe handle keyed by
    Studio's old PID after Studio is closed and reopened, and never rediscovers
    the new one; (2) MCP silently disconnects every 5-15 minutes on some
    machines. The documented user workaround for both is "toggle Studio's MCP
    server off/on" / "reopen the MCP panel" - which just forces StudioMCP to
    redo its handshake. Restarting OUR proxy process is the equivalent from
    this side (taskkill + fresh launch_studio_mcp.py), so do it automatically
    once a drop looks real (sustained, not a momentary blip) instead of leaving
    the user to notice and toggle it themselves."""
    prev_app = initial_app
    prev_place = initial_place
    disconnected_since = None
    last_auto_restart = 0.0
    empty_since = None       # when the roblox catalogue was first seen empty
    last_reclaim = 0.0       # cooldown for the zombie-StudioMCP port reclaim
    place_transitions = []
    known_studio_exe = await asyncio.to_thread(_current_studio_exe)
    update_suspected = False
    # Only auto-restart a disconnect that follows a real connection (matches
    # the two known bugs above) - never spam-restart while Studio simply isn't
    # open yet at all (prev_app starting False/None is the common cold-start
    # case and restarting there would just be noise every cooldown).
    ever_connected = initial_app is True
    while True:
        await asyncio.sleep(4)
        # If StudioMCP launched while Studio was closed, its catalogue is EMPTY
        # and stays that way: start()'s 12s retry loop has long given up, and
        # nothing else ever re-asks for tools/list (probe_studio can't - the
        # probe tools themselves are part of the missing catalogue, which is
        # why it short-circuits to "not connected" on an empty cache). So a
        # Studio opened AFTER that window was never detected until the user
        # restarted the whole bridge (seen live 2026-07-11). Re-ask here on
        # every poll while the catalogue is empty; the moment Studio attaches,
        # tools appear, the index rebuilds, and the normal probe below flips
        # the state to connected on this same iteration.
        rc0 = mgr.clients.get("roblox")
        if rc0 is not None and rc0.is_alive() and not rc0.tools_cache:
            got = False
            try:
                got = bool(await asyncio.to_thread(rc0.refresh_tools, 3))
            except Exception:
                got = False
            if got:
                mgr.rebuild_index()
                log(f"Roblox Studio's tools appeared ({len(rc0.tools_cache)}) - Studio attached.", "gr")
                empty_since = None
            else:
                now0 = time.time()
                if empty_since is None:
                    empty_since = now0
                # First: a PROVEN port hijack (stderr showed StudioMCP talking to
                # a foreign host, e.g. ropilot). Hard evidence, so recover fast
                # and unconditionally - no need to wait out the sustained-empty
                # window the ambiguous zombie case below uses.
                if (rc0.saw_foreign_ws_host and now0 - last_reclaim > 180):
                    last_reclaim = now0
                    killed, sname = await asyncio.to_thread(_kill_port_squatter)
                    if killed:
                        try:
                            await asyncio.to_thread(mgr.restart, "roblox")
                        except Exception as e:
                            log(f"roblox proxy restart after squatter kill failed: {e}", "rd")
                        _print_squatter_hint(sname)
                        await broadcast_status()
                # Otherwise: catalogue stuck empty WITH a Studio window open often
                # means a zombie StudioMCP.exe (not ours) still owns port 13469 and
                # swallowed Studio's one-shot registration - a state no manual
                # restart combination can escape (see _reclaim_studio_port).
                # Sustained-empty threshold + cooldown so a Studio that is
                # merely slow to boot never triggers a spurious kill.
                elif (now0 - empty_since > 20 and now0 - last_reclaim > 180
                        and await asyncio.to_thread(_roblox_studio_app_running) is True):
                    last_reclaim = now0
                    if await asyncio.to_thread(_reclaim_studio_port, rc0):
                        try:
                            await asyncio.to_thread(mgr.restart, "roblox")
                        except Exception as e:
                            log(f"roblox proxy restart after zombie kill failed: {e}", "rd")
                        _print_reregister_hint()
                        await broadcast_status()
        else:
            empty_since = None
        try:
            st = await asyncio.to_thread(probe_studio)
        except Exception:
            continue
        app, place = st["app"], st["place"]
        if app is not None and app != prev_app:
            if app is True:
                # Roblox-only count, not mgr.list_tools() (sums every server,
                # e.g. + Blender) - this message is specifically about Roblox
                # attaching, so it must not borrow addon tool counts (same
                # class of bug as the startup banner, see roblox_total above).
                rc = mgr.clients.get("roblox")
                roblox_now = len(rc.tools_cache) if rc else 0
                log(f"Roblox Studio connected - {roblox_now} tools ready.", "gr")
                ever_connected = True
                disconnected_since = None
                update_suspected = False
            else:
                cur_exe = await asyncio.to_thread(_current_studio_exe)
                if cur_exe and known_studio_exe and cur_exe != known_studio_exe:
                    # A newer Studio version folder appeared since we last saw
                    # one - restarting the proxy will NOT fix this (Studio
                    # itself refuses the MCP connection while its own toggle
                    # is off), so tell the user the actual fix instead of
                    # letting the generic auto-recovery below spin uselessly.
                    ver = os.path.basename(os.path.dirname(cur_exe))
                    log(f"Roblox Studio appears to have UPDATED (new version: {ver}). "
                        "Studio often turns its MCP toggle back OFF after an update - open "
                        "Roblox Studio > Assistant Settings > MCP Servers and re-enable "
                        "'Enable Studio as MCP server'.", "yl")
                    update_suspected = True
                else:
                    log("Roblox Studio disconnected - re-enable its MCP server (toggle off/on).", "yl")
                    update_suspected = False
                known_studio_exe = cur_exe or known_studio_exe
                if ever_connected and disconnected_since is None:
                    disconnected_since = time.time()
            prev_app = app
            # studio_watch only used to LOG transitions - an extension sitting
            # on the pre-start standby screen (no tool calls happening, so
            # nothing else round-trips to the bridge) never saw Studio connect
            # or disconnect mid-session until it happened to poll for an
            # unrelated reason. Push it immediately instead of leaving that
            # extension staring at a stale snapshot indefinitely.
            await broadcast_status()
        # Set once per iteration: BOTH the app-drop branch and the place-churn
        # block below use it. It used to be assigned only inside the app-drop
        # branch, so any iteration that skipped that branch crashed the whole
        # watcher with UnboundLocalError on the churn line (seen live: the task
        # died right after a successful reconnect, silently ending ALL Studio
        # monitoring and status broadcasts until the bridge was restarted).
        now = time.time()
        if app is False and ever_connected and disconnected_since is not None and not update_suspected:
            # ~20s sustained (5 polls) before treating it as a real drop, not a
            # momentary blip; 90s cooldown between recovery attempts so a
            # Studio that is genuinely closed for a while doesn't get hammered.
            # Skipped entirely when a version bump was the likely cause (see
            # above) - restarting our proxy cannot flip Studio's own toggle
            # back on, so retrying would just be noise every 90s.
            if now - disconnected_since > 20 and now - last_auto_restart > 90:
                last_auto_restart = now
                # Which recovery applies depends on whether a Studio WINDOW is
                # actually running (validated live 2026-07-11, both directions):
                #  - Studio RUNNING but not attached: Studio's MCP plugin only
                #    registers ONCE, at Studio boot or on a toggle flip. It
                #    never retries by itself, and restarting OUR proxy cannot
                #    reach into Studio to re-register it - worse, a restart
                #    that lands while Studio is booting kills the listener at
                #    the exact moment the plugin makes its single attempt,
                #    which is precisely how this state got created. So: do NOT
                #    touch the proxy; tell the user the one action that works.
                #  - No Studio running: a restart is safe (nothing to collide
                #    with) and clears genuinely stuck/stale proxy state.
                if await asyncio.to_thread(_roblox_studio_app_running) is True:
                    log("Roblox Studio is RUNNING but its MCP plugin has not registered with the "
                        "bridge yet.", "yl")
                    log("If Studio is still STARTING UP, give it a minute (its plugin registers "
                        "late in boot).", "yl")
                    log("If Studio is fully loaded and this stays yellow: in Roblox Studio, simply "
                        "OPEN Assistant Settings > MCP Servers - opening that panel makes the "
                        "plugin re-register (validated twice live). If that's not enough, toggle "
                        "'Enable Studio as MCP server' OFF then ON there.", "yl")
                else:
                    log("Roblox Studio proxy looks stuck (known StudioMCP disconnect bug) - "
                        "restarting it to recover.", "yl")
                    try:
                        await asyncio.to_thread(mgr.restart, "roblox")
                        await broadcast_status()
                    except Exception as e:
                        log(f"auto-restart of roblox proxy failed: {e}", "rd")
        # PLACE-level churn: `app` can stay stuck reporting True the whole time
        # (seen live 2026-07-11 - Studio fully closed, list_roblox_studios kept
        # answering with a leftover studio entry for 4+ minutes, so the app-drop
        # trigger above never fires) while `place` flip-flops "loaded"/"closed"
        # every ~10-20s forever. That is not a user opening/closing places that
        # fast - it is the same class of stuck-proxy bug, just visible at the
        # place layer instead of the app layer. A fresh StudioMCP.exe process
        # cannot carry over stale cached state, so the same restart applies.
        place_transitions[:] = [t for t in place_transitions if now - t < 90]
        if len(place_transitions) >= 4 and now - last_auto_restart > 90:
            # Same running-Studio guard as the app-drop recovery above: with a
            # real Studio window up, a proxy restart can only collide with the
            # plugin's one-shot registration; the churn is Studio-side state.
            if await asyncio.to_thread(_roblox_studio_app_running) is not True:
                last_auto_restart = now
                log(f"Roblox Studio's place status flipped {len(place_transitions)} times in the last "
                    "90s (known StudioMCP stuck-proxy bug) - restarting the proxy to recover.", "yl")
                try:
                    await asyncio.to_thread(mgr.restart, "roblox")
                    await broadcast_status()
                except Exception as e:
                    log(f"auto-restart of roblox proxy failed: {e}", "rd")
                place_transitions.clear()
        if place is not None and place != prev_place:
            # Debounce: StudioMCP's binding to Studio blips every few seconds
            # on some machines (self-healing in ~1-4s - seen live as "Bound
            # studio ... disconnected" stderr). A probe landing in that window
            # can misread EITHER direction - most confusingly, reporting
            # "place loaded" from a stale cached response while the place is
            # actually still closed (seen live). Recheck once before trusting
            # a transition, in either direction.
            await asyncio.sleep(1.2)
            try:
                confirm = (await asyncio.to_thread(probe_studio))["place"]
            except Exception:
                confirm = None
            if confirm is None or confirm != place:
                continue  # didn't hold up on recheck - treat as noise, not a real change
            if place is True:
                log("Place loaded in Studio.", "gr")
            else:
                log("Place closed (Studio app still connected).", "yl")
            prev_place = place
            place_transitions.append(time.time())
            await broadcast_status()


async def _supervised(name, coro_factory):
    """Run a watcher coroutine forever, restarting it if it ever raises.

    Both watchers are designed to never raise, but one line proved that wrong
    in practice (an UnboundLocalError killed studio_watch SILENTLY - asyncio
    only prints 'Task exception was never retrieved' at shutdown, so all
    Studio monitoring and status broadcasts just stopped until the user
    restarted the bridge). A crash in a watcher must never be silent or
    permanent: log it loudly, wait a beat, start a fresh instance.
    """
    while True:
        try:
            await coro_factory()
            return  # normal completion (doesn't happen today, but respect it)
        except Exception as e:
            log(f"{name} crashed: {type(e).__name__}: {e} - restarting it in 5s "
                f"(please report this).", "rd")
            await asyncio.sleep(5)


async def main():
    main_loop=asyncio.get_running_loop()
    BLENDER_WORKSPACE.on_change=lambda:asyncio.run_coroutine_threadsafe(broadcast_status(),main_loop) if not main_loop.is_closed() else None
    if websockets is None:
        raise RuntimeError("Missing dependency 'websockets'. Run Setup.bat / Setup.sh, or: pip install websockets")
    print(f"\n{C['cy']}  Multi-Script Bridge v{BRIDGE_VERSION}{C['reset']}  {C['dim']}- Multi-Engine MCP - ws://{HOST}:{PORT}{C['reset']}\n")
    log(f"===== BRIDGE START  v{BRIDGE_VERSION}  pid={os.getpid()}  log={LOG_PATH} =====", "cy")
    await asyncio.to_thread(_kill_orphan_studio_mcp)
    killed_squatter = await asyncio.to_thread(check_studio_port)
    mgr.load_config()

    # Shared "we already told the user the corrective step" flag. Two producers
    # can print the 'toggle Studio's MCP server' action banner: the early
    # _early_studio_guidance task (fast, doesn't wait for start_all's ~48s grace
    # loop) and the post-start_all diagnostic block in _boot_and_diagnose. This
    # flag lets whichever fires first suppress the other, so the user never sees
    # the same instruction twice. Mutable dict so both nested coroutines share it.
    _guidance_shown = {"v": False}

    async def _early_studio_guidance():
        """Print the corrective action banner WITHOUT waiting for start_all()'s
        full ~48s grace loop.

        RobloxClient.start() retries tools/list for up to ~48s to catch a Studio
        that attaches a little late - correct for a Studio that IS coming, but it
        also means a user whose Studio is simply closed or whose MCP toggle is off
        waits ~48s before the terminal tells them what to do (the extension, which
        reads status over the socket, already says it immediately). So after a
        short grace we check independently and, if still not connected, show the
        step now. If Studio then attaches, studio_watch prints the green
        'connected' line - so an early banner is at worst redundant, never wrong
        (the user confirmed a premature toggle hint during boot is harmless).

        Deliberately does NOT try to distinguish 'Studio closed' from 'MCP toggle
        off': probe_studio can't tell them apart (both read app=False, see its
        docstring), and the banner wording already covers both, so there is no
        finer detection to preserve here. A proven port-squatter case is left to
        _boot_and_diagnose / studio_watch, which print their own, more specific
        hint."""
        if PRIMARY_SERVER_ID not in mgr.clients:
            return
        await asyncio.sleep(12)  # give a fast, normal attach the chance to win
        if _guidance_shown["v"]:
            return
        rc = mgr.clients.get(PRIMARY_SERVER_ID)
        if rc is None or getattr(rc, "saw_foreign_ws_host", False):
            return
        if rc.tools_cache:
            # Tools present - either connected, or an attach is mid-flight; defer
            # to the authoritative probe / studio_watch rather than second-guess.
            st = await asyncio.to_thread(probe_studio)
            if st["app"] is not False:
                return
        _guidance_shown["v"] = True
        action_banner([
            "Open your place in Roblox Studio.",
            "Go to: Assistant Settings > MCP Servers",
            "       > 'Enable Studio as MCP server'",
            "It can take up to ~10s; this window will turn green.",
        ])

    async def _boot_and_diagnose():
        """Launch every configured MCP server and print the boot diagnostic
        banner. Runs as a background task AFTER the socket below is already
        listening, so a slow or absent Roblox Studio never delays the
        extension's ability to connect and use OTHER MCP servers (e.g.
        Blender) right away - only the terminal banner and Roblox's own
        auto-recovery loop wait on this. (mgr.start_all() itself also
        launches every server in parallel now, for the same reason.)"""
        try:
            await asyncio.to_thread(mgr.start_all)
        except Exception as e:
            log(f"server startup error: {e}", "rd")
            log("The bridge will keep running; it retries on the first tool call.", "yl")
        total = len(mgr.list_tools())
        # Roblox-only count for the corrective message below: list_tools() sums
        # every configured server (Roblox + addons like Blender), so printing
        # `total` there falsely blamed addon tools on "NO Roblox Studio connected"
        # (seen live: 49 = 27 Roblox + 22 Blender, message only about Roblox).
        roblox_client = mgr.clients.get("roblox")
        roblox_total = len(roblox_client.tools_cache) if roblox_client else 0

        # Port-hijack check (ropilot etc.), done at boot: the child's stderr has
        # by now had its ~12s grace loop to reveal it connected to a foreign host
        # on the MCP port. This is proof the port is squatted even when the
        # one-shot check_studio_port() at startup missed it (a background helper
        # grabbing the port a beat after that check ran - seen live 2026-07-13).
        if (roblox_client is not None and roblox_total == 0
                and roblox_client.saw_foreign_ws_host):
            killed, sname = await asyncio.to_thread(_kill_port_squatter)
            if killed:
                try:
                    await asyncio.to_thread(mgr.restart, "roblox")
                    roblox_total = len(roblox_client.tools_cache)
                    total = len(mgr.list_tools())
                except Exception as e:
                    log(f"roblox proxy restart after squatter kill failed: {e}", "rd")
                _print_squatter_hint(sname)

        # Set True if we kill a leftover StudioMCP zombie below and print the
        # re-register hint - so the diagnostic block further down doesn't ALSO
        # print its own near-identical action banner (the same de-duplication
        # killed_squatter already does for the ropilot-squatter path).
        reclaimed_zombie = False
        # Zombie-port deadlock check, done at boot too (not just studio_watch):
        # with Studio ALREADY open, _kill_orphan_studio_mcp was skipped by its
        # safety guard, so a leftover StudioMCP.exe may still own the port and
        # our fresh proxy just spent its 12s grace loop talking to nothing.
        if (roblox_client is not None and roblox_total == 0
                and await asyncio.to_thread(_roblox_studio_app_running) is True
                and await asyncio.to_thread(_reclaim_studio_port, roblox_client)):
            try:
                await asyncio.to_thread(mgr.restart, "roblox")
                roblox_total = len(roblox_client.tools_cache)
                total = len(mgr.list_tools())
            except Exception as e:
                log(f"roblox proxy restart after zombie kill failed: {e}", "rd")
            reclaimed_zombie = True
            _print_reregister_hint()

        # A tool count alone only proves StudioMCP (the proxy) is up - it advertises
        # its catalogue even with NO Studio attached. The authoritative "a Studio is
        # actually connected" signal is the list_roblox_studios probe. So we probe
        # FIRST and only show the green "ready" line when Studio is really attached;
        # otherwise we show just the corrective step (no misleading green success).
        # Probe even when total == 0: StudioMCP advertises an EMPTY catalogue when
        # Studio's MCP server toggle is off (or no place is open), so 0 tools is the
        # most common "needs a corrective step" state, not a success.
        _st = await asyncio.to_thread(probe_studio)
        # Even when Studio (and its place) were ALREADY open before the bridge
        # started, the freshly-launched StudioMCP proxy needs a moment to (re)bind
        # to Studio's own MCP port - so an instant probe right after launch often
        # reads app=False for a beat before flipping True a few seconds later
        # (studio_watch would catch it, but only after printing a scary yellow
        # "not connected" block first). Give it the same grace period the tools
        # probe already gets before deciding it is a real problem.
        if _st["app"] is False:
            with _Spinner("    waiting for Roblox Studio to attach..."):
                for _ in range(8):
                    await asyncio.sleep(1)
                    _st = await asyncio.to_thread(probe_studio)
                    if _st["app"] is not False:
                        break
        # A single app=True reading can be a STALE positive: StudioMCP.exe can
        # answer list_roblox_studios with a leftover studio entry from a PREVIOUS
        # session even though no Studio window is actually open right now (seen
        # live 2026-07-11: bridge booted with Studio fully closed, still printed
        # "Roblox Studio connected" from the very first probe). studio_watch
        # already distrusts a single reading for PLACE transitions the same way -
        # apply the identical confirm-before-trusting step here for APP, so the
        # boot banner can't announce a connection that isn't really there.
        if _st["app"] is True:
            await asyncio.sleep(1.5)
            confirm = await asyncio.to_thread(probe_studio)
            if confirm["app"] is not True:
                _st = confirm
        if roblox_client is not None and (roblox_total == 0 or _st["app"] is False):
            if killed_squatter or reclaimed_zombie or _guidance_shown["v"]:
                # The action banner was ALREADY shown - either right after a kill
                # (check_studio_port / _print_reregister_hint for a zombie) or by
                # the early _early_studio_guidance task. Repeating the full
                # explanation here in a different color, seconds later, reads as a
                # second unrelated problem to a non-technical user (seen live
                # 2026-07-13: the toggle instruction and this block blurred
                # together). Just confirm we're still waiting, no new instructions.
                log("    still waiting for you to toggle Studio's MCP server "
                    "(see the action box above)...", "yl")
            else:
                _guidance_shown["v"] = True
                # No squatter: Studio is simply closed, or its MCP option is off.
                # Match the exact steps the extension itself tells the user
                # (Assistant Settings > MCP Servers), not a paraphrase - a
                # differently-worded instruction here reads as a second,
                # unrelated problem instead of the same one step.
                if roblox_total > 0:
                    log(f"    {roblox_total} Roblox tools loaded, but NO Roblox Studio is connected yet.", "yl")
                    log("    (This can be a slow attach that clears itself within ~10-15s -", "yl")
                    log("    watch for a green 'Roblox Studio connected' line right after.)", "yl")
                action_banner([
                    "Open your place in Roblox Studio.",
                    "Go to: Assistant Settings > MCP Servers",
                    "       > 'Enable Studio as MCP server'",
                    "It can take up to ~10s; this window will turn green.",
                ])
        elif _st["app"] is True:
            log(f"ready {total} tools available - Roblox Studio connected", "gr")
        else:
            log(f"ready {total} tools available ({len(mgr.clients)} MCP server(s))", "gr")
        asyncio.create_task(_supervised(
            "studio_watch", lambda: studio_watch(_st["app"], _st["place"])))

    async def _early_status_pushes():
        """A few follow-up status broadcasts shortly after boot.

        mgr.start_all() still doesn't RETURN until every server's thread has
        joined - including Roblox's, which can take up to ~48s (StudioMCP's
        own internal "waiting for tools" retry loop, seen live). So a single
        broadcast placed after start_all() would be just as slow as the old
        blocking behavior for the exact case this is meant to fix: an addon
        server (e.g. Blender) that's ready in 1-13s while Roblox is still
        slowly timing out. Poll-and-broadcast a few times instead, cheaply,
        so any extension that connected during that window self-corrects
        quickly instead of staying stuck on its first, incomplete snapshot.
        """
        for interval in (2, 2, 4, 6, 6):  # cumulative: 2s, 4s, 8s, 14s, 20s after boot
            await asyncio.sleep(interval)
            await broadcast_status()

    # Free our own port from a leftover bridge (double-launch / X-closed window /
    # prior crash) BEFORE binding, so relaunching the bridge "just works" instead
    # of dying on WinError 10048. Only ever kills a proven bridge.py; anything
    # else falls through to the friendly bind-error below.
    if await asyncio.to_thread(_reclaim_bridge_port):
        await asyncio.sleep(0.6)  # let Windows release the socket before we bind

    try:
        server_ctx = await websockets.serve(
            handler, HOST, PORT, ping_interval=20, ping_timeout=20,
            max_size=16 * 1024 * 1024)
    except OSError as e:
        # errno 10048 (Win) / EADDRINUSE: something we could NOT auto-kill still
        # owns the port - another app, or a python whose cmdline we couldn't read.
        if getattr(e, "errno", None) in (98, 10048) or "10048" in str(e):
            owner = await asyncio.to_thread(_port_owner, PORT)
            who = f" by '{owner[1]}' (pid {owner[0]})" if owner else ""
            log(f"could not start: port {PORT} is already in use{who}.", "rd")
            log(f"    A previous bridge may still be running, or another app took "
                f"the port. Close it, then relaunch. To find it:", "yl")
            if sys.platform == "win32":
                log(f"      netstat -ano | findstr {PORT}", "yl")
                log("      taskkill /F /PID <the pid from the last column>", "yl")
                log("    Or set a different port before launching:  set ZS_BRIDGE_PORT=17614", "yl")
            else:
                log(f"      lsof -nP -iTCP:{PORT} -sTCP:LISTEN", "yl")
                log("      kill <the PID in the last column>", "yl")
                log("    Or set a different port before launching:  ZS_BRIDGE_PORT=17614 bash Start.sh", "yl")
            return
        raise

    try:
        plugin_server = await asyncio.start_server(plugin_http_handler, HOST, PLUGIN_PORT, limit=65536)
    except OSError as e:
        plugin_server = None
        log(f"companion-plugin status port {PLUGIN_PORT} unavailable: {e}", "yl")

    async with server_ctx:
        if plugin_server:
            await plugin_server.start_serving()
        log(f"listening on ws://{HOST}:{PORT}  - companion plugin http://{HOST}:{PLUGIN_PORT}", "cy")
        asyncio.create_task(_supervised("server_watch", server_watch))
        asyncio.create_task(_boot_and_diagnose())
        asyncio.create_task(_early_studio_guidance())
        asyncio.create_task(_early_status_pushes())
        await asyncio.Future()  # run forever


def _install_signal_handlers():
    """Turn SIGTERM/SIGHUP into the same clean shutdown as Ctrl+C.

    The bridge had no signal handler at all, so on macOS/Linux stopping it (or
    `_reclaim_bridge_port` terminating a stale instance - the NORMAL path, not an
    edge case) killed the process outright and orphaned every MCP child:
    StudioMCP, and the uvx/npx servers, which keep holding ports and project
    locks. Mapping the signals onto KeyboardInterrupt reuses the existing
    shutdown path below instead of adding a second one.
    SIGKILL cannot be handled, by design.
    """
    if sys.platform == "win32":
        # Windows does not deliver SIGTERM to console apps, and signal.SIGHUP
        # does not exist there; Ctrl+C already raises KeyboardInterrupt.
        return

    def _handler(_signum, _frame):
        raise KeyboardInterrupt()

    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            # Not on the main thread, or the signal is unavailable here.
            pass


if __name__ == "__main__":
    _install_signal_handlers()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("shutting down...", "yl")
        for c in mgr.clients.values():
            c.stop()
    finally:
        PHONE_REMOTE.close()
        BLENDER_WORKSPACE.close()
        log("===== BRIDGE STOP =====", "cy")
