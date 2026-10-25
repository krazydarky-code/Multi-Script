"""blockkit: ready-made body parts built only from studkit blocks (box / seg / slab), in the same style.

Rules every helper follows (and your own pieces should too):
  - every piece is seated in its neighbour (about half its depth inside): nothing floats, nothing only grazes;
  - leg tops start INSIDE the torso and are narrower than it where they enter, so no leg top shows beside the body;
  - no two faces of different colours in the same plane (they flicker in Roblox): make sizes differ by 0.05+;
  - eyes have NO pupil: a glowing block under a dark angry brow (aggressive, mythic), or a white block under a
    dark lid (farm, cute, funny).
"""
from mathutils import Vector as V


def side_eye(d, bone, c, size, tilt=10, lid=0.42, cols=('eye', 'lid'), rim=None):
    """Eye on the LEFT side face of a head, mirrored to the right. c = centre on the head's side face (x > 0),
    size = (length along y, height). The lid covers the top `lid` part of the eye and drops towards the nose by
    `tilt` degrees (more tilt = more attitude). With a glowing eye colour the lid reads as an angry brow.
    rim = colour of a dark outline behind the eye, for a pale eye on pale skin."""
    x, y, z = c
    w, h = size
    if rim:
        d.box((0.08, w + 0.16, h + 0.16), (x + 0.035, y, z), col=rim, bone=bone, mirror=True)
    d.box((0.12, w, h), (x + 0.03, y, z), col=cols[0], bone=bone, mirror=True)
    d.box((0.16, w * 1.22, h * lid), (x + 0.07, y, z + h * (0.5 - lid / 2) + 0.03), rot=(tilt, 0, 0), col=cols[1], bone=bone, mirror=True)


def front_eye(d, bone, c, size, tilt=14, lid=0.42, cols=('eye', 'lid'), rim=None):
    """Eye on the FRONT face of a head (facing -y), left one at x > 0, mirrored. The lid drops towards the middle."""
    x, y, z = c
    w, h = size
    if rim:
        d.box((w + 0.16, 0.08, h + 0.16), (x, y - 0.035, z), col=rim, bone=bone, mirror=True)
    d.box((w, 0.12, h), (x, y - 0.03, z), col=cols[0], bone=bone, mirror=True)
    d.box((w * 1.22, 0.16, h * lid), (x, y - 0.07, z + h * (0.5 - lid / 2) + 0.03), rot=(0, -tilt, 0), col=cols[1], bone=bone, mirror=True)


def leg(d, up, down, top, knee, foot, tu, td, col, hoof=None, hoof_col='hoof', col_down=None):
    """One leg (the left one, mirrored): an upper block top -> knee on bone `up` and a lower block knee -> foot on
    bone `down`. The upper block runs a little past the knee and the lower one starts a little above it, so a bent
    knee shows no gap. hoof = (sx, sy, sz): a block standing on the ground under the foot.
    The blocks stay upright seen from the front (top and foot take the knee's x)."""
    knee = V(knee)
    top, foot = V((knee.x, top[1], top[2])), V((knee.x, foot[1], foot[2]))
    a = (knee - top).normalized()
    b = (foot - knee).normalized()
    t = tu if isinstance(tu, (int, float)) else max(tu)
    d.seg(top, knee + a * (t * 0.3), tu, col=col, bone=up, mirror=True)
    d.seg(knee - b * (t * 0.3), foot, td, col=col_down or col, bone=down, mirror=True)
    if hoof:
        d.box(hoof, (foot.x, foot.y, hoof[2] / 2), col=hoof_col, bone=down, mirror=True)


def paw(d, bone, c, size, col, claw_col, toes=3, claw=None, mirror=True):
    """A foot block standing on the ground at c = (x, y), size (w, l, h), with `toes` tapered claws coming out of its
    front (-y) down to the ground. Mirrored to the other side unless mirror=False."""
    x, y = c
    w, l, h = size
    d.box((w, l, h), (x, y, h / 2), col=col, bone=bone, mirror=mirror)
    tw = w / toes
    cl = claw or l * 0.35
    for i in range(toes):
        cx = x - w / 2 + tw * (i + 0.5)
        t = tw * 0.5
        d.seg((cx, y - l / 2 + t, h * 0.55), (cx, y - l / 2 - cl, t * 0.45), (t, t * 0.9), col=claw_col, bone=bone, taper=(0.3, 0.3),
              mirror=mirror)


