# SPDX-License-Identifier: GPL-3.0-or-later
"""Godot building/modeling tools: enterable buildings, linear structures along paths (CSG path roads/walls/rails + posts/lamps/planks),
prop scattering. Everything is written as plain .tscn text and loaded by a real headless Godot in the test-suite."""
import math
import os
import random

from engine_toolkit import tool, as_list, as_dict, num, boolean, ToolkitError
from toolkit_godot import _proj, _abs, _res, _read, _write, G, Scene
from toolkit_godot_pro import SB, Out, OVERWRITE, INTO, PARENT, f, V2, V3, C, Cx, hex_rgba, ident, norm_res, target_scene, set_raw

VEC3 = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}


class Boxes:
    """Collects boxes/prisms/cylinders into an SB scene with shared meshes + materials."""

    def __init__(self, sb):
        self.sb, self._mat, self._mesh, self._shape = sb, {}, {}, {}

    def mat(self, key, color, emission=None, alpha=None, rough=0.85, metallic=0.0):
        if key not in self._mat:
            c = hex_rgba(color)
            lines = ["albedo_color = " + Cx(c[:3] + ((alpha,) if alpha is not None else (c[3],))), "roughness = " + f(rough)]
            if metallic:
                lines.append("metallic = " + f(metallic))
            if alpha is not None and alpha < 1:
                lines.append("transparency = 1")
            if emission:
                lines += ["emission_enabled = true", "emission = " + C(emission), "emission_energy_multiplier = 1.6"]
            self._mat[key] = self.sb.sub("StandardMaterial3D", lines=lines, hint="m_" + key)
        return self._mat[key]

    def box_mesh(self, size, mat):
        k = ("b", tuple(round(x, 4) for x in size), mat)
        if k not in self._mesh:
            self._mesh[k] = self.sb.sub("BoxMesh", lines=['material = SubResource("%s")' % mat, "size = " + V3(*size)], hint="box")
        return self._mesh[k]

    def box_shape(self, size):
        k = tuple(round(x, 4) for x in size)
        if k not in self._shape:
            self._shape[k] = self.sb.sub("BoxShape3D", lines=["size = " + V3(*size)], hint="bs")
        return self._shape[k]

    def box(self, parent, name, pos, size, mat, collide=False, rot=None, body=None):
        props = {"position": V3(*pos)}
        if rot:
            props["rotation"] = V3(*rot)
        props["mesh"] = 'SubResource("%s")' % self.box_mesh(size, mat)
        k = self.sb.node(name, "MeshInstance3D", parent, props)
        if collide:
            cp = {"position": V3(*pos), "shape": 'SubResource("%s")' % self.box_shape(size)}
            if rot:
                cp["rotation"] = V3(*rot)
            self.sb.node(name + "_col", "CollisionShape3D", body or parent, cp)
        return k

    def prism(self, parent, name, pos, size, mat, rot=None):
        mid = self._mesh.get(("p", size, mat)) or self.sb.sub("PrismMesh", lines=['material = SubResource("%s")' % mat, "size = " + V3(*size)], hint="prism")
        self._mesh[("p", size, mat)] = mid
        props = {"position": V3(*pos), "mesh": 'SubResource("%s")' % mid}
        if rot:
            props["rotation"] = V3(*rot)
        return self.sb.node(name, "MeshInstance3D", parent, props)

    def cylinder(self, parent, name, pos, radius, height, mat, collide=False, rot=None, body=None, top=None):
        k = ("c", round(radius, 3), round(height, 3), mat, top)
        if k not in self._mesh:
            self._mesh[k] = self.sb.sub("CylinderMesh", lines=['material = SubResource("%s")' % mat, "top_radius = " + f(radius if top is None else top), "bottom_radius = " + f(radius), "height = " + f(height), "radial_segments = 16", "rings = 1"], hint="cyl")
        props = {"position": V3(*pos), "mesh": 'SubResource("%s")' % self._mesh[k]}
        if rot:
            props["rotation"] = V3(*rot)
        n = self.sb.node(name, "MeshInstance3D", parent, props)
        if collide:
            sk = ("cs", round(radius, 3), round(height, 3))
            if sk not in self._shape:
                self._shape[sk] = self.sb.sub("CylinderShape3D", lines=["radius = " + f(radius), "height = " + f(height)], hint="cs")
            cp = {"position": V3(*pos), "shape": 'SubResource("%s")' % self._shape[sk]}
            if rot:
                cp["rotation"] = V3(*rot)
            self.sb.node(name + "_col", "CollisionShape3D", body or parent, cp)
        return n

    def sphere(self, parent, name, pos, radius, mat, squash=1.0, collide=False, body=None):
        k = ("s", round(radius, 3), squash, mat)
        if k not in self._mesh:
            self._mesh[k] = self.sb.sub("SphereMesh", lines=['material = SubResource("%s")' % mat, "radius = " + f(radius), "height = " + f(radius * 2 * squash)], hint="sph")
        n = self.sb.node(name, "MeshInstance3D", parent, {"position": V3(*pos), "mesh": 'SubResource("%s")' % self._mesh[k]})
        if collide:
            sk = ("ss", round(radius, 3))
            if sk not in self._shape:
                self._shape[sk] = self.sb.sub("SphereShape3D", lines=["radius = " + f(radius)], hint="ss")
            self.sb.node(name + "_col", "CollisionShape3D", body or parent, {"position": V3(*pos), "shape": 'SubResource("%s")' % self._shape[sk]})
        return n


# ───────────────────────── buildings ─────────────────────────
BUILDINGS = {
    # w, d, floors, floor_h, roof, wall, roof_color, trim, window cols per long wall, extras
    "house": dict(w=8, d=6, floors=2, fh=3.0, roof="gable", wall="#e8dcc4", rc="#a8442f", trim="#6b4a2b", cols=3),
    "cottage": dict(w=6, d=5, floors=1, fh=2.8, roof="gable", wall="#d9c9a8", rc="#8a5a2b", trim="#4d3a22", cols=2),
    "shop": dict(w=8, d=7, floors=1, fh=3.4, roof="flat", wall="#c9b08a", rc="#5a4a3a", trim="#2f3a4d", cols=2, awning=True),
    "tower": dict(w=5, d=5, floors=4, fh=3.0, roof="battlement", wall="#9a9a98", rc="#6a6a68", trim="#4a4a48", cols=1),
    "castle_keep": dict(w=12, d=12, floors=3, fh=4.0, roof="battlement", wall="#8a8a86", rc="#5a5a58", trim="#3a3a38", cols=2),
    "barn": dict(w=10, d=14, floors=1, fh=5.0, roof="gable", wall="#a8372b", rc="#4a3a30", trim="#efe8dc", cols=2),
    "watchtower": dict(w=4, d=4, floors=3, fh=2.8, roof="stepped", wall="#8a6a4a", rc="#5a3a22", trim="#3a2a18", cols=1),
    "hut": dict(w=4, d=4, floors=1, fh=2.4, roof="gable", wall="#b8905a", rc="#c9a24a", trim="#5a3a22", cols=1),
}
ROOFS = ["gable", "flat", "stepped", "battlement"]
SIDES = ["front", "back", "left", "right"]


def wall_boxes(length, floors, fh, openings):
    """openings: [(floor, u_center, w, y0, y1)] -> list of (u_center, y_center, w, h). y relative to the wall base."""
    out = []
    for fl in range(floors):
        base = fl * fh
        ops = sorted([o for o in openings if o[0] == fl], key=lambda o: o[1])
        cursor = -length / 2.0
        for (_f, u, w, y0, y1) in ops:
            a, b = u - w / 2.0, u + w / 2.0
            if a - cursor > 0.01:
                out.append(((cursor + a) / 2.0, base + fh / 2.0, a - cursor, fh))
            if y0 > 0.01:
                out.append((u, base + y0 / 2.0, w, y0))
            if fh - y1 > 0.01:
                out.append((u, base + (y1 + fh) / 2.0, w, fh - y1))
            cursor = b
        if length / 2.0 - cursor > 0.01:
            out.append(((cursor + length / 2.0) / 2.0, base + fh / 2.0, length / 2.0 - cursor, fh))
    return out


