#!/usr/bin/env python3
"""Staged-code tools, no silent re-send of mutating native calls, transient-drop rule, MS_TOOL_RESULT_LIMIT."""
import json, os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools")); sys.path.insert(0, os.path.join(ROOT, "runtime"))
import schema_audit
b = schema_audit.load_bridge()
A = b.ASSIST
failed = 0
def check(name, cond, detail=""):
    global failed
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond: failed += 1
def out(r): return json.loads(r["text"])

class Host:
    def __init__(self): self.calls = []
    def call(self, tool, args, timeout):
        self.calls.append((tool, json.loads(json.dumps(args)))); return {"text": "ok", "images": []}
    def studio_id(self, args): return (args.get("studio_id") or "S1", "")

h = Host()
# ── ms_stage_code ──
A.run("ms_stage_code", {"name": "t1", "action": "clear"}, [], h)
r = out(A.run("ms_stage_code", {"name": "t1", "chunk": "local a = 1\n"}, [], h))
check("stage: first chunk stored", r["chars"] == 12 and r["parts"] == 1, r)
r = out(A.run("ms_stage_code", {"name": "t1", "chunk": "print(a)\n"}, [], h))
check("stage: chunks append", r["chars"] == 21 and r["parts"] == 2, r)
r = out(A.run("ms_stage_code", {"name": "t1", "action": "show"}, [], h))
check("stage: show reports size and tail", r["chars"] == 21 and r["last_lines"][-1] == "print(a)", r)
r = out(A.run("ms_stage_code", {"name": "t1", "lines": ["x", "y"]}, [], h))
check("stage: lines[] accepted", r["added"] == 4, r)
r = out(A.run("ms_stage_code", {"name": "t1", "chunk": "z", "reset": True}, [], h))
check("stage: reset starts over", r["chars"] == 1 and r["parts"] == 1, r)
try: A.run("ms_stage_code", {"name": "t1", "chunk": ""}, [], h); check("stage: empty chunk rejected", False)
except RuntimeError: check("stage: empty chunk rejected", True)
try: A.run("ms_stage_code", {"chunk": "x"}, [], h); check("stage: name required", False)
except RuntimeError: check("stage: name required", True)
big = "x" * 200000
for i in range(5): A.run("ms_stage_code", {"name": "big", "chunk": big, "reset": i == 0}, [], h)
r = out(A.run("ms_stage_code", {"name": "big", "action": "show"}, [], h))
check("stage: 1,000,000 chars staged in 5 chunks intact", r["chars"] == 1_000_000, r)
A.run("ms_stage_code", {"name": "big", "action": "clear"}, [], h)

# ── ms_run_staged_luau ──
A.run("ms_stage_code", {"name": "run", "chunk": "print('hi')\n", "reset": True}, [], h)
A.run("ms_run_staged_luau", {"name": "run", "studio_id": "S9"}, [], h)
tool, args = h.calls[-1]
check("run_staged: calls ms_roblox_run_luau with the code", tool == "ms_roblox_run_luau" and args["code"] == "print('hi')\n" and args["studio_id"] == "S9", h.calls[-1])
try: A.run("ms_run_staged_luau", {"name": "run"}, [], h); check("run_staged: buffer cleared after run", False)
except RuntimeError as e: check("run_staged: buffer cleared after run", "nothing is staged" in str(e))
try: A.run("ms_run_staged_luau", {"name": "never"}, [], h); check("run_staged: empty buffer errors", False)
except RuntimeError: check("run_staged: empty buffer errors", True)
A.run("ms_stage_code", {"name": "keep", "chunk": "a"}, [], h)
A.run("ms_run_staged_luau", {"name": "keep", "keep": True}, [], h)
check("run_staged: keep=true retains buffer", out(A.run("ms_stage_code", {"name": "keep", "action": "show"}, [], h))["chars"] == 1)

