"""Chimera (epic tier). Three beasts in one: a muscular
golden lion with a dark back ridge and flame tufts on the elbows, its roaring head - angry brows over glowing ember
eyes, fangs, a pale muzzle - framed by a sun-ring mane of living fire; a black goat head with big curled ram horns,
angry brows, glowing eyes and a beard rising from the back on its own neck; leathery dragon wings with ember
webbing; and a scaled serpent tail rearing up into a snake head with glowing eyes, fangs and a forked tongue."""
import math
import blockkit as bk
from mathutils import Vector as V


def build(sk):
    rgb = sk.rgb
    pal = {'fur': rgb(204, 142, 70), 'fur2': rgb(164, 104, 48), 'light': rgb(242, 212, 160), 'flame': rgb(255, 118, 20),
           'flame2': rgb(255, 210, 60), 'goat': rgb(64, 56, 56), 'goat2': rgb(44, 38, 40), 'horn': rgb(222, 206, 170),
           'snake': rgb(84, 128, 60), 'snake2': rgb(54, 86, 40), 'eye': rgb(255, 170, 30), 'mouth': rgb(140, 30, 30),
           'tooth': rgb(248, 244, 232), 'claw': rgb(40, 30, 26), 'nose': rgb(84, 52, 40), 'mem': rgb(150, 40, 30),
           'mem2': rgb(110, 26, 24), 'tongue': rgb(210, 50, 80)}
    d = sk.Creature('Chimera', pal)
    d.glow.update({'eye', 'flame', 'flame2'})
    d.smooth.update({'horn', 'tooth', 'claw'})

    d.bone('Body', (0, 3.6, 6.8), (0, -3.6, 7.6))
    d.bone('ArmU_L', (1.8, -3.6, 7.6), (2.0, -3.0, 4.2), 'Body', mirror=True)
    d.bone('ArmD_L', (2.0, -3.0, 4.2), (1.95, -3.8, 0.6), 'ArmU_L', mirror=True)
    d.bone('LegU_L', (1.8, 3.0, 7.6), (2.0, 1.8, 4.4), 'Body', mirror=True)
    d.bone('LegD_L', (2.0, 1.8, 4.4), (1.95, 3.4, 0.6), 'LegU_L', mirror=True)
    d.bone('Neck', (0, -4.8, 9.0), (0, -6.0, 10.6), 'Body')
    d.bone('Head', (0, -6.2, 11.2), (0, -10.4, 11.2), 'Neck')
    d.bone('Jaw', (0, -8.0, 10.2), (0, -10.0, 9.4), 'Head')
    d.bone('Neck2', (0, -1.6, 9.4), (0, -2.4, 13.0), 'Body')
    d.bone('Head2', (0, -2.4, 13.8), (0, -6.0, 13.2), 'Neck2')
    d.bone('Jaw2', (0, -4.0, 13.0), (0, -5.6, 12.4), 'Head2')
    d.bone('Wing1_L', (1.6, -2.4, 9.2), (3.8, -1.6, 11.6), 'Body', mirror=True)
    d.bone('Wing2_L', (3.8, -1.6, 11.6), (6.2, -0.4, 13.0), 'Wing1_L', mirror=True)
    d.bone('Tail1', (0, 4.8, 7.6), (0, 7.2, 8.4), 'Body')
    d.bone('Tail2', (0, 7.2, 8.4), (0, 9.4, 8.6), 'Tail1')
    d.bone('Tail3', (0, 9.4, 8.6), (0, 10.6, 10.4), 'Tail2')

    # ---------------- muscular lion body ----------------
    B = 'Body'
    d.box((4.4, 3.4, 4.2), (0, -2.4, 7.7), col='fur', bone=B)                       # chest
    d.box((3.6, 3.6, 3.2), (0, 0.8, 7.5), col='fur', bone=B)                        # waist
    d.box((4.0, 2.4, 3.6), (0, 3.0, 7.5), col='fur', bone=B)                        # hips
    d.box((2.0, 7.0, 0.4), (0, 0.4, 9.45), col='fur2', bone=B)                      # dark back ridge
    d.box((2.8, 6.0, 0.25), (0, 0.4, 5.86), col='light', bone=B)                    # pale belly
    for k in (1, -1):
        d.box((1.1, 2.8, 3.2), (2.45 * k, -2.6, 7.8), col='fur2', bone=B)            # shoulders
        d.box((1.1, 2.4, 3.0), (2.3 * k, 2.8, 7.5), col='fur2', bone=B)              # haunches

    # ---------------- roaring lion head in a sun-ring of fire ----------------
    N, H = 'Neck', 'Head'
    d.seg((0, -3.8, 8.6), (0, -6.2, 11.0), (2.6, 2.8), col='fur', bone=N)
    d.spikes((0, -4.4, 10.0), (0, -6.0, 12.2), 3, 1.6, 2.0, 1.0, 'flame', N, lean=55, tip='flame2')
    O = V((0, -7.4, 11.3))

    def P(x, y, z):
        return O + V((x, y, z))

    d.box((3.0, 2.8, 2.6), P(0, 0, 0), col='fur', bone=H)                            # skull
    d.box((2.2, 1.6, 1.4), P(0, -2.0, -0.55), col='light', bone=H)                   # muzzle
    d.box((0.9, 0.4, 0.5), P(0, -2.85, 0.05), col='nose', bone=H)                    # nose
    d.box((3.0, 1.2, 0.5), P(0, -0.9, 1.4), col='fur2', bone=H)                      # brow plate
    for k in (1, -1):
        d.box((1.3, 1.3, 0.5), P(0.75 * k, -1.35, 1.25), rot=(0, -26 * k, 0), col='fur2', bone=H)   # angry brows
        d.box((0.8, 0.2, 0.4), P(0.75 * k, -1.48, 0.72), col='eye', bone=H)          # glowing ember eyes
        d.box((0.2, 0.7, 0.4), P(1.52 * k, -1.0, 0.72), col='eye', bone=H)
        d.box((0.6, 0.4, 0.6), P(1.1 * k, 0.4, 1.45), col='fur2', bone=H)            # ears
        d.box((0.3, 0.3, 1.0), P(0.6 * k, -2.5, -1.45), rot=(180, 0, 0), col='tooth', bone=H, taper=(0.25, 0.3))   # upper fangs
    d.box((1.7, 1.4, 0.3), P(0, -1.8, -1.35), col='mouth', bone=H)
    jr = (24, 0, 0)
    Rj = sk._rot(jr)
    jp = P(0, -0.6, -1.1)
    d.box((1.9, 2.0, 0.6), jp + Rj @ V((0, -1.0, -0.3)), rot=jr, col='light', bone='Jaw')
    d.box((1.5, 1.7, 0.2), jp + Rj @ V((0, -1.0, 0.05)), rot=jr, col='mouth', bone='Jaw')
    for k in (1, -1):
        d.box((0.28, 0.28, 0.8), jp + Rj @ V((0.55 * k, -1.7, 0.45)), rot=jr, col='tooth', bone='Jaw', taper=(0.25, 0.3))   # lower fangs
    d.box((3.6, 1.0, 3.4), P(0, 0.9, 0.1), col='flame', bone=H)                      # the fire mane's base behind the face
    for i in range(11):                                                               # sun-ring of flame spikes round the face
        a = math.radians(-120 + i * 24)
        out = V((math.sin(a), 0, math.cos(a)))
        base = P(0, 0.9, 0.1) + out * 1.4
        R = sk.look_rot(out + V((0, 0.35, 0)))
        h = 1.8 if i % 2 == 0 else 1.3
        d.box((0.8, 0.8, h), base + R @ V((0, 0, h / 2)), rot=R, col='flame', bone=H, taper=(0.35, 0.35))
        d.box((0.35, 0.35, 0.7), base + R @ V((0, 0, h + 0.2)), rot=R, col='flame2', bone=H, taper=(0.2, 0.2))

    # ---------------- goat head rising from the back ----------------
    N2, H2 = 'Neck2', 'Head2'
    d.seg((0, -1.6, 9.0), (0, -2.4, 13.2), 1.4, col='goat', bone=N2)
    d.seg((0, -1.1, 9.6), (0, -1.9, 12.6), (0.9, 0.6), col='goat2', bone=N2)        # shaggy ridge
    d.box((1.7, 1.9, 1.6), (0, -3.0, 14.0), col='goat', bone=H2)
    d.box((1.2, 1.8, 1.0), (0, -4.6, 13.6), col='goat', bone=H2, taper=(0.85, 1))
    d.box((0.5, 0.5, 1.3), (0, -4.6, 12.55), rot=(180, 0, 0), col='goat2', bone=H2, taper=(0.4, 0.4))   # beard
    for k in (1, -1):
        d.box((0.8, 0.9, 0.3), (0.5 * k, -3.55, 14.85), rot=(0, -24 * k, 0), col='goat2', bone=H2)       # angry brows
        d.box((0.45, 0.15, 0.3), (0.5 * k, -4.0, 14.4), col='eye', bone=H2)
        d.box((0.15, 0.7, 0.32), (0.87 * k, -3.4, 14.3), col='eye', bone=H2)
        d.horn((0.6 * k, -2.6, 14.7), (0.5 * k, 0.7, 0.6), 3.4, 0.62, 7, -50, 'horn', H2)                  # big curled ram horns
        d.seg((0.7 * k, -2.4, 14.4), (1.3 * k, -2.0, 14.6), (0.35, 0.25), col='goat2', bone=H2)          # ears
    jr2 = (16, 0, 0)
    Rj2 = sk._rot(jr2)
    jp2 = V((0, -3.8, 13.0))
    d.box((0.9, 1.6, 0.3), jp2 + Rj2 @ V((0, -0.8, -0.15)), rot=jr2, col='goat2', bone='Jaw2')

    # ---------------- leathery dragon wings ----------------
    bk.bat_wing(d, (1.5, -2.4, 9.0), (3.8, -1.6, 11.6), (6.2, -0.4, 13.0),
                [(8.8, 0.6, 14.4), (10.4, 2.0, 12.2), (9.8, 3.2, 9.8), (7.2, 3.2, 8.6)], [(1.5, 0.4, 8.6), (1.5, 2.4, 8.6)],
                'fur2', 'claw', mem=('mem', 'mem2'), size=0.6)

    # ---------------- scaled serpent tail rearing into a snake head ----------------
    tp = [V((0, 4.0, 7.8)), V((0, 7.2, 8.4)), V((0, 9.4, 8.6)), V((0, 10.6, 10.4))]
    for i, (th, b) in enumerate(((1.2, 'Tail1'), (1.05, 'Tail2'), (0.95, 'Tail3'))):
        a, c = tp[i], tp[i + 1]
        d.seg(a, c + (c - a).normalized() * 0.2, th, col='snake', bone=b)
        d.seg(a.lerp(c, 0.3), a.lerp(c, 0.5), th + 0.15, col='snake2', bone=b)       # scale band
    S = 'Tail3'
    d.box((1.4, 1.6, 1.0), (0, 11.2, 10.9), col='snake', bone=S)                     # snake skull
    d.box((1.0, 1.1, 0.7), (0, 12.4, 10.8), col='snake', bone=S, taper=(0.85, 1))
    for k in (1, -1):
        d.box((0.6, 0.7, 0.25), (0.42 * k, 11.7, 11.48), rot=(0, 24 * k, 0), col='snake2', bone=S)   # angry brows
        d.box((0.4, 0.15, 0.3), (0.4 * k, 12.03, 11.15), col='eye', bone=S)          # glowing eyes (it faces back)
        d.box((0.2, 0.2, 0.6), (0.3 * k, 12.7, 10.25), rot=(180, 0, 0), col='tooth', bone=S, taper=(0.25, 0.3))   # fangs
    d.box((0.9, 1.2, 0.25), (0, 12.2, 10.0), rot=(-20, 0, 0), col='snake2', bone=S)  # open lower jaw
    d.seg((0, 12.6, 10.2), (0, 13.6, 10.0), (0.2, 0.08), col='tongue', bone=S)
    for k in (1, -1):
        d.seg((0, 13.5, 10.0), (0.25 * k, 14.0, 10.0), (0.14, 0.08), col='tongue', bone=S)

    # ---------------- lion legs, big paws, flame tufts ----------------
    for k, s in ((1, 'L'), (-1, 'R')):
        AU, AD, LU, LD = 'ArmU_' + s, 'ArmD_' + s, 'LegU_' + s, 'LegD_' + s
        x = 2.0 * k
        d.seg((x, -3.4, 7.8), (x, -3.0, 4.2), (1.7, 1.9), col='fur', bone=AU)
        d.seg((x, -3.0, 4.4), (x, -3.7, 0.6), (1.3, 1.4), col='fur', bone=AD)
        d.foot((x, -3.9, 0.4), (1.6, 1.8, 0.6), 3, 'fur2', 'claw', AD, forward=-1)
        d.spikes((x, -2.3, 4.6), (x, -2.3, 4.6), 1, 0.9, 0.9, 0.5, 'flame', AD, lean=70, tip='flame2')   # flame tuft on the elbow
        d.seg((x, 3.0, 7.8), (x, 1.8, 4.4), (1.5, 1.9), col='fur', bone=LU)
        d.seg((x, 1.8, 4.6), (x, 3.3, 0.6), (1.2, 1.3), col='fur', bone=LD)
        d.foot((x, 3.0, 0.4), (1.6, 1.8, 0.6), 3, 'fur2', 'claw', LD, forward=-1)
    return d
