# SPDX-License-Identifier: GPL-3.0-or-later
"""Native "pro" engine tools (animation, VFX, UI, terrain, level blockout, gameplay kits...).

Each engine section runs the generated program against the REAL engine when it is available and
SKIPS otherwise (never fails on a plain machine):
  Blender -> headless bpy (tests/support/bpy_worker.py)     Godot -> headless Godot 4 loading the generated files
  Roblox  -> real Luau compiler (syntax) + Roblox API mock   Unity  -> C# syntax via tree-sitter + plan checks
"""
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "tests" / "support"))
import engine_toolkit as T  # noqa: E402
import live_engines as L  # noqa: E402

T.ensure_loaded()
fails, skips = [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)[:400]) if (detail and not ok) else ""))
    if not ok:
        fails.append(name)


def run(ctx, _tool, **args):
    return json.loads(T.run(_tool, args, ctx)["text"])


check("pro modules imported without errors", not T.PRO_ERRORS, T.PRO_ERRORS)
counts = T.counts()
check("blender gained native pro tools", counts["blender"] >= 44, counts)

# schema hygiene for every registered tool
PRO = {n: sp for n, sp in T.REGISTRY.items() if getattr(sp["handler"], "__module__", "").endswith(("_pro", "_world", "_game", "_build", "_props", "_npc"))}
check("pro tools registered", len(PRO) >= 14, len(PRO))
check("every schema property is an object", all(isinstance(v, dict) for sp in T.REGISTRY.values() for v in sp["inputSchema"]["properties"].values()))
untyped = [(n, k) for n, sp in PRO.items() for k, v in sp["inputSchema"]["properties"].items() if not (v.get("type") or v.get("enum"))]
check("every pro-tool property is typed", not untyped, untyped[:5])
check("pro tool descriptions are specific", all(len(sp["description"]) > 80 for sp in PRO.values()), [n for n, sp in PRO.items() if len(sp["description"]) <= 80])
check("pro tool names follow ms_<engine>_*", all(n.startswith("ms_" + sp["engine"] + "_") for n, sp in PRO.items()))
check("required fields exist in properties", all(set(sp["inputSchema"]["required"]) <= set(sp["inputSchema"]["properties"]) for sp in T.REGISTRY.values()))

# ═══════════════════════════ Blender (real bpy) ═══════════════════════════
if not L.blender_python():
    skips.append("blender")
    print("SKIP blender: no bpy python")