def build_building(kind, a):
    d = BUILDINGS[kind]
    W, D = num(a.get("width"), d["w"], 2, 80), num(a.get("depth"), d["d"], 2, 80)
    floors = int(num(a.get("floors"), d["floors"], 1, 20, True))
    fh = num(a.get("floor_height"), d["fh"], 2.2, 12)
    t = num(a.get("wall_thickness"), 0.3, 0.1, 2)
    roof = str(a.get("roof") or d["roof"])
    if roof not in ROOFS:
        raise ToolkitError("unknown roof '%s'" % roof, "Roofs: " + ", ".join(ROOFS))
    door_side = str(a.get("door_side") or "front")
    if door_side not in SIDES:
        raise ToolkitError("unknown door_side '%s'" % door_side, "Sides: " + ", ".join(SIDES))
    name = ident(a.get("name") or kind.title().replace("_", ""), "Building")
    sb = SB(name, "Node3D", "bld_" + name)
    B = Boxes(sb)
    m_wall = B.mat("wall", a.get("wall_color") or d["wall"])
    m_roof = B.mat("roof", a.get("roof_color") or d["rc"])
    m_trim = B.mat("trim", a.get("trim_color") or d["trim"])
    m_floor = B.mat("floor", "#6b5a45")
    lit = boolean(a.get("lit_windows"), False)
    m_glass = B.mat("glass", "#9fd0ff", emission="#ffd98a" if lit else None, alpha=0.45, rough=0.05)
    total_h = floors * fh
    for grp, typ in (("Walls", "StaticBody3D"), ("Floors", "StaticBody3D"), ("Roof", "StaticBody3D"), ("Trim", "Node3D"), ("Windows", "Node3D")):
        sb.node(grp, typ, ".")
    # slabs
    B.box("Floors", "Ground", (0, -0.1, 0), (W + 0.4, 0.2, D + 0.4), m_floor, True, body="Floors")
    for fl in range(1, floors):
        B.box("Floors", "Slab%d" % fl, (0, fl * fh - 0.1, 0), (W - 2 * t, 0.2, D - 2 * t), m_floor, True, body="Floors")
    # openings per wall (length axis)
    door_w, door_h = 1.3, min(2.2, fh - 0.3)
    win_w, win_h, sill = 1.1, min(1.2, fh - 1.4), 0.9
    walls = {"front": (W, 1), "back": (W, -1), "left": (D, -1), "right": (D, 1)}  # side -> (length, outward sign)
    ncols = {"front": d["cols"], "back": d["cols"], "left": max(1, d["cols"] - 1), "right": max(1, d["cols"] - 1)}
    shop = bool(d.get("awning")) and kind == "shop"
    wi = 0
    for side, (L, sign) in walls.items():
        ops = []          # (floor, u, w, y0, y1, tag)
        n = ncols[side]
        for fl in range(floors):
            for i in range(n):
                u = -L / 2.0 + L * (i + 0.5) / n
                if fl == 0 and ((side == door_side and abs(u) < max(door_w, 1.6) * 0.9) or (shop and side == "front")):
                    continue
                ops.append((fl, u, win_w, sill, sill + win_h, "win"))
        if shop and side == "front":
            ops.append((0, -1.0, L - 4.4, 0.9, door_h + 0.3, "win"))
            ops.append((0, L / 2.0 - 1.4, door_w, 0.0, door_h, "door"))
        elif side == door_side:
            ops.append((0, 0.0, door_w, 0.0, door_h, "door"))
        L_eff = L if side in ("front", "back") else D - 2 * t
        if side in ("left", "right"):
            ops = [o for o in ops if abs(o[1]) + o[2] / 2 <= L_eff / 2.0 + 0.001]
        for (u, yc, w, h) in wall_boxes(L_eff, floors, fh, [o[:5] for o in ops]):
            if side == "front":
                pos, size = (u, yc, D / 2.0 - t / 2.0), (w, h, t)
            elif side == "back":
                pos, size = (-u, yc, -D / 2.0 + t / 2.0), (w, h, t)
            elif side == "left":
                pos, size = (-W / 2.0 + t / 2.0, yc, u), (t, h, w)
            else:
                pos, size = (W / 2.0 - t / 2.0, yc, -u), (t, h, w)
            wi += 1
            B.box("Walls", "Wall%d" % wi, pos, size, m_wall, True, body="Walls")
        # glass + frames
        for (fl, u, w, y0, y1, tag) in ops:
            kindn = "Door" if tag == "door" else "Win"
            yc = fl * fh + (y0 + y1) / 2.0
            hh = y1 - y0
            if side == "front":
                p, sz, fr = (u, yc, D / 2.0 - t / 2.0), (w, hh, 0.05), (0, 0, 1)
            elif side == "back":
                p, sz, fr = (-u, yc, -D / 2.0 + t / 2.0), (w, hh, 0.05), (0, 0, 1)
            elif side == "left":
                p, sz, fr = (-W / 2.0 + t / 2.0, yc, u), (0.05, hh, w), (1, 0, 0)
            else:
                p, sz, fr = (W / 2.0 - t / 2.0, yc, -u), (0.05, hh, w), (1, 0, 0)
            if kindn == "Win":
                B.box("Windows", "Glass%d" % wi, p, sz, m_glass)
                wi += 1
            # frame: top + sides + sill
            ft = 0.08
            if fr == (0, 0, 1):
                parts = [((p[0], p[1] + hh / 2 + ft / 2, p[2]), (w + 2 * ft, ft, t + 0.08)), ((p[0] - w / 2 - ft / 2, p[1], p[2]), (ft, hh, t + 0.08)), ((p[0] + w / 2 + ft / 2, p[1], p[2]), (ft, hh, t + 0.08))]
                if kindn == "Win":
                    parts.append(((p[0], p[1] - hh / 2 - ft / 2, p[2]), (w + 2 * ft, ft, t + 0.14)))
            else:
                parts = [((p[0], p[1] + hh / 2 + ft / 2, p[2]), (t + 0.08, ft, w + 2 * ft)), ((p[0], p[1], p[2] - w / 2 - ft / 2), (t + 0.08, hh, ft)), ((p[0], p[1], p[2] + w / 2 + ft / 2), (t + 0.08, hh, ft))]
                if kindn == "Win":
                    parts.append(((p[0], p[1] - hh / 2 - ft / 2, p[2]), (t + 0.14, ft, w + 2 * ft)))
            for j, (pp, ss) in enumerate(parts):
                wi += 1
                B.box("Trim", "Frame%d" % wi, pp, ss, m_trim)
    # corner trim
    for sx in (-1, 1):
        for sz in (-1, 1):
            B.box("Trim", "Corner%d%d" % (sx + 1, sz + 1), (sx * (W / 2.0), total_h / 2.0, sz * (D / 2.0)), (0.22, total_h, 0.22), m_trim)
    # ceiling + roof
    B.box("Roof", "Ceiling", (0, total_h + 0.1, 0), (W, 0.2, D), m_roof if roof != "gable" else m_floor, True, body="Roof")
    ov = 0.5
    if roof == "gable":
        rise = max(1.2, min(W, D) * 0.45)
        if W >= D:      # ridge along X
            B.prism("Roof", "RoofPrism", (0, total_h + 0.2 + rise / 2.0, 0), (D + 2 * ov, rise, W + 2 * ov), m_roof, rot=(0, math.pi / 2, 0))
        else:           # ridge along Z
            B.prism("Roof", "RoofPrism", (0, total_h + 0.2 + rise / 2.0, 0), (W + 2 * ov, rise, D + 2 * ov), m_roof)
    elif roof == "flat":
        B.box("Roof", "Parapet0", (0, total_h + 0.4, D / 2.0 - 0.1), (W, 0.6, 0.2), m_trim)
        B.box("Roof", "Parapet1", (0, total_h + 0.4, -D / 2.0 + 0.1), (W, 0.6, 0.2), m_trim)
        B.box("Roof", "Parapet2", (W / 2.0 - 0.1, total_h + 0.4, 0), (0.2, 0.6, D - 0.4), m_trim)
        B.box("Roof", "Parapet3", (-W / 2.0 + 0.1, total_h + 0.4, 0), (0.2, 0.6, D - 0.4), m_trim)
    elif roof == "stepped":
        for i in range(3):
            s = 1.0 - i * 0.28
            B.box("Roof", "Step%d" % i, (0, total_h + 0.4 + i * 0.5, 0), (W * s + 0.6, 0.5, D * s + 0.6), m_roof, True, body="Roof")
    else:  # battlement
        B.box("Roof", "Rim", (0, total_h + 0.3, 0), (W + 0.5, 0.4, D + 0.5), m_trim)
        n_w, n_d = max(2, int(W // 1.4)), max(2, int(D // 1.4))
        for i in range(n_w):
            if i % 2 == 0:
                u = -W / 2.0 + (i + 0.5) * W / n_w
                B.box("Roof", "MerlonF%d" % i, (u, total_h + 0.95, D / 2.0 + 0.1), (W / n_w, 0.9, 0.4), m_trim)
                B.box("Roof", "MerlonB%d" % i, (u, total_h + 0.95, -D / 2.0 - 0.1), (W / n_w, 0.9, 0.4), m_trim)
        for i in range(n_d):
            if i % 2 == 0:
                u = -D / 2.0 + (i + 0.5) * D / n_d
                B.box("Roof", "MerlonL%d" % i, (-W / 2.0 - 0.1, total_h + 0.95, u), (0.4, 0.9, D / n_d), m_trim)
                B.box("Roof", "MerlonR%d" % i, (W / 2.0 + 0.1, total_h + 0.95, u), (0.4, 0.9, D / n_d), m_trim)
    if d.get("awning"):
        B.box("Trim", "Awning", (0, door_h + 0.55, D / 2.0 + 0.6), (W - 1.6, 0.12, 1.4), B.mat("awning", "#d94a3d"), rot=(0.25, 0, 0))
    if lit:
        for fl in range(floors):
            sb.node("Light%d" % fl, "OmniLight3D", ".", {"position": V3(0, fl * fh + fh * 0.7, 0), "light_color": C("#ffd9a0"), "omni_range": f(max(W, D) * 0.9), "light_energy": "1.2"})
    rot = math.radians(num(a.get("rotation_y"), 0, -360, 360))
    pos = [float(x) for x in as_list(a.get("position"))] + [0, 0, 0]
    sb.nodes[0]["body"] += ["position = " + V3(*pos[:3])] + (["rotation = " + V3(0, rot, 0)] if rot else [])
    return sb, dict(kind=kind, size=[W, D], floors=floors, floor_height=fh, roof=roof, door_side=door_side, height=total_h + (0.2 if roof != "gable" else 0.2 + max(1.2, min(W, D) * 0.45)), pieces=wi)


@tool(G, "ms_godot_building_generator",
      "Procedurally build an enterable building scene: house, cottage, shop, tower, castle_keep, barn, watchtower or hut. Real wall segments around a door and window openings (glass panes, frames), floor slabs per storey, "
      "corner trim and a gable / flat / stepped / battlement roof, all with collisions. Size, floors, colours, door side, rotation and lit windows (OmniLights) are adjustable. Saves a scene or merges into one.",
      {"kind": {"type": "string", "enum": sorted(BUILDINGS)}, "position": VEC3, "rotation_y": {"type": "number"}, "width": {"type": "number"}, "depth": {"type": "number"}, "floors": {"type": "integer"},
       "floor_height": {"type": "number"}, "wall_thickness": {"type": "number"}, "roof": {"type": "string", "enum": ROOFS}, "door_side": {"type": "string", "enum": SIDES},
       "wall_color": {"type": ["string", "array"]}, "roof_color": {"type": ["string", "array"]}, "trim_color": {"type": ["string", "array"]}, "lit_windows": {"type": "boolean"}, "name": {"type": "string"},
       "scene_path": {"type": "string"}, "into_scene": INTO, "parent": PARENT, "overwrite": OVERWRITE}, ["kind"], writes=True, local=True)
def building_generator(args, ctx):
    kind = str(args.get("kind") or "").lower()
    if kind not in BUILDINGS:
        raise ToolkitError("unknown kind '%s'" % kind, "Kinds: " + ", ".join(sorted(BUILDINGS)))
    p = _proj(args, ctx)
    sb, info = build_building(kind, args)
    out = Out(p, args)
    scene, top = target_scene(p, args, sb, "res://scenes/buildings/%s.tscn" % sb.nodes[0]["name"].lower(), out)
    return out.done(scene=scene, root=top, **info)


# ───────────────────────── path builder ─────────────────────────
PATH_KINDS = ["road", "path", "fence", "rail", "bridge", "wall", "pipe", "lamps", "stones"]
_DEFAULT_COLOR = {"road": "#3a3d42", "path": "#9a7b55", "fence": "#8a6a45", "rail": "#6a6a6e", "bridge": "#8a6a45", "wall": "#8a8a86", "pipe": "#6a7a8a", "lamps": "#2f3338", "stones": "#8e9094"}


def catmull(points, sub):
    if sub <= 0 or len(points) < 3:
        return [tuple(p) for p in points]
    pts = [tuple(p) for p in points]
    ext = [pts[0]] + pts + [pts[-1]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for s in range(sub):
            t = s / float(sub)
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t ** 3) for k in range(3)))
    out.append(pts[-1])
    return out


