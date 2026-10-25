"""Megalodon (epic tier). The giant shark: a stepped
torpedo, blue over white with a jagged countershading line, dark tiger stripes over the back, a glowing dashed
lateral line, five deep gill slits, a stepped pointed snout with angry brows over glowing eyes, jaws gaping wide with
two rows of flat triangular teeth top and bottom, a tall sickle dorsal fin with a bite notch and scars, scythe
pectoral fins, small pelvic, second dorsal and anal fins, keels on the tail stock and a huge crescent tail."""
from mathutils import Vector as V


def build(sk):
    rgb = sk.rgb
    pal = {'body': rgb(70, 94, 128), 'body2': rgb(94, 122, 160), 'dark': rgb(42, 58, 86), 'belly': rgb(238, 240, 242),
           'fin': rgb(58, 80, 112), 'mouth': rgb(140, 36, 52), 'gum': rgb(190, 70, 84), 'tooth': rgb(250, 248, 240),
           'gill': rgb(28, 36, 54), 'eye': rgb(160, 244, 255), 'lumi': rgb(90, 230, 255), 'scar': rgb(198, 212, 228)}
    d = sk.Creature('Megalodon', pal)
    d.glow.update({'eye', 'lumi'})
    d.smooth.update({'tooth'})

    # ---------------- bones ----------------
    d.bone('Body', (0, 4.0, 6.8), (0, -3.4, 6.8))
    d.bone('Head', (0, -3.4, 6.8), (0, -12.6, 7.6), 'Body')
    d.bone('Jaw', (0, -4.6, 4.4), (0, -11.0, 2.0), 'Head')
    d.bone('Tail1', (0, 4.0, 6.8), (0, 8.0, 7.0), 'Body')
    d.bone('Tail2', (0, 8.0, 7.0), (0, 11.6, 7.2), 'Tail1')
    d.bone('Tail3', (0, 11.6, 7.2), (0, 14.8, 7.3), 'Tail2')
    d.bone('Fin_L', (2.9, -2.4, 4.8), (8.6, 0.4, 2.6), 'Body', mirror=True)

    # ---------------- stepped torpedo ----------------
    B = 'Body'
    d.box((6.0, 7.8, 6.2), (0, 0.2, 6.8), col='body', bone=B)
    d.box((4.4, 7.2, 0.8), (0, 0.4, 10.3), col='body', bone=B)                      # rounded back step
    d.box((5.0, 7.4, 0.6), (0, 0.2, 3.45), col='belly', bone=B)                     # white belly
    for k in (1, -1):
        d.box((0.3, 7.6, 1.8), (3.05 * k, 0.2, 4.6), col='belly', bone=B)           # white only underneath
        for y, h in ((-2.4, 0.5), (-0.4, 0.9), (1.4, 0.4), (3.0, 0.7)):             # ragged countershading line (steps, not teeth)
            d.box((0.3, 1.6, h), (3.05 * k, y, 5.5 + h / 2), col='belly', bone=B)
        for y in (-2.6, 0.0, 2.6):                                                  # glowing dashed lateral line
            d.box((0.2, 1.8, 0.3), (3.12 * k, y, 7.4), col='lumi', bone=B)
        for y in (-2.0, 0.4, 2.8):                                                  # tiger stripes down the flanks
            d.box((0.3, 0.8, 1.8), (3.05 * k, y, 8.9), col='dark', bone=B)
    for y in (-2.0, 0.4, 2.8):                                                      # ... and over the back
        d.box((3.6, 0.8, 0.3), (0, y, 10.75), col='dark', bone=B)
    for a, b in (((3.14, -3.0, 9.6), (3.14, -1.6, 7.9)), ((3.14, -2.2, 9.8), (3.14, -0.8, 8.1)), ((-3.14, 1.0, 9.4), (-3.14, 2.6, 8.0))):
        d.seg(a, b, (0.14, 0.3), col='scar', bone=B)                                # pale claw scars

    # tall sickle dorsal fin with a bite notch and dark trailing edge
    d.slab([(0, -2.6, 10.6), (0, 0.6, 14.0), (0, 2.8, 12.8), (0, 3.8, 10.6)], 0.9, col='fin', bone=B)
    d.slab([(0, 0.4, 13.8), (0, 2.6, 16.8), (0, 3.1, 16.4), (0, 2.8, 12.8)], 0.7, col='fin', bone=B)
    d.seg((0, 2.9, 16.3), (0, 3.6, 10.8), (0.8, 0.5), col='dark', bone=B)
    d.box((0.95, 0.6, 0.6), (0, 2.6, 13.6), col='belly', bone=B)                    # pale bite notch
    for y, z in ((0.4, 12.0), (1.2, 12.6)):
        d.box((0.95, 0.3, 0.3), (0, y, z), col='scar', bone=B)

    # ---------------- head: stepped snout, gills, angry brows ----------------
    H = 'Head'
    d.box((5.6, 3.8, 5.6), (0, -5.2, 7.0), col='body', bone=H)
    d.box((4.8, 3.2, 4.4), (0, -8.5, 7.5), col='body', bone=H)
    d.box((3.6, 2.2, 3.0), (0, -11.1, 8.0), col='body', bone=H)
    d.box((2.4, 0.8, 1.8), (0, -12.6, 8.1), col='body2', bone=H)                   # snout tip
    d.box((3.8, 2.2, 1.2), (0, -11.0, 5.95), col='body', bone=H)                    # under the snout
    d.box((4.2, 7.0, 0.5), (0, -7.4, 9.95), col='dark', bone=H)                     # dark crown over the head
    d.box((2.6, 2.0, 0.4), (0, -11.0, 9.65), col='dark', bone=H)
    for k in (1, -1):
        for i, y in enumerate((-3.8, -4.4, -5.0, -5.6, -6.2)):                     # five deep gill slits
            d.box((0.2, 0.28, 3.0 - i * 0.2), (2.85 * k, y, 7.0), rot=(-12, 0, 0), col='gill', bone=H)
        d.box((0.3, 3.4, 1.4), (2.85 * k, -5.2, 4.6), col='belly', bone=H)          # white throat sides
        # glowing eyes on the corners, under heavy angry brows (inner ends lower)
        d.box((1.1, 0.2, 0.6), (1.95 * k, -10.15, 8.3), col='eye', bone=H)
        d.box((0.2, 1.6, 0.6), (2.64 * k, -9.3, 8.3), col='eye', bone=H)
        d.box((0.2, 2.2, 1.2), (2.5 * k, -9.3, 8.2), col='gill', bone=H)             # dark eye socket
        d.box((1.8, 2.2, 0.6), (1.8 * k, -9.6, 9.05), rot=(14, -24 * k, 0), col='dark', bone=H)
        d.box((0.2, 0.3, 0.3), (1.0 * k, -12.95, 7.6), col='gill', bone=H)          # nostrils
        for y in (-7.6, -9.0):                                                      # ampullae dots along the snout
            d.box((0.2, 0.3, 0.3), (2.42 * k, y, 6.4), col='gill', bone=H)
    # upper jaw: two rows of flat triangular teeth
    d.box((4.6, 6.6, 1.2), (0, -8.6, 4.8), col='body', bone=H)
    d.box((4.4, 6.4, 0.4), (0, -8.7, 4.0), col='gum', bone=H)
    d.box((3.4, 5.4, 0.3), (0, -8.4, 3.75), col='mouth', bone=H)
    d.box((3.6, 2.0, 1.6), (0, -5.0, 3.4), col='mouth', bone=H)                    # throat behind the open jaw
    for k in (1, -1):
        for i in range(6):
            y = -11.2 + i * 1.0
            h = 1.3 - i * 0.08
            d.box((0.3, 0.8, h), (1.95 * k, y, 3.85 - h / 2), rot=(180, 0, 0), col='tooth', bone=H, taper=(0.6, 0.12))
            if i < 5:
                d.box((0.24, 0.6, h * 0.65), (1.35 * k, y + 0.5, 3.85 - h * 0.33), rot=(180, 0, 0), col='tooth', bone=H, taper=(0.6, 0.12))
    for x in (-1.3, -0.45, 0.45, 1.3):
        d.box((0.8, 0.3, 1.4), (x, -11.75, 3.15), rot=(180, 0, 0), col='tooth', bone=H, taper=(0.12, 0.6))

    # lower jaw gaping wide
    jr = (24, 0, 0)
    Rj = sk._rot(jr)
    jp = V((0, -4.6, 4.4))

    def JB(size, off, col, **kw):
        d.box(size, jp + Rj @ V(off), rot=jr, col=col, bone='Jaw', **kw)

    JB((4.6, 7.0, 1.3), (0, -3.6, -0.65), 'belly')
    JB((3.8, 6.4, 0.3), (0, -3.7, 0.05), 'mouth')
    JB((2.0, 3.6, 0.3), (0, -3.0, 0.2), 'gum')                                      # tongue
    for k in (1, -1):
        JB((0.4, 6.8, 0.6), (2.15 * k, -3.6, 0.0), 'body')                           # blue rim of the lower jaw
        for i in range(6):
            h = 1.2 - i * 0.08
            JB((0.3, 0.8, h), (1.7 * k, -6.4 + i * 1.0, h / 2), 'tooth', taper=(0.6, 0.12))
            if i < 4:
                JB((0.24, 0.6, h * 0.6), (1.15 * k, -5.9 + i * 1.0, h * 0.3), 'tooth', taper=(0.6, 0.12))
    for x in (-0.9, 0.0, 0.9):
        JB((0.7, 0.3, 1.2), (x, -6.85, 0.6), 'tooth', taper=(0.12, 0.6))

    # ---------------- fins ----------------
    d.slab([(2.9, -3.4, 5.0), (8.8, 0.0, 2.4), (8.6, 0.9, 2.2), (6.4, 0.4, 3.0), (2.9, -0.6, 4.4)], 0.6, col='fin', bone='Fin_L', mirror=True)
    d.seg((3.1, -3.3, 5.2), (8.9, -0.1, 2.6), (0.6, 0.5), col='dark', bone='Fin_L', mirror=True)       # leading edge
    d.box((0.8, 0.9, 0.7), (8.5, 0.5, 2.35), col='dark', bone='Fin_L', mirror=True)                    # dark tip
    d.slab([(2.2, 5.0, 4.6), (4.0, 7.6, 3.4), (3.4, 8.0, 3.4), (2.0, 6.8, 4.4)], 0.4, col='fin', bone='Tail1', mirror=True)   # pelvic fins
    d.slab([(0, 8.6, 8.8), (0, 10.2, 10.6), (0, 10.8, 10.4), (0, 10.6, 8.8)], 0.5, col='fin', bone='Tail2')   # second dorsal
    d.slab([(0, 8.8, 5.4), (0, 10.4, 3.8), (0, 10.9, 4.0), (0, 10.6, 5.4)], 0.5, col='fin', bone='Tail2')     # anal fin

    # ---------------- tail stock and crescent tail ----------------
    d.box((5.0, 4.4, 5.2), (0, 6.0, 6.9), col='body', bone='Tail1')
    d.box((4.2, 4.0, 0.5), (0, 6.0, 4.15), col='belly', bone='Tail1')
    d.box((3.4, 3.8, 3.8), (0, 9.8, 7.1), col='body', bone='Tail2')
    d.box((2.2, 3.4, 2.6), (0, 13.0, 7.2), col='body', bone='Tail3')
    for y, w in ((6.0, 3.6), (9.8, 2.4)):
        d.box((w, 0.8, 0.3), (0, y, 9.55 if y < 8 else 9.1), col='dark', bone='Tail1' if y < 8 else 'Tail2')
    d.box((3.6, 3.0, 0.6), (0, 13.0, 7.2), col='dark', bone='Tail3')                 # keels on the tail stock
    d.slab([(0, 13.4, 8.2), (0, 17.6, 14.6), (0, 18.5, 14.4), (0, 15.8, 7.4)], 0.8, col='fin', bone='Tail3')    # upper lobe
    d.slab([(0, 13.6, 6.4), (0, 15.8, 7.0), (0, 17.6, 2.0), (0, 16.8, 1.8)], 0.8, col='fin', bone='Tail3')      # lower lobe
    d.box((1.0, 2.8, 2.4), (0, 15.0, 7.2), col='fin', bone='Tail3')
    d.seg((0, 18.4, 14.3), (0, 15.9, 7.6), (0.9, 0.5), col='dark', bone='Tail3')                                # dark trailing edges
    d.seg((0, 15.9, 6.8), (0, 17.5, 2.2), (0.9, 0.5), col='dark', bone='Tail3')
    return d
