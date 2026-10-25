"""Kraken (epic tier). A colossal crimson squid: a wide head
with two ENORMOUS glowing gold eyes in dark rings under heavy angry brows, a hooked black beak, a tall stepped mantle
leaning back, banded and spotted with glowing bioluminescence, a row of spikes down its back and big arrowhead fins
on top; eight thick tentacles spreading over the ground, curling up at the tips, dark-ridged on top with two rows
of pale suckers underneath, and two long hunting tentacles raised up in front with hooked clubs."""
import math
from mathutils import Vector as V
C = V((0, -0.6, 0))


def _tentacles():
    out = []
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        r = V((math.cos(a), math.sin(a), 0))
        tg = V((-math.sin(a), math.cos(a), 0))
        p0 = C + r * 2.6 + V((0, 0, 7.6))
        p1 = C + r * 6.4 + V((0, 0, 4.0))
        p2 = C + r * 10.4 + V((0, 0, 1.3))
        p3 = p2 + r * 2.0 + tg * 1.2 + V((0, 0, 2.6))                          # the tip curls up and to the side
        out.append((p0, p1, p2, p3))
    for k in (1, -1):                                                          # hunting tentacles raised in front
        out.append((V((1.6 * k, -3.6, 8.4)), V((4.4 * k, -6.6, 11.2)), V((5.4 * k, -8.2, 15.0)), V((4.4 * k, -7.8, 18.2))))
    return out


TENTACLES = _tentacles()


