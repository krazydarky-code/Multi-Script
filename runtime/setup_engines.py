#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""setup_engines.py - one-time, best-effort engine prerequisites.

Called by Setup.bat / Setup.sh after the native host is registered. Everything
here is ADVISORY: it never fails the setup. It makes the three optional engines
(Unity, Godot, Blender) as close to plug-and-play as possible:

  1. uv/uvx    - needed by the Unity and Blender launchers. If missing, we try
                 the official installer (astral.sh). Offline or refused? We say
                 exactly what to type later.
  2. BlenderMCP add-on - downloaded into runtime/addons/blender-mcp-addon.py so
                 the user can install it from Blender's Preferences without
                 hunting GitHub.
  3. config.json - gets the bundled Blender entry if it has none, so the bridge
                 tries the launcher as soon as Blender's add-on is connected.
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADDON_DIR = HERE / "addons"
ADDON_FILE = ADDON_DIR / "blender-mcp-addon.py"
ADDON_URL = "https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py"
UV_INSTALL_PS = 'irm https://astral.sh/uv/install.ps1 | iex'
UV_INSTALL_SH = 'curl -LsSf https://astral.sh/uv/install.sh | sh'

def say(msg=""):
    print(msg, flush=True)

def find_uvx():
    override = os.environ.get("ZS_UVX_PATH")
    if override and Path(override).expanduser().is_file():
        return str(Path(override).expanduser())
    found = shutil.which("uvx")
    if found:
        return found
    home = Path.home()
    cands = [home / ".local" / "bin" / ("uvx.exe" if os.name == "nt" else "uvx"),
             home / ".cargo" / "bin" / ("uvx.exe" if os.name == "nt" else "uvx")]
    if os.name == "nt":
        for key in ("LOCALAPPDATA", "APPDATA"):
            if os.environ.get(key):
                cands.append(Path(os.environ[key]) / "uv" / "bin" / "uvx.exe")
    for c in cands:
        if c.is_file():
            return str(c)
    return None

def try_install_uv():
    """Attempt the official uv install. Returns True when uvx works afterwards."""
    try:
        if os.name == "nt":
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", UV_INSTALL_PS],
                           timeout=600, check=False)
        else:
            subprocess.run(["sh", "-c", UV_INSTALL_SH], timeout=600, check=False)
    except Exception as exc:
        say(f"  … automatic uv install could not run ({exc}).")
        return False
    return find_uvx() is not None

def fetch_blender_addon():
    if ADDON_FILE.is_file() and ADDON_FILE.stat().st_size > 2000:
        say(f"  ok BlenderMCP add-on already downloaded: {ADDON_FILE}")
        return True
    try:
        ADDON_DIR.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(ADDON_URL, headers={"User-Agent": "Multi-Script-Setup"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) < 2000 or b"BlenderMCP" not in data:
            raise ValueError("download looked wrong - leaving it out")
        ADDON_FILE.write_bytes(data)
        say(f"  ok BlenderMCP add-on saved to: {ADDON_FILE}")
        return True
    except Exception as exc:
        say(f"  … could not download the BlenderMCP add-on ({exc}).")
        say(f"     Later: download addon.py from the blender-mcp project and save it as {ADDON_FILE}")
        return False

def ensure_blender_config():
    cfg_path = HERE / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {"mcpServers": {}}
        servers = cfg.setdefault("mcpServers", {})
        if "blender" in servers:
            say("  ok config.json already has a blender entry")
            return True
        servers["blender"] = {"command": "launch_blender_mcp.py", "args": []}
        import tempfile
        fd, tmp = tempfile.mkstemp(prefix="config.", suffix=".tmp", dir=HERE, text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2); f.write("\n")
        os.replace(tmp, cfg_path)
        say("  ok added the bundled Blender launcher to config.json")
        return True
    except Exception as exc:
        say(f"  … could not update config.json ({exc}); you can add Blender later in Settings → Engines.")
        return False

def check_node():
    """Godot's server runs via npx. Advisory check with per-OS hints."""
    npx = shutil.which("npx")
    if npx:
        say(f"  ok npx found: {npx}  (Godot server can start)")
        return
    say("  … npx (Node.js) not found - Godot needs it. Install Node.js LTS:")
    if sys.platform == "darwin":
        say("       macOS:   brew install node   or   https://nodejs.org/")
    elif os.name == "nt":
        say("       Windows: winget install OpenJS.NodeJS.LTS   or   https://nodejs.org/")
    else:
        say("       Linux:   sudo apt install nodejs npm   (or your distro's nodejs package) / https://nodejs.org/")

def main():
    say("")
    say("  Engine extras (optional engines: Unity, Godot, Blender)")
    uvx = find_uvx()
    if uvx:
        say(f"  ok uvx found: {uvx}  (Unity + Blender servers can start)")
    else:
        say("  … uvx not found - Unity and Blender need it. Trying the official installer…")
        if try_install_uv():
            say(f"  ok uv installed: {find_uvx()}")
        else:
            say("     Install it later with:")
            say(f"       Windows PowerShell:  {UV_INSTALL_PS}")
            say(f"       macOS / Linux:       {UV_INSTALL_SH}")
    check_node()
    fetch_blender_addon()
    ensure_blender_config()
    if os.name=='nt' and os.environ.get('MS_BLENDER_SKIP_PREPARE')!='1':
        try:
            import blender_portable
            say('  Preparing the Blender Workspace runtime (one-time download, about 380 MB on Windows x64)…')
            executable=blender_portable.prepare(progress=lambda **x:say('  '+x['message']) if x.get('message') else None)
            say('  ok Blender Workspace ready: '+executable)
        except Exception as exc:
            say('  … Blender Workspace can finish preparation later in Settings → Engines: '+str(exc))
    say("")
    say("  Remaining per-engine clicks (also in Settings → Engines → Engine setup guides):")
    say("    Roblox Studio: open a place, enable Studio's MCP server in its Assistant/MCP settings.")
    say("    Unity:  add the MCP-for-Unity package to the open project, start its window's server.")
    say("    Godot:  open the project that has project.godot (Node.js/npx needed).")
    if ADDON_FILE.is_file():
        say(f"    Blender: Edit → Preferences → Add-ons → Install… → pick")
        say(f"             {ADDON_FILE}")
        say("             then N-panel → BlenderMCP → Connect to MCP server.")
    else:
        say("    Blender: install the BlenderMCP add-on, then N-panel → BlenderMCP → Connect.")
    say("    Then press 'Restart MCP servers' in Settings → Engines.")
    say('    Blender Workspace: Settings → Engines → Open Blender Workspace. No add-on or desktop window required.')
    return 0

if __name__ == "__main__":
    sys.exit(main())
