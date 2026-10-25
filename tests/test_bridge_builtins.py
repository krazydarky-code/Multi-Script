import importlib.util, json, sys, types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
w = types.ModuleType("websockets")
w.ConnectionClosed = Exception
sys.modules.setdefault("websockets", w)
spec = importlib.util.spec_from_file_location("ms_bridge", ROOT / "runtime" / "bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
class Manager:
    def health(self): return [{"id": "unity", "alive": True, "tools": 9}]
def call(name, args): return bridge._builtin_call(name, args, Manager())
assert len(bridge.BUILTIN_TOOLS) >= 5
assert "critic-loop" in json.loads(call("ms_get_skill", {"skill_id":"critic-loop"})["text"])["id"]
assert json.loads(call("ms_critic_review", {"objective":"ship", "checks":[], "evidence":[]})["text"])["verdict"] == "revise"
review = json.loads(call("ms_critic_review", {"objective":"ship", "changed_assets":["scene"], "checks":["build"], "evidence":["Build completed with zero errors"], "known_issues":[], "round":2})["text"])
assert review["verdict"] == "pass"
assert "Import through the unity MCP" in call("ms_engine_handoff", {"source":"blender", "target":"unity", "asset_type":"prop"})["text"]
print("PASS bridge built-ins and critic loop")
