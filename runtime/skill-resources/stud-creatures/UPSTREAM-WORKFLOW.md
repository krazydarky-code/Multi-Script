---
name: stud-creatures
description: Build rigged, blocky, stud-textured creatures for Roblox in Blender, in the epic "brick toy" style of stud games - angular blocks, angry glowing eyes, big jaws full of teeth, horns, spikes and armour plates - from a simple farm animal to a giant mythical beast. Use whenever someone asks for a creature, animal, monster, pet, mount or boss model in a stud / blocky / brick / "like Steal an Egg" style, for a Roblox game, or names this skill. Outputs review renders, a rigged FBX (one mesh per colour, skeleton included) and a Roblox Studio setup script; studs are optional.
---

# Stud Creatures

Blocky creatures built only from straight blocks with a stud texture: every piece is a box, a box stretched between
two points, or a flat slab. One mesh per colour, each block glued rigidly to one bone, so the model is rigged and
ready to animate in Roblox. The style is the one in `examples/` (look at `examples/*.jpg` before starting): **Dragon,
T-Rex, Cerberus, Hydra, Leviathan, Kraken, Megalodon, Titanoboa, Roc and Chimera are the epic tier, Arctodus is the
normal tier, Cow is the simple tier.** Match them: a new creature should look like it belongs in that line-up.

Reply in the user's language. The scripts, file names and code stay in English.

## Before anything

- **Blender 4.2 or newer must be installed** (5.1 is tested). Everything runs headless from the command line; no
  add-on or MCP connection is needed. Find the executable (Windows: `C:\Program Files\Blender Foundation\Blender X.Y\blender.exe`,
  macOS: `/Applications/Blender.app/Contents/MacOS/Blender`, Linux: `blender`). If it is missing, tell the user to
  install it from blender.org and stop.
- Read `references/style.md` (how to think, and the body-part recipes) before writing the first block. Open the
  closest example in `examples/` (table below), look at its two pictures and reuse its code patterns.
  `references/api.md` lists every function.

| Asked for | Start from |
|---|---|
| dragon, wyvern, any winged reptile | `dragon.py` (body, head, bat wings) |
| dinosaur, biped predator | `trex.py` |
| wolf, dog, big cat, many-headed beast | `cerberus.py`, `chimera.py` (fire mane, goat head, snake tail) |
| several heads on long necks | `hydra.py` |
| bear, heavy mammal, normal-tier creature | `arctodus.py` |
| shark, fish, whale | `megalodon.py` |
| snake on the ground, cobra, boa | `titanoboa.py` |
| flying sea serpent, eel, wyrm | `leviathan.py` |
| squid, octopus, anything with tentacles | `kraken.py` (also: a smooth tapered cone made of blocks) |
| bird, eagle, griffin, phoenix | `roc.py` (layered feathers, talons) |
| farm, cute or funny animal | `cow.py` |
- Work in a folder of the user's choice: one file per creature (`hydra.py`), outputs go to `out/<Name>/`.

## The mindset (why most first attempts look wrong)

A generic 3D model of "a hydra" is smooth, realistic and detailed. This style is the opposite: **a toy built from
bricks that looks dangerous.** Keep these in your head the whole time:

1. **Blocks only.** `box`, `seg`, `slab`, `horn`, `spikes`, `foot`, and the `blockkit` helpers. No round meshes, no
   bevels, no smoothing, no welding pieces together. Angles come from rotating and tapering blocks.
2. **Big readable masses first.** A torso is 2-3 big overlapping boxes (chest, belly, hips), not one box and not
   twenty small ones. Limbs are thick. Heads are big. The silhouette must read from far away.
3. **Attitude lives in the head.** Angry brows slanting down towards the nose, glowing eyes under them, a jaw that
   rests OPEN with rows of tapered teeth, horns, cheek spikes, a crest. On epic creatures the head gets about a third
   of all the detail. A head that is just "a box with eyes" is the most common failure.
4. **Layered detail, not tiny noise.** Plates on the belly and chest in a contrast colour, armour boxes over the
   shoulders and hips, spikes down the spine with dark tips, stripes or scales laid half into the body. Each detail
   is a clear block you could see in a thumbnail.
5. **Colour = 2-3 shades of the main colour + 1 contrast + dark + glow.** Main / darker / lighter, a pale or warm
   contrast for belly and plates, near-black for claws and horn tips, off-white teeth, dark red mouth, and ONE glow
   accent family (eyes, fire, lava, runes, crystals) that becomes Neon in Roblox.
6. **Eyes have no pupils.** Aggressive or mythic: a glowing block under a dark angry brow. Farm, cute or funny: a
   white block under a dark lid. Never a black dot.
7. **Every creature has its own figure.** Same style, different shapes: a serpent is a long wave, a bear is a heavy
   front, a raptor is all legs and jaws. Don't reuse one body for everything.
