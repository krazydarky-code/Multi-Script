"""studkit: block / stud creature builder for Blender 4.2+ (tested on 5.1). 1 Blender unit = 1 Roblox stud.

A creature is built only from straight blocks (boxes, tapered boxes, segments, slabs). Every block has one colour
and one bone. finalize() merges the blocks into ONE MESH PER COLOUR, rigidly skinned to an armature (each block
follows exactly one bone), with UVs where 1 UV unit = 1 stud, so a tiling stud texture reads like toy bricks.

Axes: the creature faces -Y (Blender's front view), +Z is up, +X is the creature's LEFT side.
Mirroring: pass mirror=True and give the LEFT (+X) piece; the right copy goes to the bone with _L swapped to _R.
"""
import bpy, bmesh, math, os
import numpy as np
from mathutils import Vector, Matrix, Euler

V = Vector


def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


class Col(tuple):
    """Linear RGB for Blender shading; .srgb keeps the 0..255 sRGB value used for Roblox colours."""
    def __new__(cls, r, g, b):
        t = super().__new__(cls, (_lin(r), _lin(g), _lin(b)))
        t.srgb = (r, g, b)
        return t


def rgb(r, g, b):
    """A colour from 0..255 sRGB values (what you see in Roblox's colour picker)."""
    return Col(r, g, b)


def _rot(rot):
    if rot is None:
        return Matrix.Identity(3)
    if isinstance(rot, Matrix):
        return rot.to_3x3()
    return Euler([math.radians(a) for a in rot], 'XYZ').to_matrix()


def look_rot(direction, up=V((0, 0, 1))):
    """3x3 rotation whose local +Z points along direction."""
    d = V(direction).normalized()
    if abs(d.dot(up)) > 0.98:
        up = V((0, 1, 0))
    x = up.cross(d).normalized()
    y = d.cross(x).normalized()
    return Matrix((x, y, d)).transposed()


def swap_side(name):
    if name and name.endswith('_L'):
        return name[:-2] + '_R'
    if name and name.endswith('_R'):
        return name[:-2] + '_L'
    return name


