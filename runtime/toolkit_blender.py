# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender tools for engine_toolkit. Every tool compiles to one Python program that
runs through blender-mcp's `execute_blender_code` and prints a single JSON line."""
from engine_toolkit import (tool, run_code, as_list, as_dict, vec3, color4, num, boolean, ToolkitError,
                            snapshot_store, snapshot_get, diff_maps)

B = "blender"
OBJ = {"type": "string", "description": "Exact object name (see ms_blender_list_objects)."}
VEC = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
NAMES = {"type": "array", "items": {"type": "string"}, "description": "Object names."}


def _exec(ctx, args, body, label, timeout=None):
    res, call = run_code(ctx, B, body, args, timeout or int(num(args.get("timeout_seconds"), 120, 5, 600)), label)
    if res.get("dryRun"):
        return {"dryRun": True, "nativeCall": {"tool": call["tool"]}, "code": res["code"]}
    ok = res.pop("ok", True) if isinstance(res, dict) else True
    out = {"ok": ok, "nativeCall": call["tool"]}
    out.update(res if isinstance(res, dict) else {"result": res})
    return out


def _names(args, *keys):
    out = []
    for k in keys or ("names", "name", "object", "objects"):
        out += [str(x) for x in as_list(args.get(k)) if str(x).strip()]
    return list(dict.fromkeys(out))


@tool(B, "ms_blender_scene_summary",
      "Summarise the open Blender scene in one call: object counts by type, collections, selection/active object, camera, "
      "frame range, fps, render engine/resolution, units, Blender version and whether the file has unsaved changes. Use it first.", {})
def scene_summary(args, ctx):
    return _exec(ctx, args, '''
        sc = bpy.context.scene
        counts = {}
        for o in sc.objects: counts[o.type] = counts.get(o.type, 0) + 1
        R["scene"] = sc.name
        R["blender"] = bpy.app.version_string
        R["file"] = bpy.data.filepath or None
        R["unsaved_changes"] = bool(bpy.data.is_dirty)
        R["object_counts"] = counts
        R["collections"] = [{"name": c.name, "objects": len(c.objects)} for c in bpy.data.collections]
        R["selected"] = [o.name for o in bpy.context.selected_objects]
        R["active"] = bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None
        R["camera"] = sc.camera.name if sc.camera else None
        R["frames"] = {"start": sc.frame_start, "end": sc.frame_end, "current": sc.frame_current, "fps": sc.render.fps}
        R["render"] = {"engine": sc.render.engine, "resolution": [sc.render.resolution_x, sc.render.resolution_y], "percent": sc.render.resolution_percentage}
        R["units"] = {"system": sc.unit_settings.system, "scale": sc.unit_settings.scale_length}
        R["datablocks"] = {"meshes": len(bpy.data.meshes), "materials": len(bpy.data.materials), "images": len(bpy.data.images), "actions": len(bpy.data.actions)}
    ''', "scene summary")


@tool(B, "ms_blender_list_objects",
      "List objects with transform, parent, vertex/face counts, materials, modifiers and collections. Filter by type, name text, "
      "collection or selection. Read-only.",
      {"type": {"type": "string", "description": "MESH, LIGHT, CAMERA, EMPTY, ARMATURE, CURVE, FONT, ... (case-insensitive)."},
       "name_contains": {"type": "string"}, "collection": {"type": "string"},
       "selected_only": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "description": "Default 100."}})
def list_objects(args, ctx):
    args = dict(args, limit=num(args.get("limit"), 100, 1, 1000, True), type=str(args.get("type") or "").upper())
    return _exec(ctx, args, '''
        objs = list(bpy.context.selected_objects if A.get("selected_only") else bpy.context.scene.objects)
        t = A.get("type"); s = (A.get("name_contains") or "").lower(); c = A.get("collection")
        rows = []
        for o in objs:
            if t and o.type != t: continue
            if s and s not in o.name.lower(): continue
            if c and c not in [x.name for x in o.users_collection]: continue
            rows.append(_info(o))
        R["total"] = len(rows)
        R["objects"] = rows[:A["limit"]]
        if len(rows) > A["limit"]: R["truncated"] = True
    ''', "list objects")


_PRIMS = {
    "cube": ("primitive_cube_add", ["size"]),
    "plane": ("primitive_plane_add", ["size"]),
    "circle": ("primitive_circle_add", ["radius", "vertices"]),
    "uv_sphere": ("primitive_uv_sphere_add", ["radius", "segments", "ring_count"]),
    "sphere": ("primitive_uv_sphere_add", ["radius", "segments", "ring_count"]),
    "ico_sphere": ("primitive_ico_sphere_add", ["radius", "subdivisions"]),
    "cylinder": ("primitive_cylinder_add", ["radius", "depth", "vertices"]),
    "cone": ("primitive_cone_add", ["radius1", "radius2", "depth", "vertices"]),
    "torus": ("primitive_torus_add", ["major_radius", "minor_radius", "major_segments", "minor_segments"]),
    "grid": ("primitive_grid_add", ["x_subdivisions", "y_subdivisions", "size"]),
    "monkey": ("primitive_monkey_add", ["size"]),
    "empty": (None, []),
}


@tool(B, "ms_blender_create_primitive",
      "Create a primitive (cube, plane, circle, uv_sphere, ico_sphere, cylinder, cone, torus, grid, monkey, empty) with a name, "
      "location, rotation (degrees), scale, optional smooth shading and target collection. Returns the created object's info.",
      {"shape": {"type": "string", "enum": sorted(_PRIMS), "description": "Primitive kind."},
       "name": {"type": "string"}, "location": VEC, "rotation_deg": VEC, "scale": VEC,
       "size": {"type": "number", "description": "Cube/plane/grid/monkey size."}, "radius": {"type": "number"}, "depth": {"type": "number", "description": "Cylinder/cone height."},
       "segments": {"type": "integer"}, "rings": {"type": "integer"}, "subdivisions": {"type": "integer"},
       "collection": {"type": "string", "description": "Collection to place it in (created if missing)."},
       "smooth": {"type": "boolean"}}, ["shape"], writes=True)