def tube(d, pts, thick, bones, col, taper=None, over=0.25, mirror=False):
    """Blocks along a line of points (tails, necks, antlers): block i runs pts[i] -> pts[i+1] on bones[i] (one bone
    name for all is fine) and reaches `over` into the next block, so a bend shows no gap. thick = one size for all or
    one per block; col = one colour or one per block; taper = taper of the LAST block."""
    pts = [V(p) for p in pts]
    n = len(pts) - 1
    for i in range(n):
        a, b = pts[i], pts[i + 1]
        t = thick[i] if isinstance(thick, list) else thick
        bn = bones[i] if isinstance(bones, list) else bones
        c = col[i] if isinstance(col, list) else col
        end = b + (b - a).normalized() * over if i < n - 1 else b
        d.seg(a, end, t, col=c, bone=bn, taper=taper if (taper and i == n - 1) else (1, 1), mirror=mirror)


def bat_wing(d, S, E, W, tips, root, arm, claw, mem=('membrane', 'membrane2'), bones=('Wing1_L', 'Wing2_L'), size=1.0, web=0.24,
             spikes=True):
    """A dragon wing (left, mirrored): an arm S (shoulder) -> E (elbow) -> W (wrist) with joint blocks, finger bones
    from W to each tip (a claw at the end), membrane slabs between the fingers and from the last finger back to the
    body (root = two points along the body side). size scales every thickness."""
    S, E, W = V(S), V(E), V(W)
    tips = [V(t) for t in tips]
    root = [V(r) for r in root]
    b1, b2 = bones
    d.seg(S, E, 1.15 * size, col=arm, bone=b1, mirror=True)
    d.seg(E, W, 0.95 * size, col=arm, bone=b2, mirror=True)
    d.box((1.6 * size,) * 3, E, col=arm, bone=b1, mirror=True)
    d.box((1.3 * size,) * 3, W, col=arm, bone=b2, mirror=True)
    if spikes:
        d.seg(E, E + V((0.4, 1.6, -0.6)) * size, 0.5 * size, col=claw, bone=b1, taper=(0.3, 0.3), mirror=True)    # elbow spike
        d.seg(W, W + V((0.4, -0.4, 1.8)) * size, 0.5 * size, col=claw, bone=b2, taper=(0.25, 0.25), mirror=True)  # thumb claw
    for i, t in enumerate(tips):
        d.seg(W, t, (0.62 - i * 0.06) * size, col=arm, bone=b2, taper=(0.7, 0.7), mirror=True)
        dirv = (t - W).normalized()
        d.seg(t - dirv * 0.2 * size, t + dirv * 1.1 * size, 0.42 * size, col=claw, bone=b2, taper=(0.2, 0.2), mirror=True)
    for i in range(len(tips) - 1):
        d.slab([W, tips[i], tips[i + 1]], web, col=mem[i % 2], bone=b2, mirror=True)
    d.slab([W, tips[-1], root[1], root[0]], web, col=mem[1], bone=b2, mirror=True)
    d.slab([S, E, W, root[0]], web, col=mem[0], bone=b1, mirror=True)


def serpent(d, pts, radii, col, belly=None, flat=0.88, root='Root'):
    """A serpent body of blocks along pts (pts[0] = the neck end): bones Seg1 (front) .. SegN (tail end, parented to
    `root`). Each segment is one block, height 2*flat*r, reaching a little into its neighbours; `belly` lays a pale
    strip under it. Returns, per segment i (1..N), a dict with a, b (ends), t (direction), up (block top), side, r,
    h (half height) and bone, so you can add fins, spots, sails and armour along it."""
    pts = [V(p) for p in pts]
    n = len(pts) - 1
    for i in range(n, 0, -1):
        d.bone('Seg%d' % i, pts[i], pts[i - 1], 'Seg%d' % (i + 1) if i < n else root)
    out = []
    for i in range(1, n + 1):
        a, b = pts[i], pts[i - 1]
        r = max(radii[i], 0.4)
        t = (b - a).normalized()
        side = t.cross(V((0, 0, 1))).normalized()
        up = side.cross(t).normalized()
        bone = 'Seg%d' % i
        d.seg(a - t * 0.3, b + t * (0.6 if i > 1 else 0.3), (2 * r, 2 * flat * r), col=col, bone=bone,
              taper=(0.5, 0.5) if i == n else (1, 1))
        if belly and r > 0.7:
            d.seg(a.lerp(b, 0.15) - up * (flat * r - 0.08), a.lerp(b, 0.85) - up * (flat * r - 0.08), (1.2 * r, 0.3), col=belly, bone=bone)
        out.append(dict(a=a, b=b, t=t, up=up, side=side, r=r, bone=bone, i=i, h=flat * r))
    return out
