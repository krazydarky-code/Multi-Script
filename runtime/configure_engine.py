#!/usr/bin/env python3
"""Safely add/update a stdio MCP server in Multi-Script config.json."""
import argparse, json, os, shlex, tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description="Configure a Unity/Godot/Unreal/Blender or other stdio MCP server")
p.add_argument("engine", choices=["unity","godot","unreal","blender","figma","custom"])
p.add_argument("--id", dest="server_id")
p.add_argument("--command", default="", help="Exact stdio start command from that MCP server's documentation (optional for blender/figma: the bundled launcher is used)")
p.add_argument("--env-json", default="{}", help="Optional JSON object of environment variables")
a=p.parse_args()
sid=(a.server_id or a.engine).strip().lower()
if sid=="roblox" or not sid or not all(c.isalnum() or c in "-_" for c in sid): p.error("id must use letters/numbers/-/_ and cannot be roblox")
if not a.command and a.engine in {"blender","figma"}: a.command="launch_"+a.engine+"_mcp.py"
if not a.command: p.error("--command is required for this engine")
parts=shlex.split(a.command, posix=os.name!="nt")
if not parts: p.error("command is empty")
try: env=json.loads(a.env_json)
except Exception as e: p.error(f"invalid --env-json: {e}")
if not isinstance(env,dict): p.error("--env-json must be a JSON object")
path=HERE/'config.json'
cfg=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'mcpServers':{}}
cfg.setdefault('mcpServers',{})[sid]={'command':parts[0],'args':parts[1:]}
if env: cfg['mcpServers'][sid]['env']={str(k):str(v) for k,v in env.items()}
fd,tmp=tempfile.mkstemp(prefix='config.',suffix='.tmp',dir=HERE,text=True)
with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(cfg,f,indent=2); f.write('\n')
os.replace(tmp,path)
print(f"Configured {sid}. Restart the Multi-Script bridge to connect it.")
