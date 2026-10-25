# SPDX-License-Identifier: GPL-3.0-or-later
"""Godot "world" tools: ASCII level blockouts (3D + 2D), procedural terrain and a project/scene audit.
Everything is written as plain .tscn/.gd text and checked by a real headless Godot in the test-suite."""
import os
import re

from engine_toolkit import tool, as_list, as_dict, num, boolean, ToolkitError
from toolkit_godot import _proj, _abs, _res, _read, _write, G, Scene, parse_project
from toolkit_godot_pro import (SB, Out, OVERWRITE, INTO, PARENT, f, V2, V3, C, Cx, hex_rgba, gstr, ident, fill, norm_res, target_scene, set_raw)

# ───────────────────────── ASCII level blockout ─────────────────────────
THEMES = {
    "grassland": {"floor": "#5aa64b", "wall": "#8a8f98", "accent": "#d9b45a", "lava": "#ff4a1c", "water": "#3a8fd8", "sky": "#8fb8e8"},
    "dungeon": {"floor": "#4a4a52", "wall": "#2e2e36", "accent": "#8a5a2b", "lava": "#ff4a1c", "water": "#2a5a78", "sky": "#0c0c12"},
    "sci_fi": {"floor": "#2b3547", "wall": "#4d5d7a", "accent": "#3df2ff", "lava": "#ff2d6f", "water": "#1b6aa8", "sky": "#0a1020"},
    "desert": {"floor": "#d9bf80", "wall": "#b58b55", "accent": "#8a5a2b", "lava": "#d94a1c", "water": "#4aa8c8", "sky": "#e8cfa0"},
    "candy": {"floor": "#ffb3d9", "wall": "#a0e8ff", "accent": "#ffe066", "lava": "#ff4d6d", "water": "#9be3ff", "sky": "#ffe8f4"},
    "snow": {"floor": "#eaf2ff", "wall": "#9fb7d4", "accent": "#6b4a2b", "lava": "#ff6a3d", "water": "#7ac4f0", "sky": "#cfe0f5"},
}
LEGEND = {"#": "wall", ".": "floor", "+": "floor", "S": "spawn", "C": "coin", "L": "lava", "~": "water", "G": "goal", "D": "door", "P": "pillar", "T": "tree", "B": "crate",
          "K": "checkpoint", "E": "enemy", "^": "stairs", "=": "platform"}
KINDS = sorted(set(LEGEND.values()))
MODES = ("3d", "2d_topdown", "2d_platformer")
_FLOORED = {"floor", "spawn", "coin", "goal", "door", "pillar", "tree", "crate", "checkpoint", "enemy", "stairs"}


def merge_rects(cells):
    """Greedy-merge a set of (col,row) cells into the fewest rectangles -> [(col,row,w,h)]."""
    left, out = set(cells), []
    for (c, r) in sorted(cells, key=lambda t: (t[1], t[0])):
        if (c, r) not in left:
            continue
        w = 1
        while (c + w, r) in left:
            w += 1
        h = 1
        while all((c + i, r + h) in left for i in range(w)):
            h += 1
        for j in range(h):
            for i in range(w):
                left.discard((c + i, r + j))
        out.append((c, r, w, h))
    return out


class Blockout:
    def __init__(self, sb, theme, mode, cell, wall_h, floor_t):
        self.sb, self.th, self.mode, self.cell, self.wall_h, self.floor_t = sb, THEMES[theme], mode, cell, wall_h, floor_t
        self._mats, self._shapes, self._meshes = {}, {}, {}
        self.groups = {}

    def mat(self, key, color, emission=None, alpha=None, rough=0.85):
        if key not in self._mats:
            col = hex_rgba(color)
            if alpha is not None:
                col = col[:3] + (alpha,)
            props = ["albedo_color = " + Cx(col), "roughness = " + f(rough)]
            if alpha is not None and alpha < 1:
                props.append("transparency = 1")
            if emission:
                props += ["emission_enabled = true", "emission = " + C(emission), "emission_energy_multiplier = 1.4"]
            self._mats[key] = self.sb.sub("StandardMaterial3D", lines=props, hint="mat_" + key)
        return self._mats[key]

    def box_mesh(self, size, mat):
        k = ("box", tuple(round(x, 4) for x in size), mat)
        if k not in self._meshes:
            self._meshes[k] = self.sb.sub("BoxMesh", lines=["material = SubResource(\"%s\")" % mat, "size = " + V3(*size)], hint="box")
        return self._meshes[k]

    def box_shape(self, size):
        k = tuple(round(x, 4) for x in size)
        if k not in self._shapes:
            self._shapes[k] = self.sb.sub("BoxShape3D", lines=["size = " + V3(*size)], hint="shape")
        return self._shapes[k]

    def body3(self, name, parent, pos, size, mat, kind="StaticBody3D", groups=None, emission=None):
        k = self.sb.node(name, kind, parent, {"position": V3(*pos)}, groups=groups)
        self.sb.node("Mesh", "MeshInstance3D", k, {"mesh": 'SubResource("%s")' % self.box_mesh(size, mat)})
        self.sb.node("Shape", "CollisionShape3D", k, {"shape": 'SubResource("%s")' % self.box_shape(size)})
        return k

    def area3(self, name, parent, pos, size, mat, groups, visible=True):
        k = self.sb.node(name, "Area3D", parent, {"position": V3(*pos)}, groups=groups)
        if visible:
            self.sb.node("Mesh", "MeshInstance3D", k, {"mesh": 'SubResource("%s")' % self.box_mesh(size, mat)})
        self.sb.node("Shape", "CollisionShape3D", k, {"shape": 'SubResource("%s")' % self.box_shape(size)})
        return k


def _parse_rows(args):
    rows = [str(r) for r in as_list(args.get("rows"))]
    if not rows and args.get("ascii"):
        rows = str(args["ascii"]).strip("\n").split("\n")
    rows = [r.rstrip("\r") for r in rows]
    if not rows or not any(r.strip() for r in rows):
        raise ToolkitError("give `rows` (array of strings) or `ascii`", 'Example: ["#####","#S.C#","#####"]')
    if len(rows) > 150 or max(len(r) for r in rows) > 150:
        raise ToolkitError("map too large (max 150x150 cells)")
    return rows