# ── ms_write_staged (double-apply guard) ──
n0 = len(h.calls)
A.run("ms_stage_code", {"name": "w", "chunk": "print(1)", "reset": True}, [], h)
A.run("ms_write_staged", {"name": "w", "file_path": "game.ServerScriptService.A", "keep": True}, [], h)
tool, args = h.calls[-1]
check("write_staged: one multi_edit with the staged text", tool == "multi_edit" and args["edits"] == [{"old_string": "", "new_string": "print(1)"}] and args["studio_id"] == "S1", h.calls[-1])
try: A.run("ms_write_staged", {"name": "w", "file_path": "game.ServerScriptService.A", "keep": True}, [], h); check("write_staged: identical re-write refused", False)
except RuntimeError as e: check("write_staged: identical re-write refused", "twice" in str(e))
check("write_staged: refused write did not reach Studio", len(h.calls) == n0 + 1, h.calls)
A.run("ms_write_staged", {"name": "w", "file_path": "game.ServerScriptService.B"}, [], h)
check("write_staged: a different script is allowed", len(h.calls) == n0 + 2)

# ── advertised + schema ──
names = {d["name"] for d in A.DEFINITIONS}
check("staged tools are defined", {"ms_stage_code", "ms_run_staged_luau", "ms_write_staged"} <= names)

# ── bridge: mutating native calls are not silently re-sent ──
check("multi_edit/execute_luau are marked non-idempotent", {"multi_edit", "execute_luau"} <= set(b._NON_IDEMPOTENT_NATIVE))
check("read-only tools are not marked non-idempotent", not ({"script_read", "inspect_instance", "get_studio_state"} & set(b._NON_IDEMPOTENT_NATIVE)))
class FakeClient(b.MCPClient):
    def __init__(self):
        self.id = "fake"; self.call_lock = threading.RLock(); self.requests = 0; self.restarts = 0; self.alive = False
    def is_alive(self): return self.alive
    def restart(self): self.restarts += 1; self.alive = True
    def _request(self, method, params, timeout):
        self.requests += 1
        if self.requests == 1:
            self.alive = False; return None          # server died mid-call
        return {"result": {"content": [{"type": "text", "text": "done"}]}}
c = FakeClient()
try: c.call_tool("multi_edit", {"x": 1}, 5); check("multi_edit not re-sent after server death", False)
except RuntimeError as e: check("multi_edit not re-sent after server death", c.requests == 1 and "NOT re-sent" in str(e), (c.requests, str(e)))
c = FakeClient()
res = c.call_tool("script_read", {"x": 1}, 5)
check("read-only call is still retried after server death", c.requests == 2 and res["text"] == "done", c.requests)

check("short 'not connected' text counts as a transient drop", b._looks_like_transient_studio_drop("No Studio instance connected"))
check("long script output mentioning it does NOT trigger a retry", not b._looks_like_transient_studio_drop("No Studio instance connected " + "print line\n" * 100))

# ── MS_TOOL_RESULT_LIMIT ──
import engine_toolkit as et
import inspect
src = inspect.getsource(et)
check("engine toolkit honours MS_TOOL_RESULT_LIMIT", "MS_TOOL_RESULT_LIMIT" in src)

# ── Limits setting -> bridge: result_limit overrides the native clip per call ──
class _Sp:
    def call(self, tool, args, timeout): return {"text": "ok", "images": []}
    def studio_id(self, args): return ("S1", "given")
big = {"code": "return 1"}
os.environ.pop("MS_TOOL_RESULT_LIMIT", None)
b.apply_result_limit(0)
check("result_limit 0 -> env 0 (no bridge clip)", os.environ.get("MS_TOOL_RESULT_LIMIT") == "0")
import engine_toolkit as _et
_et.REGISTRY["ms_zz_big"] = {"name": "ms_zz_big", "engine": "zz", "description": "d" * 100, "inputSchema": {"type": "object", "properties": {}, "required": []}, "writes": False, "local": True,
                             "handler": lambda a, c: {"blob": "x" * 150000}}
txt = _et.run("ms_zz_big", {}, _Sp())["text"]
check("with limit 0 a 150k native result is delivered whole", len(txt) > 150000 and "truncated" not in txt, len(txt))
b.apply_result_limit(None)
txt = _et.run("ms_zz_big", {}, _Sp())["text"]
check("absent limit restores the bridge default clip (60k) and a helpful marker", len(txt) < 61000 + 300 and "Settings > Limits" in txt, len(txt))
b.apply_result_limit("junk")
check("junk limit values are ignored", os.environ.get("MS_TOOL_RESULT_LIMIT") is None)
del _et.REGISTRY["ms_zz_big"]

print(f"\n{failed} failure(s)")
sys.exit(1 if failed else 0)
