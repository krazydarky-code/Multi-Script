import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=types.ModuleType("websockets");w.ConnectionClosed=Exception;sys.modules.setdefault("websockets",w)
spec=importlib.util.spec_from_file_location("bridge_virtual",ROOT/"runtime"/"bridge.py");b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class M: pass
def call(n,a): return json.loads(b._builtin_call(n,a,M())["text"])
data=json.load(open(ROOT/"runtime"/"virtual-tools.json"));assert data["total"]==263 and len(data["tools"])==263
assert data["engineCounts"]=={"roblox":90,"unity":70,"godot":70,"blender":33}
for tid,v in data["tools"].items():
 assert len(v["stages"])>=8 and len(v["qualityGates"])>=8
 out=call("ms_run_virtual_tool",{"tool_id":tid,"request":"do it professionally"})
 assert out["silentAugmentation"] and out["preserveExplicitRequirements"] and out["outputContract"]["implementImmediately"]
cases=[("roblox","make me a good ui for this roblox game, classic","ui"),("unity","professional locomotion and combat animation","animation"),("godot","stylized water shader with foam","shader-water"),("blender","model rig texture and export a game character","model-character")]
for engine,request,want in cases:
 out=call("ms_match_virtual_tools",{"request":request,"engine":engine,"limit":5});ids=" ".join(x["id"] for x in out["matches"]);assert want in ids,(engine,ids)
print("PASS 263 virtual tools: every profile runs; matching covers Roblox UI, Unity animation, Godot shaders and Blender characters")