def _grid(rows, leg):
    w = max(len(r) for r in rows)
    grid = {}
    for r, line in enumerate(rows):
        for c, ch in enumerate(line.ljust(w)):
            kind = leg.get(ch)
            if kind:
                grid[(c, r)] = kind
    return grid, w, len(rows)


def build_blockout_3d(rows, leg, theme, cell, wall_h, floor_t, name, origin, lighting):
    grid, W, H = _grid(rows, leg)
    sb = SB(name, "Node3D", "bo3_" + name)
    B = Blockout(sb, theme, "3d", cell, wall_h, floor_t)
    th = THEMES[theme]
    m_floor, m_wall, m_acc = B.mat("floor", th["floor"]), B.mat("wall", th["wall"]), B.mat("accent", th["accent"])
    m_lava = B.mat("lava", th["lava"], emission=th["lava"])
    m_water = B.mat("water", th["water"], alpha=0.55, rough=0.1)
    ox, oy, oz = origin

    def cpos(c, r, y=0.0):
        return (ox + (c + 0.5) * cell, oy + y, oz + (r + 0.5) * cell)

    def rect_geo(rc, y0, y1):
        c, r, w, h = rc
        return ((ox + (c + w / 2.0) * cell, oy + (y0 + y1) / 2.0, oz + (r + h / 2.0) * cell), (w * cell, y1 - y0, h * cell))

    counts = {}

    def bump(k, n=1):
        counts[k] = counts.get(k, 0) + n

    for grp in ("Floors", "Walls", "Hazards", "Props", "Markers"):
        sb.node(grp, "Node3D", ".")
    floor_cells = {k for k, v in grid.items() if v in _FLOORED or v == "platform"}
    for i, rc in enumerate(merge_rects({k for k, v in grid.items() if v in _FLOORED})):
        pos, size = rect_geo(rc, -floor_t, 0)
        B.body3("Floor%d" % i, "Floors", pos, size, m_floor, groups=["floor"])
        bump("floor")
    for i, rc in enumerate(merge_rects({k for k, v in grid.items() if v == "wall"})):
        pos, size = rect_geo(rc, -floor_t, wall_h)
        B.body3("Wall%d" % i, "Walls", pos, size, m_wall, groups=["wall"])
        bump("wall")
    for i, rc in enumerate(merge_rects({k for k, v in grid.items() if v == "platform"})):
        pos, size = rect_geo(rc, wall_h * 0.4 - 0.4, wall_h * 0.4)
        B.body3("Platform%d" % i, "Walls", pos, size, m_acc, groups=["platform"])
        bump("platform")
    for i, rc in enumerate(merge_rects({k for k, v in grid.items() if v == "lava"})):
        pos, size = rect_geo(rc, -0.4, 0.0)
        B.area3("Lava%d" % i, "Hazards", pos, size, m_lava, ["killzone", "hazard"])
        bump("lava")
    for i, rc in enumerate(merge_rects({k for k, v in grid.items() if v == "water"})):
        pos, size = rect_geo(rc, -wall_h * 0.4, -0.15)
        B.area3("Water%d" % i, "Hazards", pos, size, m_water, ["water"])
        bump("water")
    sph = {}

    def sphere(kind_key, radius, mat):
        if kind_key not in sph:
            sph[kind_key] = sb.sub("SphereMesh", lines=['material = SubResource("%s")' % mat, "radius = " + f(radius), "height = " + f(radius * 2)], hint="sph_" + kind_key)
        return sph[kind_key]

    shapes_s = {}

    def sphere_shape(radius):
        if radius not in shapes_s:
            shapes_s[radius] = sb.sub("SphereShape3D", lines=["radius = " + f(radius)], hint="sshape")
        return shapes_s[radius]

    m_coin = B.mat("coin", "#ffd23f", emission="#ffb000")
    m_goal = B.mat("goal", "#7dff99", emission="#33cc55", alpha=0.45)
    m_check = B.mat("check", "#4dd0ff", emission="#1a80c0", alpha=0.6)
    m_enemy = B.mat("enemy", "#ff3d3d", emission="#a00d0d")
    m_trunk, m_leaf = B.mat("trunk", "#6b4a2b"), B.mat("leaf", "#40902f")
    m_door = B.mat("door", th["accent"], emission=th["accent"], alpha=0.7)
    cyl = {}
    spawns = 0
    for (c, r), kind in sorted(grid.items(), key=lambda t: (t[0][1], t[0][0])):
        n = counts.get(kind, 0)
        if kind == "spawn":
            k = sb.node("PlayerSpawn" if spawns == 0 else "PlayerSpawn%d" % (spawns + 1), "Marker3D", "Markers", {"position": V3(*cpos(c, r, 1.0))}, groups=["player_spawn"])
            sb.node("Gizmo", "MeshInstance3D", k, {"mesh": 'SubResource("%s")' % sphere("spawn", 0.3, B.mat("spawn", "#ffffff", emission="#ffffff", alpha=0.35))})
            spawns += 1
            bump("spawn")
        elif kind == "coin":
            k = sb.node("Coin%d" % n, "Area3D", "Props", {"position": V3(*cpos(c, r, 1.0))}, groups=["coin"])
            sb.node("Mesh", "MeshInstance3D", k, {"mesh": 'SubResource("%s")' % sphere("coin", 0.35, m_coin)})
            sb.node("Shape", "CollisionShape3D", k, {"shape": 'SubResource("%s")' % sphere_shape(0.6)})
            bump("coin")
        elif kind == "goal":
            B.area3("Goal%d" % n, "Props", cpos(c, r, wall_h * 0.3), (cell, wall_h * 0.6, cell), m_goal, ["goal"])
            bump("goal")
        elif kind == "checkpoint":
            B.area3("Checkpoint%d" % n, "Props", cpos(c, r, 0.4), (cell * 0.8, 0.8, cell * 0.8), m_check, ["checkpoint"])
            bump("checkpoint")
        elif kind == "door":
            B.area3("Door%d" % n, "Props", cpos(c, r, wall_h * 0.4), (cell * 0.9, wall_h * 0.8, cell * 0.25), m_door, ["door"])
            bump("door")
        elif kind == "enemy":
            k = sb.node("EnemySpawn%d" % n, "Marker3D", "Markers", {"position": V3(*cpos(c, r, 1.0))}, groups=["enemy_spawn"])
            sb.node("Gizmo", "MeshInstance3D", k, {"mesh": 'SubResource("%s")' % sphere("enemy", 0.45, m_enemy)})
            bump("enemy")
        elif kind == "crate":
            B.body3("Crate%d" % n, "Props", cpos(c, r, cell * 0.35), (cell * 0.7,) * 3, m_acc, groups=["crate"])
            bump("crate")
        elif kind == "pillar":
            key = ("pillar", wall_h)
            if key not in cyl:
                cyl[key] = (sb.sub("CylinderMesh", lines=['material = SubResource("%s")' % m_wall, "top_radius = " + f(cell * 0.25), "bottom_radius = " + f(cell * 0.25), "height = " + f(wall_h)], hint="pillar"),
                            sb.sub("CylinderShape3D", lines=["radius = " + f(cell * 0.25), "height = " + f(wall_h)], hint="pillarshape"))
            k = sb.node("Pillar%d" % n, "StaticBody3D", "Props", {"position": V3(*cpos(c, r, wall_h / 2.0))}, groups=["pillar"])
            sb.node("Mesh", "MeshInstance3D", k, {"mesh": 'SubResource("%s")' % cyl[key][0]})
            sb.node("Shape", "CollisionShape3D", k, {"shape": 'SubResource("%s")' % cyl[key][1]})
            bump("pillar")
        elif kind == "tree":
            if "trunk" not in cyl:
                cyl["trunk"] = (sb.sub("CylinderMesh", lines=['material = SubResource("%s")' % m_trunk, "top_radius = " + f(cell * 0.12), "bottom_radius = " + f(cell * 0.16), "height = " + f(cell * 0.9)], hint="trunk"),
                                sb.sub("CylinderShape3D", lines=["radius = " + f(cell * 0.16), "height = " + f(cell * 0.9)], hint="trunkshape"),
                                sb.sub("SphereMesh", lines=['material = SubResource("%s")' % m_leaf, "radius = " + f(cell * 0.65), "height = " + f(cell * 1.3)], hint="leaves"))
            k = sb.node("Tree%d" % n, "StaticBody3D", "Props", {"position": V3(*cpos(c, r, cell * 0.45))}, groups=["tree"])
            sb.node("Trunk", "MeshInstance3D", k, {"mesh": 'SubResource("%s")' % cyl["trunk"][0]})
            sb.node("Leaves", "MeshInstance3D", k, {"mesh": 'SubResource("%s")' % cyl["trunk"][2], "position": V3(0, cell * 0.95, 0)})
            sb.node("Shape", "CollisionShape3D", k, {"shape": 'SubResource("%s")' % cyl["trunk"][1]})
            bump("tree")
        elif kind == "stairs":
            steps = 6
            k = sb.node("Stairs%d" % n, "Node3D", "Props", {"position": V3(*cpos(c, r, 0))})
            for i in range(steps):
                hh = wall_h / steps * (i + 1) * 0.5
                B.body3("Step%d" % i, k.replace("Props/", "Props/") if False else "Props/" + "Stairs%d" % n, (0, hh / 2.0, -cell / 2.0 + (i + 0.5) * cell / steps), (cell, hh, cell / steps), m_acc, groups=["stairs"])
            bump("stairs")
    if lighting:
        sun = sb.node("Sun", "DirectionalLight3D", ".", {"transform": "Transform3D(0.866, -0.354, 0.354, 0, 0.707, 0.707, -0.5, -0.612, 0.612, 0, 8, 0)", "shadow_enabled": "true", "light_energy": "1.1"})
        sky = hex_rgba(th["sky"])
        env = sb.sub("Environment", lines=["background_mode = 1", "background_color = " + Cx(sky), "ambient_light_source = 2", "ambient_light_color = " + Cx(tuple(min(1, x * 0.9 + 0.1) for x in sky[:3]) + (1,)),
                                           "ambient_light_energy = 0.8", "tonemap_mode = 2"], hint="env")
        sb.node("WorldEnvironment", "WorldEnvironment", ".", {"environment": 'SubResource("%s")' % env})
    return sb, counts, spawns, (W, H)


