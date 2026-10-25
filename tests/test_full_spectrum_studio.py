import importlib.util,json,sys,types
from pathlib import Path
r=Path(__file__).resolve().parents[1];w=types.ModuleType("websockets");w.ConnectionClosed=Exception;sys.modules.setdefault("websockets",w);sp=importlib.util.spec_from_file_location("b",r/"runtime/bridge.py");b=importlib.util.module_from_spec(sp);sp.loader.exec_module(b)
class M:
 def health(self):return []
m=M();assert len(b.BUILTIN_TOOLS)==279 and len(b.STUDIO_DIRECT_CONTRACTS)==47
for req,eng,expected in [("make a beautiful animated Roblox combat system","roblox","ms_roblox_animation_studio"),("polish this shop GUI","unity","ms_unity_ui_studio"),("make a professional character model","blender","ms_blender_model_studio")]:
 d=json.loads(b._builtin_call("ms_studio_director",{"request":req,"engine":eng},m)["text"]);assert d["hiddenCoordination"] and d["simultaneousCoverage"] and d["neverSubstitutePlanForDeliverable"] and expected in d["selectedDirectTools"] and len(d["selectedSkills"])>=18
listing=json.loads(b._builtin_call("ms_list_direct_tools",{"category":"animation","limit":100},m)["text"]);assert listing["totalMatches"]==14
d=json.loads(b._builtin_call("ms_direct_tool_details",{"tool":"ms_roblox_animation_studio"},m)["text"]);assert len(d["contract"]["stages"])==8 and len(d["contract"]["qualityGates"])==8
print("PASS full-spectrum studio coordination: concrete animation, UI, modeling and all supporting disciplines")