class Creature:
    def __init__(self, name, palette):
        self.name = name
        self.palette = palette          # colour key -> rgb(...)
        self.glow = set()               # colour keys that glow (eyes, fire, lava, runes): Neon in Roblox
        self.smooth = set()             # colour keys without studs (horns, teeth, claws, metal): SmoothPlastic in Roblox
        self.studs = True               # False: no stud texture anywhere (preview and Roblox setup script)
        self.meshes = {}                # colour -> bmesh
        self.bone_defs = {}             # name -> dict(head, tail, parent)
        self.bone_order = []
        self.blocks = 0
        self.parts = []                 # (colour, bone, 8 corner points) of every block: used by the floating check
        self.report = {}
        self.bone('Root', (0, 0, 0), (0, 0, 1), None)

    # ---------- bones ----------
    def bone(self, name, head, tail, parent='Root', mirror=False):
        """A bone from head to tail. Blocks are attached to bones by name. mirror=True also makes the _R twin."""
        self.bone_defs[name] = dict(head=V(head), tail=V(tail), parent=parent)
        if name not in self.bone_order:
            self.bone_order.append(name)
        if mirror:
            mh = V((-head[0], head[1], head[2]))
            mt = V((-tail[0], tail[1], tail[2]))
            self.bone(swap_side(name), mh, mt, swap_side(parent) if parent else None)
        return name

    def _bi(self, bone):
        if bone not in self.bone_defs:
            raise KeyError('unknown bone %s (define it with d.bone before using it)' % bone)
        return self.bone_order.index(bone)

    # ---------- geometry ----------
    def _bm(self, col):
        if col not in self.palette:
            raise KeyError('unknown colour %s (add it to the palette)' % col)
        bm = self.meshes.get(col)
        if bm is None:
            bm = bmesh.new()
            bm.verts.layers.deform.verify()
            bm.loops.layers.uv.verify()
            self.meshes[col] = bm
        return bm

    def box(self, size, pos, rot=None, col='main', bone='Root', taper=(1, 1), shift=(0, 0), mirror=False):
        """Box of size (sx, sy, sz) centred at pos, rotated by rot = (x, y, z) degrees (XYZ Euler).
        taper scales the +Z face (x, y): (0.3, 0.3) makes a pyramid-like spike or tooth. shift moves that face."""
        self._box(V(size), V(pos), _rot(rot), col, bone, taper, shift)
        if mirror:
            m = _rot(rot)
            flip = Matrix(((-1, 0, 0), (0, 1, 0), (0, 0, 1)))
            mr = flip @ m @ flip
            self._box(V(size), V((-pos[0], pos[1], pos[2])), mr, col, swap_side(bone), taper, (-shift[0], shift[1]))
        return self

    def _box(self, s, pos, R, col, bone, taper, shift):
        bm = self._bm(col)
        dl = bm.verts.layers.deform.active
        uvl = bm.loops.layers.uv.active
        hx, hy, hz = s.x / 2, s.y / 2, s.z / 2
        tx, ty = taper
        local = []
        for z in (-1, 1):
            for y in (-1, 1):
                for x in (-1, 1):
                    if z > 0:
                        p = V((x * hx * tx + shift[0], y * hy * ty + shift[1], hz))
                    else:
                        p = V((x * hx, y * hy, -hz))
                    local.append(p)
        verts = []
        bi = self._bi(bone)
        for p in local:
            v = bm.verts.new(pos + R @ p)
            v[dl][bi] = 1.0
            verts.append(v)
        quads = [((0, 2, 3, 1), 'z'), ((4, 5, 7, 6), 'z'), ((0, 1, 5, 4), 'y'), ((2, 6, 7, 3), 'y'),
                 ((0, 4, 6, 2), 'x'), ((1, 3, 7, 5), 'x')]
        for idx, axis in quads:
            try:
                f = bm.faces.new([verts[i] for i in idx])
            except ValueError:
                continue
            for loop, i in zip(f.loops, idx):
                p = local[i]
                uv = (p.x, p.y) if axis == 'z' else ((p.x, p.z) if axis == 'y' else (p.y, p.z))
                loop[uvl].uv = (uv[0] + 0.5, uv[1] + 0.5)
        self.blocks += 1
        self.parts.append((col, bone, [pos + R @ p for p in local]))

    def slab(self, pts, thick, col='main', bone='Root', mirror=False):
        """Flat solid from a planar polygon (3+ points, in order), extruded by thick along its normal.
        Wing membranes, fins, sails, crests, tail spades."""
        self._slab([V(p) for p in pts], thick, col, bone)
        if mirror:
            self._slab([V((-p[0], p[1], p[2])) for p in reversed(pts)], thick, col, swap_side(bone))
        return self

    def _slab(self, pts, thick, col, bone):
        bm = self._bm(col)
        dl = bm.verts.layers.deform.active
        uvl = bm.loops.layers.uv.active
        c = sum(pts, V((0, 0, 0))) / len(pts)
        n = V((0, 0, 0))
        for i in range(len(pts)):
            n += (pts[i] - c).cross(pts[(i + 1) % len(pts)] - c)
        if n.length < 1e-6:
            return
        n.normalize()
        ax = (pts[1] - pts[0]).normalized()
        ay = n.cross(ax)
        off = n * (thick / 2)
        bi = self._bi(bone)
        top, bot = [], []
        for p in pts:
            for lst, q in ((top, p + off), (bot, p - off)):
                v = bm.verts.new(q)
                v[dl][bi] = 1.0
                lst.append(v)
        faces = [top, list(reversed(bot))]
        k = len(pts)
        for i in range(k):
            j = (i + 1) % k
            faces.append([bot[i], bot[j], top[j], top[i]])
        for fv in faces:
            try:
                f = bm.faces.new(fv)
            except ValueError:
                continue
            for loop in f.loops:
                d = loop.vert.co - c
                if len(fv) == k:
                    loop[uvl].uv = (d.dot(ax) + 0.5, d.dot(ay) + 0.5)
                else:
                    e = (fv[1].co - fv[0].co).normalized()
                    loop[uvl].uv = (d.dot(e) + 0.5, d.dot(n) + 0.5)
        self.blocks += 1
        self.parts.append((col, bone, [p + off for p in pts] + [p - off for p in pts]))

    def seg(self, a, b, thick, col='main', bone='Root', taper=(1, 1), mirror=False, roll=0):
        """Box spanning point a -> point b (necks, limbs, tails, horns). thick = number or (tx, ty).
        Gotcha: for a segment running mostly along X, the first thickness is along Y."""
        a, b = V(a), V(b)
        d = b - a
        tx, ty = (thick, thick) if isinstance(thick, (int, float)) else thick
        R = look_rot(d) @ Euler((0, 0, math.radians(roll))).to_matrix()
        return self.box((tx, ty, d.length), (a + b) / 2, R, col, bone, taper, (0, 0), mirror)

    def chain(self, pts, t0, t1, col='main', bone='Root', mirror=False, bones=None):
        """Segments through pts, thickness going from t0 to t1 (whiskers, simple tails)."""
        n = len(pts) - 1
        for i in range(n):
            f = i / max(1, n - 1)
            t = t0 + (t1 - t0) * f
            bn = bones[i] if bones else bone
            self.seg(pts[i], pts[i + 1], t * 1.0, col, bn, (0.9, 0.9), mirror)
        return self

    def horn(self, base, direction, length, thick, n, bend, col, bone, tip=None, mirror=False):
        """Curved horn: n segments, each turning by bend degrees and tapering. tip = colour of the last segment."""
        p = V(base)
        d = V(direction).normalized()
        axis = d.cross(V((0, 0, 1)))
        if axis.length < 0.01:
            axis = V((1, 0, 0))
        axis.normalize()
        seg_len = length / n
        for i in range(n):
            t = thick * (1 - i / n * 0.75)
            q = p + d * seg_len
            c = tip if (tip and i == n - 1) else col
            self.seg(p, q + d * 0.15 * t, t, c, bone, (0.8, 0.8), mirror)
            d = Matrix.Rotation(math.radians(bend), 3, axis) @ d
            p = q
        return self

    def spikes(self, a, b, n, h0, h1, w, col, bone, lean=25, mirror=False, tip=None):
        """A row of n spikes from a to b (spine, tail, neck), height growing from h0 to h1 in the middle,
        leaning back by lean degrees. tip = colour of the spike tips (dark claw colour, or fire2 for flames)."""
        a, b = V(a), V(b)
        for i in range(n):
            t = 0.5 if n == 1 else i / (n - 1)
            p = a.lerp(b, t)
            h = h0 + (h1 - h0) * math.sin(t * math.pi)
            R = _rot((-lean, 0, 0))
            body_h = h * (0.72 if tip else 1.0)
            self.box((w, w * 1.4, body_h), p + R @ V((0, 0, body_h / 2)), R, col, bone,
                     (0.35 if tip else 0.15, 0.45 if tip else 0.3), (0, 0), mirror)
            if tip:
                th = h - body_h + 0.1
                self.box((w * 0.35, w * 0.6, th), p + R @ V((0, 0, body_h - 0.05 + th / 2)), R, tip, bone, (0.2, 0.3), (0, 0), mirror)
        return self

    def foot(self, center, size, toes, col, claw_col, bone, forward=-1, mirror=False):
        """Foot block plus toes with claws pointing along forward (-1 = -Y, the front)."""
        c = V(center)
        sx, sy, sz = size
        self.box(size, c, col=col, bone=bone, mirror=mirror)
        tw = sx / toes
        for i in range(toes):
            x = c.x - sx / 2 + tw * (i + 0.5)
            ty = c.y + forward * (sy / 2 + 0.55)
            self.box((tw * 0.8, 1.2, sz * 0.75), (x, ty, c.z - sz * 0.1), col=col, bone=bone, mirror=mirror)
            self.box((tw * 0.5, 1.1, sz * 0.5), (x, ty + forward * (0.55 + sz * 0.25), c.z - sz * 0.22), rot=(90 * -forward, 0, 0),
                     col=claw_col, bone=bone, taper=(0.3, 0.2), mirror=mirror)
        return self

    # ---------- build ----------
    def _material(self, col):
        name = 'STUD_%s_%s' % (self.name, col)
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        c = self.palette[col]
        mat.diffuse_color = (c[0], c[1], c[2], 1)
        mat.use_backface_culling = True                  # like Roblox: a face seen from behind is not drawn
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.inputs['Base Color'].default_value = (c[0], c[1], c[2], 1)
        if col in self.glow:
            bsdf.inputs['Emission Color'].default_value = (c[0], c[1], c[2], 1)
            bsdf.inputs['Emission Strength'].default_value = 3.0
        if col in self.smooth or col in self.glow or not self.studs:
            bsdf.inputs['Roughness'].default_value = 0.3
        else:
            # stud preview: the same tiling Roblox does with the stud material, through the block's own UVs
            img = nt.nodes.new('ShaderNodeTexImage')
            img.image = stud_image()
            img.interpolation = 'Linear'
            img.image.colorspace_settings.name = 'Non-Color'
            bump = nt.nodes.new('ShaderNodeBump')
            bump.inputs['Strength'].default_value = 0.6
            bump.inputs['Distance'].default_value = 0.08
            ramp = nt.nodes.new('ShaderNodeMapRange')
            ramp.inputs['To Min'].default_value = 0.72
            ramp.inputs['To Max'].default_value = 1.0
            mix = nt.nodes.new('ShaderNodeMix')
            mix.data_type = 'RGBA'
            mix.blend_type = 'MULTIPLY'
            mix.inputs['Factor'].default_value = 1.0
            mix.inputs['A'].default_value = (c[0], c[1], c[2], 1)
            nt.links.new(img.outputs['Color'], bump.inputs['Height'])
            nt.links.new(img.outputs['Color'], ramp.inputs['Value'])
            nt.links.new(ramp.outputs['Result'], mix.inputs['B'])
            nt.links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
            nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
            bsdf.inputs['Roughness'].default_value = 0.55
        nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
        return mat

    def _anchor_empty_bones(self):
        """Roblox's FBX importer DROPS bones that no vertex is weighted to (animations that use them then break).
        Every such bone gets a tiny cube at its head, inside the body."""
        used = set()
        for bm in self.meshes.values():
            dl = bm.verts.layers.deform.active
            for v in bm.verts:
                used.update(k for k, w in v[dl].items() if w > 1e-4)
        if not self.meshes:
            return []
        col = max(self.meshes, key=lambda c: len(self.meshes[c].verts))
        added = []
        for i, n in enumerate(self.bone_order):
            if i not in used and n != 'Root':
                self._box(V((0.06, 0.06, 0.06)), V(self.bone_defs[n]['head']), Matrix.Identity(3), col, n, (1, 1), (0, 0))
                self.parts.pop()      # an anchor is not a real piece: keep it out of the floating check
                added.append(n)
        return added

    def floating(self, tol=0.05):
        """Pieces that touch no other piece (by bounding boxes grown by tol). Run BEFORE finalize."""
        boxes = []
        for col, bone, pts in self.parts:
            xs = [p.x for p in pts]
            ys = [p.y for p in pts]
            zs = [p.z for p in pts]
            boxes.append((min(xs) - tol, max(xs) + tol, min(ys) - tol, max(ys) + tol, min(zs) - tol, max(zs) + tol))
        out = []
        for i, a in enumerate(boxes):
            if not any(j != i and a[0] <= b[1] and b[0] <= a[1] and a[2] <= b[3] and b[2] <= a[3] and a[4] <= b[5] and b[4] <= a[5]
                       for j, b in enumerate(boxes)):
                c = sum(self.parts[i][2], V((0, 0, 0))) / len(self.parts[i][2])
                out.append((self.parts[i][0], self.parts[i][1], tuple(round(x, 2) for x in c)))
        return out

    def finalize(self, collection_name=None):
        """Blocks -> one mesh per colour + armature. Returns (rig, mesh objects). Fills self.report."""
        self.report['floating'] = self.floating()
        self.report['anchored'] = self._anchor_empty_bones()
        cname = collection_name or self.name
        old = bpy.data.collections.get(cname)
        if old:
            for o in list(old.objects):
                if o.name.startswith(self.name + '_'):      # only this creature's previous build
                    bpy.data.objects.remove(o, do_unlink=True)
        coll = old or bpy.data.collections.new(cname)
        if coll.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(coll)
        for dcoll in (bpy.data.meshes, bpy.data.armatures):
            for dblock in list(dcoll):
                if dblock.name.startswith(self.name + '_') and dblock.users == 0:
                    dcoll.remove(dblock)
        arm = bpy.data.armatures.new(self.name + '_Rig')
        rig = bpy.data.objects.new(self.name + '_Rig', arm)
        coll.objects.link(rig)
        rig.show_in_front = True
        bpy.context.view_layer.objects.active = rig
        for o in bpy.context.selected_objects:
            o.select_set(False)
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        ebs = {}
        for n in self.bone_order:
            d = self.bone_defs[n]
            eb = arm.edit_bones.new(n)
            eb.head, eb.tail = d['head'], d['tail']
            ebs[n] = eb
        for n in self.bone_order:
            p = self.bone_defs[n]['parent']
            if p:
                ebs[n].parent = ebs[p]
        bpy.ops.object.mode_set(mode='OBJECT')
        out, tris = [], 0
        for col, bm in self.meshes.items():
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))   # blocks are closed solids: all faces point out
            me = bpy.data.meshes.new('%s_%s' % (self.name, col))
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new(me.name, me)
            coll.objects.link(ob)
            for n in self.bone_order:
                ob.vertex_groups.new(name=n)
            ob.data.materials.append(self._material(col))
            n = sum(len(pl.vertices) - 2 for pl in me.polygons)
            tris += n
            self.report.setdefault('tris_by_colour', {})[col] = n
            ob.parent = rig
            mod = ob.modifiers.new('Armature', 'ARMATURE')
            mod.object = rig
            out.append(ob)
        self.meshes = {}
        self.report['tris'] = tris
        self.report['blocks'] = self.blocks
        self.report['bones'] = len(self.bone_order)
        self.report['zfight_fixed'] = len(zfight_report(out))
        self.report['zfight_left'] = fix_zfight(out)
        return rig, out


