# SPDX-License-Identifier: GPL-3.0-or-later
"""native_host.py - the Chrome/Edge/Brave Native Messaging host for Multi-Script.

WHY
A web page and an extension cannot start a program. The one browser-sanctioned
way for an extension to run something on your machine is a *native messaging
host* that YOU registered once. This is that host. With it, the terminal icon in
the chat bar can start, stop and watch the local bridge without you ever opening
the old start.bat launcher (removed in 6.24.0).

SAFETY MODEL
* The browser only lets the extension IDs listed in the host manifest talk to it.
  No website can reach this process.
* It starts/stops only the registered bridge. It also stages publisher-signed
  Dev releases and applies managed files only while that bridge is stopped.
  The release key/feed are pinned locally; there is no arbitrary command verb.
* It only ever kills the process it started (tracked in logs/bridge.pid) or a
  process whose command line is this folder's bridge.py.

PROTOCOL
Chrome framing: 4-byte little-endian length + UTF-8 JSON, both directions.
The extension uses sendNativeMessage (one request, one reply, host exits), which
is robust against MV3 service workers being suspended; a connectNative loop is
also supported. Every reply is {"ok": bool, ...} and never raises.
"""
import json
import os
import re
import socket
import struct
import subprocess
import sys
import sysconfig
import time

HOST_VERSION = "1.3.0"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOGS = os.path.join(ROOT, "logs")
PID_FILE = os.path.join(LOGS, "bridge.pid")
STDOUT_LOG = os.path.join(LOGS, "bridge_stdout.log")
BRIDGE = os.path.join(HERE, "bridge.py")
PORT = int(os.environ.get("ZS_BRIDGE_PORT", "17613"))
IS_WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000          # CREATE_NO_WINDOW
NEW_PROCESS_GROUP = 0x00000200  # CREATE_NEW_PROCESS_GROUP
BREAKAWAY_FROM_JOB = 0x01000000  # CREATE_BREAKAWAY_FROM_JOB
START_LOCK = os.path.join(LOGS, "start.lock")
PROC_CACHE = os.path.join(LOGS, "processes.cache.json")

def _quiet_start():
    """Windows: this host is started by the browser through a .bat launcher, so it
    owns a console. Hide it at once, and make every child we spawn windowless too -
    otherwise each status poll flashes a command prompt. Called from main() only
    (never on import: the installer imports this module and must keep its window)."""
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import winquiet as _winquiet
        _winquiet.install()
        _winquiet.hide_own_console()
    except Exception:
        pass


def _cf():
    """creationflags for helper children (tasklist, powershell, pip...)."""
    return NO_WINDOW if IS_WIN else 0

# Desktop apps worth showing next to the bridge ("everything that is running").
# Matched as SUBSTRINGS of the lowercased executable basename.
APP_PATTERNS = [
    ("Roblox Studio", ("robloxstudiobeta", "robloxstudio")),
    ("Unity Editor", ("unity.exe", "unity hub", "/unity", "unityhub")),
    ("Godot", ("godot",)),
    ("Blender", ("blender",)),
    ("Figma", ("figma",)),
]
# Matched by EQUALITY against the lowercased executable basename.
# macOS and Linux report the binary basename with no extension, and it often
# differs from the Windows image name - the Unity Editor's process is exactly
# "unity", which none of the substring keys above match (that is why Unity was
# never listed on macOS). These must be equality, not substring: "unity" as a
# substring would also match "community" and mislabel an unrelated process.
APP_EXACT = [
    ("Unity Editor", ("unity",)),
    ("Unity Hub", ("unityhub", "unity hub")),
    ("Godot", ("godot",)),
    ("Blender", ("blender",)),
    ("Figma", ("figma",)),
    ("Roblox Studio", ("robloxstudio", "robloxstudiobeta")),
    ("Roblox Player", ("robloxplayer", "robloxplayerbeta")),
]


# ---------------------------------------------------------------- framing
def _read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    (length,) = struct.unpack("<I", raw)
    if length <= 0 or length > 1024 * 1024:
        return {"cmd": "__invalid__"}
    data = sys.stdin.buffer.read(length)
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return {"cmd": "__invalid__"}


def _send(obj):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


# ---------------------------------------------------------------- helpers
def port_listening(port=PORT, timeout=0.4):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _read_pid():
    try:
        with open(PID_FILE, "r", encoding="utf-8") as fh:
            pid = int(fh.read().strip().split()[0])
        return pid if pid > 0 else None
    except Exception:
        return None