else:
    ctx = L.LiveBlender()

    def probe(code):
        out = ctx.call("blender", "execute_blender_code", {"code": "import bpy, json, math\n" + code})["text"]
        m = re.search(r"PROBE(.*)", out)
        return json.loads(m.group(1)) if m else {"raw": out[-300:]}

    def ok_(name, out):
        check(name, out.get("ok") is True, {k: out.get(k) for k in ("error", "trace", "raw")})
        return out

    ok_("blender prims", run(ctx, "ms_blender_create_primitive", shape="cube", name="Box", location=[0, 0, 1]))
    run(ctx, "ms_blender_create_primitive", shape="uv_sphere", name="Ball", location=[3, 0, 1])
    check("create_primitive shape works", probe("print('PROBE'+json.dumps(len(bpy.data.objects['Ball'].data.vertices)))") > 100)
    run(ctx, "ms_blender_create_primitive", type="cone", name="AliasCone")
    check("create_primitive accepts type= alias", probe("print('PROBE'+json.dumps(len(bpy.data.objects['AliasCone'].data.vertices)))") < 40)

    # motion presets produce real keyframes on the right channels
    for p, ch in (("bounce", "location"), ("spin", "rotation_euler"), ("pulse", "scale"), ("pop_in", "scale"), ("shake", "location"), ("orbit", "location"), ("pendulum", "rotation_euler")):
        run(ctx, "ms_blender_motion_preset", objects=["Box"], preset=p, duration_frames=24)
    info = probe('''
a = bpy.data.objects["Box"].animation_data.action
def fcs(a):
    fc = getattr(a, "fcurves", None)
    if fc is not None: return list(fc)
    return [f for l in a.layers for s in l.strips for cb in s.channelbags for f in cb.fcurves]
f = fcs(a)
print("PROBE" + json.dumps({"channels": sorted({x.data_path for x in f}), "keys": sum(len(x.keyframe_points) for x in f), "cyc": any(m.type == "CYCLES" for x in f for m in x.modifiers)}))''')
    check("motion presets wrote location/rotation/scale keyframes", {"location", "rotation_euler", "scale"} <= set(info["channels"]) and info["keys"] > 20 and info["cyc"], info)
    out = run(ctx, "ms_blender_motion_preset", objects=["Box", "Ball"], preset="bounce", stagger_frames=6, start_frame=10, duration_frames=30, loops=2, cyclic=False)
    check("stagger + loops reflected in frame range", out["ok"] and out["objects"][1]["frames"][0] == 16 and out["frame_range"][1] >= 76, out)
    bad = run(ctx, "ms_blender_motion_preset", objects=["Box"], preset="nope")
    check("unknown preset gives a helpful error", not bad["ok"] and "bounce" in bad.get("hint", ""), bad)

    ok_("actions create", run(ctx, "ms_blender_animation_actions", action="create", action_name="Idle"))
    out = ok_("actions list", run(ctx, "ms_blender_animation_actions", action="list"))
    check("actions list shows Idle + assigned", any(x["name"] == "Idle" for x in out["actions"]) and "Box" in out["assigned"], out)
    ok_("nla push", run(ctx, "ms_blender_animation_actions", action="nla_push", object="Ball", action_name="Idle", frame_start=1))
    out = run(ctx, "ms_blender_animation_actions", action="nla_list")
    check("nla track exists", any(t["object"] == "Ball" for t in out.get("tracks", [])), out)

    ok_("shape key add", run(ctx, "ms_blender_shape_keys", action="add", object="Ball", name="Squash"))
    out = ok_("shape key keyframe", run(ctx, "ms_blender_shape_keys", action="keyframe", object="Ball", values={"Squash": 1.0}, frame=12))
    check("shape keys listed with Basis", [k["name"] for k in out["shape_keys"]] == ["Basis", "Squash"], out)

    run(ctx, "ms_blender_create_primitive", shape="cylinder", name="Body", location=[0, 0, 0.9], scale=[0.2, 0.2, 0.9])
    out = ok_("humanoid rig + auto weights", run(ctx, "ms_blender_armature_rig", action="create", preset="humanoid", name="Rig", bind_to=["Body"], height=1.8))
    check("rig bones + vertex groups created", len(out["bones"]) == 13 and out["vertex_groups"]["Body"] >= 10, out)
    ok_("pose + keyframe", run(ctx, "ms_blender_armature_rig", action="pose", name="Rig", pose={"upper_arm.L": [0, 0, 45]}, frame=5))
    ok_("mirror", run(ctx, "ms_blender_armature_rig", action="mirror", name="Rig"))
    out = run(ctx, "ms_blender_armature_rig", action="list")
    check("mirror created .R bones", any(b["name"] == "upper_arm.R" for a in out["armatures"] for b in a["bones"]), out)
    ok_("ik", run(ctx, "ms_blender_armature_rig", action="ik", name="Rig", bone="shin.L"))
    for pr in ("spine_chain", "tail", "quadruped"):
        ok_("rig preset " + pr, run(ctx, "ms_blender_armature_rig", action="create", preset=pr, name="R_" + pr))

    for m in ("wood", "marble", "brick", "brushed_metal", "gold", "copper", "chrome", "rock", "concrete", "grass", "sand", "snow", "water", "lava", "glass", "neon", "toon", "plastic", "fabric", "rubber", "ice", "leather"):
        out = run(ctx, "ms_blender_procedural_material", preset=m, assign_to=["Box"])
        if not out.get("ok") or out.get("nodes", 0) < 2:
            check("material " + m, False, out)
    check("all 22 procedural materials build valid node trees", True)
    info = probe('print("PROBE"+json.dumps([m.name for m in bpy.data.objects["Box"].data.materials]))')
    check("material assigned (replace slots)", info == ["MS_Leather"], info)

    out = ok_("terrain", run(ctx, "ms_blender_terrain", name="T", size=60, resolution=48, island=True, water=True, height=10, seed=3))
    check("terrain heights span the requested relief", abs(out["height_range"][1] - 10) < 0.01 and out["vertices"] == 49 * 49 and "water" in out, out)
    out2 = run(ctx, "ms_blender_terrain", name="T2", size=60, resolution=48, island=True, height=10, seed=3)
    out3 = run(ctx, "ms_blender_terrain", name="T3", size=60, resolution=48, island=True, height=10, seed=4)
    h = lambda n: probe('o=bpy.data.objects["%s"]; print("PROBE"+json.dumps([round(v.co.z,3) for v in o.data.vertices[:200]]))' % n)
    check("terrain deterministic by seed, differs across seeds", h("T") == h("T2") and h("T") != h("T3"))
    run(ctx, "ms_blender_create_primitive", shape="cone", name="Tree", radius=0.8, depth=3)
    out = ok_("scatter", run(ctx, "ms_blender_scatter", source="Tree", target="T", count=120, min_distance=2.0, min_height=2.0, max_height=8.0, align_to_normal=True))
    check("scatter placed instances within height band", out["placed"] >= 40 and out["bounds"]["min"][2] >= 1.99 and out["bounds"]["max"][2] <= 8.01, out)
    info = probe('c=bpy.data.collections["MS_Scatter"]; print("PROBE"+json.dumps({"n":len(c.objects),"shared":len({o.data.name for o in c.objects})}))')
    check("scatter instances share mesh data", info["shared"] == 1 and info["n"] == out["placed"], info)

    for pr in ("fire", "smoke", "sparks", "magic", "rain", "snow", "dust", "embers", "fountain", "fireflies"):
        o = run(ctx, "ms_blender_vfx_preset", preset=pr, name="V_" + pr)
        if not o.get("ok"):
            check("vfx " + pr, False, o)
    info = probe('''
sc = bpy.context.scene; sc.frame_set(20)
dg = bpy.context.evaluated_depsgraph_get()
e = bpy.data.objects["V_fire"].evaluated_get(dg)
print("PROBE" + json.dumps({"particles": len(e.particle_systems[0].particles), "count": e.particle_systems[0].settings.count}))''')
    check("particle systems really emit on the timeline", info["particles"] > 0, info)

    out = ok_("curve path + followers", run(ctx, "ms_blender_curve_path", points=[[0, 0, 0], [5, 0, 2], [8, 5, 0], [2, 8, 1]], followers=["Ball"], bevel_depth=0.1, closed=True, duration_frames=60))
    info = probe('print("PROBE"+json.dumps([c.type for c in bpy.data.objects["Ball"].constraints]))')
    check("follow-path constraint added", info == ["FOLLOW_PATH"], info)
    out = run(ctx, "ms_blender_mesh_cleanup", objects=["Ball"], decimate_ratio=0.5)
    check("decimate on a mesh with shape keys degrades with a warning, not an error", out["ok"] and out.get("warnings"), out)
    run(ctx, "ms_blender_create_primitive", shape="uv_sphere", name="Dec", location=[0, 5, 0])
    out = ok_("mesh cleanup", run(ctx, "ms_blender_mesh_cleanup", objects=["Dec"], triangulate=True, decimate_ratio=0.5, shade="auto", fill_holes=4))
    b, a_ = out["objects"][0]["before"], out["objects"][0]["after"]
    check("decimate reduced the mesh", a_["vertices"] < b["vertices"] * 0.7, out)

    for l in ("three_point", "product", "dramatic", "soft", "rim", "sunset", "night", "none"):
        o = run(ctx, "ms_blender_scene_studio", targets=["Box", "Ball"], lighting=l, backdrop=(l == "soft"), turntable=(l == "three_point"), render={"engine": "CYCLES", "width": 320, "height": 180, "samples": 8})
        if not o.get("ok"):
            check("studio " + l, False, o)
    info = probe('sc=bpy.context.scene; print("PROBE"+json.dumps({"cam": sc.camera.name, "res": [sc.render.resolution_x, sc.render.resolution_y], "engine": sc.render.engine}))')
    check("studio set camera/render settings", info["cam"] == "MS_Camera" and info["res"] == [320, 180] and info["engine"] == "CYCLES", info)
    o = run(ctx, "ms_blender_scene_studio", targets=["Box"], lighting="three_point", turntable=True, turntable_frames=48)
    info = probe('''
sc = bpy.context.scene
rig = bpy.data.objects["MS_TurntableRig"]
sc.frame_set(1); a0 = rig.rotation_euler.z; sc.frame_set(25); a1 = rig.rotation_euler.z
print("PROBE" + json.dumps({"half": round(a1 - a0, 2), "end": sc.frame_end}))''')
    check("turntable rotates linearly (half turn at half the frames)", abs(info["half"] - 3.1416) < 0.2 and info["end"] == 48, info)

    for st, roof in (("modern", "flat"), ("classic", "gabled"), ("industrial", "hip"), ("tower", "none")):
        o = run(ctx, "ms_blender_building", style=st, roof=roof, floors=3, name="B_" + st)
        if not o.get("ok") or o["vertices"] < 200 or len(o["materials"]) != 5:
            check("building " + st, False, o)
    check("buildings generate real geometry for all styles", True)

    # prop generator: every kind builds real geometry, sits on the ground and keeps its material slots
    import toolkit_blender_props as BP
    for kind in BP.PROP_KINDS:
        o = run(ctx, "ms_blender_prop_generator", kind=kind, name="Prop_" + kind, smooth=True, bevel=0.01, seed=3)
        check("prop " + kind, o.get("ok") is True and o.get("vertices", 0) >= 12 and all(d > 0.05 for d in o.get("dimensions", [0])), {k: o.get(k) for k in ("error", "trace", "dimensions", "vertices")})
    info = probe("o = bpy.data.objects['Prop_crate']; print('PROBE' + json.dumps({'z': round(min(v.co.z for v in o.data.vertices), 3), 'mats': len(o.data.materials), 'mods': [m.type for m in o.modifiers]}))")
    check("prop origin is on the ground with material slots and bevel", info.get("z") == 0.0 and info.get("mats", 0) >= 2 and info.get("mods") == ["BEVEL"], info)
    o = run(ctx, "ms_blender_prop_generator", kind="tree_round", name="BigTree", scale=[2, 2, 3], location=[5, 0, 0])
    check("prop scale and location", o.get("ok") and o["dimensions"][2] > 8, o)
    check("prop rejects unknown kinds", run(ctx, "ms_blender_prop_generator", kind="nope").get("ok") is False)
    out = ok_("level blockout", run(ctx, "ms_blender_level_blockout", rows=["#######", "#..E..#", "#.P.C.#", "#..S..W", "###D###"], cell_size=2))
    check("blockout counts match the map", out["counts"] == {"floor": 15, "wall": 19, "door": 1, "prop": 3} and out["size_m"] == [14.0, 10.0], out)

    ok_("rigid body", run(ctx, "ms_blender_physics", kind="rigid_body", objects=["Ball"], mass=2.5))
    ok_("passive rigid body", run(ctx, "ms_blender_physics", kind="rigid_body", objects=["Box"], body_type="PASSIVE"))
    info = probe('print("PROBE"+json.dumps({"mass": bpy.data.objects["Ball"].rigid_body.mass, "type": bpy.data.objects["Box"].rigid_body.type}))')
    check("physics values applied", info == {"mass": 2.5, "type": "PASSIVE"}, info)
    ok_("cloth", run(ctx, "ms_blender_physics", kind="cloth", objects=["T2"], preset="silk"))
    ok_("force field", run(ctx, "ms_blender_physics", kind="force_field", field_type="WIND", strength=3))
    ctx.close()


