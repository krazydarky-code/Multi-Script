# SPDX-License-Identifier: GPL-3.0-or-later
"""install_native_host.py - one-time setup that lets the chat bar's terminal icon
start the Multi-Script bridge for you (this replaced the old start.bat launcher).

    python runtime/install_native_host.py              # auto-detect everything
    python runtime/install_native_host.py --extension-id <id> [--extension-id <id2>]
    python runtime/install_native_host.py --uninstall
    python runtime/install_native_host.py --status

What it does (all per-user, nothing needs administrator rights):
  1. checks Python and installs the one dependency (websockets)
  2. writes a tiny launcher next to native_host.py
  3. writes the native-messaging manifest listing ONLY your extension ID(s)
  4. registers that manifest for Chrome, Edge, Brave, Chromium and Vivaldi (+ Beta/Dev/Canary,
     Opera and Arc builds on macOS / Linux)
Run it once. After that the terminal icon starts, stops and watches the bridge.
"""
import argparse
import base64
import glob
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import sysconfig
import threading
import time

HOST_NAME = "com.multiscript.bridge"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXT_DIR = os.path.join(ROOT, "extension")
HOST_PY = os.path.join(HERE, "native_host.py")
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
LOG_DIR = os.path.join(ROOT, "logs")

# (label, windows registry subkey, mac app-support dir, linux config dir)
BROWSERS = [
    ("Chrome", r"Software\Google\Chrome", "Google/Chrome", "google-chrome"),
    ("Edge", r"Software\Microsoft\Edge", "Microsoft Edge", "microsoft-edge"),
    ("Brave", r"Software\BraveSoftware\Brave-Browser", "BraveSoftware/Brave-Browser", "BraveSoftware/Brave-Browser"),
    ("Chromium", r"Software\Chromium", "Chromium", "chromium"),
    ("Vivaldi", r"Software\Vivaldi", "Vivaldi", "vivaldi"),
]
# macOS / Linux only: how to tell a browser is installed even if it was never started
# (its config folder does not exist yet) - (label, [mac app bundle names], [linux commands]).
POSIX_PRESENCE = {
    "Chrome": (["Google Chrome.app"], ["google-chrome", "google-chrome-stable"]),
    "Edge": (["Microsoft Edge.app"], ["microsoft-edge", "microsoft-edge-stable"]),
    "Brave": (["Brave Browser.app"], ["brave-browser", "brave", "brave-browser-stable"]),
    "Chromium": (["Chromium.app"], ["chromium", "chromium-browser"]),
    "Vivaldi": (["Vivaldi.app"], ["vivaldi", "vivaldi-stable"]),
}
# Further Chromium builds that read their own NativeMessagingHosts folder:
# (label, mac app-support dir, linux config dir, mac app bundle, linux command)
POSIX_MORE = [
    ("Chrome Beta", "Google/Chrome Beta", "google-chrome-beta", "Google Chrome Beta.app", "google-chrome-beta"),
    ("Chrome Dev", "Google/Chrome Dev", "google-chrome-unstable", "Google Chrome Dev.app", "google-chrome-unstable"),
    ("Chrome Canary", "Google/Chrome Canary", None, "Google Chrome Canary.app", None),
    ("Edge Beta", "Microsoft Edge Beta", "microsoft-edge-beta", "Microsoft Edge Beta.app", "microsoft-edge-beta"),
    ("Brave Beta", "BraveSoftware/Brave-Browser-Beta", "BraveSoftware/Brave-Browser-Beta", "Brave Browser Beta.app", "brave-browser-beta"),
    ("Opera", "com.operasoftware.Opera", "opera", "Opera.app", "opera"),
    ("Arc", "Arc/User Data", None, "Arc.app", None),
    ("Edge Dev", "Microsoft Edge Dev", "microsoft-edge-dev", "Microsoft Edge Dev.app", "microsoft-edge-dev"),
    ("Edge Canary", "Microsoft Edge Canary", None, "Microsoft Edge Canary.app", None),
    ("Brave Nightly", "BraveSoftware/Brave-Browser-Nightly", "BraveSoftware/Brave-Browser-Nightly", "Brave Browser Nightly.app", "brave-browser-nightly"),
    ("Vivaldi Snapshot", "Vivaldi Snapshot", "vivaldi-snapshot", "Vivaldi Snapshot.app", "vivaldi-snapshot"),
    ("Thorium", "Thorium", "thorium", "Thorium.app", "thorium-browser"),
    ("Chrome for Testing", "Google/Chrome for Testing", "google-chrome-for-testing", "Google Chrome for Testing.app", None),
]
# Browsers packaged as Flatpak / Snap run in a sandbox that cannot start a program from
# your home folder, so the terminal icon cannot work there (the bridge itself still does).
# Detect them to say so instead of failing silently: (label, path relative to $HOME).
SANDBOXED_BROWSER_DIRS = [
    ("Chromium (Snap)", "snap/chromium"), ("Chrome (Flatpak)", ".var/app/com.google.Chrome"),
    ("Chromium (Flatpak)", ".var/app/org.chromium.Chromium"), ("Brave (Flatpak)", ".var/app/com.brave.Browser"),
    ("Edge (Flatpak)", ".var/app/com.microsoft.Edge"), ("Vivaldi (Flatpak)", ".var/app/com.vivaldi.Vivaldi"),
    ("Opera (Flatpak)", ".var/app/com.opera.Opera"), ("Brave (Snap)", "snap/brave"),
]