def create_primitive(args, ctx):
    shape = str(args.get("shape") or args.get("type") or args.get("kind") or "cube").lower().replace(" ", "_")  # `type`/`kind` accepted as aliases
    if shape not in _PRIMS:
        raise ToolkitError(f"unknown shape '{shape}'", "Use one of: " + ", ".join(sorted(_PRIMS)))
    op, _ = _PRIMS[shape]
    kw = {}
    size, radius, depth = num(args.get("size")), num(args.get("radius")), num(args.get("depth"))
    if shape in ("cube", "plane", "grid", "monkey") and size is not None:
        kw["size"] = size
    if shape in ("circle", "uv_sphere", "sphere", "ico_sphere", "cylinder") and radius is not None:
        kw["radius"] = radius
    if shape == "cone" and radius is not None:
        kw["radius1"] = radius
    if shape in ("cylinder", "cone") and depth is not None:
        kw["depth"] = depth
    if args.get("segments") is not None:
        kw["vertices" if shape in ("circle", "cylinder", "cone") else "segments"] = num(args.get("segments"), 32, 3, 512, True)
        if shape in ("uv_sphere", "sphere"):
            pass
    if args.get("rings") is not None and shape in ("uv_sphere", "sphere"):
        kw["ring_count"] = num(args.get("rings"), 16, 2, 256, True)
    if args.get("subdivisions") is not None and shape == "ico_sphere":
        kw["subdivisions"] = num(args.get("subdivisions"), 2, 1, 7, True)
    a = dict(args, shape=shape, _op=op, _kw=kw)
    return _exec(ctx, a, '''
        _mode_object()
        loc = _v(A.get("location")); rot = _rad(_v(A.get("rotation_deg")))
        if A["shape"] == "empty":
            bpy.ops.object.empty_add(type="PLAIN_AXES", location=loc, rotation=rot)
        else:
            getattr(bpy.ops.mesh, A["_op"])(location=loc, rotation=rot, **A["_kw"])
        o = bpy.context.active_object
        if A.get("name"): o.name = A["name"]
        if A.get("scale"): o.scale = _v(A["scale"], (1, 1, 1))
        if A.get("smooth") and o.type == "MESH":
            for p in o.data.polygons: p.use_smooth = True
        cn = A.get("collection")
        if cn:
            col = bpy.data.collections.get(cn)
            if col is None:
                col = bpy.data.collections.new(cn); bpy.context.scene.collection.children.link(col)
            for c in list(o.users_collection): c.objects.unlink(o)
            col.objects.link(o)
        R["created"] = _info(o)
    ''', f"create {shape}")


@tool(B, "ms_blender_transform_objects",
      "Move/rotate/scale one or more objects. Values are absolute unless relative=true. Rotation is in degrees. Can also set the parent.",
      {"names": NAMES, "name": OBJ, "location": VEC, "rotation_deg": VEC, "scale": VEC, "relative": {"type": "boolean"},
       "parent": {"type": "string", "description": "Parent object name, or empty string to clear."}}, [], writes=True)
def transform_objects(args, ctx):
    names = _names(args, "names", "name")
    if not names:
        raise ToolkitError("give `names` (or `name`)")
    return _exec(ctx, dict(args, names=names), '''
        res = []
        for n in A["names"]:
            o = _obj(n)
            rel = bool(A.get("relative"))
            if A.get("location"):
                v = _v(A["location"])
                o.location = tuple(o.location[i] + v[i] for i in range(3)) if rel else v
            if A.get("rotation_deg"):
                r = _rad(_v(A["rotation_deg"]))
                o.rotation_euler = tuple(o.rotation_euler[i] + r[i] for i in range(3)) if rel else r
            if A.get("scale"):
                s = _v(A["scale"], (1, 1, 1))
                o.scale = tuple(o.scale[i] * s[i] for i in range(3)) if rel else s
            if "parent" in A and A["parent"] is not None:
                if A["parent"] == "": 
                    m = o.matrix_world.copy(); o.parent = None; o.matrix_world = m
                else:
                    p = _obj(A["parent"]); m = o.matrix_world.copy(); o.parent = p; o.matrix_parent_inverse = p.matrix_world.inverted()
            res.append(_info(o))
        R["objects"] = res
    ''', "transform")


@tool(B, "ms_blender_delete_objects",
      "Delete objects by exact names or by a name substring. Refuses to delete everything unless confirm_all=true. Optionally purges orphaned data.",
      {"names": NAMES, "name_contains": {"type": "string"}, "purge_orphans": {"type": "boolean"}, "confirm_all": {"type": "boolean"}}, [], writes=True)
def delete_objects(args, ctx):
    if not _names(args, "names", "name") and not args.get("name_contains"):
        raise ToolkitError("give `names` or `name_contains`")
    return _exec(ctx, dict(args, names=_names(args, "names", "name")), '''
        _mode_object()
        targets = [bpy.data.objects[n] for n in A["names"] if n in bpy.data.objects]
        s = (A.get("name_contains") or "").lower()
        if s: targets += [o for o in bpy.data.objects if s in o.name.lower() and o not in targets]
        if len(targets) >= len(bpy.data.objects) and len(targets) > 1 and not A.get("confirm_all"):
            raise ValueError("that would delete every object in the file; pass confirm_all=true if you really mean it")
        missing = [n for n in A["names"] if n not in bpy.data.objects]
        names = [o.name for o in targets]
        for o in targets: bpy.data.objects.remove(o, do_unlink=True)
        if A.get("purge_orphans"):
            try: bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
            except Exception: pass
        R["deleted"] = names; R["missing"] = missing
    ''', "delete objects")


@tool(B, "ms_blender_duplicate_object",
      "Duplicate an object `count` times, each offset by `offset` from the previous (linked data optional).",
      {"name": OBJ, "count": {"type": "integer", "minimum": 1, "maximum": 200}, "offset": VEC, "linked": {"type": "boolean"}, "new_name": {"type": "string"}}, ["name"], writes=True)
def duplicate_object(args, ctx):
    return _exec(ctx, dict(args, count=num(args.get("count"), 1, 1, 200, True)), '''
        src = _obj(A["name"]); off = _v(A.get("offset"), (1, 0, 0)); out = []
        last = src
        for i in range(A["count"]):
            d = src.copy()
            if not A.get("linked") and src.data is not None: d.data = src.data.copy()
            for c in src.users_collection: c.objects.link(d)
            d.location = tuple(last.location[k] + off[k] for k in range(3))
            if A.get("new_name"): d.name = A["new_name"] if A["count"] == 1 else "%s.%03d" % (A["new_name"], i + 1)
            out.append(_info(d)); last = d
        R["created"] = out
    ''', "duplicate")


@tool(B, "ms_blender_manage_collection",
      "Create, list, delete or fill collections: action=create|list|delete|move_objects|link_objects|set_visibility.",
      {"action": {"type": "string", "enum": ["create", "list", "delete", "move_objects", "link_objects", "set_visibility"]},
       "name": {"type": "string"}, "parent": {"type": "string"}, "objects": NAMES,
       "hide_viewport": {"type": "boolean"}, "hide_render": {"type": "boolean"}}, ["action"], writes=True)
def manage_collection(args, ctx):
    args = dict(args, action=str(args.get("action") or "list").lower(), objects=_names(args, "objects"))
    return _exec(ctx, args, '''
        act = A["action"]
        def col(n, create=False):
            c = bpy.data.collections.get(n)
            if c is None and create:
                c = bpy.data.collections.new(n)
                par = bpy.data.collections.get(A["parent"]) if A.get("parent") else bpy.context.scene.collection
                (par or bpy.context.scene.collection).children.link(c)
            if c is None: raise ValueError("no collection named %r" % n)
            return c
        if act == "list":
            R["collections"] = [{"name": c.name, "objects": [o.name for o in c.objects], "children": [x.name for x in c.children], "hide_viewport": c.hide_viewport} for c in bpy.data.collections]
        elif act == "create":
            c = col(A["name"], True); R["created"] = c.name
        elif act == "delete":
            c = col(A["name"]); bpy.data.collections.remove(c); R["deleted"] = A["name"]
        elif act in ("move_objects", "link_objects"):
            c = col(A["name"], True)
            for n in A["objects"]:
                o = _obj(n)
                if act == "move_objects":
                    for x in list(o.users_collection): x.objects.unlink(o)
                if o.name not in c.objects: c.objects.link(o)
            R["collection"] = c.name; R["objects"] = A["objects"]
        elif act == "set_visibility":
            c = col(A["name"])
            if A.get("hide_viewport") is not None: c.hide_viewport = bool(A["hide_viewport"])
            if A.get("hide_render") is not None: c.hide_render = bool(A["hide_render"])
            R["collection"] = c.name
        else:
            raise ValueError("unknown action %r" % act)
    ''', "collection " + args["action"])


