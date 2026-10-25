# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared SIGTERM/SIGHUP forwarding for the MCP launcher wrappers.

Every engine MCP server is started through a small Python wrapper
(launch_studio_mcp.py, launch_blender_mcp.py, launch_unity_mcp.py,
launch_godot_mcp.py) which spawns the real server as a child and forwards stdio.

The bridge stops a server by closing its stdin and then terminating the WRAPPER
(see MCPClient.stop). On Windows that termination is `taskkill /F /T`, which
takes the whole process tree. On macOS and Linux it is a plain SIGTERM to the
wrapper alone - so without a handler the wrapper died and the real server
(StudioMCP, or the uvx/npx process) was orphaned, still holding its port and any
project lock.

`launch_studio_mcp.py` always had this handling; the other three did not. It now
lives here so all four behave identically and a fifth launcher cannot forget it.

Nothing in here may write to stdout: stdout is the MCP protocol channel.
"""
from __future__ import annotations

import signal
import sys


def forward_signals(proc):
    """Make SIGTERM/SIGHUP terminate `proc` before this wrapper exits.

    No-op on Windows, where the bridge already kills the whole tree with
    `taskkill /F /T` and where SIGHUP does not exist.

    Returns the list of signal names that were installed (useful in tests).
    """
    if sys.platform == "win32":
        return []

    installed = []

    def _forward(_signum, _frame):
        try:
            proc.terminate()
        except Exception:
            pass

    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _forward)
            installed.append(name)
        except (ValueError, OSError):
            # Not the main thread, or the signal is unavailable: skip it.
            pass
    return installed
