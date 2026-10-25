# SPDX-License-Identifier: GPL-3.0-or-later
"""ms_godot_gameplay_kit: ready-made, compile-checked GDScript gameplay systems (2D + 3D) with prefab scenes,
input actions and autoload registration. Templates live in godot_templates.py."""
import os

from engine_toolkit import tool, as_list, as_dict, boolean, ToolkitError
from toolkit_godot import _proj, _abs, _res, _read, _write, G, Scene, parse_project, set_setting, _key_event
from toolkit_godot_pro import SB, Out, OVERWRITE, INTO, PARENT, f, V2, V3, C, Cx, hex_rgba, ident, norm_res, target_scene, set_raw
from toolkit_godot_world import _DEFAULT_KEYS
import godot_templates as GT

KINDS = sorted(GT.T)
_PLAYER_KINDS = ("player_third_person", "player_first_person", "player_platformer", "player_topdown")


def _mats(sb, color, emission=None, alpha=None):
    col = hex_rgba(color)
    lines = ["albedo_color = " + Cx(col[:3] + ((alpha,) if alpha is not None else (col[3],)))]
    if alpha is not None and alpha < 1:
        lines.append("transparency = 1")
    if emission:
        lines += ["emission_enabled = true", "emission = " + C(emission)]
    return sb.sub("StandardMaterial3D", lines=lines, hint="mat")


def _poly(sb, parent, color, w, h, name="Visual", shape="rect", props=None):
    if shape == "diamond":
        pts = (0, -h / 2, w / 2, 0, 0, h / 2, -w / 2, 0)
    else:
        pts = (-w / 2, -h / 2, w / 2, -h / 2, w / 2, h / 2, -w / 2, h / 2)
    p = {"color": Cx(hex_rgba(color)), "polygon": "PackedVector2Array(%s)" % ", ".join(f(x) for x in pts)}
    p.update(props or {})
    return sb.node(name, "Polygon2D", parent, p)


def _shape3(sb, parent, kind, **kw):
    if kind == "capsule":
        sid = sb.sub("CapsuleShape3D", lines=["radius = " + f(kw.get("r", 0.4)), "height = " + f(kw.get("h", 1.8))], hint="cap")
    elif kind == "sphere":
        sid = sb.sub("SphereShape3D", lines=["radius = " + f(kw.get("r", 0.5))], hint="sph")
    else:
        sid = sb.sub("BoxShape3D", lines=["size = " + V3(*kw.get("size", (1, 1, 1)))], hint="box")
    return sb.node(kw.get("name", "Shape"), "CollisionShape3D", parent, {"shape": 'SubResource("%s")' % sid, **({"position": V3(*kw["pos"])} if kw.get("pos") else {})})


def _shape2(sb, parent, kind, **kw):
    if kind == "capsule":
        sid = sb.sub("CapsuleShape2D", lines=["radius = " + f(kw.get("r", 14)), "height = " + f(kw.get("h", 36))], hint="cap")
    elif kind == "circle":
        sid = sb.sub("CircleShape2D", lines=["radius = " + f(kw.get("r", 12))], hint="circ")
    else:
        sid = sb.sub("RectangleShape2D", lines=["size = " + V2(*kw.get("size", (32, 32)))], hint="rect")
    return sb.node(kw.get("name", "Shape"), "CollisionShape2D", parent, {"shape": 'SubResource("%s")' % sid, **({"position": V2(*kw["pos"])} if kw.get("pos") else {})})


def _mesh_node(sb, parent, mesh_type, mesh_lines, mat, name="Mesh", pos=None, rot=None):
    mid = sb.sub(mesh_type, lines=['material = SubResource("%s")' % mat] + mesh_lines, hint="mesh")
    props = {"mesh": 'SubResource("%s")' % mid}
    if pos:
        props["position"] = V3(*pos)
    if rot:
        props["rotation"] = V3(*rot)
    return sb.node(name, "MeshInstance3D", parent, props)