# Extra Chromium-based browsers that are only used to FIND the extension id (their
# native-messaging lookup reuses the Chrome / Chromium registry keys above).
EXTRA_ROOTS_WIN = [
    ("Opera", r"%APPDATA%\Opera Software\Opera Stable"),
    ("Opera GX", r"%APPDATA%\Opera Software\Opera GX Stable"),
    ("Comet", r"%LOCALAPPDATA%\Perplexity\Comet\User Data"),
    ("Yandex", r"%LOCALAPPDATA%\Yandex\YandexBrowser\User Data"),
    ("Chrome Beta", r"%LOCALAPPDATA%\Google\Chrome Beta\User Data"),
    ("Chrome Dev", r"%LOCALAPPDATA%\Google\Chrome Dev\User Data"),
    ("Edge Beta", r"%LOCALAPPDATA%\Microsoft\Edge Beta\User Data"),
    ("Thorium", r"%LOCALAPPDATA%\Thorium\User Data"),
    ("Arc", r"%LOCALAPPDATA%\Packages\TheBrowserCompany.Arc_ttt1ap7aakyb4\LocalCache\Local\Arc\User Data"),
]
# user-data roots used to auto-detect the unpacked extension's ID
def _user_data_roots():
    home = os.path.expanduser("~")
    out = []
    for label, _reg, mac, lin in BROWSERS:
        if IS_WIN:
            la = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
            sub = {"Chrome": r"Google\Chrome", "Edge": r"Microsoft\Edge", "Brave": r"BraveSoftware\Brave-Browser",
                   "Chromium": "Chromium", "Vivaldi": "Vivaldi"}[label]
            out.append((label, os.path.join(la, sub, "User Data")))
        elif IS_MAC:
            out.append((label, os.path.join(home, "Library", "Application Support", mac)))
        else:
            out.append((label, os.path.join(_xdg_config(), lin)))
    if IS_WIN:
        out.extend((n, os.path.expandvars(p)) for n, p in EXTRA_ROOTS_WIN)
    else:
        for label, base in _posix_more():
            out.append((label, base))
    return out


def _xdg_config():
    """Chromium on Linux follows $XDG_CONFIG_HOME (default ~/.config)."""
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")


def _posix_more():
    """(label, config dir) for the extra Chromium builds on this macOS / Linux machine."""
    home = os.path.expanduser("~")
    out = []
    for label, mac, lin, _app, _cmd in POSIX_MORE:
        if IS_MAC:
            out.append((label, os.path.join(home, "Library", "Application Support", mac)))
        elif lin:
            out.append((label, os.path.join(_xdg_config(), lin)))
    return out


def _installed_posix(label, base, app_names, commands):
    """True when the browser's config folder exists OR the browser itself is installed
    (a browser that was installed but never started has no config folder yet)."""
    if os.path.isdir(base):
        return True
    if IS_MAC:
        home = os.path.expanduser("~")
        return any(os.path.isdir(os.path.join(root, a)) for a in app_names for root in ("/Applications", os.path.join(home, "Applications")))
    return any(shutil.which(c) for c in commands)


