"""Cow (simple tier, farm animal). The reference for the SIMPLE end of the style: few big blocks, clean
patches laid half into the body, a white eye under a dark lid (no glow), short legs on hooves, no extra
accessories. Faces -Y."""
import blockkit as bk



def build(sk):
    rgb = sk.rgb
    pal = {'white': rgb(248, 246, 240), 'white2': rgb(226, 222, 214), 'black': rgb(38, 36, 40), 'muzzle': rgb(255, 176, 186),
           'nose': rgb(170, 80, 100), 'horn': rgb(236, 226, 200), 'eye': rgb(252, 250, 244), 'lid': rgb(34, 30, 34), 'hoof': rgb(60, 50, 46)}
    d = sk.Creature('Cow', pal)
    d.smooth.update({'horn', 'eye', 'lid'})

    # ---------------- bones (as cow_v2) ----------------
    d.bone('Body', (0, 2.4, 4.2), (0, -2.4, 4.4))
    d.bone('ArmU_L', (0.8, -1.5, 4.0), (1.0, -2.02, 2.0), 'Body', mirror=True)
    d.bone('ArmD_L', (1.0, -2.02, 2.0), (1.0, -1.9, 0.4), 'ArmU_L', mirror=True)
    d.bone('LegU_L', (0.84, 1.43, 4.2), (1.05, 2.65, 2.1), 'Body', mirror=True)
    d.bone('LegD_L', (1.05, 2.65, 2.1), (1.05, 2.1, 0.4), 'LegU_L', mirror=True)
    d.bone('Neck', (0, -2.5, 4.9), (0, -3.4, 5.5), 'Body')
    d.bone('Head', (0, -3.0, 5.6), (0, -5.6, 5.3), 'Neck')
    d.bone('Jaw', (0, -4.3, 5.0), (0, -5.3, 4.8), 'Head')
    d.bone('Tail1', (0, 2.6, 5.0), (0, 3.25, 4.3), 'Body')
    d.bone('Tail2', (0, 3.25, 4.3), (0, 3.3, 2.7), 'Tail1')

    # ---------------- torso ----------------
    d.box((3.4, 5.6, 3.0), (0, 0.1, 4.4), col='white', bone='Body')                  # barrel
    d.box((3.5, 2.0, 3.2), (0, -1.9, 4.6), col='white', bone='Body')                 # shoulders
    d.box((3.5, 1.8, 3.1), (0, 2.3, 4.55), col='white', bone='Body')                 # hips
    d.box((2.5, 1.0, 0.4), (0, 2.4, 6.25), col='white', bone='Body')                 # hip bones
    d.box((2.6, 4.6, 0.3), (0, 0.0, 2.8), col='white2', bone='Body')                 # belly
    d.box((0.9, 1.0, 0.7), (0, 1.0, 2.5), col='muzzle', bone='Body')                 # udder
    for x in (-0.25, 0.25):
        for y in (0.75, 1.25):
            d.box((0.18, 0.18, 0.35), (x, y, 2.07), col='muzzle', bone='Body')
    # black patches, laid on the skin (half inside); each side different
    d.box((0.14, 1.8, 1.7), (1.71, 0.3, 4.6), col='black', bone='Body')
    d.box((0.16, 0.9, 0.8), (1.71, -0.35, 5.45), col='black', bone='Body')
    d.box((0.16, 1.0, 1.0), (1.76, -2.15, 4.3), col='black', bone='Body')
    d.box((0.14, 1.4, 1.3), (-1.71, -0.1, 4.0), col='black', bone='Body')
    d.box((0.16, 1.2, 0.9), (-1.76, 2.3, 5.0), col='black', bone='Body')
    d.box((0.16, 0.8, 0.7), (-1.71, 0.9, 5.1), col='black', bone='Body')
    d.box((1.6, 1.6, 0.14), (0.4, -0.6, 5.91), col='black', bone='Body')

    # ---------------- neck & head ----------------
    d.seg((0, -2.4, 4.9), (0, -3.7, 5.6), (2.2, 2.0), col='white', bone='Neck')
    d.box((2.3, 1.9, 2.0), (0, -4.0, 5.9), col='white', bone='Head')                 # skull
    d.box((2.0, 1.25, 1.3), (0, -5.45, 5.35), col='muzzle', bone='Head')             # long pink muzzle
    d.box((0.3, 0.1, 0.25), (0.45, -6.1, 5.55), col='nose', bone='Head', mirror=True)
    d.box((1.7, 1.2, 0.5), (0, -5.35, 4.55), col='muzzle', bone='Jaw')               # lower jaw
    d.box((1.05, 0.1, 0.8), (-0.695, -4.95, 6.45), col='black', bone='Head')         # patch round the right eye,
    d.box((0.1, 1.42, 1.0), (-1.15, -4.31, 6.3), col='black', bone='Head')           # wrapping the corner
    bk.front_eye(d, 'Head', (0.62, -4.95, 6.45), (0.6, 0.5), tilt=8, rim='lid')
    d.box((1.2, 0.5, 0.35), (0, -3.5, 7.0), col='white', bone='Head')               # poll between the horns
    d.horn((0.95, -3.5, 6.7), (1, 0, 0.3), 1.1, 0.4, 3, 32, 'horn', 'Head', mirror=True)
    d.box((1.0, 0.35, 0.5), (1.5, -3.6, 6.3), rot=(0, 15, 0), col='white', bone='Head', mirror=True)     # ears
    d.box((0.7, 0.1, 0.3), (1.58, -3.79, 6.28), rot=(0, 15, 0), col='muzzle', bone='Head', mirror=True)

    # ---------------- legs ----------------
    bk.leg(d, 'ArmU_L', 'ArmD_L', (1.0, -1.75, 4.0), (1.0, -2.02, 2.0), (1.0, -1.9, 0.4), (1.1, 1.2), (0.85, 0.95), 'white',
           hoof=(1.0, 1.1, 0.5))
    bk.leg(d, 'LegU_L', 'LegD_L', (1.05, 1.6, 4.2), (1.05, 2.65, 2.1), (1.05, 2.1, 0.4), (1.2, 1.4), (0.85, 0.95), 'white',
           hoof=(1.0, 1.1, 0.5))

    # ---------------- tail ----------------
    d.seg((0, 3.0, 5.5), (0, 3.5, 4.3), 0.36, col='white', bone='Tail1')
    d.seg((0, 3.5, 4.45), (0, 3.5, 2.95), 0.3, col='white', bone='Tail2')
    d.box((0.55, 0.55, 0.8), (0, 3.5, 2.6), col='black', bone='Tail2')
    return d