def _pid_alive(pid):
    if not pid:
        return False
    if IS_WIN:
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, timeout=8,
                                 creationflags=_cf()).stdout
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def process_table(max_age=0.0):
    """[{pid, ppid, name, cmd}] for the whole machine, best effort.

    `max_age` > 0 re-uses a snapshot written by a previous host process that many
    seconds ago. Every browser request is a fresh host process, so without this a
    status poll would spawn PowerShell (slow, CPU-heavy) every few seconds."""
    if max_age > 0:
        try:
            if time.time() - os.path.getmtime(PROC_CACHE) < max_age:
                with open(PROC_CACHE, "r", encoding="utf-8") as fh:
                    cached = json.load(fh)
                if isinstance(cached, list) and cached:
                    return cached
        except Exception:
            pass
    rows = _process_table_uncached()
    if rows:
        try:
            os.makedirs(LOGS, exist_ok=True)
            with open(PROC_CACHE, "w", encoding="utf-8") as fh:
                json.dump(rows, fh)
        except Exception:
            pass
    return rows


def _process_table_uncached():
    rows = []
    try:
        if IS_WIN:
            ps = ("Get-CimInstance Win32_Process | "
                  "Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress")
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 timeout=20, creationflags=_cf()).stdout
            data = json.loads(out) if out.strip() else []
            if isinstance(data, dict):
                data = [data]
            for p in data:
                rows.append({"pid": int(p.get("ProcessId") or 0), "ppid": int(p.get("ParentProcessId") or 0),
                             "name": p.get("Name") or "", "cmd": p.get("CommandLine") or ""})
        else:
            out = subprocess.run(["ps", "-eo", "pid=,ppid=,comm=,args="], capture_output=True, text=True,
                                 timeout=10).stdout
            for line in out.splitlines():
                parts = line.strip().split(None, 3)
                if len(parts) >= 3 and parts[0].isdigit():
                    rows.append({"pid": int(parts[0]), "ppid": int(parts[1]), "name": parts[2],
                                 "cmd": parts[3] if len(parts) > 3 else parts[2]})
    except Exception:
        pass
    return rows


def _norm_path(p):
    return os.path.normcase(os.path.abspath(p)).replace("\\", "/")


def _is_our_bridge(cmd):
    """True only for `python ... <this folder>/bridge.py` - never another
    program that merely mentions a file called bridge.py. Substring match on the
    normalised absolute path, so folders with spaces ("John Smith") still work."""
    flat = (cmd or "").replace('"', "").replace("\\", "/").lower()
    return _norm_path(BRIDGE).lower() in flat


def find_bridge_pids(rows=None):
    rows = rows if rows is not None else process_table()
    pids = [r["pid"] for r in rows if _is_our_bridge(r["cmd"]) and r["pid"] != os.getpid()]
    pid = _read_pid()
    if pid and pid not in pids and _pid_alive(pid):
        pids.append(pid)
    return pids


def descendants(root, rows):
    kids = {}
    for r in rows:
        kids.setdefault(r["ppid"], []).append(r)
    out, stack = [], list(kids.get(root, []))
    while stack:
        r = stack.pop()
        out.append(r)
        stack.extend(kids.get(r["pid"], []))
    return out


def _short(cmd, n=140):
    cmd = " ".join((cmd or "").split())
    return cmd if len(cmd) <= n else cmd[: n - 1] + "..."


