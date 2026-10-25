"""Arctodus (normal tier). The short-faced bear as a real giant BEAR, not a
box on stilts: a massive deep body with a high shoulder hump, heavy shoulders and hips, a darker saddle, shaggy fur
hanging from the chest and belly, claw scars on the flank; thick legs of bear length with fur tufts at the elbows
and big paws with long pale claws; a broad head with a fur ruff, round ears, a heavy brow with angry brows over
glowing orange eyes, a short blunt muzzle with a big nose, roaring jaws with fangs; a stub tail."""
from mathutils import Vector as V


def build(sk):
    rgb = sk.rgb
    pal = {'fur': rgb(112, 74, 48), 'fur2': rgb(84, 54, 34), 'fur3': rgb(136, 94, 62), 'light': rgb(170, 130, 92),
           'nose': rgb(30, 24, 22), 'eye': rgb(255, 156, 46), 'tooth': rgb(248, 244, 232), 'claw': rgb(236, 228, 210),
           'scar': rgb(196, 126, 114), 'mouth': rgb(130, 40, 40)}
    d = sk.Creature('Arctodus', pal)
    d.glow.add('eye')
    d.smooth.update({'tooth', 'claw'})

    d.bone('Body', (0, 3.2, 7.6), (0, -3.4, 8.6))
    d.bone('ArmU_L', (2.6, -3.0, 8.4), (2.6, -2.8, 4.6), 'Body', mirror=True)
    d.bone('ArmD_L', (2.6, -2.8, 4.6), (2.5, -3.4, 0.8), 'ArmU_L', mirror=True)
    d.bone('LegU_L', (2.6, 2.8, 8.2), (2.6, 1.6, 4.8), 'Body', mirror=True)
    d.bone('LegD_L', (2.6, 1.6, 4.8), (2.5, 3.0, 0.8), 'LegU_L', mirror=True)
    d.bone('Neck', (0, -4.4, 9.8), (0, -5.8, 10.8), 'Body')
    d.bone('Head', (0, -5.8, 11.4), (0, -10.6, 11.0), 'Neck')
    d.bone('Jaw', (0, -7.4, 10.2), (0, -10.0, 9.2), 'Head')
    d.bone('Tail1', (0, 4.6, 8.4), (0, 5.4, 8.0), 'Body')

    # ---------------- massive body ----------------
    B = 'Body'
    d.box((5.8, 4.4, 5.2), (0, -2.0, 8.2), col='fur', bone=B)                       # deep chest
    d.box((4.8, 3.2, 1.8), (0, -2.4, 11.6), col='fur2', bone=B)                     # shoulder hump
    d.box((3.2, 2.0, 0.8), (0, -2.4, 12.8), col='fur2', bone=B)
    d.box((5.2, 3.8, 4.6), (0, 1.6, 8.1), col='fur', bone=B)                        # belly
    d.box((5.0, 2.2, 4.6), (0, 4.0, 8.4), col='fur', bone=B)                        # rump
    d.box((4.0, 4.4, 0.4), (0, 2.0, 10.55), col='fur2', bone=B)                     # darker saddle
    d.box((4.0, 6.4, 0.3), (0, 0.0, 5.55), col='light', bone=B)                     # pale belly
    for k in (1, -1):
        d.box((1.2, 3.0, 3.6), (2.95 * k, -2.6, 8.6), col='fur3', bone=B)            # heavy shoulders
        d.box((1.2, 2.6, 3.4), (2.85 * k, 3.0, 8.4), col='fur3', bone=B)             # hips
        for y in (-0.6, 0.6, 1.8):                                                  # shaggy fur hanging from the belly
            d.box((0.6, 0.9, 1.2), (2.4 * k, y, 5.6), rot=(180, 0, 0), col='fur2', bone=B, taper=(0.5, 0.5))
    for x in (-1.6, -0.5, 0.6, 1.7):                                                 # ... and from the chest
        d.box((0.9, 0.6, 1.4), (x, -4.25, 6.0), rot=(180, 0, 0), col='fur2', bone=B, taper=(0.5, 0.5))
    d.spikes((0, -3.6, 13.2), (0, -1.2, 13.2), 3, 0.7, 0.9, 0.8, 'fur2', B, lean=55)    # shaggy hump
    for q in range(3):                                                               # claw scars on the left flank
        d.seg((2.62, -0.2 + q * 0.5, 9.6), (2.62, 0.6 + q * 0.5, 8.0), (0.12, 0.26), col='scar', bone=B)

    # ---------------- broad roaring head ----------------
    N, H = 'Neck', 'Head'
    d.seg((0, -3.8, 9.4), (0, -6.0, 11.0), (3.4, 3.4), col='fur', bone=N)
    O = V((0, -7.4, 11.4))

    def P(x, y, z):
        return O + V((x, y, z))

    d.box((3.6, 2.8, 2.8), P(0, 0, 0), col='fur', bone=H)                           # broad skull
    d.box((4.4, 1.4, 2.8), P(0, 1.0, -0.3), col='fur2', bone=H)                     # fur ruff round the head
    d.box((2.4, 1.8, 1.6), P(0, -2.0, -0.5), col='light', bone=H)                   # short blunt muzzle
    d.box((1.1, 0.5, 0.6), P(0, -2.95, 0.1), col='nose', bone=H)                    # big nose
    d.box((3.4, 1.0, 0.6), P(0, -1.0, 1.35), col='fur2', bone=H)                    # heavy brow
    for k in (1, -1):
        d.box((1.4, 1.0, 0.5), P(0.85 * k, -1.35, 1.15), rot=(0, -26 * k, 0), col='fur2', bone=H)   # angry brows
        d.box((0.8, 0.2, 0.4), P(0.85 * k, -1.48, 0.6), col='eye', bone=H)           # glowing orange eyes
        d.box((0.2, 0.7, 0.4), P(1.82 * k, -0.9, 0.6), col='eye', bone=H)
        d.box((0.9, 0.5, 0.9), P(1.4 * k, 0.6, 1.7), col='fur2', bone=H)             # round ears
        d.box((0.34, 0.34, 1.0), P(0.75 * k, -2.55, -1.55), rot=(180, 0, 0), col='tooth', bone=H, taper=(0.25, 0.3))   # upper fangs
    d.box((2.0, 1.6, 0.3), P(0, -1.8, -1.4), col='mouth', bone=H)
    jr = (26, 0, 0)
    Rj = sk._rot(jr)
    jp = P(0, -0.4, -1.3)
    d.box((2.2, 2.4, 0.7), jp + Rj @ V((0, -1.2, -0.35)), rot=jr, col='light', bone='Jaw')
    d.box((1.8, 2.0, 0.2), jp + Rj @ V((0, -1.2, 0.05)), rot=jr, col='mouth', bone='Jaw')
    for k in (1, -1):
        d.box((0.3, 0.3, 0.8), jp + Rj @ V((0.7 * k, -2.1, 0.45)), rot=jr, col='tooth', bone='Jaw', taper=(0.25, 0.3))   # lower fangs

    # ---------------- thick bear legs, big clawed paws ----------------
    for k, s in ((1, 'L'), (-1, 'R')):
        AU, AD, LU, LD = 'ArmU_' + s, 'ArmD_' + s, 'LegU_' + s, 'LegD_' + s
        x = 2.6 * k
        d.seg((x, -3.0, 9.0), (x, -2.8, 4.6), (2.2, 2.4), col='fur', bone=AU)
        d.box((1.0, 1.0, 1.2), (x, -1.6, 4.9), rot=(180, 0, 0), col='fur2', bone=AD, taper=(0.5, 0.5))   # elbow tuft
        d.seg((x, -2.8, 4.8), (x, -3.4, 1.0), (1.9, 2.0), col='fur', bone=AD)
        d.foot((x, -3.7, 0.5), (2.4, 2.4, 1.0), 4, 'fur2', 'claw', AD, forward=-1)
        d.seg((x, 2.8, 8.8), (x, 1.6, 4.8), (2.4, 2.8), col='fur', bone=LU)
        d.seg((x, 1.6, 5.0), (x, 3.0, 1.0), (1.9, 2.0), col='fur', bone=LD)
        d.foot((x, 2.7, 0.5), (2.4, 2.4, 1.0), 4, 'fur2', 'claw', LD, forward=-1)

    # ---------------- stub tail ----------------
    d.box((1.0, 1.0, 1.0), (0, 5.2, 9.2), col='fur2', bone='Tail1')
    return d
