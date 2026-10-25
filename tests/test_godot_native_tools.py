#!/usr/bin/env python3
"""Real headless-Godot verification of the 6.28.2 Godot builders: gameplay kit, building generator, path builder,
scatter, model tools, terrain/blockout and shaders. SKIPS (exit 0) when no Godot 4 binary is available."""
import json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "support"), os.path.join(os.path.dirname(HERE), "runtime")]
import engine_toolkit as T  # noqa: E402
import live_engines as L  # noqa: E402

T.ensure_loaded()
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)[:500]) if (detail and not ok) else ""))
    if not ok:
        fails.append(name)


if not L.godot_bin():
    print("SKIP godot: no Godot 4 binary (set GODOT_BIN)")
    sys.exit(0)

P = tempfile.mkdtemp(prefix="ms_godot_native_")
with open(os.path.join(P, "project.godot"), "w") as f:
    f.write('config_version=5\n\n[application]\n\nconfig/name="Native"\n')
os.environ["GODOT_PATH"] = L.godot_bin()


class Ctx(T.Ctx):
    def advertised(self, s):
        return set()

    def call(self, *a, **k):
        return {"text": ""}

    def project_hint(self, e):
        return P


ctx = Ctx()


def run(tool, **a):
    return json.loads(T.run(tool, a, ctx)["text"])


def validate(name, scenes):
    res = L.godot_validate(P, scenes, ready=True)
    info, errs = res
    bad = [k for k, v in info.items() if not isinstance(v, dict)]
    check(name + " load and _ready without errors", not bad and not [e for e in errs if "ERROR" in e or "Parse Error" in e], (bad, errs[:4]))
    return info


