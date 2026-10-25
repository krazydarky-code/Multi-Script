"""Hydra (epic tier). A heavy sapphire dragon body - armoured
chest, belly and hips, gold belly plates, a glowing star crystal in the chest, cyan fin spikes down the spine - on
four clawed legs, five armoured necks fanning out of a wide shoulder mantle, each ending in a full dragon head (angry
brows, glowing gold eyes, open jaws with teeth, a cyan glow in the throat, swept horns, a fin crest), the middle one
biggest and highest, and a long spiked tail ending in a fin fan."""
import math
from mathutils import Vector as V

# head n = 1..5 from the right (-x) to the left (+x): skull centre, yaw (degrees, + turns to the left), size
HEADS = [((-11.6, -8.0, 15.6), -34, 0.74), ((-6.4, -11.4, 18.8), -16, 0.86), ((0.0, -12.8, 21.6), 0, 1.0),
         ((6.4, -11.4, 18.8), 16, 0.86), ((11.6, -8.0, 15.6), 34, 0.74)]
BASES = [(-3.3, -4.8, 11.2), (-1.65, -5.2, 11.6), (0.0, -5.4, 11.9), (1.65, -5.2, 11.6), (3.3, -4.8, 11.2)]
MIDS = [(-7.6, -6.4, 13.4), (-4.0, -8.0, 15.8), (0.0, -8.6, 17.8), (4.0, -8.0, 15.8), (7.6, -6.4, 13.4)]


