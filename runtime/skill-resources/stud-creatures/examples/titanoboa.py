"""Titanoboa (epic tier). The colossal constrictor: a
thick body lying in a big S on the ground, the front third reared up in a strike curve; python saddle blotches with
paler centres down the back, dark side blotches, pale ridges running across the joints, a banded pale belly and
glowing jade spots along the spine; a wide, heavy, angry head - horned brow ridges over glowing eyes, dark eye
stripes, glowing jade heat pits along the lips, jaws open with long fangs and a forked tongue."""
import blockkit as bk
from mathutils import Vector as V

PTS = [(0, -9.2, 11.4), (0, -6.8, 11.2), (0, -4.8, 9.2), (0, -4.0, 6.3), (0.6, -2.6, 3.0), (3.6, -0.2, 2.8), (4.8, 3.4, 2.8),
       (2.6, 6.6, 2.8), (-1.2, 7.6, 2.7), (-4.4, 9.6, 2.5), (-5.2, 13.0, 2.2), (-3.4, 16.0, 1.9), (-0.4, 17.6, 1.5), (2.6, 18.2, 1.0)]
RADII = [2.0, 2.1, 2.3, 2.5, 2.7, 2.8, 2.8, 2.7, 2.55, 2.3, 2.0, 1.6, 1.1, 0.55]