def build_blockout_2d(rows, leg, theme, cell, mode, name, origin):
    grid, W, H = _grid(rows, leg)
    sb = SB(name, "Node2D", "bo2_" + name)
    th = THEMES[theme]
    platformer = mode == "2d_platformer"
    ox, oy = origin[0], origin[1]
    counts = {}

    def bump(k):
        counts[k] = counts.get(k, 0) + 1

    shapes, rects = {}, {}

    def rshape(w, h):
        k = (round(w, 3), round(h, 3))
        if k not in shapes:
            shapes[k] = sb.sub("RectangleShape2D", lines=["size = " + V2(w, h)], hint="rect")
        return shapes[k]

    def poly(parent, col, w, h, name="Visual", extra=None):
        props = {"color": Cx(hex_rgba(col)), "polygon": "PackedVector2Array(%s, %s, %s, %s, %s, %s, %s, %s)" % tuple(f(x) for x in (-w / 2, -h / 2, w / 2, -h / 2, w / 2, h / 2, -w / 2, h / 2))}
        props.update(extra or {})
        return sb.node(name, "Polygon2D", parent, props)

    def rect_pos(rc):
        c, r, w, h = rc
        return (ox + (c + w / 2.0) * cell, oy + (r + h / 2.0) * cell), (w * cell, h * cell)

    for grp in ("Ground", "Hazards", "Props", "Markers"):
        sb.node(grp, "Node2D", ".")
    if not platformer:
        for i, rc in enumerate(merge_rects({k for k, v in grid.items() if v in _FLOORED})):
            pos, size = rect_pos(rc)
            sb.node("Floor%d" % i, "Polygon2D", "Ground", {"position": V2(*pos), "z_index": "-1", "color": Cx(hex_rgba(th["floor"])),
                                                           "polygon": "PackedVector2Array(%s, %s, %s, %s, %s, %s, %s, %s)" % tuple(f(x) for x in (-size[0] / 2, -size[1] / 2, size[0] / 2, -size[1] / 2, size[0] / 2, size[1] / 2, -size[0] / 2, size[1] / 2))})
            bump("floor")
    for i, rc in enumerate(merge_rects({k for k, v in grid.items() if v == "wall"})):
        pos, size = rect_pos(rc)
        k = sb.node("Wall%d" % i, "StaticBody2D", "Ground", {"position": V2(*pos)}, groups=["wall"])
        poly(k, th["wall"], *size)
        sb.node("Shape", "CollisionShape2D", k, {"shape": 'SubResource("%s")' % rshape(*size)})
        bump("wall")
    for i, rc in enumerate(merge_rects({k for k, v in grid.items() if v == "platform"})):
        pos, size = rect_pos(rc)
        k = sb.node("Platform%d" % i, "StaticBody2D", "Ground", {"position": V2(*pos[:1], pos[1] - size[1] * 0.25)}, groups=["platform"])
        poly(k, th["accent"], size[0], size[1] * 0.5)
        sb.node("Shape", "CollisionShape2D", k, {"shape": 'SubResource("%s")' % rshape(size[0], size[1] * 0.5), "one_way_collision": "true"})
        bump("platform")
    for kind, nm, col, groups in (("lava", "Lava", th["lava"], ["killzone", "hazard"]), ("water", "Water", th["water"], ["water"])):
        for i, rc in enumerate(merge_rects({k for k, v in grid.items() if v == kind})):
            pos, size = rect_pos(rc)
            k = sb.node("%s%d" % (nm, i), "Area2D", "Hazards", {"position": V2(*pos)}, groups=groups)
            r, g, b, a = hex_rgba(col)
            poly(k, "#000000", *size, extra={"color": Cx((r, g, b, 0.6 if kind == "water" else 1.0))})
            sb.node("Shape", "CollisionShape2D", k, {"shape": 'SubResource("%s")' % rshape(*size)})
            bump(kind)
    circ = {}

    def cshape(rad):
        if rad not in circ:
            circ[rad] = sb.sub("CircleShape2D", lines=["radius = " + f(rad)], hint="circ")
        return circ[rad]

    spawns = 0
    for (c, r), kind in sorted(grid.items(), key=lambda t: (t[0][1], t[0][0])):
        pos = (ox + (c + 0.5) * cell, oy + (r + 0.5) * cell)
        n = counts.get(kind, 0)
        if kind == "spawn":
            sb.node("PlayerSpawn" if spawns == 0 else "PlayerSpawn%d" % (spawns + 1), "Marker2D", "Markers", {"position": V2(*pos)}, groups=["player_spawn"])
            spawns += 1
            bump("spawn")
        elif kind == "coin":
            k = sb.node("Coin%d" % n, "Area2D", "Props", {"position": V2(*pos)}, groups=["coin"])
            poly(k, "#ffd23f", cell * 0.4, cell * 0.4)
            sb.node("Shape", "CollisionShape2D", k, {"shape": 'SubResource("%s")' % cshape(cell * 0.3)})
            bump("coin")
        elif kind in ("goal", "checkpoint", "door"):
            col = {"goal": "#7dff99", "checkpoint": "#4dd0ff", "door": th["accent"]}[kind]
            k = sb.node("%s%d" % (kind.capitalize(), n), "Area2D", "Props", {"position": V2(*pos)}, groups=[kind])
            r_, g_, b_, _a = hex_rgba(col)
            poly(k, "#000000", cell * 0.9, cell * 0.9, extra={"color": Cx((r_, g_, b_, 0.55))})
            sb.node("Shape", "CollisionShape2D", k, {"shape": 'SubResource("%s")' % rshape(cell * 0.9, cell * 0.9)})
            bump(kind)
        elif kind == "enemy":
            sb.node("EnemySpawn%d" % n, "Marker2D", "Markers", {"position": V2(*pos)}, groups=["enemy_spawn"])
            bump("enemy")
        elif kind in ("crate", "pillar", "tree", "stairs"):
            sz = {"crate": cell * 0.7, "pillar": cell * 0.5, "tree": cell * 0.8, "stairs": cell}[kind]
            col = {"crate": th["accent"], "pillar": th["wall"], "tree": "#40902f", "stairs": th["accent"]}[kind]
            k = sb.node("%s%d" % (kind.capitalize(), n), "StaticBody2D", "Props", {"position": V2(*pos)}, groups=[kind])
            poly(k, col, sz, sz)
            sb.node("Shape", "CollisionShape2D", k, {"shape": 'SubResource("%s")' % rshape(sz, sz)})
            bump(kind)
    if not platformer:
        pass
    return sb, counts, spawns, (W, H)