def resample(points, spacing, closed=False):
    pts = list(points) + ([points[0]] if closed else [])
    out, carry = [], 0.0
    for a, b in zip(pts, pts[1:]):
        seg = [b[k] - a[k] for k in range(3)]
        ln = math.sqrt(sum(c * c for c in seg))
        if ln < 1e-6:
            continue
        d = [c / ln for c in seg]
        pos = spacing - carry if carry else 0.0
        while pos <= ln + 1e-6:
            out.append((tuple(a[k] + d[k] * pos for k in range(3)), tuple(d)))
            pos += spacing
        carry = (ln - (pos - spacing)) % spacing if ln > 0 else carry
    if not out or math.dist(out[-1][0], pts[-1]) > spacing * 0.3:
        d = [pts[-1][k] - pts[-2][k] for k in range(3)]
        ln = math.sqrt(sum(c * c for c in d)) or 1.0
        out.append((tuple(pts[-1]), tuple(c / ln for c in d)))
    return out


def basis_along(d, roll_up=(0, 1, 0)):
    """Basis whose X axis follows direction d (length axis), Y stays up. Returns text for Transform3D (rows) without origin."""
    ex = d
    n = math.sqrt(sum(c * c for c in ex)) or 1.0
    ex = tuple(c / n for c in ex)
    ez = (ex[1] * roll_up[2] - ex[2] * roll_up[1], ex[2] * roll_up[0] - ex[0] * roll_up[2], ex[0] * roll_up[1] - ex[1] * roll_up[0])
    m = math.sqrt(sum(c * c for c in ez))
    if m < 1e-6:
        ez, m = (0.0, 0.0, 1.0), 1.0
    ez = tuple(c / m for c in ez)
    ey = (ez[1] * ex[2] - ez[2] * ex[1], ez[2] * ex[0] - ez[0] * ex[2], ez[0] * ex[1] - ez[1] * ex[0])
    return ex, ey, ez


def xform(d, origin):
    ex, ey, ez = basis_along(d)
    vals = [ex[0], ey[0], ez[0], ex[1], ey[1], ez[1], ex[2], ey[2], ez[2], origin[0], origin[1], origin[2]]
    return "Transform3D(%s)" % ", ".join(f(round(v, 5)) for v in vals)


def curve_sub(sb, pts):
    flat = []
    for p in pts:
        flat += [0, 0, 0, 0, 0, 0, p[0], p[1], p[2]]
    return sb.sub("Curve3D", lines=["_data = {", '"points": PackedVector3Array(%s),' % ", ".join(f(round(v, 4)) for v in flat), '"tilts": PackedFloat32Array(%s)' % ", ".join("0" for _ in pts), "}", "up_vector_enabled = true"], hint="curve")


def polygon_text(poly):
    return "PackedVector2Array(%s)" % ", ".join("%s, %s" % (f(round(x, 4)), f(round(y, 4))) for x, y in poly)


def csg_path(sb, name, path_name, poly, mat, closed=False, collide=True, interval=1.0, smooth=True):
    props = {"polygon": polygon_text(poly), "mode": "2", "path_node": 'NodePath("../%s")' % path_name, "path_interval_type": "0", "path_interval": f(interval),
             "path_rotation": "2", "path_local": "false", "path_joined": "true" if closed else "false", "smooth_faces": "true" if smooth else "false",
             "material": 'SubResource("%s")' % mat, "use_collision": "true" if collide else "false"}
    return sb.node(name, "CSGPolygon3D", ".", props)


def circle_poly(r, n=12, cx=0.0, cy=0.0):
    return [(cx + math.cos(i * 2 * math.pi / n) * r, cy + math.sin(i * 2 * math.pi / n) * r) for i in range(n)]