def build_prefab(kind, d3, name, script, color):
    """Return an SB (scene) for kinds that have a natural prefab, else None."""
    root_type = {
        "player_third_person": "CharacterBody3D", "player_first_person": "CharacterBody3D", "player_platformer": "CharacterBody2D", "player_topdown": "CharacterBody2D",
        "enemy_ai": "CharacterBody3D" if d3 else "CharacterBody2D", "collectible": "Area3D" if d3 else "Area2D", "checkpoint": "Area3D" if d3 else "Area2D",
        "kill_zone": "Area3D" if d3 else "Area2D", "moving_platform": "AnimatableBody3D" if d3 else "AnimatableBody2D", "projectile": "Area3D" if d3 else "Area2D",
        "door": "AnimatableBody3D" if d3 else "AnimatableBody2D", "interactable": "Area3D" if d3 else "Area2D", "spawner": "Node3D" if d3 else "Node2D",
        "level_rules": "Node", "camera_follow": "Camera3D" if d3 else "Camera2D", "day_night_cycle": "DirectionalLight3D" if d3 else "CanvasModulate",
        "floating_text": "Label3D" if d3 else "Label"}.get(kind)
    if not root_type:
        return None
    sb = SB(name, root_type, "gk_" + kind)
    sb.nodes[0]["body"].append('script = ExtResource("%s")' % sb.ext_res(script, "Script"))
    r = sb.root
    col = color
    if kind == "player_third_person":
        _shape3(sb, ".", "capsule", r=0.4, h=1.8, pos=(0, 0.9, 0))
        v = sb.node("Visual", "Node3D", ".")
        _mesh_node(sb, "Visual", "CapsuleMesh", ["radius = 0.4", "height = 1.8"], _mats(sb, col), "Body", pos=(0, 0.9, 0))
        _mesh_node(sb, "Visual", "BoxMesh", ["size = Vector3(0.3, 0.2, 0.3)"], _mats(sb, "#ffffff"), "Nose", pos=(0, 1.4, -0.4))
        sb.node("CameraRig", "Node3D", ".", {"position": V3(0, 1.4, 0)})
        sb.node("SpringArm3D", "SpringArm3D", "CameraRig", {"spring_length": "5.0", "margin": "0.3"})
        sb.node("Camera3D", "Camera3D", "CameraRig/SpringArm3D", {"current": "true"})
    elif kind == "player_first_person":
        _shape3(sb, ".", "capsule", r=0.4, h=1.8, pos=(0, 0.9, 0))
        sb.node("Head", "Node3D", ".", {"position": V3(0, 0.7, 0)})
        sb.node("Camera3D", "Camera3D", "Head", {"current": "true", "position": V3(0, 0.9, 0)})
    elif kind == "player_platformer":
        _shape2(sb, ".", "capsule", r=14, h=36)
        _poly(sb, ".", col, 28, 36)
        sb.node("Camera2D", "Camera2D", ".", {"position_smoothing_enabled": "true", "position_smoothing_speed": "8.0"})
    elif kind == "player_topdown":
        _shape2(sb, ".", "circle", r=12)
        _poly(sb, ".", col, 26, 26)
        sb.node("Camera2D", "Camera2D", ".", {"position_smoothing_enabled": "true"})
    elif kind == "enemy_ai":
        if d3:
            _shape3(sb, ".", "capsule", r=0.4, h=1.8, pos=(0, 0.9, 0))
            _mesh_node(sb, ".", "CapsuleMesh", ["radius = 0.4", "height = 1.8"], _mats(sb, "#e04848"), "Body", pos=(0, 0.9, 0))
            sb.node("NavigationAgent3D", "NavigationAgent3D", ".", {"path_desired_distance": "0.6", "target_desired_distance": "0.8"})
        else:
            _shape2(sb, ".", "capsule", r=13, h=32)
            _poly(sb, ".", "#e04848", 26, 32)
    elif kind == "collectible":
        if d3:
            _shape3(sb, ".", "sphere", r=0.6)
            _mesh_node(sb, ".", "CylinderMesh", ["top_radius = 0.35", "bottom_radius = 0.35", "height = 0.08"], _mats(sb, "#ffd23f", emission="#ffb000"), "Mesh", rot=(1.5708, 0, 0))
        else:
            _shape2(sb, ".", "circle", r=14)
            _poly(sb, ".", "#ffd23f", 22, 22, shape="diamond")
    elif kind == "checkpoint":
        if d3:
            _shape3(sb, ".", "box", size=(2, 2.4, 2), pos=(0, 1.2, 0))
            _mesh_node(sb, ".", "CylinderMesh", ["top_radius = 0.9", "bottom_radius = 0.9", "height = 0.15"], _mats(sb, "#4dd0ff", emission="#1a80c0", alpha=0.6), "Pad", pos=(0, 0.08, 0))
        else:
            _shape2(sb, ".", "rect", size=(40, 56))
            _poly(sb, ".", "#4dd0ff", 40, 56, props={"color": Cx(hex_rgba("#4dd0ff")[:3] + (0.5,))})
    elif kind == "kill_zone":
        if d3:
            _shape3(sb, ".", "box", size=(20, 1, 20))
        else:
            _shape2(sb, ".", "rect", size=(640, 32))
    elif kind == "moving_platform":
        if d3:
            _shape3(sb, ".", "box", size=(4, 0.4, 4))
            _mesh_node(sb, ".", "BoxMesh", ["size = Vector3(4, 0.4, 4)"], _mats(sb, "#d9b45a"), "Mesh")
        else:
            _shape2(sb, ".", "rect", size=(128, 20))
            _poly(sb, ".", "#d9b45a", 128, 20)
    elif kind == "projectile":
        if d3:
            _shape3(sb, ".", "sphere", r=0.15)
            _mesh_node(sb, ".", "SphereMesh", ["radius = 0.12", "height = 0.24"], _mats(sb, "#ffcc33", emission="#ff8800"), "Mesh")
        else:
            _shape2(sb, ".", "circle", r=5)
            _poly(sb, ".", "#ffcc33", 12, 6)
    elif kind == "door":
        if d3:
            _shape3(sb, ".", "box", size=(2, 3, 0.3), pos=(0, 1.5, 0))
            _mesh_node(sb, ".", "BoxMesh", ["size = Vector3(2, 3, 0.3)"], _mats(sb, "#8a5a2b"), "Mesh", pos=(0, 1.5, 0))
            a = sb.node("InteractArea", "Area3D", ".")
            _shape3(sb, "InteractArea", "box", size=(4, 3, 3.5), pos=(0, 1.5, 0))
        else:
            _shape2(sb, ".", "rect", size=(24, 96))
            _poly(sb, ".", "#8a5a2b", 24, 96)
            sb.node("InteractArea", "Area2D", ".")
            _shape2(sb, "InteractArea", "rect", size=(96, 110))
    elif kind == "interactable":
        if d3:
            _shape3(sb, ".", "box", size=(2.5, 2, 2.5), pos=(0, 1, 0))
            sb.node("Prompt", "Label3D", ".", {"text": '"Press E to interact"', "position": V3(0, 2.2, 0), "billboard": "1", "no_depth_test": "true", "fixed_size": "true", "pixel_size": "0.0012"})
        else:
            _shape2(sb, ".", "rect", size=(96, 80))
            sb.node("Prompt", "Label", ".", {"text": '"Press E to interact"', "position": V2(-60, -70)})
    elif kind == "floating_text":
        sb.nodes[0]["body"].append("text = \"0\"")
    return sb


