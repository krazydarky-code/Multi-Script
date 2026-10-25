import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=types.ModuleType("websockets");w.ConnectionClosed=Exception;sys.modules.setdefault("websockets",w)
sp=importlib.util.spec_from_file_location("roblox_v3",ROOT/"runtime"/"bridge.py");b=importlib.util.module_from_spec(sp);sp.loader.exec_module(b)
assert len(b.ROBLOX_STUDIO_V3_CONTRACTS)==24
assert len(b.BUILTIN_TOOLS)==279 and len(b.BUILTIN_TOOL_NAMES)==279
for name,spec in b.ROBLOX_STUDIO_V3_CONTRACTS.items():
 assert name in b.BUILTIN_TOOL_BY_NAME and len(spec["stages"])==8 and len(spec["qualityGates"])==8
 out=json.loads(b._builtin_call(name,{"engine":"roblox","feature":"professional test"},object())["text"])
 assert out["providerModelOwnsExecution"] and out["realImplementationRequired"]
v=json.load(open(ROOT/"runtime/virtual-tools.json")); assert v["total"]==263 and v["engineCounts"]["roblox"]==90
rv=[x for x in v["tools"].values() if x["engine"]=="roblox"];assert len(rv)==90
for x in rv:
 assert x["professionalRevision"]=="roblox-studio-v3" and x["outputContract"]["robloxStudioV3"]
 assert len(x["stages"])>=8 and len(x["qualityGates"])>=8 and len(x["robloxStudioStandards"])==5
sk={k:{**json.load(open(ROOT/"runtime/skill-shared-policy.json")),**v} for k,v in json.load(open(ROOT/"runtime/skills.json")).items()};rs=[x for x in sk.values() if x.get("engine")=="roblox"];assert len(rs)==54
for x in rs:
 assert x["qualityProfile"]=="studio-v4-project-aware"
 for key in ("architecturePolicy","platformPolicy","studioEvidencePolicy","securityPolicy"): assert x.get(key)
plugin=(ROOT/"roblox-plugin/MultiScriptCompanion.server.lua").read_text()
companion=json.load(open(ROOT/"runtime/roblox-plugin-tools.json"))["tools"]
assert len(companion)==26 and all(t["permission"] in {"read","project","full"} for t in companion)
assert all(("handlers."+t["name"]+"=") in plugin for t in companion) and "loadstring(" not in plugin
print("PASS Roblox Studio v3: direct/virtual/skill layers plus 26 secure opt-in companion tools")