@tool(B, "ms_blender_create_material",
      "Create (or update) a Principled BSDF material: base colour (hex/name/[r,g,b]), metallic, roughness, emission, alpha, and an optional "
      "base-colour image texture. Optionally assigns it to objects.",
      {"name": {"type": "string"}, "base_color": {"type": "string", "description": "Hex like #ff8800, a colour name, or [r,g,b(,a)] as a JSON array string."},
       "metallic": {"type": "number", "minimum": 0, "maximum": 1}, "roughness": {"type": "number", "minimum": 0, "maximum": 1},
       "emission_color": {"type": "string"}, "emission_strength": {"type": "number", "minimum": 0},
       "alpha": {"type": "number", "minimum": 0, "maximum": 1}, "texture_path": {"type": "string", "description": "Absolute image path for the base colour."},
       "assign_to": NAMES}, ["name"], writes=True)
def create_material(args, ctx):
    a = dict(args)
    for k in ("base_color", "emission_color"):
        if args.get(k) is not None:
            c = color4(args.get(k))
            if c is None:
                raise ToolkitError(f"could not read colour for {k}: {args.get(k)!r}", "Use a hex string like #ff8800.")
            a[k] = c
    a["assign_to"] = _names(args, "assign_to")
    return _exec(ctx, a, '''
        m = bpy.data.materials.get(A["name"]) or bpy.data.materials.new(A["name"])
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf is None: raise ValueError("material has no Principled BSDF node")
        def setin(key, val):
            if key in bsdf.inputs: bsdf.inputs[key].default_value = val
        if A.get("base_color"): setin("Base Color", A["base_color"])
        if A.get("metallic") is not None: setin("Metallic", float(A["metallic"]))
        if A.get("roughness") is not None: setin("Roughness", float(A["roughness"]))
        if A.get("alpha") is not None:
            setin("Alpha", float(A["alpha"]))
            if float(A["alpha"]) < 1:
                try: m.blend_method = "BLEND"
                except Exception: pass
        if A.get("emission_color"):
            setin("Emission Color", A["emission_color"]); setin("Emission", A["emission_color"])
        if A.get("emission_strength") is not None: setin("Emission Strength", float(A["emission_strength"]))
        if A.get("texture_path"):
            img = bpy.data.images.load(A["texture_path"], check_existing=True)
            tex = m.node_tree.nodes.new("ShaderNodeTexImage"); tex.image = img
            m.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        for n in A["assign_to"]:
            o = _obj(n)
            if o.data is None or not hasattr(o.data, "materials"): raise ValueError("%s cannot hold materials" % n)
            if len(o.data.materials) == 0: o.data.materials.append(m)
            else: o.data.materials[0] = m
        R["material"] = m.name; R["assigned"] = A["assign_to"]
    ''', "material " + str(args.get("name")))


@tool(B, "ms_blender_assign_material",
      "Assign an existing material to objects (slot 0 by default, or a given slot index; adds slots as needed).",
      {"objects": NAMES, "material": {"type": "string"}, "slot": {"type": "integer", "minimum": 0}}, ["objects", "material"], writes=True)
def assign_material(args, ctx):
    return _exec(ctx, dict(args, objects=_names(args, "objects"), slot=num(args.get("slot"), 0, 0, 64, True)), '''
        m = bpy.data.materials.get(A["material"])
        if m is None: raise ValueError("no material %r (have: %s)" % (A["material"], ", ".join(list(bpy.data.materials.keys())[:30])))
        for n in A["objects"]:
            o = _obj(n)
            while len(o.data.materials) <= A["slot"]: o.data.materials.append(None)
            o.data.materials[A["slot"]] = m
        R["assigned"] = A["objects"]
    ''', "assign material")


_MODS = ["SUBSURF", "BEVEL", "MIRROR", "ARRAY", "SOLIDIFY", "BOOLEAN", "DECIMATE", "WEIGHTED_NORMAL", "EDGE_SPLIT", "TRIANGULATE",
         "SMOOTH", "DISPLACE", "SIMPLE_DEFORM", "SHRINKWRAP", "REMESH", "WIREFRAME", "SCREW", "SKIN", "CURVE", "LATTICE"]


@tool(B, "ms_blender_add_modifier",
      "Add a modifier to an object and set its fields from `settings` (any RNA property, e.g. SUBSURF {levels:2}, BEVEL {width:0.02,segments:3}, "
      "MIRROR {use_axis:[true,false,false]}, ARRAY {count:5,relative_offset_displace:[1.1,0,0]}). Optionally apply it immediately.",
      {"object": OBJ, "type": {"type": "string", "enum": _MODS}, "name": {"type": "string"},
       "settings": {"type": "object", "description": "Modifier property -> value."}, "apply": {"type": "boolean"}}, ["object", "type"], writes=True)
def add_modifier(args, ctx):
    t = str(args.get("type") or "").upper().replace(" ", "_")
    if t not in _MODS:
        raise ToolkitError(f"unsupported modifier type '{t}'", "Use one of: " + ", ".join(_MODS))
    return _exec(ctx, dict(args, type=t, settings=as_dict(args.get("settings"))), '''
        o = _obj(A["object"])
        m = o.modifiers.new(A.get("name") or A["type"].title(), A["type"])
        applied, skipped = [], {}
        for k, v in (A.get("settings") or {}).items():
            try:
                if k == "object" and isinstance(v, str): v = _obj(v)
                cur = getattr(m, k)
                if isinstance(v, list) and hasattr(cur, "__len__"):
                    for i, x in enumerate(v): cur[i] = x
                else: setattr(m, k, v)
                applied.append(k)
            except Exception as e:
                skipped[k] = str(e)[:120]
        if A.get("apply"):
            _select([o], o); bpy.ops.object.modifier_apply(modifier=m.name)
        R["object"] = o.name; R["modifier"] = m.name; R["applied_settings"] = applied; R["skipped_settings"] = skipped
        R["stack"] = [x.type for x in o.modifiers]
    ''', "modifier " + t)


@tool(B, "ms_blender_modifier_stack",
      "List, remove, apply or reorder an object's modifiers: action=list|remove|apply|move_up|move_down|clear.",
      {"object": OBJ, "action": {"type": "string", "enum": ["list", "remove", "apply", "move_up", "move_down", "clear"]}, "modifier": {"type": "string"}},
      ["object", "action"], writes=True)
