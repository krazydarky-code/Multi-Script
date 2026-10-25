import importlib.util,json,sys,types
from pathlib import Path
R=Path(__file__).resolve().parents[1];w=types.ModuleType("websockets");w.ConnectionClosed=Exception;sys.modules.setdefault("websockets",w)
s=importlib.util.spec_from_file_location("mesh",R/"runtime"/"bridge.py");b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
class M:
 def health(self):return []
def call(name,args):return json.loads(b._builtin_call(name,args,M())["text"])
assert "ms_quality_multiplier" not in b.BUILTIN_TOOL_NAMES and "ms_adaptive_quality_inference" not in b.BUILTIN_TOOL_NAMES
assert "ms_full_spectrum_skill_mesh" in b.BUILTIN_TOOL_NAMES and "ms_cross_discipline_integration_review" in b.BUILTIN_TOOL_NAMES
for request in ["make a classic character model","make a classic gui","high quality stud texture ui panel","high quality walk dash and punch animation","make it fun"]:
 out=call("ms_studio_director",{"request":request,"engine":"roblox"});assert out["simultaneousCoverage"] and out["simplePromptIsEnough"]
 assert len(out["selectedDirectTools"])>=16 and len(out["selectedSkills"])>=18 and len(out["selectedVirtualTools"])>=15
 assert {"design","implementation","polish","optimization","validation"}.issubset(set(out["coveredSkillRoles"])),out["coveredSkillRoles"]
 assert len(set(out["coveredSkillDomains"]))>=16,out["coveredSkillDomains"]
mesh=call("ms_full_spectrum_skill_mesh",{"request":"make it fun","engine":"roblox"})["skillToolMesh"];assert mesh["simultaneousCoverage"] and len(mesh["skills"])>=18
review=call("ms_cross_discipline_integration_review",{"request":"make it fun","engine":"roblox","evidence":["runtime capture"]});assert review["executionRequired"] and not review["planOnly"]
print("PASS comprehensive skill/tool mesh: weak prompts receive simultaneous specialist coverage without a generic multiplier")