# ═══════════════════════════ Roblox (real Luau compiler + API mock) ═══════════════════════════
import luau_mock as LM  # noqa: E402
from pro_samples import SAMPLES  # noqa: E402


class RobloxCtx(T.Ctx):
    def advertised(self, s):
        return {"execute_luau"} if s == "roblox" else None

    def studio_id(self, a):
        return ("S1", "ok")

    def call(self, *a, **k):
        return {"text": ""}


if not LM.available():
    skips.append("roblox")
    print("SKIP roblox: pip install lupa")
else:
    import toolkit_roblox_pro as RP  # noqa: E402
    rctx = RobloxCtx()
    mock = LM.LuauMock(T, rctx)
    SETUP = 'local p=Instance.new("Part"); p.Name="Part"; p.Parent=workspace; p.Size=Vector3.new(4,6,1); p.Anchored=true'
    rb_pro = [n for n, sp in PRO.items() if sp["engine"] == "roblox"]
    check("roblox pro tools registered (15+)", len(rb_pro) >= 15, len(rb_pro))
    missing = [n for n in rb_pro if n not in SAMPLES]
    check("every roblox pro tool has a sample", not missing, missing)

    def rb(_tool, _setup=SETUP, **args):
        res, rt = mock.run(_tool, args, _setup)
        return res or {"ok": False, "error": "no result"}, rt

    def lua(rt, code):
        return mock.probe(rt, code)

    # 1) real Luau compiler on every program + every embedded runtime script
    comp_bad = []
    for n in rb_pro:
        d = json.loads(T.run(n, dict(SAMPLES[n], dry_run=True), rctx)["text"])
        r = L.luau_compile(d.get("code", ""))
        if r is not None and not r[0]:
            comp_bad.append((n, str(r)[:200]))
        m = re.search(r"JSONDecode\(\[=*\[(.*?)\]=*\]\)", d.get("code", ""), re.S)
        if m:
            A = json.loads(m.group(1))
            for key in ("script_source", "play_src", "car_src", "lift_src"):
                if isinstance(A.get(key), str):
                    r = L.luau_compile(A[key])
                    if r is not None and not r[0]:
                        comp_bad.append((n, key, str(r)[:200]))
    check("every roblox program and generated runtime script compiles with the real Luau compiler", not comp_bad, comp_bad)

    # 2) every sample executes in the API mock
    for n in rb_pro:
        res, _rt = rb(n, **SAMPLES[n])
        check("runs in mock: " + n, res.get("ok") is True, res)

    # 3) behaviour checks
    res, rt = rb("ms_roblox_level_blockout", rows=["#######", "#S..C.#", "#.LL..#", "#..^.G#", "#######"], cell=8, theme="dungeon")
    check("blockout merges walls into 4 rectangles and floors into few parts", res["counts"].get("Wall") == 4 and res["counts"].get("Floor", 99) <= 6 and res["spawns"] == 1 and res["coins"] == 1, res)
    tags = lua(rt, "local out = {} for _, d in ipairs(workspace.MS_Blockout:GetChildren()) do for _, t in ipairs(d._tags) do out[t] = (out[t] or 0) + 1 end end return out")
    check("blockout tags gameplay pieces", tags.get("Spawn") == 1 and tags.get("Coin") == 1 and tags.get("KillBrick") == 1 and tags.get("Goal") == 1, tags)
    res, _ = rb("ms_roblox_level_blockout", ascii="##\n#S", legend={"#": "pillar"})
    check("blockout accepts ascii + legend override", res.get("ok") and res["counts"].get("Pillar") == 3, res)
    res, _ = rb("ms_roblox_level_blockout", rows=["..S", ".."], theme="nope")
    check("blockout rejects an unknown theme", res.get("ok") is False, res)

    res, rt = rb("ms_roblox_scatter", prop="rock", center=[10, 0, 10], size=[60, 60], count=25, min_distance=8, seed=3)
    pos = lua(rt, "local out = {} for _, m in ipairs(workspace.MS_Scatter_rock:GetChildren()) do local p = m:GetPivot().Position out[#out+1] = {p.X, p.Y, p.Z} end return out")
    dmin = min((math.hypot(a[0] - b[0], a[2] - b[2]) for i, a in enumerate(pos) for b in pos[i + 1:]), default=99)
    check("scatter respects count, area and spacing", res["placed"] == len(pos) >= 15 and dmin >= 7.99 and all(-20.1 <= p[0] <= 40.1 and -20.1 <= p[2] <= 40.1 for p in pos), (res, dmin))
    low = lua(rt, "local m = workspace.MS_Scatter_rock:GetChildren()[1] local cf, s = m:GetBoundingBox() return cf.Position.Y - s.Y/2")
    check("scatter sits props on the ground (lowest point at the hit)", abs(low + 0.2) < 0.05, low)
    r1, rt1 = rb("ms_roblox_scatter", prop="tree", size=[50, 50], count=12, seed=5)
    r2, rt2 = rb("ms_roblox_scatter", prop="tree", size=[50, 50], count=12, seed=5)
    q = "local o = {} for _, m in ipairs(workspace.MS_Scatter_tree:GetChildren()) do o[#o+1] = m:GetPivot().Position.X end return o"
    check("scatter is deterministic per seed", lua(rt1, q) == lua(rt2, q))
    res, _ = rb("ms_roblox_scatter", source="Workspace.Part", size=[30, 30], count=5, min_distance=3)
    check("scatter clones a template part", res.get("ok") and res["placed"] == 5, res)

    for kind in RP.PATH_KINDS:
        res, rt = rb("ms_roblox_path_builder", points=[[0, 0, 0], [30, 0, 0], [60, 0, 20]], kind=kind, smooth=2)
        check("path " + kind, res.get("ok") and res["parts"] >= 4, res)
    res, rt = rb("ms_roblox_path_builder", points=[[0, 0, 0], [40, 0, 0]], kind="fence", spacing=4)
    check("fence: posts every `spacing` studs plus rails", res["parts"] >= 11 + 20, res)
    res, rt = rb("ms_roblox_path_builder", points=[[0, 30, 0], [40, 30, 0]], kind="path", snap_to_ground=True)
    y = lua(rt, "local m = workspace.MS_path:GetChildren()[1] return m.Position.Y")
    check("path snaps to the ground by raycast", abs(y + 0.25) < 0.01, y)

    for kind in RP.BUILDINGS:
        res, rt = rb("ms_roblox_building_generator", kind=kind)
        names = lua(rt, "local o = {} for _, p in ipairs(workspace:GetChildren()[2]:GetChildren()) do o[p.Name] = (o[p.Name] or 0) + 1 end return o")
        check("building " + kind, res.get("ok") and names.get("Window", 0) >= 3 and names.get("Lintel", 0) >= 1 and names.get("Foundation") == 1, (res, names))
    res, rt = rb("ms_roblox_building_generator", kind="house", floors=3, width=30, depth=20, rotation_y=90, position=[100, 0, 0])
    check("building honours floors/size", res["floors"] == 3 and res["size"][0] == 30 and res["size"][2] == 20, res)
    pivot = lua(rt, "local m = workspace:GetChildren()[2] local p = m.PrimaryPart.Position return {p.X, p.Y, p.Z}")
    check("building foundation lands at the requested position", abs(pivot[0] - 100) < 0.01 and abs(pivot[1] - 0.5) < 0.01, pivot)

    res, rt = rb("ms_roblox_model_tools", operation="array", targets=["Workspace.Part"], count=4, offset=[10, 0, 0], name="Pillar")
    xs = lua(rt, 'local o = {} for _, c in ipairs(workspace:GetChildren()) do if c.ClassName == "Part" then o[#o+1] = c.Position.X end end table.sort(o) return o')
    check("array count/offset", res.get("ok") and xs == [0, 10, 20, 30], (res, xs))
    res, rt = rb("ms_roblox_model_tools", operation="array", targets=["Workspace.Part"], grid=[2, 1, 2], spacing=[5, 5, 5])
    check("grid array adds 3 clones", len(res["created"]) == 3, res)
    res, rt = rb("ms_roblox_model_tools", operation="array", targets=["Workspace.Part"], radius=10, count=6)
    check("circle array adds 5 clones", len(res["created"]) == 5, res)
    res, rt = rb("ms_roblox_model_tools", SETUP + "; workspace.Part.Position = Vector3.new(5,1,2)", operation="mirror", targets=["Workspace.Part"], axis="x")
    check("mirror negates the axis", lua(rt, "return workspace.Part_Mirror.Position.X") == -5, res)
    res, rt = rb("ms_roblox_model_tools", operation="anchor", targets=["Workspace.Part"], value=False)
    check("anchor toggles", lua(rt, "return workspace.Part.Anchored") is False, res)
    res, rt = rb("ms_roblox_model_tools", operation="group", targets=["Workspace.Part"], group_name="G")
    check("group wraps in a Model", lua(rt, "return workspace.G.Part.Name") == "Part", res)
    res, rt = rb("ms_roblox_model_tools", SETUP + '; local m=Instance.new("Model"); m.Name="M"; m.Parent=workspace; for i=1,3 do local q=Instance.new("Part"); q.Name="Q"..i; q.Parent=m end', operation="weld", targets=["Workspace.M"])
    check("weld joins parts to the root", res.get("welds") == 2, res)
    res, rt = rb("ms_roblox_model_tools", SETUP + '; local q=Instance.new("Part"); q.Name="P2"; q.Size=Vector3.new(2,2,2); q.Position=Vector3.new(0,9,0); q.Parent=workspace', operation="align", targets=["Workspace.Part", "Workspace.P2"], axis="y", mode="min")
    ys = lua(rt, "return {workspace.Part.Position.Y - workspace.Part.Size.Y/2, workspace.P2.Position.Y - workspace.P2.Size.Y/2}")
    check("align min lines up bottoms", abs(ys[0] - ys[1]) < 1e-6, ys)
    res, rt = rb("ms_roblox_model_tools", operation="snap_to_ground", targets=["Workspace.Part"])
    check("snap_to_ground", abs(lua(rt, "return workspace.Part.Position.Y - workspace.Part.Size.Y/2")) < 1e-6, res)
    for op in ("stats", "pivot", "randomize", "rename", "collision_group", "unweld"):
        res, _ = rb("ms_roblox_model_tools", operation=op, targets=["Workspace.Part"], color_jitter=0.1, scale_min=0.8, name="X")
        check("model_tools " + op + " runs", res.get("ok") is True, res)

    for pr in RP.MECHS:
        res, rt = rb("ms_roblox_constraint_preset", preset=pr, target="Workspace.Part", position=[0, 6, 0])
        check("mechanism " + pr, res.get("ok") is True, res)
        if pr == "car":
            kinds = lua(rt, "local o = {} for _, d in ipairs(workspace:GetDescendants()) do o[d.ClassName] = (o[d.ClassName] or 0) + 1 end return o")
            check("car has 4 hinge wheels, a VehicleSeat and a script", kinds.get("HingeConstraint") == 4 and kinds.get("VehicleSeat") == 1 and kinds.get("Script") == 1, kinds)
    res, rt = rb("ms_roblox_constraint_preset", preset="elevator", target="Workspace.Part", distance=25)
    cnt = lua(rt, "local pc = workspace.Part.MS_elevator return {pc.UpperLimit, pc.ClassName}")
    check("elevator prismatic travel", cnt == [25, "PrismaticConstraint"], cnt)

    for k in RP.GAMEPLAY:
        res, rt = rb("ms_roblox_gameplay_kit", kind=k, position=[0, 3, 0], options={"damage": 250})
        check("gameplay kit " + k, res.get("ok") is True and res["lines"] > 5, res)
    res, rt = rb("ms_roblox_gameplay_kit", kind="kill_brick", options={"damage": 250}, targets=["Workspace.Part"], attributes={"Damage": 7})
    src = lua(rt, 'return game:GetService("ServerScriptService").MS_KillBrick.Source')
    check("gameplay options are baked into the source", "or 250" in src and "@" not in src, src[-300:])
    check("targets are tagged and given attributes", lua(rt, "return workspace.Part._tags[1]") == "KillBrick" and lua(rt, "return workspace.Part._attrs.Damage") == 7)
    res, _ = rb("ms_roblox_gameplay_kit", kind="nope")
    check("gameplay unknown kind -> error with the list", res.get("ok") is False and "kill_brick" in str(res), res)

    for pr in RP.TERRAIN_PRESETS:
        res, rt = rb("ms_roblox_terrain_generate", preset=pr, size=[96, 96], resolution=8, seed=11)
        fills = lua(rt, "return #workspace.Terrain._fills")
        check("terrain " + pr, res.get("ok") and fills == res["fill_calls"] and fills > 0, res)
    res, rt = rb("ms_roblox_terrain_generate", preset="volcano", size=[200, 200], resolution=10)
    res2, rt2 = rb("ms_roblox_terrain_generate", preset="flat", size=[200, 200], resolution=10)
    check("volcano is much taller than flat", res["height_range"][1] > res2["height_range"][1] + 60, (res["height_range"], res2["height_range"]))
    res, _ = rb("ms_roblox_terrain_generate", preset="hills", size=[8000, 8000], resolution=4)
    check("terrain refuses oversized requests", res.get("ok") is False, res)

    for pr in RP.FX:
        res, rt = rb("ms_roblox_particle_effect", preset=pr, target="Workspace.Part")
        check("particle " + pr, res.get("ok") is True and res["emitter"]["rate"] >= 0, res)
    for lk in RP.LOOKS:
        res, _ = rb("ms_roblox_post_processing", look=lk)
        check("look " + lk, res.get("ok") is True, res)

    res, rt = rb("ms_roblox_keyframe_sequence", preset="run", frames=5)
    chain = lua(rt, """local ks = game:GetService("ReplicatedStorage").MS_Anim_run
local kf = ks:GetChildren()[1]
local root = kf:GetChildren()[1]
local path = {root.Name}
local cur = root
for _, want in ipairs({"LowerTorso", "UpperTorso", "LeftUpperArm", "LeftLowerArm", "LeftHand"}) do
    local nxt = cur:FindFirstChild(want)
    if not nxt then path[#path+1] = "MISSING:" .. want break end
    path[#path+1] = nxt.Name
    cur = nxt
end
return path""")
    check("keyframe poses nest HumanoidRootPart > LowerTorso > UpperTorso > arm chain", chain == ["HumanoidRootPart", "LowerTorso", "UpperTorso", "LeftUpperArm", "LeftLowerArm", "LeftHand"], chain)
    for pr in RP.ANIM_PRESETS:
        res, _ = rb("ms_roblox_keyframe_sequence", preset=pr)
        check("animation " + pr, res.get("ok") and res["keyframes"] >= 3, res)
    res, _ = rb("ms_roblox_keyframe_sequence", keyframes=[{"time": 0, "poses": {"RightUpperArm": [0, 0, 0]}}, {"time": 1, "poses": {"RightUpperArm": [0, 0, 150]}}], name="Custom")
    check("custom keyframes", res.get("ok") and res["keyframes"] == 2, res)
    walk0, _ = RP._r15_pose("walk", 0.25)
    walk1, _ = RP._r15_pose("walk", 0.75)
    check("walk alternates legs and arms", walk0["LeftUpperLeg"][0] > 0 > walk1["LeftUpperLeg"][0] and walk0["LeftUpperArm"][0] < 0 < walk1["LeftUpperArm"][0], (walk0, walk1))

    for k in RP.TWEEN_KINDS:
        res, _ = rb("ms_roblox_tween_animation", target="Workspace.Part", kind=k, steps=[{"props": {"Position": [0, 5, 0]}, "time": 1}])
        check("tween " + k, res.get("ok") is True, res)

    res, rt = rb("ms_roblox_ui_kit", components=["main_menu", "hud", "shop", "inventory", "dialog", "toast", "settings", "leaderboard", "loading"], theme="neon", behavior_script=True)
    audit, _ = mock.run("ms_roblox_ui_audit", {}, rt=rt)
    check("ui_kit output passes ui_audit without errors", audit and audit["counts"]["error"] == 0, audit)

    res, rt = rb("ms_roblox_optimize", SETUP + '; local q=Instance.new("Part"); q.Name="Tiny"; q.Size=Vector3.new(0.2,0.2,0.2); q.Anchored=true; q.Parent=workspace; local u=Instance.new("Part"); u.Name="Loose"; u.Parent=workspace', apply=True, fixes=["anchor_static", "decor_no_collide", "no_shadow_small"])
    check("optimize applies only the requested safe fixes", res["fixed"].get("anchor_static") == 1 and res["fixed"].get("decor_no_collide") == 1 and lua(rt, "return workspace.Loose.Anchored") is True and lua(rt, "return workspace.Tiny.CanCollide") is False, res)
    res, rt = rb("ms_roblox_optimize", SETUP + '; local u=Instance.new("Part"); u.Name="Loose"; u.Parent=workspace', apply=False, fixes=["anchor_static"])
    check("optimize audit-only changes nothing", lua(rt, "return workspace.Loose.Anchored") is False and res["applied"] is False, res)


