# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender prop-modelling tools for engine_toolkit: `ms_blender_prop_generator` builds clean, game-ready props
(trees, rocks, furniture, weapons, fences, lamps, ...) from bmesh primitives with named material slots, correct
origin on the ground, optional bevel/smooth shading, and variation seeds. Verified against real headless Blender."""
from engine_toolkit import tool, ToolkitError, color4
from toolkit_blender import _exec, VEC

B = "blender"
PROP_KINDS = ["tree_pine", "tree_round", "tree_palm", "rock", "crate", "barrel", "fence", "chair", "table", "bed", "bookshelf", "lamp_post",
              "sword", "shield", "axe", "column", "arch", "stairs", "well", "tent", "campfire", "tower", "bridge", "gravestone", "mushroom", "chest"]


@tool(B, "ms_blender_prop_generator",
      "Model a game-ready PROP from real bmesh geometry (trees, rocks, crates, barrels, fences, furniture, lamps, swords, shields, columns, arches, stairs, wells, tents, towers, bridges...). "
      "Origin on the ground centre, +Z up, named material slots, per-axis scale, seeded variation, optional bevel/smooth. Returns object name, counts and dimensions. kind=list shows all kinds.",
      {"kind": {"type": "string", "enum": PROP_KINDS + ["list"]}, "name": {"type": "string"}, "location": VEC,
       "scale": {"type": ["number", "array"], "description": "Uniform number or [x,y,z]."}, "seed": {"type": "integer", "description": "Variation seed."},
       "detail": {"type": "integer", "minimum": 3, "maximum": 64, "description": "Radial segments for round parts (default 12)."},
       "bevel": {"type": "number", "description": "Add a Bevel modifier of this width (m); 0 = none."}, "smooth": {"type": "boolean"},
       "color": {"type": ["string", "array"], "description": "Tint for the main material slot (hex / name / [r,g,b])."},
       "count": {"type": "integer", "minimum": 1, "maximum": 40, "description": "Fence/stairs/bridge segment count (default per kind)."},
       "collection": {"type": "string"}},
      ["kind"], writes=True)
def prop_generator(args, ctx):
    a = dict(args)
    kind = str(a.get("kind") or "").lower()
    if kind == "list":
        return {"ok": True, "kinds": PROP_KINDS}
    if kind not in PROP_KINDS:
        raise ToolkitError(f"unknown kind '{kind}'", "Use one of: " + ", ".join(PROP_KINDS))
    a["kind"] = kind
    a.setdefault("name", kind.title().replace("_", ""))
    if a.get("color") is not None:
        a["color"] = list(color4(a["color"]))
    s = a.get("scale", 1)
    a["scale"] = [float(x) for x in s] if isinstance(s, (list, tuple)) and len(s) == 3 else [float(s if isinstance(s, (int, float)) else 1)] * 3
    return _exec(ctx, a, _PROP_BODY, "prop " + kind)


_PROP_BODY = '''
    import bmesh, random, math
    from mathutils import Matrix, Vector
    K = A["kind"]; rng = random.Random(int(A.get("seed") or 1)); SEG = int(A.get("detail") or 12)
    bm = bmesh.new(); MATS = []
    def mat(name):
        if name not in MATS: MATS.append(name)
        return MATS.index(name)
    def fin(vs, M, mi):
        bmesh.ops.transform(bm, matrix=M, verts=vs)
        for f in {f for v in vs for f in v.link_faces}: f.material_index = mi
    def box(c, s, m, rot=(0, 0, 0)):
        vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        R = Matrix.Rotation(rot[2], 4, "Z") @ Matrix.Rotation(rot[1], 4, "Y") @ Matrix.Rotation(rot[0], 4, "X")
        fin(vs, Matrix.Translation(c) @ R @ Matrix.Diagonal((s[0], s[1], s[2], 1.0)), mat(m))
    def cyl(c, r1, r2, h, m, seg=None, rot=(0, 0, 0)):
        vs = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg or SEG, radius1=r1, radius2=r2, depth=1.0)["verts"]
        R = Matrix.Rotation(rot[2], 4, "Z") @ Matrix.Rotation(rot[1], 4, "Y") @ Matrix.Rotation(rot[0], 4, "X")
        fin(vs, Matrix.Translation(c) @ R @ Matrix.Diagonal((1, 1, h, 1.0)), mat(m))
    def sph(c, r, m, sq=1.0, seg=None):
        vs = bmesh.ops.create_uvsphere(bm, u_segments=seg or SEG, v_segments=max(3, (seg or SEG) // 2 + 1), radius=1.0)["verts"]
        fin(vs, Matrix.Translation(c) @ Matrix.Diagonal((r, r, r * sq, 1.0)), mat(m))
    def tri_prism(c, w, d, h, m):
        # gable prism (ridge along Y)
        v = [bm.verts.new(p) for p in [(-w/2, -d/2, 0), (w/2, -d/2, 0), (w/2, d/2, 0), (-w/2, d/2, 0), (0, -d/2, h), (0, d/2, h)]]
        for fi in [(0, 1, 4), (2, 3, 5), (1, 2, 5, 4), (3, 0, 4, 5), (3, 2, 1, 0)]:
            f = bm.faces.new([v[i] for i in fi]); f.material_index = mat(m)
        bmesh.ops.translate(bm, verts=v, vec=c)
    N = A.get("count")
    if K == "tree_pine":
        h = 4.0 + rng.random() * 1.0
        cyl((0, 0, 0.6), 0.18, 0.12, 1.2, "Bark", max(6, SEG // 2))
        for i in range(4):
            r = 1.4 - i * 0.3; z = 1.0 + i * 0.95
            cyl((0, 0, z + 0.7), r, 0.05, 1.6 - i * 0.15, "Leaves")
    elif K == "tree_round":
        cyl((0, 0, 0.9), 0.22, 0.16, 1.8, "Bark", max(6, SEG // 2))
        for _ in range(5):
            sph(((rng.random() - .5) * 1.2, (rng.random() - .5) * 1.2, 2.5 + rng.random() * 1.0), 0.9 + rng.random() * 0.4, "Leaves", 0.85)
        sph((0, 0, 2.8), 1.3, "Leaves", 0.85)
    elif K == "tree_palm":
        segs = 8; lean = (rng.random() - .5) * 0.6
        for i in range(segs):
            cyl((lean * i / segs, 0, 0.45 + i * 0.5), 0.2 - i * 0.012, 0.19 - i * 0.012, 0.5, "Bark", max(6, SEG // 2))
        top = (lean * (segs / segs) , 0, segs * 0.5)
        for i in range(8):
            ang = i * math.tau / 8
            box((top[0] + math.cos(ang) * 1.0, math.sin(ang) * 1.0, top[2] + 0.1), (2.0, 0.35, 0.04), "Leaves", (0, math.radians(-18), ang))
    elif K == "rock":
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
        for v in bm.verts: v.co = Vector((v.co.x * (1 + (rng.random() - .5) * 0.9), v.co.y * (1 + (rng.random() - .5) * 0.9), v.co.z * (0.65 + rng.random() * 0.3)))
        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts: v.co.z -= zmin
        for f in bm.faces: f.material_index = mat("Stone")
    elif K == "crate":
        box((0, 0, 0.5), (1, 1, 1), "Wood")
        for sx in (-0.45, 0.45):
            for sy in (-0.45, 0.45): box((sx, sy, 0.5), (0.1, 0.1, 1.04), "Frame")
        for z in (0.04, 0.96): box((0, 0, z), (1.04, 1.04, 0.08), "Frame")
    elif K == "barrel":
        cyl((0, 0, 0.5), 0.4, 0.4, 1.0, "Wood", max(SEG, 10)); sph((0, 0, 0.5), 0.46, "Wood", 1.0 / 0.46 * 0.5, max(SEG, 10))
        for z in (0.15, 0.85): cyl((0, 0, z), 0.43, 0.43, 0.05, "Metal", max(SEG, 10))
    elif K == "fence":
        n = int(N or 4); sp = 1.2
        for i in range(n + 1): box((i * sp, 0, 0.5), (0.12, 0.12, 1.0), "Wood")
        for z in (0.35, 0.75): box((n * sp / 2, 0, z), (n * sp, 0.06, 0.1), "Wood")
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=(-n * sp / 2, 0, 0))
    elif K == "chair":
        for sx in (-0.2, 0.2):
            for sy in (-0.2, 0.2): box((sx, sy, 0.225), (0.05, 0.05, 0.45), "Wood")
        box((0, 0, 0.47), (0.5, 0.5, 0.06), "Wood"); box((0, 0.22, 0.8), (0.46, 0.05, 0.6), "Wood")
    elif K == "table":
        box((0, 0, 0.73), (1.6, 0.9, 0.06), "Wood")
        for sx in (-0.72, 0.72):
            for sy in (-0.38, 0.38): box((sx, sy, 0.35), (0.08, 0.08, 0.7), "Wood")
    elif K == "bed":
        box((0, 0, 0.25), (1.0, 2.0, 0.3), "Frame"); box((0, 0.05, 0.5), (0.94, 1.9, 0.2), "Sheet"); box((0, 0.8, 0.65), (0.6, 0.3, 0.12), "Pillow")
        box((0, 1.02, 0.55), (1.04, 0.06, 0.9), "Frame")
    elif K == "bookshelf":
        box((0, 0, 1.0), (1.2, 0.35, 2.0), "Wood")
        for z in (0.35, 0.8, 1.25, 1.7): box((0, -0.03, z), (1.1, 0.3, 0.04), "Shelf")
        for i in range(10): box((-0.5 + i * 0.11, -0.05, 0.55 + (i % 3) * 0.45), (0.07, 0.2, 0.25 + rng.random() * 0.1), "Books")
    elif K == "lamp_post":
        cyl((0, 0, 0.1), 0.18, 0.15, 0.2, "Metal"); cyl((0, 0, 1.7), 0.06, 0.05, 3.2, "Metal", 8); sph((0, 0, 3.4), 0.22, "Light", 1.0)
        box((0, 0, 3.65), (0.5, 0.5, 0.06), "Metal")
    elif K == "sword":
        box((0, 0, 0.7), (0.1, 0.02, 1.0), "Blade"); box((0, 0, 0.18), (0.35, 0.05, 0.05), "Guard"); cyl((0, 0, 0.0), 0.025, 0.025, 0.3, "Grip", 8, ); sph((0, 0, -0.17), 0.045, "Guard", 1.0, 8)
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0, 0, 0.2))
    elif K == "shield":
        cyl((0, 0, 0.0), 0.5, 0.5, 0.06, "Face", max(SEG, 12), rot=(math.pi / 2, 0, 0)); cyl((0, 0.05, 0), 0.12, 0.08, 0.1, "Metal", 10, rot=(math.pi / 2, 0, 0))
        cyl((0, 0, 0), 0.52, 0.52, 0.04, "Metal", max(SEG, 12), rot=(math.pi / 2, 0, 0))
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0, 0, 0.5))
    elif K == "axe":
        cyl((0, 0, 0.6), 0.03, 0.03, 1.2, "Handle", 8); box((0.12, 0, 1.05), (0.25, 0.04, 0.28), "Blade")
    elif K == "column":
        box((0, 0, 0.15), (1.0, 1.0, 0.3), "Stone"); cyl((0, 0, 1.8), 0.4, 0.34, 3.0, "Stone", max(SEG, 12)); box((0, 0, 3.45), (1.0, 1.0, 0.3), "Stone")
    elif K == "arch":
        for sx in (-1.2, 1.2): box((sx, 0, 1.5), (0.6, 0.8, 3.0), "Stone")
        n = 9
        for i in range(n):
            a0 = math.pi * i / (n - 1); box((math.cos(a0) * 1.2, 0, 3.0 + math.sin(a0) * 1.0), (0.55, 0.8, 0.5), "Stone", (0, -(a0 - math.pi / 2) , 0))
    elif K == "stairs":
        n = int(N or 8)
        for i in range(n): box((0, i * 0.3 + 0.15, i * 0.2 + 0.1), (1.6, 0.3, 0.2 * (i + 1)), "Stone")
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0, -n * 0.15, 0))
    elif K == "well":
        cyl((0, 0, 0.45), 1.0, 1.0, 0.9, "Stone", max(SEG, 14))
        for sx in (-0.9, 0.9): box((sx, 0, 1.6), (0.12, 0.12, 1.5), "Wood")
        box((0, 0, 2.4), (2.2, 0.15, 0.1), "Wood"); tri_prism((0, 0, 2.45), 2.6, 1.6, 0.7, "Roof")
    elif K == "tent":
        tri_prism((0, 0, 0), 2.4, 3.0, 1.8, "Canvas"); box((0, -1.51, 0.5), (0.7, 0.04, 1.0), "Dark")
    elif K == "campfire":
        for i in range(6):
            a0 = i * math.tau / 6; cyl((math.cos(a0) * 0.7, math.sin(a0) * 0.7, 0.1), 0.1, 0.1, 0.2, "Stone", 6)
        for i in range(4):
            box((0, 0, 0.17), (0.9, 0.1, 0.1), "Wood", (0, 0, i * math.pi / 4))
        cyl((0, 0, 0.45), 0.25, 0.01, 0.6, "Flame", 8)
    elif K == "tower":
        cyl((0, 0, 2.5), 1.6, 1.4, 5.0, "Stone", max(SEG, 12))
        cyl((0, 0, 5.15), 1.8, 1.8, 0.3, "Stone", max(SEG, 12)); cyl((0, 0, 6.4), 1.7, 0.0, 2.2, "Roof", max(SEG, 12))
        for i in range(8):
            a0 = i * math.tau / 8; box((math.cos(a0) * 1.75, math.sin(a0) * 1.75, 5.5), (0.45, 0.45, 0.4), "Stone", (0, 0, a0))
    elif K == "bridge":
        n = int(N or 6)
        for i in range(n): box((0, i * 1.0, 0.5 + math.sin(i / max(n - 1, 1) * math.pi) * 0.4), (3.0, 1.02, 0.2), "Wood")
        for sx in (-1.5, 1.5):
            for i in range(0, n + 1, 2): box((sx, i * 1.0 - 0.5, 1.0), (0.12, 0.12, 1.0), "Rail")
            box((sx, n / 2 - 0.5, 1.45), (0.1, n, 0.1), "Rail")
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0, -n / 2, 0))
    elif K == "gravestone":
        box((0, 0, 0.5), (0.7, 0.15, 1.0), "Stone"); cyl((0, 0, 1.0), 0.35, 0.35, 0.15, "Stone", 14, rot=(math.pi / 2, 0, 0)); box((0, -0.08, 0.4), (0.4, 0.03, 0.05), "Moss")
    elif K == "mushroom":
        cyl((0, 0, 0.3), 0.12, 0.09, 0.6, "Stem", 10); sph((0, 0, 0.65), 0.4, "Cap", 0.6)
    elif K == "chest":
        box((0, 0, 0.3), (1.0, 0.6, 0.6), "Wood"); cyl((0, 0, 0.6), 0.3, 0.3, 1.0, "Wood", 12, rot=(0, math.pi / 2, 0))
        box((0, -0.31, 0.45), (0.12, 0.03, 0.18), "Metal"); box((0, 0, 0.3), (1.04, 0.62, 0.08), "Metal")
    # normalise: origin on ground centre
    xs = [v.co.x for v in bm.verts]; ys = [v.co.y for v in bm.verts]; zs = [v.co.z for v in bm.verts]
    cx = (min(xs) + max(xs)) / 2; cy = (min(ys) + max(ys)) / 2; zmin = min(zs)
    if K not in ("fence", "bridge", "stairs", "sword", "shield"): bmesh.ops.translate(bm, verts=bm.verts[:], vec=(-cx, -cy, -zmin))
    elif K in ("sword", "shield"): bmesh.ops.translate(bm, verts=bm.verts[:], vec=(-cx, -cy, 0))
    sc = A.get("scale") or [1, 1, 1]
    bmesh.ops.scale(bm, vec=Vector(sc), verts=bm.verts[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(A["name"]); bm.to_mesh(me); bm.free()
    PAL = {"Bark": (0.25, 0.15, 0.08, 1), "Leaves": (0.12, 0.45, 0.14, 1), "Stone": (0.45, 0.45, 0.47, 1), "Wood": (0.5, 0.33, 0.18, 1), "Frame": (0.3, 0.2, 0.1, 1),
           "Metal": (0.55, 0.56, 0.6, 1), "Blade": (0.8, 0.82, 0.88, 1), "Guard": (0.7, 0.55, 0.2, 1), "Grip": (0.15, 0.08, 0.05, 1), "Light": (1.0, 0.85, 0.5, 1),
           "Roof": (0.5, 0.15, 0.1, 1), "Canvas": (0.8, 0.72, 0.55, 1), "Flame": (1.0, 0.45, 0.1, 1), "Cap": (0.8, 0.12, 0.1, 1), "Stem": (0.9, 0.88, 0.8, 1),
           "Face": (0.6, 0.12, 0.12, 1), "Sheet": (0.75, 0.75, 0.9, 1), "Pillow": (0.95, 0.95, 0.95, 1), "Books": (0.5, 0.2, 0.2, 1), "Shelf": (0.4, 0.28, 0.16, 1),
           "Handle": (0.4, 0.25, 0.12, 1), "Rail": (0.35, 0.22, 0.12, 1), "Moss": (0.2, 0.4, 0.2, 1), "Dark": (0.05, 0.04, 0.04, 1)}
    for i, nm in enumerate(MATS):
        m = bpy.data.materials.new("%s_%s" % (A["name"], nm))
        try: m.use_nodes = True
        except Exception: pass
        b = m.node_tree.nodes.get("Principled BSDF")
        col = tuple(A["color"]) if (A.get("color") and i == 0) else PAL.get(nm, (0.6, 0.6, 0.6, 1))
        if b:
            b.inputs["Base Color"].default_value = col; b.inputs["Roughness"].default_value = 0.35 if nm in ("Metal", "Blade", "Guard") else 0.8
            if nm in ("Metal", "Blade", "Guard") and "Metallic" in b.inputs: b.inputs["Metallic"].default_value = 0.9
            if nm in ("Light", "Flame"):
                for k in ("Emission Color", "Emission"):
                    if k in b.inputs: b.inputs[k].default_value = col; break
                if "Emission Strength" in b.inputs: b.inputs["Emission Strength"].default_value = 4.0
        me.materials.append(m)
    obj = bpy.data.objects.new(A["name"], me)
    coll = bpy.context.scene.collection
    if A.get("collection"):
        coll = bpy.data.collections.get(A["collection"]) or bpy.data.collections.new(A["collection"])
        if coll.name not in bpy.context.scene.collection.children: bpy.context.scene.collection.children.link(coll)
    coll.objects.link(obj); obj.location = _v(A.get("location"))
    if A.get("smooth"):
        for p in me.polygons: p.use_smooth = True
    if A.get("bevel"):
        md = obj.modifiers.new("Bevel", "BEVEL"); md.width = float(A["bevel"]); md.segments = 2; md.limit_method = "ANGLE"
    d = obj.dimensions
    R["object"] = obj.name; R["kind"] = K; R["vertices"] = len(me.vertices); R["faces"] = len(me.polygons)
    R["dimensions"] = [round(d.x, 3), round(d.y, 3), round(d.z, 3)]; R["materials"] = [m.name for m in me.materials]
'''
