# Style and recipes

Everything here comes from the reference creatures in `examples/`. When in doubt, open the closest example and copy
its patterns, then make the shape your own.

## 1. Axes, sizes and proportions

- The creature faces **-Y**. **+Z** is up, the ground is z = 0. **+X is the creature's left**: give the left piece
  and `mirror=True`, the right copy is made for you (bones ending in `_L` become `_R`).
- 1 unit = 1 Roblox stud. The avatar is ~5 studs tall. Reference sizes from the examples:

| example | tier | length | height | blocks |
|---|---|---|---|---|
| Cow | simple | 10 | 7.5 | 57 |
| T-Rex | epic | 48 | 27 | 135 |
| Dragon | epic | 40 | 24 (wingspan 34) | 257 |
| Cerberus | epic | 34 | 21 | 305 |

- Proportions that read as "epic toy": a big head (a quarter to a third of the body length on predators), thick
  limbs (a leg is at least a third as wide as the torso), chunky feet, a tail as long as the body.

## 2. Bones

Make bones first; every block goes on one bone. Standard names (the Roblox Animation Editor accepts any names, but
these make every creature animate the same way):

| part | bones |
|---|---|
| torso | `Body` (from the hips forward to the chest) |
| neck, head, jaw | `Neck` (or `Neck1`, `Neck2`), `Head`, `Jaw` (child of `Head`, its head at the hinge) |
| front legs / arms | `ArmU_L` (shoulder to elbow), `ArmD_L` (elbow to wrist) |
| hind legs | `LegU_L` (hip to knee), `LegD_L` (knee to foot) |
| tail | `Tail1`, `Tail2`, `Tail3`... (each a child of the one before) |
| wings | `Wing1_L` (shoulder to elbow), `Wing2_L` (elbow to wrist) |
| serpent body | `Seg1` (behind the head) ... `SegN` (tail tip), made by `blockkit.serpent` |
| extra heads | `Neck2`/`Head2`/`Jaw2`..., or `NeckS_L`/`HeadS_L`/`JawS_L` for a mirrored pair |

Rules:
- A bone runs from the joint to the next joint; a block belongs to the bone of the part it moves with.
- Every joint needs **overlap**: the block before the joint runs a little past it and the block after starts a
  little before it, so bending opens no gap (`blockkit.leg` and `tube` do this for you).
