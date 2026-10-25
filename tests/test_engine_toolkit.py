# SPDX-License-Identifier: GPL-3.0-or-later
"""Engine toolkit: typed native tools for Blender / Roblox / Unity / Godot.

Runs every generated program for real where that is possible without the engine:
Python (Blender) against a mocked bpy, Luau against a Roblox API mock inside a Lua VM
(lupa, skipped when not installed), and Godot against files in a temp project."""
import importlib.util
import contextlib
import io
import json
import os
import signal
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import engine_toolkit as T  # noqa: E402

T.ensure_loaded()
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)[:300]) if (detail and not ok) else ""))
    if not ok:
        fails.append(name)


class Ctx(T.Ctx):
    def __init__(self, adv=None, replies=None, studio=("S1", "single")):
        self.adv, self.replies, self.studio, self.calls, self._proj = adv, replies or {}, studio, [], {}

    def advertised(self, server):
        return None if self.adv is None else set(self.adv.get(server, []))

    def call(self, server, tool, arguments, timeout=120):
        self.calls.append((server, tool, arguments))
        r = self.replies.get(tool)
        r = r(arguments) if callable(r) else r
        return {"text": r if r is not None else '{"success": true, "data": {}}', "images": []}

    def studio_id(self, args):
        return (args.get("studio_id") or self.studio[0], "given" if args.get("studio_id") else self.studio[1])

    def project_hint(self, engine):
        return self._proj.get(engine, "")

    def remember_project(self, engine, path):
        self._proj[engine] = path


def run(name, args, ctx):
    return json.loads(T.run(name, args, ctx)["text"])


# ── registry shape ──────────────────────────────────────────────────────────
print("=== registry ===")
c = T.counts()
check("every engine has a real catalogue (>=20 tools each)", all(v >= 20 for v in c.values()), c)
check("tool names are unique and prefixed ms_<engine>_", all(n.startswith("ms_" + t["engine"] + "_") for n, t in T.REGISTRY.items()))
bad_schema = []
for n, t in T.REGISTRY.items():
    s = t["inputSchema"]
    if s.get("type") != "object" or not isinstance(s.get("properties"), dict):
        bad_schema.append(n)
    for r in s.get("required", []):
        if r not in s["properties"]:
            bad_schema.append(n + ":" + r)
    for k, v in s["properties"].items():
        if v.get("type") == "array" and "items" not in v:
            bad_schema.append(f"{n}.{k} array without items")
        if "enum" in v and not v["enum"]:
            bad_schema.append(f"{n}.{k} empty enum")
        if not v.get("description") and "enum" not in v and k not in ("name", "path", "root", "parent", "label", "type", "names", "paths", "objects", "action", "folder", "scene_path", "node"):
            pass
check("every schema is a well-formed object schema (arrays have items, required exist)", not bad_schema, bad_schema)
check("every tool carries dry_run", all("dry_run" in t["inputSchema"]["properties"] for t in T.REGISTRY.values()))
check("roblox tools expose studio_id + mode", all("studio_id" in t["inputSchema"]["properties"] for t in T.REGISTRY.values() if t["engine"] == "roblox" and not t["local"]))
check("godot tools expose project_path", all("project_path" in t["inputSchema"]["properties"] for t in T.REGISTRY.values() if t["engine"] == "godot"))
check("descriptions stay compact (<= 520 chars)", all(len(d["description"]) <= 520 for d in T.definitions()), [d["name"] for d in T.definitions() if len(d["description"]) > 520])

# ── helpers ─────────────────────────────────────────────────────────────────
print("=== helpers ===")
check("vec3 accepts list / dict / csv / json", T.vec3("1,2,3") == [1, 2, 3] and T.vec3({"x": 1, "y": 2, "z": 3}) == [1, 2, 3] and T.vec3("[1,2,3]") == [1, 2, 3] and T.vec3([1, 2]) is None)
check("color4 reads hex, short hex, names, 0-255 arrays", T.color4("#ff0000") == [1, 0, 0, 1] and T.color4("#f00")[0] == 1 and T.color4("red")[0] == 1 and T.color4([255, 0, 0])[0] == 1.0)
check("long_bracket never collides with the content", T.long_bracket("x]==]y") == "[===[x]==]y]===]")
check("extract_result takes the last marker amid noise", T.extract_result('hi\nMS_RESULT:{"a":1}\nMS_RESULT:{"ok":true,"n":2}\nbye')["n"] == 2)
d = T.diff_maps({"a": {"x": 1}, "b": {"x": 1}}, {"a": {"x": 2}, "c": {}})
check("diff_maps reports added/removed/changed", d["added"] == ["c"] and d["removed"] == ["b"] and d["changed"]["a"]["x"]["to"] == 2)