def build_path(a):
    kind = str(a.get("kind") or "").lower()
    if kind not in PATH_KINDS:
        raise ToolkitError("unknown kind '%s'" % kind, "Kinds: " + ", ".join(PATH_KINDS))
    raw = [[float(c) for c in pt] for pt in as_list(a.get("points"))]
    if len(raw) < 2 or any(len(pt) != 3 for pt in raw):
        raise ToolkitError("`points` needs at least two [x, y, z] points")
    if len(raw) > 400:
        raise ToolkitError("too many points (max 400)")
    closed = boolean(a.get("closed"), False)
    pts = catmull(raw + ([raw[0]] if closed else []), int(num(a.get("smooth"), 0, 0, 24, True)))
    if closed and len(pts) > 1:
        pts = pts[:-1]
    name = ident(a.get("name") or kind.title(), "Path")
    color = a.get("color") or _DEFAULT_COLOR[kind]
    sb = SB(name, "Node3D", "path_" + name)
    B = Boxes(sb)
    width = num(a.get("width"), {"road": 6.0, "path": 2.0, "bridge": 3.0, "rail": 2.4, "wall": 0.8, "pipe": 0.4}.get(kind, 1.0), 0.05, 100)
    height = num(a.get("height"), {"fence": 1.2, "wall": 2.5, "lamps": 4.5, "stones": 0.15, "bridge": 1.0}.get(kind, 1.0), 0.05, 50)
    thick = num(a.get("thickness"), {"road": 0.25, "path": 0.12}.get(kind, 0.1), 0.01, 5)
    spacing = num(a.get("spacing"), {"fence": 2.0, "lamps": 12.0, "stones": 1.0, "bridge": 0.55, "rail": 0.9, "pipe": 6.0}.get(kind, 2.0), 0.1, 200)
    sb.node("Path3D", "Path3D", ".", {"curve": 'SubResource("%s")' % curve_sub(sb, [(p[0], p[1] + (0.02 if kind in ("road", "path") else 0.0), p[2]) for p in pts])})
    # fix: Path3D is created before curve id exists in render order -> subs always render first, fine.
    m = B.mat("main", color, rough=0.9, metallic=0.4 if kind in ("rail", "pipe") else 0.0)
    count = 0
    if kind == "road":
        csg_path(sb, "Surface", "Path3D", [(-width / 2, 0), (width / 2, 0), (width / 2, -thick), (-width / 2, -thick)], m, closed, interval=2.0, smooth=False)
        line = B.mat("line", "#e8d36a", emission="#a89030")
        for i, (pos, d) in enumerate(resample(pts, spacing or 3.0, closed)):
            if i % 2 == 0:
                sb.node("Line%d" % i, "MeshInstance3D", ".", {"transform": xform(d, (pos[0], pos[1] + 0.04, pos[2])), "mesh": 'SubResource("%s")' % B.box_mesh((spacing * 0.5 if spacing else 1.5, 0.02, 0.18), line)})
                count += 1
    elif kind == "path":
        r = width / 2
        csg_path(sb, "Surface", "Path3D", [(-r, -thick), (-r * 0.9, 0.0), (r * 0.9, 0.0), (r, -thick)], m, closed, interval=1.5)
    elif kind == "wall":
        w2 = width / 2
        csg_path(sb, "Wall", "Path3D", [(-w2, 0), (-w2 * 0.8, height), (w2 * 0.8, height), (w2, 0)], m, closed, interval=1.5, smooth=False)
    elif kind == "pipe":
        r = width / 2
        csg_path(sb, "Pipe", "Path3D", circle_poly(r, 12, 0, r), m, closed, interval=1.0)
        jm = B.mat("joint", "#4a5560", metallic=0.5)
        for i, (pos, d) in enumerate(resample(pts, spacing, closed)):
            sb.node("Joint%d" % i, "MeshInstance3D", ".", {"transform": xform(d, (pos[0], pos[1] + r, pos[2])), "mesh": 'SubResource("%s")' % B.box_mesh((0.35, r * 2.5, r * 2.5), jm)})
            count += 1
    elif kind == "rail":
        gauge = width / 2
        rm = B.mat("rail", "#9aa0a8", metallic=0.7, rough=0.4)
        bm = B.mat("ballast", "#6b6760")
        csg_path(sb, "Ballast", "Path3D", [(-width * 0.9, -0.25), (-width * 0.55, 0.0), (width * 0.55, 0.0), (width * 0.9, -0.25)], bm, closed, interval=2.0, smooth=False)
        for side, nm in ((-1, "RailL"), (1, "RailR")):
            csg_path(sb, nm, "Path3D", [(side * gauge / 2 - 0.04, 0.2), (side * gauge / 2 + 0.04, 0.2), (side * gauge / 2 + 0.04, 0.0), (side * gauge / 2 - 0.04, 0.0)], rm, closed, collide=False, interval=1.5, smooth=False)
        for i, (pos, d) in enumerate(resample(pts, spacing, closed)):
            sb.node("Sleeper%d" % i, "MeshInstance3D", ".", {"transform": xform(d, (pos[0], pos[1] + 0.0, pos[2])), "mesh": 'SubResource("%s")' % B.box_mesh((0.22, 0.1, width * 1.25), m)})
            count += 1
    elif kind in ("fence", "bridge"):
        body = sb.node("Body", "StaticBody3D", ".", {})
        posts = resample(pts, spacing if kind == "fence" else 2.0, closed)
        for i, (pos, d) in enumerate(posts):
            offs = [0.0] if kind == "fence" else [-width / 2, width / 2]
            for oi, off in enumerate(offs):
                ex, ey, ez = basis_along(d)
                x, y, z = pos[0] + ez[0] * off, pos[1], pos[2] + ez[2] * off
                B.box("Body", "Post%d_%d" % (i, oi), (x, y + height / 2, z), (0.14, height, 0.14), m, True, body="Body")
                count += 1
        rails = 2 if kind == "fence" else 1
        for (p0, _d0), (p1, _d1) in zip(posts, posts[1:] + ([posts[0]] if closed else [])):
            seg = [p1[k] - p0[k] for k in range(3)]
            ln = math.sqrt(sum(c * c for c in seg))
            if ln < 0.05:
                continue
            offs = [0.0] if kind == "fence" else [-width / 2, width / 2]
            ex, ey, ez = basis_along(seg)
            for off in offs:
                for r in range(rails):
                    ry = height * (0.4 + 0.45 * r) if kind == "fence" else height * 0.92
                    mid = [(p0[k] + p1[k]) / 2 + ez[k] * off for k in range(3)]
                    nm = "Rail%d_%d_%d" % (count, r, int(off * 10))
                    sb.node(nm, "MeshInstance3D", "Body", {"transform": xform(seg, (mid[0], mid[1] + ry, mid[2])), "mesh": 'SubResource("%s")' % B.box_mesh((ln, 0.08, 0.06), m)})
                    sb.node(nm + "_col", "CollisionShape3D", "Body", {"transform": xform(seg, (mid[0], mid[1] + ry, mid[2])), "shape": 'SubResource("%s")' % B.box_shape((ln, 0.08, 0.06))})
                    count += 1
        if kind == "bridge":
            dm = B.mat("deck", "#9a7a50")
            for i, (pos, d) in enumerate(resample(pts, spacing, closed)):
                sb.node("Plank%d" % i, "MeshInstance3D", "Body", {"transform": xform(d, (pos[0], pos[1] - 0.05, pos[2])), "mesh": 'SubResource("%s")' % B.box_mesh((spacing * 0.9, 0.1, width), dm)})
                sb.node("Plank%d_col" % i, "CollisionShape3D", "Body", {"transform": xform(d, (pos[0], pos[1] - 0.05, pos[2])), "shape": 'SubResource("%s")' % B.box_shape((spacing * 0.9 + 0.05, 0.1, width))})
                count += 1
    elif kind == "lamps":
        pm = B.mat("pole", color, metallic=0.5, rough=0.5)
        gm = B.mat("lamp", "#fff2c0", emission="#ffd070")
        for i, (pos, d) in enumerate(resample(pts, spacing, closed)):
            ex, ey, ez = basis_along(d)
            side = (width if a.get("width") else 1.5) * (1 if i % 2 == 0 else -1)
            x, y, z = pos[0] + ez[0] * side, pos[1], pos[2] + ez[2] * side
            lamp = sb.node("Lamp%d" % i, "Node3D", ".", {"position": V3(x, y, z)})
            B.cylinder(lamp, "Pole", (0, height / 2, 0), 0.06, height, pm)
            B.sphere(lamp, "Bulb", (0, height + 0.1, 0), 0.22, gm)
            sb.node("Light", "OmniLight3D", lamp, {"position": V3(0, height + 0.1, 0), "light_color": C("#ffd9a0"), "omni_range": f(height * 2.2), "light_energy": "1.3"})
            count += 1
    elif kind == "stones":
        rng = random.Random(int(num(a.get("seed"), 7, 0, 10 ** 9, True)))
        body = sb.node("Body", "StaticBody3D", ".", {})
        for i, (pos, d) in enumerate(resample(pts, spacing, closed)):
            r = rng.uniform(0.28, 0.45)
            B.cylinder("Body", "Stone%d" % i, (pos[0] + rng.uniform(-0.15, 0.15), pos[1] - height / 2 + 0.02, pos[2] + rng.uniform(-0.15, 0.15)), r, height, m, True, body="Body")
            count += 1
    return sb, dict(kind=kind, points=len(pts), pieces=count, closed=closed)


