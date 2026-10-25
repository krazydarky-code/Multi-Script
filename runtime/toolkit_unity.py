# SPDX-License-Identifier: GPL-3.0-or-later
"""Unity tools for engine_toolkit. They compile to the exact, advertised CoplayDev unity-mcp
tool calls (manage_gameobject, manage_components, manage_material, ...) run in order, plus
a few bridge-side project-file tools that work even when the editor is closed."""
import json
import math
import os
import re
import time

from engine_toolkit import (tool, as_list, as_dict, vec3, color4, num, boolean, ToolkitError, _need,
                            snapshot_store, snapshot_get, diff_maps)

U = "unity"
VEC = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
TARGET = {"type": "string", "description": "GameObject name, hierarchy path (Parent/Child) or instance id."}
SEARCH = {"type": "string", "enum": ["by_name", "by_path", "by_id", "by_tag", "by_layer", "by_component"], "description": "How `target` is looked up (default by_name)."}


def _parse(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def _failed(parsed, text):
    if isinstance(parsed, dict):
        if parsed.get("success") is False:
            return True
        if parsed.get("error"):
            return True
    low = (text or "")[:300].lower()
    return low.startswith("error") or "unknown tool" in low or "invalid parameters" in low


def _steps(ctx, args, steps, label, stop_on_error=True, timeout=120):
    """Run [(tool_name, arguments, label)] in order. Returns the envelope body."""
    resolved = []
    for tname, targs, lab in steps:
        names = tname if isinstance(tname, (tuple, list)) else (tname,)
        resolved.append((_need(ctx, U, *names), targs, lab))
    plan = [{"tool": t, "arguments": a, "label": l} for t, a, l in resolved]
    if args.get("dry_run"):
        return {"dryRun": True, "plan": plan}
    results, images = [], []
    ok = True
    for t, a, l in resolved:
        raw = ctx.call(U, t, a, timeout)
        text = str((raw or {}).get("text") or "")
        parsed = _parse(text)
        bad = _failed(parsed, text)
        entry = {"tool": t, "label": l, "ok": not bad}
        if parsed is not None:
            entry["data"] = parsed.get("data", parsed) if isinstance(parsed, dict) else parsed
            if isinstance(parsed, dict) and parsed.get("message"):
                entry["message"] = parsed["message"]
        else:
            entry["text"] = text[:3000]
        results.append(entry)
        images.extend((raw or {}).get("images") or [])
        if bad:
            ok = False
            if stop_on_error:
                break
    body = {"ok": ok, "results": results if len(results) > 1 else results[0], "nativeCalls": [{"tool": t, "label": l} for t, a, l in resolved[:len(results)]]}
    if len(results) == 1 and ok:
        body = {"ok": True, "result": results[0].get("data", results[0].get("text")), "message": results[0].get("message"), "nativeCall": results[0]["tool"]}
    return (body, images) if images else body


def _clean(d):
    return {k: v for k, v in d.items() if v is not None and v != ""}


def _vec_or_none(v):
    return vec3(v)


@tool(U, "ms_unity_hierarchy",
      "Read the scene hierarchy (paged) with optional local transforms. Use `parent` to drill into a branch. Read-only.",
      {"parent": TARGET, "page_size": {"type": "integer", "minimum": 1, "maximum": 500}, "cursor": {"type": "integer", "minimum": 0}, "include_transform": {"type": "boolean"}})
def hierarchy(args, ctx):
    a = _clean({"action": "get_hierarchy", "page_size": num(args.get("page_size"), 100, 1, 500, True), "cursor": num(args.get("cursor"), None, 0, None, True),
                "parent": args.get("parent") or None, "include_transform": boolean(args.get("include_transform"), False) or None})
    return _steps(ctx, args, [("manage_scene", a, "get hierarchy")], "hierarchy")


@tool(U, "ms_unity_find_objects",
      "Find GameObjects by name, path, tag, layer or component type. Returns instance ids to pass to the other ms_unity_* tools. Read-only.",
      {"search_term": {"type": "string"}, "search_method": SEARCH, "include_inactive": {"type": "boolean"},
       "page_size": {"type": "integer", "minimum": 1, "maximum": 500}, "cursor": {"type": "integer", "minimum": 0}}, ["search_term"])
def find_objects(args, ctx):
    a = _clean({"search_term": str(args.get("search_term") or ""), "search_method": args.get("search_method") or "by_name",
                "include_inactive": boolean(args.get("include_inactive"), False), "page_size": num(args.get("page_size"), 50, 1, 500, True),
                "cursor": num(args.get("cursor"), None, 0, None, True)})
    return _steps(ctx, args, [("find_gameobjects", a, "find")], "find")


@tool(U, "ms_unity_create_object",
      "Create a GameObject: primitive (Cube, Sphere, Capsule, Cylinder, Plane, Quad) or empty, or instantiate a prefab (`prefab_path`). Sets name, position, "
      "rotation (euler degrees), scale, parent, tag, layer and adds components in one call.",
      {"name": {"type": "string"}, "primitive_type": {"type": "string", "enum": ["Cube", "Sphere", "Capsule", "Cylinder", "Plane", "Quad"]},
       "prefab_path": {"type": "string"}, "position": VEC, "rotation": VEC, "scale": VEC, "parent": TARGET,
       "tag": {"type": "string"}, "layer": {"type": "string"}, "components_to_add": {"type": "array", "items": {"type": "string"}, "description": "e.g. Rigidbody, BoxCollider, AudioSource."}}, ["name"], writes=True)
def create_object(args, ctx):
    a = _clean({"action": "create", "name": str(args.get("name") or "GameObject"), "primitive_type": args.get("primitive_type"), "prefab_path": args.get("prefab_path"),
                "position": vec3(args.get("position")), "rotation": vec3(args.get("rotation")), "scale": vec3(args.get("scale")), "parent": args.get("parent"),
                "tag": args.get("tag"), "layer": args.get("layer"), "components_to_add": as_list(args.get("components_to_add")) or None})
    return _steps(ctx, args, [("manage_gameobject", a, "create " + a["name"])], "create")


@tool(U, "ms_unity_modify_object",
      "Modify an existing GameObject: position/rotation/scale, active state, layer, tag, add/remove components, and set component fields via `component_properties` "
      "{Rigidbody:{mass:5}}. Use ms_unity_find_objects first to get a precise target.",
      {"target": TARGET, "search_method": SEARCH, "position": VEC, "rotation": VEC, "scale": VEC, "set_active": {"type": "boolean"}, "layer": {"type": "string"}, "tag": {"type": "string"},
       "new_name": {"type": "string"}, "components_to_add": {"type": "array", "items": {"type": "string"}}, "components_to_remove": {"type": "array", "items": {"type": "string"}},
       "component_properties": {"type": "object"}}, ["target"], writes=True)
def modify_object(args, ctx):
    a = _clean({"action": "modify", "target": str(args.get("target") or ""), "search_method": args.get("search_method") or "by_name",
                "position": vec3(args.get("position")), "rotation": vec3(args.get("rotation")), "scale": vec3(args.get("scale")),
                "set_active": args.get("set_active"), "layer": args.get("layer"), "tag": args.get("tag"), "name": args.get("new_name"),
                "components_to_add": as_list(args.get("components_to_add")) or None, "components_to_remove": as_list(args.get("components_to_remove")) or None,
                "component_properties": as_dict(args.get("component_properties")) or None})
    return _steps(ctx, args, [("manage_gameobject", a, "modify " + a["target"])], "modify")


@tool(U, "ms_unity_delete_object", "Delete a GameObject from the open scene.", {"target": TARGET, "search_method": SEARCH}, ["target"], writes=True)
def delete_object(args, ctx):
    a = _clean({"action": "delete", "target": str(args.get("target") or ""), "search_method": args.get("search_method") or "by_name"})
    return _steps(ctx, args, [("manage_gameobject", a, "delete " + a["target"])], "delete")


@tool(U, "ms_unity_duplicate_object", "Duplicate a GameObject with a new name and an offset from the original.",
      {"target": TARGET, "new_name": {"type": "string"}, "offset": VEC, "count": {"type": "integer", "minimum": 1, "maximum": 50}}, ["target"], writes=True)
def duplicate_object(args, ctx):
    n = num(args.get("count"), 1, 1, 50, True)
    off = vec3(args.get("offset"), [1.0, 0.0, 0.0])
    steps = []
    for i in range(n):
        a = _clean({"action": "duplicate", "target": str(args.get("target") or ""), "new_name": (f"{args['new_name']}{i + 1 if n > 1 else ''}" if args.get("new_name") else None),
                    "offset": [off[0] * (i + 1), off[1] * (i + 1), off[2] * (i + 1)]})
        steps.append(("manage_gameobject", a, f"duplicate #{i + 1}"))
    return _steps(ctx, args, steps, "duplicate")


@tool(U, "ms_unity_arrange_objects",
      "Lay out existing GameObjects in a pattern - grid, line or circle - by computing every position and applying them in order. "
      "Great for level dressing: pass `targets` and the pattern parameters.",
      {"targets": {"type": "array", "items": {"type": "string"}, "description": "GameObject names/paths in layout order."},
       "pattern": {"type": "string", "enum": ["grid", "line", "circle"]}, "origin": VEC, "spacing": {"type": "number"}, "columns": {"type": "integer", "minimum": 1},
       "radius": {"type": "number"}, "axis": {"type": "string", "enum": ["x", "y", "z"]}, "face_center": {"type": "boolean"}}, ["targets", "pattern"], writes=True)
def arrange_objects(args, ctx):
    targets = [str(t) for t in as_list(args.get("targets"))][:60]
    if not targets:
        raise ToolkitError("give `targets`")
    origin = vec3(args.get("origin"), [0.0, 0.0, 0.0])
    pat = str(args.get("pattern") or "grid").lower()
    sp = num(args.get("spacing"), 2.0, 0.01, 1000)
    steps = []
    for i, t in enumerate(targets):
        if pat == "line":
            ax = {"x": 0, "y": 1, "z": 2}.get(str(args.get("axis") or "x").lower(), 0)
            p = list(origin)
            p[ax] += i * sp
            rot = None
        elif pat == "circle":
            r = num(args.get("radius"), max(sp * len(targets) / (2 * math.pi), 1.0), 0.01, 10000)
            ang = 2 * math.pi * i / len(targets)
            p = [origin[0] + r * math.cos(ang), origin[1], origin[2] + r * math.sin(ang)]
            rot = [0.0, round(-math.degrees(ang) + 90, 3), 0.0] if boolean(args.get("face_center"), False) else None
        else:
            cols = num(args.get("columns"), max(1, int(math.ceil(math.sqrt(len(targets))))), 1, 1000, True)
            p = [origin[0] + (i % cols) * sp, origin[1], origin[2] + (i // cols) * sp]
            rot = None
        p = [round(x, 4) for x in p]
        steps.append(("manage_gameobject", _clean({"action": "modify", "target": t, "position": p, "rotation": rot}), f"place {t}"))
    return _steps(ctx, args, steps, "arrange")


@tool(U, "ms_unity_components",
      "Add, remove or set fields on components: action=add|remove|set_property. For set_property pass `property`+`value` or a `properties` object. "
      "Object references accept {name:..}, {path:..}, {guid:..} or an asset path string.",
      {"action": {"type": "string", "enum": ["add", "remove", "set_property"]}, "target": TARGET, "component_type": {"type": "string"},
       "property": {"type": "string"}, "value": {"description": "New value (number, string, bool, array, object reference)."}, "properties": {"type": "object"},
       "search_method": SEARCH}, ["action", "target", "component_type"], writes=True)
def components(args, ctx):
    act = str(args.get("action") or "add").lower()
    a = _clean({"action": act, "target": str(args.get("target") or ""), "component_type": str(args.get("component_type") or ""),
                "search_method": args.get("search_method") or "by_name", "property": args.get("property"), "value": args.get("value"),
                "properties": as_dict(args.get("properties")) or None})
    if act == "set_property" and "property" not in a and "properties" not in a:
        raise ToolkitError("set_property needs `property`+`value` or `properties`")
    return _steps(ctx, args, [("manage_components", a, f"{act} {a['component_type']}")], "components")


def _uri(path):
    p = str(path or "").replace("\\", "/").lstrip("/")
    return p if p.startswith("mcpforunity://") else "mcpforunity://path/" + p


def _source(args):
    if args.get("lines"):
        return "\n".join(str(x) for x in as_list(args.get("lines")))
    return args.get("contents") if args.get("contents") is not None else args.get("source")


@tool(U, "ms_unity_create_script",
      "Create or overwrite a C# script, then refresh/compile, validate it and read the console errors - the whole write->compile->verify loop in one call. "
      "Give the source as `lines` (array) or `contents`.",
      {"path": {"type": "string", "description": "Assets/Scripts/Player.cs"}, "contents": {"type": "string"}, "lines": {"type": "array", "items": {"type": "string"}},
       "namespace": {"type": "string"}, "validate": {"type": "boolean"}}, ["path"], writes=True)
def create_script(args, ctx):
    path = str(args.get("path") or "")
    if not re.match(r"^Assets/.+\.cs$", path.replace("\\", "/")):
        raise ToolkitError("path must be like Assets/Scripts/Name.cs", "Scripts must live under Assets/ and end in .cs")
    src = _source(args)
    if not src:
        raise ToolkitError("give `contents` or `lines`")
    steps = [("create_script", _clean({"path": path.replace("\\", "/"), "contents": src, "namespace": args.get("namespace")}), "create script"),
             ("refresh_unity", {"mode": "force", "scope": "all", "compile": "request", "wait_for_ready": True}, "compile")]
    if boolean(args.get("validate"), True):
        steps.append(("validate_script", {"uri": _uri(path), "level": "standard", "include_diagnostics": True}, "validate"))
    steps.append(("read_console", {"action": "get", "types": ["error"], "count": 15, "format": "plain"}, "console errors"))
    out = _steps(ctx, args, steps, "create script", stop_on_error=True, timeout=180)
    body = out[0] if isinstance(out, tuple) else out
    if body.get("ok") and isinstance(body.get("results"), list):
        errs = body["results"][-1].get("data") or body["results"][-1].get("text")
        body["compileErrors"] = errs
        txt = json.dumps(errs) if not isinstance(errs, str) else errs
        if re.search(r"error CS\d+", txt):
            body["ok"] = False
            body["hint"] = "The script has compile errors (see compileErrors). Fix them with ms_unity_edit_script and re-check."
    return out


@tool(U, "ms_unity_edit_script",
      "Edit an existing C# script safely. mode=structured uses script_apply_edits ops (replace_method, insert_method, delete_method, anchor_insert, regex_replace, prepend, append); "
      "mode=text uses precise line/column edits. Always followed by refresh + validate.",
      {"path": {"type": "string"}, "mode": {"type": "string", "enum": ["structured", "text"]},
       "edits": {"type": "array", "items": {"type": "object"}, "description": "structured: [{op:'replace_method',methodName,replacement}...]; text: [{startLine,startCol,endLine,endCol,newText}...] (1-indexed)."}},
      ["path", "edits"], writes=True)
def edit_script(args, ctx):
    path = str(args.get("path") or "").replace("\\", "/")
    edits = [as_dict(e) for e in as_list(args.get("edits"))]
    if not edits:
        raise ToolkitError("give `edits`")
    mode = str(args.get("mode") or ("text" if "startLine" in edits[0] else "structured")).lower()
    if mode == "text":
        first = ("apply_text_edits", {"uri": _uri(path), "edits": edits}, "apply text edits")
    else:
        folder, _, fname = path.rpartition("/")
        first = ("script_apply_edits", {"name": re.sub(r"\.cs$", "", fname), "path": folder, "edits": edits}, "apply structured edits")
    steps = [first, ("refresh_unity", {"mode": "force", "scope": "scripts", "compile": "request", "wait_for_ready": True}, "compile"),
             ("validate_script", {"uri": _uri(path), "level": "standard", "include_diagnostics": True}, "validate"),
             ("read_console", {"action": "get", "types": ["error"], "count": 15, "format": "plain"}, "console errors")]
    return _steps(ctx, args, steps, "edit script", timeout=180)


@tool(U, "ms_unity_script_check", "Validate a script and read the latest console errors. Read-only.",
      {"path": {"type": "string"}}, ["path"])
def script_check(args, ctx):
    path = str(args.get("path") or "").replace("\\", "/")
    return _steps(ctx, args, [("validate_script", {"uri": _uri(path), "level": "standard", "include_diagnostics": True}, "validate"),
                              ("read_console", {"action": "get", "types": ["error", "warning"], "count": 20, "format": "plain"}, "console")], "check", stop_on_error=False)


@tool(U, "ms_unity_scene",
      "Scene operations: action=active|build_settings|create|load|save. create takes `name` (+ folder `path`), load takes the scene asset `path`.",
      {"action": {"type": "string", "enum": ["active", "build_settings", "create", "load", "save"]}, "name": {"type": "string"}, "path": {"type": "string"}}, ["action"], writes=True)
def scene(args, ctx):
    act = str(args.get("action") or "active").lower()
    m = {"active": "get_active", "build_settings": "get_build_settings"}.get(act, act)
    a = {"action": m}
    if act == "create":
        a.update(name=str(args.get("name") or "NewScene"), path=str(args.get("path") or "Assets/Scenes/"))
    elif act == "load":
        if not args.get("path"):
            raise ToolkitError("load needs the scene asset `path`")
        a["path"] = str(args["path"])
    elif act == "save" and args.get("path"):
        a["path"] = str(args["path"])
    return _steps(ctx, args, [("manage_scene", a, "scene " + act)], "scene")


@tool(U, "ms_unity_material",
      "Create a material (Standard/URP/HDRP shader), set colour and shader properties, and optionally assign it to renderers - one call. "
      "Pick the shader that matches the render pipeline (ms_unity_project_info tells you).",
      {"material_path": {"type": "string", "description": "Assets/Materials/Red.mat"}, "shader": {"type": "string", "description": "Standard, Universal Render Pipeline/Lit, HDRP/Lit ..."},
       "color": {"type": "string", "description": "Hex like #ff0000 or [r,g,b,a]."}, "color_property": {"type": "string", "description": "_Color (Standard) or _BaseColor (URP/HDRP)."},
       "shader_properties": {"type": "object", "description": "{_Metallic:0.8,_Smoothness:0.6}"}, "assign_to": {"type": "array", "items": {"type": "string"}}}, ["material_path"], writes=True)
def material(args, ctx):
    path = str(args.get("material_path") or "")
    shader = str(args.get("shader") or "Standard")
    col = color4(args.get("color"))
    prop = str(args.get("color_property") or ("_BaseColor" if re.search(r"universal|urp|hdrp|lit$", shader, re.I) and shader != "Standard" else "_Color"))
    steps = [("manage_material", _clean({"action": "create", "material_path": path, "shader": shader, "properties": ({prop: col} if col else None)}), "create material")]
    for k, v in as_dict(args.get("shader_properties")).items():
        steps.append(("manage_material", {"action": "set_material_shader_property", "material_path": path, "property": k, "value": v}, f"set {k}"))
    for t in as_list(args.get("assign_to")):
        steps.append(("manage_material", {"action": "assign_material_to_renderer", "target": str(t), "material_path": path, "slot": 0}, f"assign to {t}"))
    return _steps(ctx, args, steps, "material")


@tool(U, "ms_unity_asset",
      "Asset database operations: action=search|info|create_folder|move|rename|duplicate|delete|create. search takes `pattern` (glob or t:Type filter) under `path`.",
      {"action": {"type": "string", "enum": ["search", "info", "create_folder", "move", "rename", "duplicate", "delete", "create"]}, "path": {"type": "string"},
       "destination": {"type": "string"}, "pattern": {"type": "string"}, "asset_type": {"type": "string"}, "properties": {"type": "object"},
       "page_size": {"type": "integer", "minimum": 1, "maximum": 100}, "page": {"type": "integer", "minimum": 1}}, ["action"], writes=True)
def asset(args, ctx):
    act = str(args.get("action") or "search").lower()
    m = {"info": "get_info"}.get(act, act)
    a = _clean({"action": m, "path": args.get("path") or ("Assets" if act == "search" else None), "destination": args.get("destination"),
                "search_pattern": args.get("pattern"), "filter_type": args.get("asset_type") if act == "search" else None,
                "asset_type": args.get("asset_type") if act == "create" else None, "properties": as_dict(args.get("properties")) or None,
                "page_size": num(args.get("page_size"), 25, 1, 100, True) if act == "search" else None,
                "page_number": num(args.get("page"), 1, 1, None, True) if act == "search" else None, "generate_preview": False if act == "search" else None})
    if act in ("move", "rename", "duplicate") and not a.get("destination"):
        raise ToolkitError(f"{act} needs `destination`")
    return _steps(ctx, args, [("manage_asset", a, "asset " + act)], "asset")


@tool(U, "ms_unity_prefab",
      "Prefab operations: action=info|hierarchy|create_from_object|modify|open|save|close. create_from_object turns a scene object into a prefab asset; modify edits the prefab headlessly.",
      {"action": {"type": "string", "enum": ["info", "hierarchy", "create_from_object", "modify", "open", "save", "close"]}, "prefab_path": {"type": "string"}, "target": TARGET,
       "overwrite": {"type": "boolean"}, "modify": {"type": "object", "description": "For modify: {position,components_to_add,component_properties,create_child,delete_child,...}."}}, ["action"], writes=True)
def prefab(args, ctx):
    act = str(args.get("action") or "info").lower()
    m = {"info": "get_info", "hierarchy": "get_hierarchy", "create_from_object": "create_from_gameobject", "modify": "modify_contents",
         "open": "open_prefab_stage", "save": "save_prefab_stage", "close": "close_prefab_stage"}.get(act)
    if not m:
        raise ToolkitError(f"unknown prefab action '{act}'", "use info, hierarchy, create_from_object, modify, open, save or close")
    a = _clean({"action": m, "prefab_path": args.get("prefab_path"), "target": args.get("target"), "allow_overwrite": args.get("overwrite") if act == "create_from_object" else None})
    if act == "modify":
        a.update(as_dict(args.get("modify")))
    return _steps(ctx, args, [(("manage_prefabs",) if act not in ("open", "save", "close") else ("manage_editor", "manage_prefabs"), a, "prefab " + act)], "prefab")


@tool(U, "ms_unity_play", "Editor play state: action=play|pause|stop.", {"action": {"type": "string", "enum": ["play", "pause", "stop"]}}, ["action"], writes=True)
def play(args, ctx):
    act = str(args.get("action") or "play").lower()
    return _steps(ctx, args, [("manage_editor", {"action": act}, "editor " + act)], "play")


@tool(U, "ms_unity_playtest",
      "Play-test loop: clear console, enter play mode, wait `seconds`, collect errors/warnings, stop play mode. Returns PASS/WARN/FAIL with the evidence.",
      {"seconds": {"type": "integer", "minimum": 1, "maximum": 120}, "stop_after": {"type": "boolean"}}, [], writes=True)
def playtest(args, ctx):
    ed = _need(ctx, U, "manage_editor")
    con = _need(ctx, U, "read_console")
    secs = num(args.get("seconds"), 6, 1, 120, True)
    plan = [{"tool": con, "arguments": {"action": "clear"}}, {"tool": ed, "arguments": {"action": "play"}}, {"wait_seconds": secs},
            {"tool": con, "arguments": {"action": "get", "types": ["error", "warning"], "count": 40, "format": "plain"}}]
    if args.get("dry_run"):
        return {"dryRun": True, "plan": plan}
    ctx.call(U, con, {"action": "clear"}, 30)
    ctx.call(U, ed, {"action": "play"}, 60)
    time.sleep(secs)
    out = ctx.call(U, con, {"action": "get", "types": ["error", "warning"], "count": 40, "format": "plain"}, 60)
    text = str((out or {}).get("text") or "")
    stopped = False
    if boolean(args.get("stop_after"), True):
        try:
            ctx.call(U, ed, {"action": "stop"}, 60)
            stopped = True
        except Exception as exc:
            text += f"\n[could not stop play mode: {exc}]"
    lines = [l for l in text.splitlines() if l.strip()]
    errs = [l for l in lines if re.search(r"error|exception|nullreference|cs\d{4}", l, re.I)]
    warns = [l for l in lines if "warn" in l.lower() and l not in errs]
    return {"ok": True, "verdict": "FAIL" if errs else ("WARN" if warns else "PASS"), "ran_seconds": secs, "stopped": stopped,
            "errors": errs[:30], "warnings": warns[:20], "next": "Fix each error, refresh, and run ms_unity_playtest again until PASS."}


@tool(U, "ms_unity_console", "Read or clear the Unity console: action=get|clear, with `types` (error|warning|log|all), text filter and count.",
      {"action": {"type": "string", "enum": ["get", "clear"]}, "types": {"type": "array", "items": {"type": "string", "enum": ["error", "warning", "log", "all"]}},
       "filter_text": {"type": "string"}, "count": {"type": "integer", "minimum": 1, "maximum": 200}, "stacktrace": {"type": "boolean"}}, ["action"])
def console(args, ctx):
    act = str(args.get("action") or "get").lower()
    a = {"action": act} if act == "clear" else _clean({"action": "get", "types": as_list(args.get("types")) or ["error", "warning"], "count": num(args.get("count"), 30, 1, 200, True),
                                                       "filter_text": args.get("filter_text"), "format": "detailed", "include_stacktrace": boolean(args.get("stacktrace"), False)})
    return _steps(ctx, args, [("read_console", a, "console " + act)], "console")


@tool(U, "ms_unity_run_tests", "Run Unity Test Framework tests (EditMode/PlayMode), wait for the job and return pass/fail details.",
      {"mode": {"type": "string", "enum": ["EditMode", "PlayMode"]}, "test_names": {"type": "array", "items": {"type": "string"}}, "wait_seconds": {"type": "integer", "minimum": 5, "maximum": 600}}, [], writes=True)
def run_tests(args, ctx):
    rt = _need(ctx, U, "run_tests")
    gj = _need(ctx, U, "get_test_job")
    a = _clean({"mode": str(args.get("mode") or "EditMode"), "test_names": as_list(args.get("test_names")) or None, "include_failed_tests": True})
    if args.get("dry_run"):
        return {"dryRun": True, "plan": [{"tool": rt, "arguments": a}, {"tool": gj}]}
    start = ctx.call(U, rt, a, 120)
    parsed = _parse(str((start or {}).get("text") or "")) or {}
    job = (parsed.get("data") or parsed).get("job_id") if isinstance(parsed, dict) else None
    if not job:
        return {"ok": False, "error": "run_tests did not return a job_id", "raw": str((start or {}).get("text"))[:1500]}
    wait = num(args.get("wait_seconds"), 120, 5, 600, True)
    deadline = time.time() + wait
    last = None
    while time.time() < deadline:
        r = ctx.call(U, gj, {"job_id": job, "wait_timeout": min(30, wait), "include_failed_tests": True}, 60 + 30)
        last = _parse(str((r or {}).get("text") or "")) or {"text": str((r or {}).get("text"))[:1500]}
        d = last.get("data", last) if isinstance(last, dict) else {}
        if str(d.get("status", "")).lower() in ("complete", "completed", "failed", "succeeded"):
            break
    d = (last or {}).get("data", last) if isinstance(last, dict) else last
    failed = isinstance(d, dict) and (str(d.get("status", "")).lower() == "failed" or (d.get("results") or {}).get("failed"))
    return {"ok": not failed, "job_id": job, "result": d}


@tool(U, "ms_unity_packages", "Package Manager: action=list|search|add|remove|status; `package` is an id (com.unity.cinemachine) or git url.",
      {"action": {"type": "string", "enum": ["list", "search", "add", "remove", "status"]}, "package": {"type": "string"}, "query": {"type": "string"}}, ["action"], writes=True)
def packages(args, ctx):
    act = str(args.get("action") or "list").lower()
    m = {"list": "list_packages", "search": "search_packages", "add": "add_package", "remove": "remove_package", "status": "status"}[act]
    a = _clean({"action": m, "package_name": args.get("package"), "query": args.get("query")})
    return _steps(ctx, args, [("manage_packages", a, "packages " + act)], "packages")


def _dispatch_tool(name, native, desc, actions):
    @tool(U, name, desc, {"action": {"type": "string", "enum": actions}, "params": {"type": "object", "description": "Extra arguments for that action, exactly as the native tool takes them."}}, ["action"], writes=True)
    def _fn(args, ctx):
        act = str(args.get("action") or "").strip().lower()
        if actions and act not in actions:
            raise ToolkitError(f"unknown action '{act}'", "Use one of: " + ", ".join(actions))
        a = {"action": act}
        a.update(as_dict(args.get("params")))
        return _steps(ctx, args, [(native, a, f"{native} {act}")], name)
    return _fn


_dispatch_tool("ms_unity_physics", "manage_physics",
               "Physics setup: rigidbody config, joints, physics materials, forces, collision matrix, raycast/linecast queries. params go to manage_physics.",
               ["add_joint", "apply_force", "assign_physics_material", "configure_joint", "configure_rigidbody", "create_physics_material", "get_collision_matrix", "get_settings", "linecast", "raycast", "set_settings", "set_collision_matrix"])
_dispatch_tool("ms_unity_camera", "manage_camera",
               "Cameras/Cinemachine: create_camera, set_aim, set_blend, list_cameras, screenshot, multiview screenshots. params go to manage_camera.",
               ["add_extension", "create_camera", "ensure_brain", "force_camera", "list_cameras", "ping", "release_override", "screenshot", "screenshot_multiview", "set_aim", "set_blend", "set_follow", "set_lens", "set_priority"])
_dispatch_tool("ms_unity_ui", "manage_ui",
               "UI Toolkit: create/read/update UXML and USS files, create PanelSettings, attach a UIDocument, inspect the visual tree. params go to manage_ui.",
               ["attach_ui_document", "create", "create_panel_settings", "get_visual_tree", "read", "update"])
_dispatch_tool("ms_unity_graphics", "manage_graphics",
               "Graphics: render features, light/reflection probes, lightmap baking, volumes/post-processing. params go to manage_graphics.",
               ["bake_create_light_probe_group", "bake_create_reflection_probe", "bake_start", "bake_status", "feature_add", "feature_list", "feature_reorder", "feature_toggle", "ping", "volume_create", "volume_set_effect", "volume_get_info"])
_dispatch_tool("ms_unity_profiler", "manage_profiler",
               "Profiler: frame timing, counters, object memory, frame-debugger events. params go to manage_profiler.",
               ["frame_debugger_disable", "frame_debugger_enable", "frame_debugger_get_events", "get_counters", "get_frame_timing", "get_object_memory", "memory_compare_snapshots", "memory_take_snapshot", "ping"])


@tool(U, "ms_unity_editor_settings", "Project tags/layers/tools: action=add_tag|remove_tag|add_layer|remove_layer|set_active_tool.",
      {"action": {"type": "string", "enum": ["add_tag", "remove_tag", "add_layer", "remove_layer", "set_active_tool"]}, "name": {"type": "string"}}, ["action", "name"], writes=True)
def editor_settings(args, ctx):
    act = str(args.get("action") or "")
    key = {"add_tag": "tag_name", "remove_tag": "tag_name", "add_layer": "layer_name", "remove_layer": "layer_name", "set_active_tool": "tool_name"}.get(act)
    if not key:
        raise ToolkitError("unknown action", "add_tag, remove_tag, add_layer, remove_layer or set_active_tool")
    return _steps(ctx, args, [("manage_editor", {"action": act, key: str(args.get("name") or "")}, act)], "editor settings")


@tool(U, "ms_unity_menu_item", "Run any Unity menu item by path (e.g. 'GameObject/3D Object/Cube', 'File/Save Project').",
      {"menu_path": {"type": "string"}}, ["menu_path"], writes=True)
def menu_item(args, ctx):
    return _steps(ctx, args, [("execute_menu_item", {"menu_path": str(args.get("menu_path") or "")}, "menu item")], "menu")


@tool(U, "ms_unity_screenshot",
      "Capture the scene as an image returned to you (optionally from a named camera, aimed at a target, or as a surround/orbit contact sheet). Use it to LOOK at the result.",
      {"camera": {"type": "string"}, "view_target": {"type": "string"}, "batch": {"type": "string", "enum": ["surround", "orbit"]},
       "max_resolution": {"type": "integer", "minimum": 64, "maximum": 2048}}, [])
def screenshot(args, ctx):
    a = _clean({"action": "screenshot", "camera": args.get("camera"), "view_target": args.get("view_target"), "batch": args.get("batch"),
                "include_image": True, "max_resolution": num(args.get("max_resolution"), 512, 64, 2048, True)})
    return _steps(ctx, args, [("manage_scene", a, "screenshot")], "screenshot")


@tool(U, "ms_unity_api_lookup", "Look up Unity API docs or reflect over loaded types: source=docs|reflect, with `query` (class/member) - avoids guessing API names.",
      {"source": {"type": "string", "enum": ["docs", "reflect"]}, "query": {"type": "string"}, "type_name": {"type": "string"}}, ["query"])
def api_lookup(args, ctx):
    if str(args.get("source") or "docs") == "reflect":
        a = _clean({"action": "search" if not args.get("type_name") else "get_type", "query": args.get("query"), "type_name": args.get("type_name")})
        return _steps(ctx, args, [("unity_reflect", a, "reflect")], "api lookup")
    return _steps(ctx, args, [("unity_docs", {"action": "lookup", "query": str(args.get("query") or "")}, "docs")], "api lookup")


def _flatten(node, out, path=""):
    if isinstance(node, dict):
        name = node.get("name")
        here = (path + "/" + str(name)) if name is not None else path
        if name is not None:
            sig = {k: node.get(k) for k in ("instanceID", "instance_id", "active", "tag", "layer", "position", "localPosition", "components") if k in node}
            out[here or str(name)] = sig
        for k in ("children", "items", "data", "objects", "hierarchy", "nodes"):
            if k in node:
                _flatten(node[k], out, here)
    elif isinstance(node, list):
        for it in node:
            _flatten(it, out, path)


@tool(U, "ms_unity_changes",
      "See what changed in the scene since a checkpoint - including edits the USER made by hand. action=checkpoint stores the hierarchy; action=diff reports added/removed/changed objects.",
      {"action": {"type": "string", "enum": ["checkpoint", "diff"]}, "label": {"type": "string"}, "include_transform": {"type": "boolean"}}, ["action"])
def changes(args, ctx):
    label = str(args.get("label") or "default")
    t = _need(ctx, U, "manage_scene")
    if args.get("dry_run"):
        return {"dryRun": True, "plan": [{"tool": t, "arguments": {"action": "get_hierarchy"}}]}
    snap, cursor, pages = {}, 0, 0
    while pages < 12:
        raw = ctx.call(U, t, {"action": "get_hierarchy", "page_size": 500, "cursor": cursor, "include_transform": boolean(args.get("include_transform"), True)}, 90)
        parsed = _parse(str((raw or {}).get("text") or ""))
        if parsed is None:
            for i, line in enumerate(str((raw or {}).get("text") or "").splitlines()):
                snap[f"{i}:{line.strip()}"] = {}
            break
        _flatten(parsed, snap)
        d = parsed.get("data", parsed) if isinstance(parsed, dict) else {}
        nxt = d.get("next_cursor") if isinstance(d, dict) else None
        pages += 1
        if nxt is None:
            break
        cursor = nxt
    act = str(args.get("action") or "diff").lower()
    if act == "checkpoint":
        snapshot_store(U, label, snap)
        return {"ok": True, "label": label, "objects": len(snap)}
    prev = snapshot_get(U, label)
    if not prev:
        raise ToolkitError(f"no checkpoint '{label}'", "Call with action=checkpoint first.")
    out = diff_maps(prev["data"], snap)
    out["added"], out["removed"] = out["added"][:200], out["removed"][:200]
    out.update({"ok": True, "label": label, "since_seconds": int(time.time() - prev["at"])})
    return out


# ── file-native (no editor required) ────────────────────────────────────────
@tool(U, "ms_unity_project_info",
      "Read a Unity project straight from disk (works with the editor closed): Unity version, render pipeline, installed packages, input system, scenes, build "
      "scenes, and asset counts by type. Tells you which shader/UI/input choices are correct before you build.",
      {"project_path": {"type": "string", "description": "Absolute path of the folder containing Assets/ and ProjectSettings/."}}, ["project_path"], local=True)
def project_info(args, ctx):
    root = str(args.get("project_path") or "").strip()
    if not root or not os.path.isdir(os.path.join(root, "Assets")):
        raise ToolkitError("project_path must be the folder that contains Assets/", "Use the project root, not Assets/ itself.")
    info = {"project": os.path.basename(os.path.normpath(root))}
    ver = os.path.join(root, "ProjectSettings", "ProjectVersion.txt")
    if os.path.isfile(ver):
        m = re.search(r"m_EditorVersion:\s*(\S+)", open(ver, encoding="utf-8", errors="replace").read())
        info["unity_version"] = m.group(1) if m else None
    pk = {}
    mf = os.path.join(root, "Packages", "manifest.json")
    if os.path.isfile(mf):
        try:
            pk = json.load(open(mf, encoding="utf-8")).get("dependencies", {})
        except Exception:
            pass
    info["packages"] = {k: v for k, v in sorted(pk.items()) if not k.startswith("com.unity.modules.")}
    info["render_pipeline"] = ("HDRP" if "com.unity.render-pipelines.high-definition" in pk else "URP" if "com.unity.render-pipelines.universal" in pk else "Built-in")
    info["shader_hint"] = {"HDRP": "HDRP/Lit", "URP": "Universal Render Pipeline/Lit"}.get(info["render_pipeline"], "Standard")
    info["input_system"] = "com.unity.inputsystem" in pk
    info["ugui"] = "com.unity.ugui" in pk
    info["textmeshpro"] = "com.unity.textmeshpro" in pk or "com.unity.ugui" in pk
    info["cinemachine"] = "com.unity.cinemachine" in pk
    counts, scenes = {}, []
    for dp, dn, fn in os.walk(os.path.join(root, "Assets")):
        for f in fn:
            ext = os.path.splitext(f)[1].lower()
            if ext == ".meta":
                continue
            counts[ext or "(none)"] = counts.get(ext or "(none)", 0) + 1
            if ext == ".unity" and len(scenes) < 100:
                scenes.append(os.path.relpath(os.path.join(dp, f), root).replace("\\", "/"))
    info["asset_counts"] = dict(sorted(counts.items(), key=lambda kv: -kv[1])[:20])
    info["scenes"] = scenes
    bs = os.path.join(root, "ProjectSettings", "EditorBuildSettings.asset")
    if os.path.isfile(bs):
        info["build_scenes"] = re.findall(r"path:\s*(Assets/[^\r\n]+\.unity)", open(bs, encoding="utf-8", errors="replace").read())
    ctx.remember_project(U, root)
    return info