8. **Only defining accessories.** Keep what makes the creature what it is (the cactus's hat, the chains of a
   hellhound). No saddles, bells or bags just to add pieces. Nothing held in hands: weapons go on the back.
9. **Simple when the creature is simple.** Farm and cute animals: 40-70 blocks, clean, original, a bit funny.
   Normal creatures: 70-160. Epic, mythic and bosses: 150-350. (Mirrored pieces count twice.)
10. **Scale in studs.** 1 Blender unit = 1 Roblox stud; the review scene has a 5-stud avatar. Small pets are about
    avatar size, giants are many times bigger. Bigger is not better, but a mix of sizes makes a world feel epic.
    Build at the size the creature will have in game: Roblox tiles the studs by the mesh UVs, so scaling the model
    later scales the studs too.

## Workflow

1. **Brief.** Decide (and say in one short line): the creature, its tier (simple / normal / epic), its mood
   (aggressive / cute / funny), 3-5 signature features, the palette (6-12 colour keys) and its size in studs. If the
   user gave pictures, take the silhouette and the signature features from them. Ask only if something essential
   is unclear; otherwise choose and state the choice.
2. **Write `<name>.py`** with `build(sk)` returning the `Creature`, in this order: palette, bones, torso, neck and
   head, limbs, tail, wings / extras. Start from the closest example. Name colours by role (`main`, `dark`, `belly`,
   `horn`, `eye`...). Put `d.glow` on glowing colours and `d.smooth` on horns, teeth, claws and metal.
3. **Build and look:**
   `blender -b --factory-startup -P <skill>/scripts/build.py -- <name>.py --pose`
   Read `out/<Name>/<Name>_report.txt`, then LOOK at `out/<Name>/<Name>_sheet.png` (four views, a head close-up and
   a test pose). Fix every FLOAT line (a piece touching nothing), anything that pokes out in the pose, and anything
   the checklist below catches. Repeat until it passes; 2-4 rounds is normal. Never show a model you have not
   looked at.
4. **Show the sheet** to the user, say what you chose, ask what to change.
5. **Export:** add `--export` (and `--colours` for the moderation check: each colour mesh alone must not look like
   anything inappropriate, Roblox reviews every mesh on its own). Then walk the user through `references/roblox.md`.

## Checklist before showing a model

- The silhouette reads at thumbnail size, and it is unmistakably THIS creature.
- Epic tier: brows, glowing eyes, open jaw with teeth, at least one of horns / crest / spikes on the head.
- Torso has more than one mass; belly or chest has contrast plates; shoulders and hips have some armour or bulk.
- Legs start INSIDE the torso and are narrower than it where they enter; feet stand on the ground (z = 0).
- Report: 0 FLOAT, 0 coplanar faces left, no colour over 20,000 triangles.
- The pose render shows no gaps opening at knees, neck or tail joints (blocks overlap across every joint).
- Bones: one chain per limb, neck, head, jaw and tail (see `references/style.md`), so it can be animated.
- No pupils, nothing held in hands, no accessory that does not define the creature.
- **Face test** on the head close-up from the FRONT: both eyes are visible (not hidden behind the snout or a
  brow), they look angry (inner ends of the brows lower), and NOTHING ELSE reads as eyes (nostrils, sockets).
- **Read test** on every view: nothing reads as something it isn't - a second face, letters or symbols (W, > <,
  check marks), glasses, a moustache, a hand of fingers, a hat, teeth where there are none. See
  `references/style.md` section 14: these are the mistakes that happen most.

## Studs on or off

Studs are the default. If the user wants the same model without studs, set `d.studs = False` in the file or pass
`--no-studs`: the preview renders smooth and the generated Roblox setup script is written with `STUDS = false`. In
Roblox the setup script uses the game's existing stud MaterialVariant if there is one (any variant with "stud" in its
name) and creates one if not; `references/roblox.md` explains both cases and how to upload your own stud textures
(`textures/stud_color.png`, `textures/stud_normal.png`).

## Files

- `scripts/studkit.py` - the block builder, checks, renders and FBX export.
- `scripts/blockkit.py` - ready parts: eyes, legs, paws, tubes, bat wings, serpent bodies.
- `scripts/build.py` - build + check + render + export in one command (options in its header).
- `scripts/stud_textures.py` - makes your own stud colour and normal maps.
- `references/style.md` - the style and the recipes for every body part. Read it.
- `references/api.md` - every function and its arguments.
- `references/roblox.md` - importing, the setup script, studs, animating, troubleshooting.
- `examples/` - 12 creatures with a three-quarter render (`<name>.jpg`) and a front close-up of the face
  (`<name>_head.jpg`): dragon, trex, cerberus, hydra, chimera, leviathan, titanoboa, kraken, megalodon, roc (epic),
  arctodus (normal), cow (simple).
