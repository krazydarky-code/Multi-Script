#!/usr/bin/env python3
"""Pins the engine-native facade's dialect translation.

The facade is the layer that lets one engine-neutral call work on Roblox, Unity,
Godot and Blender, whose vocabularies do not overlap. Its whole value is that the
translation is RIGHT for an engine that may not be running, so it must be tested
without an engine - hence a stub manager with a hand-written advertised
catalogue per engine.

Every assertion here encodes a real dialect fact:
  * Roblox needs studio_id on place-scoped calls, and must never guess between
    two Studios.
  * Unity is action-dispatch: the action goes in params.action.
  * Godot needs camelCase projectPath (folder holding project.godot), and
    list_projects is the one tool taking `directory`.
  * Blender is code-execution based, so a script write becomes execute_blender_code.

Run: python tests/test_native_facade.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("ms_bridge_facade", os.path.join(ROOT, "runtime", "bridge.py"))
B = importlib.util.module_from_spec(spec)
sys.modules["ms_bridge_facade"] = B
spec.loader.exec_module(B)

PASS = 0
FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL {label}" + (f"\n       {detail}" if detail else ""))


class StubClient:
    def __init__(self, names):
        self.tools_cache = [{"name": n, "inputSchema": {"type": "object", "properties": {}}} for n in names]
        self.calls = []

    def call_tool(self, name, args, timeout):
        self.calls.append((name, args))
        return {"text": json.dumps({"echo": name, "args": args}), "images": []}


class StubManager:
    def __init__(self, catalogue):
        self.clients = {sid: StubClient(names) for sid, names in catalogue.items()}

    def health(self):
        return [{"id": sid, "alive": True, "tools": len(c.tools_cache)} for sid, c in self.clients.items()]

    def list_tools(self, refresh=False):
        return []

    def call_on_server(self, sid, name, args, timeout=120):
        client = self.clients[sid]
        if name not in {t["name"] for t in client.tools_cache}:
            raise RuntimeError(f"unknown tool '{name}'")
        return client.call_tool(name, args, timeout)

    def smoke_test(self, sid, tool=None, arguments=None):
        return {"server": sid, "connected": True}


REAL_CATALOGUE = {
    "roblox": ["list_roblox_studios", "get_studio_state", "search_game_tree", "script_read",
               "multi_edit", "execute_luau", "get_console_output", "inspect_instance",
               "script_search", "start_stop_play"],
    "unity": ["manage_scene", "manage_gameobject", "find_gameobjects", "read_console", "find_in_file",
              "script_apply_edits", "create_script", "refresh_unity", "validate_script",
              "get_sha", "manage_editor", "manage_components"],
    "godot": ["get_godot_version", "get_project_info", "list_projects", "create_scene",
              "add_node", "save_scene", "run_project", "get_debug_output", "stop_project"],
    "blender": ["get_scene_info", "get_object_info", "execute_blender_code"],
}

print("=== facade tools are registered ===")
for name in ("ms_native_capabilities", "ms_native_read", "ms_native_write", "ms_native_verify",
             "ms_native_batch", "ms_native_debug"):
    check(f"{name} in catalogue", name in B.BUILTIN_TOOL_BY_NAME)

print("=== every facade schema validates a minimal call ===")
minimal = {
    "ms_native_capabilities": {},
    "ms_native_read": {"server": "roblox", "what": "tree"},
    "ms_native_write": {"server": "roblox", "what": "script", "target": "a.b", "content": "x"},
    "ms_native_verify": {"server": "roblox", "what": "tree"},
    "ms_native_batch": {"server": "roblox", "steps": [{"tool": "get_studio_state"}]},
    "ms_native_debug": {},
}
for name, args in minimal.items():
    tool = B.BUILTIN_TOOL_BY_NAME[name]
    try:
        B._normalize_tool_arguments(tool["inputSchema"], dict(args), name)
        check(f"{name} accepts a minimal payload", True)
    except Exception as exc:
        check(f"{name} accepts a minimal payload", False, str(exc))

print("=== schemas are not stricter than the handlers (bound audit) ===")
for name, args in minimal.items():
    tool = B.BUILTIN_TOOL_BY_NAME[name]
    findings = [f for f in (B._schema_risk_analysis(tool["inputSchema"]).get("issues") or [])
                if f.get("severity") == "high"]
    check(f"{name} has no high-severity schema defect", not findings, json.dumps(findings))
# Limit params must accept 1 (clamp-not-reject), not reject it.
for name in ("ms_native_read", "ms_native_batch"):
    spec_ = B.BUILTIN_TOOL_BY_NAME[name]["inputSchema"]["properties"]
    for field in ("limit", "timeout_seconds"):
        if field in spec_:
            lo = spec_[field].get("minimum")
            check(f"{name}.{field} accepts 1", lo == 1, f"minimum={lo}")

print("=== roblox read translates with studio_id ===")
mgr = StubManager(REAL_CATALOGUE)
mgr.clients["roblox"].call_tool = mgr.clients["roblox"].call_tool  # keep
out = B._native_facade_call("ms_native_read", {"server": "roblox", "what": "tree", "studio_id": "S1"}, mgr)
payload = json.loads(out["text"])
check("roblox read ok", payload.get("ok") is True, out["text"][:300])
check("roblox read used search_game_tree",
      payload["nativeCalls"][0]["tool"] == "search_game_tree", json.dumps(payload.get("nativeCalls"))[:200])
check("roblox read passed studio_id",
      payload["nativeCalls"][0]["arguments"].get("studio_id") == "S1",
      json.dumps(payload["nativeCalls"][0]["arguments"]))
check("roblox read passed datamodel_type",
      payload["nativeCalls"][0]["arguments"].get("datamodel_type") == "Edit")

print("=== roblox refuses to guess between two studios ===")
B.plugin_state["studios"] = [{"id": "A"}, {"id": "B"}]
out = B._native_facade_call("ms_native_read", {"server": "roblox", "what": "state"}, mgr)
payload = json.loads(out["text"])
check("ambiguous studio_id is refused", payload.get("ok") is False, out["text"][:300])
check("refusal names studio_id", "studio_id" in payload.get("reason", ""), payload.get("reason", ""))
B.plugin_state["studios"] = [{"id": "ONLY"}]
tr = B._facade_translate(mgr, "roblox", {"operation": "read", "what": "state"})
check("single studio is auto-filled", tr["ok"] and tr["calls"][0]["arguments"].get("studio_id") == "ONLY",
      json.dumps(tr)[:300])
B.plugin_state["studios"] = []

print("=== unity is action-dispatch ===")
tr = B._facade_translate(mgr, "unity", {"operation": "read", "what": "tree"})
check("unity tree ok", tr["ok"], json.dumps(tr)[:300])
check("unity tree is manage_scene", tr["calls"][0]["tool"] == "manage_scene", json.dumps(tr["calls"])[:200])
check("unity action lives in params.action",
      tr["calls"][0]["arguments"].get("action") == "get_hierarchy", json.dumps(tr["calls"][0]["arguments"]))
tr = B._facade_translate(mgr, "unity", {"operation": "read", "what": "console"})
check("unity console is read_console + action get",
      tr["calls"][0]["tool"] == "read_console" and tr["calls"][0]["arguments"].get("action") == "get",
      json.dumps(tr["calls"])[:200])

print("=== godot uses camelCase projectPath ===")
tr = B._facade_translate(mgr, "godot", {"operation": "read", "what": "project", "project_path": "C:/g/MyGame"})
check("godot project ok", tr["ok"], json.dumps(tr)[:300])
check("godot key is camelCase projectPath",
      "projectPath" in tr["calls"][0]["arguments"] and "project_path" not in tr["calls"][0]["arguments"],
      json.dumps(tr["calls"][0]["arguments"]))
tr = B._facade_translate(mgr, "godot", {"operation": "read", "what": "project"})
check("godot with no project_path is a structured refusal", tr["ok"] is False, json.dumps(tr)[:200])
tr = B._facade_translate(mgr, "godot", {"operation": "write", "what": "node", "target": "res://M.tscn",
                                        "node_type": "Node2D", "parent": "Player", "name": "Health",
                                        "project_path": "C:/g/MyGame"})
# nodeName names the NEW node; the parent goes in parentNodePath. Passing the
# parent as nodeName creates a misnamed child - the bug this test now pins shut.
check("godot add_node names the NEW node in nodeName",
      tr["ok"] and tr["calls"][0]["arguments"].get("nodeType") == "Node2D"
      and tr["calls"][0]["arguments"].get("nodeName") == "Health", json.dumps(tr)[:400])
check("godot add_node puts the parent in parentNodePath",
      tr["calls"][0]["arguments"].get("parentNodePath") == "Player", json.dumps(tr["calls"][0]["arguments"]))
check("godot add_node is followed by save_scene",
      len(tr["calls"]) == 2 and tr["calls"][1]["tool"] == "save_scene", json.dumps(tr["calls"])[:300])
# A node with no explicit name must still get a usable one rather than the
# scene path, which is what using `target` as the name would have produced.
tr = B._facade_translate(mgr, "godot", {"operation": "write", "what": "node", "target": "res://M.tscn",
                                        "node_type": "Node2D", "project_path": "C:/g/MyGame"})
check("godot add_node falls back to the node type, never the scene path",
      tr["ok"] and tr["calls"][0]["arguments"].get("nodeName") == "Node2D"
      and tr["calls"][0]["arguments"].get("nodeName") != "res://M.tscn", json.dumps(tr["calls"][0]["arguments"]))

print("=== blender is code-execution based ===")
tr = B._facade_translate(mgr, "blender", {"operation": "write", "what": "script", "target": "Cube",
                                          "content": "import bpy"})
check("blender script write becomes execute_blender_code",
      tr["ok"] and tr["calls"][0]["tool"] == "execute_blender_code", json.dumps(tr)[:300])
tr = B._facade_translate(mgr, "blender", {"operation": "read", "what": "object", "target": "Cube"})
check("blender object read uses get_object_info + object_name",
      tr["ok"] and tr["calls"][0]["arguments"].get("object_name") == "Cube", json.dumps(tr)[:300])

print("=== unity write paths use the right TOOL and the right PARAM NAMES ===")
# Three distinct upstream facts that are easy to get wrong and silent when wrong:
#  1. create_script takes `path` + `contents` (find_in_file takes `uri`; mixing
#     them up yields an argument error at call time, or a file named after a URI).
#  2. GameObjects are created by manage_gameobject(action="create"); manage_scene
#     has no create_object action at all.
#  3. manage_scene(action="create") needs a folder path or the scene lands in an
#     unpredictable place.
tr = B._facade_translate(mgr, "unity", {"operation": "write", "what": "script",
                                        "target": "Assets/Scripts/Player.cs",
                                        "content": "public class Player {}"})
check("unity create_script uses path + contents",
      tr["ok"] and tr["calls"][0]["tool"] == "create_script"
      and tr["calls"][0]["arguments"] == {"path": "Assets/Scripts/Player.cs",
                                          "contents": "public class Player {}"},
      json.dumps(tr["calls"][0])[:300])
check("unity create_script is followed by a refresh",
      any(c["tool"] == "refresh_unity" for c in tr["calls"]), json.dumps(tr["calls"])[:300])

tr = B._facade_translate(mgr, "unity", {"operation": "write", "what": "node",
                                        "node_type": "Cube", "name": "MyCube"})
check("unity object creation uses manage_gameobject, not manage_scene",
      tr["ok"] and tr["calls"][0]["tool"] == "manage_gameobject", json.dumps(tr["calls"])[:300])
check("unity create_object sends action=create + name + primitive_type",
      tr["calls"][0]["arguments"].get("action") == "create"
      and tr["calls"][0]["arguments"].get("name") == "MyCube"
      and tr["calls"][0]["arguments"].get("primitive_type") == "Cube",
      json.dumps(tr["calls"][0]["arguments"]))

tr = B._facade_translate(mgr, "unity", {"operation": "write", "what": "scene", "name": "Level1"})
check("unity create scene goes through manage_scene with a folder path",
      tr["ok"] and tr["calls"][0]["tool"] == "manage_scene"
      and tr["calls"][0]["arguments"].get("action") == "create"
      and tr["calls"][0]["arguments"].get("path") == "Assets/Scenes/",
      json.dumps(tr["calls"][0]["arguments"]))

print("=== a missing native tool is a structured refusal, never an invented call ===")
poorman = StubManager({"unity": ["manage_scene"], "roblox": ["get_studio_state"], "godot": [], "blender": []})
tr = B._facade_translate(poorman, "godot", {"operation": "write", "what": "scene", "target": "res://a.tscn",
                                            "project_path": "C:/g"})
check("missing godot create_scene is refused", tr["ok"] is False, json.dumps(tr)[:200])
check("refusal does not emit any call", not tr["calls"], json.dumps(tr)[:200])
tr = B._facade_translate(poorman, "unity", {"operation": "read", "what": "console"})
check("missing unity read_console is refused", tr["ok"] is False, json.dumps(tr)[:200])

print("=== an unreachable server is reported, not crashed on ===")
tr = B._facade_translate(StubManager({"roblox": []}), "blender", {"operation": "read", "what": "tree"})
check("unreachable blender reported", tr["ok"] is False and "reachable" in tr["reason"], json.dumps(tr)[:200])
B.plugin_state["studios"] = []
tr = B._facade_translate(StubManager({"roblox": []}), "roblox", {"operation": "read", "what": "tree"})
check("empty roblox catalogue is reported", tr["ok"] is False, json.dumps(tr)[:200])

print("=== lua / python literal emission ===")
check("vector3 emitted for a 3-number list", B._lua_literal([1, 2, 3]) == "Vector3.new(1.0, 2.0, 3.0)",
      B._lua_literal([1, 2, 3]))
check("bool emitted before int", B._lua_literal(True) == "true" and B._lua_literal(False) == "false")
check("string is quoted", B._lua_literal("hi") == '"hi"', B._lua_literal("hi"))
check("python bool emitted", B._python_literal(True) == "True" and B._python_literal(None) == "None")
check("roblox property setter guards a missing target",
      "target not found" in B._roblox_property_setter("Workspace.Part", {"Anchored": True}))
check("roblox property setter rejects an injected key",
      "__import__" not in B._roblox_property_setter("Workspace.Part", {"__import__('os')": 1}))
check("blender property setter guards a missing object",
      "object not found" in B._blender_property_setter("Cube", {"hide_viewport": True}))
# A dot-path must WALK. game:FindFirstChild("Workspace.Door") returns nil, so a
# caller would be told a path that plainly exists does not.
check("roblox dot-path walks each segment",
      B._roblox_path_expr("Workspace.Door") == 'game:FindFirstChild("Workspace"):FindFirstChild("Door")',
      B._roblox_path_expr("Workspace.Door"))
check("roblox slash-path also walks",
      B._roblox_path_expr("Workspace/Door/Handle")
      == 'game:FindFirstChild("Workspace"):FindFirstChild("Door"):FindFirstChild("Handle")',
      B._roblox_path_expr("Workspace/Door/Handle"))
check("roblox game-rooted path is dereferenced directly",
      B._roblox_path_expr("game.Workspace.Door") == "game.Workspace.Door",
      B._roblox_path_expr("game.Workspace.Door"))
check("roblox property report line is quoted safely",
      B._roblox_property_setter("X", {"ok": 1}).rstrip().endswith('return "set ok"'),
      B._roblox_property_setter("X", {"ok": 1}).splitlines()[-1])
check("blender property report line is quoted safely",
      B._blender_property_setter("Cube", {"ok": 1}).rstrip().endswith('print("set: ok")'),
      B._blender_property_setter("Cube", {"ok": 1}).splitlines()[-1])

print("=== dry_run emits the call without executing ===")
mgr = StubManager(REAL_CATALOGUE)
before = len(mgr.clients["roblox"].calls)
out = B._native_facade_call("ms_native_write", {"server": "roblox", "what": "script",
                                                "target": "game.ServerScriptService.Main",
                                                "content": "print(1)", "studio_id": "S1", "dry_run": True}, mgr)
payload = json.loads(out["text"])
check("dry_run reports ok", payload.get("ok") is True and payload.get("dryRun") is True, out["text"][:200])
check("dry_run executed nothing", len(mgr.clients["roblox"].calls) == before)
check("dry_run shows the multi_edit call", payload["calls"][0]["tool"] == "multi_edit",
      json.dumps(payload.get("calls"))[:200])
check("dry_run uses the empty-string create sentinel",
      payload["calls"][0]["arguments"]["edits"][0]["old_string"] == "",
      json.dumps(payload["calls"][0]["arguments"])[:300])

print("=== write then verify round-trips ===")
mgr = StubManager(REAL_CATALOGUE)
out = B._native_facade_call("ms_native_write", {"server": "roblox", "what": "code",
                                                "content": "return 1", "studio_id": "S1"}, mgr)
check("roblox code write ok", json.loads(out["text"]).get("ok") is True, out["text"][:200])
check("roblox code write used execute_luau", mgr.clients["roblox"].calls[-1][0] == "execute_luau",
      str(mgr.clients["roblox"].calls[-1]))
v = B._native_facade_call("ms_native_verify", {"server": "roblox", "what": "tree", "studio_id": "S1"}, mgr)
vp = json.loads(v["text"])
check("verify returns a fingerprint", vp.get("ok") is True and len(vp.get("fingerprint", "")) == 24, v["text"][:300])
out2 = B._native_facade_call("ms_native_verify",
                             {"server": "roblox", "what": "tree", "studio_id": "S1", "before": vp["fingerprint"]}, mgr)
vp2 = json.loads(out2["text"])
check("verify with an identical before reports UNCHANGED", vp2.get("verdict") == "UNCHANGED", out2["text"][:300])

print("=== batch stops at the first failure and refuses unknown tools ===")
mgr = StubManager(REAL_CATALOGUE)
out = B._native_facade_call("ms_native_batch", {"server": "roblox", "steps": [
    {"tool": "get_studio_state", "arguments": {}},
    {"tool": "not_a_real_tool", "arguments": {}},
], "studio_id": "S1"}, mgr)
payload = json.loads(out["text"])
check("batch refuses an unadvertised tool", payload.get("ok") is False, out["text"][:300])
check("batch lists what IS advertised", "advertised" in payload, out["text"][:200])
out = B._native_facade_call("ms_native_batch", {"server": "roblox", "steps": [
    {"tool": "get_studio_state", "arguments": {}},
    {"tool": "get_console_output", "arguments": {}},
], "studio_id": "S1"}, mgr)
payload = json.loads(out["text"])
check("batch runs every step", payload.get("ok") is True and payload.get("completed") == 2, out["text"][:400])

print("=== debug reports resolution state without crashing ===")
mgr = StubManager(REAL_CATALOGUE)
out = B._native_facade_call("ms_native_debug", {}, mgr)
payload = json.loads(out["text"])
check("debug reports all four engines", len(payload.get("servers", [])) == 4, out["text"][:300])
roblox_row = next(r for r in payload["servers"] if r["server"] == "roblox")
check("debug includes studioIdResolution", "studioIdResolution" in roblox_row, json.dumps(roblox_row)[:300])

print("=== capabilities reports real counts ===")
out = B._native_facade_call("ms_native_capabilities", {"server": "unity"}, mgr)
payload = json.loads(out["text"])
row = payload["engines"][0]
check("capabilities counts the real catalogue", row["nativeToolCount"] == len(REAL_CATALOGUE["unity"]),
      json.dumps(row)[:300])
check("capabilities maps tree -> manage_scene", row["facadeCoverage"].get("read_tree") == "manage_scene",
      json.dumps(row.get("facadeCoverage")))

print("=== the in-chat terminal panel is wired end to end ===")
# The terminal icon opens a live view of the bridge INSIDE the extension. There
# is no external launcher any more: the panel reads the bridge's log ring over
# the authenticated socket (and the loopback /logs route as a fallback), so it
# keeps working mid-reconnect. These assertions pin that contract on every side
# so it cannot silently rot.
EXT = os.path.join(ROOT, "extension")
bg_src = open(os.path.join(EXT, "background.js"), encoding="utf-8").read()
main_src = open(os.path.join(EXT, "core", "main.js"), encoding="utf-8").read()
term_src = open(os.path.join(EXT, "core", "terminal.js"), encoding="utf-8").read()
bridge_src = open(os.path.join(ROOT, "runtime", "bridge.py"), encoding="utf-8").read()

check("no external launcher remains in the worker", "launcher_start" not in bg_src and "LAUNCHER_PORT" not in bg_src)
check("bridge serves a log backlog frame", 'mtype == "bridge_log"' in bridge_src)
check("bridge serves a terminal liveness probe", 'mtype == "terminal_probe"' in bridge_src)
check("bridge keeps a bounded ring buffer", "deque(maxlen=LOG_RING_MAX)" in bridge_src)
check("bridge publishes log records to subscribers", "_publish_log" in bridge_src and "_subscribe_log" in bridge_src)
check("bridge serves a loopback /logs fallback", '"/logs"' in bridge_src)
check("worker exposes a terminal snapshot route", '"terminal_snapshot"' in bg_src)
check("worker falls back to HTTP when the socket is quiet", "fetchLogs" in bg_src and "http://127.0.0.1" in bg_src)
check("worker forwards pushed log frames to provider tabs", "ms-log-push" in bg_src and "broadcastToProviders" in bg_src)
check("worker resets its cursor when the bridge restarts", "logCursor = 0" in bg_src)
check("content script handles pushed log frames", 'msg.type === "ms-log-push"' in main_src
      and "termPanel.push(" in main_src)
check("content script handles a cleared log", 'msg.type === "ms-log-cleared"' in main_src)
check("panel renders log lines as text, never as HTML",
      "textContent" in term_src and "innerHTML" not in term_src.split("_line(")[0].split("document")[-1])
check("panel dedupes by sequence so a push cannot double-print",
      "this.seen.has(seq)" in term_src and "this.seen.add(seq)" in term_src)
check("panel autoscroll respects the reading position",
      "atBottom" in term_src and "this.autoscroll" in term_src)
check("terminal button exists in the bar markup", 'id="zs-bridge"' in main_src)
check("terminal button toggles the panel", "onBridgeClick" in main_src and "ensureTerm()" in main_src)
# The icon must be repainted from inside setStatus itself - that is the only place
# bridge connectivity becomes known, so a repaint anywhere else would be guessing.
# NB: main.js has a local `function setStatus(text, tone)` inside the media-relay
# closure, so anchor on the real signature `function setStatus(s)`.
_setstatus = main_src.split("function setStatus(s)", 1)[1].split("function ", 1)[0]
check("terminal button repaints on every status push",
      "A.bridge = s;" in _setstatus and "bridgeIdlePaint();" in _setstatus
      and _setstatus.index("A.bridge = s;") < _setstatus.index("bridgeIdlePaint();"))

print("=== the panel offers a start path but cannot spawn a process ===")
# A content script has no process API. Rather than pretend otherwise, the panel
# hands the user the real command and explains the limitation in one line - then
# watches for the bridge to answer so the wait is visible.
check("panel offers a start action", "Setup.bat" in term_src and "host_start" in term_src or "_hostAct" in term_src)
check("panel explains why a page cannot spawn a process", "cannot" in term_src.lower())
check("panel keeps polling while the bridge is down, so a manual start is noticed", "POLL_MS" in term_src and "pollTimer" in term_src)
check("panel has a help explainer", "_help(" in term_src and "17613" in term_src)
check("panel renders the service chips from the snapshot", "_paintServices" in term_src)
check("panel has a copy-to-clipboard fallback", "execCommand" in term_src)

print(f"\n{'PASS' if FAIL == 0 else 'FAIL'}: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