# ── Blender: run every program against a mocked bpy ─────────────────────────
print("=== blender programs ===")
SAMPLES_B = {
    "ms_blender_create_primitive": {"shape": "cube", "name": "X", "location": [1, 2, 3]}, "ms_blender_transform_objects": {"names": ["a"], "location": [1, 2, 3], "parent": "b"},
    "ms_blender_delete_objects": {"names": ["a"]}, "ms_blender_duplicate_object": {"name": "a", "count": 2}, "ms_blender_manage_collection": {"action": "list"},
    "ms_blender_create_material": {"name": "m", "base_color": "#f80", "assign_to": ["a"]}, "ms_blender_add_modifier": {"object": "a", "type": "bevel", "settings": {"width": 0.1}, "apply": True},
    "ms_blender_modifier_stack": {"object": "a", "action": "list"}, "ms_blender_boolean": {"object": "a", "operand": "b"}, "ms_blender_add_light": {"type": "sun"},
    "ms_blender_camera": {"action": "create", "target": "a"}, "ms_blender_keyframes": {"object": "a", "action": "insert", "frame": 1, "value": [0, 0, 0]}, "ms_blender_file": {"action": "info"},
    "ms_blender_add_text": {"text": "hi"}, "ms_blender_run_python": {"lines": ["result = 1 + 1"]}, "ms_blender_world": {"color": "#112233", "strength": 1},
    "ms_blender_render_settings": {"engine": "CYCLES", "samples": 16}, "ms_blender_select": {"mode": "all"}, "ms_blender_scene_summary": {}, "ms_blender_list_objects": {},
    "ms_blender_mesh_stats": {}, "ms_blender_rig_info": {}, "ms_blender_render": {},
}
EXPECTED_GUARDS = {  # mock objects are not real meshes/files; these guards firing proves they work
    "ms_blender_assign_material", "ms_blender_mesh_edit", "ms_blender_uv_unwrap", "ms_blender_lod_generate", "ms_blender_import", "ms_blender_export", "ms_blender_changes"}
SAMPLES_B.update({"ms_blender_assign_material": {"objects": ["a"], "material": "m"}, "ms_blender_mesh_edit": {"objects": ["a"], "operations": ["shade_smooth"]},
                  "ms_blender_uv_unwrap": {"objects": ["a"]}, "ms_blender_lod_generate": {"object": "a"}, "ms_blender_import": {"filepath": "/x/a.fbx"},
                  "ms_blender_export": {"filepath": "/x/a.glb"}, "ms_blender_changes": {"action": "diff"}})


class _TO(Exception):
    pass


def _alarm(*_):
    raise _TO()


has_alarm = hasattr(signal, "SIGALRM")
if has_alarm:
    signal.signal(signal.SIGALRM, _alarm)
blender_ctx = Ctx({"blender": ["execute_blender_code"]})
unexpected = []
sys.path.insert(0, str(ROOT / "tests" / "support"))
from pro_samples import SAMPLES as PRO_SAMPLES  # noqa: E402
IS_PRO = lambda spec: getattr(spec["handler"], "__module__", "").endswith(("_pro", "_world", "_game", "_build", "_props"))  # noqa: E731
for n, spec in T.REGISTRY.items():
    if spec["engine"] != "blender":
        continue
    if IS_PRO(spec):
        continue  # pro tools are executed against real bpy in test_native_pro_tools.py
    a = dict(SAMPLES_B.get(n, {}), dry_run=True)
    d = run(n, a, blender_ctx)
    code = d.get("code")
    if not code:
        unexpected.append((n, "no code", d))
        continue
    try:
        compile(code, n, "exec")
    except SyntaxError as exc:
        unexpected.append((n, "syntax", str(exc)))
        continue
    buf = io.StringIO()
    mods = {"bpy": mock.MagicMock(), "bmesh": mock.MagicMock(), "mathutils": mock.MagicMock()}
    # Blender's material slots grow after append(). MagicMock has a permanently
    # zero length and used to make the generated slot-fill loop hang on Windows
    # (SIGALRM is unavailable there). Model the actual mutable sequence.
    mods["bpy"].data.objects.get.return_value.data.materials = []
    if has_alarm:
        signal.alarm(3)
    with mock.patch.dict(sys.modules, mods), contextlib.redirect_stdout(buf):
        try:
            exec(compile(code, n, "exec"), {"__name__": "ms"})
        except BaseException as exc:  # noqa: BLE001
            unexpected.append((n, "raised", repr(exc)))
    if has_alarm:
        signal.alarm(0)
    lines = [l for l in buf.getvalue().splitlines() if l.startswith(T.MARKER)]
    res = T.extract_result(lines[-1]) if lines else None
    if res is None:
        unexpected.append((n, "no result line", buf.getvalue()[-200:]))
    elif not res.get("ok") and n not in EXPECTED_GUARDS:
        unexpected.append((n, "not ok", res.get("error")))
check("every Blender program compiles and runs to a result line (mock bpy)", not unexpected, unexpected)

