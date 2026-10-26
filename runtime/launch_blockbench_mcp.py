# SPDX-License-Identifier: GPL-3.0-or-later
"""Launch only a prepared, pinned Blockbench runtime; stdout is MCP-only."""
import subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import winquiet
winquiet.install()
from launcher_env import EX_CONFIG,child_env,exit_code
from mcp_child_signals import forward_signals
import blockbench_workspace

def main():
    try:command=blockbench_workspace.command()
    except (RuntimeError,OSError,ValueError) as error:
        print('[blockbench] '+str(error),file=sys.stderr);return EX_CONFIG
    child=subprocess.Popen(command,cwd=str(blockbench_workspace.cache_root()),env=child_env(),stdin=sys.stdin,stdout=sys.stdout,stderr=sys.stderr)
    forward_signals(child)
    return exit_code(child.wait())
if __name__=='__main__':raise SystemExit(main())