def modifier_stack(args, ctx):
    return _exec(ctx, dict(args, action=str(args.get("action") or "list").lower()), '''
        o = _obj(A["object"]); act = A["action"]
        def mod():
            m = o.modifiers.get(A.get("modifier") or "")
            if m is None: raise ValueError("no modifier %r on %s (have: %s)" % (A.get("modifier"), o.name, ", ".join(x.name for x in o.modifiers)))
            return m
        if act == "remove": o.modifiers.remove(mod())
        elif act == "clear": o.modifiers.clear()
        elif act == "apply": _select([o], o); bpy.ops.object.modifier_apply(modifier=mod().name)
        elif act in ("move_up", "move_down"):
            _select([o], o)
            (bpy.ops.object.modifier_move_up if act == "move_up" else bpy.ops.object.modifier_move_down)(modifier=mod().name)
        R["modifiers"] = [{"name": x.name, "type": x.type, "show_viewport": x.show_viewport} for x in o.modifiers]
    ''', "modifier stack")


@tool(B, "ms_blender_boolean",
      "Boolean-combine two meshes: operation=UNION|DIFFERENCE|INTERSECT with `operand` applied to `object`. Applies by default and hides/removes the operand as asked.",
      {"object": OBJ, "operand": OBJ, "operation": {"type": "string", "enum": ["UNION", "DIFFERENCE", "INTERSECT"]},
       "apply": {"type": "boolean"}, "operand_after": {"type": "string", "enum": ["keep", "hide", "delete"]}}, ["object", "operand"], writes=True)
def boolean_op(args, ctx):
    return _exec(ctx, dict(args, operation=str(args.get("operation") or "DIFFERENCE").upper(), apply=boolean(args.get("apply"), True),
                           operand_after=str(args.get("operand_after") or "hide")), '''
        o = _obj(A["object"]); b = _obj(A["operand"])
        m = o.modifiers.new("MS_Boolean", "BOOLEAN"); m.operation = A["operation"]; m.object = b
        try: m.solver = "EXACT"
        except Exception: pass
        if A["apply"]:
            _select([o], o); bpy.ops.object.modifier_apply(modifier=m.name)
            if A["operand_after"] == "hide": b.hide_set(True); b.hide_render = True
            elif A["operand_after"] == "delete": bpy.data.objects.remove(b, do_unlink=True)
        R["result"] = _info(o)
    ''', "boolean")


_MESH_OPS = ["shade_smooth", "shade_flat", "recalc_normals", "flip_normals", "remove_doubles", "triangulate", "center_origin",
             "apply_transforms", "delete_loose", "fill_holes", "dissolve_degenerate", "set_origin_to_bottom"]


@tool(B, "ms_blender_mesh_edit",
      "Run mesh clean-up operations on objects: " + ", ".join(_MESH_OPS) + ". `operations` runs in order; unknown names are rejected before anything runs.",
      {"objects": NAMES, "operations": {"type": "array", "items": {"type": "string", "enum": _MESH_OPS}},
       "merge_distance": {"type": "number", "description": "For remove_doubles (default 0.0001)."}}, ["objects", "operations"], writes=True)
def mesh_edit(args, ctx):
    ops = [str(o).lower() for o in as_list(args.get("operations"))]
    bad = [o for o in ops if o not in _MESH_OPS]
    if bad or not ops:
        raise ToolkitError("unknown/empty operations: " + ", ".join(bad or ["(none)"]), "Use: " + ", ".join(_MESH_OPS))
    a = dict(args, operations=ops, objects=_names(args, "objects"), merge_distance=num(args.get("merge_distance"), 0.0001, 0, 10))
    return _exec(ctx, a, '''
        import bmesh
        _mode_object()
        report = {}
        for n in A["objects"]:
            o = _obj(n)
            if o.type != "MESH": raise ValueError("%s is %s, not MESH" % (n, o.type))
            _select([o], o); done = []
            for op in A["operations"]:
                if op == "shade_smooth":
                    for p in o.data.polygons: p.use_smooth = True
                elif op == "shade_flat":
                    for p in o.data.polygons: p.use_smooth = False
                elif op == "apply_transforms":
                    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
                elif op == "center_origin":
                    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
                elif op == "set_origin_to_bottom":
                    mw = o.matrix_world; zs = [(mw @ v.co).z for v in o.data.vertices]
                    cur = bpy.context.scene.cursor.location.copy()
                    bpy.context.scene.cursor.location = (o.location.x, o.location.y, min(zs))
                    bpy.ops.object.origin_set(type="ORIGIN_CURSOR"); bpy.context.scene.cursor.location = cur
                else:
                    bm = bmesh.new(); bm.from_mesh(o.data)
                    if op == "recalc_normals": bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                    elif op == "flip_normals":
                        for f in bm.faces: f.normal_flip()
                    elif op == "remove_doubles": bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=A["merge_distance"])
                    elif op == "triangulate": bmesh.ops.triangulate(bm, faces=bm.faces[:])
                    elif op == "delete_loose":
                        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_edges], context="VERTS")
                    elif op == "fill_holes": bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary])
                    elif op == "dissolve_degenerate": bmesh.ops.dissolve_degenerate(bm, dist=A["merge_distance"], edges=bm.edges)
                    bm.to_mesh(o.data); bm.free(); o.data.update()
                done.append(op)
            report[n] = {"done": done, "vertices": len(o.data.vertices), "faces": len(o.data.polygons)}
        R["report"] = report
    ''', "mesh edit")


@tool(B, "ms_blender_mesh_stats",
      "Game-readiness audit of meshes: vertices/faces/triangles, n-gons, non-manifold edges, loose vertices, UV layers, dimensions, "
      "unapplied scale, material slots - with warnings against an optional triangle budget. Read-only.",
      {"objects": NAMES, "triangle_budget": {"type": "integer", "minimum": 1, "description": "Warn when an object exceeds this triangle count."}})
def mesh_stats(args, ctx):
    return _exec(ctx, dict(args, objects=_names(args, "objects"), triangle_budget=num(args.get("triangle_budget"), 0, 0, 10 ** 9, True)), '''
        import bmesh
        objs = [_obj(n) for n in A["objects"]] if A["objects"] else [o for o in bpy.context.scene.objects if o.type == "MESH"]
        rows, warn, total_tris = [], [], 0
        for o in objs:
            if o.type != "MESH": continue
            bm = bmesh.new(); bm.from_mesh(o.data)
            tris = sum(len(f.verts) - 2 for f in bm.faces)
            row = {"name": o.name, "vertices": len(bm.verts), "faces": len(bm.faces), "triangles": tris,
                   "ngons": sum(1 for f in bm.faces if len(f.verts) > 4),
                   "non_manifold_edges": sum(1 for e in bm.edges if not e.is_manifold),
                   "loose_vertices": sum(1 for v in bm.verts if not v.link_edges),
                   "uv_layers": len(o.data.uv_layers), "dimensions": [round(d, 4) for d in o.dimensions],
                   "scale": [round(s, 4) for s in o.scale], "material_slots": len(o.material_slots)}
            bm.free(); total_tris += tris; rows.append(row)
            if row["non_manifold_edges"]: warn.append("%s: %d non-manifold edges" % (o.name, row["non_manifold_edges"]))
            if row["loose_vertices"]: warn.append("%s: %d loose vertices" % (o.name, row["loose_vertices"]))
            if not row["uv_layers"]: warn.append("%s: no UV map" % o.name)
            if any(abs(s - 1) > 1e-4 for s in o.scale): warn.append("%s: unapplied scale %s" % (o.name, row["scale"]))
            if A["triangle_budget"] and tris > A["triangle_budget"]: warn.append("%s: %d triangles exceeds budget %d" % (o.name, tris, A["triangle_budget"]))
        R["meshes"] = rows; R["total_triangles"] = total_tris; R["warnings"] = warn
        R["verdict"] = "clean" if not warn else "%d issue(s)" % len(warn)
    ''', "mesh stats")