@tool(G, "ms_godot_level_blockout",
      "Turn an ASCII map into a playable greybox scene: # wall, . floor, S spawn, C coin, L lava, ~ water, G goal, D door, P pillar, T tree, B crate, K checkpoint, E enemy, ^ stairs, = platform (override with `legend`). "
      "mode=3d (default), 2d_topdown or 2d_platformer. Cells are merged into the fewest bodies with collisions; spawns/coins/goals/hazards are in groups (player_spawn, coin, goal, killzone, checkpoint, enemy_spawn). 6 themes.",
      {"rows": {"type": "array", "items": {"type": "string"}}, "ascii": {"type": "string"}, "mode": {"type": "string", "enum": list(MODES)}, "theme": {"type": "string", "enum": sorted(THEMES)},
       "cell": {"type": "number", "description": "Cell size (metres in 3D, pixels in 2D; default 4 / 48)."}, "wall_height": {"type": "number"}, "floor_thickness": {"type": "number"},
       "origin": {"type": "array", "items": {"type": "number"}}, "legend": {"type": "object", "description": "char -> kind (" + ", ".join(KINDS) + ")"}, "name": {"type": "string"},
       "lighting": {"type": "boolean", "description": "3D: add a sun + WorldEnvironment (default true unless merging into a scene)."},
       "scene_path": {"type": "string"}, "into_scene": INTO, "parent": PARENT, "overwrite": OVERWRITE}, [], writes=True, local=True)
