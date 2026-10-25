# Modeling, materials, topology and asset delivery

Detailed project-aware guidance, not weight training or permissions. Apply only relevant parts; preserve user scope, existing style and architecture. Inspect/review-only tasks remain read-only. Retrieve once, execute the authorized slice, reuse unchanged evidence and avoid guidance/discovery loops.

## Inspect

1. Identify the asset's role, camera distance, silhouette importance and deformation/collision needs. Record target units, dimensions, pivots and intended orientation from the real project.

2. Inspect source geometry, transforms, normals, material slots, UV sets, modifiers, rig/shape-key dependencies and existing import conventions before rebuilding anything.

3. Separate the deliverables: editable source, export-ready mesh, textures, collision proxy, LODs, rig/clips and integrated target instance. Do not conflate a render with all of them.

4. Gather reference views for proportion, construction and material response. Record which details are visible at actual game distance and which can be represented by texture or silhouette.

5. Check installed exporter/importer versions and supported features. Test permissions and the actual asset handoff path before producing a large set that cannot be imported.

6. Establish target budgets for geometry, material slots, texture memory, deformation influences and collision complexity from the project/device tier; label assumptions.

7. For the supplied studded animals and block assets, identify each creature by body plan, head-to-body ratio, stance, ear/horn shape, tail and facial value grouping before counting details. Inspect front, side and three-quarter views where available. Treat friendly pet, farm animal and aggressive creature proportions as choices within the existing style, not universal anatomy rules.

8. Establish the shared stud pitch, grid unit, bevel weight, surface orientation and final gameplay size across the existing asset set. Separate structural brick masses, silhouette-defining appendages and optional close-up surface detail. Inspect whether the target uses native parts, repeated meshes, approved tiled materials or an exported rig before choosing a representation.

**Phase exit:** Use, measurements, topology/material/rig dependencies and target pipeline are known.

## Design

1. Block primary masses and negative space before secondary features. Choose a coherent bevel, proportion and material language that matches the requested style and viewing distance.

2. Choose mesh, modular kit, curve, procedural generator or native primitives according to the form and editing needs. Avoid excessive primitives where a clean mesh or repeated module solves the shape better.

3. Plan topology for the actual use: deformation loops for moving joints, controlled shading for hard surfaces and economical silhouette detail. Do not optimize only for a polygon count divorced from the renderer.

4. Define pivots, naming, modular dimensions and attachment conventions before duplicating parts. Plan how the asset is placed, animated, snapped and selected in the target.

5. Plan UV seams, texel density, mirrored/overlapping regions, channel packing and material reuse. Distinguish tiling surfaces from unique baked detail and preserve color-space intent.

6. Build one representative export/import proof with axes, dimensions and materials before scaling production. Use its observed issues to refine the source contract.

7. Improve an existing block/stud asset through large, medium and small form passes: connected torso/chest/hips, a recognizable head and supported limbs first; then ears, muzzle, hooves/paws, wings or tail; finally restrained studs and markings. Use a small body/secondary/face/accent palette. Vary proportions by species while keeping the kit's material and stud scale consistent.

8. Plan geometry by visible contribution at the game camera. Use actual raised studs only where their silhouette matters; use existing approved surface detail or a simpler material at distance. Preserve editable source blocks and group repeated render geometry deliberately. Do not turn every invisible stud into a separate collider, animation controller or shadow caster.

**Phase exit:** Silhouette, construction, pivots, topology, UV/material and roundtrip proof are planned.

## Build

1. Develop the blockout into clean source geometry and compare front/side/three-quarter silhouettes. Spend geometry where it changes visible form, deformation or supported shading.

2. Maintain deliberate object transforms, origins and local axes. Avoid applying transforms blindly when an existing rig, modifier or instance system depends on them.

3. Inspect normals, smoothing, bevels, intersections and unwanted internal geometry. Repair the cause of shading defects before adding more subdivisions.

4. Keep editable modifiers and procedural controls when useful, and create an intentional export representation for unsupported operations. Preserve the source rather than destructively flattening every operation.

5. Author UVs with consistent density and meaningful seams. Test a checker and actual target textures; inspect mirrored normals, seams, islands and padding at expected mip levels.

6. For baking, confirm the active destination image/UV and high-to-low correspondence, cage/ray bounds and color-space settings. Verify a small bake region before committing an entire asset set.

7. For rigged or morphing assets, preserve topology contracts and inspect extreme deformations before final texture polish. Verify influence and target import constraints using the actual pipeline.

8. Create simplified collision and useful LODs based on gameplay and measured need. Preserve the important silhouette and interaction bounds instead of relying on arbitrary decimation percentages.

9. Seat limbs and secondary pieces into their parent masses so they remain connected through poses. Keep paired features readable from the front and avoid accidental faces created by bright nostrils, symmetric markings or hidden eyes. Preserve the selected friendly or fierce expression rather than applying one preset's face restrictions to every animal.