# ═══════════════════════════ Unity (real C# compiler vs Unity reference assemblies) ═══════════════════════════
import csharp_check as CS  # noqa: E402
import toolkit_unity_pro as UP  # noqa: E402
import unity_templates as UT  # noqa: E402
from pro_samples import SAMPLES as _S  # noqa: E402

un_pro = sorted(n for n, sp in PRO.items() if sp["engine"] == "unity")
check("unity gained native pro tools", counts["unity"] >= 44 and len(un_pro) >= 14, (counts, len(un_pro)))
check("every unity pro tool has a sample", all(n in _S for n in un_pro), [n for n in un_pro if n not in _S])
check("unity pro descriptions fit the registry limit", all(len(PRO[n]["description"]) <= 490 for n in un_pro), [(n, len(PRO[n]["description"])) for n in un_pro if len(PRO[n]["description"]) > 490])


class UnityCtx(T.Ctx):
    """Fake Unity MCP server: records calls, answers read_console with a canned MS_RESULT line."""
    def __init__(self, console="MS_RESULT:{\"ok\":true,\"count\":3}", errors=""):
        self.calls, self.console, self.errors = [], console, errors

    def advertised(self, server):
        return {"create_script", "refresh_unity", "execute_menu_item", "read_console", "manage_asset", "validate_script", "manage_components"} if server == "unity" else None

    def call(self, server, tool, arguments, timeout=120):
        self.calls.append((tool, arguments))
        if tool == "read_console":
            types = arguments.get("types") or []
            if arguments.get("action") == "get" and types == ["error"]:
                return {"text": self.errors}
            return {"text": self.console if arguments.get("action") == "get" else ""}
        return {"text": json.dumps({"success": True})}


