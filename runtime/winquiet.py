# SPDX-License-Identifier: GPL-3.0-or-later
"""winquiet.py - stop Windows from flashing a console window for every child process.

WHY THIS EXISTS
On Windows, when a process that has NO console (for example the bridge started
by the browser's terminal icon) launches a console program such as netstat,
tasklist, taskkill, powershell or python, Windows gives that child a brand-new
console window. The bridge does this constantly (port probes, Studio watch,
MCP launcher restarts), which looked like "a bunch of command prompts rapidly
opening and closing" the moment the browser opened.

install() makes every subprocess.Popen / subprocess.run in THIS process default
to CREATE_NO_WINDOW. It does nothing on macOS/Linux, and it can be switched off
with the environment variable ZS_SHOW_CONSOLES=1 (for debugging).
"""
import os
import subprocess
import sys

CREATE_NEW_CONSOLE = 0x00000010
DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000


def install():
    """Idempotent. Returns True when the patch is active."""
    if sys.platform != "win32" or os.environ.get("ZS_SHOW_CONSOLES") == "1":
        return False
    if getattr(subprocess.Popen, "_zs_quiet", False):
        return True
    orig = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):
        # args[13] would be a positional creationflags; leave those calls alone.
        if len(args) < 14:
            flags = kwargs.get("creationflags", 0) or 0
            if not flags & (CREATE_NEW_CONSOLE | DETACHED_PROCESS):
                kwargs["creationflags"] = flags | CREATE_NO_WINDOW
        orig(self, *args, **kwargs)

    subprocess.Popen.__init__ = __init__
    subprocess.Popen._zs_quiet = True
    return True


def hide_own_console():
    """Hide the console window attached to THIS process (if any). Used by the
    native-messaging host: a .bat launcher can briefly show a console."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
            return True
    except Exception:
        pass
    return False