def expected_bridge_version():
    """The BRIDGE_VERSION declared by THIS folder's bridge.py (read as text - the
    bridge is never imported here). The extension compares it with the version
    of the bridge it is connected to, to spot a stale copy still holding the port."""
    try:
        with open(BRIDGE, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = re.match(r'\s*BRIDGE_VERSION\s*=\s*["\']([^"\']+)["\']', line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return ""


def _proc_net_owners(port):
    """Linux without lsof/ss: LISTEN sockets in /proc/net/tcp{,6} -> inode -> owning pid."""
    inodes = set()
    for tbl in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(tbl, "r") as fh:
                next(fh, None)
                for line in fh:
                    f = line.split()
                    if len(f) > 9 and f[3] == "0A" and int(f[1].rsplit(":", 1)[1], 16) == port:
                        inodes.add(f[9])
        except (OSError, ValueError, IndexError):
            continue
    if not inodes:
        return []
    out = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            for fd in os.listdir("/proc/%s/fd" % d):
                try:
                    link = os.readlink("/proc/%s/fd/%s" % (d, fd))
                except OSError:
                    continue
                if link.startswith("socket:[") and link[8:-1] in inodes:
                    out.append(int(d))
                    break
        except OSError:
            continue
    return out


def port_owner_pids(port=PORT):
    """PIDs LISTENING on 127.0.0.1/::1 `port`, best effort, any folder. Windows uses
    netstat (both stacks); POSIX tries lsof, then ss, then /proc."""
    pids = []
    try:
        if IS_WIN:
            for proto in ("TCP", "TCPv6"):
                out = subprocess.run(["netstat", "-ano", "-p", proto], capture_output=True, text=True,
                                     timeout=10, creationflags=_cf()).stdout
                for line in out.splitlines():
                    if "LISTENING" in line and f":{port} " in line:
                        last = line.split()[-1]
                        if last.isdigit() and int(last) > 0 and int(last) not in pids:
                            pids.append(int(last))
        else:
            out = ""
            try:
                out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                                     capture_output=True, text=True, timeout=10).stdout
                for tok in out.split():
                    if tok.isdigit() and int(tok) not in pids:
                        pids.append(int(tok))
            except (OSError, subprocess.SubprocessError):
                pass
            if not pids and sys.platform.startswith("linux"):
                pids.extend(p for p in _proc_net_owners(port) if p not in pids)
            if not pids:
                try:
                    out = subprocess.run(["ss", "-ltnpH", f"sport = :{port}"], capture_output=True, text=True,
                                         timeout=10).stdout
                    for m in re.finditer(r"pid=(\d+)", out):
                        if int(m.group(1)) not in pids:
                            pids.append(int(m.group(1)))
                except (OSError, subprocess.SubprocessError):
                    pass
    except Exception:
        pass
    return pids


def _row_for(pid, rows):
    return next((r for r in rows if r["pid"] == pid), None)


def _is_any_bridge(row):
    """True for `python ... bridge.py` from ANY Multi-Script folder: an old download,
    a previous 6.x copy, the folder the user just moved. Needs a python-like
    executable AND bridge.py as the script, and callers only pass processes that listen on
    OUR port, so an unrelated program that merely mentions bridge.py is never touched."""
    if not row:
        return False
    name = os.path.basename((row.get("name") or "").replace("\\", "/")).lower()
    flat = (row.get("cmd") or "").replace('"', " ").replace("\\", "/").lower()
    if "python" not in name and name not in ("py", "py.exe", "pyw.exe") and "python" not in flat:
        return False
    # Only ever consulted for a process that LISTENS on our port, so a bare
    # `python bridge.py` (started from inside runtime/) counts too.
    return re.search(r"(^|[\s/])bridge\.py(\s|$)", flat) is not None


def _bridge_folder(cmd):
    """The Multi-Script folder (the parent of runtime/) named in a bridge command line."""
    m = re.search(r'((?:[A-Za-z]:[\\/]|/)[^"]*?)[\\/]runtime[\\/]bridge\.py', cmd or "")
    if not m:
        return ""
    # Lazy match starts at the FIRST drive/slash in the line (which can be python.exe's
    # own path), so keep only the part after the last interpreter / option token.
    tail = re.split(r'(?i)\.exe"?\s+(?:-\S+\s+)*|\s-u\s+|\s-X\s+\S+\s+', m.group(1))[-1]
    return tail.strip('" ')


def stale_port_bridges(rows=None):
    """Bridges holding our port that are NOT this folder's: [{pid, cmd, folder}]."""
    rows = rows if rows is not None else process_table()
    out = []
    for pid in port_owner_pids():
        row = _row_for(pid, rows)
        if pid != os.getpid() and _is_any_bridge(row) and not _is_our_bridge(row.get("cmd")):
            out.append({"pid": pid, "cmd": _short(row.get("cmd")), "folder": _bridge_folder(row.get("cmd"))})
    return out


def foreign_port_owners(rows=None):
    """Processes on our port that are NOT a Multi-Script bridge at all."""
    rows = rows if rows is not None else process_table()
    out = []
    for pid in port_owner_pids():
        row = _row_for(pid, rows)
        if pid != os.getpid() and not _is_any_bridge(row):
            out.append({"pid": pid, "name": (row or {}).get("name") or "?", "cmd": _short((row or {}).get("cmd"))})
    return out


# ---------------------------------------------------------------- commands
def cmd_ping(_m):
    return {"ok": True, "hostVersion": HOST_VERSION, "python": sys.executable,
            "pythonVersion": sys.version.split()[0], "platform": sys.platform, "root": ROOT,
            "bridgeFile": os.path.isfile(BRIDGE), "expectedBridgeVersion": expected_bridge_version(),
            "port": PORT}


def _deps_ok():
    try:
        r = subprocess.run([sys.executable, "-c", "import websockets"], capture_output=True, timeout=30,
                           creationflags=_cf())
        return r.returncode == 0
    except Exception:
        return False


def _ensure_deps():
    if _deps_ok():
        return True, ""
    last = ""
    # Several strategies: --user is the normal one; a plain install covers
    # venv / Store Python where --user is refused; --break-system-packages covers
    # "externally managed" Linux/macOS Pythons; ensurepip covers a missing pip.
    attempts = [["--user"], [], ["--user", "--break-system-packages"]]
    for i, extra in enumerate(attempts):
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet"] + extra + ["websockets"],
                               capture_output=True, text=True, timeout=180, creationflags=_cf())
            if r.returncode == 0 and _deps_ok():
                return True, "installed websockets"
            last = (r.stderr or r.stdout or "pip failed").strip()[-400:]
            if i == 0 and "No module named pip" in last:
                subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], capture_output=True,
                               timeout=120, creationflags=_cf())
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
    return False, last