def _unity_sources(tool, argsets):
    out = {}
    for i, a in enumerate(argsets):
        d = json.loads(T.run(tool, dict(a, dry_run=True), UnityCtx())["text"])
        if "code" in d:
            out["%s_%d" % (tool, i)] = d["code"].replace("namespace MultiScript.Generated", "namespace T_%s_%d" % (tool, i))
        else:
            for j, st in enumerate(d.get("plan", [])):
                c = (st.get("arguments") or {}).get("contents")
                if c:
                    out["%s_%d_%d" % (tool, i, j)] = c
    return out


VARIANTS = {n: [dict(_S[n])] for n in un_pro}
VARIANTS["ms_unity_animation_clip"] = [{"preset": p, "target": "Cube", "assign": True} for p in UP.ANIM_PRESETS if p != "custom"] + [{"preset": "custom", "curves": [{"type": "Transform", "property": "localPosition.y", "keys": [[0, 0], [1, 2]]}], "loop": True}]
VARIANTS["ms_unity_animator_controller"] = [{"path": "Assets/A/%s.controller" % t, "template": t, "assign_to": "Hero"} for t in sorted(UP._CTRL_TEMPLATES)] + [
    {"path": "Assets/A/c.controller", "parameters": [{"name": "Speed", "type": "float"}, {"name": "Go", "type": "trigger"}], "states": [{"name": "Idle"}, {"name": "Run"}],
     "transitions": [{"from": "Idle", "to": "Run", "when": [{"param": "Speed", "mode": "greater", "value": 0.1}]}, {"from": "Any", "to": "Idle", "when": [{"param": "Go", "mode": "if"}]}]}]
