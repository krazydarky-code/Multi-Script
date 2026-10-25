import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];w=types.ModuleType("websockets");w.ConnectionClosed=Exception;sys.modules.setdefault("websockets",w)
sp=importlib.util.spec_from_file_location("b64",ROOT/"runtime/bridge.py");b=importlib.util.module_from_spec(sp);sp.loader.exec_module(b)
class M: pass
cases={"make me an RPG":"rpg","make a horror game":"horror","make a platformer":"platformer","make a racing game":"racing","make a survival game":"survival","make a tycoon simulator":"simulation"}
for engine in ("roblox","unity","godot","blender"):
 for prompt,signal in cases.items():
  out=json.loads(b._builtin_call("ms_studio_director",{"request":prompt,"engine":engine},M())["text"]);assert signal in out["interpretedIntent"]["signals"]
  assert len(out["interpretedIntent"]["productPillars"])>=2 and len(out["interpretedIntent"]["verticalSlice"])>=4
  assert len(out["selectedSkills"])==30 and len(out["selectedVirtualTools"])==24
assert all(len(x.get("capabilityLifecycle",[]))==8 and len(x.get("antiShallowRules",[]))==4 for x in b.ADVANCED_DIRECT_CONTRACTS.values())
sk={k:{**json.load(open(ROOT/"runtime/skill-shared-policy.json")),**v} for k,v in json.load(open(ROOT/"runtime/skills.json")).items()};assert len(sk)==249 and all(len(x.get("capabilityLifecycle",[]))==8 and x.get("collaborationPolicy") for x in sk.values())
v=json.load(open(ROOT/"runtime/virtual-tools.json"))["tools"];assert len(v)==263 and all(len(x.get("capabilityLifecycle",[]))==8 and x.get("adaptiveDepthPolicy") for x in v.values())
st=json.load(open(ROOT/"runtime/studio-standard.json"));assert st["version"]=="12.1" and len(st["capabilityMentalModel"])==6 and len(st["developmentLifecycle"])==8 and st["promptRewriting"]["independentFromCapabilityEnhancement"] and st["menuSettingsCoverage"] and st["portableSettings"]
print("PASS 6.4 universal capability foundation: every tool/skill deepened; six broad genres route to complete product meshes")