@tool(G, "ms_godot_path_builder",
      "Build linear structures along waypoints as a scene: road (CSG path with dashed centre line), dirt path, fence, railway (ballast, rails, sleepers), plank bridge with rails, wall, pipe with joints, street lamps (with OmniLights) or stepping stones. "
      "Optional Catmull-Rom smoothing, closed loops, width/height/spacing/colour. Surfaces use native Path3D + CSGPolygon3D so they stay editable by dragging curve points.",
      {"points": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}, "description": "[[x,y,z], ...] (at least 2)."}, "kind": {"type": "string", "enum": PATH_KINDS},
       "width": {"type": "number"}, "height": {"type": "number"}, "thickness": {"type": "number"}, "spacing": {"type": "number"}, "smooth": {"type": "integer"}, "closed": {"type": "boolean"},
       "color": {"type": ["string", "array"]}, "seed": {"type": "integer"}, "name": {"type": "string"}, "scene_path": {"type": "string"}, "into_scene": INTO, "parent": PARENT, "overwrite": OVERWRITE}, ["points", "kind"], writes=True, local=True)
def path_builder(args, ctx):
    p = _proj(args, ctx)
    sb, info = build_path(args)
    out = Out(p, args)
    scene, top = target_scene(p, args, sb, "res://scenes/paths/%s.tscn" % sb.nodes[0]["name"].lower(), out)
    return out.done(scene=scene, root=top, **info)


# ───────────────────────── props + scatter ─────────────────────────
PROPS = ["tree", "pine", "rock", "bush", "crystal", "mushroom", "lamp_post", "pillar", "barrel", "flower"]


def prop_scene(prop):
    sb = SB("Prop_" + prop.title().replace("_", ""), "Node3D", "prop_" + prop)
    B = Boxes(sb)
    r = "."
    if prop == "tree":
        body = sb.node("Body", "StaticBody3D", r)
        B.cylinder("Body", "Trunk", (0, 1.1, 0), 0.22, 2.2, B.mat("trunk", "#6b4a2b"), True, body="Body", top=0.16)
        lm = B.mat("leaf", "#3f9a3a")
        for i, (y, rad) in enumerate(((2.6, 1.3), (3.4, 1.0), (4.0, 0.7))):
            B.sphere(r, "Leaves%d" % i, (0, y, 0), rad, lm)
    elif prop == "pine":
        body = sb.node("Body", "StaticBody3D", r)
        B.cylinder("Body", "Trunk", (0, 0.8, 0), 0.18, 1.6, B.mat("trunk", "#5a3d22"), True, body="Body")
        lm = B.mat("needle", "#2d6a3a")
        for i, (y, rad, h) in enumerate(((2.0, 1.3, 1.8), (3.0, 1.0, 1.6), (3.9, 0.7, 1.4))):
            B.cylinder(r, "Cone%d" % i, (0, y, 0), rad, h, lm, top=0.0)
    elif prop == "rock":
        body = sb.node("Body", "StaticBody3D", r)
        B.sphere("Body", "Rock", (0, 0.35, 0), 0.7, B.mat("rock", "#8e9094", rough=1.0), squash=0.7, collide=True, body="Body")
        B.sphere(r, "Rock2", (0.55, 0.15, 0.2), 0.35, B.mat("rock", "#8e9094", rough=1.0), squash=0.8)
    elif prop == "bush":
        bm = B.mat("bush", "#4a9a3d")
        for i, (x, z, rad) in enumerate(((0, 0, 0.6), (0.5, 0.2, 0.45), (-0.4, 0.3, 0.4))):
            B.sphere(r, "Leaf%d" % i, (x, rad * 0.8, z), rad, bm)
    elif prop == "crystal":
        cm = B.mat("crystal", "#6ae0ff", emission="#2090d0", alpha=0.85, rough=0.1)
        for i, (x, z, h, tilt) in enumerate(((0, 0, 1.6, 0.0), (0.35, 0.1, 1.0, 0.35), (-0.3, -0.15, 0.8, -0.4))):
            B.cylinder(r, "Shard%d" % i, (x, h / 2, z), 0.22, h, cm, rot=(0, 0, tilt), top=0.0)
    elif prop == "mushroom":
        B.cylinder(r, "Stem", (0, 0.2, 0), 0.08, 0.4, B.mat("stem", "#efe6d2"))
        B.sphere(r, "Cap", (0, 0.45, 0), 0.28, B.mat("cap", "#d94a3d"), squash=0.6)
    elif prop == "lamp_post":
        body = sb.node("Body", "StaticBody3D", r)
        B.cylinder("Body", "Pole", (0, 2.0, 0), 0.07, 4.0, B.mat("pole", "#2f3338", metallic=0.5), True, body="Body")
        B.sphere(r, "Bulb", (0, 4.15, 0), 0.22, B.mat("bulb", "#fff2c0", emission="#ffd070"))
        sb.node("Light", "OmniLight3D", r, {"position": V3(0, 4.15, 0), "light_color": C("#ffd9a0"), "omni_range": "9.0", "light_energy": "1.3"})
    elif prop == "pillar":
        body = sb.node("Body", "StaticBody3D", r)
        sm = B.mat("stone", "#b8b4aa")
        B.box("Body", "Base", (0, 0.2, 0), (1.0, 0.4, 1.0), sm, True, body="Body")
        B.cylinder("Body", "Shaft", (0, 2.0, 0), 0.35, 3.2, sm, True, body="Body")
        B.box("Body", "Cap", (0, 3.8, 0), (1.0, 0.4, 1.0), sm, True, body="Body")
    elif prop == "barrel":
        body = sb.node("Body", "StaticBody3D", r)
        B.cylinder("Body", "Barrel", (0, 0.45, 0), 0.38, 0.9, B.mat("wood", "#8a5a2b"), True, body="Body", top=0.32)
        bm = B.mat("band", "#3a3d42", metallic=0.6)
        B.cylinder(r, "BandTop", (0, 0.75, 0), 0.355, 0.06, bm)
        B.cylinder(r, "BandBottom", (0, 0.15, 0), 0.355, 0.06, bm)
    elif prop == "flower":
        B.cylinder(r, "Stem", (0, 0.2, 0), 0.015, 0.4, B.mat("stemg", "#3f8a3a"))
        B.sphere(r, "Head", (0, 0.42, 0), 0.1, B.mat("petal", "#ffcf3f"), squash=0.5)
    return sb


def build_scatter(a, prefab_res, name, count, shape, center, size, radius):
    sb = SB(name, "Node3D", "scatter_" + name)
    rng = random.Random(int(num(a.get("seed"), 1, 0, 10 ** 9, True)))
    min_d = num(a.get("min_distance"), 1.5, 0.0, 500)
    smin, smax = num(a.get("scale_min"), 0.8, 0.05, 50), num(a.get("scale_max"), 1.3, 0.05, 50)
    yaw = boolean(a.get("random_yaw"), True)
    sink = num(a.get("sink"), 0.0, -5, 10)
    ground = num(a.get("ground_y"), center[1], -1e5, 1e5)
    placed, tries = [], 0
    while len(placed) < count and tries < count * 40:
        tries += 1
        if shape == "circle":
            ang, rr = rng.uniform(0, 2 * math.pi), radius * math.sqrt(rng.random())
            x, z = center[0] + math.cos(ang) * rr, center[2] + math.sin(ang) * rr
        else:
            x, z = center[0] + rng.uniform(-size[0] / 2, size[0] / 2), center[2] + rng.uniform(-size[1] / 2, size[1] / 2)
        if min_d > 0 and any((x - px) ** 2 + (z - pz) ** 2 < min_d * min_d for px, pz in placed):
            continue
        placed.append((x, z))
        s = rng.uniform(smin, smax)
        ry = rng.uniform(0, 2 * math.pi) if yaw else 0.0
        c, sn = math.cos(ry) * s, math.sin(ry) * s
        tr = "Transform3D(%s, 0, 0, %s, 0, %s, 0, %s, %s, %s, %s, %s)" % (f(round(c, 5)), f(round(-sn, 5)), f(round(s, 5)), f(round(sn, 5)), f(round(c, 5)), f(round(x, 4)), f(round(ground - sink, 4)), f(round(z, 4)))
        # Transform3D rows: (c,0,-sn)? build explicit 9-values row-major: [c,0,sn, 0,s,0, -sn,0,c]
        tr = "Transform3D(%s)" % ", ".join(f(round(v, 5)) for v in (c, 0, sn, 0, s, 0, -sn, 0, c, x, ground - sink, z))
        sb.node("%s%d" % (name, len(placed)), None, ".", {"transform": tr}, instance=prefab_res)
    return sb, placed