@tool(B, "ms_blender_uv_unwrap",
      "UV-unwrap mesh objects: method=smart|cube|sphere|cylinder|lightmap (smart by default).",
      {"objects": NAMES, "method": {"type": "string", "enum": ["smart", "cube", "sphere", "cylinder", "lightmap"]},
       "angle_limit_deg": {"type": "number"}, "island_margin": {"type": "number"}}, ["objects"], writes=True)
def uv_unwrap(args, ctx):
    return _exec(ctx, dict(args, objects=_names(args, "objects"), method=str(args.get("method") or "smart").lower(),
                           angle=num(args.get("angle_limit_deg"), 66, 1, 89), margin=num(args.get("island_margin"), 0.02, 0, 1)), '''
        import math
        _mode_object(); out = {}
        for n in A["objects"]:
            o = _obj(n)
            if o.type != "MESH": raise ValueError("%s is not a mesh" % n)
            _select([o], o); bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
            m = A["method"]
            if m == "smart": bpy.ops.uv.smart_project(angle_limit=math.radians(A["angle"]), island_margin=A["margin"])
            elif m == "cube": bpy.ops.uv.cube_project()
            elif m == "sphere": bpy.ops.uv.sphere_project()
            elif m == "cylinder": bpy.ops.uv.cylinder_project()
            elif m == "lightmap": bpy.ops.uv.lightmap_pack()
            bpy.ops.object.mode_set(mode="OBJECT"); out[n] = len(o.data.uv_layers)
        R["uv_layers"] = out
    ''', "uv unwrap")


@tool(B, "ms_blender_lod_generate",
      "Generate LOD copies of a mesh with Decimate: ratios default [1.0, 0.5, 0.25, 0.1] named <Name>_LOD0.._LODn. Returns triangle counts per level.",
      {"object": OBJ, "ratios": {"type": "array", "items": {"type": "number", "minimum": 0.01, "maximum": 1}}, "collection": {"type": "string"}}, ["object"], writes=True)
def lod_generate(args, ctx):
    ratios = [num(r, None, 0.01, 1.0) for r in as_list(args.get("ratios"))] or [1.0, 0.5, 0.25, 0.1]
    ratios = [r for r in ratios if r is not None][:8]
    return _exec(ctx, dict(args, ratios=ratios), '''
        _mode_object(); src = _obj(A["object"])
        if src.type != "MESH": raise ValueError("%s is not a mesh" % src.name)
        out = []
        for i, r in enumerate(A["ratios"]):
            d = src.copy(); d.data = src.data.copy(); d.name = "%s_LOD%d" % (src.name, i)
            for c in src.users_collection: c.objects.link(d)
            if r < 0.999:
                m = d.modifiers.new("LOD", "DECIMATE"); m.ratio = r
                _select([d], d); bpy.ops.object.modifier_apply(modifier=m.name)
            out.append({"name": d.name, "ratio": r, "triangles": sum(len(p.vertices) - 2 for p in d.data.polygons)})
        R["lods"] = out
    ''', "lods")


@tool(B, "ms_blender_add_light",
      "Add a light: type=POINT|SUN|SPOT|AREA with energy, colour, location, rotation (degrees), spot size or area size.",
      {"type": {"type": "string", "enum": ["POINT", "SUN", "SPOT", "AREA"]}, "name": {"type": "string"}, "energy": {"type": "number", "minimum": 0},
       "color": {"type": "string"}, "location": VEC, "rotation_deg": VEC, "spot_size_deg": {"type": "number"}, "size": {"type": "number"}}, ["type"], writes=True)
def add_light(args, ctx):
    a = dict(args, type=str(args.get("type") or "POINT").upper())
    if a["type"] not in ("POINT", "SUN", "SPOT", "AREA"):
        raise ToolkitError("type must be POINT, SUN, SPOT or AREA")
    if args.get("color") is not None:
        a["color"] = color4(args.get("color"), [1, 1, 1, 1])
    return _exec(ctx, a, '''
        _mode_object()
        d = bpy.data.lights.new(A.get("name") or A["type"].title(), A["type"])
        if A.get("energy") is not None: d.energy = float(A["energy"])
        if A.get("color"): d.color = A["color"][:3]
        if A["type"] == "SPOT" and A.get("spot_size_deg"): d.spot_size = math.radians(float(A["spot_size_deg"]))
        if A["type"] == "AREA" and A.get("size"): d.size = float(A["size"])
        o = bpy.data.objects.new(d.name, d); bpy.context.scene.collection.objects.link(o)
        o.location = _v(A.get("location"), (0, 0, 5)); o.rotation_euler = _rad(_v(A.get("rotation_deg")))
        R["light"] = _info(o)
    ''', "light")


@tool(B, "ms_blender_camera",
      "Create or aim a camera: action=create|set_active|look_at|set_lens. look_at takes a `target` object name or `target_point` [x,y,z].",
      {"action": {"type": "string", "enum": ["create", "set_active", "look_at", "set_lens"]}, "name": {"type": "string"}, "location": VEC,
       "target": {"type": "string"}, "target_point": VEC, "focal_length_mm": {"type": "number"}, "sensor_mm": {"type": "number"},
       "clip_start": {"type": "number"}, "clip_end": {"type": "number"}, "make_active": {"type": "boolean"}}, ["action"], writes=True)
def camera(args, ctx):
    return _exec(ctx, dict(args, action=str(args.get("action") or "create").lower()), '''
        import mathutils
        _mode_object(); act = A["action"]
        if act == "create":
            d = bpy.data.cameras.new(A.get("name") or "Camera"); o = bpy.data.objects.new(d.name, d)
            bpy.context.scene.collection.objects.link(o); o.location = _v(A.get("location"), (7, -7, 5))
        else:
            o = bpy.data.objects.get(A.get("name") or "") or bpy.context.scene.camera
            if o is None or o.type != "CAMERA": raise ValueError("no camera found; pass `name`")
            if A.get("location"): o.location = _v(A["location"])
        if A.get("focal_length_mm"): o.data.lens = float(A["focal_length_mm"])
        if A.get("sensor_mm"): o.data.sensor_width = float(A["sensor_mm"])
        if A.get("clip_start"): o.data.clip_start = float(A["clip_start"])
        if A.get("clip_end"): o.data.clip_end = float(A["clip_end"])
        tgt = None
        if A.get("target"): tgt = _obj(A["target"]).matrix_world.translation.copy()
        elif A.get("target_point"): tgt = mathutils.Vector(A["target_point"])
        if tgt is not None or act == "look_at":
            if tgt is None: tgt = mathutils.Vector((0, 0, 0))
            direction = tgt - o.matrix_world.translation
            o.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        if act in ("create", "set_active") and (act == "set_active" or A.get("make_active", True)):
            bpy.context.scene.camera = o
        R["camera"] = _info(o); R["active"] = bpy.context.scene.camera.name if bpy.context.scene.camera else None
    ''', "camera " + str(args.get("action")))