hostile = 'quote " and \' and \\ and \n newline ]==] and """ triple ```'
d = run("ms_blender_run_python", {"lines": ["result = 'ok'"], "dry_run": True}, blender_ctx)
d2 = run("ms_blender_add_text", {"text": hostile, "dry_run": True}, blender_ctx)
ns = {}
src = d2["code"]
import base64  # noqa: E402
b64 = src.split('base64.b64decode("', 1)[1].split('"', 1)[0]
check("hostile text survives the base64 JSON transport byte-for-byte", json.loads(base64.b64decode(b64).decode())["text"] == hostile)
r = run("ms_blender_run_python", {"lines": ["def broken(:", "  pass"]}, blender_ctx)
check("syntax errors in user python are caught before anything is sent to Blender", r["ok"] is False and "SyntaxError" in r["error"] and not blender_ctx.calls)

# real round trip through a fake blender-mcp
sent = []


def fake_blender(arguments):
    sent.append(arguments["code"])
    return 'Code executed successfully: MS_RESULT:{"ok": true, "created": {"name": "Crate"}}\n'


bc = Ctx({"blender": ["execute_blender_code"]}, {"execute_blender_code": fake_blender})
r = run("ms_blender_create_primitive", {"shape": "cube", "name": "Crate"}, bc)
check("create_primitive returns the structured result from the engine", r["ok"] and r["created"]["name"] == "Crate" and r["nativeCall"] == "execute_blender_code" and r["next"])
check("create_primitive rejects unknown shapes with a hint", run("ms_blender_create_primitive", {"shape": "banana"}, bc)["ok"] is False)
r = run("ms_blender_add_modifier", {"object": "a", "type": "nonsense"}, bc)
check("add_modifier validates the modifier type before sending", r["ok"] is False and "SUBSURF" in r["hint"])
r = run("ms_blender_scene_summary", {}, Ctx(None))
check("a disconnected engine is a clear, actionable error", r["ok"] is False and "not connected" in r["error"])
r = run("ms_blender_scene_summary", {}, Ctx({"blender": ["get_scene_info"]}))
check("a server without execute_blender_code is reported precisely", r["ok"] is False and "execute_blender_code" in r["error"])
bc2 = Ctx({"blender": ["execute_blender_code"]}, {"execute_blender_code": lambda a: "Error: Traceback boom"})
r = run("ms_blender_list_objects", {}, bc2)
check("raw engine failure text is surfaced, not swallowed", r["ok"] is False and "boom" in json.dumps(r))

# ── Roblox: syntax + real execution in a Lua VM with an API mock ────────────
print("=== roblox programs ===")
try:
    from lupa import LuaRuntime
except Exception:  # pragma: no cover
    LuaRuntime = None
SAMPLES_R = {
    "ms_roblox_set_properties": {"path": "Workspace.A", "properties": {"Anchored": True}}, "ms_roblox_create_instance": {"class_name": "Part", "parent": "Workspace"},
    "ms_roblox_build_tree": {"parent": "Workspace", "tree": {"class": "Frame"}}, "ms_roblox_clone_instance": {"path": "Workspace.A"}, "ms_roblox_delete_instances": {"path": "Workspace.A"},
    "ms_roblox_move_instance": {"path": "Workspace.A"}, "ms_roblox_transform": {"path": "Workspace.A", "position": [1, 2, 3]}, "ms_roblox_tags": {"action": "list", "path": "Workspace.A"},
    "ms_roblox_attributes": {"action": "get", "path": "Workspace.A"}, "ms_roblox_terrain": {"action": "stats"}, "ms_roblox_script_manage": {"action": "read", "path": "Workspace.S"},
    "ms_roblox_replace_in_scripts": {"find": "a", "replace_with": "b"}, "ms_roblox_selection": {"action": "get"}, "ms_roblox_collision_groups": {"action": "list"},
    "ms_roblox_measure": {"paths": ["Workspace.A"]}, "ms_roblox_camera": {"action": "get"}, "ms_roblox_history": {"action": "undo"}, "ms_roblox_changes": {"action": "diff"},
    "ms_roblox_get_properties": {"path": "Workspace.A"}, "ms_roblox_run_luau": {"code": "return 1"},
}
roblox_ctx = Ctx({"roblox": ["execute_luau", "start_stop_play", "get_console_output"]})
if LuaRuntime is None:
    print("SKIP roblox Luau checks (pip install lupa to enable)")
