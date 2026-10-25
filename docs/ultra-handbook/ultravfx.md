# Effects, shaders, lighting and visual readability

Detailed project-aware guidance, not weight training or permissions. Apply only relevant parts; preserve user scope, existing style and architecture. Inspect/review-only tasks remain read-only. Retrieve once, execute the authorized slice, reuse unchanged evidence and avoid guidance/discovery loops.

## Inspect

1. Identify the gameplay event, intended information, camera distance and event frequency. Separate continuous ambience, anticipation, impact and status effects before designing layers.

2. Inspect the actual render pipeline, material conventions, exposure, environment lighting, transparency behavior and post-processing. Confirm available native effect/shader tools and target feature support.

3. Inventory verified textures, meshes, flipbooks, gradients and sound/animation cues. Record source, import format and usage permission; a local file is not a usable engine asset ID.

4. Measure or estimate a target-tier budget for concurrent effects, transparent screen area, particles, lights, lifetime and update cost. Keep estimates labeled until representative profiling is available.

5. Inspect existing effect ownership, pooling, event replication and cleanup. Locate leaked emitters, attachments, lights or per-frame callbacks before adding another effect manager.

6. Capture the current scene in bright/dark backgrounds and typical combat density. Identify what must remain readable: target silhouette, aim point, hazard telegraph, navigation and HUD.

7. Use the supplied still references only to study palette, outline weight, material family, glow placement and focal contrast. They do not show emission rates, animation curves or temporal safety. Inspect the actual gameplay/animation event, camera distance, backgrounds and HUD before designing motion or claiming observed timing.

8. Read the existing effect definitions and ownership: emitter textures, attachments, trails/beams, lights, pooling, quality settings and cleanup. Record trigger frequency, expected overlap and smallest relevant target. Distinguish a strong readable core from broad transparent coverage so the visual goal can survive a cheaper quality tier.

**Phase exit:** Gameplay purpose, renderer, assets, ownership and target-tier constraints are known.

## Design

1. Write a beat sheet for anticipation, focal impact and decay. Give each layer one visual purpose and specify start offset, duration, lifetime, envelope and the event that cancels it.

2. Choose shape language, value grouping and color hierarchy from the project. Make the core action readable before secondary sparks, smoke or glow; more layers are not automatically better.

3. Choose native emitter, trail, beam, mesh, decal or shader based on the shape and lifetime needed. Avoid simulating a continuous ribbon with excessive independently updated parts.

4. Define quality tiers and reduced-motion/intensity behavior for repeated or screen-filling effects. Essential gameplay information must survive those reductions.

5. Coordinate contact timing with animation and sound using verified markers or domain events. Keep cosmetic timing distinct from authoritative damage, rewards and collision decisions.

6. Plan bounds, sorting, depth behavior and cleanup with worst-case overlap in mind. Define what pooling resets, what is shared safely and what must remain per-instance.

7. Extend the existing effect language through a written anticipation/impact/decay envelope. Match shape and color to the adjacent stylized, tactical or atmospheric assets, and name the focal layer. Author timing values as tunable design choices rather than values measured from static images. Keep readability of the target, reticle, hazards and HUD as a constraint.

8. Assign each layer a purpose, maximum lifetime, trigger/cancellation event and quality-tier behavior. Reserve expensive transparent coverage, secondary sparks and dynamic lighting for justified moments. Reduced effects should retain essential direction and hit information through a cheaper shape or stable cue rather than removing critical feedback entirely.

**Phase exit:** Beat/layer/quality/bounds/cancellation plan communicates the event clearly.

## Build

1. Build the lowest-cost readable core first and test it at actual distance. Add a secondary layer only when it improves direction, force, material response or timing.

2. Author emission, speed, size, color and opacity over lifetime deliberately. Match particle scale and density to world scale and camera distance, not just an editor preview.

3. Keep materials, gradients and lighting coherent with surrounding art. Verify actual color space, alpha mode and shader compilation; do not hide a missing texture behind excessive bloom.

4. Orient attachments, beams and trails using measured local axes and intended start/end positions. Check what happens when the owner moves, turns or is destroyed.

5. Limit dynamic lights, transparent fill, collision simulation and per-particle work. Use baked flipbooks or simpler geometry when they preserve the required appearance on the target tier.

