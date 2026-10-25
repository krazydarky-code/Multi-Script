#!/usr/bin/env python3
"""ms_find_tool, ms_tool_stats, retired aliases and the self-healing builtin call path."""
import json, os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools")); sys.path.insert(0, os.path.join(ROOT, "runtime"))
import schema_audit
b = schema_audit.load_bridge()
failed = 0
def check(name, cond, detail=""):
    global failed
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond: failed += 1

mgr = b.MCPManager.__new__(b.MCPManager)
mgr.clients, mgr.index, mgr.index_lock = {}, {}, threading.Lock()

# catalogue: new tools advertised, retired ones hidden but still callable
names = {t["name"] for t in mgr.list_tools()}
check("discovery, blueprint, workflow and completion helpers are advertised",
      {"ms_find_tool", "ms_tool_stats", "ms_request_blueprint", "ms_tool_workflow", "ms_completion_gate"} <= names)
check("retired duplicates are hidden from the catalogue", not (set(b.RETIRED_FROM_CATALOGUE) & names))
check("every retired alias points at a real advertised tool",
      all(v in names for v in b.RETIRED_FROM_CATALOGUE.values()), [v for v in b.RETIRED_FROM_CATALOGUE.values() if v not in names])
check("retired aliases still exist as callable built-ins", all(k in b.BUILTIN_TOOL_NAMES for k in b.RETIRED_FROM_CATALOGUE))
r = mgr.call("ms_performance_budget_designer", {"feature": "door"}, 30)
check("calling a retired alias works and names the replacement", b.RETIRED_FROM_CATALOGUE["ms_performance_budget_designer"] in r["text"])

# search
tools = [dict(t, server="zeroscript") for t in mgr.list_tools()] + \
        [dict(t, server=b._TOOLKIT.engine_of(t["name"])) for t in b._TOOLKIT.definitions()]
def top(q, **kw):
    return [m["name"] for m in b.ASSIST.find(tools, dict(query=q, limit=5, **kw))["matches"]]
check("find: screenshot -> a capture/screenshot tool", "ms_unity_screenshot" in top("take a screenshot"), top("take a screenshot"))
check("find: bevel -> blender modifier", "ms_blender_add_modifier" in top("bevel edges"), top("bevel edges"))
check("find: movement -> movement tools", any(any(w in n for w in ("controller","locomotion","gameplay","character")) for n in top("player movement feel")), top("player movement feel"))
check("find: engine filter respected", all(n.startswith("ms_godot_") for n in top("read a script", engine="godot")))
res = b.ASSIST.find(tools, {"query": "tween animation", "limit": 1})["matches"][0]
check("find returns a copy-ready call", res["call"]["command"] == res["name"] and isinstance(res["call"]["params"], dict))
try:
    mgr.call("ms_find_tool", {}, 30); check("find without query errors clearly", False)
except RuntimeError as e:
    check("find without query errors clearly", "query" in str(e))
check("find tolerates stringified limit and envelope",
      json.loads(mgr.call("ms_find_tool", {"arguments": {"query": "undo", "limit": "2"}}, 30)["text"])["matches"].__len__() <= 2)

# weak prompt -> live workflow -> strict evidence gate
bp = json.loads(mgr.call("ms_request_blueprint", {"request": "make my game cool", "engine": "roblox"}, 30)["text"])
check("weak requests become execution-ready without losing the original",
      bp["weakPrompt"] and bp["originalRequest"] == "make my game cool" and len(bp["acceptanceCriteria"]) >= 4, bp)
wf = json.loads(mgr.call("ms_tool_workflow", {"objective": "make a polished player movement system", "engine": "roblox"}, 30)["text"])
check("tool workflow uses only real advertised tools",
      wf["liveCatalogueOnly"] and (wf["coverage"]["implement"] or "Implementation coverage is unavailable" in wf["warning"]) and wf["coverage"]["verify"]
      and all(s["name"] in names or s["name"] in {t["name"] for t in tools} for s in wf["steps"]), wf)
gate = json.loads(mgr.call("ms_completion_gate", {
    "criteria": ["Build exits cleanly with zero errors", "Final player movement state is read back"],
    "evidence": ["done", "Build succeeded with exit code 0 and zero errors", "Player movement configuration read back from game.PlayerScripts.Controller"],
    "require_clean_run": True,
}, 30)["text"])
check("completion gate rejects vague claims but accepts concrete coverage",
      gate["verdict"] == "pass" and gate["vagueEvidenceRejected"] == 1, gate)
bad_gate = json.loads(mgr.call("ms_completion_gate", {"criteria": ["UI works on phone"], "evidence": ["done"]}, 30)["text"])
check("completion gate blocks unsupported success claims", bad_gate["verdict"] == "revise" and bad_gate["missing"], bad_gate)

# With genuinely advertised implementation tools, all phases must be covered.
live=[{"name": "roblox_"+phase,"server":"roblox","description":desc,"inputSchema":{"type":"object","properties":{}}} for phase,desc in [("inspect","inspect read current player movement state"),("implement","implement player movement controller gameplay"),("verify","test verify screenshot console player movement")]]
complete=b.ASSIST._tool_workflow(live,{"objective":"player movement","engine":"roblox"})
check("connected workflow covers actual implementation and verification",all(complete["coverage"].values()) and all(x["name"] in {t["name"] for t in live} for x in complete["steps"]),complete)

# stats
mgr.call("ms_list_skills", {"limit": 1}, 30)
st = json.loads(mgr.call("ms_tool_stats", {"sort": "busiest"}, 30)["text"])
check("stats record builtin calls", any(t["name"] == "ms_list_skills" and t["calls"] >= 1 for t in st["tools"]), st)
try: mgr.call("ms_get_skill", {}, 30)
except RuntimeError: pass
st = json.loads(mgr.call("ms_tool_stats", {"sort": "failing"}, 30)["text"])
check("stats record failures", any(t["name"] == "ms_get_skill" and t["errors"] >= 1 for t in st["tools"]), st)
json.loads(mgr.call("ms_tool_stats", {"reset": True}, 30)["text"])
check("stats reset", json.loads(mgr.call("ms_tool_stats", {}, 30)["text"])["tools_measured"] == 0)

# self-healing builtin path (the production entry point)
r = mgr.call("ms_list_skills", {"arguments": {"limit": "3"}}, 30)
check("envelope + stringified number repaired on a built-in", json.loads(r["text"])["count"] == 3, r["text"][:80])
r = mgr.call("ms_test_matrix", {"Feature": "door"}, 30)
check("key-case slip repaired on a built-in", json.loads(r["text"])["feature"] == "door")
print("\n%d failed" % failed)
sys.exit(1 if failed else 0)