else:
    lua = LuaRuntime(unpack_returned_tuples=True)
    syntax = lua.eval("function(c) local f, e = load(c); return e end")
    bad = []
    for n, spec in T.REGISTRY.items():
        if spec["engine"] != "roblox" or n in ("ms_roblox_playtest", "ms_roblox_run_luau"):
            continue
        d = run(n, dict(SAMPLES_R.get(n, PRO_SAMPLES.get(n, {})), dry_run=True), roblox_ctx)
        err = syntax(d["code"]) if d.get("code") else "no code"
        if err:
            bad.append((n, err))
    check("every Luau program is syntactically valid", not bad, bad)

    mock_src = (ROOT / "tests" / "fixtures" / "roblox_mock.lua").read_text(encoding="utf-8")

    def to_lua(rt, v):
        if isinstance(v, dict):
            return rt.table_from({k: to_lua(rt, x) for k, x in v.items()})
        if isinstance(v, list):
            return rt.table_from([to_lua(rt, x) for x in v])
        return v

    def from_lua(v):
        if hasattr(v, "items"):
            items = list(v.items())
            if items and all(isinstance(k, int) for k, _ in items) and sorted(k for k, _ in items) == list(range(1, len(items) + 1)):
                return [from_lua(x) for _, x in sorted(items)]
            return {str(k): from_lua(x) for k, x in items}
        return v

    def exec_luau(name, args, setup=None):
        rt = LuaRuntime(unpack_returned_tuples=True)
        rt.globals().JSON_DECODE = lambda s: to_lua(rt, json.loads(s))
        rt.globals().JSON_ENCODE = lambda t: json.dumps(from_lua(t))
        rt.execute(mock_src)
        if setup:
            rt.execute(setup)
        d = run(name, dict(args, dry_run=True), roblox_ctx)
        out = rt.execute(d["code"].replace("return out", "return out"))
        return T.extract_result(str(out)), rt

    res, rt = exec_luau("ms_roblox_create_part", {"shape": "Ball", "name": "Orb", "size": [2, 2, 2], "position": [1, 5, 1], "color": "#ff8800", "material": "Neon", "parent": "Workspace"})
    check("create_part runs in the VM and parents a real Part", res and res["ok"] and res["created"]["name"] == "Orb", res)
    res, rt = exec_luau("ms_roblox_build_tree", {"parent": "Workspace", "tree": {"class": "Frame", "name": "Menu", "properties": {"Size": {"xs": 0.5, "xo": 0, "ys": 0.5, "yo": 0}, "Visible": True},
                                                                             "children": [{"class": "TextLabel", "name": "Title", "properties": {"Text": "Hi"}}]}})
    check("build_tree creates nested UI with UDim2 coercion", res and res["ok"] and res["nodes"] == 2, res)
    res, rt = exec_luau("ms_roblox_list_children", {"path": "Workspace", "depth": 2}, 'local p=Instance.new("Part"); p.Name="P1"; p.Parent=workspace; local m=Instance.new("Model"); m.Name="M"; m.Parent=workspace; local q=Instance.new("Part"); q.Name="Q"; q.Parent=m')
    check("list_children walks depth and reports parts", res and res["ok"] and res["count"] == 3, res)
    res, rt = exec_luau("ms_roblox_set_properties", {"path": "Workspace.P1", "properties": {"Anchored": True, "Color": "#00ff00", "Material": "Wood", "Size": [1, 2, 3]}}, 'local p=Instance.new("Part"); p.Name="P1"; p.Parent=workspace')
    check("set_properties coerces Vector3/Color3/Enum to the property's real type", res and res["ok"] and sorted(res["results"][0]["applied"]) == ["Anchored", "Color", "Material", "Size"], res)
    res, rt = exec_luau("ms_roblox_set_properties", {"path": "Workspace.P1", "properties": {"NotAProp": 1}}, 'local p=Instance.new("Part"); p.Name="P1"; p.Parent=workspace')
    check("an unknown property is a precise error, not a silent no-op", res and res["ok"] is False and "NotAProp" in res["error"], res)
    res, rt = exec_luau("ms_roblox_set_properties", {"path": "Workspace.Nope", "properties": {"Anchored": True}})
    check("a bad path error lists the real children", res and res["ok"] is False and "cannot find 'Nope'" in res["error"], res)
    res, rt = exec_luau("ms_roblox_find_instances", {"name_contains": "p", "class": "Part"}, 'for i=1,3 do local p=Instance.new("Part"); p.Name="P"..i; p.Parent=workspace end')
    check("find_instances filters by name and class", res and res["ok"] and res["total"] == 3, res)
    res, rt = exec_luau("ms_roblox_get_properties", {"path": "Workspace.P1"}, 'local p=Instance.new("Part"); p.Name="P1"; p.Parent=workspace')
    check("get_properties returns class-appropriate defaults", res and res["ok"] and "Anchored" in res["properties"] and "Position" in res["properties"], res)
    res, rt = exec_luau("ms_roblox_script_manage", {"action": "create", "path": "ServerScriptService", "name": "Boot", "class_name": "Script", "source": 'print("hi")\nprint(1)'})
    check("script_manage creates a script with the exact source", res and res["ok"] and res["class"] == "Script" and res["lines"] == 2, res)
    res, rt = exec_luau("ms_roblox_delete_instances", {"path": "Workspace"})
    check("delete refuses to remove a service", res and res["ok"] is False and "refusing" in res["error"], res)
    res, rt = exec_luau("ms_roblox_lighting", {"properties": {"ClockTime": 6}})
    check("lighting applies a property and reads it back", res and res["ok"] and res["lighting"]["ClockTime"] == 6, res)
    hostile_lua = 'x]]==] "quote" \\ \n line2'
    res, rt = exec_luau("ms_roblox_attributes", {"action": "set", "path": "Workspace", "attributes": {"note": hostile_lua}})
    check("hostile strings survive the Luau JSON transport", res and res["ok"] and res["attributes"]["note"] == hostile_lua, res)

