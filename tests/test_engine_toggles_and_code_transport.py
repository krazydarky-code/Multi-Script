# SPDX-License-Identifier: GPL-3.0-or-later
"""Engine on/off switches, Roblox script-transfer repair, tolerant Software Builder arguments,
and the "keep running while the browser is covered" setting.

Reported: ms_* tools "keep erroring with JSON errors", scripts not transferring to Roblox Studio,
the agent no longer re-running/sending on its own, and no way to switch an engine off.
"""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "runtime")
sys.path.insert(0, RT)
fails = []


def check(name, cond, extra=""):
    if cond:
        print("PASS", name)
    else:
        print("FAIL", name, extra)
        fails.append(name)


def rd(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


# ── script transfer repair ──────────────────────────────────────────────────
import schema_repair as S  # noqa: E402

fixed, notes = S.repair_code_text('local a = 1\\nprint(\\"hi\\")\\nreturn a')
check("double-escaped one-liner becomes real Luau lines", fixed == 'local a = 1\nprint("hi")\nreturn a' and notes, repr(fixed))
fixed, notes = S.repair_code_text('print("line1\\nline2\\nline3 and more text")')
check("a legitimate one-liner with \\n inside a string is left alone", fixed == 'print("line1\\nline2\\nline3 and more text")' and not notes)
real = 'local x = 1\nprint("a\\nb")\nreturn x'
check("code that already has real newlines is never touched", S.repair_code_text(real) == (real, []))
check("markdown fence removed", S.repair_code_text("```lua\nprint(1)\n```")[0] == "print(1)")
check("###LUA### markers removed", S.repair_code_text("###LUA###\nprint(1)\n###END_LUA###")[0] == "print(1)")
check("BOM / zero-width characters removed", S.repair_code_text("\ufeffprint(1)\u200b")[0] == "print(1)")
args, notes = S.repair_code_arguments("execute_luau", {"lines": ["local a = 1", "return a"], "datamodel_type": "Edit"})
check("`lines` is joined into `code` for execute_luau", args.get("code") == "local a = 1\nreturn a" and "lines" not in args, str(args))
args, _ = S.repair_code_arguments("get_studio_state", {"code": "a\\nb\\nc"})
check("non-code tools are never rewritten", args == {"code": "a\\nb\\nc"})

# ── Software Builder: no JSON-schema rejections for numbers ─────────────────
import software_workspace as W  # noqa: E402

bad = []
for t in W.TOOLS:
    def walk(n, path=""):
        if isinstance(n, dict):
            for k, v in n.items():
                if k in ("minimum", "maximum"):
                    bad.append(f"{t['name']}{path}.{k}")
                walk(v, path + "." + k)
    walk(t["inputSchema"])
check("ms_ws_* schemas carry no numeric bounds that reject a model's value", not bad, str(bad))
check("tolerant int: '7.9' -> clamped", W._int("7.9", 1, 1, 5) == 5 and W._int("abc", 4) == 4 and W._int(None, 3) == 3)

# ── engine switches in the bridge ──────────────────────────────────────────
spec = importlib.util.spec_from_file_location("ms_bridge_toggle_test", os.path.join(RT, "bridge.py"))
B = importlib.util.module_from_spec(spec)
sys.modules["ms_bridge_toggle_test"] = B
spec.loader.exec_module(B)
tmp = tempfile.mkdtemp(prefix="ms-eng-")
B.ENGINE_PREFS_PATH = os.path.join(tmp, "engine-prefs.json")


class Stub:
    def __init__(self, sid, names):
        self.id, self.tools_cache, self.alive, self.started, self.stopped = sid, [{"name": n, "inputSchema": {"type": "object", "properties": {}}} for n in names], True, 0, 0

    def is_alive(self):
        return self.alive

    def start(self):
        self.alive = True
        self.started += 1

    def stop(self):
        self.alive = False
        self.stopped += 1

    def call_tool(self, n, a, t):
        return {"text": "ran " + n, "images": []}


m = B.MCPManager()
m.clients = {"roblox": Stub("roblox", ["execute_luau"]), "unity": Stub("unity", ["manage_scene"])}
m.rebuild_index()
names = {t["name"] for t in m.list_tools()}
check("both engines advertise tools initially", "execute_luau" in names and "manage_scene" in names)
r = m.set_engine_enabled("unity", False)
check("switching Unity off succeeds and reports it", r["ok"] and r["enabled"] is False and r["engine"] == "unity", str(r))
check("its server was stopped and parked", m.clients.get("unity") is None and m.parked["unity"].stopped == 1)
names = {t["name"] for t in m.list_tools()}
check("Unity's tools disappear from the catalogue", "manage_scene" not in names and "execute_luau" in names)
check("no ms_unity_* tool is advertised while Unity is off", not any(n.startswith("ms_unity_") for n in names))
try:
    m.call("manage_scene", {}, 5)
    check("calling a switched-off engine's tool is refused", False)
except RuntimeError as e:
    check("calling a switched-off engine's tool is refused with an explanation", "switched OFF" in str(e) and "Unity" in str(e), str(e))
try:
    m.call("ms_unity_status", {}, 5)
    check("toolkit tool of a switched-off engine is refused", False)
except RuntimeError as e:
    check("toolkit tool of a switched-off engine is refused", "switched OFF" in str(e), str(e))
check("choice is saved to disk", json.load(open(B.ENGINE_PREFS_PATH))["disabled"] == ["unity"])
check("health lists it as disabled", any(h["id"] == "unity" and h["enabled"] is False for h in m.health()))
check("engine_list reports enabled flags", {e["id"]: e["enabled"] for e in m.engine_list()}["unity"] is False)

m2 = B.MCPManager()
m2.clients = {"roblox": Stub("roblox", ["execute_luau"]), "unity": Stub("unity", ["manage_scene"])}
B._read_config = lambda: {"mcpServers": {}}
m2.disabled = B._load_engine_prefs()
for sid in list(m2.clients):
    if sid in m2.disabled:
        m2.parked[sid] = m2.clients.pop(sid)
check("a fresh manager (bridge restart) starts with Unity still parked", "unity" in m2.parked and "unity" not in m2.clients)

r = m.set_engine_enabled("unity", True)
check("switching back on restarts the server", r["enabled"] is True and m.clients["unity"].started == 1 and "unity" not in m.parked)
check("its tools return", "manage_scene" in {t["name"] for t in m.list_tools()})
check("and the saved choice is cleared", json.load(open(B.ENGINE_PREFS_PATH))["disabled"] == [])
m.set_engine_enabled("roblox", False)
check("companion plugin tools are hidden when Roblox is off", not any(t.get("server") == "roblox-companion" for t in m.list_tools()))
check("invalid engine id rejected", m.set_engine_enabled("../x", False)["ok"] is False)

# ── extension wiring ────────────────────────────────────────────────────────
main, bg, term = rd("extension", "core", "main.js"), rd("extension", "background.js"), rd("extension", "core", "terminal.js")
check("Engines tab has the Active engines switches", "ms-engine-toggles" in main and "bindEngineToggles" in main and 'data-engine="${id}"' in main)
check("worker relays engine_prefs / set_engine to the bridge", 'case "set_engine"' in bg and 'case "engine_prefs"' in bg)
check("terminal shows a switched-off engine", "switched off in Settings" in term)
check("loop gating honours 'keep running when covered'", "const pageHidden" in main and "keepRunningHidden" in main and main.count("pageHidden()") >= 10)
check("hidden-tab waits use the worker timer", 'type: "ms_sleep"' in main and 'case "ms_sleep"' in bg)

print("\n%d failed" % len(fails))
sys.exit(1 if fails else 0)