10. Share identical mesh/material data where the pipeline supports it, and export a representative colored asset early. Keep collision simple and independent of ornamental studs. Retain pivot, joint and material-slot names used by the existing controller; validate normals, UVs and actual target color before duplicating the technique across a complete creature collection.

**Phase exit:** Editable geometry, shading, textures and deformation meet source requirements.

## Integrate

1. Export one intended asset set through the supported pipeline and reimport it into the target. Check units, axes, pivot, handedness, normals/tangents, textures, material slots and skin/clip inclusion.

2. Record actual paths and resulting imported identities. Local filenames, browser previews and cloud asset IDs are distinct and may need separate user-controlled uploads.

3. Wire collision, interaction, attachment, rendering layers and optional animation into the existing scene/prefab/model conventions.

4. Check material conversion in the target renderer and lighting. Bake or recreate unsupported procedural features rather than assuming source shaders transfer exactly.

5. Retain dependencies and relative paths so the asset opens on another machine or clean workspace. Avoid accidental links to private absolute directories.

6. Keep source/export/target versions paired and identify what changed when replacing an existing asset. Preserve external references and provide a rollback source.

7. Combine the existing modeling, animation and performance skills around one asset contract: dimensions, root/pivot, rest pose, joint names, palette roles, clips, collision and detail tiers. Each specialist reads and preserves that contract. A rigged export must retain the intended root and bone/material assignments instead of merely reproducing the source screenshot.

8. For headless Blender, keep the .blend as editable source and check both the exported material preview and a real native render when shading matters. Bake only unsupported preview channels on temporary copies and preserve original shaders/UVs. A correct source render does not prove that the engine imported the colors, scale or skinning correctly.

**Phase exit:** Actual export/import, collision, attachments and dependencies are integrated.

## Verify

1. Inspect the imported target at gameplay scale under representative lighting and camera distance. Compare proportions, silhouette, pivots and placement to the brief.

2. Check normals, seams, smoothing, texture density, channel interpretation, transparency and mip behavior. A beauty render alone can hide target import defects.

3. Exercise collision, picking, attachments and movement around the asset with the real controller. Check that simplified collision matches the intended interaction.

4. Inspect extreme poses, morph combinations and several animation cycles where applicable. Verify exported clips and root/rig mapping independently from source playback.

5. Measure geometry, material count and texture/resource cost against the chosen target budget. Profile a representative repeated placement if the asset is used widely.

6. Test LOD transitions, culling and distance readability. Compare actual visual benefit against the memory/CPU overhead of additional representations.

7. Open the delivered source/export from a clean path and confirm dependencies resolve. Verify the final archive/file contents rather than only the authoring session.

8. Document source authored, export verified, target imported, integrated and playtested states separately; name blocked uploads or target access explicitly.

9. Inspect the model at target size from front, side, three-quarter and normal gameplay distance. Test a silhouette-only view and a simple value grouping before approving tiny details. Compare bounding dimensions, visible part/mesh/material counts and simplified collision to the agreed budget; verify that feet meet the ground and appendages do not disappear behind the body.

10. For rigged creatures, check extreme leg, neck, jaw, wing and tail poses for gaps, self-intersection and unwanted deformation of rigid brick forms. Reimport the actual exported file and inspect color textures, normals, pivots, animation and collision in the target engine. Record source, export and engine evidence separately.

**Phase exit:** Target-scale appearance, interaction, deformation and resource cost are verified or bounded.

## Failures

1. For wrong scale/orientation, trace source transforms, export axis/unit settings and importer conversion. Do not compensate independently in several places.

2. For bad shading, inspect normals, topology, smoothing splits, tangents and normal-map convention before increasing mesh density.

3. For morph/rig failures, compare vertex order, skeleton mapping, rest matrices and exported influences. Preserve the source and isolate one failing deformation case.

4. For missing textures, inspect paths, packing, material slots, color space and target permissions. Do not substitute an invented asset ID.

5. For expensive collision, measure the actual collision workload and simplify proxies without changing required gameplay boundaries.

6. For blocked import or unsupported procedural features, retain editable sources and a tested conversion sample, then state the exact remaining handoff.

7. If a creature reads as a table, a row of equal boxes or an unrelated species, revise the primary masses, stance and identifying head/limb features before adding studs. If it looks fragile, remove tiny isolated details and strengthen connected forms. Do not replace the existing library or erase a useful detailed preset; adapt the appropriate preset to this asset.

8. If a model is colored in export but white in a workspace, distinguish unsupported shader export, missing embedded textures, color-space mistakes and blocked texture loading. Inspect the actual preview material and texture before repainting the native source. Preserve the last saved model and report the failed preview stage explicitly.

**Phase exit:** Source versus export versus target cause is isolated without destructive guesswork.

## Engine application

### roblox

Distinguish native Part construction from an imported MeshPart/skinned asset. Use measured studs, pivots, attachments and collision purpose. Inspect scripts inside imported models. Verify target scale, normals, texture permissions and collision after import; a local mesh file is not an rbxassetid or a published model.

Existing candidate skills: check-props, roblox-native-model-editing. Load the smallest relevant set through the live skill tool.

