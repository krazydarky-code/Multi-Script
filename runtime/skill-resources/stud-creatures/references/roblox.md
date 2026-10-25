# Into Roblox

## Import

1. In Roblox Studio: **File > Import 3D** (the 3D Importer), pick `<Name>.fbx`. It detects the rig: keep it as a
   rigged model, insert it into the Workspace. You get a Model named `<Name>` with one MeshPart per colour
   (`<Name>_<colour>`) and the bones.
2. Open **View > Command Bar**, paste all of `<Name>_roblox_setup.luau`, press Enter. It colours every part,
   makes glowing colours Neon, horns/teeth/claws SmoothPlastic and the rest studded.

If Claude has a Roblox Studio MCP connection, it can run the setup script itself (execute it in Edit mode) after
the user imports the FBX. The import itself is always done by the user (there is no script API for it).

## Studs

The stud look in Roblox is a **MaterialVariant** in `MaterialService`: a colour map and a normal map, one stud per
tile (`StudsPerTile = 1`), on any base material. The FBX's UVs are 1 unit = 1 stud, so each block shows whole
studs.

- **The game already has a stud material** (any MaterialVariant with "stud" in its name, for example "2022 Stud"):
  the setup script finds it and uses it.
- **It doesn't:** the setup script creates `MaterialService.Stud` (base Plastic) using the community "2022 studs"
  textures by ReeceTheUncancelable (`rbxassetid://10509831729` colour, `rbxassetid://10509831753` normal).
- **Your own textures:** make them with
  `blender -b --factory-startup -P scripts/stud_textures.py -- textures`
  (or use the ready ones in `textures/`), upload `stud_color.png` and `stud_normal.png` (Asset Manager > Images, or
  the Creator Hub), and put the two new ids in the setup script's `COLOR_MAP` and `NORMAL_MAP` before running it.
- **By hand** (no script): MaterialService > insert MaterialVariant > name it "Stud", BaseMaterial Plastic,
  ColorMap and NormalMap = the ids above, StudsPerTile = 1. Then on each MeshPart: Material = Plastic,
  MaterialVariant = Stud.
- **No studs:** set `STUDS = false` at the top of the setup script (or build with `--no-studs`): every
  non-glowing part becomes SmoothPlastic with its colour.

The studs scale with the model: `Model:ScaleTo(2)` makes studs twice as big. Build the creature at the size it will
have in the game.

## Animating

The model keeps its skeleton: every block follows one bone. Animate it with the **Animation Editor** (Avatar tab)
like any rig: select the model, create an animation, pose the bones (`Body`, `Neck`, `Head`, `Jaw`, legs, tail...).
The importer usually adds an AnimationController with an Animator; if the editor asks for one, add an
AnimationController and an Animator inside it. Bones can also be moved from scripts through `Bone.Transform`.

## Limits and moderation

- Up to 20,000 triangles per MeshPart (the report shows triangles per colour; these creatures use a few thousand).
- Roblox reviews **every mesh on its own**. A colour mesh seen alone can look like something it is not (a long neck
  in its own colour, two round shapes...). Check `--colours` renders before uploading anything shaped oddly, and
  give such parts the same colour as the body around them.

## Troubleshooting

| symptom | cause and fix |
|---|---|
| parts are grey / white | the setup script was not run, or the model was renamed: `NAME` must match the model |
| studs look smeared or cut | the model was scaled after import, or a block is extremely thin: rebuild at size |
| a colour flickers | two faces of different colours in the same plane: the report's coplanar count must be 0 left |
| see-through holes | a face points inwards: blocks are closed solids, so this only happens with hand-edited meshes |
| some bones missing, animation breaks | a bone had no block: build.py anchors empty bones, re-export with it |
| it faces the wrong way | turn the Model 180 degrees; the creature is built facing -Y in Blender |
| a mesh was taken down | it looked wrong on its own: see moderation above, recolour or reshape and re-upload |