def define_inputs(proj_text, names, args):
    """Add missing default input actions to project.godot text. Returns (new_text, added)."""
    entries, _l = parse_project(proj_text)
    have = {e["key"] for e in entries if e["section"] == "input"}
    added = []
    for n in names:
        if n in have or n not in _DEFAULT_KEYS:
            continue
        events = ", ".join(_key_event(k) for k in _DEFAULT_KEYS[n])
        proj_text = set_setting(proj_text, "input", n, '{\n"deadzone": 0.5,\n"events": [%s]\n}' % events)
        added.append(n)
    return proj_text, added


_AUTOLOAD_NAME = {"game_manager": "GameManager", "save_system": "SaveSystem", "scene_transition": "SceneTransition"}
_COLORS = {"player_third_person": "#4a90e2", "player_first_person": "#4a90e2", "player_platformer": "#4a90e2", "player_topdown": "#4a90e2"}


@tool(G, "ms_godot_gameplay_kit",
      "Install a ready-made gameplay system as a compile-checked GDScript + prefab scene (2D or 3D): player controllers (third/first person, platformer, topdown), cameras, health, hitbox/hurtbox, "
      "pickups, checkpoints, projectiles, enemies, spawners, doors, inventory, state machine, day/night, and autoloads (game_manager, save_system, scene_transition). Defines missing inputs; kind=list shows all.",
      {"kind": {"type": "string", "enum": KINDS + ["list"]}, "mode": {"type": "string", "enum": ["3d", "2d"]}, "name": {"type": "string"}, "color": {"type": ["string", "array"], "description": "Body color for prefabs."},
       "script_path": {"type": "string"}, "scene_path": {"type": "string"}, "with_scene": {"type": "boolean", "description": "Create the prefab scene (default true when the kind has one)."},
       "attach_to": {"type": "object", "description": "{scene_path, node}: assign the script to a node of an existing scene instead of creating a prefab."},
       "register_autoload": {"type": "boolean"}, "define_inputs": {"type": "boolean"}, "into_scene": INTO, "parent": PARENT, "overwrite": OVERWRITE}, [], writes=True, local=True)