def build(sk):
    rgb = sk.rgb
    pal = {'main': rgb(88, 116, 58), 'main2': rgb(118, 150, 76), 'dark': rgb(46, 60, 34), 'dark2': rgb(30, 40, 24),
           'belly': rgb(222, 208, 150), 'belly2': rgb(186, 168, 112), 'jade': rgb(70, 240, 160), 'eye': rgb(255, 214, 60),
           'mouth': rgb(150, 50, 60), 'tongue': rgb(200, 40, 70), 'tooth': rgb(248, 244, 230), 'horn': rgb(70, 58, 44),
           'claw': rgb(24, 22, 20)}
    d = sk.Creature('Titanoboa', pal)
    d.glow.update({'eye', 'jade'})
    d.smooth.update({'tooth', 'horn', 'claw'})

    # ---------------- the body: a big S on the ground, the front reared up ----------------
    segs = bk.serpent(d, PTS, RADII, 'main', belly='belly', flat=0.86)
    for s in segs:
        a, b, t, up, side, r, h, bone, i = s['a'], s['b'], s['t'], s['up'], s['side'], s['r'], s['h'], s['bone'], s['i']
        m = a.lerp(b, 0.5)
        L = (b - a).length
        if r < 0.7:
            continue
        # python saddles: a dark blotch with a paler centre, every other segment; a jade spot on the others
        if i % 2 == 0:
            d.seg(a.lerp(b, 0.15) + up * (h - 0.02), a.lerp(b, 0.85) + up * (h - 0.02), (2 * r * 0.78, 0.42), col='dark', bone=bone)
            d.seg(a.lerp(b, 0.35) + up * (h + 0.1), a.lerp(b, 0.65) + up * (h + 0.1), (2 * r * 0.36, 0.36), col='main2', bone=bone)
        else:
            d.seg(a.lerp(b, 0.3) + up * (h - 0.02), a.lerp(b, 0.7) + up * (h - 0.02), (2 * r * 0.34, 0.4), col='dark2', bone=bone)
            d.box((0.5, 0.5, 0.36), m + up * (h + 0.2), col='jade', bone=bone)
        for k in (1, -1):
            # pale ridge along each flank, running across the joints so the body reads as one piece
            d.seg(a - t * 0.45 + side * k * (r - 0.1) + up * h * 0.35, b + t * 0.45 + side * k * (r - 0.1) + up * h * 0.35, (0.5, 0.7),
                  col='main2', bone=bone)
            # dark side blotches, staggered against the saddles
            off = 0.3 if i % 2 == 0 else 0.7
            c = a.lerp(b, off) + side * k * (r + 0.02) - up * h * 0.25
            d.seg(c - t * min(0.9, L * 0.2), c + t * min(0.9, L * 0.2), (0.3, h * 0.7), col='dark', bone=bone)
        # belly scutes
        for f in (0.3, 0.7):
            p = a.lerp(b, f) - up * (h + 0.14)
            d.seg(p - side * r * 0.55, p + side * r * 0.55, (0.3, 0.16), col='belly2', bone=bone)
    tail = segs[-1]
    d.seg(tail['a'], tail['a'] - tail['t'] * 1.2, (0.5, 0.45), col='dark', bone=tail['bone'], taper=(0.3, 0.3))   # tail tip

    # ---------------- the head: wide, heavy and angry ----------------
    O = V((0, -11.8, 11.7))
    H, J = 'Head', 'Jaw'

    def P(x, y, z):
        return O + V((x, y, z))

    d.bone(H, P(0, 2.6, -0.2), P(0, -5.0, -0.2), 'Seg1')
    d.bone(J, P(0, 1.4, -1.3), P(0, -4.6, -3.4), H)
    d.box((5.4, 4.6, 2.6), P(0, 0, 0), col='main', bone=H)                                  # broad flat skull
    d.box((4.4, 3.2, 1.8), P(0, -3.7, -0.4), col='main', bone=H, taper=(0.85, 1))           # snout
    d.box((4.2, 1.6, 2.2), P(0, 2.8, -0.2), col='main', bone=H)                             # back of the skull into the neck
    d.box((5.0, 2.4, 0.6), P(0, -0.7, 1.55), col='dark', bone=H)                            # brow plate
    d.box((3.6, 2.4, 0.5), P(0, 1.6, 1.45), col='dark2', bone=H)                            # crown plate
    d.box((1.0, 1.0, 0.3), P(0, 1.6, 1.8), rot=(0, 0, 45), col='jade', bone=H)              # jade rune on the crown
    d.box((2.0, 2.6, 0.4), P(0, -3.6, 0.68), col='main2', bone=H)                           # snout ridge
    for k in (1, -1):
        d.box((2.1, 2.6, 0.8), P(1.65 * k, -1.7, 1.55), rot=(0, -26 * k, 0), col='dark', bone=H)     # heavy angry brows
        d.horn(P(2.1 * k, -0.6, 1.7), (0.45 * k, 1.0, 0.55), 3.6, 0.75, 4, -12, 'horn', H, tip='claw')   # brow horns swept back
        d.box((1.4, 0.22, 0.8), P(1.85 * k, -2.36, 0.85), col='eye', bone=H)                  # big glowing eyes, front face
        d.box((0.24, 1.8, 0.8), P(2.74 * k, -1.4, 0.85), col='eye', bone=H)                  # ... and side face
        d.seg(P(2.74 * k, -0.6, 0.3), P(2.74 * k, 2.0, -1.1), (0.22, 0.5), col='dark2', bone=H)   # dark stripe from eye to jaw
        for y in (-2.6, -3.3, -4.0, -4.7):                                                   # glowing heat pits along the lip
            d.box((0.2, 0.36, 0.3), P(2.12 * k - 0.04 * k * (y + 2.6) * 1.0, y, -1.0), col='jade', bone=H)
        d.box((0.5, 2.6, 1.6), P(2.75 * k, 0.6, -0.4), col='dark', bone=H)                   # cheek scales
    # open mouth: palate, small teeth and long front fangs
    d.box((3.8, 6.6, 0.4), P(0, -2.4, -1.5), col='mouth', bone=H)
    for k in (1, -1):
        for y in (-3.6, -2.8, -2.0, -1.2, -0.4):
            d.box((0.3, 0.3, 0.55), P(1.55 * k, y, -1.95), rot=(180, 0, 0), col='tooth', bone=H, taper=(0.3, 0.3))
        d.box((0.5, 0.5, 2.0), P(1.25 * k, -4.6, -2.6), rot=(170, 0, 0), col='tooth', bone=H, taper=(0.2, 0.25))
    jr = (28, 0, 0)
    Rj = sk._rot(jr)
    jp = P(0, 1.4, -1.3)

    def JB(size, off, col, **kw):
        d.box(size, jp + Rj @ V(off), rot=jr, col=col, bone=J, **kw)

    JB((4.4, 6.6, 0.9), (0, -3.3, -0.6), 'main')
    JB((3.6, 6.0, 0.3), (0, -3.4, -0.05), 'mouth')
    JB((4.0, 6.2, 0.4), (0, -3.2, -1.2), 'belly')
    for k in (1, -1):
        JB((0.4, 5.4, 0.5), (2.15 * k, -3.0, -0.4), 'dark')                                   # scales along the jaw
        for y in (-5.6, -4.8, -4.0, -3.2, -2.4):
            JB((0.28, 0.28, 0.5), (1.5 * k, y, 0.25), 'tooth', taper=(0.3, 0.3))
    # forked tongue flicking out
    t0 = jp + Rj @ V((0, -4.2, 0.15))
    t1 = jp + Rj @ V((0, -8.0, 0.6))
    d.seg(t0, t1, (0.4, 0.16), col='tongue', bone=J)
    for k in (1, -1):
        d.seg(t1, t1 + V((0.55 * k, -1.2, -0.1)), (0.26, 0.14), col='tongue', bone=J)
    return d
