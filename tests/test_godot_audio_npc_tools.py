#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""ms_godot_audio_kit / ms_godot_npc_kit (6.28.2).

Always: every generated GDScript parses with the real GDScript 4 grammar (gdtoolkit, when installed) and passes structural lint
(tab indentation, balanced brackets, no unfilled placeholders); scenes are well-formed; autoloads/inputs land in project.godot;
hostile input is rejected or neutralised. With a Godot 4 binary (GODOT_BIN) the scripts are also run through `--check-only`."""
import json, os, re, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "support"), os.path.join(os.path.dirname(HERE), "runtime")]
import engine_toolkit as T  # noqa: E402

T.ensure_loaded()
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)[:400]) if (detail and not ok) else ""))
    if not ok:
        fails.append(name)


P = tempfile.mkdtemp(prefix="ms_godot_an_")
with open(os.path.join(P, "project.godot"), "w") as fh:
    fh.write('config_version=5\n\n[application]\n\nconfig/name="AN"\n')


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


def read(res):
    with open(os.path.join(P, res.replace("res://", "")), encoding="utf-8") as fh:
        return fh.read()


try:
    from gdtoolkit.parser import parser as gdparser
except Exception:  # pragma: no cover
    gdparser = None


def lint(name, src):
    probs = []
    if re.search(r"__[A-Z]+__", src):
        probs.append("placeholder left")
    if not src.startswith("extends "):
        probs.append("no extends")
    for n, line in enumerate(src.split("\n"), 1):
        lead = re.match(r"[ \t]*", line).group(0)
        if " " in lead:
            probs.append("space indent line %d" % n)
        code = line.split("#")[0] if '"' not in line.split("#")[0] else line
        if code.replace('\\"', "").count('"') % 2:
            probs.append("odd quotes line %d" % n)
    for a, b in ("()", "[]", "{}"):
        if src.count(a) != src.count(b):
            probs.append("unbalanced " + a + b)
    if gdparser is not None:
        try:
            gdparser.parse(src, gather_metadata=True)
        except Exception as e:  # noqa
            probs.append("grammar: " + str(e)[:160].replace("\n", " "))
    check("GDScript " + name, not probs, probs)


try:
    check("godot tool count includes the new kits", T.counts()["godot"] >= 40 and "ms_godot_audio_kit" in T.REGISTRY and "ms_godot_npc_kit" in T.REGISTRY, T.counts())
    for t in ("ms_godot_audio_kit", "ms_godot_npc_kit"):
        check(t + " description is under 520 chars", len(T.REGISTRY[t]["description"]) <= 520)
    print(("grammar check: gdtoolkit active" if gdparser is not None else "grammar check: gdtoolkit not installed (structural lint only)"))

    scripts = []
    # ── audio ──
    kinds = run("ms_godot_audio_kit", kind="list")["kinds"]
    check("audio kinds listed", {k["kind"] for k in kinds} == {"audio_manager", "sfx_pool", "footsteps", "ambience_zone", "music_playlist", "ui_sounds"}, kinds)
    for k in kinds:
        for m in k["modes"]:
            mode = None if m == "any" else m
            o = run("ms_godot_audio_kit", kind=k["kind"], **({"mode": mode} if mode else {}), overwrite=True,
                    options={"sounds": {"click": "res://audio/click.ogg", "hover": "audio/hover.ogg"}})
            check("audio %s/%s writes" % (k["kind"], m), "error" not in o and o.get("script"), o)
            if o.get("script"):
                lint("%s/%s" % (k["kind"], m), read(o["script"]))
                scripts.append(o["script"])
            if k["kind"] == "ambience_zone":
                sc = read(o["scene"])
                check("ambience scene %s has Area, shape and script" % m, ("Area%s" % m.upper()) in sc and "CollisionShape" in sc and "script = ExtResource" in sc, sc[:300])
    pg = open(os.path.join(P, "project.godot")).read()
    check("autoloads registered", all(a in pg for a in ("AudioManager=", "SpatialAudio=", "UiSounds=")), pg[-500:])
    am = read("res://scripts/audio/audio_manager.gd")
    check("named sounds baked into the AudioManager", '"click": "res://audio/click.ogg"' in am and '"hover": "res://audio/hover.ogg"' in am, am[:900])
    o = run("ms_godot_audio_kit", kind="audio_manager", overwrite=True, options={"sounds": {"evil": 'res://a"; OS.kill(1); "', "../x": "res://ok.ogg", "fine": "res://../../etc/passwd"}})
    am = read(o["script"])
    check("unsafe sound names/paths are dropped with warnings", "OS.kill" not in am and "passwd" not in am and len(o.get("warnings", [])) >= 2, o.get("warnings"))
    o = run("ms_godot_audio_kit", kind="footsteps")
    check("existing files are not overwritten by default", o.get("ok") is False, o)
    check("unknown kind rejected", run("ms_godot_audio_kit", kind="nope").get("ok") is False)
    check("bad mode rejected", run("ms_godot_audio_kit", kind="sfx_pool", mode="4d").get("ok") is False)
    o = run("ms_godot_audio_kit", kind="ui_sounds", overwrite=True)
    check("ui_sounds without sounds warns", any("no hover/click" in w for w in o.get("warnings", [])), o)
    o = run("ms_godot_audio_kit", kind="audio_manager", name="X", script_path="res://x/am.gd", overwrite=True, dry_run=True)
    check("dry run previews without breaking", o.get("dryRun") is True, o)

    # ── NPC ──
    nk = run("ms_godot_npc_kit", kind="list")
    check("npc kinds listed", {k["kind"] for k in nk["kinds"]} == {"npc_brain", "dialogue", "npc_spawner"} and "patrol" in nk["behaviors"], nk)
    for mode in ("3d", "2d"):
        for beh in nk["behaviors"]:
            pts = [[0, 0, 0], [5, 0, 5]] if mode == "3d" else [[0, 0], [200, 80]]
            o = run("ms_godot_npc_kit", kind="npc_brain", mode=mode, behavior=beh, waypoints=pts, name="npc_%s_%s" % (beh, mode), script_path="res://scripts/npc/brain_%s_%s.gd" % (beh, mode), overwrite=True)
            check("npc_brain %s/%s writes" % (beh, mode), "error" not in o and o.get("script") and o.get("scene"), o)
            if o.get("script"):
                src = read(o["script"])
                lint("npc_brain %s/%s" % (beh, mode), src)
                check("behavior %s baked in (%s)" % (beh, mode), 'var behavior: String = "%s"' % beh in src)
                scripts.append(o["script"])
                sc = read(o["scene"])
                check("npc scene %s/%s well-formed" % (beh, mode), sc.startswith("[gd_scene") and "CollisionShape" in sc and "Navigation" in sc and "script = ExtResource" in sc, sc[:200])
        for kind in ("dialogue", "npc_spawner"):
            o = run("ms_godot_npc_kit", kind=kind, mode=mode, overwrite=True, **({"lines": ['He said "hi"', "Line two\nnewline"], "npc_name": 'Bob"; evil'} if kind == "dialogue" else {}))
            check("%s/%s writes" % (kind, mode), "error" not in o and o.get("script"), o)
            if o.get("script"):
                src = read(o["script"])
                lint("%s/%s" % (kind, mode), src)
                scripts.append(o["script"])
                if kind == "dialogue":
                    check("dialogue strings are escaped", 'He said \\"hi\\"' in src and "evil" in src and 'Bob"; evil' not in src and "Line two newline" in src, src[:600])
    pg = open(os.path.join(P, "project.godot")).read()
    check("dialogue defines the interact input", "interact=" in pg, pg[-400:])
    src = read("res://scripts/npc/brain_patrol_3d.gd")
    check("patrol points are embedded", "Vector3(0, 0, 0), Vector3(5, 0, 5)" in src or "Vector3(0.0, 0.0, 0.0)" in src, re.findall(r"patrol_points.*", src))
    check("bad waypoint rejected", run("ms_godot_npc_kit", kind="npc_brain", waypoints=[[1, 2]], overwrite=True).get("ok") is False)
    check("non-numeric waypoint rejected", run("ms_godot_npc_kit", kind="npc_brain", waypoints=[["a", "b", "c"]], overwrite=True).get("ok") is False)
    check("unknown behavior rejected", run("ms_godot_npc_kit", kind="npc_brain", behavior="evil").get("ok") is False)
    check("unknown npc kind rejected", run("ms_godot_npc_kit", kind="nope").get("ok") is False)
    o = run("ms_godot_npc_kit", kind="npc_brain", behavior="patrol", name="warnme", script_path="res://scripts/npc/warn.gd", scene_path="res://scenes/npc/warn.tscn", overwrite=True)
    check("patrol without waypoints warns", any("patrol" in w for w in o.get("warnings", [])), o)

    # Optional: the real engine
    try:
        import live_engines as L
        if L.godot_bin():
            os.environ["GODOT_PATH"] = L.godot_bin()
            bad = L.godot_check_scripts(P, scripts)
            check("scripts pass godot --check-only", not bad, bad[:2])
        else:
            print("SKIP godot --check-only: no Godot 4 binary (set GODOT_BIN)")
    except Exception as e:  # noqa
        print("SKIP godot --check-only:", e)
finally:
    shutil.rmtree(P, ignore_errors=True)

if fails:
    print("FAILED:", len(fails))
    sys.exit(1)
print("ALL PASSED")