def cmd_start(msg):
    if not os.path.isfile(BRIDGE):
        return {"ok": False, "code": "no_bridge", "error": f"bridge.py not found at {BRIDGE}"}
    if port_listening() and not msg.get("force"):
        return {"ok": True, "already": True, "listening": True, "pids": []}
    ok, why = _ensure_deps()
    if not ok:
        return {"ok": False, "code": "deps", "error": "Could not install the 'websockets' library: " + why}
    os.makedirs(LOGS, exist_ok=True)
    # One start at a time. Two near-simultaneous requests (several tabs, the
    # auto-start plus a click) used to launch two bridges that then killed each
    # other while fighting for the port.
    if not _take_start_lock():
        deadline = time.time() + float(msg.get("wait", 10))
        while time.time() < deadline:
            if port_listening():
                return {"ok": True, "already": True, "listening": True, "pids": []}
            time.sleep(0.25)
        return {"ok": True, "started": True, "listening": False, "note": "Another start is already in progress."}
    try:
        _drop_proc_cache()
        return _spawn_bridge(msg)
    finally:
        _drop_start_lock()


def _take_start_lock():
    try:
        if os.path.exists(START_LOCK) and time.time() - os.path.getmtime(START_LOCK) > 45:
            os.remove(START_LOCK)   # stale (a host that died mid-start)
        fd = os.open(START_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True   # cannot lock (read-only folder?) - do not block the start


def _drop_start_lock():
    try:
        os.remove(START_LOCK)
    except OSError:
        pass


def _spawn_bridge(msg):
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["ZS_STARTED_BY"] = "native-host"
    out = open(STDOUT_LOG, "ab", buffering=0)
    out.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} start requested by the extension =====\n".encode())
    kwargs = {"cwd": HERE, "env": env, "stdin": subprocess.DEVNULL, "stdout": out, "stderr": subprocess.STDOUT}
    if IS_WIN:
        # NEW_PROCESS_GROUP + NO_WINDOW (+ BREAKAWAY when the browser allows it):
        # the bridge survives this host exiting and gets a HIDDEN console that all
        # of its own children (netstat, tasklist, MCP launchers...) inherit.
        #
        # Do NOT add DETACHED_PROCESS here. It overrides NO_WINDOW and leaves the
        # bridge with no console at all, so Windows opens a brand-new visible
        # console window for every console program the bridge launches - the
        # "command prompts rapidly opening and closing" bug of 6.25.0.
        base = NEW_PROCESS_GROUP | NO_WINDOW
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= 0x00000001   # STARTF_USESHOWWINDOW
            si.wShowWindow = 0         # SW_HIDE
            kwargs["startupinfo"] = si
        except Exception:
            pass
        kwargs["creationflags"] = base | BREAKAWAY_FROM_JOB
    else:
        kwargs["start_new_session"] = True
    try:
        try:
            py = [sys.executable]
            if sysconfig.get_config_var("Py_GIL_DISABLED"):
                py += ["-X", "gil=1"]
            proc = subprocess.Popen(py + ["-u", BRIDGE], **kwargs)
        except OSError:
            if not IS_WIN:
                raise
            # The browser's job object forbids breakaway: start without it.
            kwargs["creationflags"] = base
            py = [sys.executable]
            if sysconfig.get_config_var("Py_GIL_DISABLED"):
                py += ["-X", "gil=1"]
            proc = subprocess.Popen(py + ["-u", BRIDGE], **kwargs)
    except Exception as exc:
        return {"ok": False, "code": "spawn", "error": f"{type(exc).__name__}: {exc}"}
    try:
        with open(PID_FILE, "w", encoding="utf-8") as fh:
            fh.write(str(proc.pid))
    except Exception:
        pass
    deadline = time.time() + float(msg.get("wait", 10))
    while time.time() < deadline:
        if port_listening():
            return {"ok": True, "started": True, "listening": True, "pid": proc.pid}
        if proc.poll() is not None:
            return {"ok": False, "code": "exited", "exitCode": proc.returncode,
                    "error": "The bridge exited right after starting.", "tail": _tail(40)}
        time.sleep(0.25)
    return {"ok": True, "started": True, "listening": False, "pid": proc.pid,
            "note": "Bridge process started; it is still booting its engines."}


