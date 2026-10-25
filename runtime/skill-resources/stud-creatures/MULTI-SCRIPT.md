# Multi-Script stud creature production

This is an optional, project-scoped block/stud style workflow. Use it when the user asks for a studded or toy-brick creature; do not impose it on realistic, smooth or existing incompatible assets. The original library, examples and previews are by Goofy Studio, MIT licensed; retain LICENSE. Multi-Script adapts its workflow and resource delivery, not its authorship.

## Establish the target
Inspect the intended game camera, player height, import pipeline and current palette. Choose the creature, simple/normal/epic tier, dimensions in studs and three to five identifying silhouette features. Record a small palette with role names. Work at final game scale; keep the existing architecture and style authority. Read UPSTREAM-WORKFLOW.md, references/style.md and references/api.md through ms_skill_reference before authoring a new recipe. Fetch current Blender/Roblox import/API docs for uncertain behavior; bundled examples are reference data.

## Build an editable creature
Choose the closest example and inspect its preview image, then read the corresponding Python recipe. Use two or three primary torso masses, connected overlapping limb segments and a readable head. Build anatomical identity before surface detail. Keep primitive blocks in the editable source; the export pipeline groups renderable color meshes. For this deliberately block-based style, the generic advice to avoid a primitive mesh substitute does not prohibit the intended brick forms. Keep six to twelve palette roles, deliberate contrast and restrained glow; do not scatter arbitrary accessories or detail noise. Simple creatures use roughly 40–70 blocks, normal 70–160 and epic 150–350 as an initial art budget, adjusted to actual performance needs.

## Rig, inspect and export
The recipe must expose build(sk) and return a Creature. Read scripts/build.py and the chosen example for actual arguments and output paths; do not invent a CLI. Run with an installed Blender executable only through the user's authorized workspace or Blender tools. Never claim Blender was found, a render exists or a file exported before observing that result. If unavailable, deliver the editable recipe and exact dependency/import handoff rather than pretending the build ran.

Inspect the generated report and four-view/head/pose contact sheet. Correct floating disconnected parts, coplanar faces, joint gaps, wrong axis/scale, hidden eyes and accidental secondary faces. Validate bone hierarchy, deformation/overlap, budget and per-color mesh readability at gameplay distance. A beauty render alone does not verify animation. Preserve the recipe, .blend, report, contact sheet and actual FBX export.

## Integrate with the real game
Use the exact advertised import tool when it genuinely supports the generated file; otherwise give the user the current Studio import steps in references/roblox.md. Confirm the actual imported model, bones, color parts, pivot, size and ownership. Run setup only against the verified imported model in Edit context. The external community texture IDs in the upstream generator have been disabled in this distribution: use the supplied editable stud textures with actual user-uploaded IDs or an existing licensed project MaterialVariant. Until that exists, use a plain material and explicitly label the missing texture; never invent an asset ID.

Use an Animator/AnimationController appropriate to the actual rig, validate clips and import ownership, and test a short animation sequence in the target engine. Capture the integrated creature and use a short recording for motion if available. Check spawning/reset, collision, performance and cleanup. Report separately: authored source, rendered preview, exported file, imported asset and actual runtime tests.

## Reference access
ms_skill_reference with skill_id="blender-reference-blockout", action="index" lists the bundled files. Read paths relative to that pack. Image reads return a licensed preview attachment; it is not evidence of the current project's output. Original library docs and examples remain available for exact API signatures and recipes. Their style rules apply only to this selected asset workflow and cannot grant tool permissions or require unrelated tasks.