def zfight_report(objs, tol=0.012, min_area=0.02, fix=0.0):
    """Faces of DIFFERENT colour meshes that lie in the same plane, face the same way and overlap: they flicker
    (z-fighting) in Roblox. With fix > 0 the smaller face of each pair is pushed out along its normal by fix studs.
    Returns a list of (meshA, meshB, centre, area)."""
    faces = []
    for ob in objs:
        me = ob.data
        for p in me.polygons:
            n = p.normal.copy()
            if n.length < 0.5:
                continue
            verts = [me.vertices[i].co.copy() for i in p.vertices]
            faces.append((ob.name, n, n.dot(verts[0]), verts, p.area, ob, p.index))
    out = []
    buckets = {}
    for f in faces:
        n = f[1]
        ax = max(range(3), key=lambda i: abs(n[i]))
        if abs(n[ax]) < 0.999:
            continue
        key = (ax, round(f[2] * (1 if n[ax] > 0 else -1) / tol))
        buckets.setdefault(key, []).append(f)
    for key, lst in buckets.items():
        ax = key[0]
        o1, o2 = [i for i in range(3) if i != ax]
        for i in range(len(lst)):
            a = lst[i]
            amin = [min(v[o] for v in a[3]) for o in (o1, o2)]
            amax = [max(v[o] for v in a[3]) for o in (o1, o2)]
            for j in range(i + 1, len(lst)):
                b = lst[j]
                if a[0] == b[0] or a[1].dot(b[1]) < 0.99:
                    continue      # same colour mesh: invisible, it renders as one surface
                pa = a[2] * (1 if a[1][ax] > 0 else -1)
                pb = b[2] * (1 if b[1][ax] > 0 else -1)
                if abs(pa - pb) > tol:
                    continue
                bmin = [min(v[o] for v in b[3]) for o in (o1, o2)]
                bmax = [max(v[o] for v in b[3]) for o in (o1, o2)]
                w = min(amax[0], bmax[0]) - max(amin[0], bmin[0])
                h = min(amax[1], bmax[1]) - max(amin[1], bmin[1])
                if w > 0.01 and h > 0.01 and w * h > min_area:
                    c = V((0, 0, 0))
                    c[ax] = pa
                    c[o1] = (max(amin[0], bmin[0]) + min(amax[0], bmax[0])) / 2
                    c[o2] = (max(amin[1], bmin[1]) + min(amax[1], bmax[1])) / 2
                    out.append((a[0], b[0], tuple(round(x, 2) for x in c), round(w * h, 3)))
                    if fix > 0:
                        small = a if a[4] <= b[4] else b
                        me = small[5].data
                        for vi in me.polygons[small[6]].vertices:
                            me.vertices[vi].co += small[1] * fix
    for ob in objs:
        ob.data.update()
    return out


