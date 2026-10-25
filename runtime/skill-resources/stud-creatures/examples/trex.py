"""T-Rex (epic tier). The reference for a huge open jaw: two rows of teeth, red gums and palate, a hinged lower
jaw resting open, angry brows over glowing eyes, dark stripes across the back, tiny clawed arms, thick legs
bent back, a long striped and spiked tail. Faces -Y."""
import math


def build(sk):
    V, rgb = sk.V, sk.rgb
    pal = {
        'green': rgb(112, 150, 72), 'green2': rgb(88, 124, 56), 'stripe': rgb(56, 82, 40), 'belly': rgb(228, 216, 178),
        'mouth': rgb(196, 44, 56), 'gum': rgb(140, 26, 40), 'tooth': rgb(248, 244, 230), 'claw': rgb(30, 28, 26),
        'eye': rgb(255, 196, 30), 'scar': rgb(150, 110, 90),
    }
    d = sk.Creature('TRex', pal)
    d.glow.add('eye')

    # ---------------- bones ----------------
    d.bone('Body', (0, 2.0, 13.0), (0, -5.0, 16.0))
    d.bone('Neck', (0, -7.0, 17.6), (0, -9.4, 21.0), 'Body')
    d.bone('Head', (0, -9.6, 21.6), (0, -18.0, 21.6), 'Neck')
    d.bone('Jaw', (0, -10.6, 19.6), (0, -18.0, 17.8), 'Head')
    d.bone('ArmU_L', (2.9, -6.6, 14.6), (3.3, -8.0, 12.8), 'Body', mirror=True)
    d.bone('ArmD_L', (3.3, -8.0, 12.8), (3.3, -9.6, 12.4), 'ArmU_L', mirror=True)
    d.bone('LegU_L', (3.4, 2.0, 12.0), (3.7, -1.0, 7.2), 'Body', mirror=True)
    d.bone('LegD_L', (3.7, -1.0, 7.2), (3.7, 2.8, 2.4), 'LegU_L', mirror=True)
    d.bone('Tail1', (0, 5.0, 13.6), (0, 10.0, 13.0), 'Body')
    d.bone('Tail2', (0, 10.0, 13.0), (0, 15.0, 12.0), 'Tail1')
    d.bone('Tail3', (0, 15.0, 12.0), (0, 20.0, 10.8), 'Tail2')
    d.bone('Tail4', (0, 20.0, 10.8), (0, 26.0, 9.8), 'Tail3')

    # ---------------- torso ----------------
    d.box((6.6, 6.4, 6.4), (0, 2.0, 13.4), col='green', bone='Body')                       # hips
    d.box((7.6, 6.4, 7.4), (0, -2.2, 14.6), col='green', bone='Body')                      # belly
    d.box((6.8, 5.0, 6.6), (0, -5.6, 16.4), rot=(18, 0, 0), col='green', bone='Body')       # chest
    d.box((6.0, 9.0, 1.6), (0, -1.0, 7.4 + 3.6 + 0.2), col='belly', bone='Body')            # belly underside
    d.box((5.0, 1.0, 5.0), (0, -8.0, 15.4), rot=(18, 0, 0), col='belly', bone='Body')       # chest front
    for i, y in enumerate((-5.2, -2.6, 0.0, 2.6, 4.8)):                                     # stripes over the back
        d.box((7.0 - i * 0.2, 1.1, 0.4), (0, y, 18.2 - i * 0.55 + (0.6 if y < -4 else 0)), col='stripe', bone='Body')
        d.box((0.4, 1.1, 3.6), (3.6 if y > -1 else 3.9, y, 15.2 - i * 0.4), col='stripe', bone='Body', mirror=True)
    d.spikes((0, -6.2, 19.0), (0, 4.6, 16.0), 7, 0.6, 1.0, 0.7, 'green2', 'Body', lean=30)
    d.box((0.6, 3.0, 0.4), (3.85, -3.4, 13.6), rot=(0, 0, 0), col='scar', bone='Body')      # battle scar
    d.box((0.6, 2.0, 0.4), (3.85, -2.6, 14.6), rot=(30, 0, 0), col='scar', bone='Body')

    # ---------------- neck & head ----------------
    d.seg((0, -6.8, 16.8), (0, -9.6, 21.4), (5.2, 4.8), col='green', bone='Neck')
    d.box((4.2, 1.2, 4.0), (0, -9.6, 18.0), rot=(-30, 0, 0), col='belly', bone='Neck')
    d.box((5.4, 7.6, 4.4), (0, -13.2, 22.4), col='green', bone='Head')                       # skull
    d.box((4.6, 4.4, 3.2), (0, -18.6, 22.2), col='green', bone='Head', taper=(0.92, 1))      # upper snout
    d.box((5.6, 3.0, 1.0), (0, -12.2, 25.0), col='green2', bone='Head')                       # brow plate
    d.box((4.8, 3.4, 0.8), (0, -17.8, 24.0), col='green2', bone='Head')                       # snout ridge
    for s in (1, -1):
        d.box((1.9, 2.2, 0.9), (1.75 * s, -16.0, 25.6), rot=(0, -24 * s, 0), col='stripe', bone='Head')   # angry brow
        d.box((0.3, 1.6, 0.8), (2.72 * s, -15.9, 24.75), col='eye', bone='Head')                       # eyes (side)
        d.box((1.2, 0.5, 0.65), (1.7 * s, -16.85, 24.85), col='eye', bone='Head')                      # eyes (front)
        d.box((0.4, 4.0, 0.5), (2.72 * s, -11.6, 23.4), col='stripe', bone='Head')                     # head stripe
        d.box((0.55, 0.3, 0.35), (1.1 * s, -20.8, 23.2), col='stripe', bone='Head')                    # nostrils
    d.box((4.4, 9.0, 0.6), (0, -15.4, 20.0), col='mouth', bone='Head')                        # palate
    d.box((5.0, 9.6, 0.8), (0, -15.2, 20.6), col='gum', bone='Head')                          # upper gum
    for i in range(7):                                                                       # upper teeth
        y = -11.4 - i * 1.25
        for s in (1, -1):
            d.box((0.55, 0.55, 1.2), (2.0 * s, y, 19.5), rot=(180, 0, 0), col='tooth', bone='Head', taper=(0.25, 0.3))
    for x in (-1.2, -0.4, 0.4, 1.2):
        d.box((0.5, 0.5, 1.0), (x, -19.9, 19.6), rot=(180, 0, 0), col='tooth', bone='Head', taper=(0.25, 0.3))
    # lower jaw (hinged, rests open)
    jr = (16, 0, 0)
    d.box((4.8, 8.8, 1.6), (0, -14.8, 18.0), rot=jr, col='green', bone='Jaw')
    d.box((4.0, 8.0, 0.4), (0, -14.8, 18.9), rot=jr, col='mouth', bone='Jaw')
    d.box((4.6, 8.4, 0.9), (0, -14.8, 16.95), rot=jr, col='belly', bone='Jaw')
    d.box((2.2, 3.0, 0.5), (0, -14.4, 19.1), rot=jr, col='gum', bone='Jaw')                   # tongue
    jc, Rj = V((0, -14.8, 18.0)), sk._rot(jr)
    for i in range(6):
        dy = 2.8 - i * 1.25
        for s in (1, -1):
            d.box((0.5, 0.5, 1.0), jc + Rj @ V((1.85 * s, dy, 1.25)), rot=jr, col='tooth', bone='Jaw', taper=(0.25, 0.3))
    for s in (1, -1):
        d.box((0.8, 2.6, 1.6), (2.7 * s, -11.6, 21.2), col='green2', bone='Head')                # jaw muscle

    # ---------------- arms (tiny, clawed) ----------------
    d.seg((2.9, -6.6, 14.8), (3.3, -8.0, 12.8), 1.1, col='green', bone='ArmU_L', mirror=True)
    d.seg((3.3, -8.0, 12.8), (3.3, -9.4, 12.6), 0.9, col='green', bone='ArmD_L', mirror=True)
    for dx in (-0.25, 0.25):
        d.seg((3.3 + dx, -9.4, 12.6), (3.3 + dx, -10.2, 12.0), 0.3, col='claw', bone='ArmD_L', taper=(0.3, 0.3), mirror=True)

    # ---------------- legs ----------------
    d.seg((3.4, 2.6, 13.0), (3.7, -1.0, 7.0), (3.6, 4.6), col='green', bone='LegU_L', mirror=True)   # thigh
    d.box((1.0, 3.6, 3.6), (4.95, 0.8, 10.6), rot=(-34, 0, 0), col='stripe', bone='LegU_L', mirror=True)
    d.seg((3.7, -1.0, 7.4), (3.7, 2.8, 2.2), (2.4, 2.6), col='green', bone='LegD_L', mirror=True)    # shin (bent back)
    d.seg((3.7, 2.8, 2.6), (3.7, 1.2, 0.8), (2.2, 2.2), col='green2', bone='LegD_L', mirror=True)   # ankle
    d.foot((3.7, 0.0, 0.6), (3.2, 3.6, 1.2), 3, 'green', 'claw', 'LegD_L', forward=-1, mirror=True)
    d.box((0.7, 1.2, 0.7), (3.7, 3.0, 0.5), rot=(-90, 0, 0), col='claw', bone='LegD_L', taper=(0.3, 0.3), mirror=True)

    # ---------------- tail ----------------
    tp = [V((0, 4.6, 13.6)), V((0, 10.0, 13.0)), V((0, 15.0, 12.0)), V((0, 20.0, 10.8)), V((0, 26.4, 9.6))]
    th = [(5.6, 5.2), (4.4, 4.0), (3.2, 2.9), (2.0, 1.8)]
    tb = ['Tail1', 'Tail2', 'Tail3', 'Tail4']
    for i in range(4):
        a, b = tp[i], tp[i + 1]
        d.seg(a, b + (b - a).normalized() * 0.4, th[i], col='green', bone=tb[i])
        d.seg(a.lerp(b, 0.1) - V((0, 0, th[i][1] / 2 - 0.15)), a.lerp(b, 0.9) - V((0, 0, th[i][1] / 2 - 0.15)),
              (th[i][0] * 0.7, 0.5), col='belly', bone=tb[i])
        m = a.lerp(b, 0.5)
        d.box((th[i][0] + 0.2, 1.0, th[i][1] * 0.6), m + V((0, 0, th[i][1] * 0.25)), col='stripe', bone=tb[i])
    for i in range(4):
        a, b = tp[i], tp[i + 1]
        top = th[i][1] / 2 - 0.1
        d.spikes(a.lerp(b, 0.2) + V((0, 0, top)), a.lerp(b, 0.8) + V((0, 0, top)), 2, 0.9 - i * 0.15, 1.0 - i * 0.15,
                 0.6 - i * 0.08, 'green2', tb[i], lean=40)
    return d