def build(sk):
    rgb = sk.rgb
    pal = {'main': rgb(176, 46, 84), 'main2': rgb(204, 74, 108), 'dark': rgb(116, 26, 58), 'light': rgb(236, 140, 162),
           'sucker': rgb(252, 210, 212), 'eye': rgb(255, 214, 46), 'lumi': rgb(96, 240, 255), 'beak': rgb(44, 32, 32),
           'eyering': rgb(70, 18, 40)}
    d = sk.Creature('Kraken', pal)
    d.glow.update({'eye', 'lumi'})
    d.smooth.update({'beak'})

    d.bone('Body', (0, -0.6, 7.0), (0, 1.6, 26.0))
    for k, pts in enumerate(TENTACLES):
        for j in range(3):
            d.bone('Ten%d_%d' % (k + 1, j + 1), pts[j], pts[j + 1], 'Body' if j == 0 else 'Ten%d_%d' % (k + 1, j))

    # ---------------- head: huge eyes, angry brows, hooked beak ----------------
    B = 'Body'
    d.box((6.4, 6.4, 1.6), (0, -0.6, 7.6), col='dark', bone=B)                       # ring where the tentacles join
    d.box((7.8, 7.2, 4.6), (0, -0.6, 10.6), col='main', bone=B)                      # wide head
    d.box((8.2, 7.6, 0.6), (0, -0.6, 12.9), col='dark', bone=B)                      # collar under the mantle
    for k in (1, -1):
        d.box((2.8, 0.3, 2.6), (2.2 * k, -4.3, 10.6), col='eyering', bone=B)          # dark eye ring
        d.box((2.2, 0.3, 1.9), (2.2 * k, -4.45, 10.5), col='eye', bone=B)             # enormous glowing eye, front
        d.box((0.3, 2.4, 1.9), (4.05 * k, -2.6, 10.5), col='eye', bone=B)             # ... wrapping round the side
        d.box((0.3, 3.0, 2.6), (3.95 * k, -2.6, 10.6), col='eyering', bone=B)
        d.box((3.2, 1.6, 0.9), (2.2 * k, -4.4, 12.2), rot=(0, -24 * k, 0), col='dark', bone=B)   # heavy angry brows
        d.box((0.9, 1.2, 1.4), (3.6 * k, -4.0, 8.6), col='dark', bone=B)              # cheek ridges
    d.box((2.0, 1.6, 1.2), (0, -4.4, 8.4), col='beak', bone=B)                        # hooked beak
    d.box((1.4, 1.2, 1.4), (0, -5.0, 7.6), rot=(-20, 0, 0), col='beak', bone=B, taper=(0.4, 0.6))
    d.box((1.2, 1.0, 1.0), (0, -4.6, 6.6), rot=(160, 0, 0), col='beak', bone=B, taper=(0.4, 0.5))
    d.box((0.8, 0.3, 0.6), (0, -4.6, 9.3), col='light', bone=B)                       # pale glint over the beak

    # ---------------- tall tapering mantle, leaning back ----------------
    # each block's top face is shrunk and shifted back to meet the next one: one smooth cone, not a stack of boxes
    steps = [((7.6, 7.2, 4.0), (0, -0.2, 15.0), (6.8, 6.6)), ((6.8, 6.6, 4.0), (0, 0.5, 19.0), (5.6, 5.6)),
             ((5.6, 5.6, 3.6), (0, 1.2, 22.8), (4.0, 4.2)), ((4.0, 4.2, 2.8), (0, 1.9, 26.0), (2.4, 2.6))]

    def face(i, f, side, k=1):
        """A point on step i's front (side='front') or flank (side='flank', k = +1 left / -1 right) at height fraction f."""
        (sx, sy, sz), c, (tx, ty) = steps[i]
        z = c[2] - sz / 2 + sz * f
        cy = c[1] + 0.7 * f
        if side == 'front':
            return V((0, cy - (sy + (ty - sy) * f) / 2, z))
        return V((k * (sx + (tx - sx) * f) / 2, cy, z))

    for (sx, sy, sz), c, (tx, ty) in steps:
        d.box((sx, sy, sz), c, col='main', bone=B, taper=(tx / sx, ty / sy), shift=(0, 0.7))
    d.box((2.4, 2.6, 1.6), (0, 2.6, 28.2), col='main', bone=B, taper=(0.3, 0.3), shift=(0, 0.4))       # mantle tip
    for i, f, x in ((0, 0.35, -1.6), (0, 0.7, 1.4), (1, 0.2, -0.4), (1, 0.6, 2.0), (1, 0.85, -1.8), (2, 0.3, 0.6), (2, 0.75, -1.0), (3, 0.4, 0.4)):
        p = face(i, f, 'front')
        d.box((0.5, 0.5, 0.5), p + V((x * (1 - 0.15 * i), 0, 0)), col='lumi', bone=B)              # glowing spots on the front
    for k in (1, -1):
        for i, f, y in ((0, 0.3, -1.6), (0, 0.7, 1.2), (1, 0.4, -0.8), (1, 0.8, 1.6), (2, 0.5, 0.2), (3, 0.3, -0.2)):
            d.box((0.5, 0.5, 0.5), face(i, f, 'flank', k) + V((0, y, 0)), col='lumi', bone=B)
        for i in range(3):                                                                             # pale stripe down each flank
            d.seg(face(i, 0.0, 'flank', k) + V((0, 1.6, 0)), face(i, 1.0, 'flank', k) + V((0, 1.6, 0)), (0.8, 0.4), col='main2', bone=B)
        # swept fins on the upper mantle (squid fins), angled back and up
        d.slab([(2.2 * k, 1.0, 20.6), (6.2 * k, 4.4, 23.6), (5.0 * k, 4.6, 25.4), (1.6 * k, 2.8, 26.4)], 0.6, col='main2', bone=B)
        d.seg((2.4 * k, 1.0, 20.8), (6.2 * k, 4.4, 23.6), (0.5, 0.5), col='dark', bone=B)
    d.spikes((0, 3.5, 14.6), (0, 3.7, 25.0), 6, 1.2, 1.8, 0.8, 'dark', B, lean=60, tip='beak')   # spikes down its back

    # ---------------- tentacles ----------------
    TH = [(2.1, 1.8), (1.6, 1.35), (1.1, 0.95)]
    for k, pts in enumerate(TENTACLES):
        hunt = k >= 8
        for j in range(3):
            a, b = pts[j], pts[j + 1]
            t = (b - a).normalized()
            side = t.cross(V((0, 0, 1)))
            side = side.normalized() if side.length > 0.01 else V((1, 0, 0))
            up = side.cross(t).normalized()
            w, h = TH[j] if not hunt else (TH[j][0] * 0.8, TH[j][1] * 0.8)
            bone = 'Ten%d_%d' % (k + 1, j + 1)
            d.seg(a - t * 0.35, b + t * (0.35 if j < 2 else 0.0), (w, h), col='main', bone=bone, taper=(1, 1) if j < 2 else (0.6, 0.6))
            L = (b - a).length
            # dark ridge along the top
            d.seg(a.lerp(b, 0.1) + up * (h / 2 - 0.05), a.lerp(b, 0.85) + up * (h / 2 - 0.05), (w * 0.4, 0.3), col='dark', bone=bone)
            # two rows of pale suckers underneath ('up' of a hunting arm faces outward, its suckers face the prey)
            n = 3 if j < 2 else 2
            for q in range(n):
                p = a.lerp(b, 0.2 + 0.6 * q / max(1, n - 1)) - up * (h / 2 + 0.05)
                for s in (1, -1):
                    d.box((0.45 * w / 2.1 + 0.15, 0.5, 0.3), p + side * s * w * 0.22, rot=None, col='sucker', bone=bone)
            if j == 1 and not hunt:
                d.box((0.4, 0.4, 0.3), a.lerp(b, 0.5) + up * (h / 2 + 0.1), col='lumi', bone=bone)
        if hunt:
            # hooked club at the end of each hunting tentacle
            a, b = pts[2], pts[3]
            t = (b - a).normalized()
            d.seg(b - t * 0.4, b + t * 2.2, (1.8, 1.6), col='main2', bone='Ten%d_3' % (k + 1), taper=(0.5, 0.5))
            for q in range(3):
                p = (b + t * (0.2 + q * 0.7))
                for s in (1, -1):
                    out = V((s * 1.0, -0.6, 0)).normalized()
                    d.seg(p + out * 0.6, p + out * 1.5 + t * 0.3, 0.32, col='beak', bone='Ten%d_3' % (k + 1), taper=(0.2, 0.2))
    return d