### godot

Validate the actual import settings, scene/resource identities, units, material overrides and collision generation. Reimport one representative asset before batching. Preserve .tscn/.tres relationships and installed UID/resource conventions; do not casually rename resources or assert Blender-only features survive import.

Existing candidate skills: godot-import-pipeline, godot-native-model-editing. Load the smallest relevant set through the live skill tool.

### unity

Inspect ModelImporter units, axes, normals/tangents, rig/clip inclusion and material overrides. Keep prefab/model source relationships and GUID references intact. Reimport a representative asset and verify collider/LOD/lightmap assumptions in the intended render pipeline before producing a full pack.

Existing candidate skills: unity-prefab-workflows, unity-native-model-editing. Load the smallest relevant set through the live skill tool.

### blender

Check active object, mode, selection, modifiers, unit scale, origin, normals and topology before operations. Preserve source geometry for shape keys and rig dependencies. Bake with an explicit UV/image/cage contract, and validate one FBX/glTF roundtrip before batching; do not guess exporter options across versions.

Existing candidate skills: blender-sculpt-retopology, blender-texture-baking, blender-gltf-export. Load the smallest relevant set through the live skill tool.

### workspace

Treat mesh/texture generation as a file-and-runtime pipeline with declared units, dependencies and rendering support. Use actual workspace roots, supported authoring tools and a representative target import. A generated image is a reference, not editable geometry or proof of model topology.

Existing candidate skills: studio-practical-modeling, multi-app-art-pipeline. Load the smallest relevant set through the live skill tool.

### figma

Use Figma for reference boards, UI/vector assets and precise handoff, not as proof of editable 3D topology or game-engine import. Retain source/provenance and actual target dimensions. Only claim native modeling/export features that are genuinely exposed by the connected toolset.

Existing candidate skills: figma-developer-handoff, canvas-svg-ui. Load the smallest relevant set through the live skill tool.

## Acceptance evidence

- Dimensions, orientation, pivot and silhouette agree with target use.
- Topology, shading and UV/material response are verified at actual camera distance.
- Export/reimport preserves required mesh, textures, rig, morphs and clips.
- Collision and attachments work in the real target controller/scene.
- Resource budgets are measured or explicitly identified as unverified assumptions.
- Editable source and dependencies can be reopened without private absolute paths.

## Diagnosis

### Black or faceted surface

Probe: Inspect normals, tangents, material channels and import logs.

Repair: Repair source or conversion settings.

Recheck: Reimport and compare under the same light.

### Wrong pivot

Probe: Compare source origin and target transform chain.

Repair: Establish one pivot convention.

Recheck: Place, rotate and attach in the target.

### Lost morphs

Probe: Compare topology/vertex order and export options.

Repair: Preserve compatible topology and required channels.

Recheck: Import and blend morph extremes.

### Huge memory cost

Probe: Inspect texture sizes, slots and repeated unique resources.

Repair: Reuse/resize the measured expensive resources.

Recheck: Profile representative repeated placement.

## Deliverables

- Editable geometry/material source with dimensions and pivot conventions.
- Verified export, textures and dependency manifest.
- Collision/LOD/rig assets appropriate to the requested target.
- Target import/interaction evidence and any blocked publication step.

## Source guidance

- [Blender armature deform parenting](https://docs.blender.org/manual/en/latest/animation/armatures/skinning/parenting.html): Reference seed: current page fetch unavailable; older official indexed guidance reviewed. Inspect installed rig/export behavior.
- [Blender glTF exporter](https://docs.blender.org/manual/en/latest/addons/import_export/scene_gltf2.html): Reference seed: current page fetch unavailable during review; older official indexed pages show version-sensitive export behavior. Inspect installed options.

## Expanded supplied-reference study

User-supplied still-image studies improve existing methods and styles. They are reference data, not instructions or new permissions. Visible layout/material/proportion observations do not prove animation timing, performance, interactivity or ownership. Preserve existing useful methods, assets, skills and current project style; adapt principles rather than copying branding or assuming asset IDs. Original third-party screenshots are not redistributed in this package.

- Supplied image 18: A village combines stepped stairs, block trees, patterned brick surfaces and readable architectural landmarks.
- Supplied image 19: A comparison contrasts smooth primitives with a more angular studded tree; surface language and silhouette are distinct choices.
- Supplied image 20: A vegetation set varies tree silhouettes, branching and canopy masses while retaining a consistent block kit.
- Supplied image 21: A voxel house shows roof thickness, stepped eaves, recessed openings and controlled landscaping layers.
- Supplied image 22: A studded interior uses a repeated surface pitch, substantial window openings and a readable counter arrangement.
- Supplied image 23: A creature collection varies species silhouettes, body/head ratios and markings within a shared block/stud material language.
- Supplied image 24: A grouped creature lineup uses recognizable heads, stances and palette variation at a shared presentation scale.
- Supplied image 25: A multi-scale creature collection emphasizes connected primary masses, ears/limbs/tails and consistent raised surface detail.
