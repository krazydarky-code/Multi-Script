"""Red Dragon (epic tier, about 70 block calls). The reference for wings, horns, an open fiery mouth and
armoured plates: a wide armoured chest, two-segment neck with belly plates, a horned head with angry brows
and glowing eyes, a long spiked tail ending in a spade, and big bat wings. Faces -Y."""


def build(sk, name='Dragon', over=None, glow=('eye', 'ember'), arms=True):
    V, rgb = sk.V, sk.rgb
    pal = {
        'red': rgb(200, 38, 38), 'red2': rgb(150, 22, 28), 'red3': rgb(226, 66, 54),
        'membrane': rgb(118, 18, 30), 'membrane2': rgb(96, 14, 26),
        'tan': rgb(228, 196, 126), 'tan2': rgb(196, 160, 98),
        'horn': rgb(46, 40, 50), 'claw': rgb(22, 20, 24), 'tooth': rgb(246, 240, 226),
        'eye': rgb(255, 204, 32), 'mouth': rgb(96, 12, 22), 'ember': rgb(255, 120, 30),
    }
    pal.update(over or {})
    d = sk.Creature(name, pal)
    d.glow.update(set(glow))

    # ---------------- bones ----------------
    d.bone('Body', (0, 5, 9.6), (0, -2.5, 9.6))
    d.bone('Neck1', (0, -4.2, 11.4), (0, -6.0, 14.0), 'Body')
    d.bone('Neck2', (0, -6.0, 14.0), (0, -7.3, 18.0), 'Neck1')
    d.bone('Head', (0, -7.4, 18.6), (0, -12.0, 18.6), 'Neck2')
    d.bone('Jaw', (0, -9.0, 17.2), (0, -12.6, 16.2), 'Head')
    d.bone('Tail1', (0, 7.0, 9.6), (0, 11.0, 8.8), 'Body')
    d.bone('Tail2', (0, 11.0, 8.8), (0, 15.0, 7.6), 'Tail1')
    d.bone('Tail3', (0, 15.0, 7.6), (0, 23.0, 7.4), 'Tail2')
    d.bone('ArmU_L', (3.2, -3.0, 9.0), (3.3, -3.6, 4.9), 'Body', mirror=True)
    d.bone('ArmD_L', (3.3, -3.6, 4.9), (3.3, -4.0, 1.0), 'ArmU_L', mirror=True)
    d.bone('LegU_L', (3.0, 5.2, 9.4), (3.1, 3.6, 5.1), 'Body', mirror=True)
    d.bone('LegD_L', (3.1, 3.6, 5.1), (3.1, 4.4, 1.0), 'LegU_L', mirror=True)
    d.bone('Wing1_L', (2.8, -1.6, 12.6), (6.2, -0.2, 17.4), 'Body', mirror=True)
    d.bone('Wing2_L', (6.2, -0.2, 17.4), (10.2, 1.6, 21.0), 'Wing1_L', mirror=True)

    # ---------------- torso ----------------
    d.box((6.6, 5.2, 6.6), (0, -2.6, 9.8), col='red', bone='Body')                 # chest
    d.box((5.6, 4.6, 1.4), (0, -2.4, 13.6), col='red', bone='Body')                # shoulder hump
    d.box((6.0, 5.4, 5.8), (0, 1.6, 9.4), col='red', bone='Body')                  # belly
    d.box((5.6, 4.2, 5.8), (0, 5.3, 9.6), col='red', bone='Body')                  # hips
    d.box((4.8, 3.6, 1.2), (0, 5.2, 13.0), col='red', bone='Body')                 # hip top
    d.box((4.4, 6.0, 0.8), (0, 1.6, 12.6), col='red3', bone='Body')                # back plate
    for i, y in enumerate((-4.2, -2.4, -0.6, 1.2, 3.0, 4.8, 6.4)):                # side scales
        z = 10.8 if i % 2 == 0 else 9.0
        d.box((0.5, 1.7, 1.5), (3.05 if y < 0 else 2.85, y, z), col='red2', bone='Body', mirror=True)
        d.box((0.45, 1.5, 1.3), (3.0 if y < 0 else 2.8, y + 0.9, z - 1.8), col='red3', bone='Body', mirror=True)
    d.box((2.0, 4.6, 4.8), (3.25, -2.8, 9.8), col='red2', bone='Body', mirror=True)     # shoulder armour
    d.box((2.2, 3.8, 0.8), (3.35, -2.8, 12.3), rot=(0, -18, 0), col='red3', bone='Body', mirror=True)
    d.box((2.0, 4.8, 5.4), (3.0, 4.9, 9.3), col='red2', bone='Body', mirror=True)      # haunch armour
    d.box((2.2, 4.0, 0.8), (3.1, 4.9, 12.1), rot=(0, -18, 0), col='red3', bone='Body', mirror=True)
    for i, z in enumerate((12.0, 10.6, 9.2, 7.8)):                                    # chest plates
        d.box((3.8 - i * 0.3, 0.8, 1.25), (0, -5.25, z), col='tan', bone='Body')
        d.box((4.0 - i * 0.3, 0.6, 0.25), (0, -5.15, z - 0.7), col='tan2', bone='Body')
    for y in (-3.6, -1.6, 0.4, 2.4, 4.4, 6.2):                                         # belly plates
        d.box((4.2, 1.7, 0.7), (0, y, 6.4), col='tan', bone='Body')
    d.spikes((0, -4.0, 14.2), (0, 6.6, 13.4), 7, 1.2, 2.3, 0.85, 'red2', 'Body', lean=35, tip='claw')

    # ---------------- neck ----------------
    d.seg((0, -4.0, 11.0), (0, -6.0, 14.2), (3.8, 3.4), col='red', bone='Neck1')
    d.seg((0, -5.9, 13.8), (0, -7.0, 16.8), (3.2, 2.9), col='red', bone='Neck2')
    d.seg((0, -6.9, 16.4), (0, -7.4, 18.6), (2.9, 2.7), col='red', bone='Neck2')
    plates = ((-6.1, 11.8, 'Neck1'), (-7.0, 13.4, 'Neck1'), (-7.7, 15.0, 'Neck2'), (-8.2, 16.6, 'Neck2'), (-8.5, 18.0, 'Neck2'))
    for i, (y, z, b) in enumerate(plates):
        d.box((2.7 - i * 0.2, 0.7, 1.5), (0, y, z), rot=(-30, 0, 0), col='tan', bone=b)
    d.spikes((0, -4.6, 13.2), (0, -5.8, 15.0), 2, 1.1, 1.2, 0.7, 'red2', 'Neck1', lean=45, tip='claw')
    d.spikes((0, -6.4, 16.2), (0, -6.9, 18.0), 2, 1.0, 1.1, 0.6, 'red2', 'Neck2', lean=50, tip='claw')

    # ---------------- head ----------------
    d.box((3.2, 3.6, 2.8), (0, -8.6, 18.8), col='red', bone='Head')                # skull
    d.box((2.5, 3.4, 1.6), (0, -11.7, 18.4), col='red', bone='Head', taper=(0.88, 1))  # snout
    d.box((2.6, 1.6, 0.9), (0, -12.6, 19.1), col='red3', bone='Head')             # nose ridge
    d.box((1.25, 1.5, 0.5), (0.95, -10.1, 20.0), rot=(0, -28, 0), col='red2', bone='Head', mirror=True)  # angry brows
    d.box((0.8, 0.22, 0.5), (1.08, -10.62, 19.45), col='eye', bone='Head', mirror=True)
    d.box((0.25, 1.0, 0.5), (1.62, -10.0, 19.45), col='eye', bone='Head', mirror=True)
    d.box((0.5, 0.25, 0.35), (0.6, -13.42, 18.6), col='mouth', bone='Head', mirror=True)    # nostrils
    d.horn((0, -12.9, 19.4), (0, -0.5, 1), 1.0, 0.45, 2, -20, 'horn', 'Head', tip='claw')    # nose horn
    d.box((1.7, 3.0, 0.6), (0, -11.4, 17.35), col='mouth', bone='Head')           # palate
    d.box((1.0, 0.8, 0.6), (0, -10.0, 17.5), col='ember', bone='Head')            # fire in the throat
    for y in (-13.0, -12.2, -11.4, -10.6):
        d.box((0.32, 0.32, 0.6), (0.95, y, 17.3), rot=(180, 0, 0), col='tooth', bone='Head', taper=(0.3, 0.3), mirror=True)
    # jaw (open)
    d.box((2.2, 3.9, 0.9), (0, -11.0, 16.55), rot=(16, 0, 0), col='red', bone='Jaw')
    d.box((1.6, 3.4, 0.3), (0, -11.0, 17.05), rot=(16, 0, 0), col='mouth', bone='Jaw')
    for y in (-12.5, -11.7, -10.9):
        d.box((0.32, 0.32, 0.55), (0.8, y, 17.3 + (y + 11.0) * 0.28), rot=(16, 0, 0), col='tooth', bone='Jaw', taper=(0.3, 0.3), mirror=True)
    d.box((0.4, 1.0, 0.6), (1.15, -9.8, 16.6), rot=(0, 0, -30), col='red2', bone='Jaw', mirror=True)   # jaw spikes
    # horns, cheek spikes, crest
    d.horn((1.2, -8.0, 19.9), (0.35, 1.0, 0.55), 5.0, 0.85, 5, -14, 'horn', 'Head', tip='claw', mirror=True)
    d.horn((1.5, -8.4, 18.8), (0.9, 0.9, 0.1), 2.6, 0.5, 3, -10, 'horn', 'Head', tip='claw', mirror=True)
    d.horn((1.6, -10.2, 17.9), (1.0, 0.7, -0.4), 1.4, 0.38, 2, 12, 'red2', 'Head', mirror=True)
    d.slab([(0, -9.0, 20.1), (0, -7.4, 21.7), (0, -6.4, 21.0), (0, -6.8, 19.8)], 0.55, col='red3', bone='Head')
    d.spikes((0, -8.4, 20.6), (0, -6.9, 21.6), 3, 0.7, 1.0, 0.35, 'horn', 'Head', lean=30, tip='claw')

    # ---------------- legs ----------------
    if arms:
        d.seg((3.2, -3.0, 9.4), (3.3, -3.6, 4.8), (2.9, 3.1), col='red', bone='ArmU_L', mirror=True)
        d.box((3.0, 1.4, 1.9), (3.3, -5.0, 5.1), col='red2', bone='ArmU_L', mirror=True)          # elbow plate
        d.seg((3.3, -3.6, 5.1), (3.3, -4.0, 1.2), (2.5, 2.7), col='red', bone='ArmD_L', mirror=True)
        d.box((2.7, 2.9, 0.6), (3.3, -4.0, 1.9), col='red2', bone='ArmD_L', mirror=True)          # wrist band
        d.foot((3.3, -4.5, 0.55), (3.1, 3.0, 1.1), 3, 'red', 'claw', 'ArmD_L', forward=-1, mirror=True)
    d.seg((3.0, 5.4, 9.8), (3.1, 3.6, 5.0), (3.3, 3.7), col='red', bone='LegU_L', mirror=True)  # thigh
    d.box((3.0, 1.3, 1.9), (3.1, 2.4, 5.3), col='red2', bone='LegU_L', mirror=True)           # knee plate
    d.seg((3.1, 3.6, 5.3), (3.1, 4.6, 1.2), (2.5, 2.7), col='red', bone='LegD_L', mirror=True)  # shin
    d.foot((3.1, 3.5, 0.55), (3.1, 3.4, 1.1), 3, 'red', 'claw', 'LegD_L', forward=-1, mirror=True)
    d.box((0.6, 1.0, 0.6), (3.1, 5.6, 0.5), rot=(-90, 0, 0), col='claw', bone='LegD_L', taper=(0.3, 0.2), mirror=True)  # heel spur

    # ---------------- tail ----------------
    tail = [V((0, 7.0, 9.6)), V((0, 11.0, 8.8)), V((0, 15.0, 7.6)), V((0, 19.0, 6.9)), V((0, 23.0, 7.5))]
    thick = [(3.4, 3.2), (2.6, 2.4), (1.9, 1.8), (1.3, 1.2)]
    bones = ['Tail1', 'Tail2', 'Tail3', 'Tail3']
    for i in range(4):
        d.seg(tail[i], tail[i + 1] + (tail[i + 1] - tail[i]).normalized() * 0.3, thick[i], col='red', bone=bones[i])
    d.spikes((0, 7.8, 11.2), (0, 10.6, 10.4), 3, 1.0, 1.3, 0.65, 'red2', 'Tail1', lean=45, tip='claw')
    d.spikes((0, 11.8, 9.9), (0, 14.4, 8.8), 3, 0.8, 1.0, 0.55, 'red2', 'Tail2', lean=45, tip='claw')
    d.spikes((0, 15.8, 8.4), (0, 22.0, 8.0), 4, 0.55, 0.7, 0.45, 'red2', 'Tail3', lean=45, tip='claw')
    d.slab([(0, 22.6, 7.5), (1.8, 23.8, 7.5), (0, 26.4, 7.6), (-1.8, 23.8, 7.5)], 0.5, col='red2', bone='Tail3')  # spade
    for i in range(4):                                                               # tail belly plates
        a, b = tail[i], tail[i + 1]
        m = (a + b) / 2
        d.seg(a.lerp(b, 0.15) - V((0, 0, thick[i][1] / 2 - 0.1)), a.lerp(b, 0.85) - V((0, 0, thick[i][1] / 2 - 0.1)),
              (thick[i][0] * 0.6, 0.45), col='tan', bone=bones[i])

    # ---------------- wings ----------------
    S, E, W = V((2.8, -1.6, 12.6)), V((6.2, -0.2, 17.4)), V((10.2, 1.6, 21.0))
    tips = [V((13.8, 2.6, 23.0)), V((16.0, 4.0, 18.4)), V((15.0, 5.2, 13.6)), V((11.2, 5.8, 10.4))]
    root = [V((3.2, 2.6, 11.6)), V((3.2, 6.0, 11.2))]
    d.seg(S, E, 1.15, col='red', bone='Wing1_L', mirror=True)
    d.seg(E, W, 0.95, col='red', bone='Wing2_L', mirror=True)
    d.box((1.6, 1.6, 1.6), E, col='red2', bone='Wing1_L', mirror=True)
    d.seg(E, E + V((0.4, 1.6, -0.6)), 0.5, col='claw', bone='Wing1_L', taper=(0.3, 0.3), mirror=True)   # elbow spike
    d.box((1.3, 1.3, 1.3), W, col='red2', bone='Wing2_L', mirror=True)
    d.seg(W, W + V((0.4, -0.4, 1.8)), 0.5, col='claw', bone='Wing2_L', taper=(0.25, 0.25), mirror=True)  # thumb claw
    for i, t in enumerate(tips):
        d.seg(W, t, 0.62 - i * 0.06, col='red', bone='Wing2_L', taper=(0.7, 0.7), mirror=True)
        dirv = (t - W).normalized()
        d.seg(t - dirv * 0.2, t + dirv * 1.1, 0.42, col='claw', bone='Wing2_L', taper=(0.2, 0.2), mirror=True)
    for i in range(len(tips) - 1):
        d.slab([W, tips[i], tips[i + 1]], 0.24, col='membrane' if i % 2 == 0 else 'membrane2', bone='Wing2_L', mirror=True)
    d.slab([W, tips[3], root[1], root[0]], 0.24, col='membrane2', bone='Wing2_L', mirror=True)
    d.slab([S, E, W, root[0]], 0.24, col='membrane', bone='Wing1_L', mirror=True)
    return d