_SNAP_GD = '''extends SceneTree
var frames := 0
var targets: Array = []
var ground: Node
var holder: Node

func _initialize() -> void:
	ground = (load("@@GROUND@@") as PackedScene).instantiate()
	root.add_child(ground)
	holder = (load("@@SCATTER@@") as PackedScene).instantiate()
	root.add_child(holder)

func _physics_process(_delta: float) -> bool:
	frames += 1
	if frames < 3:
		return false
	var space := root.get_world_3d().direct_space_state
	var out := {}
	for n in holder.get_children():
		if not (n is Node3D):
			continue
		var p: Vector3 = n.global_position
		var q := PhysicsRayQueryParameters3D.create(Vector3(p.x, @@TOP@@, p.z), Vector3(p.x, @@BOTTOM@@, p.z))
		var hit := space.intersect_ray(q)
		if hit.is_empty():
			out[str(n.name)] = null
		else:
			var h: Vector3 = hit["position"]
			var nrm: Vector3 = hit["normal"]
			out[str(n.name)] = [h.x, h.y, h.z, nrm.x, nrm.y, nrm.z]
	print("MS_SNAP:" + JSON.stringify(out))
	return true
'''


def snap_to_ground(proj, ground_scene, scatter_scene, top=800.0, bottom=-400.0):
    from toolkit_godot_pro import godot_run
    import json
    gd = _SNAP_GD.replace("@@GROUND@@", ground_scene).replace("@@SCATTER@@", scatter_scene).replace("@@TOP@@", f(top)).replace("@@BOTTOM@@", f(bottom))
    rc, so, se, timed = godot_run(proj, gd, 90)
    for ln in so.splitlines():
        if ln.startswith("MS_SNAP:"):
            return json.loads(ln[len("MS_SNAP:"):])
    raise ToolkitError("ground snapping failed", ((so + se).strip()[-300:]) or "Godot produced no result")


@tool(G, "ms_godot_scatter",
      "Scatter props over an area as a scene: built-in props (tree, pine, rock, bush, crystal, mushroom, lamp_post, pillar, barrel, flower - saved once as reusable scenes) or your own `prefab` scene. Rectangle or circle area, count, minimum spacing, "
      "random yaw, scale range, sink, seed. `ground_scene` snaps every instance to the surface with real physics raycasts (needs the Godot executable) and can align to the surface normal.",
      {"prefab": {"type": "string", "description": "res:// scene to instance instead of a built-in prop."}, "prop": {"type": "string", "enum": PROPS}, "center": VEC3, "size": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
       "radius": {"type": "number"}, "count": {"type": "integer"}, "min_distance": {"type": "number"}, "scale_min": {"type": "number"}, "scale_max": {"type": "number"}, "random_yaw": {"type": "boolean"}, "sink": {"type": "number"},
       "ground_y": {"type": "number"}, "ground_scene": {"type": "string", "description": "res:// scene with collision (terrain, level) to drop the props onto."}, "align_to_normal": {"type": "boolean"},
       "max_slope_degrees": {"type": "number"}, "seed": {"type": "integer"}, "name": {"type": "string"}, "scene_path": {"type": "string"}, "into_scene": INTO, "parent": PARENT, "overwrite": OVERWRITE}, [], writes=True, local=True)
def scatter(args, ctx):
    p = _proj(args, ctx)
    prop = str(args.get("prop") or "").lower()
    prefab = args.get("prefab")
    if not prefab and prop not in PROPS:
        raise ToolkitError("give `prop` (%s) or `prefab`" % ", ".join(PROPS))
    count = int(num(args.get("count"), 30, 1, 3000, True))
    center = [float(x) for x in as_list(args.get("center"))] + [0, 0, 0]
    size = [float(x) for x in as_list(args.get("size"))] or [40.0, 40.0]
    radius = num(args.get("radius"), 0.0, 0, 5000)
    shape = "circle" if radius > 0 else "rect"
    name = ident(args.get("name") or ("Scatter_" + (prop or "prefab")), "Scatter")
    out = Out(p, args)
    if prefab:
        pres = norm_res(prefab, ".tscn")
        if not os.path.isfile(_abs(p, pres)):
            raise ToolkitError("prefab not found: %s" % prefab)
    else:
        pres = "res://scenes/props/ms_%s.tscn" % prop
        if not os.path.isfile(_abs(p, pres)) or boolean(args.get("overwrite"), False):
            out.put(pres, prop_scene(prop).render(), "prop scene", allow_overwrite=True)
    sb, placed = build_scatter(args, pres, name, count, shape, center, size, radius)
    snapped = None
    out_scene, top = target_scene(p, args, sb, "res://scenes/scatter/%s.tscn" % name.lower(), out)
    if args.get("ground_scene") and not args.get("dry_run"):
        g = norm_res(args["ground_scene"], ".tscn")
        if not os.path.isfile(_abs(p, g)):
            raise ToolkitError("ground scene not found: %s" % g)
        if args.get("into_scene"):
            raise ToolkitError("ground snapping works on a standalone scatter scene", "Omit `into_scene`, then instance the scatter scene in your level.")
        hits = snap_to_ground(p, g, out_scene)
        sc = Scene(_read(_abs(p, out_scene)))
        max_slope = math.radians(num(args.get("max_slope_degrees"), 90, 0, 90))
        align = boolean(args.get("align_to_normal"), False)
        kept, dropped = 0, 0
        for n in list(sc.nodes()):
            if n["attrs"].get("parent") != ".":
                continue
            h = hits.get(n["attrs"]["name"])
            body = n["body"]
            ti = next((i for i, ln in enumerate(body) if ln.startswith("transform = Transform3D(")), None)
            if h is None or ti is None or math.acos(max(-1, min(1, h[4]))) > max_slope:
                sc.blocks.remove(n)
                dropped += 1
                continue
            vals = [float(x) for x in body[ti][len("transform = Transform3D("):-1].split(",")]
            sink = num(args.get("sink"), 0.0, -5, 10)
            vals[9], vals[10], vals[11] = h[0], h[1] - sink, h[2]
            if align:
                ny = (h[3], h[4], h[5])
                s = math.sqrt(vals[0] ** 2 + vals[6] ** 2) or 1.0
                ex, ey, ez = basis_along((vals[0], 0, -vals[6]), ny) if False else (None, None, None)
                up = ny
                fwd = (vals[0], 0.0, -vals[6])
                # x axis = fwd projected onto the surface plane
                dot = sum(fwd[k] * up[k] for k in range(3))
                xa = tuple(fwd[k] - dot * up[k] for k in range(3))
                xl = math.sqrt(sum(c * c for c in xa)) or 1.0
                xa = tuple(c / xl * s for c in xa)
                za = (xa[1] * up[2] - xa[2] * up[1], xa[2] * up[0] - xa[0] * up[2], xa[0] * up[1] - xa[1] * up[0])
                zl = math.sqrt(sum(c * c for c in za)) or 1.0
                za = tuple(c / zl * s for c in za)
                ya = tuple(c * s for c in up)
                vals[:9] = [xa[0], ya[0], za[0], xa[1], ya[1], za[1], xa[2], ya[2], za[2]]
            body[ti] = "transform = Transform3D(%s)" % ", ".join(f(round(v, 5)) for v in vals)
            kept += 1
        out.put(out_scene, sc.text().rstrip("\n") + "\n", "scene (snapped)", allow_overwrite=True)
        snapped = {"kept": kept, "dropped": dropped}
        count = kept
    return out.done(scene=out_scene, root=top, prop=prop or None, prefab=pres, instances=len(placed) if not snapped else snapped["kept"], snapped=snapped)


