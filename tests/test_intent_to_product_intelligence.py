import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];w=types.ModuleType("websockets");w.ConnectionClosed=Exception;sys.modules.setdefault("websockets",w)
sp=importlib.util.spec_from_file_location("b63",ROOT/"runtime"/"bridge.py");b=importlib.util.module_from_spec(sp);sp.loader.exec_module(b)
class M: pass
for engine in ("roblox","unity","godot","blender"):
 out=json.loads(b._builtin_call("ms_studio_director",{"request":"Make me realistic graphics, and a shooter game","engine":engine},M())["text"])
 intent=out["interpretedIntent"];assert intent["signals"]==["shooter","realistic-graphics"]
 assert len(intent["productPillars"])>=7 and len(intent["professionalDefaults"])>=9 and len(intent["verticalSlice"])>=10 and len(intent["acceptanceCriteria"])>=8
 for name in ("ms_realistic_art_production","ms_pbr_material_studio","ms_lighting_production","ms_shader_production","ms_combat_system_design","ms_combat_feel_director","ms_camera_system_design","ms_input_mapping_plan","ms_ai_behavior_design","ms_animation_state_machine"): assert name in out["selectedDirectTools"],(engine,name)
 assert len(out["selectedSkills"])==30 and len(out["selectedVirtualTools"])==24 and len(out["executionPattern"])==7
assert all(len(x.get("contributionContract",[]))==6 and x.get("weakPromptPolicy") and x.get("evidencePolicy") for x in b.ADVANCED_DIRECT_CONTRACTS.values())
sk={k:{**json.load(open(ROOT/"runtime/skill-shared-policy.json")),**v} for k,v in json.load(open(ROOT/"runtime/skills.json")).items()};assert len(sk)==249 and all(len(x.get("contributionContract",[]))==6 and len(x.get("qualityDimensions",[]))==8 for x in sk.values())
v=json.load(open(ROOT/"runtime/virtual-tools.json"))["tools"];assert len(v)==263 and all(len(x.get("concreteContribution",[]))==7 and len(x.get("integrationChecklist",[]))==7 and len(x.get("qualityDimensions",[]))==8 for x in v.values())
config=(ROOT/"extension/core/config.js").read_text();assert "CAPABILITY VISIBILITY" in config and "only the engine's real commands change the project" in config
print("PASS 6.3 intent-to-product: all tools/skills enriched; realistic shooter becomes a coherent verified vertical slice")