def level_blockout(args, ctx):
    p = _proj(args, ctx)
    rows = _parse_rows(args)
    mode = str(args.get("mode") or "3d").lower()
    if mode not in MODES:
        raise ToolkitError("unknown mode '%s'" % mode, "Use: " + ", ".join(MODES))
    theme = str(args.get("theme") or "grassland").lower()
    if theme not in THEMES:
        raise ToolkitError("unknown theme '%s'" % theme, "Themes: " + ", ".join(sorted(THEMES)))
    leg = dict(LEGEND)
    for k, v in as_dict(args.get("legend")).items():
        if str(v) not in KINDS:
            raise ToolkitError("legend kind '%s' unknown" % v, "Kinds: " + ", ".join(KINDS))
        leg[str(k)[:1]] = str(v)
    name = ident(args.get("name") or "Level", "Level")
    org = [float(x) for x in as_list(args.get("origin"))] + [0.0, 0.0, 0.0]
    if mode == "3d":
        cell = num(args.get("cell"), 4.0, 0.25, 100)
        sb, counts, spawns, dims = build_blockout_3d(rows, leg, theme, cell, num(args.get("wall_height"), 5.0, 0.25, 200), num(args.get("floor_thickness"), 0.5, 0.05, 20), name, org[:3],
                                                     boolean(args.get("lighting"), not args.get("into_scene")))
    else:
        cell = num(args.get("cell"), 48.0, 4, 1000)
        sb, counts, spawns, dims = build_blockout_2d(rows, leg, theme, cell, mode, name, org[:2])
    warn = []
    if spawns == 0:
        warn.append("No spawn (S) in the map - add an S cell.")
    if not counts.get("goal"):
        warn.append("No goal (G) in the map.")
    out = Out(p, args)
    scene, top = target_scene(p, args, sb, "res://scenes/%s.tscn" % name.lower(), out)
    return out.done(scene=scene, root=top, mode=mode, theme=theme, cells=list(dims), size=[dims[0] * cell, dims[1] * cell], counts=counts, spawns=spawns, warnings=warn,
                    hint="Groups: player_spawn, coin, goal, killzone, checkpoint, enemy_spawn, door, water. Use ms_godot_gameplay_kit to add a player, collectibles and kill zones that react to them.")


# ───────────────────────── procedural terrain ─────────────────────────
TERRAIN_PRESETS = {
    # freq, octaves, gain, height (m), power, ridged, island, terrace, water fraction, palette (low, mid, high, peak)
    "flat": dict(freq=0.004, oct=2, gain=0.4, h=4, power=1.0, ridged=False, island=False, terrace=0, water=-1, pal=("#6aa84f", "#5f9a46", "#7fae60", "#9bbf7a")),
    "plains": dict(freq=0.004, oct=4, gain=0.45, h=18, power=1.2, ridged=False, island=False, terrace=0, water=0.06, pal=("#c9c28a", "#6aa84f", "#5b9444", "#8a8f6a")),
    "hills": dict(freq=0.006, oct=5, gain=0.5, h=45, power=1.4, ridged=False, island=False, terrace=0, water=0.08, pal=("#c9c28a", "#5fa04a", "#4d8a3c", "#8a8a80")),
    "mountains": dict(freq=0.005, oct=6, gain=0.5, h=140, power=1.8, ridged=True, island=False, terrace=0, water=0.05, pal=("#4d8a3c", "#7a7a72", "#9a9a98", "#f4f6fa")),
    "islands": dict(freq=0.007, oct=5, gain=0.5, h=50, power=1.6, ridged=False, island=True, terrace=0, water=0.2, pal=("#e8d9a0", "#5fa04a", "#4d8a3c", "#8a8a80")),
    "desert": dict(freq=0.005, oct=4, gain=0.45, h=35, power=1.3, ridged=False, island=False, terrace=0, water=-1, pal=("#d9bf80", "#e0c68a", "#c9a066", "#a8794a")),
    "canyon": dict(freq=0.006, oct=5, gain=0.5, h=90, power=1.5, ridged=False, island=False, terrace=7, water=0.04, pal=("#a8522a", "#c9733a", "#d9945a", "#e8b47a")),
    "tundra": dict(freq=0.005, oct=5, gain=0.5, h=40, power=1.4, ridged=False, island=False, terrace=0, water=0.06, pal=("#9fb2c0", "#d8e4ee", "#eef4fa", "#ffffff")),
    "volcano": dict(freq=0.006, oct=5, gain=0.5, h=130, power=1.5, ridged=False, island=True, terrace=0, water=0.1, pal=("#3a3a3a", "#5a4a42", "#7a3a22", "#2a2a2a")),
}