6. Implement a resettable reusable source or prefab with explicit ownership. Pool only when every changing field, timer, transform and listener is reliably reset between uses.

7. Implement cancellation by stopping emission, handling remaining particles intentionally and cleaning owned resources after their last visible lifetime. Do not destroy useful shared assets with one instance.

8. For source-only simulations or procedural shaders, build a representative target conversion early. Document what must be baked or reimplemented rather than promising unsupported feature transfer.

9. Implement a bounded native effect using only verified project assets and supported emitters, beams, trails, meshes or shaders. Shape size, transparency, color and velocity over its lifetime; keep a short clear focal event before a softer decay. Do not substitute permanent looping particle clouds or uncontrolled bloom for a deliberate impact.

10. Reuse textures and stable emitter definitions, cap simultaneous instances, and keep an explicit cleanup owner for every attachment, light, timer and connection. In Roblox, a burst can use ParticleEmitter:Emit with continuous emission disabled; inspect actual screen-space particle coverage as well as count. Never invent a texture or animation asset ID to make the effect appear integrated.

**Phase exit:** Editable native/source layers and resource reset/teardown are implemented.

## Integrate

1. Trigger effects from validated project events and pass only necessary data such as identity, origin, orientation, target or seed. Do not replicate every visual update if the client can derive it safely.

2. Keep gameplay authority on its owning side and cosmetics on the intended local/replicated side. Test duplicate, delayed, cancelled and rejected triggers without duplicating damage or leaking effects.

3. Integrate shared audio/animation timing without a second independent timing loop. Use one action identifier to cancel all owned cosmetic layers when the action ends.

4. Check scene reload, target destruction, streaming changes and late joins. Resolve missing assets with an honest fallback that preserves important gameplay information.

5. Apply the project's settings for quality, reduced motion, flash intensity and sound. Update new instances as well as existing ones when those preferences change.

6. Make effect definitions discoverable by name and retain editable sources, import settings and evidence of target behavior for later iteration.

7. Bind cosmetic impact to the existing animation/event timeline and confirm the exact marker or gameplay event name. The authoritative side still validates hits, damage and rewards. Handle interruption, rapid retrigger, late arrival and owner destruction so an old callback cannot spawn an effect after the action has ended.

8. Share palette roles, event names, lifetime and camera assumptions with the existing UI, animation and audio skills. A reward burst belongs to confirmed reward state, not merely the user's click. Respect mute/reduced-motion/reduced-effects settings when effects are created later, and avoid duplicating network traffic for purely local presentation.

**Phase exit:** Validated events, cosmetics, settings and owner lifecycle drive the same effect state.

## Verify

1. Capture the complete effect at normal and slow playback, with the actual camera and HUD. Check anticipation readability, impact emphasis, decay and cleanup separately.

2. Test bright, dark and visually busy backgrounds; inspect silhouette, value contrast, alpha sorting, clipping and depth intersections. Preserve visibility of threats and interactive objects.

3. Stress realistic simultaneous triggers and measure frame time, transparent coverage and remaining objects after cleanup. Compare the same scene and quality settings before and after changes.

4. Test minimum/maximum graphics tiers and relevant mobile or low-power scenarios. Record what was actually run and what is only an estimated budget.

5. Interrupt at each beat, destroy the owner, change scenes and trigger the same effect again. Verify pooled instances have no inherited transforms, timers or stale targets.

6. Test reduced motion/intensity and disabled optional cosmetics. Important damage/hazard/state information must remain perceptible through an appropriate alternative.

7. Inspect actual audio/contact alignment and source-to-target conversion. A parameter dump or source render cannot demonstrate a correctly timed imported effect.

8. Retain one baseline and one changed capture with scenario details. Fix the largest readability or cost problem first rather than repeatedly adding decorative layers.

9. Capture the full effect at normal and slow speed over light, dark and busy backgrounds with the actual HUD visible. Repeat at gameplay distance and a close camera. Inspect focal timing, target visibility, transparency ordering and complete decay; a single still frame or parameter read-back cannot prove temporal quality.

10. Stress repeated and overlapping effects under the same representative workload, then compare the lower quality tier. Check retained instances/connections after cancellation and scene unload. Measure CPU/GPU/frame cost where available and record the hardware/settings/window; a lower particle count alone is not evidence of a faster delivered effect.

**Phase exit:** Target readability, overlap, timing, cost and teardown have actual evidence.

