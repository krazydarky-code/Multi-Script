"""Leviathan (epic tier). The colossal sea serpent: a long
body that waves in 3D, thick behind the head and tapering to the tail, covered in overlapping dark armour scales,
with blade spikes down the back, pale side ridges, a pale banded belly, glowing abyss runes, webbed pectoral fins
and a big tail blade; and a huge aggressive head - armoured brow over glowing eyes, a long snout, jaws hanging
open with rows of teeth, a webbed crown of spines and swept-back horns."""
import math
import blockkit as bk
from mathutils import Vector as V

PTS = [(0, -16.0, 14.6), (0, -11.4, 13.2), (2.6, -7.0, 11.6), (5.0, -2.6, 10.2), (4.6, 2.2, 9.4), (1.4, 6.2, 9.8), (-2.6, 9.8, 10.8),
       (-4.8, 14.0, 11.8), (-3.8, 18.6, 12.2), (-0.6, 22.2, 11.8), (2.8, 25.4, 11.0), (4.2, 29.0, 10.2), (3.4, 32.6, 9.8)]
RADII = [2.8, 2.9, 3.2, 3.3, 3.2, 3.0, 2.7, 2.4, 2.0, 1.65, 1.3, 0.95, 0.6]


def build(sk):
    rgb = sk.rgb
    pal = {'main': rgb(30, 104, 140), 'main2': rgb(56, 146, 180), 'dark': rgb(18, 58, 92), 'belly': rgb(176, 230, 226),
           'belly2': rgb(120, 194, 198), 'fin': rgb(70, 206, 222), 'fin2': rgb(40, 140, 186), 'horn': rgb(226, 244, 244),
           'claw': rgb(14, 28, 42), 'tooth': rgb(250, 252, 255), 'mouth': rgb(110, 22, 46), 'gum': rgb(156, 34, 58),
           'eye': rgb(255, 110, 40), 'rune': rgb(90, 240, 255)}
    d = sk.Creature('Leviathan', pal)
    d.glow.update({'eye', 'rune'})
    d.smooth.update({'horn', 'tooth', 'claw'})

    # ---------------- body: a long 3D wave of armoured segments ----------------
    segs = bk.serpent(d, PTS, RADII, 'main', belly='belly', flat=0.85)
    n = len(segs)
    for s in segs:
        a, b, t, up, side, r, h, bone, i = s['a'], s['b'], s['t'], s['up'], s['side'], s['r'], s['h'], s['bone'], s['i']
        m = a.lerp(b, 0.5)
        L = (b - a).length
        # overlapping armour scales on the back: one across the joint behind, one over the middle (no stacked look)
        d.seg(a - t * min(1.0, L * 0.25) + up * (h - 0.05), a + t * L * 0.45 + up * (h - 0.05), (2 * r * 0.84, 0.55), col='dark', bone=bone)
        d.seg(a + t * L * 0.4 + up * (h + 0.2), b + t * 0.2 + up * (h + 0.2), (2 * r * 0.66, 0.5), col='dark', bone=bone)
        # pale ridges along both sides, running across the joints
        for k in (1, -1):
            d.seg(a - t * 0.4 + side * k * (r - 0.12) + up * h * 0.2, b + t * 0.4 + side * k * (r - 0.12) + up * h * 0.2, (0.5, 0.85),
                  col='main2', bone=bone)
        # banded belly
        if r > 0.9:
            d.seg(m - side * r * 0.62 - up * (h - 0.02), m + side * r * 0.62 - up * (h - 0.02), (1.1, 0.4), col='belly2', bone=bone)
        # blade spikes down the back, biggest at the front
        if i <= n - 1:
            hh = 1.0 + 0.55 * r
            d.spikes(m + up * (h + 0.35), m + up * (h + 0.35), 1, hh, hh, 0.45 + 0.18 * r, 'fin', bone, lean=42, tip='fin2')
        # glowing abyss runes on every other segment
        if i % 2 == 0 and r > 1.2:
            for k in (1, -1):
                for dy in (-0.45, 0.45):
                    p = m + t * dy + side * k * (r + 0.04)
                    d.seg(p - up * h * 0.35, p + up * h * 0.15, (0.3, 0.3), col='rune', bone=bone)

    # ---------------- webbed pectoral fins (Seg2) and a smaller pair (Seg6) ----------------
    for idx, size in ((1, 1.0), (5, 0.62)):
        s = segs[idx]
        m, t, up, side, r, h, bone = s['a'].lerp(s['b'], 0.55), s['t'], s['up'], s['side'], s['r'], s['h'], s['bone']
        for k in (1, -1):
            base = m + side * k * (r - 0.3) - up * h * 0.3
            tips = [base + (side * k * 6.2 + t * 1.4 - up * 1.2) * size, base + (side * k * 6.8 - t * 1.6 - up * 2.4) * size,
                    base + (side * k * 5.2 - t * 4.2 - up * 2.6) * size, base + (side * k * 2.8 - t * 5.4 - up * 1.6) * size]
            for j, tp in enumerate(tips):
                d.seg(base, tp, (0.5 - j * 0.06) * size + 0.1, col='horn', bone=bone, taper=(0.5, 0.5))
            for j in range(len(tips) - 1):
                d.slab([base, tips[j], tips[j + 1]], 0.22, col='fin' if j % 2 == 0 else 'fin2', bone=bone)

    # ---------------- tail blade ----------------
    s = segs[-1]
    e, t, up, side, bone = s['a'], -s['t'], s['up'], s['side'], s['bone']
    d.slab([e - t * 0.8, e + t * 3.6 + up * 4.6, e + t * 5.8 + up * 0.4, e + t * 3.4 - up * 3.4], 0.36, col='fin2', bone=bone)
    d.slab([e - t * 0.2, e + t * 2.6 + up * 3.0, e + t * 4.2 + up * 0.3, e + t * 2.4 - up * 2.2], 0.5, col='fin', bone=bone)
    for tp in (e + t * 3.6 + up * 4.6, e + t * 5.8 + up * 0.4, e + t * 3.4 - up * 3.4):
        d.seg(e - t * 0.4, tp, 0.4, col='horn', bone=bone, taper=(0.4, 0.4))

    # ---------------- the head: clearly bigger than the neck, all attitude ----------------
    S = 1.3                                      # head scale: the leviathan's head must dwarf its neck
    O = V((0, -20.4, 15.9))                      # skull centre; the head faces -Y
    H, J = 'Head', 'Jaw'

    def P(x, y, z):
        return O + V((x, y, z)) * S

    def B(size, loc, col, bone=H, rot=None, **kw):
        d.box(tuple(c * S for c in size), P(*loc), rot=rot, col=col, bone=bone, **kw)

    d.bone(H, P(0, 3.2, -0.2), P(0, -10.6, -0.4), 'Seg1')
    d.bone(J, P(0, -0.8, -2.6), P(0, -9.6, -4.4), H)
    B((6.8, 6.4, 5.0), (0, 0, 0), 'main')                                   # skull
    B((5.4, 2.4, 4.2), (0, 3.4, 0.0), 'main')                               # back of the skull, into the neck
    B((5.4, 7.0, 3.0), (0, -6.2, -0.6), 'main', taper=(0.82, 1))            # long snout
    B((3.6, 6.4, 0.9), (0, -5.8, 1.15), 'main2')                            # snout ridge
    B((4.2, 1.6, 1.6), (0, -9.5, -0.2), 'dark')                             # nose plate
    B((7.2, 3.0, 1.2), (0, -1.0, 2.9), 'dark')                              # heavy brow plate
    for k in (1, -1):
        B((2.8, 2.6, 1.0), (2.1 * k, -2.6, 2.75), 'dark', rot=(0, -28 * k, 0))      # angry brows, low over the eyes
        B((1.6, 0.24, 0.8), (2.0 * k, -3.32, 1.6), 'eye')                          # glowing eyes, front face
        B((0.26, 2.0, 0.8), (3.42 * k, -2.2, 1.6), 'eye')                          # glowing eyes, side face
        B((0.5, 0.24, 0.3), (1.1 * k, -10.3, 0.25), 'claw')                        # nostrils
        B((1.2, 4.0, 2.6), (3.6 * k, -0.6, -0.6), 'dark')                          # cheek armour
        d.horn(P(2.4 * k, -0.2, 2.9), (0.4 * k, 1.0, 0.5), 6.2 * S, 1.0 * S, 5, -12, 'horn', H, tip='claw')   # swept-back horns
        for i in range(7):                                                          # upper teeth
            B((0.6, 0.6, 1.3), (2.3 * k, -2.0 - i * 1.15, -2.85), 'tooth', rot=(180, 0, 0), taper=(0.25, 0.3))
        B((0.8, 0.8, 2.2), (1.55 * k, -9.0, -3.1), 'tooth', rot=(180, 0, 0), taper=(0.25, 0.3))   # long front fangs
        # gill frill behind the cheek: three spines with webbing
        gb = P(3.9 * k, 1.4, -0.2)
        gt = [gb + V((2.6 * k, 1.6, 2.4)) * S, gb + V((3.2 * k, 2.2, 0.2)) * S, gb + V((2.6 * k, 1.8, -2.0)) * S]
        for tp in gt:
            d.seg(gb, tp, 0.4 * S, col='horn', bone=H, taper=(0.35, 0.35))
        for j in range(len(gt) - 1):
            d.slab([gb, gt[j], gt[j + 1]], 0.22 * S, col='fin' if j % 2 == 0 else 'fin2', bone=H)
    B((5.6, 8.6, 0.8), (0, -5.4, -2.35), 'gum')                              # upper gum
    B((4.6, 8.0, 0.6), (0, -5.6, -1.95), 'mouth')                            # palate
    B((2.2, 1.4, 1.2), (0, -1.6, -2.0), 'rune')                              # abyss glow in the throat
    # lower jaw hanging open, with its own teeth, spikes and a chin horn
    jr = (20, 0, 0)
    Rj = sk._rot(jr)
    jc = P(0, -5.0, -3.8)

    def JB(size, off, col, **kw):
        d.box(tuple(c * S for c in size), jc + Rj @ (V(off) * S), rot=jr, col=col, bone=J, **kw)

    JB((5.0, 8.8, 1.6), (0, 0, 0), 'main')
    JB((4.2, 8.0, 0.4), (0, 0, 0.9), 'mouth')
    JB((4.6, 8.4, 0.9), (0, 0, -1.05), 'belly')
    JB((2.2, 3.6, 0.5), (0, 0.6, 1.15), 'gum')                               # tongue
    for k in (1, -1):
        for i in range(6):
            JB((0.5, 0.5, 1.0), (1.85 * k, 3.0 - i * 1.15, 1.25), 'tooth', taper=(0.25, 0.3))
        JB((0.75, 0.75, 1.9), (1.4 * k, -3.6, 1.4), 'tooth', taper=(0.25, 0.3))      # lower fangs
        JB((0.6, 2.6, 0.9), (2.55 * k, 0.4, -0.2), 'dark')                            # jaw armour along the sides
        d.horn(jc + Rj @ (V((2.4 * k, 1.6, -0.6)) * S), (k, 0.5, -0.5), 1.8 * S, 0.5 * S, 2, 10, 'horn', J, tip='claw')   # jaw spikes
    d.horn(jc + Rj @ (V((0, -3.8, -0.9)) * S), (0, -0.4, -1), 1.4 * S, 0.6 * S, 2, -15, 'horn', J, tip='claw')            # chin horn
    # webbed crown of spines round the back of the head
    base = P(0, 2.2, 1.6)
    tips = []
    for ang in (-80, -52, -26, 0, 26, 52, 80):
        ar = math.radians(ang)
        tips.append(base + V((math.sin(ar) * 5.0, 2.4, math.cos(ar) * 4.6)) * S)
    for tp in tips:
        d.seg(base, tp, 0.5 * S, col='horn', bone=H, taper=(0.35, 0.35))
    for j in range(len(tips) - 1):
        d.slab([base, tips[j], tips[j + 1]], 0.24 * S, col='fin' if j % 2 == 0 else 'fin2', bone=H)
    return d