def posix_targets():
    """[(label, NativeMessagingHosts dir)] for every supported browser present on macOS / Linux."""
    home = os.path.expanduser("~")
    out = []
    for label, _r, mac, lin in BROWSERS:
        base = os.path.join(home, "Library", "Application Support", mac) if IS_MAC else os.path.join(_xdg_config(), lin)
        apps, cmds = POSIX_PRESENCE.get(label, ([], []))
        if _installed_posix(label, base, apps, cmds):
            out.append((label, os.path.join(base, "NativeMessagingHosts")))
    for label, mac, lin, app, cmd in POSIX_MORE:
        if IS_MAC:
            base = os.path.join(home, "Library", "Application Support", mac)
        elif lin:
            base = os.path.join(_xdg_config(), lin)
        else:
            continue
        if _installed_posix(label, base, [app], [cmd] if cmd else []):
            out.append((label, os.path.join(base, "NativeMessagingHosts")))
    return out


def sandboxed_browsers():
    """Flatpak / Snap browsers found (the terminal icon cannot start programs from inside them)."""
    home = os.path.expanduser("~")
    return [label for label, rel in SANDBOXED_BROWSER_DIRS if not IS_WIN and os.path.isdir(os.path.join(home, rel))]


_LOG_FH = None


def say(msg=""):
    print(msg, flush=True)
    if _LOG_FH:
        try:
            _LOG_FH.write(str(msg) + "\n")
            _LOG_FH.flush()
        except Exception:
            pass


def _open_log():
    global _LOG_FH
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _LOG_FH = open(os.path.join(LOG_DIR, "setup.log"), "a", encoding="utf-8", errors="replace")
        _LOG_FH.write("\n===== setup %s  python %s  %s =====\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), sys.version.split()[0], sys.platform))
    except Exception:
        _LOG_FH = None


def manifest_extension_id():
    """The extension id that extension/manifest.json's pinned "key" produces.
    Chrome derives an unpacked extension's id from its key (or, with no key, from
    the folder path - which is why the id used to change whenever the folder
    moved). Computing it here means Setup never has to guess or ask."""
    try:
        with open(os.path.join(EXT_DIR, "manifest.json"), "r", encoding="utf-8") as fh:
            key = json.load(fh).get("key")
        if not key:
            return None
        digest = hashlib.sha256(base64.b64decode(key)).hexdigest()[:32]
        return "".join(chr(ord("a") + int(c, 16)) for c in digest)
    except Exception:
        return None


def norm(p):
    return os.path.normcase(os.path.realpath(p)).rstrip("\\/")


def detect_extension_ids():
    """Find IDs of Chromium extensions loaded unpacked from OUR extension folder."""
    found = {}
    want = norm(EXT_DIR)
    seen_roots = set()
    for label, root in _user_data_roots():
        if not os.path.isdir(root) or norm(root) in seen_roots:
            continue
        seen_roots.add(norm(root))
        for pref in glob.glob(os.path.join(root, "*", "Preferences")) + glob.glob(os.path.join(root, "*", "Secure Preferences")):
            try:
                with open(pref, "r", encoding="utf-8", errors="replace") as fh:
                    data = json.load(fh)
                settings = ((data.get("extensions") or {}).get("settings")) or {}
            except Exception:
                continue
            for eid, info in settings.items():
                path = (info or {}).get("path")
                if not (isinstance(path, str) and path and re.fullmatch(r"[a-p]{32}", eid)):
                    continue
                # Same folder as this Setup, OR any other unpacked copy of
                # Multi-Script (an older download in another folder has a
                # different id and must be allowed too).
                name = str(((info or {}).get("manifest") or {}).get("name") or "")
                if norm(path) == want or ("Multi-Script" in name and os.path.basename(path.rstrip("\\/")).lower() == "extension"):
                    found.setdefault(eid, label)
    return found


def check_python():
    if sys.version_info < (3, 9):
        say(f"  x Python {sys.version.split()[0]} is too old - the bridge needs 3.9 or newer.")
        say("    Install the current Python from https://www.python.org/downloads/ (tick 'Add to PATH').")
        return False
    say(f"  ok Python {sys.version.split()[0]}  ({sys.executable})")
    return True


def ensure_pillow():
    try:
        from PIL import ImageGrab
        say("  ok Pillow screen recording backend present")
        return True
    except ImportError:
        pass
    say("  .. installing Pillow for bounded screen recording...")
    for extra in ([], ["--user"]):
        try:
            result = subprocess.run([sys.executable, "-m", "pip", "install"] + extra + ["Pillow"])
            if result.returncode == 0: return True
        except OSError:
            pass
    say("  x Install Pillow with this Python before using screen recording.")
    return False


def ensure_websockets():
    try:
        __import__("websockets")
        say("  ok websockets library present")
        return True
    except ImportError:
        pass
    say("  .. installing the websockets library (first time only)...")
    attempts = [["--user"], [], ["--user", "--break-system-packages"]]
    for i, extra in enumerate(attempts):
        r = subprocess.run([sys.executable, "-m", "pip", "install"] + extra + ["websockets"])
        if r.returncode == 0:
            say("  ok websockets installed")
            return True
        if i == 0:
            subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], capture_output=True)
    say("  x pip could not install websockets (no internet, firewall, or no pip).")
    say("    Try:  " + sys.executable + " -m pip install websockets      then run this setup again.")
    return False