@tool(B, "ms_blender_render_settings",
      "Read or change render settings: engine (BLENDER_EEVEE_NEXT/BLENDER_EEVEE/CYCLES/BLENDER_WORKBENCH), resolution, percentage, samples, "
      "film transparency, fps, frame range, output file format/path. Omit everything to just read the current values.",
      {"engine": {"type": "string"}, "resolution": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
       "percentage": {"type": "integer", "minimum": 1, "maximum": 1000}, "samples": {"type": "integer", "minimum": 1},
       "film_transparent": {"type": "boolean"}, "fps": {"type": "integer", "minimum": 1}, "frame_start": {"type": "integer"}, "frame_end": {"type": "integer"},
       "file_format": {"type": "string", "description": "PNG, JPEG, OPEN_EXR, FFMPEG, ..."}, "output_path": {"type": "string"}}, [], writes=True)
def render_settings(args, ctx):
    return _exec(ctx, dict(args), '''
        sc = bpy.context.scene; r = sc.render; changed = []
        def setp(obj, k, v):
            setattr(obj, k, v); changed.append(k)
        if A.get("engine"):
            e = str(A["engine"]).upper()
            if e == "EEVEE": e = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [x.identifier for x in r.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
            setp(r, "engine", e)
        if A.get("resolution"): r.resolution_x, r.resolution_y = int(A["resolution"][0]), int(A["resolution"][1]); changed.append("resolution")
        if A.get("percentage"): setp(r, "resolution_percentage", int(A["percentage"]))
        if A.get("film_transparent") is not None: setp(r, "film_transparent", bool(A["film_transparent"]))
        if A.get("fps"): setp(r, "fps", int(A["fps"]))
        if A.get("frame_start") is not None: setp(sc, "frame_start", int(A["frame_start"]))
        if A.get("frame_end") is not None: setp(sc, "frame_end", int(A["frame_end"]))
        if A.get("file_format"): setp(r.image_settings, "file_format", str(A["file_format"]).upper())
        if A.get("output_path"): setp(r, "filepath", A["output_path"])
        if A.get("samples"):
            if r.engine == "CYCLES": setp(sc.cycles, "samples", int(A["samples"]))
            elif hasattr(sc, "eevee"): setp(sc.eevee, "taa_render_samples", int(A["samples"]))
        R["changed"] = changed
        R["now"] = {"engine": r.engine, "resolution": [r.resolution_x, r.resolution_y], "percentage": r.resolution_percentage,
                    "fps": r.fps, "frames": [sc.frame_start, sc.frame_end], "format": r.image_settings.file_format, "output": r.filepath,
                    "transparent": r.film_transparent}
    ''', "render settings")


@tool(B, "ms_blender_render",
      "Render the current scene to an image file (still frame) and report the path and size. Blocks until finished; use a low `percentage` for previews.",
      {"filepath": {"type": "string", "description": "Output path (default: <temp>/ms_render.png)."}, "frame": {"type": "integer"},
       "percentage": {"type": "integer", "minimum": 1, "maximum": 200}, "timeout_seconds": {"type": "integer", "minimum": 30, "maximum": 3600, "description": "Max seconds to wait for the render (default 600)."}}, [], writes=True)
def render(args, ctx):
    return _exec(ctx, dict(args, timeout_seconds=num(args.get("timeout_seconds"), 600, 30, 3600, True)), '''
        import os, tempfile
        sc = bpy.context.scene
        path = A.get("filepath") or os.path.join(tempfile.gettempdir(), "ms_render.png")
        if A.get("frame") is not None: sc.frame_set(int(A["frame"]))
        old = sc.render.resolution_percentage; oldp = sc.render.filepath
        if A.get("percentage"): sc.render.resolution_percentage = int(A["percentage"])
        sc.render.filepath = path
        try: bpy.ops.render.render(write_still=True)
        finally:
            sc.render.resolution_percentage = old; sc.render.filepath = oldp
        R["file"] = path; R["exists"] = os.path.exists(path); R["bytes"] = os.path.getsize(path) if os.path.exists(path) else 0
    ''', "render", 600)


@tool(B, "ms_blender_world",
      "Set the world background: flat `color` + `strength`, or an HDRI image path.",
      {"color": {"type": "string"}, "strength": {"type": "number", "minimum": 0}, "hdri_path": {"type": "string"}}, [], writes=True)
def world(args, ctx):
    a = dict(args)
    if args.get("color") is not None:
        a["color"] = color4(args.get("color"), [0.05, 0.05, 0.05, 1])
    return _exec(ctx, a, '''
        w = bpy.context.scene.world or bpy.data.worlds.new("World"); bpy.context.scene.world = w
        w.use_nodes = True; nt = w.node_tree
        bg = nt.nodes.get("Background") or nt.nodes.new("ShaderNodeBackground")
        if A.get("hdri_path"):
            env = nt.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(A["hdri_path"], check_existing=True)
            nt.links.new(env.outputs["Color"], bg.inputs["Color"])
        elif A.get("color"): bg.inputs["Color"].default_value = A["color"]
        if A.get("strength") is not None: bg.inputs["Strength"].default_value = float(A["strength"])
        R["world"] = w.name
    ''', "world")


@tool(B, "ms_blender_keyframes",
      "Animate: action=insert|clear|list. insert keys `property` (location|rotation_euler|scale|any custom RNA path) at `frame` with `value` "
      "(rotation in DEGREES), or many at once via `keys` [{frame,value}]. Optionally set interpolation and the scene frame range/fps.",
      {"object": OBJ, "action": {"type": "string", "enum": ["insert", "clear", "list"]},
       "property": {"type": "string"}, "frame": {"type": "integer"}, "value": {"type": "array", "items": {"type": "number"}},
       "keys": {"type": "array", "items": {"type": "object", "properties": {"frame": {"type": "integer"}, "value": {"type": "array", "items": {"type": "number"}}}}},
       "interpolation": {"type": "string", "enum": ["CONSTANT", "LINEAR", "BEZIER", "SINE", "QUAD", "CUBIC", "EASE", "BOUNCE", "ELASTIC"]},
       "frame_start": {"type": "integer"}, "frame_end": {"type": "integer"}, "fps": {"type": "integer"}}, ["object", "action"], writes=True)