# ───────────────────────── model tools (headless scene editing) ─────────────────────────
MODEL_ACTIONS = ["stats", "array", "mirror", "align", "distribute", "group", "ungroup", "randomize", "rename", "colliders", "visibility_range", "set_material", "center_pivot", "static"]

_MODEL_GD = r'''extends SceneTree
var P = {}
var R = {}
var scene_root: Node

func _vec(n: Node, a, d := 0.0):
	if n is Node2D:
		return Vector2(float(a[0]) if a.size() > 0 else d, float(a[1]) if a.size() > 1 else d)
	return Vector3(float(a[0]) if a.size() > 0 else d, float(a[1]) if a.size() > 1 else d, float(a[2]) if a.size() > 2 else d)

func _own(n: Node, owner_node: Node) -> void:
	n.owner = owner_node
	for c in n.get_children():
		_own(c, owner_node)

func _find(path: String) -> Node:
	if path == "." or path == "":
		return scene_root
	return scene_root.get_node_or_null(path)

func _targets() -> Array:
	var out = []
	for t in P.get("targets", []):
		var n = _find(str(t))
		if n == null:
			R["error"] = "target not found: " + str(t)
			return []
		out.append(n)
	return out

func _aabb_of(n: Node) -> AABB:
	var box = AABB()
	var first = true
	var stack = [n]
	while not stack.is_empty():
		var c = stack.pop_back()
		if c is MeshInstance3D and c.mesh:
			var a: AABB = c.global_transform * c.mesh.get_aabb()
			box = a if first else box.merge(a)
			first = false
		for k in c.get_children():
			stack.append(k)
	return box

func _tris(n: Node) -> int:
	var total = 0
	var stack = [n]
	while not stack.is_empty():
		var c = stack.pop_back()
		if c is MeshInstance3D and c.mesh:
			for s in c.mesh.get_surface_count():
				var arr = c.mesh.surface_get_arrays(s)
				if arr.size() > Mesh.ARRAY_INDEX and arr[Mesh.ARRAY_INDEX] != null and arr[Mesh.ARRAY_INDEX].size() > 0:
					total += arr[Mesh.ARRAY_INDEX].size() / 3
				elif arr.size() > 0 and arr[Mesh.ARRAY_VERTEX] != null:
					total += arr[Mesh.ARRAY_VERTEX].size() / 3
		for k in c.get_children():
			stack.append(k)
	return total

func _initialize() -> void:
	P = JSON.parse_string(@@PARAMS@@)
	var ps = load(P["scene"])
	if ps == null:
		R["error"] = "cannot load scene"
		_finish()
		return
	scene_root = ps.instantiate()
	root.add_child(scene_root)
	var act: String = P["action"]
	var ts = _targets()
	if R.has("error"):
		_finish()
		return
	var changed = false
	match act:
		"stats":
			var rows = []
			for n in (ts if not ts.is_empty() else [scene_root]):
				var counts = {}
				var stack = [n]
				var total = 0
				while not stack.is_empty():
					var c = stack.pop_back()
					counts[c.get_class()] = counts.get(c.get_class(), 0) + 1
					total += 1
					for k in c.get_children():
						stack.append(k)
				var box = _aabb_of(n)
				rows.append({"node": str(scene_root.get_path_to(n)), "nodes": total, "classes": counts, "triangles": _tris(n), "size": [box.size.x, box.size.y, box.size.z], "center": [box.get_center().x, box.get_center().y, box.get_center().z]})
			R["stats"] = rows
		"array":
			var mode: String = P.get("mode", "linear")
			var count: int = int(P.get("count", 3))
			var made = 0
			for src in ts:
				var parent = src.get_parent()
				var base = src.position
				var off = _vec(src, P.get("offset", [2, 0, 0]))
				var idx = 0
				var combos = []
				if mode == "grid":
					var g: Array = P.get("grid", [3, 1, 3])
					var sp = _vec(src, P.get("spacing", [2, 2, 2]), 2.0)
					for x in int(g[0]):
						for y in (int(g[1]) if g.size() > 1 else 1):
							for z in (int(g[2]) if g.size() > 2 else 1):
								if x == 0 and y == 0 and z == 0:
									continue
								combos.append(Vector3(x * sp.x, y * sp.y, z * sp.z) if src is Node3D else Vector2(x * sp.x, y * sp.y))
				elif mode == "radial":
					var rad: float = float(P.get("radius", 4.0))
					for i in range(1, count):
						var ang = TAU * i / count
						if src is Node3D:
							combos.append(Vector3(cos(ang) * rad - rad, 0, sin(ang) * rad))
						else:
							combos.append(Vector2(cos(ang) * rad - rad, sin(ang) * rad))
				else:
					for i in range(1, count):
						combos.append(off * i)
				for c in combos:
					var d = src.duplicate()
					d.name = str(src.name) + "_" + str(idx + 1)
					parent.add_child(d)
					d.position = base + c
					if mode == "radial" and src is Node3D:
						d.rotation.y = -atan2(c.z, c.x + float(P.get("radius", 4.0)))
					_own(d, scene_root)
					idx += 1
					made += 1
			R["created"] = made
			changed = made > 0
		"mirror":
			var axis: int = {"x": 0, "y": 1, "z": 2}.get(str(P.get("axis", "x")), 0)
			var pivot: float = float(P.get("pivot", 0.0))
			var made2 = 0
			for src in ts:
				var d = src.duplicate()
				d.name = str(src.name) + "_mirror"
				src.get_parent().add_child(d)
				var p = src.position
				p[axis] = 2.0 * pivot - p[axis]
				d.position = p
				if d is Node3D:
					var s: Vector3 = d.scale
					s[axis] = -s[axis]
					d.scale = s
				elif d is Node2D and axis < 2:
					var s2: Vector2 = d.scale
					s2[axis] = -s2[axis]
					d.scale = s2
				_own(d, scene_root)
				made2 += 1
			R["created"] = made2
			changed = made2 > 0
		"align", "distribute":
			var axis2: int = {"x": 0, "y": 1, "z": 2}.get(str(P.get("axis", "x")), 0)
			if ts.size() < 2:
				R["error"] = "need at least two targets"
			else:
				var vals = []
				for n in ts:
					vals.append(n.position[axis2])
				if act == "align":
					var mode2: String = P.get("mode", "center")
					var ref: float = vals.min() if mode2 == "min" else (vals.max() if mode2 == "max" else (vals.min() + vals.max()) / 2.0)
					for n in ts:
						var p2 = n.position
						p2[axis2] = ref
						n.position = p2
				else:
					var sorted = ts.duplicate()
					sorted.sort_custom(func(a, b): return a.position[axis2] < b.position[axis2])
					var lo: float = sorted[0].position[axis2]
					var hi: float = sorted[sorted.size() - 1].position[axis2]
					for i in sorted.size():
						var p3 = sorted[i].position
						p3[axis2] = lo + (hi - lo) * i / float(sorted.size() - 1)
						sorted[i].position = p3
				changed = true
		"group":
			if ts.is_empty():
				R["error"] = "group needs targets"
			else:
				var parent2 = ts[0].get_parent()
				var g3 = Node3D.new() if ts[0] is Node3D else Node2D.new()
				g3.name = str(P.get("name", "Group"))
				parent2.add_child(g3)
				var centroid = ts[0].position * 0.0
				for n in ts:
					centroid += n.position
				centroid /= ts.size()
				g3.position = centroid
				for n in ts:
					var keep = n.position
					n.reparent(g3, false)
					n.position = keep - centroid
				_own(g3, scene_root)
				R["group"] = str(scene_root.get_path_to(g3))
				changed = true
		"ungroup":
			for n in ts:
				var par = n.get_parent()
				for c in n.get_children():
					c.reparent(par, true)
				n.queue_free()
				par.remove_child(n)
			_own(scene_root, scene_root)
			changed = not ts.is_empty()
		"randomize":
			var rng = RandomNumberGenerator.new()
			rng.seed = int(P.get("seed", 1))
			var jit: float = float(P.get("position_jitter", 0.0))
			for n in ts:
				if n is Node3D:
					if P.get("yaw", true):
						n.rotation.y = rng.randf() * TAU
					n.position += Vector3(rng.randf_range(-jit, jit), 0, rng.randf_range(-jit, jit))
					var s3 = rng.randf_range(float(P.get("scale_min", 1.0)), float(P.get("scale_max", 1.0)))
					n.scale = Vector3.ONE * s3
				elif n is Node2D:
					if P.get("yaw", true):
						n.rotation = rng.randf() * TAU
					n.position += Vector2(rng.randf_range(-jit, jit), rng.randf_range(-jit, jit))
					n.scale = Vector2.ONE * rng.randf_range(float(P.get("scale_min", 1.0)), float(P.get("scale_max", 1.0)))
			changed = not ts.is_empty()
		"rename":
			var i2 = 1
			for n in ts:
				var nm = str(n.name)
				if P.has("pattern"):
					nm = str(P["pattern"]).replace("{name}", nm).replace("{n}", str(i2))
				elif P.has("find"):
					nm = nm.replace(str(P["find"]), str(P.get("replace", "")))
				n.name = nm
				i2 += 1
			changed = not ts.is_empty()
		"colliders":
			var made3 = 0
			var kind: String = P.get("collider", "box")
			for n in ts:
				var meshes = []
				var st = [n]
				while not st.is_empty():
					var c = st.pop_back()
					if c is MeshInstance3D and c.mesh:
						meshes.append(c)
					for k in c.get_children():
						st.append(k)
				for m in meshes:
					for k in m.get_children():
						if (k is StaticBody3D) and P.get("replace", true):
							m.remove_child(k)
							k.queue_free()
					if kind == "convex":
						m.create_convex_collision(true, true)
					elif kind == "trimesh":
						m.create_trimesh_collision()
					else:
						var body = StaticBody3D.new()
						body.name = str(m.name) + "_Body"
						var cs = CollisionShape3D.new()
						cs.name = "Shape"
						var a: AABB = m.mesh.get_aabb()
						if kind == "sphere":
							var sh = SphereShape3D.new()
							sh.radius = max(a.size.x, a.size.z) / 2.0
							cs.shape = sh
						elif kind == "capsule":
							var sh2 = CapsuleShape3D.new()
							sh2.radius = max(a.size.x, a.size.z) / 2.0
							sh2.height = max(a.size.y, sh2.radius * 2.0)
							cs.shape = sh2
						else:
							var sh3 = BoxShape3D.new()
							sh3.size = a.size
							cs.shape = sh3
						cs.position = a.get_center()
						body.add_child(cs)
						m.add_child(body)
					made3 += 1
			_own(scene_root, scene_root)
			R["colliders"] = made3
			changed = made3 > 0
		"visibility_range":
			var ends: Array = P.get("distances", [60.0])
			for n in ts:
				var st2 = [n]
				while not st2.is_empty():
					var c2 = st2.pop_back()
					if c2 is GeometryInstance3D:
						c2.visibility_range_end = float(ends[0])
						c2.visibility_range_end_margin = float(P.get("margin", 4.0))
						c2.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
					for k in c2.get_children():
						st2.append(k)
			changed = not ts.is_empty()
		"set_material":
			var mat = load(str(P.get("material", "")))
			if mat == null:
				R["error"] = "material not found"
			else:
				for n in ts:
					var st3 = [n]
					while not st3.is_empty():
						var c3 = st3.pop_back()
						if c3 is GeometryInstance3D:
							c3.material_override = mat
						for k in c3.get_children():
							st3.append(k)
				changed = not ts.is_empty()
		"center_pivot":
			var pm: String = P.get("mode", "bottom")
			for n in ts:
				if not (n is Node3D):
					continue
				var box = _aabb_of(n)
				var par2 = n.get_parent()
				var anchor = box.get_center()
				if pm == "bottom":
					anchor.y = box.position.y
				elif pm == "top":
					anchor.y = box.end.y
				var holder = Node3D.new()
				holder.name = str(n.name)
				n.name = "Model"
				par2.add_child(holder)
				holder.global_position = anchor
				n.reparent(holder, true)
				_own(holder, scene_root)
			changed = not ts.is_empty()
		"static":
			for n in ts:
				var st4 = [n]
				while not st4.is_empty():
					var c4 = st4.pop_back()
					if c4 is GeometryInstance3D:
						c4.gi_mode = GeometryInstance3D.GI_MODE_DYNAMIC if P.get("off", false) else GeometryInstance3D.GI_MODE_STATIC
					for k in c4.get_children():
						st4.append(k)
			changed = not ts.is_empty()
	if changed and not R.has("error") and not P.get("dry", false):
		var out = PackedScene.new()
		var err = out.pack(scene_root)
		if err == OK:
			var serr = ResourceSaver.save(out, P.get("save_to", P["scene"]))
			R["saved"] = serr == OK
			R["save_error"] = serr
		else:
			R["error"] = "pack failed: " + str(err)
	_finish()

func _finish() -> void:
	print("MS_RESULT:" + JSON.stringify(R))
	quit(0)
'''