VARIANTS["ms_unity_particle_effect"] = [{"preset": p} for p in sorted(UP.FX_PRESETS)]
VARIANTS["ms_unity_terrain_generate"] = [{"preset": p} for p in sorted(UP.TERRAIN_PRESETS)]
VARIANTS["ms_unity_level_blockout"] = [{"rows": ["#####", "#S.C#", "#L~G#", "#K^E#", "#####"], "theme": th} for th in sorted(UP.BLOCK_THEMES)]
VARIANTS["ms_unity_lighting_preset"] = [{"preset": p} for p in sorted(UP.LIGHT_PRESETS)] + [{"preset": "day", "hour": 17.5, "fog_density": 0.01}]
VARIANTS["ms_unity_scatter"] = [{"prop": p, "size": [60, 60]} for p in UP.SCATTER_PROPS] + [{"prefab": "Assets/Prefabs/Tree.prefab", "radius": 40, "align_to_normal": True}]
VARIANTS["ms_unity_ui_kit"] = [{"screen": sc, "theme": th} for sc, th in zip(UP.UI_SCREENS * 2, (list(UP.UI_THEMES) * 3)[:16])]
VARIANTS["ms_unity_model_tools"] = [{"action": ac, "target": "A", "targets": ["B", "C", "D"]} for ac in UP.MODEL_ACTIONS] + [{"action": "array", "target": "A", "mode": m, "count": 6} for m in ("linear", "grid", "radial")]
VARIANTS["ms_unity_navmesh"] = [{"action": ac, "target": "E", "from": [0, 0, 0], "to": [5, 0, 5]} for ac in UP.NAV_ACTIONS]
VARIANTS["ms_unity_scene_audit"] = [{}, {"fix": True}]
VARIANTS["ms_unity_path_builder"] = [{"points": [[0, 0, 0], [10, 0, 0], [20, 0, 10]], "kind": k, "smooth": 2, "snap_to_ground": True} for k in UP.PATH_KINDS]
VARIANTS["ms_unity_building_generator"] = [{"kind": k} for k in UP.BUILDINGS] + [{"kind": "house", "roof": "stepped", "door_side": "left", "lit_windows": True}]
VARIANTS["ms_unity_run_csharp"] = [{"code": "R[\"n\"] = 1;"}, {"lines": ["var g = MustFind(\"A\");", "R[\"p\"] = g.transform.position;"], "helpers": "static int Twice(int x) { return x * 2; }", "usings": ["UnityEngine.UI"]}]