def gameplay_kit(args, ctx):
    kind = str(args.get("kind") or "list").lower()
    if kind == "list":
        return {"kinds": [{"kind": k, "modes": list(v["modes"]), "summary": v["summary"], "inputs": v["inputs"], "autoload": v["autoload"]} for k, v in sorted(GT.T.items())]}
    if kind not in GT.T:
        raise ToolkitError("unknown kind '%s'" % kind, "Kinds: " + ", ".join(KINDS))
    t = GT.T[kind]
    mode = str(args.get("mode") or t["modes"][0]).lower()
    if mode not in ("3d", "2d") or mode not in t["modes"]:
        raise ToolkitError("%s supports mode %s" % (kind, " / ".join(t["modes"])))
    d3 = mode == "3d"
    p = _proj(args, ctx)
    name = ident(args.get("name") or kind.title().replace("_", ""), "Kit")
    out = Out(p, args)
    same = GT.render_kind(kind, True) == GT.render_kind(kind, False) if len(t["modes"]) > 1 else True
    suffix = "" if d3 or same else "_2d"
    spath = out.put(norm_res(args.get("script_path") or "res://scripts/%s%s.gd" % (kind, suffix), ".gd", "res://scripts"), GT.render_kind(kind, d3), "GDScript")
    for fname, src in t["files"].items():
        out.put(os.path.dirname(spath) + "/" + fname, src, "GDScript")
    scene = None
    top = None
    attached = None
    at = as_dict(args.get("attach_to"))
    if at:
        sp = _abs(p, norm_res(at.get("scene_path") or "", ".tscn"))
        if not os.path.isfile(sp):
            raise ToolkitError("scene not found: %s" % at.get("scene_path"))
        sc = Scene(_read(sp))
        node = sc.find(str(at.get("node") or "."))
        set_raw(sc, node, "script", 'ExtResource("%s")' % sc.ext_id(spath, "Script"))
        out.put(_res(p, sp), sc.text().rstrip("\n") + "\n", "scene (script attached)", allow_overwrite=True)
        attached = {"scene": _res(p, sp), "node": sc.key(node)}
    elif boolean(args.get("with_scene"), True) and not t["autoload"]:
        sb = build_prefab(kind, d3, name, spath, args.get("color") or _COLORS.get(kind, "#4a90e2"))
        if sb is not None:
            scene, top = target_scene(p, args, sb, "res://scenes/%s.tscn" % name.lower(), out)
    added_inputs, registered = [], None
    pj = os.path.join(p, "project.godot")
    if os.path.isfile(pj):
        text = _read(pj)
        new = text
        if boolean(args.get("define_inputs"), True) and t["inputs"]:
            new, added_inputs = define_inputs(new, t["inputs"], args)
        if t["autoload"] and boolean(args.get("register_autoload"), True):
            an = _AUTOLOAD_NAME.get(kind, name)
            new = set_setting(new, "autoload", an, '"*%s"' % spath)
            registered = an
        if new != text:
            _write(pj, new, args)
    nxt = {True: "Instance the scene (or attach the script) and press Play.", False: ""}[scene is not None]
    if t["autoload"]:
        nxt = "Autoload %s is registered: call it from any script (e.g. %s.%s)." % (registered, registered, {"game_manager": "add_score(1)", "save_system": "save_game(1)", "scene_transition": 'change_scene("res://scenes/next.tscn")'}[kind])
    return out.done(kind=kind, mode=mode, script=spath, scene=scene, root=top, attached=attached, inputs_defined=added_inputs, autoload=registered, groups=t["groups"], summary=t["summary"], hint=nxt or "Attach the script to a node (attach_to) or add it as a child.")