try:
    check("godot tool count", T.counts()["godot"] >= 36, T.counts())
    # ── gameplay kit ──
    kinds = run("ms_godot_gameplay_kit", kind="list")["kinds"]
    scenes, scripts = [], []
    for k in kinds:
        for m in k["modes"]:
            o = run("ms_godot_gameplay_kit", kind=k["kind"], mode=m, name="%s_%s" % (k["kind"], m), overwrite=True)
            if "error" in o:
                check("gameplay kit %s/%s" % (k["kind"], m), False, o)
                continue
            scripts.append(o["script"])
            if o.get("scene"):
                scenes.append(o["scene"])
    check("gameplay kit has >= 27 kinds", len(kinds) >= 27, len(kinds))
    validate("gameplay kit prefabs", scenes)
    bad = L.godot_check_scripts(P, scripts)
    check("gameplay kit scripts parse (--check-only)", not bad, bad[:2])
    pg = open(os.path.join(P, "project.godot")).read()
    check("gameplay kit defines inputs and autoloads", "[input]" in pg and "[autoload]" in pg, pg[-400:])
    check("gameplay kit rejects unknown kinds", run("ms_godot_gameplay_kit", kind="nope").get("ok") is False)

    # ── buildings ──
    import toolkit_godot_build as B
    sc = []
    for k in sorted(B.BUILDINGS):
        o = run("ms_godot_building_generator", kind=k, name="b_" + k, lit_windows=True)
        check("building " + k, "error" not in o, o)
        sc.append(o.get("scene"))
    for roof in B.ROOFS:
        o = run("ms_godot_building_generator", kind="house", roof=roof, name="r_" + roof, floors=3, rotation_y=30)
        sc.append(o.get("scene"))
    validate("buildings", [s for s in sc if s])

    # ── paths ──
    pts = [[0, 0, 0], [10, 0.5, 4], [20, 1, 0], [30, 0.5, -8], [40, 0, 0]]
    sc = []
    for k in B.PATH_KINDS:
        for sm, cl in ((0, False), (6, False), (4, True)):
            o = run("ms_godot_path_builder", kind=k, points=pts, smooth=sm, closed=cl, name="%s_%d_%d" % (k, sm, cl), overwrite=True)
            check("path %s smooth=%s closed=%s" % (k, sm, cl), "error" not in o, o)
            sc.append(o.get("scene"))
    validate("paths", [s for s in sc if s])
    check("path builder rejects one point", run("ms_godot_path_builder", kind="road", points=[[0, 0, 0]]).get("ok") is False)

    # ── terrain + scatter (snapped to the real heightfield) ──
    o = run("ms_godot_terrain_generate", preset="hills", size=[100, 100], resolution=48, name="Ground", overwrite=True)
    check("terrain generates", o.get("ok") is not False and "error" not in o, o)
    sc = []
    for pr in B.PROPS:
        o = run("ms_godot_scatter", prop=pr, count=25, size=[30, 30], name="sc_" + pr, seed=3, overwrite=True)
        check("scatter " + pr, "error" not in o, o)
        sc.append(o.get("scene"))
    o = run("ms_godot_scatter", prop="rock", count=40, size=[60, 60], ground_scene="res://scenes/ground.tscn", align_to_normal=True, max_slope_degrees=40, name="snapped", overwrite=True, seed=9)
    check("scatter snaps to ground", o.get("ok") is not False and (o.get("snapped") or {}).get("kept", 0) > 0, o)
    sc.append(o.get("scene"))
    validate("scatter", [s for s in sc if s])
    code = '''
var g = load("res://scenes/ground.tscn").instantiate()
g.generate()
var s = load("res://scenes/scatter/snapped.tscn").instantiate()
var worst := 0.0
for n in s.get_children():
	worst = max(worst, abs(g.height_at(n.position.x, n.position.z) - n.position.y))
R["worst"] = worst
R["count"] = s.get_child_count()
'''
    r = run("ms_godot_run_gdscript", code=code)
    res = r.get("result") or {}
    check("snapped props sit on the terrain within 8 cm", res.get("count", 0) > 0 and res.get("worst", 9) < 0.08, r)

    # ── model tools on a generated house ──
    run("ms_godot_building_generator", kind="house", name="mt_house", overwrite=True)
    scn = "res://scenes/buildings/mt_house.tscn"
    st = run("ms_godot_model_tools", scene_path=scn, action="stats")
    check("model_tools stats", st.get("ok") and st["stats"][0]["triangles"] > 0, st)
    for kw in ({"action": "array", "targets": ["Trim/Corner00"], "mode": "linear", "count": 3, "offset": [0, 0, 1]},
               {"action": "mirror", "targets": ["Trim/Corner00"], "axis": "x"},
               {"action": "align", "targets": ["Trim/Corner00", "Trim/Corner02", "Trim/Corner20"], "axis": "y", "mode": "max"},
               {"action": "distribute", "targets": ["Trim/Corner00", "Trim/Corner02", "Trim/Corner20"], "axis": "x"},
               {"action": "group", "targets": ["Trim/Corner00", "Trim/Corner02"], "name": "Pair"},
               {"action": "colliders", "targets": ["Trim"], "collider": "box"},
               {"action": "visibility_range", "targets": ["Roof"], "distances": [50]},
               {"action": "center_pivot", "targets": ["Roof"], "mode": "bottom"},
               {"action": "static", "targets": ["Walls"]}):
        o = run("ms_godot_model_tools", scene_path=scn, **kw)
        check("model_tools " + kw["action"], o.get("ok") is True, o)
    o = run("ms_godot_model_tools", scene_path=scn, action="ungroup", targets=["Trim/Pair"])
    check("model_tools ungroup", o.get("ok") is True, o)
    check("model_tools reports missing targets", run("ms_godot_model_tools", scene_path=scn, action="stats", targets=["Nope"]).get("ok") is False)
    before = run("ms_godot_model_tools", scene_path=scn, action="stats")["stats"][0]["nodes"]
    run("ms_godot_model_tools", scene_path=scn, action="array", targets=["Trim/Corner20"], mode="linear", count=2, dry_run=True)
    check("model_tools dry_run changes nothing", run("ms_godot_model_tools", scene_path=scn, action="stats")["stats"][0]["nodes"] == before)
    validate("model-tools scene", [scn])

    # ── blockout + shaders ──
    for mode in ("3d", "2d_topdown", "2d_platformer"):
        o = run("ms_godot_level_blockout", rows=["#####", "#...#", "#.P.#", "#####"], mode=mode, name="lb_" + mode, overwrite=True)
        check("blockout " + mode, "error" not in o, o)
        if o.get("scene"):
            validate("blockout " + mode, [o["scene"]])
    kinds_sh = T.REGISTRY["ms_godot_shader_create"]["inputSchema"]["properties"]["shader"]["enum"] if False else [x for x in T.REGISTRY["ms_godot_shader_create"]["inputSchema"]["properties"]["shader"]["enum"] if x != "custom"]
    mats = []
    for p in kinds_sh:
        o = run("ms_godot_shader_create", shader=p, name="sh_" + p, overwrite=True)
        check("shader " + p, "error" not in o, o)
        for key in ("material", "material_path"):
            if o.get(key):
                mats.append(o[key])
    if mats:
        info = validate("shader materials", mats)
        check("every shader material compiles", all(isinstance(v, dict) for v in info.values()), info)
finally:
    shutil.rmtree(P, ignore_errors=True)

print("\n%d failed" % len(fails))
sys.exit(1 if fails else 0)