def build(sk):
    rgb = sk.rgb
    pal = {'main': rgb(40, 78, 176), 'main2': rgb(62, 104, 206), 'dark': rgb(24, 46, 118), 'belly': rgb(244, 204, 96),
           'belly2': rgb(214, 168, 66), 'fin': rgb(96, 224, 242), 'fin2': rgb(60, 162, 224), 'horn': rgb(236, 230, 210),
           'claw': rgb(20, 24, 40), 'tooth': rgb(250, 248, 240), 'mouth': rgb(96, 24, 56), 'eye': rgb(255, 216, 64),
           'star': rgb(150, 244, 255)}
    d = sk.Creature('Hydra', pal)
    d.glow.update({'eye', 'star'})
    d.smooth.update({'horn', 'tooth', 'claw'})

    # ---------------- bones ----------------
    d.bone('Body', (0, 5.0, 8.6), (0, -5.0, 9.2))
    d.bone('ArmU_L', (3.6, -3.4, 8.8), (4.6, -4.2, 4.8), 'Body', mirror=True)
    d.bone('ArmD_L', (4.6, -4.2, 4.8), (4.4, -4.8, 1.0), 'ArmU_L', mirror=True)
    d.bone('LegU_L', (3.2, 4.6, 8.6), (4.2, 3.0, 4.8), 'Body', mirror=True)
    d.bone('LegD_L', (4.2, 3.0, 4.8), (4.2, 4.4, 1.0), 'LegU_L', mirror=True)
    d.bone('Tail1', (0, 6.4, 8.6), (0, 10.4, 7.8), 'Body')
    d.bone('Tail2', (0, 10.4, 7.8), (0, 14.4, 6.8), 'Tail1')
    d.bone('Tail3', (0, 14.4, 6.8), (0, 20.6, 6.4), 'Tail2')
    frames = []
    for k, (O, yaw, s) in enumerate(HEADS):
        n = k + 1
        R = sk._rot((0, 0, yaw))
        O = V(O)
        back = O + R @ (V((0, 1.6, -0.3)) * s)
        d.bone('Neck%d' % n, BASES[k], back, 'Body')
        d.bone('Head%d' % n, back, O + R @ (V((0, -4.8, 0)) * s), 'Neck%d' % n)
        d.bone('Jaw%d' % n, O + R @ (V((0, -0.6, -1.3)) * s), O + R @ (V((0, -4.2, -2.4)) * s), 'Head%d' % n)
        frames.append((n, O, yaw, s, R, back))

    # ---------------- torso ----------------
    d.box((8.0, 5.0, 6.0), (0, -3.4, 9.0), col='main', bone='Body')                    # chest
    d.box((7.2, 5.0, 5.4), (0, 0.8, 8.5), col='main', bone='Body')                     # belly
    d.box((6.6, 4.0, 5.4), (0, 4.6, 8.5), col='main', bone='Body')                     # hips
    d.box((8.4, 3.6, 1.6), (0, -3.6, 12.6), col='main', bone='Body')                   # shoulder mantle the necks grow from
    d.box((7.6, 1.4, 4.4), (0, -5.9, 10.4), col='main', bone='Body')                   # front of the mantle
    for i, y in enumerate((-1.6, 0.2, 2.0, 3.8, 5.6)):                                  # dark armour plates down the back
        d.box((5.4 - i * 0.3, 1.7, 0.7), (0, y, 11.25 - i * 0.05), col='dark', bone='Body')
    d.spikes((0, -1.6, 11.6), (0, 6.2, 11.2), 6, 1.2, 1.9, 0.75, 'fin', 'Body', lean=35, tip='fin2')
    d.box((2.2, 4.6, 4.6), (4.15, -3.4, 9.6), col='dark', bone='Body', mirror=True)    # shoulder armour
    d.box((2.4, 3.8, 0.8), (4.25, -3.4, 12.0), rot=(0, -18, 0), col='main2', bone='Body', mirror=True)
    d.box((2.2, 4.2, 4.6), (3.55, 4.6, 8.9), col='dark', bone='Body', mirror=True)     # haunch armour
    d.box((2.4, 3.6, 0.8), (3.65, 4.6, 11.3), rot=(0, -18, 0), col='main2', bone='Body', mirror=True)
    for i, y in enumerate((-1.2, 0.6, 2.4)):                                            # side scales between them
        z = 9.6 if i % 2 == 0 else 8.2
        d.box((0.5, 1.6, 1.4), (3.62, y, z), col='main2', bone='Body', mirror=True)
        d.box((0.45, 1.4, 1.2), (3.6, y + 0.8, z - 1.6), col='dark', bone='Body', mirror=True)
    for y in (-4.4, -2.6, -0.8, 1.0, 2.8, 4.6):                                          # gold belly plates
        d.box((5.4, 1.6, 0.7), (0, y, 5.8), col='belly', bone='Body')
    for i, z in enumerate((11.4, 10.0, 8.6, 7.2)):                                        # gold chest plates
        d.box((5.2 - i * 0.5, 0.8, 1.2), (0, -6.75, z), col='belly', bone='Body')
        d.box((5.4 - i * 0.5, 0.6, 0.25), (0, -6.6, z - 0.68), col='belly2', bone='Body')
    d.box((2.6, 0.5, 2.6), (0, -7.2, 9.2), rot=(0, 45, 0), col='belly2', bone='Body')   # gold setting of the star
    d.box((1.7, 0.5, 1.7), (0, -7.45, 9.2), rot=(0, 45, 0), col='star', bone='Body')    # glowing star crystal

    # ---------------- necks ----------------
    for n, O, yaw, s, R, back in frames:
        b0, m, e = V(BASES[n - 1]), V(MIDS[n - 1]), back
        t0, t1 = 1.9 + 0.6 * s, 1.6 + 0.4 * s
        bone = 'Neck%d' % n
        for a, b, t in ((b0, m, t0), (m, e, t1)):
            dirv = (b - a).normalized()
            d.seg(a - dirv * 0.9, b + dirv * 0.5, (t, t), col='main', bone=bone)
            side = dirv.cross(V((0, 0, 1))).normalized()
            up = side.cross(dirv).normalized()
            d.seg(a + dirv * 0.4 - up * (t / 2 - 0.12), b - dirv * 0.2 - up * (t / 2 - 0.12), (t * 0.62, 0.42), col='belly', bone=bone)
            d.spikes(a.lerp(b, 0.2) + up * (t / 2 - 0.12), a.lerp(b, 0.85) + up * (t / 2 - 0.12), 2, 0.6 + 0.4 * s, 0.8 + 0.5 * s, 0.5,
                     'fin', bone, lean=45, tip='fin2')
        dirv = (m - b0).normalized()
        c = b0 + dirv * 1.0
        d.seg(c - dirv * 0.35, c + dirv * 0.35, (t0 * 1.28, t0 * 1.28), col='dark', bone=bone)             # collar
        d.seg(c - dirv * 0.45, c + dirv * 0.45, (t0 * 1.12, t0 * 1.36), col='belly2', bone=bone)          # gold band in it

    # ---------------- heads ----------------
    for n, O, yaw, s, R, back in frames:
        hd, jw = 'Head%d' % n, 'Jaw%d' % n

        def P(x, y, z):
            return O + R @ (V((x, y, z)) * s)

        def B(size, loc, col, bone=hd, rot=(0, 0, 0), **kw):
            d.box(tuple(c * s for c in size), P(*loc), rot=(rot[0], rot[1], rot[2] + yaw), col=col, bone=bone, **kw)

        def D(v):
            return R @ V(v)

        B((3.2, 3.6, 2.8), (0, 0, 0), 'main')                                   # skull
        B((2.5, 3.4, 1.6), (0, -3.1, -0.4), 'main', taper=(0.88, 1))            # snout
        B((2.6, 1.6, 0.9), (0, -4.0, 0.3), 'main2')                             # nose ridge
        B((2.2, 2.4, 0.6), (0, -0.6, 1.55), 'dark')                             # brow plate
        for k in (1, -1):
            B((1.25, 1.5, 0.5), (0.95 * k, -1.5, 1.2), 'dark', rot=(0, -28 * k, 0))            # angry brows
            B((0.8, 0.22, 0.5), (1.08 * k, -2.02, 0.65), 'eye')                               # eyes, front face
            B((0.25, 1.0, 0.5), (1.62 * k, -1.4, 0.65), 'eye')                                # eyes, side face
            B((0.36, 0.22, 0.24), (0.6 * k, -4.81, -0.25), 'claw')                            # nostrils (dark: in a bright colour they read as eyes)
            for y in (-4.4, -3.6, -2.8, -2.0):                                                 # upper teeth
                B((0.32, 0.32, 0.6), (0.95 * k, y, -1.5), 'tooth', rot=(180, 0, 0), taper=(0.3, 0.3))
            d.horn(P(1.2 * k, 0.6, 1.1), D((0.35 * k, 1.0, 0.55)), 5.0 * s, 0.85 * s, 5, -14, 'horn', hd, tip='claw')   # swept horns
            d.horn(P(1.5 * k, 0.2, 0.0), D((0.9 * k, 0.9, 0.1)), 2.6 * s, 0.5 * s, 3, -10, 'horn', hd, tip='claw')
            d.horn(P(1.6 * k, -1.6, -0.9), D((1.0 * k, 0.7, -0.4)), 1.4 * s, 0.38 * s, 2, 12, 'fin', hd)                  # cheek fins
            B((0.4, 1.0, 0.6), (1.15 * k, -1.2, -2.2), 'dark', bone=jw, rot=(0, 0, -30 * k))                  # jaw spikes
        d.horn(P(0, -4.3, 0.6), D((0, -0.5, 1)), 1.0 * s, 0.45 * s, 2, -20, 'horn', hd, tip='claw')            # nose horn
        B((1.7, 3.0, 0.6), (0, -2.8, -1.45), 'mouth')                                                          # palate
        B((1.0, 0.8, 0.6), (0, -1.4, -1.3), 'star')                                                            # glow in the throat
        B((2.2, 3.9, 0.9), (0, -2.4, -2.25), 'main', bone=jw, rot=(16, 0, 0))                                 # open jaw
        B((1.6, 3.4, 0.3), (0, -2.4, -1.75), 'mouth', bone=jw, rot=(16, 0, 0))
        B((1.9, 3.2, 0.4), (0, -2.2, -2.75), 'belly', bone=jw, rot=(16, 0, 0))                                # gold chin
        for k in (1, -1):
            for y in (-3.9, -3.1, -2.3):
                B((0.32, 0.32, 0.55), (0.8 * k, y, -1.5 + (y + 2.4) * 0.28), 'tooth', bone=jw, rot=(16, 0, 0), taper=(0.3, 0.3))
        d.slab([P(0, -0.4, 1.3), P(0, 1.2, 2.9), P(0, 2.2, 2.2), P(0, 1.8, 1.0)], 0.55 * s, col='fin', bone=hd)   # fin crest
        d.spikes(P(0, 0.2, 1.9), P(0, 1.7, 2.9), 3, 0.7 * s, 1.0 * s, 0.35 * s, 'fin2', hd, lean=30)

    # ---------------- legs ----------------
    d.seg((3.5, -3.4, 9.4), (4.6, -4.2, 4.6), (2.8, 3.0), col='main', bone='ArmU_L', mirror=True)
    d.box((3.0, 1.4, 1.9), (4.6, -5.4, 4.9), col='dark', bone='ArmU_L', mirror=True)          # elbow plate
    d.seg((4.6, -4.2, 5.0), (4.4, -4.8, 1.2), (2.4, 2.6), col='main', bone='ArmD_L', mirror=True)
    d.box((2.6, 2.8, 0.6), (4.4, -4.8, 2.0), col='belly2', bone='ArmD_L', mirror=True)        # gold wrist band
    d.foot((4.4, -5.3, 0.55), (3.0, 3.0, 1.1), 3, 'main', 'claw', 'ArmD_L', forward=-1, mirror=True)
    d.seg((3.2, 5.0, 9.2), (4.2, 3.0, 4.6), (3.2, 3.6), col='main', bone='LegU_L', mirror=True)
    d.box((3.0, 1.3, 1.9), (4.2, 1.8, 5.0), col='dark', bone='LegU_L', mirror=True)           # knee plate
    d.seg((4.2, 3.0, 5.0), (4.2, 4.4, 1.2), (2.4, 2.6), col='main', bone='LegD_L', mirror=True)
    d.foot((4.2, 3.6, 0.55), (3.0, 3.2, 1.1), 3, 'main', 'claw', 'LegD_L', forward=-1, mirror=True)
    d.box((0.6, 1.0, 0.6), (4.2, 5.6, 0.5), rot=(-90, 0, 0), col='claw', bone='LegD_L', taper=(0.3, 0.2), mirror=True)

    # ---------------- tail ----------------
    tail = [V((0, 6.0, 8.8)), V((0, 10.4, 7.8)), V((0, 14.4, 6.8)), V((0, 17.6, 6.2)), V((0, 20.6, 6.4))]
    thick = [(3.6, 3.4), (2.8, 2.6), (2.0, 1.9), (1.4, 1.3)]
    bones = ['Tail1', 'Tail2', 'Tail3', 'Tail3']
    for i in range(4):
        a, b = tail[i], tail[i + 1]
        d.seg(a, b + (b - a).normalized() * 0.3, thick[i], col='main', bone=bones[i])
        d.seg(a.lerp(b, 0.15) - V((0, 0, thick[i][1] / 2 - 0.1)), a.lerp(b, 0.85) - V((0, 0, thick[i][1] / 2 - 0.1)),
              (thick[i][0] * 0.6, 0.45), col='belly', bone=bones[i])
        top = thick[i][1] / 2 - 0.1
        d.spikes(a.lerp(b, 0.2) + V((0, 0, top)), a.lerp(b, 0.8) + V((0, 0, top)), 2, 1.0 - i * 0.18, 1.2 - i * 0.2, 0.6 - i * 0.08,
                 'fin', bones[i], lean=45, tip='fin2')
    d.slab([(0, 20.0, 6.4), (0, 22.6, 9.6), (0, 24.6, 6.6), (0, 22.6, 3.6)], 0.45, col='fin', bone='Tail3')   # fin fan
    d.slab([(0, 21.2, 6.4), (0, 22.8, 8.2), (0, 23.6, 6.5), (0, 22.8, 4.8)], 0.6, col='fin2', bone='Tail3')
    return d