srcs, plan_bad, unfilled = {}, [], []
for n in un_pro:
    if n == "ms_unity_gameplay_kit":
        continue
    for a in VARIANTS[n]:
        r = json.loads(T.run(n, dict(a, dry_run=True), UnityCtx())["text"])
        if not r.get("dryRun") or [s["tool"] for s in r["plan"]] != ["create_script", "refresh_unity", "execute_menu_item", "read_console"]:
            plan_bad.append((n, a, str(r)[:200]))
        code = r.get("code", "")
        if "@@" in code or not UP._balanced(code) or "MS_RESULT" not in code:
            unfilled.append((n, a))
    srcs.update(_unity_sources(n, VARIANTS[n]))
check("every unity C# task dry-run returns the 4-step plan", not plan_bad, plan_bad[:3])
check("generated C# is balanced with no unfilled placeholders", not unfilled, unfilled[:3])
check("unity C# variants generated", len(srcs) >= 120, len(srcs))

kit_args = [{"kinds": list(UT.KINDS)}] + [{"kind": k} for k in UT.KINDS]
kit_src = _unity_sources("ms_unity_gameplay_kit", kit_args)
check("gameplay kit writes MSCore plus one file per class", len(_unity_sources("ms_unity_gameplay_kit", [{"kinds": list(UT.KINDS)}])) == 1 + sum(len(v[0]) for v in UT.KINDS.values()), len(kit_src))

if not CS.available():
    skips.append("unity-compile")
    print("SKIP unity compile: .NET SDK + Unity reference DLLs not installed (set MS_DOTNET / MS_UNITY_REFS)")