_TERRAIN_GD = '''@tool
extends Node3D
## Procedural terrain generated by Multi-Script (ms_godot_terrain_generate).
## Change the exported values and tick `regenerate` in the inspector to rebuild it in the editor.
## height_at(x, z) and scatter() help you place trees, rocks and buildings on the surface.

@export var seed_value: int = @@SEED@@:
	set(v):
		seed_value = v
		_queue()
@export var size: Vector2 = Vector2(@@SX@@, @@SZ@@):
	set(v):
		size = v
		_queue()
@export_range(16, 512, 16) var resolution: int = @@RES@@:
	set(v):
		resolution = v
		_queue()
@export var max_height: float = @@HEIGHT@@:
	set(v):
		max_height = v
		_queue()
@export var frequency: float = @@FREQ@@:
	set(v):
		frequency = v
		_queue()
@export_range(1, 8) var octaves: int = @@OCT@@:
	set(v):
		octaves = v
		_queue()
@export var gain: float = @@GAIN@@
@export var height_power: float = @@POWER@@
@export var ridged: bool = @@RIDGED@@
@export var island: bool = @@ISLAND@@
@export_range(0, 24) var terraces: int = @@TERRACE@@
@export_range(-1.0, 1.0) var water_level: float = @@WATER@@
@export var color_low: Color = @@C0@@
@export var color_mid: Color = @@C1@@
@export var color_high: Color = @@C2@@
@export var color_peak: Color = @@C3@@
@export var with_collision: bool = true
@export var regenerate: bool = false:
	set(v):
		regenerate = false
		if v:
			generate()

var heights := PackedFloat32Array()
var _noise := FastNoiseLite.new()
var _dirty := false


func _ready() -> void:
	generate()


func _queue() -> void:
	if is_inside_tree() and not _dirty:
		_dirty = true
		call_deferred("_rebuild")


func _rebuild() -> void:
	_dirty = false
	generate()


func _sample(u: float, v: float) -> float:
	var n := _noise.get_noise_2d(u * size.x, v * size.y)
	var h: float
	if ridged:
		h = 1.0 - absf(n) * 2.0
		h = h * h
	else:
		h = n * 0.5 + 0.5
	h = clampf(h, 0.0, 1.0)
	if island:
		var d := Vector2(u - 0.5, v - 0.5).length() * 2.0
		h *= clampf(1.0 - pow(d, 2.2), 0.0, 1.0)
	h = pow(h, height_power)
	if terraces > 0:
		var t := h * terraces
		h = (floorf(t) + smoothstep(0.0, 1.0, t - floorf(t)) * 0.6) / terraces
	return clampf(h, 0.0, 1.0)


func _color_for(h: float, slope: float) -> Color:
	var c: Color
	if h < 0.25:
		c = color_low.lerp(color_mid, h / 0.25)
	elif h < 0.65:
		c = color_mid.lerp(color_high, (h - 0.25) / 0.4)
	else:
		c = color_high.lerp(color_peak, clampf((h - 0.65) / 0.3, 0.0, 1.0))
	return c.lerp(color_high.darkened(0.35), clampf((slope - 0.55) * 1.6, 0.0, 0.8))


## Terrain height (world units, relative to this node) at a local x/z position.
func height_at(x: float, z: float) -> float:
	if heights.is_empty():
		return 0.0
	var u := clampf(x / size.x + 0.5, 0.0, 1.0) * resolution
	var v := clampf(z / size.y + 0.5, 0.0, 1.0) * resolution
	var i := mini(int(u), resolution - 1)
	var j := mini(int(v), resolution - 1)
	var fu := u - i
	var fv := v - j
	var w := resolution + 1
	var a := lerpf(heights[j * w + i], heights[j * w + i + 1], fu)
	var b := lerpf(heights[(j + 1) * w + i], heights[(j + 1) * w + i + 1], fu)
	return lerpf(a, b, fv) * max_height


## Place `count` copies of `scene` on the terrain between two height fractions (0-1) on gentle slopes. Returns the instances.
func scatter(scene: PackedScene, count: int, min_h: float = 0.1, max_h: float = 0.7, max_slope: float = 0.5, rng_seed: int = 1) -> Array[Node3D]:
	var out: Array[Node3D] = []
	var rng := RandomNumberGenerator.new()
	rng.seed = rng_seed
	var tries := 0
	while out.size() < count and tries < count * 20:
		tries += 1
		var x := rng.randf_range(-size.x * 0.5, size.x * 0.5)
		var z := rng.randf_range(-size.y * 0.5, size.y * 0.5)
		var y := height_at(x, z)
		var frac := y / maxf(max_height, 0.001)
		if frac < min_h or frac > max_h:
			continue
		var dx := height_at(x + 1.0, z) - height_at(x - 1.0, z)
		var dz := height_at(x, z + 1.0) - height_at(x, z - 1.0)
		if Vector2(dx, dz).length() / 2.0 > max_slope:
			continue
		var inst := scene.instantiate() as Node3D
		add_child(inst)
		inst.position = Vector3(x, y, z)
		inst.rotation.y = rng.randf() * TAU
		out.append(inst)
	return out


func generate() -> void:
	for child in get_children():
		if child.has_meta("ms_terrain"):
			remove_child(child)
			child.queue_free()
	_noise.seed = seed_value
	_noise.frequency = frequency
	_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	_noise.fractal_type = FastNoiseLite.FRACTAL_FBM
	_noise.fractal_octaves = octaves
	_noise.fractal_gain = gain
	var res := resolution
	var w := res + 1
	heights.resize(w * w)
	for j in w:
		for i in w:
			heights[j * w + i] = _sample(float(i) / res, float(j) / res)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var step := Vector2(size.x / res, size.y / res)
	for j in range(res):
		for i in range(res):
			var idx := [Vector2i(i, j), Vector2i(i + 1, j), Vector2i(i, j + 1), Vector2i(i + 1, j), Vector2i(i + 1, j + 1), Vector2i(i, j + 1)]
			for p in idx:
				var h := heights[p.y * w + p.x]
				var hx := heights[p.y * w + mini(p.x + 1, res)] - heights[p.y * w + maxi(p.x - 1, 0)]
				var hz := heights[mini(p.y + 1, res) * w + p.x] - heights[maxi(p.y - 1, 0) * w + p.x]
				var slope := Vector2(hx * max_height / (2.0 * step.x), hz * max_height / (2.0 * step.y)).length()
				st.set_color(_color_for(h, slope))
				st.set_uv(Vector2(float(p.x) / res, float(p.y) / res) * 16.0)
				st.add_vertex(Vector3(p.x * step.x - size.x * 0.5, h * max_height, p.y * step.y - size.y * 0.5))
	st.generate_normals()
	var mat := StandardMaterial3D.new()
	mat.vertex_color_use_as_albedo = true
	mat.roughness = 0.95
	st.set_material(mat)
	var mesh := st.commit()
	var mi := MeshInstance3D.new()
	mi.name = "TerrainMesh"
	mi.mesh = mesh
	mi.set_meta("ms_terrain", true)
	add_child(mi)
	if with_collision:
		var body := StaticBody3D.new()
		body.name = "TerrainBody"
		body.set_meta("ms_terrain", true)
		var cs := CollisionShape3D.new()
		cs.name = "TerrainShape"
		var hm := HeightMapShape3D.new()
		hm.map_width = w
		hm.map_depth = w
		var data := PackedFloat32Array()
		data.resize(w * w)
		for k in w * w:
			data[k] = heights[k] * max_height
		hm.map_data = data
		cs.shape = hm
		cs.scale = Vector3(step.x, 1.0, step.y)
		body.add_child(cs)
		add_child(body)
	if water_level >= 0.0:
		var wm := MeshInstance3D.new()
		wm.name = "Water"
		wm.set_meta("ms_terrain", true)
		var pm := PlaneMesh.new()
		pm.size = size * 1.05
		var wmat := StandardMaterial3D.new()
		wmat.albedo_color = Color(0.12, 0.38, 0.62, 0.72)
		wmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		wmat.roughness = 0.08
		wmat.metallic = 0.2
		pm.material = wmat
		wm.mesh = pm
		wm.position.y = water_level * max_height
		add_child(wm)
'''


@tool(G, "ms_godot_terrain_generate",
      "Generate a procedural 3D terrain: presets flat, plains, hills, mountains (ridged), islands, desert, canyon (terraced), tundra, volcano. Writes an editable @tool script (FastNoiseLite, vertex-coloured mesh by height/slope, "
      "HeightMapShape3D collision, optional water plane, height_at() and scatter() helpers) plus a ready scene. Seeded; size, height and resolution adjustable; re-generate from the inspector.",
      {"preset": {"type": "string", "enum": sorted(TERRAIN_PRESETS)}, "size": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2, "description": "[x, z] metres (default [256,256])."},
       "height": {"type": "number"}, "resolution": {"type": "integer", "description": "Quads per side, 16-512 (default 128)."}, "seed": {"type": "integer"},
       "water_level": {"type": "number", "description": "0-1 fraction of height; -1 = no water."}, "name": {"type": "string"}, "script_path": {"type": "string"},
       "scene_path": {"type": "string"}, "into_scene": INTO, "parent": PARENT, "overwrite": OVERWRITE}, [], writes=True, local=True)