@tool(G, "ms_godot_model_tools",
      "Model/scene utilities on nodes of a saved scene, done by a headless Godot so transforms stay exact: stats (nodes, triangles, bounds), array (linear/grid/radial), mirror, align, distribute, group, ungroup, randomize (yaw/jitter/scale), "
      "rename, colliders (box/sphere/capsule/convex/trimesh), visibility_range (distance LOD), set_material, center_pivot (bottom/center/top) and static lighting flags. Works on `targets` (node paths; '.' = root); `save_to` writes a copy.",
      {"scene_path": {"type": "string"}, "action": {"type": "string", "enum": MODEL_ACTIONS}, "targets": {"type": "array", "items": {"type": "string"}}, "mode": {"type": "string", "description": "array: linear|grid|radial; align: min|center|max; center_pivot: bottom|center|top."},
       "axis": {"type": "string", "enum": ["x", "y", "z"]}, "count": {"type": "integer"}, "offset": {"type": "array", "items": {"type": "number"}}, "grid": {"type": "array", "items": {"type": "integer"}}, "spacing": {"type": "array", "items": {"type": "number"}},
       "radius": {"type": "number"}, "pivot": {"type": "number"}, "name": {"type": "string"}, "pattern": {"type": "string", "description": "rename pattern with {name} and {n}."}, "find": {"type": "string"}, "replace": {"type": "string"},
       "collider": {"type": "string", "enum": ["box", "sphere", "capsule", "convex", "trimesh"]}, "distances": {"type": "array", "items": {"type": "number"}}, "margin": {"type": "number"}, "material": {"type": "string"},
       "yaw": {"type": "boolean"}, "position_jitter": {"type": "number"}, "scale_min": {"type": "number"}, "scale_max": {"type": "number"}, "seed": {"type": "integer"}, "off": {"type": "boolean"}, "save_to": {"type": "string"}, "dry_run": {"type": "boolean"}, "preview_script": {"type": "boolean", "description": "With dry_run: return the generated GDScript."}},
      ["scene_path", "action"], writes=True, local=True)
def model_tools(args, ctx):
    import json
    from toolkit_godot_pro import godot_run, parse_gd_marker, gstr
    p = _proj(args, ctx)
    action = str(args.get("action") or "").lower()
    if action not in MODEL_ACTIONS:
        raise ToolkitError("unknown action '%s'" % action, "Actions: " + ", ".join(MODEL_ACTIONS))
    scene = norm_res(args.get("scene_path") or "", ".tscn")
    if not os.path.isfile(_abs(p, scene)):
        raise ToolkitError("scene not found: %s" % scene)
    prm = {k: v for k, v in args.items() if k not in ("scene_path", "project_path", "dry_run", "save_to")}
    prm["scene"] = scene
    if args.get("save_to"):
        prm["save_to"] = norm_res(args["save_to"], ".tscn")
    if args.get("dry_run"):
        prm["dry"] = True
    if action != "stats" and not as_list(args.get("targets")):
        raise ToolkitError("`targets` is required for %s" % action, "Node paths relative to the scene root, e.g. [\"Walls/Wall1\"].")
    script = _MODEL_GD.replace("@@PARAMS@@", gstr(json.dumps(prm)))
    if args.get("dry_run") and args.get("preview_script"):
        return {"dryRun": True, "script": script}
    rc, so, se, timed = godot_run(p, script, 90)
    res = parse_gd_marker(so)
    if res is None:
        raise ToolkitError("Godot did not return a result", ((so + se).strip()[-400:]) or "is the Godot executable configured (GODOT_PATH)?")
    if res.get("error"):
        raise ToolkitError(res["error"])
    out = {"action": action, "scene": scene, **{k: v for k, v in res.items() if k not in ("save_error",)}}
    if args.get("dry_run"):
        out["dryRun"] = True
    return out