def keyframes(args, ctx):
    keys = list(as_list(args.get("keys")))
    if args.get("frame") is not None and args.get("value") is not None:
        keys.append({"frame": args.get("frame"), "value": args.get("value")})
    return _exec(ctx, dict(args, keys=keys, action=str(args.get("action") or "list").lower(), property=str(args.get("property") or "location")), '''
        o = _obj(A["object"]); sc = bpy.context.scene; act = A["action"]
        if A.get("frame_start") is not None: sc.frame_start = int(A["frame_start"])
        if A.get("frame_end") is not None: sc.frame_end = int(A["frame_end"])
        if A.get("fps"): sc.render.fps = int(A["fps"])
        prop = A["property"]
        if act == "insert":
            if not A["keys"]: raise ValueError("insert needs `frame`+`value` or `keys`")
            for k in A["keys"]:
                v = list(k["value"]) if isinstance(k["value"], (list, tuple)) else [k["value"]]
                cur = getattr(o, prop)
                if prop == "rotation_euler": v = [math.radians(x) for x in v]
                if hasattr(cur, "__len__"):
                    for i, x in enumerate(v): cur[i] = x
                else: setattr(o, prop, v[0])
                o.keyframe_insert(data_path=prop, frame=int(k["frame"]))
            if A.get("interpolation") and o.animation_data and o.animation_data.action:
                for fc in _fcurves(o.animation_data.action):
                    for kp in fc.keyframe_points: kp.interpolation = A["interpolation"]
        elif act == "clear":
            if o.animation_data: o.animation_data_clear()
        ad = o.animation_data
        R["curves"] = [{"path": fc.data_path, "index": fc.array_index, "keys": [[round(p.co[0], 2), round(p.co[1], 4)] for p in fc.keyframe_points][:60]} for fc in (_fcurves(ad.action) if ad and ad.action else [])]
        R["frames"] = [sc.frame_start, sc.frame_end]; R["fps"] = sc.render.fps
    ''', "keyframes")


_IMPORT = {"fbx": "bpy.ops.import_scene.fbx(filepath=p)", "obj": "(bpy.ops.wm.obj_import(filepath=p) if hasattr(bpy.ops.wm, 'obj_import') else bpy.ops.import_scene.obj(filepath=p))",
           "glb": "bpy.ops.import_scene.gltf(filepath=p)", "gltf": "bpy.ops.import_scene.gltf(filepath=p)",
           "stl": "(bpy.ops.wm.stl_import(filepath=p) if hasattr(bpy.ops.wm, 'stl_import') else bpy.ops.import_mesh.stl(filepath=p))",
           "ply": "(bpy.ops.wm.ply_import(filepath=p) if hasattr(bpy.ops.wm, 'ply_import') else bpy.ops.import_mesh.ply(filepath=p))",
           "usd": "bpy.ops.wm.usd_import(filepath=p)", "usdc": "bpy.ops.wm.usd_import(filepath=p)", "usda": "bpy.ops.wm.usd_import(filepath=p)",
           "abc": "bpy.ops.wm.alembic_import(filepath=p)", "dae": "bpy.ops.wm.collada_import(filepath=p)"}


@tool(B, "ms_blender_import",
      "Import a model file (fbx, obj, glb, gltf, stl, ply, usd, abc, dae) and report the objects it added. Format is taken from the extension.",
      {"filepath": {"type": "string", "description": "Absolute path."}}, ["filepath"], writes=True)
def import_asset(args, ctx):
    path = str(args.get("filepath") or "")
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext not in _IMPORT:
        raise ToolkitError(f"unsupported import format '.{ext}'", "Supported: " + ", ".join(sorted(_IMPORT)))
    body = "import os\n_mode_object()\np = A['filepath']\nif not os.path.exists(p): raise ValueError('file not found: ' + p)\nbefore = set(bpy.data.objects.keys())\n" + _IMPORT[ext] + \
        "\nnew = [o for o in bpy.data.objects if o.name not in before]\nR['imported'] = [_info(o) for o in new][:100]\nR['count'] = len(new)\n"
    return _exec(ctx, dict(args), body, "import " + ext, 300)


_EXPORT = {"fbx": "bpy.ops.export_scene.fbx(filepath=p, use_selection=sel, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', use_mesh_modifiers=mods, bake_space_transform=True)",
           "glb": "bpy.ops.export_scene.gltf(filepath=p, export_format='GLB', use_selection=sel, export_apply=mods)",
           "gltf": "bpy.ops.export_scene.gltf(filepath=p, export_format='GLTF_SEPARATE', use_selection=sel, export_apply=mods)",
           "obj": "(bpy.ops.wm.obj_export(filepath=p, export_selected_objects=sel, apply_modifiers=mods) if hasattr(bpy.ops.wm, 'obj_export') else bpy.ops.export_scene.obj(filepath=p, use_selection=sel, use_mesh_modifiers=mods))",
           "stl": "(bpy.ops.wm.stl_export(filepath=p, export_selected_objects=sel, apply_modifiers=mods) if hasattr(bpy.ops.wm, 'stl_export') else bpy.ops.export_mesh.stl(filepath=p, use_selection=sel, use_mesh_modifiers=mods))",
           "usd": "bpy.ops.wm.usd_export(filepath=p, selected_objects_only=sel)"}


@tool(B, "ms_blender_export",
      "Export the scene or chosen objects to fbx, glb, gltf, obj, stl or usd for Unity, Godot or Roblox. Format comes from the extension. "
      "Reports the file size so you can prove it was written.",
      {"filepath": {"type": "string", "description": "Absolute output path including extension."}, "objects": NAMES,
       "selection_only": {"type": "boolean"}, "apply_modifiers": {"type": "boolean"}}, ["filepath"], writes=True)
def export_asset(args, ctx):
    path = str(args.get("filepath") or "")
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext not in _EXPORT:
        raise ToolkitError(f"unsupported export format '.{ext}'", "Supported: " + ", ".join(sorted(_EXPORT)))
    names = _names(args, "objects")
    body = ("import os\n_mode_object()\np = A['filepath']\nos.makedirs(os.path.dirname(p) or '.', exist_ok=True)\n"
            "names = A.get('objects') or []\nsel = bool(A.get('selection_only')) or bool(names)\nmods = A.get('apply_modifiers', True)\n"
            "if names: _select([_obj(n) for n in names], _obj(names[0]))\n" + _EXPORT[ext] +
            "\nR['file'] = p; R['exists'] = os.path.exists(p); R['bytes'] = os.path.getsize(p) if os.path.exists(p) else 0\n"
            "if not R['exists']: raise ValueError('exporter finished but no file was written')\n")
    return _exec(ctx, dict(args, objects=names), body, "export " + ext, 300)


@tool(B, "ms_blender_select",
      "Change the selection: mode=set|add|remove|all|none|invert, by `names` and/or object `type`; optionally set the active object.",
      {"names": NAMES, "mode": {"type": "string", "enum": ["set", "add", "remove", "all", "none", "invert"]}, "type": {"type": "string"}, "active": {"type": "string"}}, [], writes=True)
