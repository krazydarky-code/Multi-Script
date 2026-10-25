import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];w=types.ModuleType("websockets");w.ConnectionClosed=Exception;sys.modules.setdefault("websockets",w)
sp=importlib.util.spec_from_file_location("b62",ROOT/"runtime/bridge.py");b=importlib.util.module_from_spec(sp);sp.loader.exec_module(b)
assert len(b.ENGINE_PRO_V3_CONTRACTS)==12 and len(b.BUILTIN_TOOLS)==279
for n,c in b.ENGINE_PRO_V3_CONTRACTS.items(): assert len(c["stages"])==8 and len(c["qualityGates"])==8 and n in b.BUILTIN_TOOL_BY_NAME
v=json.load(open(ROOT/"runtime/virtual-tools.json"));assert v["total"]==263 and v["engineCounts"]=={"roblox":90,"unity":70,"godot":70,"blender":33}
for eng in ("unity","godot","blender"):
 rows=[x for x in v["tools"].values() if x["engine"]==eng];assert len(rows)==v['engineCounts'][eng]
 assert all(x.get("professionalRevision")==eng+"-professional-v3" and x["outputContract"].get("engineProfessionalV3") for x in rows)
for name in ("arena","chatgpt","deepseek"):
 text=(ROOT/"extension/providers"/(name+".js")).read_text();assert "deepQueryAll" in text and "providerHardening:" in text
assert "waitForHumanVerification" in (ROOT/"extension/providers/arena.js").read_text()
print("PASS 6.2 multi-engine v3 and Arena/ChatGPT/DeepSeek reliability hardening")