def write_launcher():
    if IS_WIN:
        path = os.path.join(HERE, "native_host.bat")
        with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
            # No `exit /b` tricks and no echo: stdout is the native-messaging pipe, so
            # the batch file must not print anything of its own.
            gil = ' -X gil=1' if sysconfig.get_config_var("Py_GIL_DISABLED") else ''
            fh.write('@echo off\r\n"%s"%s "%s" %%*\r\n' % (sys.executable, gil, HOST_PY))
        return path
    path = os.path.join(HERE, "native_host.sh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, HOST_PY))
    os.chmod(path, 0o755)
    return path


def manifest_for(launcher, ids):
    return {
        "name": HOST_NAME,
        "description": "Multi-Script bridge launcher (starts runtime/bridge.py for the extension's terminal icon)",
        "path": launcher,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{i}/" for i in ids],
    }


def register(manifest_path):
    done = []
    if IS_WIN:
        import winreg
        for label, reg, _m, _l in BROWSERS:
            try:
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg + r"\NativeMessagingHosts" + "\\" + HOST_NAME)
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, manifest_path)
                winreg.CloseKey(key)
                done.append(label)
            except OSError:
                pass
        return done
    text = open(manifest_path, encoding="utf-8").read()
    for label, d in posix_targets():
        try:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, HOST_NAME + ".json"), "w", encoding="utf-8") as fh:
                fh.write(text)
            done.append(label)
        except OSError as exc:
            say("  ! could not write the %s registration (%s)" % (label, exc))
    return done


def unregister():
    removed = []
    if IS_WIN:
        import winreg
        for label, reg, _m, _l in BROWSERS:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, reg + r"\NativeMessagingHosts" + "\\" + HOST_NAME)
                removed.append(label)
            except OSError:
                pass
    else:
        home = os.path.expanduser("~")
        dirs = []
        for label, _r, mac, lin in BROWSERS:
            base = os.path.join(home, "Library", "Application Support", mac) if IS_MAC else os.path.join(_xdg_config(), lin)
            dirs.append((label, os.path.join(base, "NativeMessagingHosts")))
        dirs.extend((label, os.path.join(base, "NativeMessagingHosts")) for label, base in _posix_more())
        for label, d in dirs:
            f = os.path.join(d, HOST_NAME + ".json")
            if os.path.isfile(f):
                os.remove(f)
                removed.append(label)
    return removed


def self_test(launcher, timeout=25):
    """Talk to the registered launcher exactly like the browser does (4-byte
    length + JSON on stdin, same on stdout). Proves the .bat/.sh, the interpreter
    path and native_host.py work BEFORE the user restarts the browser."""
    try:
        payload = json.dumps({"cmd": "ping"}).encode("utf-8")
        flags = 0x08000000 if IS_WIN else 0
        proc = subprocess.Popen([launcher], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=flags)
        result = {}

        def work():
            try:
                proc.stdin.write(struct.pack("<I", len(payload)) + payload)
                proc.stdin.flush()
                head = proc.stdout.read(4)
                if len(head) == 4:
                    (n,) = struct.unpack("<I", head)
                    result["reply"] = json.loads(proc.stdout.read(n).decode("utf-8"))
            except Exception as exc:
                result["error"] = str(exc)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(timeout)
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        reply = result.get("reply")
        if reply and reply.get("ok"):
            return True, reply
        err = ""
        try:
            err = (proc.stderr.read(600) or b"").decode("utf-8", "replace").strip()
        except Exception:
            pass
        return False, result.get("error") or err or "no reply from the launcher"
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)


def bridge_version_on_port(port, timeout=6.0):
    """(version, root) of the bridge on `port` - see bridge_status.probe."""
    sys.path.insert(0, HERE)
    import bridge_status
    return bridge_status.probe(port, timeout)


