# SPDX-License-Identifier: GPL-3.0-or-later
"""test_roblox_workflow_tools.py - the build/verify workflow tools added in 6.17.6.

These compose the official Studio MCP tools into the sequences a builder repeats.
The properties that matter, and that this test pins:

  1. They NEVER fabricate an engine result. With no engine reachable they say
     "unavailable" and list the real fixes - they do not invent a pass.
  2. Console noise is separated from real failures, because treating a
     deprecation warning as a bug trains the model to "fix" working code.
  3. The self-check's confidence is DERIVED from evidence-per-action, so it
     cannot be gamed by simply asserting success.
  4. The planning tool plans by default and only marks itself executable when
     explicitly approved.

Every native call is stubbed; the parsing and decision logic is real code and
that is where the defects would live.
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runtime"))
w = types.ModuleType("websockets")
w.ConnectionClosed = Exception
sys.modules.setdefault("websockets", w)

failures = []


def check(cond, label):
    if cond:
        print(f"  ok  {label}")
    else:
        print(f"  FAIL {label}")
        failures.append(label)


spec = importlib.util.spec_from_file_location("bridge", ROOT / "runtime" / "bridge.py")
bridge = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(bridge)
except SystemExit:  # pragma: no cover - only if a hard dependency is missing
    print("bridge could not be imported (missing websockets?)")
    sys.exit(1)


class FakeManager:
    """Stands in for the MCP manager. Records calls so we can assert the exact
    native tool sequence, which is the whole point of these wrappers."""

    def __init__(self, tools=None, responses=None, dead=False):
        self._tools = tools if tools is not None else [{"name": "execute_luau"}]
        self._responses = responses or {}
        self._dead = dead
        self.calls = []

    def list_server_tools(self, sid, refresh=False):
        if self._dead:
            raise RuntimeError("roblox is not connected")
        return self._tools

    def call_on_server(self, sid, tool, arguments, timeout):
        self.calls.append((tool, arguments))
        if self._dead:
            return {"ok": False, "error": "not connected"}
        if tool in self._responses:
            return {"ok": True, "text": self._responses[tool]}
        return {"ok": True, "text": "{}"}


def call(name, args, mgr):
    return json.loads(bridge._builtin_call(name, args, mgr)["text"])


# ── 1. every tool is registered and dispatched ───────────────────────────
print("\n1. all nine tools are advertised and dispatched")
TOOLS = [
    "ms_roblox_build_verifier", "ms_roblox_script_audit", "ms_roblox_playtest_director",
    "ms_roblox_asset_scout", "ms_roblox_scene_diff", "ms_roblox_error_triage",
    "ms_agent_plan_then_act", "ms_agent_self_check", "ms_agent_context_recall",
]
src = (ROOT / "runtime" / "bridge.py").read_text(encoding="utf-8")
for t in TOOLS:
    check(f'"name": "{t}"' in src, f"{t} is advertised")
    check(bridge.BUILTIN_TOOL_NAMES and t in bridge.BUILTIN_TOOL_NAMES, f"{t} is in the live registry")
for t in TOOLS:
    check(f'if name == "{t}"' in src, f"{t} has a dispatch branch")

# ── 2. no engine => honest unavailable, never a fabricated pass ──────────
print("\n2. with no engine reachable, tools refuse honestly instead of inventing")
dead = FakeManager(dead=True)
bv = call("ms_roblox_build_verifier", {"path": "Workspace.Door"}, dead)
check(bv["available"] is False, "build verifier reports unavailable")
check("reason" in bv and "roblox" in bv["reason"].lower(), "reason names the missing engine")
check(len(bv.get("fixes", [])) >= 3, "actionable fixes are listed")
check("verdict" not in bv, "no verdict is fabricated when nothing was read")

sa = call("ms_roblox_script_audit", {"paths": ["ServerScriptService.Main"]}, dead)
check(sa["available"] is False, "script audit reports unavailable")
asr = call("ms_roblox_asset_scout", {"query": "door"}, dead)
check(asr["available"] is False, "asset scout reports unavailable")
pt = call("ms_roblox_playtest_director", {"scenario": "door opens", "auto_run": True}, dead)
check(pt["available"] is False, "playtest execution refuses without an engine")
check(pt.get("plan"), "but the plan is still returned so the work is not lost")
check(pt["executed"] is False, "it does not claim to have executed")

# ── 3. build verifier reads state back and compares ─────────────────────
print("\n3. the build verifier compares live state against what was claimed")
live = FakeManager(responses={
    "inspect_instance": json.dumps({"name": "Door", "className": "Part", "properties": {"CanCollide": True, "Transparency": 0}}),
})
r = call("ms_roblox_build_verifier", {
    "path": "Workspace.Door",
    "expect": "a Part named Door with CanCollide true",
    "expected_properties": {"CanCollide": True, "Transparency": 0},
}, live)
check(r["found"] is True, "instance was found")
check(r["verdict"] == "verified", "verdict is verified when every property matches")
check(all(c["match"] for c in r["propertyChecks"]), "every compared property resolved as matching")
check(r["rawEvidence"], "raw evidence is preserved for the model to read")
check(live.calls and live.calls[0][0] == "inspect_instance", "it read live state, not memory")

r2 = call("ms_roblox_build_verifier", {
    "path": "Workspace.Door",
    "expected_properties": {"CanCollide": False},
}, live)
check(r2["verdict"] == "mismatched", "a wrong property yields a mismatched verdict")
check(r2["mismatched"], "the mismatched comparison is reported explicitly")

# ── 4. unreadable instance is 'unverifiable', not 'missing' ─────────────
print("\n4. a failed read is unverifiable, distinct from 'does not exist'")
blind = FakeManager(responses={})
# Force both lookup paths to return nothing.
blind._responses = {}
orig = blind.call_on_server
blind.call_on_server = lambda sid, tool, arguments, timeout: {"ok": False, "text": None}
rb = call("ms_roblox_build_verifier", {"path": "Workspace.Ghost"}, blind)
check(rb["verdict"] == "unverifiable", "verdict is unverifiable when nothing could be read")
check(rb["found"] is None, "found is unknown, not asserted false")
check("nextSteps" in rb and len(rb["nextSteps"]) >= 2, "next steps are offered")

# ── 5. error triage separates noise from failure ────────────────────────
print("\n5. console triage separates real failures from noise")
console = """deprecated: use task.wait instead
Loaded plugin: Multi-Script Companion
attempt to index nil with 'FindFirstChild'
   Stack Begin
   Script 'Workspace.Door.Script', Line 12
   Stack End