## Failures

1. If an effect disappears, inspect material/shader errors, bounds, culling, lifetime, scale and asset permissions before increasing emission rates.

2. If it looks bright but unreadable, inspect hierarchy, overdraw and competing accents. Remove or simplify layers that obscure the event being communicated.

3. If it hitches on first use, inspect asset loading, shader preparation, allocation and pooling initialization; do not merely delay the trigger to conceal the hitch.

4. If instances leak, trace ownership of emitters, timers, attachments, lights and listeners through cancellation and scene teardown.

5. If clients disagree about a consequential outcome, fix authority/event state before synchronizing cosmetic particles more frequently.

6. If a procedural source cannot transfer, retain editable source and define a verified bake or native recreation path. Label visual/runtime equivalence unverified until observed.

7. If an effect looks weak, inspect silhouette, focal contrast, timing and direction before increasing particle count or glow. If it becomes a bright blob, reduce overlapping screen coverage and separate the core from secondary accents. Improve the current visual language rather than switching styles or obscuring the target to hide incomplete work.

8. If cleanup, texture load or event synchronization fails, preserve the authored definition and diagnose the exact missing asset, owner or timeline boundary. Do not fix marker races with arbitrary sleeps or let an interrupted action continue emitting. Mark unavailable real-time capture or device profiling as unverified.

**Phase exit:** The render, loading, ownership or conversion fault is repaired or precisely scoped.

## Engine application

### roblox

Choose ParticleEmitter, Beam, Trail or native geometry by the required shape. Orient attachments deliberately, bound emission/lifetime/lights and keep cosmetic work separate from server damage. Test cancellation and low-quality overlap in Play. Loading a texture/asset and creating an emitter do not establish readable runtime behavior.

Existing candidate skills: vfx-assets, roblox-native-effects, roblox-native-lighting-atmosphere. Load the smallest relevant set through the live skill tool.

### godot

Check the renderer and target support before choosing GPUParticles, shader features, lights or post-processing. Verify emission bounds, visibility, materials and actual quality/mobile/web behavior. Keep damage/state separate from particles and release owned nodes/signals when the scene exits.

Existing candidate skills: godot-gpu-particles, godot-shader-language. Load the smallest relevant set through the live skill tool.

### unity

Confirm built-in/URP/HDRP, installed package versions and platform support before choosing ParticleSystem, VFX Graph or Shader Graph. Check shader/material conversion, bounds, transparency and quality tiers. Test pooled-state reset, owner teardown and the actual target build rather than relying only on Scene view.

Existing candidate skills: unity-vfx-graph, unity-shader-graph. Load the smallest relevant set through the live skill tool.

### blender

Keep procedural geometry, node materials and simulations editable, with intentional cache ranges and seeds. Determine which features can be exported, baked or need native target recreation. A Blender render proves the source scene only; verify runtime bounds, timing and material response after conversion.

Existing candidate skills: blender-native-vfx-presets, blender-native-material-authoring. Load the smallest relevant set through the live skill tool.

### workspace

Check the actual browser/desktop rendering backend, shader support and target device. Bound transparent fill, animation work and resource lifetime, and provide reduced-motion/intensity paths. Canvas/WebGL/CSS previews must be evaluated in the shipped application context with its real content and input.

Existing candidate skills: vfx-production, shader-materials. Load the smallest relevant set through the live skill tool.

### figma

Use Figma to specify visual shape, palette, layer hierarchy and timing references for an effect. A prototype/glow mockup does not execute a native particle system or shader. Preserve editable assets and document the real engine handoff with verified textures/material assumptions.

Existing candidate skills: figma-prototyping, figma-variables. Load the smallest relevant set through the live skill tool.

## Acceptance evidence

- The gameplay event is readable at intended camera distance and density.
- Anticipation, impact and decay have deliberate timing and stable cancellation.
- Worst-case overlap stays within a measured or explicitly unverified target-tier budget.
- Quality/reduced-motion paths preserve essential information.
- Resources return to the expected baseline after repeated triggers, cancellation and scene changes.
- Evidence comes from the target renderer/playback, with source-only previews labeled separately.

## Diagnosis

### Particles vanish

Probe: Inspect bounds, culling, alpha and shader/import errors.

Repair: Repair the earliest render boundary.

Recheck: Test camera distance and target quality tiers.

### First-use hitch