def _kill_tree(pid):
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=15,
                           creationflags=_cf())
        else:
            import signal
            # Only signal a whole process GROUP when the bridge leads its own (the
            # host starts it with start_new_session). A bridge a user started from a
            # terminal shares that shell's group; killpg would take the shell with it.
            try:
                if os.getpgid(pid) == pid:
                    os.killpg(pid, signal.SIGTERM)
                else:
                    for k in descendants(pid, process_table()):
                        try:
                            os.kill(k["pid"], signal.SIGTERM)
                        except OSError:
                            pass
                    os.kill(pid, signal.SIGTERM)
            except Exception:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
    except Exception:
        pass


def _drop_proc_cache():
    try:
        os.remove(PROC_CACHE)
    except OSError:
        pass


def cmd_stop(_m):
    _drop_proc_cache()
    rows = process_table()
    pids = find_bridge_pids(rows)
    # A bridge from ANOTHER Multi-Script folder (an older download whose launcher
    # started it, or a window the user forgot) keeps the port and keeps answering
    # the extension with its old version. It is a Multi-Script bridge by its command
    # line, so stop/restart takes it down too.
    stale = stale_port_bridges(rows)
    for item in stale:
        if item["pid"] not in pids:
            pids.append(item["pid"])
    if not pids:
        return {"ok": True, "already": True, "stopped": [], "stale": [], "listening": port_listening()}
    for pid in pids:
        _kill_tree(pid)
    deadline = time.time() + 8
    while time.time() < deadline and port_listening():
        time.sleep(0.2)
    if port_listening():
        # One more pass: a supervisor may have respawned it, or the first kill raced.
        rows = process_table()
        for item in stale_port_bridges(rows):
            _kill_tree(item["pid"])
        for pid in find_bridge_pids(rows):
            _kill_tree(pid)
        deadline = time.time() + 4
        while time.time() < deadline and port_listening():
            time.sleep(0.2)
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    _drop_proc_cache()
    return {"ok": True, "stopped": pids, "stale": stale, "listening": port_listening()}


def cmd_restart(msg):
    stopped = cmd_stop(msg)
    time.sleep(0.6)
    if port_listening():
        # Something we may not kill still owns the port. Starting a second bridge
        # would only die on bind and leave the old one answering, so say who it is.
        foreign = foreign_port_owners()
        who = ", ".join("%s (pid %s)" % (f["name"], f["pid"]) for f in foreign) or "an unknown process"
        return {"ok": False, "code": "port_busy", "listening": True, "foreign": foreign,
                "stopped": stopped.get("stopped", []), "stale": stopped.get("stale", []),
                "error": "Port %d is still held by %s, which is not a Multi-Script bridge this launcher may stop. "
                         "Close it (Task Manager) or set ZS_BRIDGE_PORT, then restart." % (PORT, who)}
    out = cmd_start(dict(msg, force=True))
    out["restarted"] = True
    out["stale"] = stopped.get("stale", [])
    out["expectedBridgeVersion"] = expected_bridge_version()
    return out