infinite yield possible on 'Players:WaitForChild("Character")'
some normal print output
"""
tri = call("ms_roblox_error_triage", {"output": console}, live)
check(tri["realIssues"] >= 2, f"real issues found (got {tri['realIssues']})")
check(tri["noiseLines"] >= 2, f"deprecation/plugin chatter classified as noise (got {tri['noiseLines']})")
highs = [f for f in tri["findings"] if f["severity"] == "high"]
check(len(highs) >= 2, "the nil-index and infinite-yield lines are high severity")
check(all("deprecat" not in f["text"].lower() for f in highs), "a deprecation warning is never high severity")
check(tri["guidance"], "guidance is produced for at least the top failure")
check(any("nil" in g["likelyCause"].lower() for g in tri["guidance"]), "nil-index guidance explains the real cause")

# ── 6. triage requires input and refuses silently-empty calls ───────────
print("\n6. triage demands real input")
try:
    call("ms_roblox_error_triage", {}, live)
    check(False, "an empty triage call raises")
except RuntimeError:
    check(True, "an empty triage call raises")

# ── 7. plan-then-act plans first, executes only when approved ───────────
print("\n7. planning is non-destructive unless explicitly approved")
p = call("ms_agent_plan_then_act", {"goal": "add a working door"}, live)
check(p["approved"] is False, "approved defaults to false")
check(p["readyToExecute"] is False, "not executable by default")
check(len(p["steps"]) >= 4, "a real ordered plan is produced")
check(any(s["phase"] == "verify" for s in p["steps"]), "the plan contains an explicit verification step")
check(p["rules"], "the plan carries the no-unverified-stacking rule")

p2 = call("ms_agent_plan_then_act", {"goal": "x", "approve": True, "max_steps": 3}, live)
check(p2["approved"] is True and p2["readyToExecute"] is True, "approve=true marks it executable")
check(len(p2["steps"]) <= 3, "max_steps is honoured")

try:
    call("ms_agent_plan_then_act", {}, live)
    check(False, "a missing goal raises")
except RuntimeError:
    check(True, "a missing goal raises")

# ── 8. self-check confidence is derived, not asserted ───────────────────
print("\n8. self-check confidence comes from evidence-per-action")
s_high = call("ms_agent_self_check", {"task": "t", "did": ["a", "b"], "evidence": ["x", "y"]}, live)
check(s_high["confidence"] == "high", "full evidence yields high confidence")
s_part = call("ms_agent_self_check", {"task": "t", "did": ["a", "b", "c"], "evidence": ["x"]}, live)
check(s_part["confidence"] == "low", "sparse evidence yields low confidence")
s_assume = call("ms_agent_self_check", {"task": "t", "did": ["a"], "evidence": ["x"], "assumptions": ["it works"]}, live)
check(s_assume["confidence"] != "high", "an unproven assumption prevents high confidence")
check(any("Assumed" in u for u in s_assume["unproven"]), "the assumption is named in unproven")
s_none = call("ms_agent_self_check", {"task": "t"}, live)
check(s_none["confidence"] == "unknown", "claiming nothing yields unknown, not high")
check(s_none["wouldAReviewerAsk"], "a reviewer's questions are always offered")

# ── 9. scene diff capture/compare is a real set difference ──────────────
print("\n9. scene diff records and compares real state")
snap = FakeManager(responses={
    "search_game_tree": "Workspace\nWorkspace.Door\nWorkspace.Door.Handle\n",
})
c1 = call("ms_roblox_scene_diff", {"action": "capture", "path": "Workspace", "label": "before"}, snap)
check(c1["captured"] is True, "capture succeeds")
check(c1["instances"] >= 3, "instances were recorded")
snap._responses["search_game_tree"] = "Workspace\nWorkspace.Door\nWorkspace.Door.Handle\nWorkspace.Door.Hinge\n"
c2 = call("ms_roblox_scene_diff", {"action": "capture", "path": "Workspace", "label": "after"}, snap)
check(c2["captured"] is True, "second capture succeeds")
diff = call("ms_roblox_scene_diff", {"action": "compare", "before": "before", "after": "after"}, snap)
check(diff["compared"] is True, "compare succeeds")
check(diff["addedCount"] == 1, f"exactly one addition detected (got {diff['addedCount']})")
check(diff["removedCount"] == 0, "no removals detected")
lst = call("ms_roblox_scene_diff", {"action": "list"}, snap)
check(len(lst["snapshots"]) >= 2, "both snapshots are listed")
try:
    call("ms_roblox_scene_diff", {"action": "nonsense"}, snap)
    check(False, "an unknown action raises")
except RuntimeError:
    check(True, "an unknown action raises")
bad = call("ms_roblox_scene_diff", {"action": "compare", "before": "nope", "after": "after"}, snap)
check(bad["compared"] is False, "unknown labels do not silently compare")
check("known" in bad, "the known labels are listed to help the caller recover")

# ── 10. snapshot store is bounded ───────────────────────────────────────
print("\n10. the snapshot store cannot grow without bound")
for i in range(bridge._SCENE_SNAPSHOT_MAX + 5):
    call("ms_roblox_scene_diff", {"action": "capture", "path": "Workspace", "label": f"spam{i}"}, snap)
check(len(bridge._SCENE_SNAPSHOTS) <= bridge._SCENE_SNAPSHOT_MAX,
      f"snapshots capped at {bridge._SCENE_SNAPSHOT_MAX} (have {len(bridge._SCENE_SNAPSHOTS)})")

# ── 11. script audit applies the real rules ─────────────────────────────
print("\n11. script audit finds the mistakes that break shipped games")
audit_mgr = FakeManager(responses={
    "script_read": """local remote = game.ReplicatedStorage.RemoteEvent