def select(args, ctx):
    return _exec(ctx, dict(args, names=_names(args, "names"), mode=str(args.get("mode") or "set").lower(), type=str(args.get("type") or "").upper()), '''
        _mode_object(); vl = bpy.context.view_layer.objects; m = A["mode"]
        pool = [o for o in vl if (not A["type"] or o.type == A["type"])]
        if m == "none": [o.select_set(False) for o in vl]
        elif m == "all": [o.select_set(True) for o in pool]
        elif m == "invert": [o.select_set(not o.select_get()) for o in pool]
        else:
            targets = [_obj(n) for n in A["names"]] if A["names"] else pool
            if m == "set": [o.select_set(False) for o in vl]
            for o in targets: o.select_set(m != "remove")
        if A.get("active"): vl.active = _obj(A["active"])
        R["selected"] = [o.name for o in bpy.context.selected_objects]; R["active"] = vl.active.name if vl.active else None
    ''', "select")


@tool(B, "ms_blender_file",
      "File operations: action=info|save|save_as|revert|purge_orphans|undo|redo. save_as needs `filepath`. Returns the resulting file state.",
      {"action": {"type": "string", "enum": ["info", "save", "save_as", "revert", "purge_orphans", "undo", "redo"]}, "filepath": {"type": "string"}}, ["action"], writes=True)
def file_ops(args, ctx):
    act = str(args.get("action") or "info").lower()
    if act == "save_as" and not args.get("filepath"):
        raise ToolkitError("save_as needs `filepath`")
    return _exec(ctx, dict(args, action=act), '''
        act = A["action"]
        if act == "save":
            if not bpy.data.filepath: raise ValueError("this file has never been saved; use save_as with a filepath")
            bpy.ops.wm.save_mainfile()
        elif act == "save_as": bpy.ops.wm.save_as_mainfile(filepath=A["filepath"], copy=False)
        elif act == "revert": bpy.ops.wm.revert_mainfile()
        elif act == "purge_orphans": bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        elif act == "undo": bpy.ops.ed.undo()
        elif act == "redo": bpy.ops.ed.redo()
        R["file"] = bpy.data.filepath or None; R["unsaved_changes"] = bool(bpy.data.is_dirty); R["blender"] = bpy.app.version_string
    ''', "file " + act)


@tool(B, "ms_blender_add_text",
      "Add a 3D text object with optional extrusion/size/location (convert to mesh with ms_blender_mesh_edit if needed).",
      {"text": {"type": "string"}, "name": {"type": "string"}, "size": {"type": "number"}, "extrude": {"type": "number"}, "location": VEC}, ["text"], writes=True)
def add_text(args, ctx):
    return _exec(ctx, dict(args), '''
        _mode_object()
        c = bpy.data.curves.new(A.get("name") or "Text", "FONT"); c.body = A["text"]
        if A.get("size"): c.size = float(A["size"])
        if A.get("extrude"): c.extrude = float(A["extrude"])
        o = bpy.data.objects.new(c.name, c); bpy.context.scene.collection.objects.link(o); o.location = _v(A.get("location"))
        R["created"] = _info(o)
    ''', "text")


@tool(B, "ms_blender_rig_info",
      "Inspect armatures: bones with parents, head/tail and constraints count, plus which meshes are skinned to them. Read-only.",
      {"armature": {"type": "string"}})
def rig_info(args, ctx):
    return _exec(ctx, dict(args), '''
        arms = [bpy.data.objects[A["armature"]]] if A.get("armature") else [o for o in bpy.data.objects if o.type == "ARMATURE"]
        out = []
        for a in arms:
            bones = [{"name": b.name, "parent": b.parent.name if b.parent else None, "head": [round(x, 3) for x in b.head_local], "tail": [round(x, 3) for x in b.tail_local]} for b in a.data.bones]
            skinned = [o.name for o in bpy.data.objects if any(m.type == "ARMATURE" and m.object == a for m in getattr(o, "modifiers", []))]
            out.append({"name": a.name, "bone_count": len(bones), "bones": bones[:200], "skinned_meshes": skinned,
                        "actions": [x.name for x in bpy.data.actions]})
        R["armatures"] = out
    ''', "rig info")


@tool(B, "ms_blender_run_python",
      "Run Python inside Blender with captured stdout and a structured result. Provide the code as `lines` (an array of source lines - no JSON "
      "escaping of newlines needed) or `code`. Set `result` in your code to return data. Prefer the typed ms_blender_* tools; use this for anything else.",
      {"lines": {"type": "array", "items": {"type": "string"}, "description": "Source lines of the program."}, "code": {"type": "string", "description": "Whole program as one string (alternative to lines)."}, "timeout_seconds": {"type": "integer", "minimum": 5, "maximum": 600, "description": "Max seconds to wait for Blender (default 120)."}}, [], writes=True)
def run_python(args, ctx):
    src = "\n".join(str(x) for x in as_list(args.get("lines"))) if args.get("lines") else str(args.get("code") or "")
    if not src.strip():
        raise ToolkitError("give `lines` or `code`")
    try:
        compile(src, "<ms_blender_run_python>", "exec")
    except SyntaxError as exc:
        raise ToolkitError(f"SyntaxError before sending: {exc.msg} (line {exc.lineno})", "Fix the Python and call again - nothing ran in Blender.")
    return _exec(ctx, {"src": src, "dry_run": args.get("dry_run"), "timeout_seconds": args.get("timeout_seconds")}, '''
        import io, contextlib
        buf = io.StringIO(); ns = {"bpy": bpy, "result": None, "math": math, "json": json}
        with contextlib.redirect_stdout(buf):
            exec(compile(A["src"], "<ms_blender_run_python>", "exec"), ns)
        R["stdout"] = buf.getvalue()[-4000:]; R["result"] = ns.get("result")
    ''', "run python")


@tool(B, "ms_blender_changes",
      "See what changed in Blender since a checkpoint - including edits the USER made by hand. action=checkpoint saves a labelled snapshot of "
      "every object's transform/materials/modifiers; action=diff compares the live scene to it (added/removed/changed). Read-only for the scene.",
      {"action": {"type": "string", "enum": ["checkpoint", "diff"]}, "label": {"type": "string", "description": "Snapshot name (default 'default')."}}, ["action"])
def changes(args, ctx):
    label = str(args.get("label") or "default")
    res = _exec(ctx, dict(args), '''
        snap = {}
        for o in bpy.context.scene.objects:
            d = _info(o); d.pop("name", None); snap[o.name] = d
        R["snapshot"] = snap
    ''', "snapshot")
    if not res.get("ok", True) or res.get("dryRun"):
        return res
    snap = res.pop("snapshot", {}) or {}
    act = str(args.get("action") or "diff").lower()
    if act == "checkpoint":
        snapshot_store(B, label, snap)
        return {"ok": True, "label": label, "objects": len(snap), "note": "Checkpoint saved. Call again with action=diff after changes."}
    prev = snapshot_get(B, label)
    if not prev:
        raise ToolkitError(f"no checkpoint named '{label}'", "Call with action=checkpoint first.")
    out = diff_maps(prev["data"], snap)
    out.update({"ok": True, "label": label, "since_seconds": int(__import__("time").time() - prev["at"])})
    return out
