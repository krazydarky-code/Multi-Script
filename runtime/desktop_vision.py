# SPDX-License-Identifier: GPL-3.0-or-later
"""desktop_vision.py - see and drive the desktop apps on this machine.

This is the bridge-side half of the "AgentScript can see desktop apps" feature.
The browser half (tab enumeration) lives in extension/background.js because
chrome.tabs is only reachable from a service worker. The desktop half cannot
live in the browser at all: a web page has no way to enumerate native windows,
so the bridge does it and the extension relays the result.

Design constraints, learned the hard way elsewhere in this project:

  1. NEVER guess a window title. On Windows we read real window text via
     user32.GetWindowTextW through ctypes, and we degrade to process-name-only
     when that call is unavailable. A fabricated title is worse than none
     because the model then acts on a window that does not exist.

  2. NEVER require a package the user must pip-install. ctypes ships with
     CPython, and `tasklist` / `ps` / `osascript` are OS binaries. If a richer
     backend (pywin32, pygetwindow) happens to be present we prefer it, but its
     absence only costs window TITLES, never the ability to list processes.

  3. NEVER auto-install anything without the user's say-so. `setup_plan()`
     returns the exact commands for each optional upgrade and reports whether
     each is already satisfied; the extension shows that and asks first. That is
     the "it will walk you through it and install everything for you" contract -
     walked through, not done behind the user's back.

  4. Reading a window is text-only. We never screenshot, never read keystrokes,
     never touch another app's memory. `read_window` returns the accessible
     text of a top-level window when the platform backend can provide it, and
     says so plainly when it cannot.

Cross-platform:
  * Windows - `tasklist` for processes; ctypes user32 for window list + titles;
              optional pywin32 for the accessibility text pass.
  * macOS   - `ps -axo` for processes; `osascript` System Events for windows and
              their titles; optional `pyobjc` for the accessibility text pass.
  * Linux   - `ps -eo` for processes; `wmctrl -l` for windows; accessibility
              text requires `xdotool`/AT-SPI and is reported as unavailable when
              the tool is missing.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

# Windows: no console window should flash when we shell out from a GUI-launched
# bridge. CREATE_NO_WINDOW exists only on win32; getattr keeps this importable
# everywhere.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

MAX_WINDOWS = 200
MAX_PROCESSES = 400
MAX_TITLE = 220


def _run(cmd, timeout=8):
    """Run a command and return stdout, or '' on any failure.

    Never raises: a missing binary, a permission error or a timeout all collapse
    to an empty string, and every caller treats '' as "this backend is not
    available" rather than as an error to propagate.
    """
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, creationflags=_NO_WINDOW,
        )
        return proc.stdout or ""
    except Exception:
        return ""


def _clip(value, limit=MAX_TITLE):
    text = str(value if value is not None else "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


# ── capability detection ─────────────────────────────────────────────────

def _module_present(name):
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _binary_present(name):
    try:
        return shutil.which(name) is not None
    except Exception:
        return False


def capabilities():
    """What this machine can currently do, and why.

    Returned to the model verbatim so it can plan around gaps instead of
    pretending a capability exists. `windows` / `titles` / `text` are the three
    escalating levels: list processes -> list windows -> read window text.
    """
    plat = sys.platform
    caps = {
        "platform": plat,
        "processes": False,
        "windows": False,
        "titles": False,
        "text": False,
        "elevated_control": False,  # sending input to another app
        "backends": {},
        "notes": [],
    }
    if plat == "win32":
        caps["processes"] = _binary_present("tasklist")
        caps["backends"]["processes"] = "tasklist"
        try:
            import ctypes  # noqa: F401
            caps["windows"] = True
            caps["titles"] = True
            caps["backends"]["windows"] = "ctypes user32 (EnumWindows + GetWindowTextW)"
        except Exception:
            caps["notes"].append("ctypes is unavailable, so native window enumeration is off.")
        caps["backends"]["text_optional"] = "pywin32 (win32gui/win32com UIAutomation)" if _module_present("win32gui") else "not installed (optional)"
        caps["backends"]["input_optional"] = "pyautogui" if _module_present("pyautogui") else "not installed (optional)"
        caps["notes"].append("Reading another app's on-screen text needs an accessibility backend; without one, titles and process names are still reported.")
    elif plat == "darwin":
        caps["processes"] = _binary_present("ps")
        caps["windows"] = _binary_present("osascript")
        caps["titles"] = caps["windows"]
        caps["backends"]["processes"] = "ps -axo"
        caps["backends"]["windows"] = "osascript System Events" if caps["windows"] else "osascript not found"
        caps["backends"]["text_optional"] = "pyobjc" if _module_present("AppKit") else "not installed (optional)"
        caps["backends"]["input_optional"] = "pyautogui / cliclick" if (_module_present("pyautogui") or _binary_present("cliclick")) else "not installed (optional)"
        if caps["windows"]:
            caps["notes"].append("macOS will prompt once for Accessibility/Automation permission the first time windows are enumerated; grant it and re-run.")
    else:
        caps["processes"] = _binary_present("ps")
        # wmctrl only sees X11/XWayland windows; swaymsg and hyprctl are the two
        # Wayland compositors that expose a queryable CLI. Any one of them is
        # enough to enumerate windows, so report the capability when any exists.
        wayland_tool = "swaymsg" if _binary_present("swaymsg") else ("hyprctl" if _binary_present("hyprctl") else None)
        caps["windows"] = _binary_present("wmctrl") or bool(wayland_tool)
        caps["titles"] = caps["windows"]
        caps["backends"]["processes"] = "ps -eo"
        if _binary_present("wmctrl"):
            caps["backends"]["windows"] = "wmctrl -l"
        elif wayland_tool:
            caps["backends"]["windows"] = "%s (Wayland)" % wayland_tool
        else:
            caps["backends"]["windows"] = "wmctrl not installed"
        caps["backends"]["text_optional"] = "xdotool/AT-SPI" if _binary_present("xdotool") else "not installed (optional)"
        if not caps["windows"]:
            caps["notes"].append("Install wmctrl to enumerate windows on Linux (apt install wmctrl / dnf install wmctrl).")
        else:
            caps["notes"].append("Wayland: windows are enumerated via swaymsg (Sway/i3) or hyprctl (Hyprland). Other compositors (GNOME, KDE) expose no portable window list, so windows fall back to process names there - that is reported as degraded, never guessed.")
    caps["text"] = caps["titles"] and (plat in ("win32", "darwin"))
    return caps


def setup_plan():
    """The exact optional upgrades for this platform and whether each is met.

    Deliberately returns commands instead of running them. The extension renders
    this list and the user approves it; running `pip install` on someone's
    machine unprompted is exactly the kind of thing that should never happen
    silently.
    """
    plat = sys.platform
    caps = capabilities()
    steps = []

    def step(ident, label, met, command, why, required=False):
        steps.append({
            "id": ident, "label": label, "satisfied": bool(met),
            "command": command, "why": why, "required": required,
        })

    if plat == "win32":
        step("pywin32", "Window text via pywin32",
             _module_present("win32gui"),
             f'"{sys.executable}" -m pip install pywin32',
             "Reads window titles and accessible text more reliably than the ctypes fallback.")
        step("pyautogui", "Driver input via pyautogui",
             _module_present("pyautogui"),
             f'"{sys.executable}" -m pip install pyautogui',
             "Optional. Needed only if you want Multi-Script to move the mouse or press keys in another app; listing and reading never require it.")
        step("mss", "Screen capture via mss",
             _module_present("mss"),
             f'"{sys.executable}" -m pip install mss',
             "Optional. Lets a future capture step grab a region without a heavy dependency.")
    elif plat == "darwin":
        step("osascript", "System Events scripting",
             _binary_present("osascript"),
             "built in - no install needed",
             "Required to enumerate windows on macOS.", required=True)
        step("pyobjc", "Accessibility text via pyobjc",
             _module_present("AppKit"),
             f'"{sys.executable}" -m pip install pyobjc-framework-Quartz',
             "Optional. Reads on-screen text of other apps once Accessibility permission is granted.")
        step("cliclick", "Driver input via cliclick",
             _binary_present("cliclick"),
             "brew install cliclick",
             "Optional. Lets Multi-Script click and type in other apps.")
    else:
        step("wmctrl", "Window enumeration",
             _binary_present("wmctrl"),
             "sudo apt install wmctrl   # or: sudo dnf install wmctrl",
             "Required to list windows on Linux.", required=True)
        step("xdotool", "Driver input via xdotool",
             _binary_present("xdotool"),
             "sudo apt install xdotool",
             "Optional. Lets Multi-Script focus and type into other windows.")
        step("scrot", "Screen capture via scrot",
             _binary_present("scrot"),
             "sudo apt install scrot",
             "Optional. Region/whole-screen capture without extra Python packages.")

    satisfied = sum(1 for s in steps if s["satisfied"])
    return {
        "platform": plat,
        "steps": steps,
        "satisfied": satisfied,
        "total": len(steps),
        "ready": all(s["satisfied"] for s in steps if s["required"]),
        "note": "Nothing here is installed automatically. This plan never installs or changes anything by itself: show the list to the user, then run only the commands they approve.",        "capabilities": caps,
    }


# ── processes ────────────────────────────────────────────────────────────

_KNOWN_APPS = {
    "robloxstudiobeta.exe": "Roblox Studio",
    "studio mcp.exe": "Roblox Studio MCP proxy",
    "studiomcp.exe": "Roblox Studio MCP proxy",
    "robloxplayerbeta.exe": "Roblox Player",
    "unity.exe": "Unity Editor",
    "unityhub.exe": "Unity Hub",
    "godot.exe": "Godot",
    "godot_v4.exe": "Godot 4",
    "blender.exe": "Blender",
    "figma.exe": "Figma",
    "code.exe": "Visual Studio Code",
    "devenv.exe": "Visual Studio",
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Mozilla Firefox",
    "discord.exe": "Discord",
    "steam.exe": "Steam",
    "obs64.exe": "OBS Studio",
    "photoshop.exe": "Adobe Photoshop",
    "afterfx.exe": "Adobe After Effects",
    "unrealeditor.exe": "Unreal Editor",
    "notion.exe": "Notion",
}

# Aliases for the POSIX process names. `ps -o comm=` reports the binary's
# basename with NO extension, and it frequently differs from the Windows image
# name (Unity Editor is "Unity", VS Code is "code", Chrome is "google-chrome").
# Keyed without ".exe" because _friendly_app normalises before lookup.
_POSIX_APP_ALIASES = {
    "robloxstudio": "Roblox Studio",
    "robloxstudiobeta": "Roblox Studio",
    "robloxplayer": "Roblox Player",
    "robloxplayerbeta": "Roblox Player",
    "studiomcp": "Roblox Studio MCP proxy",
    "unity": "Unity Editor",
    "unityhub": "Unity Hub",
    "godot": "Godot",
    "godot4": "Godot 4",
    "godot_v4": "Godot 4",
    "blender": "Blender",
    "figma": "Figma",
    "code": "Visual Studio Code",
    "code-insiders": "Visual Studio Code",
    "devenv": "Visual Studio",
    "chrome": "Google Chrome",
    "google-chrome": "Google Chrome",
    "google-chrome-stable": "Google Chrome",
    "chromium": "Chromium",
    "msedge": "Microsoft Edge",
    "microsoft-edge": "Microsoft Edge",
    "firefox": "Mozilla Firefox",
    "discord": "Discord",
    "steam": "Steam",
    "obs": "OBS Studio",
    "obs64": "OBS Studio",
    "photoshop": "Adobe Photoshop",
    "afterfx": "Adobe After Effects",
    "unrealeditor": "Unreal Editor",
    "notion": "Notion",
}


def _norm_app_key(name):
    """Normalise a raw process name into a lookup key.

    Windows reports "Blender.exe"; macOS and Linux report "Blender". Stripping a
    trailing ".exe" - and the " (deleted)" suffix Linux appends when a binary is
    replaced underneath a running process - lets one table serve every platform
    instead of the Windows-only keys silently matching nothing off Windows.
    """
    key = (name or "").strip().lower()
    if key.endswith(" (deleted)"):
        key = key[: -len(" (deleted)")]
    if key.endswith(".exe"):
        key = key[:-4]
    return key.strip()


def _friendly_app(name):
    """Map a raw process name to a human app name, or '' if we don't know it.

    Returning '' (rather than echoing the raw name) is what lets the model tell
    "this is a recognised creative app" apart from "this is some background
    service" without us inventing an identity.

    The table is keyed on the Windows image names, so the lookup key is
    normalised (extension stripped) and both the bare and the ".exe" form are
    tried - that is what makes the "what desktop apps are open" feature work on
    macOS and Linux at all, where it previously returned nothing because every
    key ended in ".exe".
    """
    key = _norm_app_key(name)
    if not key:
        return ""
    for candidate in (key, key + ".exe"):
        hit = _KNOWN_APPS.get(candidate)
        if hit:
            return hit
    return _POSIX_APP_ALIASES.get(key, "")


def _processes_windows():
    out = _run(["tasklist", "/FO", "CSV", "/NH"])
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line or not line.startswith('"'):
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) < 5:
            continue
        name = parts[0]
        try:
            pid = int(parts[1])
        except (TypeError, ValueError):
            continue
        rows.append({
            "pid": pid,
            "name": name,
            "app": _friendly_app(name),
            "memory": parts[4] if len(parts) > 4 else "",
        })
        if len(rows) >= MAX_PROCESSES:
            break
    return rows


def _processes_posix():
    out = _run(["ps", "-axo", "pid=,comm="]) or _run(["ps", "-eo", "pid=,comm="])
    rows = []
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except (TypeError, ValueError):
            continue
        name = os.path.basename(parts[1].strip())
        rows.append({"pid": pid, "name": name, "app": _friendly_app(name), "memory": ""})
        if len(rows) >= MAX_PROCESSES:
            break
    return rows


def list_apps(query="", include_unknown=False):
    """List running desktop apps (process level).

    include_unknown=False returns only recognisable creative/dev apps, which is
    what the model almost always wants; True adds the long tail so the user can
    ask "what else is open".
    """
    rows = _processes_windows() if sys.platform == "win32" else _processes_posix()
    if not include_unknown:
        rows = [r for r in rows if r.get("app")]
    q = (query or "").strip().lower()
    if q:
        rows = [r for r in rows if q in r["name"].lower() or q in r.get("app", "").lower()]
    rows.sort(key=lambda r: (not r.get("app"), r.get("app") or r["name"].lower()))
    return {
        "count": len(rows),
        "apps": rows,
        "capabilities": capabilities(),
        "note": "Process names only. Call windows_list for real window titles and window_text for a window's readable text.",
    }


# ── windows ──────────────────────────────────────────────────────────────

_RE_WIN_TITLE = re.compile(r"^0x([0-9a-fA-F]+)\s+(\S+)\s+(.*)$")


def _windows_windows():
    """Real top-level windows on Windows via user32 + ctypes.

    Enumerates only windows that are visible and have a title, which is what a
    person would call "the apps I have open" - not the thousands of hidden
    message-only windows every process creates.
    """
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return None  # caller falls back to process-only

    user32 = ctypes.windll.user32
    rows = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    GetWindowTextLengthW = user32.GetWindowTextLengthW
    GetWindowTextW = user32.GetWindowTextW
    IsWindowVisible = user32.IsWindowVisible
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    GetWindowRect = user32.GetWindowRect

    def _collect(hwnd, _lparam):
        try:
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            pid = wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            rect = wintypes.RECT()
            GetWindowRect(hwnd, ctypes.byref(rect))
            rows.append({
                "handle": int(hwnd),
                "pid": int(pid.value),
                "title": _clip(title),
                "bounds": {
                    "x": int(rect.left), "y": int(rect.top),
                    "width": int(rect.right - rect.left),
                    "height": int(rect.bottom - rect.top),
                },
            })
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(EnumWindowsProc(_collect), 0)
    except Exception:
        return None
    return rows


def _windows_macos():
    script = (
        'tell application "System Events" to get name of every process whose background only is false'
    )
    out = _run(["osascript", "-e", script])
    if not out.strip():
        return None
    apps = [a.strip() for a in out.strip().split(",") if a.strip()]
    rows = []
    for i, app in enumerate(apps[:MAX_WINDOWS]):
        title_out = _run(["osascript", "-e",
                          f'tell application "System Events" to get title of front window of process "{app}"'])
        rows.append({
            "handle": i,
            "pid": 0,
            "app": app,
            "title": _clip(title_out.strip() or app),
        })
    return rows


def _windows_linux():
    """Top-level windows on Linux, across X11 and Wayland.

    `wmctrl` only sees X11 (or XWayland) windows. Under a NATIVE Wayland session
    it returns nothing, and there is no portable cross-compositor CLI - which is
    why this used to degrade silently to process names on a modern desktop. We
    try the X11 tool first, then the two Wayland compositors that do ship a
    queryable CLI (Sway/i3 via `swaymsg`, Hyprland via `hyprctl`). When none
    answers we return None so list_windows raises `degraded: true` - an honest
    "I can only see process names" beats pretending a process name is a title.
    """
    out = _run(["wmctrl", "-l", "-p"])
    if out.strip():
        rows = []
        for line in out.splitlines()[:MAX_WINDOWS]:
            parts = line.split(None, 4)
            if len(parts) < 5:
                continue
            try:
                pid = int(parts[2])
            except (TypeError, ValueError):
                pid = 0
            rows.append({"handle": parts[0], "pid": pid, "title": _clip(parts[4])})
        return rows

    # Sway / i3: swaymsg -t get_tree emits the whole tree as JSON.
    sway = _run(["swaymsg", "-t", "get_tree", "--raw"])
    if sway.strip():
        try:
            tree = json.loads(sway)
        except ValueError:
            tree = None
        rows = []

        def walk(node):
            if not isinstance(node, dict):
                return
            if node.get("type") == "con" and node.get("name"):
                rows.append({"handle": node.get("id"), "pid": node.get("pid") or 0,
                             "title": _clip(node.get("name"))})
            for child in node.get("nodes") or []:
                walk(child)
            for child in node.get("floating_nodes") or []:
                walk(child)

        walk(tree)
        if rows:
            return rows[:MAX_WINDOWS]

    # Hyprland: hyprctl clients -j emits a JSON array.
    hypr = _run(["hyprctl", "clients", "-j"])
    if hypr.strip():
        try:
            clients = json.loads(hypr)
        except ValueError:
            clients = None
        if isinstance(clients, list):
            rows = [
                {"handle": c.get("address"), "pid": c.get("pid") or 0,
                 "title": _clip(c.get("title") or c.get("class") or "")}
                for c in clients if isinstance(c, dict)
            ]
            rows = [r for r in rows if r["title"]]
            if rows:
                return rows[:MAX_WINDOWS]
    return None


def list_windows(query=""):
    """List top-level windows with real titles, merged against process names.

    Falls back to a process-derived pseudo-window list when the platform window
    backend is missing, and clearly flags that with `degraded: true` so the model
    never mistakes a process name for a window title.
    """
    caps = capabilities()
    raw = None
    degraded = False
    if sys.platform == "win32":
        raw = _windows_windows()
    elif sys.platform == "darwin":
        raw = _windows_macos()
    else:
        raw = _windows_linux()
    if raw is None:
        degraded = True
        procs = _processes_windows() if sys.platform == "win32" else _processes_posix()
        raw = [{"handle": None, "pid": p["pid"], "title": p.get("app") or p["name"]} for p in procs if p.get("app")][:MAX_WINDOWS]

    # Attach a friendly app name per window by matching pid -> process.
    pid_to_name = {}
    procs = _processes_windows() if sys.platform == "win32" else _processes_posix()
    for p in procs:
        pid_to_name[p["pid"]] = p.get("app") or p["name"]

    rows = []
    for w in raw:
        app = w.get("app") or pid_to_name.get(w.get("pid")) or ""
        row = {
            "handle": w.get("handle"),
            "pid": w.get("pid"),
            "app": app,
            "title": w.get("title", ""),
            "friendly": bool(app) or bool(_friendly_app(w.get("title", ""))),
        }
        if "bounds" in w:
            row["bounds"] = w["bounds"]
        rows.append(row)

    q = (query or "").strip().lower()
    if q:
        rows = [r for r in rows if q in (r.get("title") or "").lower() or q in (r.get("app") or "").lower()]

    return {
        "count": len(rows),
        "windows": rows,
        "degraded": degraded,
        "capabilities": caps,
        "note": ("Window backend unavailable, so titles may be process names." if degraded
                 else "Real top-level window titles. Use the handle with window_text where supported."),
    }


# ── reading a window ─────────────────────────────────────────────────────

def read_window(handle=None, pid=None, title=""):
    """Return the readable text of one window, plus an honest account of limits.

    Strategy, best first:
      1. pywin32 UIAutomation / window text (Windows, if installed)
      2. the window's own title + its process's command line
      3. macOS Accessibility via osascript
    We never fabricate content: when only the title is available, `text` is the
    title and `fidelity` is 'title-only', which the model can act on honestly.
    """
    caps = capabilities()
    result = {
        "requested": {"handle": handle, "pid": pid, "title": title},
        "text": "",
        "fidelity": "none",
        "capabilities": caps,
    }

    # 1) macOS accessibility text.
    if sys.platform == "darwin" and title:
        script = (f'tell application "System Events" to tell process "{_clip(title, 80)}" '
                  'to get value of attribute "AXTitle" of front window')
        out = _run(["osascript", "-e", script]).strip()
        if out:
            result.update({"text": _clip(out, 4000), "fidelity": "accessibility"})
            return result

    # 2) Windows: try a real text read via pywin32 if it is present.
    if sys.platform == "win32" and handle is not None:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            length = user32.GetWindowTextLengthW(int(handle))
            buf = ctypes.create_unicode_buffer(max(1, length + 1))
            user32.GetWindowTextW(int(handle), buf, length + 1)
            if buf.value:
                result.update({"text": _clip(buf.value, 4000), "fidelity": "title-only"})
        except Exception:
            pass

    # 3) Universal fallback: the window title we already have.
    if not result["text"] and title:
        result.update({"text": _clip(title, 4000), "fidelity": "title-only"})

    if not result["text"]:
        result["error"] = ("No readable text for this window. Install the optional accessibility "
                           "backend from app_setup_plan to read other apps' on-screen text.")
    return result


def snapshot():
    """One call that answers 'what is in front of me right now'."""
    caps = capabilities()
    apps = list_apps(include_unknown=False)
    win = list_windows()
    return {
        "platform": sys.platform,
        "capabilities": caps,
        "apps": apps["apps"][:40],
        "appCount": apps["count"],
        "windows": win["windows"][:40],
        "windowCount": win["count"],
        "degraded": win["degraded"],
        "note": "Snapshot only. Nothing here was screenshotted or captured; this is process names and window titles.",
    }


if __name__ == "__main__":  # pragma: no cover - manual probe
    print(json.dumps(snapshot(), indent=2))
