"""Cerberus (epic tier). The reference for multi-headed creatures and glow: three snarling wolf heads built by
one function at different angles, fire manes, spiked collars, lava cracks, a pale chest of fur tufts and a
burning tail. Faces -Y."""
import math


def build(sk):
    V, rgb = sk.V, sk.rgb
    pal = {
        'fur': rgb(46, 42, 50), 'fur2': rgb(70, 66, 76), 'fur3': rgb(30, 28, 34), 'pale': rgb(200, 200, 210),
        'steel': rgb(160, 164, 176), 'leather': rgb(96, 36, 30), 'claw': rgb(20, 18, 22), 'tooth': rgb(246, 240, 226),
        'mouth': rgb(110, 20, 26), 'eye': rgb(255, 150, 30), 'fire': rgb(255, 84, 14), 'fire2': rgb(255, 190, 40),
        'lava': rgb(255, 78, 20),
    }
    d = sk.Creature('Cerberus', pal)
    d.glow.update({'eye', 'fire', 'fire2', 'lava'})

    # ---------------- bones ----------------
    d.bone('Body', (0, 5.2, 10.2), (0, -3.0, 10.2))
    d.bone('Neck', (0, -4.4, 12.6), (0, -6.6, 15.4), 'Body')
    d.bone('Head', (0, -6.8, 16.0), (0, -11.0, 16.0), 'Neck')
    d.bone('Jaw', (0, -9.4, 14.7), (0, -13.0, 14.4), 'Head')
    d.bone('NeckS_L', (2.4, -4.0, 12.2), (4.9, -5.8, 14.6), 'Body', mirror=True)
    d.bone('HeadS_L', (5.1, -6.2, 15.0), (6.4, -10.1, 15.0), 'NeckS_L', mirror=True)
    d.bone('JawS_L', (5.9, -8.7, 13.4), (7.0, -12.0, 13.2), 'HeadS_L', mirror=True)
    d.bone('Tail1', (0, 7.2, 11.4), (0, 10.4, 12.6), 'Body')
    d.bone('Tail2', (0, 10.4, 12.6), (0, 13.8, 12.4), 'Tail1')
    d.bone('Tail3', (0, 13.8, 12.4), (0, 17.6, 11.0), 'Tail2')
    d.bone('ArmU_L', (3.1, -3.0, 9.6), (3.2, -3.6, 5.0), 'Body', mirror=True)
    d.bone('ArmD_L', (3.2, -3.6, 5.0), (3.2, -4.0, 1.0), 'ArmU_L', mirror=True)
    d.bone('LegU_L', (3.0, 5.4, 10.0), (3.1, 3.8, 5.2), 'Body', mirror=True)
    d.bone('LegD_L', (3.1, 3.8, 5.2), (3.1, 4.6, 1.0), 'LegU_L', mirror=True)

    # ---------------- torso ----------------
    d.box((7.4, 5.8, 7.6), (0, -2.6, 10.4), col='fur', bone='Body')               # chest
    d.box((6.4, 5.0, 6.2), (0, 1.6, 9.8), col='fur', bone='Body')                 # belly
    d.box((6.8, 4.8, 6.8), (0, 5.2, 10.2), col='fur', bone='Body')                # hips
    for row, (z, w, n) in enumerate(((12.4, 5.4, 4), (10.6, 5.0, 4), (8.8, 4.4, 3), (7.2, 3.4, 2))):   # pale chest fur
        for i in range(n):
            x = (i - (n - 1) / 2) * (w / n)
            d.box((w / n + 0.25, 1.0, 2.3), (x, -5.7 - row * 0.2, z), rot=(14, 0, 0), col='pale', bone='Body', taper=(0.35, 0.8))
    d.box((5.4, 6.0, 0.8), (0, 1.6, 6.5), col='pale', bone='Body')                # pale belly
    d.box((6.0, 4.4, 1.6), (0, -2.4, 14.2), col='fur', bone='Body')               # shoulder hump
    d.box((4.6, 3.0, 1.0), (0, -2.4, 15.2), col='fur2', bone='Body')
    for s in (1, -1):                                                             # fur tufts behind the elbows
        d.box((1.2, 1.6, 2.2), (3.4 * s, -1.6, 6.6), rot=(-30, 0, 0), col='fur2', bone='ArmU_' + ('L' if s > 0 else 'R'), taper=(0.4, 0.3))
        d.box((1.2, 1.6, 2.2), (3.3 * s, 6.6, 6.8), rot=(-30, 0, 0), col='fur2', bone='LegU_' + ('L' if s > 0 else 'R'), taper=(0.4, 0.3))
    for y in (-3.6, -1.6, 0.4, 2.4, 4.4):                                          # rib plates on the sides
        d.box((0.6, 1.4, 4.2), (3.4, y, 10.2), col='fur2', bone='Body', mirror=True)
    d.box((2.2, 5.0, 5.4), (3.5, -2.8, 10.4), col='fur3', bone='Body', mirror=True)    # shoulders
    d.box((2.2, 5.0, 5.8), (3.3, 5.0, 10.0), col='fur3', bone='Body', mirror=True)     # haunches
    # lava cracks
    for a, b in (((3.82, -4.0, 11.6), (3.82, -2.2, 9.0)), ((3.82, -2.2, 9.0), (3.82, -1.2, 10.2)),
                 ((3.62, 4.0, 11.6), (3.62, 5.6, 9.6)), ((3.62, 5.6, 9.6), (3.62, 6.4, 10.6))):
        d.seg(a, b, (0.12, 0.3), col='lava', bone='Body', mirror=True)
    # spine plates and the fire mane down the back
    for i, y in enumerate((-3.6, -1.6, 0.4, 2.4, 4.4, 6.2)):
        d.box((3.0 - i * 0.1, 1.6, 0.6), (0, y, 14.4 - i * 0.12), col='steel', bone='Body')
    d.spikes((0, -3.2, 14.6), (0, 6.6, 14.0), 9, 1.8, 3.2, 1.0, 'fire', 'Body', lean=38, tip='fire2')
    d.spikes((1.4, -2.6, 14.2), (1.4, 5.0, 13.8), 5, 1.0, 1.6, 0.7, 'fire', 'Body', lean=40, tip='fire2', mirror=True)

    # ---------------- heads ----------------
    def head(neck, hd, jw, O, yaw, side):
        """Build a wolf head around origin O, facing -Y turned by yaw degrees. side = +1 left, -1 right, 0 middle."""
        Ry = sk._rot((0, 0, yaw))
        HS = 1.25

        def P(x, y, z):
            return V(O) + Ry @ (V((x, y, z)) * HS)

        def B(size, loc, col, bone, rot=(0, 0, 0), **kw):
            d.box(tuple(c * HS for c in size), P(*loc), rot=(rot[0], rot[1], rot[2] + yaw), col=col, bone=bone, **kw)

        B((3.2, 3.4, 2.8), (0, -1.0, 0.3), 'fur', hd)                                  # skull
        B((2.2, 2.8, 1.4), (0, -3.6, -0.1), 'fur', hd, taper=(0.9, 1))                 # snout
        B((2.3, 1.2, 0.6), (0, -2.6, 0.95), 'fur2', hd)                                # snout ridge
        B((1.0, 0.45, 0.6), (0, -5.0, 0.3), 'claw', hd)                                # nose
        for s in (1, -1):
            B((1.3, 1.1, 0.5), (0.85 * s, -2.5, 1.7), 'fur3', hd, rot=(0, -26 * s, 0))     # angry brows
            B((0.75, 0.22, 0.45), (0.9 * s, -2.75, 1.15), 'eye', hd)                     # eyes
            B((0.8, 0.6, 1.8), (1.0 * s, -0.2, 2.3), 'fur', hd, rot=(-14, 0, -12 * s), taper=(0.2, 0.35))   # ears
            B((0.5, 0.3, 1.1), (0.98 * s, -0.48, 2.1), 'mouth', hd, rot=(-14, 0, -12 * s), taper=(0.2, 0.3))
            B((0.7, 1.8, 1.4), (1.65 * s, -1.0, -0.3), 'fur2', hd)                       # cheek fur
            B((0.3, 0.3, 0.8), (0.65 * s, -4.45, -1.05), 'tooth', hd, rot=(180, 0, 0), taper=(0.25, 0.25))  # fangs
            B((0.26, 0.26, 0.5), (0.7 * s, -3.6, -0.95), 'tooth', hd, rot=(180, 0, 0), taper=(0.3, 0.3))
        B((1.7, 2.4, 0.4), (0, -3.4, -0.95), 'mouth', hd)                              # palate
        B((1.9, 2.8, 0.7), (0, -3.3, -1.55), 'fur', jw, rot=(14, 0, 0))                # jaw
        B((1.4, 2.4, 0.25), (0, -3.3, -1.15), 'mouth', jw, rot=(14, 0, 0))
        for s in (1, -1):
            B((0.28, 0.28, 0.6), (0.62 * s, -4.3, -1.0), 'tooth', jw, taper=(0.3, 0.3))
        # fire mane on the head
        for i, (x, y, h) in enumerate(((0, -1.6, 2.6), (0.7, -0.6, 2.4), (-0.7, -0.6, 2.4), (0, -0.2, 3.4),
                                        (0.6, 0.8, 2.6), (-0.6, 0.8, 2.6), (0, 1.6, 2.2))):
            rot = (-38 - i * 4, 0, 0)
            base = P(x, y, 1.4)
            h *= HS
            d.box((1.1 * HS, 1.3 * HS, h), base + sk._rot((rot[0], 0, yaw)) @ V((0, 0, h / 2)), rot=(rot[0], 0, yaw),
                  col='fire', bone=hd, taper=(0.15, 0.3))
            d.box((0.5 * HS, 0.6 * HS, h * 0.55), base + sk._rot((rot[0], 0, yaw)) @ V((0, 0, h * 0.4)), rot=(rot[0], 0, yaw),
                  col='fire2', bone=hd, taper=(0.2, 0.3))

    # side heads sit further out and a little lower, turned outward
    head('Neck', 'Head', 'Jaw', (0, -7.2, 16.4), 0, 0)
    head('NeckS_L', 'HeadS_L', 'JawS_L', (5.3, -6.4, 15.2), 16, 1)
    head('NeckS_R', 'HeadS_R', 'JawS_R', (-5.3, -6.4, 15.2), -16, -1)

    # necks, collars and the fire running down each neck
    for neck, a, b in (('Neck', (0, -4.0, 11.8), (0, -6.8, 16.0)), ('NeckS_L', (2.2, -3.8, 11.6), (5.0, -6.2, 15.0)),
                       ('NeckS_R', (-2.2, -3.8, 11.6), (-5.0, -6.2, 15.0))):
        a, b = V(a), V(b)
        d.seg(a, b, (3.0, 2.8), col='fur', bone=neck)
        m = a.lerp(b, 0.45)
        d.seg(m - (b - a).normalized() * 0.5, m + (b - a).normalized() * 0.5, (3.6, 3.4), col='leather', bone=neck)
        dirv = (b - a).normalized()
        side = V((1, 0, 0)).cross(dirv).normalized()
        for k in range(6):
            ang = k * math.pi / 3
            out = (V((1, 0, 0)) * math.cos(ang) + side * math.sin(ang)) if abs(dirv.x) < 0.9 else V((0, math.cos(ang), math.sin(ang)))
            p = m + out * 1.75
            d.seg(p, p + out * 0.9, 0.32, col='steel', bone=neck, taper=(0.15, 0.15))
        d.spikes(a.lerp(b, 0.65) + V((0, 0.8, 1.2)), a.lerp(b, 0.15) + V((0, 1.0, 1.4)), 3, 1.6, 2.2, 0.8, 'fire', neck,
                 lean=40, tip='fire2')

    # ---------------- legs ----------------
    d.seg((3.2, -3.0, 10.0), (3.2, -3.6, 4.8), (3.0, 3.2), col='fur', bone='ArmU_L', mirror=True)
    d.seg((3.2, -3.6, 5.2), (3.2, -4.0, 1.2), (2.5, 2.7), col='fur', bone='ArmD_L', mirror=True)
    d.box((2.7, 2.9, 0.7), (3.2, -4.0, 2.6), col='steel', bone='ArmD_L', mirror=True)          # leg band
    for z in (2.35, 2.85):
        d.box((0.3, 0.3, 0.3), (4.62, -4.0, z), col='steel', bone='ArmD_L', mirror=True)
    d.seg((4.6, -3.3, 8.4), (4.6, -3.5, 6.2), (0.12, 0.3), col='lava', bone='ArmU_L', mirror=True)
    d.foot((3.2, -4.6, 0.55), (3.0, 3.0, 1.1), 3, 'fur3', 'claw', 'ArmD_L', forward=-1, mirror=True)
    d.seg((3.0, 5.6, 10.4), (3.1, 3.8, 5.0), (3.2, 3.6), col='fur', bone='LegU_L', mirror=True)
    d.seg((3.1, 3.8, 5.3), (3.1, 4.6, 1.2), (2.5, 2.7), col='fur', bone='LegD_L', mirror=True)
    d.box((2.7, 2.9, 0.7), (3.1, 4.3, 2.6), col='steel', bone='LegD_L', mirror=True)
    d.foot((3.1, 3.6, 0.55), (3.0, 3.2, 1.1), 3, 'fur3', 'claw', 'LegD_L', forward=-1, mirror=True)

    # ---------------- tail ----------------
    pts = [V((0, 7.0, 11.4)), V((0, 10.4, 12.6)), V((0, 13.8, 12.4)), V((0, 17.6, 11.0))]
    for i, (bn, t) in enumerate((('Tail1', 2.2), ('Tail2', 1.7), ('Tail3', 1.3))):
        d.seg(pts[i], pts[i + 1] + (pts[i + 1] - pts[i]).normalized() * 0.3, t, col='fur', bone=bn)
    d.spikes((0, 8.0, 13.2), (0, 13.0, 13.4), 4, 0.9, 1.3, 0.6, 'fire', 'Tail2', lean=60, tip='fire2')
    for k in range(5):                                       # burning tail tip
        ang = k * 2 * math.pi / 5
        base = V((0, 17.4, 11.1))
        dirv = V((math.cos(ang) * 0.6, 0.8, math.sin(ang) * 0.6 + 0.4)).normalized()
        d.seg(base, base + dirv * (2.6 if k % 2 == 0 else 2.0), 0.9, col='fire', bone='Tail3', taper=(0.2, 0.2))
    d.seg(V((0, 17.2, 11.1)), V((0, 19.4, 11.8)), 0.8, col='fire2', bone='Tail3', taper=(0.2, 0.2))
    return d
