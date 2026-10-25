# API

In a creature file: `def build(sk):` where `sk` is the `studkit` module. `import blockkit as bk` for the helpers.
Positions are (x, y, z) in studs; rotations are (x, y, z) degrees, XYZ Euler; colours are palette KEYS.

## studkit

| call | what it makes |
|---|---|
| `sk.rgb(r, g, b)` | a colour from 0..255 values |
| `sk.V((x, y, z))` | a vector (mathutils.Vector) |
| `d = sk.Creature(name, palette)` | a new creature; `palette = {'main': sk.rgb(...), ...}` |
| `d.glow` / `d.smooth` | sets of colour keys: glowing (Neon) / no studs (SmoothPlastic) |
| `d.studs = False` | build without the stud texture |
| `d.bone(name, head, tail, parent='Root', mirror=False)` | a bone; `mirror` also makes the `_R` twin of an `_L` bone |
| `d.box(size, pos, rot=None, col, bone, taper=(1,1), shift=(0,0), mirror=False)` | a box centred at `pos`; `taper` shrinks the +Z face (spikes, teeth, snouts) |
| `d.seg(a, b, thick, col, bone, taper=(1,1), mirror=False, roll=0)` | a box from point `a` to point `b`; `thick` = number or `(tx, ty)` |
| `d.slab(pts, thick, col, bone, mirror=False)` | a flat plate from a planar polygon (fins, membranes, crests) |
| `d.chain(pts, t0, t1, col, bone, bones=None)` | segments through points, thickness t0 -> t1 |
| `d.horn(base, direction, length, thick, n, bend, col, bone, tip=None, mirror=False)` | curved tapering horn in n pieces |
| `d.spikes(a, b, n, h0, h1, w, col, bone, lean=25, tip=None, mirror=False)` | n spikes along a -> b |
| `d.foot(center, size, toes, col, claw_col, bone, forward=-1, mirror=False)` | foot block, toes and claws |
| `d.floating()` | pieces touching nothing (build.py reports them) |
| `rig, meshes = d.finalize()` | one mesh per colour + armature (build.py does this) |

Gotchas:
- `seg` with a segment mostly along X: the first thickness is along Y.
- `rot` is applied before `mirror`: give the LEFT piece's rotation, the right one is mirrored correctly.
- A `taper`ed box points along its local +Z: rotate `(180, 0, 0)` for teeth hanging down.

## blockkit

| call | what it makes |
|---|---|
| `bk.side_eye(d, bone, c, (w, h), tilt=10, lid=0.42, cols=('eye','lid'), rim=None)` | eye on the side of the head + lid/brow, mirrored |
| `bk.front_eye(d, bone, c, (w, h), tilt=14, lid=0.42, cols=('eye','lid'), rim=None)` | eye on the front face + lid/brow, mirrored |
| `bk.leg(d, up, down, top, knee, foot, tu, td, col, hoof=None, hoof_col='hoof')` | two-block leg with overlap at the knee, mirrored |
| `bk.paw(d, bone, (x, y), (w, l, h), col, claw_col, toes=3)` | foot on the ground with claws |
| `bk.tube(d, pts, thick, bones, col, taper=None)` | blocks along points with overlap (tails, necks, antlers) |
| `bk.bat_wing(d, S, E, W, tips, root, arm, claw, mem=('membrane','membrane2'))` | dragon wing, mirrored |
| `bk.serpent(d, pts, radii, col, belly=None, flat=0.88)` | serpent body + `Seg1..SegN` bones; returns per-segment frames |

## build.py

```
blender -b --factory-startup -P scripts/build.py -- creature.py [--out DIR] [--views a,b] [--no-studs] [--pose] [--colours] [--export] [--res WxH]
```

Writes `<Name>_report.txt` (blocks, bones, triangles, size, FLOAT lines, coplanar faces, anchored bones),
`<Name>_<view>.png`, `<Name>_head_three_quarter.png` (if there is a `Head` bone), `<Name>_pose_three_quarter.png`
(`--pose`), `<Name>_colour_<key>_three_quarter.png` (`--colours`), `<Name>_sheet.png` (all views together), and
with `--export` `<Name>.fbx` + `<Name>_roblox_setup.luau`.

Views: `three_quarter`, `three_quarter_l`, `front`, `side`, `back`, `top`, `low`.
