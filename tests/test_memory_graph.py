# SPDX-License-Identifier: GPL-3.0-or-later
"""Graph memory + sequential thinking: persistence, recall, graph ops, bridge wiring."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
tmp = tempfile.mkdtemp(prefix="msmem_")
os.environ["ZS_MEMORY_DIR"] = tmp
import memory_graph as M  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)[:300]) if (detail and not ok) else ""))
    if not ok:
        fails.append(name)


S = M.MemoryStore(tmp)
m = S.create("Roblox classic gui")
check("create named memory", m["id"] == "roblox-classic-gui" and S.list()[0]["name"] == "Roblox classic gui")
S.activate("Roblox classic gui")
r = S.remember(None, {
    "entities": [{"name": "MainMenu", "kind": "asset", "text": "ScreenGui in StarterGui with Play/Settings buttons", "tags": ["gui"]}, "Studio"],
    "facts": [{"text": "User prefers a classic grey Gotham UI with 2px black strokes", "kind": "preference", "importance": 0.9, "about": ["MainMenu"]}],
    "relations": [{"from": "MainMenu", "rel": "opens", "to": "SettingsPanel"}],
})
check("remember adds nodes/edges", r["added"] >= 4 and r["links"] >= 2, r)
r2 = S.remember(None, {"facts": [{"text": "User prefers a classic grey Gotham UI with 2px black strokes!"}]})
check("near-duplicate fact merged", r2["added"] == 0 and r2["updated"] == 1, r2)
q = S.recall(None, "classic gui style", touch=False)
check("recall finds preference", any(x["kind"] == "preference" for x in q["results"]), q)
q = S.recall(None, "menu", touch=False)
names = [x["name"] for x in q["results"]]
check("graph expansion reaches neighbors", "SettingsPanel" in names and "MainMenu" in names, names)
g = S.graph(None, "path", "MainMenu", "SettingsPanel")
check("path", g["connected"] and g["path"][0]["rel"] == "opens", g)
g = S.graph(None, "neighbors", "MainMenu")
check("neighbors", len(g["nodes"]) >= 3, g)
check("mermaid", S.graph(None, "mermaid")["mermaid"].startswith("graph LR"))
S.update(None, "MainMenu", pinned=True, importance=1.0, tags=["gui", "menu"])
ctx = S.context(None, "")
check("context packs pinned first", ctx["text"].splitlines()[0].startswith("- [asset] MainMenu"), ctx)
# persistence across instances
S2 = M.MemoryStore(tmp)
check("persists locally", S2.recall("roblox-classic-gui", "gotham", touch=False)["count"] >= 1)
# two memories are isolated
S.create("Blender hero")
S.remember("Blender hero", {"text": "Hero uses 24fps walk cycle"})
check("memories isolated", S.recall("Blender hero", "gui", touch=False)["count"] == 0)
# observe heuristic capture
o = S.observe("Roblox classic gui", "Remember that all buttons use Gotham SemiBold. Make a shop at Workspace.Shop.Door", "We decided to use UIListLayout for the shop list.", ["ms_roblox_ui_kit"])
mm = S.recall("Roblox classic gui", "Gotham SemiBold buttons", touch=False)
check("observe journals preference + episode", o["captured"] >= 3 and any(x["kind"] == "preference" for x in mm["results"]), (o, mm))
check("observe decision", any(x["kind"] == "decision" for x in S.recall("Roblox classic gui", "UIListLayout shop", touch=False)["results"]))
# forget / merge
f = S.forget("Roblox classic gui", query="UIListLayout shop")
check("forget by query", f["forgotten"] >= 1, f)
# export/import
data = S.export("Roblox classic gui")
imp = S.import_(data, name="Copy of GUI")
check("export/import", imp["nodes"] >= 3 and imp["id"] != "roblox-classic-gui", imp)
# delete
S.delete("Copy of GUI")
check("delete", all(x["name"] != "Copy of GUI" for x in S.list()))
# pruning keeps pinned
S.set_settings("Blender hero", {"maxNodes": 5})
S.update("Blender hero", S.recall("Blender hero", "walk cycle", touch=False)["results"][0]["id"], pinned=True)
for i in range(12):
    S.remember("Blender hero", {"text": f"unique throwaway note number {i} about zebra{i}"})
S.remember("Blender hero", {"text": "another fresh note about quokka"})
check("prune caps nodes", len(S.resolve("Blender hero")["nodes"]) <= 6)
# corrupted file is handled
Path(tmp, "bad.json").write_text("{not json")
try:
    S2.resolve("bad")
    check("corrupt file handled", False)
except M.MemoryError_:
    check("corrupt file handled", True)

# sequential thinking
T = M.ThinkingSessions()
a = T.step({"thought": "Plan", "thoughtNumber": 1, "totalThoughts": 3, "nextThoughtNeeded": True})
b = T.step({"thought": "Revise", "thoughtNumber": 2, "totalThoughts": 3, "nextThoughtNeeded": True, "isRevision": True, "revisesThought": 1})
c = T.step({"thought": "Alt", "thoughtNumber": 3, "totalThoughts": 3, "nextThoughtNeeded": True, "branchFromThought": 1, "branchId": "alt"})
d = T.step({"thought": "Done", "thoughtNumber": 4, "totalThoughts": 3, "nextThoughtNeeded": False, "save_to_memory": True, "memory": "Blender hero"}, S)
check("sequential thinking semantics", a["thoughtHistoryLength"] == 1 and c["branches"] == ["alt"] and d["totalThoughts"] == 4 and "memory" in d, d)

# bridge tool wiring
import bridge  # noqa: E402
names = {t["name"] for t in bridge.BUILTIN_TOOLS}
check("bridge exposes memory tools", {"ms_memory_remember", "ms_memory_recall", "ms_memory_graph", "ms_memory_update", "ms_memory_forget", "ms_memory_manage", "ms_sequential_thinking"} <= names)
M.STORE = S
bridge.MEMORY_GRAPH.STORE = S
out = bridge._builtin_call("ms_memory_recall", {"query": "gotham", "memory": "Roblox classic gui"}, None)
check("bridge builtin call", "preference" in out["text"], out)
res = M.ws_op("list", {})
check("ws op list", res["ok"] and len(res["memories"]) >= 2)
check("ws op error is not an exception", M.ws_op("open", {"memory": "zzz-none-xyz"})["ok"] in (True, False))
print("\n%d failed" % len(fails))
sys.exit(1 if fails else 0)