local Players = game:GetService("Players")
remote.OnServerEvent:Connect(function()
  print("hi")
end)
while true do
  local x = 1
end
local lp = game.Players.LocalPlayer
wait()
""",
})
au = call("ms_roblox_script_audit", {"paths": ["ServerScriptService.Main"]}, audit_mgr)
check(au["auditedCount"] == 1, "one script audited")
script = au["scripts"][0]
check(script["readable"] is True, "source was readable")
check(script["highCount"] >= 2, f"high-severity findings present (got {script['highCount']})")
rules_hit = " ".join(f["rule"] for f in script["findings"]).lower()
check("player argument" in rules_hit or "ignores" in rules_hit, "the RemoteEvent-handler rule fired")
check("localplayer" in rules_hit, "the LocalPlayer-on-server rule fired")
check("yield" in rules_hit or "loop" in rules_hit, "the unbounded-loop rule fired")
check(all(f["severity"] in ("high", "warn", "info") for f in script["findings"]), "severities are constrained")

try:
    call("ms_roblox_script_audit", {}, audit_mgr)
    check(False, "an audit with no targets raises")
except RuntimeError:
    check(True, "an audit with no targets raises rather than inventing one")
au2 = call("ms_roblox_script_audit", {"scope": "ServerScriptService"}, audit_mgr)
check(au2["auditedCount"] >= 1, "a scope discovers scripts to audit")

# ── 12. descriptors are honest about what each tool will not do ─────────
print("\n12. descriptions state the real limits")
check("never invent" in src or "Never invents asset ids" in src or "never invent an asset id" in src.lower(),
      "asset scouting states it will not invent ids")
check("never fabricate" in src.lower() or "does not fabricate" in src.lower() or "Never fabricates" in src,
      "the honesty contract is stated somewhere in the tool layer")
check("Read the raw line before acting" in src, "triage tells the model to read the raw evidence")
check("never stack" in src.lower() or "Never stack" in src, "the plan tool forbids stacking unverified changes")
check("report this honestly" in src.lower() or "Report this honestly" in src,
      "self-check asks for an honest report")

if failures:
    print(f"\ntest_roblox_workflow_tools: {len(failures)} FAILED")
    for f in failures:
        print("   -", f)
    sys.exit(1)
print("\ntest_roblox_workflow_tools: 12 sections passed")
