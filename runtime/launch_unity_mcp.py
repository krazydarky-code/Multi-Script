# SPDX-License-Identifier: GPL-3.0-or-later
"""Launch CoplayDev MCP for Unity v10.2.0 over stdio.

The Unity package must be installed in the open Unity project. The Python server
is resolved by uvx and pinned so a future upstream release cannot silently break
an existing Multi-Script bundle. Override uvx with ZS_UVX_PATH and the package
version with ZS_UNITY_MCP_VERSION when deliberately testing another release.
"""
from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path

# Sibling module: the bridge launches us by path (so our directory is already on
# sys.path), but tests and tooling import us directly, where it is not.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_child_signals import forward_signals  # noqa: E402  (path inserted above)
from launcher_env import EX_CONFIG, child_cwd, child_env, exit_code  # noqa: E402

DEFAULT_VERSION = "10.2.0"

def find_uvx():
    override=os.environ.get("ZS_UVX_PATH")
    if override and Path(override).expanduser().is_file(): return str(Path(override).expanduser())
    found=shutil.which("uvx")
    if found: return found
    home=Path.home()
    candidates=[home/".local"/"bin"/("uvx.exe" if sys.platform=="win32" else "uvx")]
    if sys.platform=="win32":
        for key in ("LOCALAPPDATA","APPDATA"):
            if os.environ.get(key): candidates.append(Path(os.environ[key])/"uv"/"bin"/"uvx.exe")
    for item in candidates:
        if item.is_file(): return str(item)
    return None

def main():
    uvx=find_uvx()
    if not uvx:
        sys.stderr.write("launch_unity_mcp: uvx was not found. Install uv from https://docs.astral.sh/uv/getting-started/installation/, restart this bridge, and keep Unity open with the MCP for Unity package installed.\n")
        return EX_CONFIG
    version=os.environ.get("ZS_UNITY_MCP_VERSION",DEFAULT_VERSION).strip() or DEFAULT_VERSION
    cmd=[uvx,"--from",f"mcpforunityserver=={version}","mcp-for-unity","--transport","stdio"]+sys.argv[1:]
    sys.stderr.write(f"launch_unity_mcp: starting CoplayDev MCP for Unity {version} via {uvx}\n"); sys.stderr.flush()
    if sys.platform=="win32" and uvx.lower().endswith((".cmd",".bat")):
        cmd=["cmd.exe","/c"]+cmd
    proc=subprocess.Popen(cmd, env=child_env(), cwd=child_cwd())
    # macOS/Linux: the bridge stops us with a bare SIGTERM, so forward it to the
    # real server instead of orphaning it (it would keep its project lock).
    forward_signals(proc)
    try: return exit_code(proc.wait())
    except KeyboardInterrupt:
        proc.terminate(); return proc.wait()

if __name__=="__main__": raise SystemExit(main())
