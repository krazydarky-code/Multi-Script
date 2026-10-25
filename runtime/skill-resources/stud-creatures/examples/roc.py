"""Roc (epic tier). The Thunderbird, a colossal storm eagle:
a deep puffed breast, cream with dark chevron feathers, layered coverts over the back and flanks, a white neck ruff,
a big white head with a heavy dark brow over glowing electric eyes, a huge hooked gold beak hanging open, a crown
of zigzag lightning feathers; wide wings of layered coverts, separate secondaries and spread finger primaries with
cream tips and glowing lightning streaks; a fanned tail, shaggy feathered trousers over banded gold legs and
black hooked talons."""
import math
from mathutils import Vector as V


def build(sk):
    rgb = sk.rgb
    pal = {'brown': rgb(96, 66, 44), 'brown2': rgb(130, 94, 60), 'brown3': rgb(66, 44, 30), 'gold': rgb(240, 188, 72),
           'gold2': rgb(200, 148, 48), 'white': rgb(248, 246, 238), 'white2': rgb(214, 212, 204), 'cream': rgb(222, 200, 156),
           'bolt': rgb(120, 224, 255), 'beak': rgb(252, 204, 64), 'beak2': rgb(214, 150, 36), 'eye': rgb(30, 196, 255),
           'talon': rgb(36, 30, 28), 'mouth': rgb(140, 50, 60)}
    d = sk.Creature('Roc', pal)
    d.glow.update({'eye', 'bolt'})
    d.smooth.update({'beak', 'beak2', 'talon'})

    # ---------------- bones ----------------
    d.bone('Body', (0, 4.0, 10.8), (0, -5.0, 12.6))
    d.bone('Neck', (0, -5.0, 13.8), (0, -6.8, 17.4), 'Body')
    d.bone('Head', (0, -6.4, 18.8), (0, -13.0, 18.8), 'Neck')
    d.bone('Jaw', (0, -9.4, 17.6), (0, -12.4, 17.0), 'Head')
    d.bone('LegU_L', (2.1, 0.6, 8.4), (2.3, 1.2, 4.4), 'Body', mirror=True)
    d.bone('LegD_L', (2.3, 1.2, 4.4), (2.3, 0.0, 0.7), 'LegU_L', mirror=True)
    d.bone('Wing1_L', (3.6, -3.2, 13.4), (11.6, -2.6, 16.4), 'Body', mirror=True)
    d.bone('Wing2_L', (11.6, -2.6, 16.4), (21.0, -1.0, 18.2), 'Wing1_L', mirror=True)
    d.bone('Tail1', (0, 5.0, 11.8), (0, 13.0, 12.6), 'Body')

    # ---------------- deep puffed breast ----------------
    B = 'Body'
    d.box((6.6, 9.4, 6.2), (0, -0.4, 11.4), col='brown', bone=B)
    d.box((5.8, 1.2, 5.6), (0, -5.6, 11.4), col='cream', bone=B)                     # cream breast
    d.box((4.6, 0.8, 4.0), (0, -6.5, 11.0), col='cream', bone=B)                     # puffed out
    d.box((5.4, 6.4, 0.5), (0, -1.6, 8.05), col='cream', bone=B)                     # cream belly
    for z, xs in ((12.4, (-1.4, 0.2, 1.8)), (11.2, (-2.0, -0.6, 1.0)), (10.0, (-1.4, 0.2, 1.8)), (8.8, (-1.0, 0.6))):   # barred breast
        for x in xs:
            y = -6.95 if abs(x) < 2.3 and z > 9.0 else -6.25
            d.box((0.9, 0.3, 0.35), (x, y, z), col='brown2', bone=B)
    zig = [V((0.6, -7.0, 13.4)), V((-0.5, -7.0, 11.6)), V((0.5, -7.0, 10.8)), V((-0.4, -7.0, 8.8))]
    for q in range(3):                                                                 # glowing lightning bolt down the breast
        d.seg(zig[q], zig[q + 1], (0.55, 0.3), col='bolt', bone=B)
    for i, y in enumerate((-3.8, -1.6, 0.6, 2.8)):                                    # layered coverts over the back
        d.box((6.0 - i * 0.4, 2.6, 0.6), (0, y, 14.75 - i * 0.12), rot=(8, 0, 0), col='brown2', bone=B)
    for k in (1, -1):
        for y in (-3.0, -0.8, 1.4, 3.4):                                              # flank feathers, tips hanging down
            d.box((0.4, 2.0, 3.0), (3.4 * k, y, 10.9), rot=(-8, 0, 0), col='brown2', bone=B, taper=(1, 0.4))
        d.box((2.6, 3.2, 1.8), (3.0 * k, -3.0, 14.0), col='brown3', bone=B)            # feather epaulettes at the wing roots

    # ---------------- neck and ruff ----------------
    N = 'Neck'
    d.seg((0, -4.6, 13.2), (0, -6.8, 18.2), 3.4, col='white', bone=N)
    d.box((4.6, 2.8, 1.2), (0, -4.8, 13.9), rot=(-22, 0, 0), col='white2', bone=N)  # layered white ruff
    d.box((4.2, 2.6, 1.2), (0, -5.5, 15.4), rot=(-22, 0, 0), col='white', bone=N)
    d.spikes((0, -4.4, 15.4), (0, -5.4, 17.8), 3, 0.9, 1.2, 0.8, 'white2', N, lean=60)   # spiky feathers on the nape

    # ---------------- head: dark brow, electric eyes, huge hooked beak, lightning crown ----------------
    H = 'Head'
    O = V((0, -8.0, 18.9))

    def P(x, y, z):
        return O + V((x, y, z))

    d.box((3.8, 4.0, 3.2), P(0, 0, 0), col='white', bone=H)                          # skull
    d.box((3.4, 1.8, 2.6), P(0, 2.4, 0.1), col='white', bone=H)                      # back of the head
    d.spikes(P(0, 2.4, 1.3), P(0, 3.2, 0.4), 3, 0.9, 1.1, 0.7, 'white2', H, lean=70)    # swept nape feathers
    d.box((4.0, 2.4, 0.6), P(0, -0.6, 1.6), col='white2', bone=H)                    # brow plate
    for k in (1, -1):
        d.box((1.7, 2.4, 0.7), P(1.15 * k, -1.4, 1.5), rot=(0, -26 * k, 0), col='brown3', bone=H)    # heavy angry brows
        d.box((1.0, 0.2, 0.6), P(1.3 * k, -2.06, 0.98), col='eye', bone=H)            # glowing electric eyes, front face
        d.box((0.2, 1.5, 0.6), P(1.96 * k, -1.2, 0.98), col='eye', bone=H)            # ... and side face
        d.box((0.3, 1.6, 0.9), P(1.95 * k, 0.6, -0.6), col='white2', bone=H)          # cheek feathers
    d.box((2.2, 0.6, 1.2), P(0, -2.2, -0.15), col='beak', bone=H)                     # cere
    d.box((2.4, 2.6, 1.8), P(0, -3.6, -0.2), col='beak', bone=H, taper=(0.8, 1))       # upper beak
    d.box((1.4, 2.8, 0.6), P(0, -3.6, 0.9), col='beak', bone=H)                       # beak ridge
    d.seg(P(0, -4.6, 0.8), P(0, -5.8, -1.6), (1.6, 1.3), col='beak2', bone=H, taper=(0.4, 0.5))   # the hook
    d.box((1.8, 2.4, 0.3), P(0, -3.4, -1.2), col='mouth', bone=H)                     # palate
    for k in (1, -1):
        d.box((0.3, 0.3, 0.3), P(0.7 * k, -3.2, 0.95), col='beak2', bone=H)           # nostril slits on top
    jr = (14, 0, 0)
    Rj = sk._rot(jr)
    jp = P(0, -1.6, -1.1)
    d.box((1.9, 3.2, 0.7), jp + Rj @ V((0, -1.8, -0.35)), rot=jr, col='beak2', bone='Jaw')    # lower beak
    d.box((1.4, 2.6, 0.2), jp + Rj @ V((0, -1.6, 0.05)), rot=jr, col='mouth', bone='Jaw')
    # crown of zigzag lightning feathers, swept back
    for x, h, lean in ((0, 3.2, 0.0), (0.9, 2.6, 0.4), (-0.9, 2.6, -0.4), (1.6, 2.0, 0.8), (-1.6, 2.0, -0.8)):
        b0 = P(x, 0.4, 1.7)
        zig = [b0, b0 + V((lean * 0.4, 1.3, h * 0.45)), b0 + V((lean * 0.6, 0.4, h * 0.62)), b0 + V((lean, 2.2, h))]
        for q in range(3):
            d.seg(zig[q], zig[q + 1], 0.42 - q * 0.08, col='bolt', bone=H)

    # ---------------- wings ----------------
    W1, W2 = 'Wing1_L', 'Wing2_L'
    n1 = V((-0.334, 0.279, 0.900))                                                   # top of the arm panel
    d.slab([(3.0, -3.8, 13.6), (11.6, -3.2, 16.6), (12.0, 1.0, 15.2), (3.0, 2.0, 11.8)], 1.0, col='brown', bone=W1, mirror=True)
    d.seg((3.2, -3.9, 13.9), (11.8, -3.3, 16.8), (1.1, 1.1), col='brown3', bone=W1, mirror=True)           # leading edge bar
    for f, c in ((0.3, 'brown2'), (0.62, 'brown')):                                                         # covert rows
        a = V((3.2, -3.8, 13.6)).lerp(V((3.2, 2.0, 11.8)), f) + n1 * 0.55
        b = V((11.6, -3.2, 16.6)).lerp(V((12.0, 1.0, 15.2)), f) + n1 * 0.55
        d.seg(a, b, (1.3, 0.5), col=c, bone=W1, mirror=True)
    for j in range(5):                                                                                       # secondaries
        base = V((3.6, 1.8, 11.9)).lerp(V((11.6, 0.9, 15.0)), j / 4)
        tip = base + V((0.2, 2.8, -0.7))
        d.seg(base, tip, (1.5, 0.4), col='brown2' if j % 2 else 'brown', bone=W1, mirror=True)
        d.seg(tip - V((0.05, 0.7, -0.18)), tip + V((0.05, 0.2, -0.05)), (1.5, 0.42), col='cream', bone=W1, mirror=True)
    d.slab([(11.4, -3.2, 16.7), (19.4, -1.6, 18.4), (19.2, 1.6, 17.2), (11.8, 1.0, 15.0)], 0.9, col='brown2', bone=W2, mirror=True)
    d.seg((11.6, -3.3, 16.9), (19.6, -1.7, 18.6), (1.0, 0.9), col='brown3', bone=W2, mirror=True)
    for j in range(3):                                                                                       # hand secondaries
        base = V((12.4, 1.0, 15.2)).lerp(V((18.0, 1.4, 17.0)), j / 2)
        tip = base + V((0.4, 2.6, -0.6))
        d.seg(base, tip, (1.5, 0.4), col='brown' if j % 2 else 'brown2', bone=W2, mirror=True)
        d.seg(tip - V((0.1, 0.7, -0.16)), tip + V((0.1, 0.2, -0.05)), (1.5, 0.42), col='cream', bone=W2, mirror=True)
    for j in range(5):                                                                                       # spread finger primaries
        base = V((18.8, -1.4, 18.2)).lerp(V((18.6, 1.4, 17.2)), j / 4)
        dirv = V((1.0, -0.25 + 0.32 * j, 0.06 - 0.03 * j)).normalized()
        L = 5.0 - 0.35 * abs(j - 1.5)
        tip = base + dirv * L
        d.seg(base, tip, (0.95, 0.38), col='brown' if j % 2 else 'brown3', bone=W2, mirror=True)
        d.seg(tip - dirv * 1.0, tip + dirv * 0.15, (1.0, 0.42), col='cream', bone=W2, mirror=True)
    for a, b in (((4.2, -1.4, 14.3), (6.8, -0.4, 15.0)), ((6.8, -0.4, 15.0), (8.6, -1.8, 15.7)), ((8.6, -1.8, 15.7), (11.0, -0.8, 16.3))):
        d.seg(V(a) + n1 * 0.62, V(b) + n1 * 0.62, (0.7, 1.4), col='bolt', bone=W1, mirror=True)               # lightning streak
    for a, b in (((12.4, -0.6, 17.0), (14.8, 0.6, 17.4)), ((14.8, 0.6, 17.4), (16.6, -0.8, 18.0)), ((16.6, -0.8, 18.0), (18.6, 0.2, 18.2))):
        d.seg(a, b, (0.7, 1.2), col='bolt', bone=W2, mirror=True)

    # ---------------- fanned tail ----------------
    T = 'Tail1'
    d.box((4.0, 3.2, 1.0), (0, 5.6, 12.6), col='brown', bone=T)                      # tail coverts
    for j in range(7):
        a = math.radians(-36 + 12 * j)
        base = V((0.3 * math.sin(a) * 4, 5.4, 12.0))
        dirv = V((math.sin(a), math.cos(a), 0.12)).normalized()
        tip = base + dirv * (7.6 - abs(j - 3) * 0.5)
        d.seg(base, tip, (1.3, 0.45), col='brown2' if j % 2 else 'brown', bone=T, roll=0)
        d.seg(tip - dirv * 1.4, tip - dirv * 0.6, (1.36, 0.5), col='cream', bone=T)      # cream band
        d.seg(tip - dirv * 0.5, tip + dirv * 0.1, (1.0, 0.5), col='bolt' if j in (2, 4) else 'brown3', bone=T)

    # ---------------- feathered trousers, banded gold legs, black talons ----------------
    for k, side in ((1, 'L'), (-1, 'R')):
        U, D = 'LegU_' + side, 'LegD_' + side
        x = 2.2 * k
        d.box((2.8, 3.0, 3.4), (x, 0.9, 7.0), col='brown3', bone=U)
        for dx, dy in ((-0.8, -1.1), (0.0, -1.2), (0.8, -1.1), (-0.8, 1.0), (0.8, 1.0)):   # shaggy fringe
            d.box((0.8, 0.8, 1.4), (x + dx, 0.9 + dy, 4.9), col='brown3', bone=U, rot=(180, 0, 0), taper=(0.4, 0.4))
        d.seg((x, 0.7, 8.4), (2.3 * k, 1.2, 4.4), 1.6, col='gold', bone=U)
        d.seg((2.3 * k, 1.2, 4.8), (2.3 * k, 0.0, 0.5), 1.15, col='gold', bone=D)
        for z in (1.6, 2.6, 3.6):
            d.seg((2.3 * k, 0.0 + (z - 0.5) / 4.3 * 1.2, z - 0.15), (2.3 * k, 0.0 + (z - 0.5) / 4.3 * 1.2, z + 0.15), 1.3, col='gold2', bone=D)
        for ang, L in ((-28, 2.0), (0, 2.3), (28, 2.0), (180, 1.3)):
            r = math.radians(ang)
            dirv = V((math.sin(r) * k, -math.cos(r), 0))
            a0 = V((2.3 * k, 0.0, 0.32))
            tip = a0 + dirv * L
            d.seg(a0, tip, (0.6, 0.55), col='gold', bone=D)
            d.seg(tip - dirv * 0.15 + V((0, 0, 0.1)), tip + dirv * 0.5 + V((0, 0, 0.12)), 0.42, col='talon', bone=D)
            d.seg(tip + dirv * 0.45 + V((0, 0, 0.12)), tip + dirv * 0.75 + V((0, 0, -0.35)), 0.34, col='talon', bone=D, taper=(0.3, 0.3))
    return d
