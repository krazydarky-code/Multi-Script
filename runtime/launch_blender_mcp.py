# SPDX-License-Identifier: GPL-3.0-or-later
"""Launch the Blender MCP server (blender-mcp) over stdio for the Multi-Script bridge.

The server talks to the "BlenderMCP" add-on running inside Blender (Blender ->
Edit -> Preferences -> Add-ons -> install addon.py from the blender-mcp project,
then N-panel -> BlenderMCP -> Connect to MCP server, default 127.0.0.1:9876).

stdout belongs to the MCP protocol: this launcher never prints to it.
Environment: ZS_UVX_PATH (uvx binary), ZS_BLENDER_MCP_VERSION (pin a release),
BLENDER_HOST / BLENDER_PORT (passed through to the server).
"""
from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path

# Sibling module: the bridge launches us by path (so our directory is already on
# sys.path), but tests and tooling import us directly, where it is not.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_child_signals import forward_signals  # noqa: E402  (path inserted above)
from launcher_env import EX_CONFIG, child_cwd, child_env, exit_code  # noqa: E402


def find_uvx():
    override = os.environ.get("ZS_UVX_PATH")
    if override and Path(override).expanduser().is_file():
        return str(Path(override).expanduser())
    found = shutil.which("uvx")
    if found:
        return found
    home = Path.home()
    cands = [home / ".local" / "bin" / ("uvx.exe" if sys.platform == "win32" else "uvx")]
    if sys.platform == "win32":
        for key in ("LOCALAPPDATA", "APPDATA"):
            if os.environ.get(key):
                cands.append(Path(os.environ[key]) / "uv" / "bin" / "uvx.exe")
    for c in cands:
        if c.is_file():
            return str(c)
    return None


def build_command(uvx, version=""):
    spec = "blender-mcp" + (("==" + version) if version else "")
    cmd = [uvx, spec]
    if sys.platform == "win32" and uvx.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd.exe", "/c"] + cmd
    return cmd


def main():
    uvx = find_uvx()
    if not uvx:
        sys.stderr.write("launch_blender_mcp: uvx was not found. Install uv from https://docs.astral.sh/uv/getting-started/installation/, restart the bridge, or set ZS_UVX_PATH.\n")
        return EX_CONFIG
    version = os.environ.get("ZS_BLENDER_MCP_VERSION", "").strip()
    cmd = build_command(uvx, version)
    sys.stderr.write("launch_blender_mcp: starting blender-mcp%s via %s\n" % (("==" + version) if version else "", uvx))
    sys.stderr.flush()
    # child_env() adds a portable realpath for uv's shims on older macOS, and a
    # neutral cwd keeps a broken shim from exec'ing "./python" in runtime/.
    proc = subprocess.Popen(cmd + sys.argv[1:], env=child_env(), cwd=child_cwd())
    # On macOS/Linux the bridge stops us with a bare SIGTERM; without forwarding
    # it the wrapper dies and the uvx server is orphaned holding its lock.
    forward_signals(proc)
    try:
        return exit_code(proc.wait())
    except KeyboardInterrupt:
        proc.terminate()
        return 130


if __name__ == "__main__":
    sys.exit(main())