r = run("ms_roblox_set_properties", {"path": "Workspace.A", "properties": {"Anchored": True}}, Ctx({"roblox": ["execute_luau"]}, {"execute_luau": 'MS_RESULT:{"ok":true,"results":[]}'}))
check("roblox call carries studio_id and datamodel_type", r["ok"])
rc = Ctx({"roblox": ["execute_luau"]}, {"execute_luau": 'MS_RESULT:{"ok":true}'})
run("ms_roblox_list_children", {"mode": "Server"}, rc)
check("studio_id is injected and the DataModel honoured", rc.calls[0][2]["studio_id"] == "S1" and rc.calls[0][2]["datamodel_type"] == "Server")
amb = Ctx({"roblox": ["execute_luau"]}, studio=("", "ambiguous"))
r = run("ms_roblox_list_children", {}, amb)
check("two connected Studios -> refuse and ask for studio_id", r["ok"] is False and "studio_id" in r["hint"] and not amb.calls)
pt = Ctx({"roblox": ["start_stop_play", "get_console_output"]}, {"get_console_output": "Workspace.Script:4: attempt to index nil\nok"})
T.time.sleep = lambda s: None
r = run("ms_roblox_playtest", {"seconds": 1}, pt)
check("playtest = start, wait, read console, stop, verdict FAIL on errors", r["verdict"] == "FAIL" and [c[1] for c in pt.calls] == ["start_stop_play", "get_console_output", "start_stop_play"] and pt.calls[2][2]["is_start"] is False, r)

# ── Unity: translation to the real native calls ─────────────────────────────
print("=== unity plans ===")
UNITY = ["manage_scene", "find_gameobjects", "manage_gameobject", "manage_components", "create_script", "refresh_unity", "validate_script", "read_console", "script_apply_edits",
         "apply_text_edits", "manage_material", "manage_asset", "manage_prefabs", "manage_editor", "run_tests", "get_test_job", "manage_packages", "manage_physics", "execute_menu_item", "manage_ui"]
uc = Ctx({"unity": UNITY})
r = run("ms_unity_create_object", {"name": "Crate", "primitive_type": "Cube", "position": "1,2,3", "components_to_add": "Rigidbody, BoxCollider", "dry_run": True}, uc)
step = r["plan"][0]
check("create_object -> manage_gameobject(action=create) with vectors and component list",
      step["tool"] == "manage_gameobject" and step["arguments"] == {"action": "create", "name": "Crate", "primitive_type": "Cube", "position": [1, 2, 3], "components_to_add": ["Rigidbody", "BoxCollider"]}, step)