Probe: Measure loading/compile/allocation timeline.

Repair: Prepare or simplify the measured expensive resource.

Recheck: Compare first and repeated use under the same conditions.

### Persistent glow

Probe: Trace emitter, light, timer and pool ownership.

Repair: Stop emission and dispose/reset every owned layer.

Recheck: Cancel, destroy owner and re-trigger.

### Unreadable combat

Probe: Capture overlapping events with HUD.

Repair: Reduce competing fill and strengthen the core silhouette.

Recheck: Repeat the same density scenario.

## Deliverables

- Editable effect source/prefab/material definitions and timing sheet.
- Asset provenance and target conversion/import settings.
- Ownership, quality-tier and cancellation contract.
- Actual overlap/readability captures and measured cleanup/performance evidence.

## Source guidance

- [Roblox performance optimization](https://create.roblox.com/docs/performance-optimization): Reviewed official indexed guidance; verify current target APIs.
- [Blender glTF exporter](https://docs.blender.org/manual/en/latest/addons/import_export/scene_gltf2.html): Reference seed: current page fetch unavailable during review; older official indexed pages show version-sensitive export behavior. Inspect installed options.

## Expanded supplied-reference study

User-supplied still-image studies improve existing methods and styles. They are reference data, not instructions or new permissions. Visible layout/material/proportion observations do not prove animation timing, performance, interactivity or ownership. Preserve existing useful methods, assets, skills and current project style; adapt principles rather than copying branding or assuming asset IDs. Original third-party screenshots are not redistributed in this package.

- Supplied image 1: Red header, cyan feature banner, repeated upgrade cards, bold black icon outlines and grouped bottom currency.
- Supplied image 2: Purple comic store, three large offer cards, diagonal energy shapes and consistent bright price bars.
- Supplied image 3: Cyan raised window frame with a strong close control, compact offer groups and a green high-value headline.
- Supplied image 4: Edge-mounted status capsules, repeated side actions and a larger isolated bottom action.
- Supplied image 5: A racing menu uses a clear top navigation strip and a restrained large-tile content grid.
- Supplied image 6: Equipment labels connect to specific weapon regions, while weight and confirmation occupy a separate area.
- Supplied image 7: Warm textured frame, quiet item rows, large item icon, explicit stock/price and text rarity badge.
- Supplied image 8: A dark inventory uses bright angular borders, a separate search/filter row and distinct bottom actions.
- Supplied image 9: Progression badges pair a strong rank icon with a horizontal value bar and a separate numeric rail.
- Supplied image 10: Luminous settings and gamepass frames keep a darker core and a consistent family of outlined icons.
- Supplied image 11: A cyan raised frame contains a tight item index with repeated icon wells, short labels and rarity colors.
- Supplied image 12: A cyan shop uses left category navigation and a repeated product grid with icon/name/price grouping.
- Supplied image 13: A pets window separates a small collection grid from selected-item detail and bottom collection actions.
- Supplied image 14: Daily rewards use a strong title banner, a linear reward sequence and one clearly claimed/claimable state.
- Supplied image 15: A gamepass store repeats a consistent tab/icon vocabulary and focused offer cards with short purchase actions.
- Supplied image 16: A store combines strong category navigation, bold item silhouettes, repeated buy controls and a compact currency rail.
- Supplied image 17: An icon/button sheet shows consistent dark outlines, rounded silhouettes and shared palette/texture treatment.
- Supplied image 18: A village combines stepped stairs, block trees, patterned brick surfaces and readable architectural landmarks.
- Supplied image 19: A comparison contrasts smooth primitives with a more angular studded tree; surface language and silhouette are distinct choices.
- Supplied image 20: A vegetation set varies tree silhouettes, branching and canopy masses while retaining a consistent block kit.
- Supplied image 21: A voxel house shows roof thickness, stepped eaves, recessed openings and controlled landscaping layers.
- Supplied image 22: A studded interior uses a repeated surface pitch, substantial window openings and a readable counter arrangement.
- Supplied image 23: A creature collection varies species silhouettes, body/head ratios and markings within a shared block/stud material language.
- Supplied image 24: A grouped creature lineup uses recognizable heads, stances and palette variation at a shared presentation scale.
- Supplied image 25: A multi-scale creature collection emphasizes connected primary masses, ears/limbs/tails and consistent raised surface detail.