else:
    ok, errs = CS.compile_sources(srcs)
    check("ALL %d generated editor C# programs compile against the real UnityEngine/UnityEditor assemblies" % len(srcs), ok, errs[:8])
    one_kit = {k: v for k, v in _unity_sources("ms_unity_gameplay_kit", [{"kinds": list(UT.KINDS)}]).items()}
    ok, errs = CS.compile_sources(one_kit)
    check("all gameplay scripts compile (old Input Manager)", ok, errs[:8])
    stub = (ROOT / "tests" / "support" / "unity_input_stub.cs").read_text(encoding="utf-8")
    ok, errs = CS.compile_sources(dict(one_kit, stub=stub), extra_defines=("ENABLE_INPUT_SYSTEM",))
    check("all gameplay scripts compile (new Input System branch)", ok, errs[:8])
    # a deliberately wrong program must fail, otherwise the checker proves nothing
    bad_ok, bad_errs = CS.compile_sources({"bad": UP.csharp_task("var x = DoesNotExist();", "bad")})
    check("compile checker rejects invalid C#", bad_ok is False and bad_errs)

# end-to-end through the fake MCP server
ctx = UnityCtx()
res = run(ctx, "ms_unity_scatter", prop="tree", count=5)
names = [c[0] for c in ctx.calls]
check("run_cs: write -> refresh -> execute -> read -> delete", res.get("ok") is True and res.get("count") == 3 and names[:2] == ["read_console", "create_script"] and "execute_menu_item" in names and names[-2:] == ["manage_asset", "refresh_unity"], (res, names))
written = [c for c in ctx.calls if c[0] == "create_script"][0][1]
check("task script path and menu item", written["path"] == UP.TASK_PATH and "[MenuItem(\"Multi-Script/Run Task\")]" in written["contents"])
ctx = UnityCtx(errors="Assets/Editor/MultiScript/MS_Task.cs(3,4): error CS0103: The name 'x' does not exist")
res = run(ctx, "ms_unity_scatter", prop="tree")
check("compile errors are surfaced and the script is cleaned up", res.get("ok") is False and "CS0103" in res.get("compileErrors", "") and "execute_menu_item" not in [c[0] for c in ctx.calls] and any(c[0] == "manage_asset" for c in ctx.calls), res)
ctx = UnityCtx(console="nothing useful here")
res = run(ctx, "ms_unity_scene_audit")
check("missing result line is reported, not silently ok", res.get("ok") is False and "no result line" in res.get("error", ""), res)
ctx = UnityCtx(console='MS_RESULT:{"ok":false,"error":"InvalidOperationException: boom"}')
res = run(ctx, "ms_unity_navmesh", action="info")
check("task exceptions come back as ok:false with the message", res.get("ok") is False and "boom" in res.get("error", ""), res)
check("parse_marker handles noise and picks the last result", UP.parse_marker('x\nMS_RESULT:{"a":1}\nlog\nMS_RESULT:{"a":2}\n') == {"a": 2} and UP.parse_marker("none") is None)

# argument validation
for tool_, bad in (("ms_unity_ui_kit", {"screen": "nope"}), ("ms_unity_ui_kit", {"screen": "hud", "theme": "nope"}), ("ms_unity_model_tools", {"action": "nope"}),
                   ("ms_unity_path_builder", {"points": [[0, 0, 0]], "kind": "road"}), ("ms_unity_path_builder", {"points": [[0, 0, 0], [1, 0, 0]], "kind": "nope"}),
                   ("ms_unity_building_generator", {"kind": "nope"}), ("ms_unity_navmesh", {"action": "add_agent"}), ("ms_unity_gameplay_kit", {"kind": "nope"}),
                   ("ms_unity_scatter", {}), ("ms_unity_particle_effect", {"preset": "nope"})):
    res = run(UnityCtx(), tool_, **bad)
    check("rejects bad input: %s %s" % (tool_, list(bad.values())[:2]), res.get("ok") is False, res)

# string literals are escaped (no C# injection through names)
code = json.loads(T.run("ms_unity_ui_kit", {"screen": "hud", "title": 'a"b\\c\n{x}', "dry_run": True}, UnityCtx())["text"])["code"]
check("C# string literals are escaped", 'a\\"b\\\\c\\n{x}' in code, code[code.find("string title"):][:120])

# gameplay kit behaviour
res = run(UnityCtx(), "ms_unity_gameplay_kit", list=True)
check("gameplay kit lists every kind", {k["kind"] for k in res["kinds"]} == set(UT.KINDS) and len(UT.KINDS) >= 18, res.get("kinds", [])[:1])
ctx = UnityCtx()
res = run(ctx, "ms_unity_gameplay_kit", kind="health", attach_to="Player")
paths = [c[1].get("path") for c in ctx.calls if c[0] == "create_script"]
check("kit writes MSCore + MSHealth, compiles, then attaches", paths == ["Assets/Scripts/MultiScript/MSCore.cs", "Assets/Scripts/MultiScript/MSHealth.cs"] and ctx.calls[-1][0] == "manage_components" and ctx.calls[-1][1]["component_type"] == "MSHealth", (paths, ctx.calls[-1]))
ctx = UnityCtx(errors="error CS0101: The namespace '<global namespace>' already contains a definition for 'MSHealth'")
res = run(ctx, "ms_unity_gameplay_kit", kind="health")
check("kit reports clashes with existing classes", res.get("ok") is False and "folder" in res.get("hint", ""), res)
check("kit scripts use no UnityEditor APIs outside #if UNITY_EDITOR", all("UnityEditor" not in c or "#if UNITY_EDITOR" in c for v in UT.KINDS.values() for c in v[0].values()))
check("kit scripts avoid LINQ-free heavy deps (no Newtonsoft/TMP)", all("Newtonsoft" not in c and "TMPro" not in c for v in UT.KINDS.values() for c in v[0].values()))

print("\n%d failed%s" % (len(fails), (" (skipped: %s)" % ", ".join(skips)) if skips else ""))
sys.exit(1 if fails else 0)