r = run("ms_unity_create_script", {"path": "Assets/Scripts/P.cs", "lines": ["using UnityEngine;", "public class P : MonoBehaviour {}"], "dry_run": True}, uc)
check("create_script plans write -> compile -> validate -> console", [s["tool"] for s in r["plan"]] == ["create_script", "refresh_unity", "validate_script", "read_console"] and "\n" in r["plan"][0]["arguments"]["contents"])
check("create_script refuses paths outside Assets/", run("ms_unity_create_script", {"path": "Scripts/P.cs", "contents": "x"}, uc)["ok"] is False)
r = run("ms_unity_arrange_objects", {"targets": ["a", "b", "c", "d"], "pattern": "grid", "columns": 2, "spacing": 3, "dry_run": True}, uc)
pos = [s["arguments"]["position"] for s in r["plan"]]
check("arrange_objects computes grid positions", pos == [[0, 0, 0], [3, 0, 0], [0, 0, 3], [3, 0, 3]], pos)
r = run("ms_unity_arrange_objects", {"targets": ["a", "b", "c", "d"], "pattern": "circle", "radius": 5, "dry_run": True}, uc)
check("arrange_objects circle keeps every object on the radius", all(abs((p[0] ** 2 + p[2] ** 2) ** 0.5 - 5) < 1e-3 for p in [s["arguments"]["position"] for s in r["plan"]]))
r = run("ms_unity_material", {"material_path": "Assets/M/Red.mat", "shader": "Universal Render Pipeline/Lit", "color": "#ff0000", "shader_properties": {"_Metallic": 0.5}, "assign_to": ["Crate"], "dry_run": True}, uc)
check("material picks _BaseColor for URP and chains property + assign", r["plan"][0]["arguments"]["properties"] == {"_BaseColor": [1, 0, 0, 1]} and [s["arguments"]["action"] for s in r["plan"]] == ["create", "set_material_shader_property", "assign_material_to_renderer"], r)
r = run("ms_unity_edit_script", {"path": "Assets/Scripts/P.cs", "edits": [{"op": "replace_method", "methodName": "Update", "replacement": "void Update(){}"}], "dry_run": True}, uc)
check("edit_script structured -> script_apply_edits with name/path split", r["plan"][0]["tool"] == "script_apply_edits" and r["plan"][0]["arguments"]["name"] == "P" and r["plan"][0]["arguments"]["path"] == "Assets/Scripts")
r = run("ms_unity_physics", {"action": "nonsense"}, uc)
check("dispatch tools reject unknown actions with the valid list", r["ok"] is False and "configure_rigidbody" in r["hint"])
r = run("ms_unity_create_object", {"name": "x"}, Ctx({"unity": ["find_gameobjects"]}))
check("missing native tool is reported by name", r["ok"] is False and "manage_gameobject" in r["error"])
okc = Ctx({"unity": UNITY}, {"manage_gameobject": '{"success": true, "data": {"instanceID": 42}}'})
r = run("ms_unity_create_object", {"name": "Crate"}, okc)
check("success path returns the parsed native data", r["ok"] and r["result"]["instanceID"] == 42, r)
failc = Ctx({"unity": UNITY}, {"manage_gameobject": '{"success": false, "error": "no such primitive"}'})
r = run("ms_unity_create_object", {"name": "Crate"}, failc)
check("a native success:false becomes ok:false", r["ok"] is False)
errc = Ctx({"unity": UNITY}, {"read_console": '{"success": true, "data": "Assets/P.cs(3,1): error CS1002: ; expected"}'})
r = run("ms_unity_create_script", {"path": "Assets/Scripts/P.cs", "contents": "class P {"}, errc)
check("create_script flags compile errors from the console", r["ok"] is False and "CS1002" in json.dumps(r["compileErrors"]), r)
with tempfile.TemporaryDirectory() as tmp:
    os.makedirs(os.path.join(tmp, "Assets", "Scenes"))
    os.makedirs(os.path.join(tmp, "Packages"))
    os.makedirs(os.path.join(tmp, "ProjectSettings"))
    open(os.path.join(tmp, "Assets", "Scenes", "Main.unity"), "w").write("x")
    open(os.path.join(tmp, "Assets", "A.cs"), "w").write("x")
    open(os.path.join(tmp, "Packages", "manifest.json"), "w").write(json.dumps({"dependencies": {"com.unity.render-pipelines.universal": "14.0.0", "com.unity.inputsystem": "1.7.0"}}))
    open(os.path.join(tmp, "ProjectSettings", "ProjectVersion.txt"), "w").write("m_EditorVersion: 2022.3.20f1\n")
    r = run("ms_unity_project_info", {"project_path": tmp}, Ctx())
    check("project_info reads version, pipeline, packages and scenes from disk", r["ok"] and r["unity_version"] == "2022.3.20f1" and r["render_pipeline"] == "URP" and r["input_system"] and r["scenes"] == ["Assets/Scenes/Main.unity"], r)