def cmd_status(_m):
    rows = process_table(max_age=3.0)
    pids = find_bridge_pids(rows)
    return {"ok": True, "hostVersion": HOST_VERSION, "listening": port_listening(), "pids": pids,
            "pidFile": _read_pid(), "pythonVersion": sys.version.split()[0], "root": ROOT,
            "expectedBridgeVersion": expected_bridge_version(), "stale": stale_port_bridges(rows)}


def cmd_processes(_m):
    rows = process_table(max_age=3.0)
    pids = find_bridge_pids(rows)
    procs = []
    seen = set()
    for pid in pids:
        row = next((r for r in rows if r["pid"] == pid), None)
        procs.append({"pid": pid, "role": "bridge", "label": "Multi-Script bridge",
                      "detail": _short(row["cmd"] if row else "bridge.py")})
        seen.add(pid)
        for k in descendants(pid, rows):
            if k["pid"] in seen:
                continue
            seen.add(k["pid"])
            low = (k["cmd"] or k["name"]).lower()
            label = "MCP server"
            for key, nice in (("launch_studio_mcp", "Roblox MCP launcher"), ("studiomcp", "Roblox Studio MCP"),
                              ("launch_unity_mcp", "Unity MCP launcher"), ("launch_godot_mcp", "Godot MCP launcher"),
                              ("godot-mcp", "Godot MCP"), ("unity-mcp", "Unity MCP"), ("blender", "Blender MCP"),
                              ("uvx", "uvx tool server"), ("npx", "npx tool server"), ("node", "Node tool server")):
                if key in low:
                    label = nice
                    break
            procs.append({"pid": k["pid"], "role": "mcp", "label": label, "detail": _short(k["cmd"] or k["name"])})
    apps = []
    for r in rows:
        if r["pid"] in seen:
            continue   # a child of the bridge is an MCP server, not the app itself
        # Match the executable NAME, not the whole command line: "npm exec
        # godot-mcp" mentions Godot but is not the Godot editor.
        low = os.path.basename((r["name"] or "").replace("\\", "/")).lower()
        for nice, keys in APP_PATTERNS:
            if any(k in low for k in keys) and not any(a["label"] == nice for a in apps):
                apps.append({"pid": r["pid"], "role": "app", "label": nice, "detail": _short(r["name"])})
        # Equality pass for the bare POSIX binary names (see APP_EXACT).
        for nice, keys in APP_EXACT:
            if low in keys and not any(a["label"] == nice for a in apps):
                apps.append({"pid": r["pid"], "role": "app", "label": nice, "detail": _short(r["name"])})
    return {"ok": True, "listening": port_listening(), "processes": procs, "apps": apps}


def _tail(n=60):
    try:
        with open(STDOUT_LOG, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 24000))
            text = fh.read().decode("utf-8", "replace")
        text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
        return text.splitlines()[-n:]
    except Exception:
        return []


def cmd_tail(msg):
    n = max(1, min(200, int(msg.get("lines") or 60)))
    return {"ok": True, "lines": _tail(n), "listening": port_listening()}


def cmd_update(msg):
    from update_manager import Updater
    action = msg.get('action', 'status')
    if action not in ('status', 'check', 'apply', 'recover','setup'):
        raise ValueError('Unsupported update action')
    updater = Updater(ROOT)
    # Never stop another process, edit a store install or update during a run.
    # Caller must explicitly stop the bridge before applying/recovering.
    if action in ('apply', 'recover','setup') and (port_listening() or find_bridge_pids()):
        raise ValueError('Stop the Multi-Script bridge before installing an update')
    return getattr(updater, action)()


COMMANDS = {"ping": cmd_ping, "start": cmd_start, "stop": cmd_stop, "restart": cmd_restart,
            "status": cmd_status, "processes": cmd_processes, "tail": cmd_tail, "update": cmd_update}


def handle(msg):
    if not isinstance(msg, dict):
        return {"ok": False, "error": "message must be an object"}
    fn = COMMANDS.get(str(msg.get("cmd") or ""))
    if not fn:
        return {"ok": False, "error": f"unknown command '{msg.get('cmd')}'", "commands": sorted(COMMANDS)}
    try:
        return fn(msg)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main():
    _quiet_start()
    if IS_WIN:
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    while True:
        msg = _read_message()
        if msg is None:
            break
        reply = handle(msg)
        if isinstance(msg, dict) and "id" in msg:
            reply["id"] = msg["id"]
        _send(reply)


if __name__ == "__main__":
    main()