def replace_bridge(keep_running=False):
    """Make the bridge on the port the one from THIS folder.

    Earlier Setup versions only started a bridge when the port was free, so an old bridge
    (previous download, a window left open, another folder's launcher) kept the port and the
    new extension kept talking to it - the "bridge v6.25.0 ... does not expose the Software
    Builder tools" error. Now any Multi-Script bridge on the port is stopped first (it only
    stops processes whose command line is a Multi-Script runtime/bridge.py) and this
    folder's bridge is started and verified."""
    try:
        sys.path.insert(0, HERE)
        import native_host as nh
        want = nh.expected_bridge_version()
        if nh.port_listening():
            have, root = bridge_version_on_port(nh.PORT)
            if keep_running and have == want:
                say("  ok bridge v%s already running on port %d" % (have, nh.PORT))
                return True
            # Default: ALWAYS restart, even when the version matches - the files in this folder
            # may have changed without a version bump. --keep-running opts out (handled above).
            say("  .. a bridge%s is already running%s - restarting it from this folder (v%s)" % (
                " v" + have if have else "", " from " + root if root else "", want))
            r = nh.cmd_restart({"wait": 15})
            for item in r.get("stale") or []:
                say("     stopped stale bridge pid %s %s" % (item.get("pid"), item.get("folder") or ""))
        else:
            r = nh.cmd_start({"wait": 15})
        if not r.get("ok"):
            say("  ! bridge did not start: " + str(r.get("error") or r.get("code")))
            if r.get("code") == "port_busy":
                say("    Close that program, or run:  set ZS_BRIDGE_PORT=17614  and Setup again.")
            return False
        have, root = bridge_version_on_port(nh.PORT)
        if have is None:
            # A freshly started bridge needs a few seconds before it answers.
            for _ in range(10):
                time.sleep(1.0)
                have, root = bridge_version_on_port(nh.PORT)
                if have is not None:
                    break
        if have == want:
            say("  ok bridge v%s is running on port %d" % (have, nh.PORT))
            return True
        say("  ! the bridge on port %d reports v%s but this folder is v%s." % (nh.PORT, have or "?", want))
        say("    Close every 'Multi-Script bridge' / python window, then run Setup again.")
        return False
    except Exception as exc:  # never fail the install over the optional start
        say("  ! could not start the bridge now: " + str(exc))
        return False