# ── Godot: real files ───────────────────────────────────────────────────────
print("=== godot files ===")
with tempfile.TemporaryDirectory() as proj:
    open(os.path.join(proj, "project.godot"), "w").write('; Engine configuration file.\nconfig_version=5\n\n[application]\n\nconfig/name="Demo"\nrun/main_scene="res://scenes/Main.tscn"\n\n[display]\n\nwindow/size/viewport_width=1280\n')
    gc = Ctx({"godot": ["run_project", "get_debug_output", "stop_project"]}, {"get_debug_output": "SCRIPT ERROR: Invalid call. Nonexistent function 'x'"})
    G = lambda n, **a: run(n, dict(a, project_path=proj), gc)  # noqa: E731
    r = G("ms_godot_script_create", path="res://scripts/Player.gd", template="platformer_2d")
    check("script_create writes a GDScript 4 template that passes the static check", r["ok"] and r["static_check"]["ok"] and os.path.isfile(os.path.join(proj, "scripts/Player.gd")), r)
    r = G("ms_godot_script_create", path="res://scripts/Player.gd", template="empty")
    check("script_create refuses to overwrite by default", r["ok"] is False)
    r = G("ms_godot_scene_create", scene_path="res://scenes/Main.tscn", root_type="Node2D", root_name="Main",
          children=[{"name": "Player", "type": "CharacterBody2D", "script": "res://scripts/Player.gd", "properties": {"position": {"x": 100, "y": 200}},
                     "children": [{"name": "Sprite", "type": "Sprite2D", "properties": {"modulate": "#ff8800"}}, {"name": "Col", "type": "CollisionShape2D"}]},
                    {"name": "HUD", "type": "CanvasLayer", "groups": ["ui"]}])
    text = open(os.path.join(proj, "scenes/Main.tscn")).read()
    check("scene_create writes a valid tscn (header, ext_resource, nested parents, literals)",
          r["ok"] and text.startswith("[gd_scene load_steps=2 format=3]") and 'parent="Player"' in text and "position = Vector2(100, 200)" in text and 'modulate = Color("#ff8800")' in text
          and 'groups=["ui"]' in text and 'script = ExtResource("1_' in text, text)
    r = G("ms_godot_node_add", scene_path="res://scenes/Main.tscn", parent="Player", name="Cam", type="Camera2D", properties={"zoom": [2, 2]})
    check("node_add inserts under the parent with a Vector2", r["ok"] and r["added"] == "Player/Cam" and "zoom = Vector2(2, 2)" in open(os.path.join(proj, "scenes/Main.tscn")).read(), r)
    check("node_add rejects duplicate siblings", G("ms_godot_node_add", scene_path="res://scenes/Main.tscn", parent="Player", name="Cam", type="Camera2D")["ok"] is False)
    check("node_add to a missing parent lists the real nodes", "Player" in G("ms_godot_node_add", scene_path="res://scenes/Main.tscn", parent="Nope", name="X", type="Node").get("hint", ""))
    r = G("ms_godot_node_edit", scene_path="res://scenes/Main.tscn", node="Player/Sprite", properties={"visible": False}, new_name="Body")
    tree = G("ms_godot_scene_tree", scene_path="res://scenes/Main.tscn")
    check("node_edit renames and sets properties; the tree reflects it", r["ok"] and "Body (Sprite2D)" in tree["text_tree"] and "visible = false" in open(os.path.join(proj, "scenes/Main.tscn")).read(), tree.get("text_tree"))
    r = G("ms_godot_signals", scene_path="res://scenes/Main.tscn", action="connect", signal="body_entered", from_node="Player", to_node=".", method="_on_hit")
    check("signals.connect writes a [connection] block", r["ok"] and r["connections"][0]["method"] == "_on_hit", r)
    r = G("ms_godot_node_edit", scene_path="res://scenes/Main.tscn", node="Player", delete=True)
    check("deleting a node removes its subtree and its connections", r["ok"] and "Player/Body" in r["deleted"] and r["connections_removed"] == 1, r)
    r = G("ms_godot_input_map", action="set", name="jump", keys=["space", "pad_a"])
    ptxt = open(os.path.join(proj, "project.godot")).read()
    check("input_map writes Godot 4 InputEvent objects for key and gamepad", r["ok"] and '"physical_keycode":32' in ptxt and "InputEventJoypadButton" in ptxt and r["actions"]["jump"]["joypad"], ptxt)
    check("input_map rejects unknown keys with a hint", G("ms_godot_input_map", action="set", name="x", keys=["banana"])["ok"] is False)
    r = G("ms_godot_project_setting", action="set", setting="display/window/size/viewport_height", value=720)
    check("project_setting adds a key inside the existing section", r["ok"] and "window/size/viewport_height=720" in open(os.path.join(proj, "project.godot")).read())
    r = G("ms_godot_project_setting", action="set", setting="rendering/renderer/rendering_method", value="mobile")
    check("project_setting creates a missing section", r["ok"] and '[rendering]' in open(os.path.join(proj, "project.godot")).read())
    check("project_setting get returns the stored literal", G("ms_godot_project_setting", action="get", setting="application/config/name")["value"] == '"Demo"')
    r = G("ms_godot_autoload", action="add", name="GameManager", path="res://scripts/Player.gd")
    check("autoload add/list", r["ok"] and r["autoloads"]["GameManager"] == "*res://scripts/Player.gd")
    check("autoload refuses a missing target", G("ms_godot_autoload", action="add", name="X", path="res://nope.gd")["ok"] is False)
    G("ms_godot_scene_create", scene_path="res://scenes/Main.tscn", root_type="Node2D", overwrite=True)
    r = G("ms_godot_validate_project")
    check("validate_project passes a consistent project", r["ok"] and r["verdict"] == "clean", r)
    open(os.path.join(proj, "scenes/Broken.tscn"), "w").write('[gd_scene load_steps=2 format=3]\n\n[ext_resource type="Script" path="res://gone.gd" id="1_x"]\n\n[node name="B" type="Node"]\n')
    r = G("ms_godot_validate_project")
    check("validate_project finds a scene pointing at a deleted script", any(p["kind"] == "missing_resource" for p in r["problems"]), r)
    r = G("ms_godot_move_file", from_path="res://scripts/Player.gd", to_path="res://actors/Player.gd")
    check("move_file rewrites references in project.godot and moves the file", r["ok"] and os.path.isfile(os.path.join(proj, "actors/Player.gd")) and "res://actors/Player.gd" in open(os.path.join(proj, "project.godot")).read(), r)
    r = G("ms_godot_find_references", path="res://actors/Player.gd")
    check("find_references reports the autoload reference", r["ok"] and not r["safe_to_delete"])
    r = G("ms_godot_script_edit", path="res://actors/Player.gd", edits=[{"op": "replace_text", "find": "NOT THERE", "replace_with": "x"}])
    check("script_edit is atomic: a failed match writes nothing", r["ok"] is False and "NOT THERE" not in open(os.path.join(proj, "actors/Player.gd")).read())
    r = G("ms_godot_script_edit", path="res://actors/Player.gd", edits=[{"op": "replace_function", "name": "_physics_process", "body": "func _physics_process(delta: float) -> void:\n\tmove_and_slide()\n"}])
    check("script_edit replace_function swaps one function", r["ok"] and "move_and_slide()" in open(os.path.join(proj, "actors/Player.gd")).read() and "coyote" in open(os.path.join(proj, "actors/Player.gd")).read())
    open(os.path.join(proj, "old.gd"), "w").write("export var hp = 3\nfunc _ready():\n    yield(get_tree(), 'idle_frame')\n")
    r = G("ms_godot_script_check", path="res://old.gd", headless=False)
    check("script_check flags Godot-3 syntax", r["scripts_with_issues"] == 1 and any("yield" in i for i in r["files"][0]["issues"]), r)
    G("ms_godot_changes", action="checkpoint")
    open(os.path.join(proj, "new.gd"), "w").write("extends Node\n")
    r = G("ms_godot_changes", action="diff")
    check("changes reports files added since the checkpoint", r["ok"] and "res://new.gd" in r["added"], r)
    r = G("ms_godot_playtest", seconds=1)
    check("godot playtest: run -> wait -> debug output -> stop, verdict FAIL on SCRIPT ERROR", r["verdict"] == "FAIL" and [c[1] for c in gc.calls][-3:] == ["run_project", "get_debug_output", "stop_project"], r)
    r = run("ms_godot_project_overview", {}, gc)
    check("project_path is remembered after the first call", r["ok"] and r["name"] == "Demo")
    try:
        r = run("ms_godot_scene_tree", {"project_path": proj, "scene_path": "../../etc/passwd.tscn"}, gc)
        check("paths cannot escape the project", r["ok"] is False and "escapes" in r["error"], r)
    except Exception as exc:
        check("paths cannot escape the project", False, exc)