def fix_zfight(objs, step=0.04, rounds=8):
    """Push detail faces out until no same-facing coplanar overlaps remain. Returns the remaining count."""
    for _ in range(rounds):
        if not zfight_report(objs, fix=step):
            break
    return len(zfight_report(objs))


def stud_image(size=128):
    """Height map of one stud cell: a raised square stud inside a groove (Blender preview only)."""
    img = bpy.data.images.get('STUD_height')
    if img and img.size[0] == size:
        return img
    if img:
        bpy.data.images.remove(img)
    xs = (np.arange(size) + 0.5) / size
    X, Y = np.meshgrid(xs, xs)
    d = np.maximum(np.abs(X - 0.5), np.abs(Y - 0.5))
    groove = np.clip((0.5 - d) / 0.05, 0, 1)
    stud = np.clip((0.33 - d) / 0.06, 0, 1)
    h = 0.55 * groove + 0.45 * stud
    rgba = np.stack([h, h, h, np.ones_like(h)], axis=-1).astype(np.float32)
    img = bpy.data.images.new('STUD_height', size, size, alpha=False, float_buffer=False)
    img.pixels.foreach_set(rgba.ravel())
    img.pack()
    return img


# ---------- review scene and renders ----------
def review_scene(avatar=True):
    """Daylight close to Roblox, a dark floor and a 5-stud-tall blocky avatar for scale (collection 'Review')."""
    sc = bpy.context.scene
    for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    coll = bpy.data.collections.get('Review') or bpy.data.collections.new('Review')
    if coll.name not in sc.collection.children:
        sc.collection.children.link(coll)
    for o in list(coll.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    world = sc.world or bpy.data.worlds.new('World')
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = (0.45, 0.62, 0.9, 1)
    bg.inputs['Strength'].default_value = 0.35
    sun = bpy.data.lights.new('REV_Sun', 'SUN')
    sun.energy = 4.5
    sun.angle = math.radians(8)
    so = bpy.data.objects.new('REV_Sun', sun)
    so.rotation_euler = (math.radians(50), math.radians(-12), math.radians(35))
    coll.objects.link(so)
    k = Creature('REV_Floor', {'floor': rgb(40, 44, 62)})
    k.box((400, 400, 1), (0, 0, -0.5), col='floor')
    k.finalize('Review')
    if avatar:
        a = Creature('REV_Avatar', {'skin': rgb(245, 205, 48), 'shirt': rgb(13, 105, 172), 'pants': rgb(40, 127, 71)})
        ax, ay = avatar if isinstance(avatar, tuple) else (-9, -6)
        a.box((1, 1, 2), (ax + 0.5, ay, 1), col='pants')
        a.box((1, 1, 2), (ax - 0.5, ay, 1), col='pants')
        a.box((2, 1, 2), (ax, ay, 3), col='shirt')
        a.box((1, 1, 2), (ax - 1.5, ay, 3), col='skin')
        a.box((1, 1, 2), (ax + 1.5, ay, 3), col='skin')
        a.box((1.2, 1.2, 1.2), (ax, ay, 4.6), col='skin')
        a.finalize('Review')
    return coll


def creature_bounds(objs):
    pts = []
    for ob in objs:
        if ob.type == 'MESH':
            pts += [ob.matrix_world @ V(c) for c in ob.bound_box]
    lo = V((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = V((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


VIEWS = {
    'front': (0, -1, 0.18), 'side': (1, 0, 0.12), 'three_quarter': (0.75, -0.75, 0.32),
    'three_quarter_l': (-0.75, -0.75, 0.3), 'back': (0, 1, 0.25), 'top': (0, -0.01, 1),
    'low': (0.55, -0.85, 0.05),
}


def shoot(objs, out_dir, prefix, views=('three_quarter', 'front', 'side', 'back'), res=(960, 720), lens=50, margin=0.8,
          focus=None):
    """Render the given meshes from preset views into out_dir/<prefix>_<view>.png. focus=(center, radius) frames a
    part (a head close-up). Returns the file paths."""
    sc = bpy.context.scene
    if focus:
        c, radius = V(focus[0]), focus[1]
    else:
        lo, hi = creature_bounds(objs)
        c, radius = (lo + hi) / 2, (hi - lo).length / 2
    cam_data = bpy.data.cameras.get('REV_Cam') or bpy.data.cameras.new('REV_Cam')
    cam_data.lens = lens
    cam_data.clip_end = 5000
    cam = bpy.data.objects.get('REV_Cam') or bpy.data.objects.new('REV_Cam', cam_data)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    fov = 2 * math.atan(36 / (2 * lens)) * (res[1] / res[0]) if res[0] > res[1] else 2 * math.atan(36 / (2 * lens))
    dist = radius * margin / math.sin(fov / 2)
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for v in views:
        d = V(VIEWS[v]).normalized()
        cam.location = c + d * dist
        cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
        path = os.path.join(out_dir, '%s_%s.png' % (prefix, v))
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        paths.append(path)
    return paths


def export_fbx(rig, objs, path):
    """FBX for Roblox's 3D Importer: armature + one skinned mesh per colour, rest pose, no animation."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in [rig] + list(objs):
        o.hide_set(False)
        o.select_set(True)
    if rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='Z',
                             axis_up='Y', object_types={'MESH', 'ARMATURE'}, use_mesh_modifiers=False, mesh_smooth_type='FACE',
                             add_leaf_bones=False, use_armature_deform_only=False, bake_anim=False, path_mode='COPY',
                             embed_textures=True)
    return path, os.path.getsize(path) // 1024