def terrain_generate(args, ctx):
    p = _proj(args, ctx)
    preset = str(args.get("preset") or "hills").lower()
    pr = TERRAIN_PRESETS.get(preset)
    if not pr:
        raise ToolkitError("unknown preset '%s'" % preset, "Presets: " + ", ".join(sorted(TERRAIN_PRESETS)))
    size = [float(x) for x in as_list(args.get("size"))] or [256.0, 256.0]
    if len(size) != 2 or min(size) < 8 or max(size) > 20000:
        raise ToolkitError("size must be [x, z] between 8 and 20000 metres")
    res = int(num(args.get("resolution"), 128, 16, 512, True))
    res = max(16, (res // 16) * 16)
    name = ident(args.get("name") or "Terrain", "Terrain")
    height = num(args.get("height"), pr["h"], 0.5, 5000)
    cols = [Cx(hex_rgba(c)) for c in pr["pal"]]
    gd = fill(_TERRAIN_GD, SEED=str(int(num(args.get("seed"), 1337, -2**31, 2**31 - 1, True))), SX=f(size[0]), SZ=f(size[1]), RES=str(res), HEIGHT=f(height), FREQ=f(pr["freq"]),
              OCT=str(pr["oct"]), GAIN=f(pr["gain"]), POWER=f(pr["power"]), RIDGED="true" if pr["ridged"] else "false", ISLAND="true" if pr["island"] else "false", TERRACE=str(pr["terrace"]),
              WATER=f(num(args.get("water_level"), pr["water"], -1, 1)), C0=cols[0], C1=cols[1], C2=cols[2], C3=cols[3])
    out = Out(p, args)
    spath = out.put(norm_res(args.get("script_path") or "res://scripts/%s.gd" % name.lower(), ".gd", "res://scripts"), gd, "GDScript")
    sb = SB(name, "Node3D", "terrain_" + name)
    sb.nodes[0]["body"].append('script = ExtResource("%s")' % sb.ext_res(spath, "Script"))
    scene, top = target_scene(p, args, sb, "res://scenes/%s.tscn" % name.lower(), out)
    return out.done(scene=scene, script=spath, preset=preset, size=size, resolution=res, height=height,
                    hint="Open the scene: the terrain is generated on load. Change seed_value/height/frequency in the inspector and tick `regenerate`. Call $%s.height_at(x, z) to place objects; scatter(scene, count) spawns props." % name)


# ───────────────────────── project / scene audit ─────────────────────────
_BODIES = ("CharacterBody2D", "CharacterBody3D", "StaticBody2D", "StaticBody3D", "RigidBody2D", "RigidBody3D", "Area2D", "Area3D", "AnimatableBody2D", "AnimatableBody3D")
_COLL_KIDS = ("CollisionShape2D", "CollisionShape3D", "CollisionPolygon2D", "CollisionPolygon3D")
_ACTION_CALL = re.compile(r"\b(is_action_pressed|is_action_just_pressed|is_action_just_released|is_action_released|get_action_strength|get_action_raw_strength|is_action|get_axis|get_vector|action_press|action_release)\s*\(([^)]*)\)")
_STR_LIT = re.compile(r'&?"([^"\\]+)"')
_ID_USE = re.compile(r'(?:ExtResource|SubResource)\(\s*"([^"]+)"\s*\)')
_DEFAULT_KEYS = {
    "move_left": ["a", "left"], "move_right": ["d", "right"], "move_up": ["w", "up"], "move_down": ["s", "down"], "move_forward": ["w", "up"], "move_back": ["s", "down"],
    "jump": ["space", "pad_a"], "sprint": ["shift"], "crouch": ["ctrl"], "interact": ["e", "pad_x"], "attack": ["mouse_left", "pad_x"], "shoot": ["mouse_left", "pad_rb"], "fire": ["mouse_left"],
    "reload": ["r"], "dash": ["shift", "pad_b"], "pause": ["escape", "pad_start"], "aim": ["mouse_right"], "use": ["e"], "inventory": ["i", "tab"], "restart": ["r"],
}


def _iter_files(root, exts, include_addons=False, limit=3000):
    n = 0
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in (".godot", ".git", ".import", "node_modules") and (include_addons or x != "addons")]
        for fn in files:
            if fn.lower().endswith(exts):
                n += 1
                if n > limit:
                    return
                yield os.path.join(d, fn)


def _res_exists(p, path):
    return path.startswith("uid://") or os.path.exists(_abs(p, path))


def audit_scene(p, full, scenes_info):
    """Return (findings, unused_ext_ids, text)."""
    rel = _res(p, full)
    text = _read(full)
    sc = Scene(text)
    out, unused = [], []
    used = set(_ID_USE.findall("\n".join(([b["header"] or "" for b in sc.blocks if b["kind"] not in ("ext_resource",)]) + [ln for b in sc.blocks for ln in b["body"]])))
    for b in sc.of("ext_resource"):
        path, rid = b["attrs"].get("path", ""), b["attrs"].get("id", "")
        if path.startswith("res://") and not _res_exists(p, path):
            out.append({"severity": "error", "file": rel, "message": "missing resource %s (%s)" % (path, b["attrs"].get("type", "")), "kind": "missing_resource"})
        if rid and rid not in used:
            unused.append(rid)
            out.append({"severity": "info", "file": rel, "message": "unused ext_resource %s -> %s" % (rid, path), "kind": "unused_resource", "fixable": True})
    nodes = sc.nodes()
    by_parent = {}
    for n in nodes:
        by_parent.setdefault(sc.key(n) if n["attrs"].get("parent") is not None else ".", [])
    kids = {}
    for n in nodes:
        par = n["attrs"].get("parent")
        if par is not None:
            kids.setdefault(par if par != "." else ".", []).append(n)
    for n in nodes:
        typ, key = n["attrs"].get("type", ""), sc.key(n)
        inst = "instance" in n["header"]
        body = "\n".join(n["body"])
        if typ in _BODIES and not inst:
            if not any(k["attrs"].get("type") in _COLL_KIDS or "instance" in k["header"] for k in kids.get(key, [])):
                out.append({"severity": "warning", "file": rel, "message": "%s '%s' has no CollisionShape child" % (typ, key), "kind": "no_collision"})
        if typ in ("CollisionShape2D", "CollisionShape3D") and not re.search(r"^shape\s*=", body, re.M):
            out.append({"severity": "warning", "file": rel, "message": "%s '%s' has no shape assigned" % (typ, key), "kind": "empty_shape"})
        if typ == "MeshInstance3D" and not re.search(r"^mesh\s*=", body, re.M) and not inst:
            out.append({"severity": "info", "file": rel, "message": "MeshInstance3D '%s' has no mesh" % key, "kind": "empty_mesh"})
        if typ in ("Sprite2D", "Sprite3D", "TextureRect") and not re.search(r"^texture\s*=", body, re.M) and not inst:
            out.append({"severity": "info", "file": rel, "message": "%s '%s' has no texture" % (typ, key), "kind": "empty_texture"})
    scenes_info[rel] = {"nodes": len(nodes), "types": {n["attrs"].get("type", "") for n in nodes}}
    return out, unused, text


def remove_ext_resources(text, ids):
    for rid in ids:
        text = re.sub(r'^\[ext_resource [^\n]*\bid="%s"[^\n]*\]\n?' % re.escape(rid), "", text, flags=re.M)
    m = re.search(r"load_steps=(\d+)", text)
    if m:
        text = text.replace(m.group(0), "load_steps=%d" % max(1, int(m.group(1)) - len(ids)), 1)
    return text


@tool(G, "ms_godot_scene_audit",
      "Audit a Godot project's files for common breakage: missing scripts/resources in .tscn/.tres, unused ext_resources, physics bodies without a CollisionShape, empty shapes/meshes/textures, "
      "missing or broken main scene and autoload files, and input actions used in scripts (Input.is_action_pressed, get_axis, get_vector ...) that are not defined in project.godot. "
      "`fix=true` removes unused ext_resources and defines missing common actions (move_*, jump, interact, attack ...) with default keys.",
      {"fix": {"type": "boolean"}, "include_addons": {"type": "boolean"}, "scene": {"type": "string", "description": "Audit only this scene (res://...tscn)."}, "max_findings": {"type": "integer"}}, [], writes=True, local=True)
def scene_audit(args, ctx):
    from toolkit_godot import _key_event, set_setting
    p = _proj(args, ctx)
    fix = boolean(args.get("fix"), False)
    findings, scenes_info, fixed = [], {}, []
    proj_file = os.path.join(p, "project.godot")
    ptext = _read(proj_file) if os.path.isfile(proj_file) else ""
    if not ptext:
        raise ToolkitError("project.godot not found in %s" % p, "Pass `project_path` or open a Godot project.")
    entries, _lines = parse_project(ptext)
    cfg = {(e["section"] + "/" + e["key"]) if e["section"] else e["key"]: e["raw"] for e in entries}
    main = cfg.get("application/run/main_scene", "").strip().strip('"')
    if not main:
        findings.append({"severity": "warning", "file": "project.godot", "message": "no main scene set (application/run/main_scene)", "kind": "no_main_scene"})
    elif main.startswith("res://") and not _res_exists(p, main):
        findings.append({"severity": "error", "file": "project.godot", "message": "main scene %s does not exist" % main, "kind": "missing_main_scene"})
    for e in entries:
        if e["section"] == "autoload":
            path = e["raw"].strip().strip('"').lstrip("*")
            if path.startswith("res://") and not _res_exists(p, path):
                findings.append({"severity": "error", "file": "project.godot", "message": "autoload %s points to missing %s" % (e["key"], path), "kind": "missing_autoload"})
    only = norm_res(args["scene"], ".tscn") if args.get("scene") else None
    for full in _iter_files(p, (".tscn", ".tres"), boolean(args.get("include_addons"), False)):
        if only and _res(p, full) != only:
            continue
        fnd, unused, text = audit_scene(p, full, scenes_info)
        findings += fnd
        if fix and unused:
            new = remove_ext_resources(text, unused)
            if new != text and _write(full, new, args):
                fixed.append({"file": _res(p, full), "removed_ext_resources": unused})
            elif new != text:
                fixed.append({"file": _res(p, full), "would_remove": unused})
    defined = {e["key"] for e in entries if e["section"] == "input"}
    used_actions = {}
    for full in _iter_files(p, (".gd",), boolean(args.get("include_addons"), False)):
        try:
            src = _read(full)
        except Exception:
            continue
        for m in _ACTION_CALL.finditer(re.sub(r"#[^\n]*", "", src)):
            for name in _STR_LIT.findall(m.group(2)):
                used_actions.setdefault(name, set()).add(_res(p, full))
    missing_actions = sorted(n for n in used_actions if n not in defined and not n.startswith("ui_") and not n.startswith("spatial_editor") and not n.startswith("scene_"))
    for n in missing_actions:
        findings.append({"severity": "error", "file": sorted(used_actions[n])[0], "message": "input action '%s' is used in code but not defined in project.godot" % n, "kind": "missing_action", "fixable": n in _DEFAULT_KEYS})
    if fix and missing_actions:
        added = []
        text = ptext
        for n in missing_actions:
            if n in _DEFAULT_KEYS:
                events = ", ".join(_key_event(k) for k in _DEFAULT_KEYS[n])
                text = set_setting(text, "input", n, '{\n"deadzone": 0.5,\n"events": [%s]\n}' % events)
                added.append(n)
        if added:
            _write(proj_file, text, args)
            fixed.append({"file": "project.godot", "defined_actions": added})
    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda x: (order[x["severity"]], x["file"]))
    cap = int(num(args.get("max_findings"), 120, 1, 1000, True))
    summary = {s: sum(1 for x in findings if x["severity"] == s) for s in ("error", "warning", "info")}
    return {"ok": summary["error"] == 0, "scenes_scanned": len(scenes_info), "summary": summary, "findings": findings[:cap], "truncated": len(findings) > cap,
            "main_scene": main or None, "used_actions": {k: sorted(v) for k, v in sorted(used_actions.items())}, "fixed": fixed}