# ── bridge integration ──────────────────────────────────────────────────────
print("=== bridge integration ===")
spec = importlib.util.spec_from_file_location("toolkit_bridge", ROOT / "runtime" / "bridge.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
check("bridge loads the toolkit", b._TOOLKIT is not None and b.TOOLKIT_ERROR is None, getattr(b, "TOOLKIT_ERROR", None))
check("toolkit names never collide with built-in tool names", not (set(T.REGISTRY) & b.BUILTIN_TOOL_NAMES))


class FakeClient:
    def __init__(self, tools):
        self.tools_cache = [{"name": n, "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}, "datamodel_type": {"type": "string"}, "studio_id": {"type": "string"}}}} for n in tools]
        self.sent = []

    def is_alive(self):
        return True

    def call_tool(self, name, args, timeout):
        self.sent.append((name, args))
        return {"text": 'MS_RESULT:{"ok": true, "items": []}', "images": []}


mgr = b.MCPManager.__new__(b.MCPManager)
mgr.clients = {"roblox": FakeClient(["execute_luau"]), "blender": FakeClient(["execute_blender_code"])}
import threading  # noqa: E402
mgr.index, mgr.index_lock = {}, threading.Lock()
visible = b._toolkit_visible_tools(mgr)
engines = {t["server"] for t in visible}
check("only engines with a configured server get their toolkit listed", engines == {"roblox", "blender"}, engines)
res = mgr.call("ms_roblox_list_children", {"path": "Workspace", "depth": "2", "mode": "edit"}, 30)
out = json.loads(res["text"])
sent = mgr.clients["roblox"].sent[0]
check("bridge routes a toolkit call through the live server with repaired arguments", out["ok"] and sent[0] == "execute_luau" and sent[1]["datamodel_type"] in ("Edit", "edit"), (out, sent))
res = mgr.call("ms_blender_list_objects", {"limit": "5", "type": "mesh"}, 30)
check("string numbers are repaired before the toolkit sees them", json.loads(res["text"])["ok"])
check("capabilities report lists the toolkit per engine", "engineToolkit" in json.dumps(b._native_facade_call("ms_native_capabilities", {"server": "blender"}, types.SimpleNamespace(
    health=lambda: [{"id": "blender", "alive": True}], clients=mgr.clients, list_tools=lambda refresh=False: []))["text"]))

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("ALL PASS")