- Bones with no block get a hidden anchor automatically (Roblox's importer drops empty bones).

## 3. Torso

Two or three big overlapping boxes, then layers on top:

```python
d.box((6.6, 5.2, 6.6), (0, -2.6, 9.8), col='red', bone='Body')     # chest (widest)
d.box((6.0, 5.4, 5.8), (0, 1.6, 9.4), col='red', bone='Body')      # belly
d.box((5.6, 4.2, 5.8), (0, 5.3, 9.6), col='red', bone='Body')      # hips
d.box((5.6, 4.6, 1.4), (0, -2.4, 13.6), col='red', bone='Body')    # shoulder hump on top
for y in (-3.6, -1.6, 0.4, 2.4, 4.4, 6.2):                          # belly plates, contrast colour
    d.box((4.2, 1.7, 0.7), (0, y, 6.4), col='tan', bone='Body')
d.box((2.0, 4.6, 4.8), (3.25, -2.8, 9.8), col='red2', bone='Body', mirror=True)   # shoulder armour
d.box((2.0, 4.8, 5.4), (3.0, 4.9, 9.3), col='red2', bone='Body', mirror=True)     # haunch armour
d.spikes((0, -4.0, 14.2), (0, 6.6, 13.4), 7, 1.2, 2.3, 0.85, 'red2', 'Body', lean=35, tip='claw')   # spine
```

Variations: a T-Rex chest is tilted (`rot=(18, 0, 0)`); a bear has a huge chest and small hips; a cat is long and
low; a farm animal is one barrel plus a shoulder and a hip block. Side detail: scales, stripes, rib plates or lava
cracks laid half into the side (`x = half width`), alternating heights.

## 4. Heads

### 4a. Dragon / reptile (the reference epic head)

```python
d.box((3.2, 3.6, 2.8), (0, -8.6, 18.8), col='red', bone='Head')                        # skull
d.box((2.5, 3.4, 1.6), (0, -11.7, 18.4), col='red', bone='Head', taper=(0.88, 1))      # snout, narrower on top
d.box((2.6, 1.6, 0.9), (0, -12.6, 19.1), col='red3', bone='Head')                      # nose ridge
d.box((1.25, 1.5, 0.5), (0.95, -10.1, 20.0), rot=(0, -28, 0), col='red2', bone='Head', mirror=True)  # ANGRY BROWS
d.box((0.8, 0.22, 0.5), (1.08, -10.62, 19.45), col='eye', bone='Head', mirror=True)    # eye, front face
d.box((0.25, 1.0, 0.5), (1.62, -10.0, 19.45), col='eye', bone='Head', mirror=True)     # eye, side face
d.box((0.5, 0.25, 0.35), (0.6, -13.42, 18.6), col='mouth', bone='Head', mirror=True)   # nostrils
d.box((1.7, 3.0, 0.6), (0, -11.4, 17.35), col='mouth', bone='Head')                    # palate
d.box((1.0, 0.8, 0.6), (0, -10.0, 17.5), col='ember', bone='Head')                     # fire in the throat (glow)
for y in (-13.0, -12.2, -11.4, -10.6):                                                  # upper teeth, pointing down
    d.box((0.32, 0.32, 0.6), (0.95, y, 17.3), rot=(180, 0, 0), col='tooth', bone='Head', taper=(0.3, 0.3), mirror=True)
d.box((2.2, 3.9, 0.9), (0, -11.0, 16.55), rot=(16, 0, 0), col='red', bone='Jaw')       # jaw resting OPEN (16 deg)
d.box((1.6, 3.4, 0.3), (0, -11.0, 17.05), rot=(16, 0, 0), col='mouth', bone='Jaw')     # inside of the jaw
d.horn((1.2, -8.0, 19.9), (0.35, 1.0, 0.55), 5.0, 0.85, 5, -14, 'horn', 'Head', tip='claw', mirror=True)   # big horns
d.horn((1.6, -10.2, 17.9), (1.0, 0.7, -0.4), 1.4, 0.38, 2, 12, 'red2', 'Head', mirror=True)               # cheek spikes
d.slab([(0, -9.0, 20.1), (0, -7.4, 21.7), (0, -6.4, 21.0), (0, -6.8, 19.8)], 0.55, col='red3', bone='Head')  # crest
```

The brow rotation sign matters: on the left side (+X) use `rot=(0, -N, 0)` so the brow's inner end drops towards
the nose (angry). `+N` makes it look sad or scared.

### 4b. Big-jaw predator (T-Rex, crocodile, shark)

Long skull and snout, a gum strip and a palate, a row of 6-7 teeth per side plus front teeth, a hinged lower jaw
resting open with its own teeth (rotate their offsets with the jaw: see `examples/trex.py`), a tongue, jaw muscles
on the cheeks, a heavy brow plate and short brows over the eyes. The mouth reads from the front: red inside, white
teeth, so keep the jaw open 14-20 degrees at rest.

### 4c. Mammal / wolf head (Cerberus)

Skull, a shorter snout with a ridge, a dark nose block, brows (`rot=(0, -26*s, 0)`), glowing eyes, ears as tapered
boxes (`taper=(0.2, 0.35)`) with an inner colour, cheek fur blocks, two fangs per side pointing down, a jaw open 14
degrees. Build the head inside a function `head(origin, yaw, size)` (see `examples/cerberus.py`): it gives you
multi-headed creatures and differently sized heads for free.

### 4d. Simple / farm head (Cow)

Skull, a muzzle block in a contrast colour, two nostril blocks, `blockkit.front_eye` (white eye, dark lid,
`rim=` dark outline on pale skin), ears sideways, short horns. No glow, no teeth, no attitude needed: clean and a
bit funny.

### 4e. Beaks (birds, griffins)

Upper beak = a tapered box hooking down at the tip (a second small tapered box angled down), lower beak = a thinner
tapered box under it, slightly open. Brows still slant down; eyes on the sides of the head.

## 5. Eyes

- Epic: glowing block(s) (`d.glow.add('eye')`) under a dark brow. On a front-facing face use two blocks (front and
  side) like the Dragon so the eye reads from both views.
- Simple: `blockkit.side_eye` / `front_eye` with a white eye colour and a dark lid; `tilt` gives attitude.
- Never a pupil, never a black dot.

## 6. Teeth, horns, spikes, plates

- Tooth: `d.box((0.32, 0.32, 0.6), pos, rot=(180, 0, 0), col='tooth', taper=(0.3, 0.3))` (down) or without the
  rotation for lower teeth (up). Off-white, smooth.
- Horn: `d.horn(base, direction, length, thick, segments, bend_degrees, col, bone, tip='claw')`: curved and
  tapering, dark tip.
- Spike rows: `d.spikes(a, b, n, h0, h1, width, col, bone, lean=30..45, tip='claw')`. Use them on the spine, neck,
  tail and head crest; heights peak in the middle of the row.
- Plates: thin boxes in the contrast colour along the belly, chest and neck (rotate them with the neck,
  `rot=(-30, 0, 0)`), half sunk into the body.

## 7. Limbs and feet

- **Upright legs** (dragon arms, bears, dogs): `seg` from inside the torso down to the elbow/knee, a plate or band
  over the joint, a second `seg` down to the foot, then `d.foot(center, size, toes, col, claw_col, bone)`.
- **Bent-back legs** (T-Rex, birds, raptors): a thick thigh going forward and down to the knee, a shin going back
  and down to the ankle, a short ankle block, a big foot, a heel spur.
- **Hooves**: `blockkit.leg(..., hoof=(sx, sy, sz))`. **Paws**: `blockkit.paw`.
- Leg tops start inside the torso and are narrower than the torso where they enter.

## 8. Tails

```python
tail = [V((0, 7.0, 9.6)), V((0, 11.0, 8.8)), V((0, 15.0, 7.6)), V((0, 19.0, 6.9)), V((0, 23.0, 7.5))]
thick = [(3.4, 3.2), (2.6, 2.4), (1.9, 1.8), (1.3, 1.2)]
bones = ['Tail1', 'Tail2', 'Tail3', 'Tail3']
for i in range(4):
    d.seg(tail[i], tail[i + 1] + (tail[i + 1] - tail[i]).normalized() * 0.3, thick[i], col='red', bone=bones[i])
```

Then spikes along the top, a belly strip underneath, stripes across, and a tip: a spade (`slab`), a fan, a flame
(tapered `fire` blocks around the tip), a club.

## 9. Wings and fins

- Bat / dragon wings: `blockkit.bat_wing(d, S, E, W, tips, root, arm_col, claw_col)` = arm, fingers with claws,
  membrane slabs in two alternating dark colours.
- Feathered wings: a thick arm `seg`, then 6-10 long thin feather boxes fanned along it, each a little longer
  towards the tip, two alternating colours, the outer row a lighter colour.
- Fins and sails: `slab` polygons in a fin colour, 0.3-0.4 thick, seated half into the body.

## 10. Serpents, sea serpents, wyrms

`segs = blockkit.serpent(d, pts, radii, 'main', belly='belly')` makes the body and the `Seg` bones, and returns each
segment's frame (`a`, `b`, `t`, `up`, `side`, `r`, `h`, `bone`) so you can decorate it. **A serpent made of equal
boxes looks like stacked blocks.** Make it a creature:
- radii change a lot: thick right behind the head, thickest in the first third, thinning to a needle tail;
- the path waves in 3D (side to side AND up and down), never a straight line;
- every segment gets armour on top (a wider, flatter plate in a darker shade, overlapping the next one like
  scales), a row of spikes or a webbed sail, side ridges or fins, the belly strip, and glow spots or stripes on
  some segments;
- the head is a full epic head (section 4a/4b) on its own `Head` and `Jaw` bones parented to `Seg1`, clearly wider
  than the neck, with a frill, horns or crown;
- fins near the front (pectorals) and a big tail fin or blade.

## 11. Many heads (hydra, cerberus)

Write one `head(origin, yaw, size, bones)` function and call it per head: same design, different size and angle.
Each neck is a `seg` (or a short chain) with plates or a collar and spikes along its top. The middle head is the
biggest and highest; side heads turn outwards. Necks start INSIDE a shoulder block that is wide enough for all of
them.

## 12. Glow accents

Pick ONE family per creature (fire, lava, runes, crystals, electricity) plus the eyes. Fire manes = tapered boxes
in `fire` with smaller `fire2` boxes inside them; lava cracks = thin `seg`s laid on the skin; crystals = rotated
boxes. Glow colours go in `d.glow` (Neon in Roblox, emissive in the preview). Keep glow to a few accents: if half
the creature glows, nothing stands out.

## 13. Palettes

```python
dragon = {'red': (200, 38, 38), 'red2': (150, 22, 28), 'red3': (226, 66, 54), 'tan': (228, 196, 126),
          'horn': (46, 40, 50), 'claw': (22, 20, 24), 'tooth': (246, 240, 226), 'eye': (255, 204, 32),
          'mouth': (96, 12, 22), 'ember': (255, 120, 30), 'membrane': (118, 18, 30)}
hellhound = {'fur': (46, 42, 50), 'fur2': (70, 66, 76), 'fur3': (30, 28, 34), 'pale': (200, 200, 210),
             'steel': (160, 164, 176), 'eye': (255, 150, 30), 'fire': (255, 84, 14), 'fire2': (255, 190, 40)}
```

Saturated but not neon for the body; the glow accent is the brightest thing on the creature.

## 14. Common mistakes

- Head = one box with two eyes: add brows, an open jaw, teeth, horns or a crest.
- Torso = one box: use chest + belly + hips and layer plates and armour.
- A long body of identical blocks: vary sizes, add plates, fins, spikes, a real head.
- Tiny pieces everywhere: fewer, bigger, clearer blocks.
- Pieces floating a little above the body, or two faces of different colours in the same plane: the report finds
  both; sink details half into the body and make sizes differ by 0.05+.
- Legs whose tops stick out beside the torso: start them inside and narrower.
- Pupils, smiles on aggressive creatures, items in hands, saddles and bells that add nothing.
- Nostrils in a bright colour on the front of the snout read as a second pair of eyes from the front: make them
  small and near-black.
- Many-headed creatures with short necks look like heads growing out of the chest: give the necks real length and
  spread the heads in a fan (outer ones lower and turned out, the middle one highest).
- Two dark squares on a plain snout front read as eyes even when they are nostrils: put nostrils on TOP of the
  snout, make them thin slits, or leave them out. The real eyes must win the face test.
- Eyes hidden behind the snout from the front: lower the snout top or raise the eyes so the front faces of the
  eyes sit above it, just under the brows.
- A pale glow (white-blue) on a white head disappears; a dark frame around it reads as glasses. Use a saturated
  glow colour (electric blue, gold, red) and no frame.
- Five upright spikes in a row on a head read as a hand from the front: use 3, swept back, the middle one tallest.
- White puffs at the nose (steam) read as a moustache or tusks from the front: leave them out.
- Symmetric marks read as symbols: a ">" and "<" pair, a W zigzag, V or check marks, a dotted arc (a smile). Cracks
  and runes are jagged 3-4 segment lightning lines, different on each side.
- Triangles along a flank (tapered boxes for countershading) read as a second row of teeth: use stepped rectangles.
- Two wide flat fins on top of a tall body read as a hat from the front: angle them back and up.
- Animals that lie (walrus, seal) standing on four stick legs: put the belly ON the ground and splay the flippers
  flat to the sides.
- A long body on very long thin legs reads as a table, not a beast: deepen the body, step its underside, make the
  legs thick and shorter.
- If the game scales creatures to a fixed overall height or length, appendages that add height or length (a tall
  mantle, raised arms, long tail fans) make the body look smaller in game. Tell the user when a design is much
  taller or longer than before.

## 15. More body plans

**Head frame helper.** Every epic head in the examples is built in a local frame, so it can be moved and scaled:

```python
O = V((0, -8.8, 14.8))                     # skull centre; the head faces -Y
def P(x, y, z): return O + V((x, y, z))
d.box((3.6, 4.4, 3.2), P(0, 0, 0), col='main', bone='Head')                       # skull
d.box((3.2, 1.8, 2.6), P(0, -2.9, -0.25), col='main', bone='Head', taper=(0.92, 1))  # snout
for k in (1, -1):                                                                     # k = +1 left, -1 right
    d.box((1.6, 1.8, 0.7), P(1.0 * k, -1.4, 1.9), rot=(0, -24 * k, 0), col='dark', bone='Head')   # angry brow
    d.box((1.0, 0.25, 0.5), P(1.05 * k, -2.25, 1.32), col='eye', bone='Head')        # eye, front face
    d.box((0.25, 1.3, 0.5), P(1.82 * k, -1.4, 1.32), col='eye', bone='Head')         # eye, side face
jr = (18, 0, 0)                            # the jaw rests open: everything on it rotates about the hinge
Rj, jp = sk._rot(jr), P(0, 0.8, -1.8)
def JB(size, off, col, **kw): d.box(size, jp + Rj @ V(off), rot=jr, col=col, bone='Jaw', **kw)
JB((3.0, 4.8, 1.1), (0, -2.4, -0.55), 'main')
JB((0.36, 0.36, 0.7), (1.05, -3.4, 0.4), 'tooth', taper=(0.25, 0.3))                 # lower tooth
```

**Smooth tapered shapes** (a squid mantle, a volcano, a tower): a stack of shrinking boxes reads as a stack. Give
each box `taper` = (next width / width, next depth / depth) and `shift` so its top face is exactly the next box's
bottom face: one continuous cone (`kraken.py`).

**Sharks and whales** (`megalodon.py`): stepped torpedo (body block plus a narrower block on the back), white only
underneath with a stepped edge, stripes over the back, gill slits as thin dark boxes, a stepped snout, jaws gaping
with two rows of flat triangular teeth (`box((0.3, 0.8, h), ..., taper=(0.6, 0.12))`), a tall sickle dorsal fin
from two convex slabs, scythe pectorals with a dark leading edge, a crescent tail of two lobes with dark trailing
edges. Slab polygons must be convex: split a hooked or notched fin into convex pieces.

**Snakes on the ground** (`titanoboa.py`): `serpent()` along an S that lies on the ground, the front third rising in a
strike curve to a wide head held high. Avoid exactly vertical segments (give each a little forward lean).

**Tentacles** (`kraken.py`): 3 bones each, thick to thin, a dark ridge along the top, two rows of pale suckers
underneath, the last block curling up; arrange 8 in a ring on the ground and raise 2 hunting arms in front.

**Birds** (`roc.py`): wing = arm slab + dark leading-edge bar + a covert row + 4 separate secondary feathers along
the trailing edge + 5 separate primaries spread like fingers, every feather tip in a contrast colour; tail = 5-7
separate feathers in a fan; feathered thighs over banded scaly shanks and hooked talons; a crest swept BACK.

**Fire manes and rings** (`chimera.py`): flame boxes placed round the face, each rotated with
`sk.look_rot(outward + V((0, 0.35, 0)))`, alternating long and short, a small second-glow box on each tip.

**Crystal clusters**: 2-5 tapered boxes from one base, fanned by rotating each one a little about Y and leaning back.

**Bears and heavy mammals** (`arctodus.py`): deep stepped torso (chest, belly, rump) with a shoulder hump, fur hanging
in tapered boxes turned upside down under the belly and chest, thick legs, `foot()` paws with long pale claws, a
wide head with a fur ruff, round ears and a roaring jaw.