def manifest_path():
    return os.path.join(HERE, HOST_NAME + ".json")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Register the Multi-Script terminal host with your browser.")
    ap.add_argument("--extension-id", action="append", default=[], help="extension ID (chrome://extensions, Developer mode)")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--no-pause", action="store_true")
    ap.add_argument("--no-start", action="store_true", help="register only; do not start the bridge now")
    ap.add_argument("--keep-running", action="store_true", help="leave an already-running bridge of the same version alone")
    ap.add_argument("--skip-deps", action="store_true", help="do not pip-install websockets (offline/testing)")
    ap.add_argument('--post-update',action='store_true',help='Refresh this installed version without starting the bridge or scanning other unpacked copies')
    a = ap.parse_args(argv)

    say()
    say("  === Multi-Script - terminal setup ===")
    say()
    if a.uninstall:
        say("  removed from: " + (", ".join(unregister()) or "(nothing was registered)"))
        return 0
    if a.status:
        say("  manifest : " + (manifest_path() if os.path.isfile(manifest_path()) else "not written"))
        if os.path.isfile(manifest_path()):
            say("  allowed  : " + ", ".join(json.load(open(manifest_path())).get("allowed_origins", [])))
        return 0

    say("  [1/4] Python")
    if not check_python():
        return 1
    say("  [2/4] Dependency")
    if not a.skip_deps and not (ensure_websockets() and ensure_pillow()):
        return 1

    say("  [3/4] Finding your Multi-Script extension")
    ids = [i.strip() for i in a.extension_id if i.strip()]
    for i in ids:
        if not re.fullmatch(r"[a-p]{32}", i):
            say(f"  x '{i}' is not a valid extension ID (32 letters a-p).")
            return 1
    # 1) the id the shipped manifest pins - works without any detection at all
    pinned = manifest_extension_id()
    if pinned:
        say(f"  ok built-in extension id: {pinned}")
        if pinned not in ids:
            ids.append(pinned)
    # 2) every unpacked Multi-Script copy the browsers already know about
    auto = {} if a.post_update else detect_extension_ids()
    for eid, browser in auto.items():
        say(f"  ok also found in {browser}: {eid}")
        if eid not in ids:
            ids.append(eid)
    # 3) ids from a previous run, so a second browser/profile is additive
    if os.path.isfile(manifest_path()):
        try:
            for o in json.load(open(manifest_path())).get("allowed_origins", []):
                m = re.fullmatch(r"chrome-extension://([a-p]{32})/", o)
                if m and m.group(1) not in ids:
                    ids.append(m.group(1))
        except Exception:
            pass
    if not ids:
        say("  ! No extension id available (the manifest has no key and none was found).")
        say("    1) Open chrome://extensions (or edge://extensions), turn on Developer mode")
        say("    2) Load unpacked ->  " + EXT_DIR)
        say("    3) Copy the ID shown on the Multi-Script card, then run:")
        say("       python runtime/install_native_host.py --extension-id <that id>")
        return 2
    say("    (after this step, load/reload the extension from: " + EXT_DIR + ")")

    say("  [4/4] Registering the host")
    launcher = write_launcher()
    with open(manifest_path(), "w", encoding="utf-8") as fh:
        json.dump(manifest_for(launcher, ids), fh, indent=2)
    where = register(manifest_path())
    if not where:
        if sandboxed_browsers():
            say("  ! Only sandboxed (Flatpak/Snap) browsers were found - they cannot launch the host.")
            say("    Run the bridge yourself with  bash Start.sh  - the extension connects to it the same way.")
            return 0
        say("  x No supported browser found to register with (looked for Chrome, Edge, Brave, Chromium, Vivaldi, Opera, Arc).")
        say("    Install one, or run the bridge directly with  bash Start.sh  (macOS/Linux)  /  Start.bat  (Windows).")
        return 1
    say("  ok registered for: " + ", ".join(where))
    sb = sandboxed_browsers()
    if sb:
        say("  ! Found sandboxed browser(s): " + ", ".join(sb) + ".")
        say("    A Flatpak/Snap browser cannot start programs from your home folder, so its terminal icon cannot")
        say("    start the bridge. Everything else works: run  bash Start.sh  once per session (or use a .deb/.rpm/tarball browser).")
    ok, info = self_test(launcher)
    if ok:
        say("  ok launcher answers (host v%s, Python %s)" % (info.get("hostVersion"), info.get("pythonVersion")))
    else:
        say("  ! launcher self-test FAILED: " + str(info))
        say("    Details are in logs/setup.log. The bridge can still be run with " + ("Start.bat." if IS_WIN else "bash Start.sh."))
        return 1
    expected=json.load(open(os.path.join(EXT_DIR,'manifest.json'),encoding='utf-8'))['version']
    if (info.get('root') and os.path.normcase(os.path.realpath(info['root']))!=os.path.normcase(os.path.realpath(ROOT))) or (info.get('expectedBridgeVersion') and info['expectedBridgeVersion']!=expected):
        say('  x Launcher answered from a different installation/version. Setup is incomplete.');return 1
    if a.post_update and (not info.get('root') or info.get('expectedBridgeVersion')!=expected):
        say('  x Updated launcher identity was not verified.');return 1
    from pathlib import Path
    from update_manager import write_json,safe_path
    home=safe_path(Path(ROOT),'.updates');home.mkdir(exist_ok=True)
    try:
        import obsidian_vault
        vault=obsidian_vault.setup()
        say('  ok Obsidian vault connected: '+vault['vault'])
    except (OSError,ValueError,RuntimeError) as error:
        say('  x Obsidian vault setup failed: '+str(error))
        say('    Choose a writable dedicated vault with MS_OBSIDIAN_VAULT, then rerun Setup. Existing notes and engine data were preserved.')
        return 1
    write_json(home/'setup-complete.json',{'version':expected,'root':os.path.realpath(ROOT),'at':int(time.time()),'launcherVerified':True})
    if not a.no_start and not a.skip_deps and not a.post_update:
        replace_bridge(a.keep_running)
    say()
    say("  Done. Fully restart the browser once (close ALL its windows), reload the")
    say("  Multi-Script extension, open any supported AI chat and click the terminal")
    say("  icon in the Multi-Script bar. It starts the bridge for you from then on.")
    say("  (No browser integration yet? " + ("Start.bat" if IS_WIN else "bash Start.sh") + " in this folder runs the bridge directly.)")
    say()
    return 0


if __name__ == "__main__":
    _open_log()
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    except BaseException:
        import traceback
        say("  x Setup crashed:")
        say(traceback.format_exc())
        code = 1
    if IS_WIN and "--no-pause" not in sys.argv and sys.stdin and sys.stdin.isatty():
        try:
            input("  Press Enter to close...")
        except EOFError:
            pass
    sys.exit(code)
