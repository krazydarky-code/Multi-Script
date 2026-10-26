# Motion design, rigs, deformation and playback

Detailed project-aware guidance, not weight training or permissions. Apply only relevant parts; preserve user scope, existing style and architecture. Inspect/review-only tasks remain read-only. Retrieve once, execute the authorized slice, reuse unchanged evidence and avoid guidance/discovery loops.

## Inspect

1. Identify the actual rig variant, skeleton hierarchy, bone/joint names, parent spaces and rest pose. Record scale, forward/up axes and whether the mesh is skinned, rigidly jointed or driven by shape keys.

2. Inspect existing actions/clips, frame rate, ranges, loop intent, root-motion policy, layers, masks and controller parameters. Find the authoritative owner of position and avoid adding a second motion controller.

3. Measure representative proportions and extreme poses. Check weights, joint limits, transforms, constraints and topology around shoulders, hips, elbows, knees, hands and facial features before writing rig automation.

4. Read import/export options and installed animation tooling. Establish which constraints, curve channels, shape keys, action slots and event markers survive the actual target pipeline.

5. Map gameplay timing: anticipation, active window, contact, recovery, cancel windows and any authority-sensitive hit event. Separate visual pose timing from server decisions.

6. Gather relevant motion references at the intended camera angle and speed. Record observed contacts, weight shifts and action beats; a generic walk-cycle tutorial is not a specification for every creature.

7. For the supplied block/stud creature and equipment references, infer only visible proportions, articulated regions and silhouette constraints. Static pictures do not establish a gait, clip length or transition. Inspect the real rig, joint axes, support contacts, controller, asset ownership and existing motion language before choosing how the character should move.

8. Identify the parts intended to remain rigid: brick body pieces, paws/hooves, jaw, ears, wings and tail segments. Determine which pieces are skinned, bone-parented or joint-driven in the target pipeline. Preserve useful existing clips, named markers and controller paths instead of rebuilding the rig merely to match a still image.

**Phase exit:** Rig, rest spaces, weights, clips, controller and export constraints are measured.

## Design

1. Define a pose/timing sheet with readable key poses, support contacts, center-of-mass shifts and intended emotional or gameplay purpose. Solve the action's silhouette before adding secondary motion.

2. Choose in-place versus root motion explicitly, including how navigation, collision and networking interact with it. Decide how the character returns to a neutral state after interruption.

3. Specify a small state graph, allowed transitions, priorities and layer masks. Identify which clips blend naturally and which need a deliberate transition pose rather than a long indiscriminate cross-fade.

4. Choose loop boundaries using matched pose and velocity, not only equal first/last transforms. Preserve foot/hand contacts and plan how speed changes affect stride and playback rate.

5. Define where secondary motion, facial shapes and props are authored and who owns their cleanup. Keep gameplay readability and camera distance ahead of extra keys or simulated detail.

6. Set deliverables for editable source, exported clip, target controller wiring and observed runtime playback. Publishing/ownership permissions are separate from the ability to author a local clip.

7. Extend the current pose language with an action sheet: intention, support, anticipation, key pose, contact and recovery. Keep the creature's identity readable at gameplay distance and decide where rigid overlap is acceptable. Plan how body mass, stride and tail/ear follow-through communicate weight without stretching every brick form.

8. For UI and rewards, define closed/opening/open/closing and focus/press/pending/result transitions in the existing controller. Choose a restrained motion hierarchy: panel movement explains navigation, a small button response confirms input, and stronger celebration follows actual success. Timing is authored and tunable; reduced motion uses a stable alternative.

**Phase exit:** Pose/contact/timing, root policy and transition/cancellation intent are explicit.

## Build

1. Block keys in a simple interpolation mode and play the result at real speed. Iterate intention, support and timing before smoothing curves or adding subtle overlap.

2. Author transformations in the intended local/pose/object space. Preserve rest transforms and avoid baking corrective offsets into both the skeleton and runtime controller.

3. Refine arcs and spacing using meaningful breakdowns. Inspect acceleration, deceleration, overshoot and recovery in motion; do not polish by uniformly easing every channel.

4. Correct joint orientation and weight distribution where deformation fails. Automatic weights are a starting point; inspect unwanted influence and preserve existing vertex groups before rebinding.

5. Use IK/contact constraints deliberately and test entry/exit when their influence changes. Bake only what the target cannot evaluate and keep the editable constrained source.

6. For shape keys, preserve vertex count/order and verify relative basis and range behavior. Test combinations, extremes and neutral restoration instead of only each shape in isolation.

7. Keep distinct actions/clips with explicit names and ranges. Verify export inclusion against the installed exporter rather than assuming every action is exported automatically.

8. Preserve event-marker identity and avoid embedding consequential damage logic in a cosmetic animation event. Provide explicit cancellation and reset behavior for each owned animation track.

9. Block the key poses and ground contacts before smoothing curves. Check that feet or hooves support the body, limbs enter the torso cleanly, and jaw/wing/tail rotations do not expose gaps or intersect neighboring pieces. Add secondary motion only after the primary action and loop seam work at normal playback speed.

10. Use the target's existing animation/state system and give each transform one owner. For UI scale or position feedback, cancel or retarget the previous tween rather than stacking repeated tweens. Do not animate expensive text-outline thickness or permanently run a frame callback for a one-shot interaction; keep the original resting transform recoverable.

**Phase exit:** Editable keys/deformation and intended clip boundaries work in source playback.

## Integrate

1. Wire clips through the project's existing animation owner and parameter conventions. Ensure only one code path starts/stops a particular action and that repeated triggers do not accumulate tracks.

2. Resolve priority, masks, additive behavior and blending against locomotion, equipment and reactions. Check both directions of transitions, including interrupted or reversed transitions.

3. Integrate root motion with the actual controller and collision authority. Compare displacement from the clip with the desired runtime movement and avoid applying both twice.

4. Bind prop attachment, sound and VFX events to verified action beats. Gate server-owned consequences through validated gameplay state rather than trusting a local event callback.

5. Reimport the intended clip/rig into the target and check scale, axes, reference pose, root extraction and included animation ranges. A source viewport cannot verify import behavior.

6. Clean owned tracks, event listeners and temporary constraints on unequip, death, despawn and scene unload. Restore a usable neutral state when the action ends or is cancelled.

7. Use named animation events for presentation timing and disconnect their listeners with the rig/controller lifetime. Coordinate footstep, impact, trail and reward effects through shared event contracts with the existing audio/VFX skills. Consequential gameplay remains authoritative, independent of whether a client animation marker was observed.

8. Handle action replacement, input reversal, death/respawn, owner removal and missing assets through one cleanup path. A rapidly reopened panel must end in the newest requested state; an interrupted creature action must blend or return to the actual rest/locomotion pose without retaining offsets or orphaned tracks.

**Phase exit:** Target import/controller/event ownership is wired without duplicate motion.

## Verify

1. Play the motion on the actual target rig at normal speed and relevant camera distance. Inspect silhouette, weight, balance, arcs, support and contact before judging small curve details.

2. Test several continuous loops and inspect pose and velocity across the seam. Check foot sliding, root drift, toe/heel timing and accumulated offsets under varying movement speeds.

3. Exercise every meaningful entry, exit, interrupt and competing layer. Test rapid repeated triggers, equipment changes, hit reactions, pause/resume, respawn and controller reset.

4. Inspect deformation in extreme poses and blended combinations. Check shoulders, hips, knees, elbows, wrists, facial shapes and attached props for collapsing volume or wrong influence.

5. Compare event timing to the actual visible contact at low and normal frame rates. Verify that sound/VFX remain coordinated and gameplay authority does not depend on a dropped visual event.

6. Record a short actual playback clip or a labeled pose/contact sequence using advertised tools. A still image cannot prove timing, loop quality or blend behavior.

7. Verify the exported file and target import independently: expected clips, names, ranges, root policy, materials and skeleton mapping. Record publishing permissions if runtime asset IDs are needed.

8. Save editable source and identify which playback paths and device conditions were observed. If native playback/recording is unavailable, label those checks unverified instead of fabricating evidence.

9. Inspect a recording or sampled pose sequence on the target rig from front, side and normal gameplay camera. Check contact, silhouette, weight, loop closure, root drift, rigid-piece gaps and extreme poses. Reimport the exported clip before claiming that bones, weights and animation survived the delivery pipeline.

10. Test repeated open/close, hover/focus/press reversal, interruption halfway through, low frame rate and reduced motion for animated interfaces. For characters, test locomotion-to-action-to-recovery, competing layers and respawn. Verify that track/listener/tween counts settle after teardown and that missing or denied assets have clear recovery.

**Phase exit:** Actual target loops, interruption, deformation and timing have appropriate motion evidence.

## Failures

1. For foot sliding, compare root/controller displacement, stride length, clip speed and contact timing before changing animation speed globally.

2. For twisted joints, inspect rest pose, bone axes, parent-space transforms and retarget mapping. Repeated offset compensation in runtime code can conceal an incorrect source rig.

3. For popping transitions, compare source/destination pose, velocity, masks and state entry parameters. Fix the transition's ownership or key poses before extending blend duration indiscriminately.

4. For missing exported actions, inspect the installed exporter's inclusion policy and action-slot/NLA organization. Export one representative clip and reimport it before batch authoring more.

5. For duplicated tracks/events, locate every subscription and play request, give the action one owner and release it on lifecycle changes.

6. For publishing/permission failures, keep local editable clips and report the specific unavailable upload or ownership step. Never invent a cloud animation ID or claim local playback proves a published asset works.

7. If motion feels floaty, inspect support duration, center-of-mass shift, anticipation and recovery before adding more keys. If a block creature deforms like rubber, revise weighting or rigid articulation within the existing rig. If UI motion feels chaotic, remove competing transform owners and unnecessary simultaneous movement rather than deleting all useful feedback.

8. If an interrupted transition ends in the wrong pose or visibility state, inspect stale completion callbacks, cancellation tokens and restoration ownership. A still render does not verify motion, and an editable local clip does not prove successful asset publishing or replicated playback. Preserve source and report the remaining exact check.

**Phase exit:** Rig, import, controller or publishing cause is isolated and repaired or precisely blocked.

## Resource application

- retrieve: OMNI pose recipes and Spring/Signal lifecycle modules

- apply: Adapt timing, anticipation, overshoot and interruption to the existing rig. Verify multiple real poses and gameplay markers; a still reference is not motion evidence.

- memory: Use bounded ms_obsidian context/search/read for this project. Save a useful durable decision once when appropriate; never require repeated bookkeeping turns.

- reuse: Relevant task resources are preloaded before the user message is submitted when available. Reuse them, retrieve deeper sections only when needed, and never claim unavailable tools or unseen screenshots.

## Engine application

### roblox

Measure the current rig/joint rest transforms and inspect the existing Animator and tracks. Keep priorities, loops, marker ownership and cleanup explicit. A local KeyframeSequence or source clip is not a published AnimationId; verify ownership/upload access separately and never invent an ID. Test locomotion blends, equip, death and respawn.

Existing candidate skills: roblox-pro-animation, roblox-native-animation-tween. Load the smallest relevant set through the live skill tool.

### godot

Inspect AnimationPlayer/AnimationTree ownership, track paths, RESET/rest values and state parameters for the installed Godot version. Keep blend transitions, root-motion policy and model import compatible with the real controller. Test scene re-entry, interruptions, retargeted transforms and exported target playback.

Existing candidate skills: godot-animation-player-tree, godot-native-sprite-animation. Load the smallest relevant set through the live skill tool.

### unity

Inspect Animator parameters, layers/masks, Avatar/rig import, clips and root-motion ownership. Blend motions with compatible intent/timing and test transitions through the existing controller. Preserve source clips, event identity and cleanup; Timeline/Playables are not interchangeable with every character state-machine task.

Existing candidate skills: unity-animator-state-machines, unity-playables-timeline. Load the smallest relevant set through the live skill tool.

### blender

Inspect armature rest matrices, pose spaces, vertex groups, constraints, actions/slots and shape keys using the installed version. Preserve topology and editable sources; fix weights rather than hiding deformation with code offsets. Verify the actual exporter and reimport target before claiming clip/constraint equivalence.

Existing candidate skills: blender-rigging-humanoid, blender-native-animation-motion, blender-shape-keys. Load the smallest relevant set through the live skill tool.

### workspace

For app/UI motion, animate meaningful state changes and test interruption, focus/layout stability and reduced motion. For rig/3D work, use the actual authoring/export/runtime tools and file pipeline. A CSS transition, pose list or source render cannot prove a rigged target clip is imported and playing correctly.

Existing candidate skills: animation-production, camera-cinematics. Load the smallest relevant set through the live skill tool.

### figma

Use prototype transitions and component states only within Figma support and the advertised tool capabilities. Define timing, interruption and reduced-motion handoff, but distinguish a prototype animation from a rig, bone weights, published engine clip or gameplay controller.

Existing candidate skills: figma-prototyping, figma-components. Load the smallest relevant set through the live skill tool.

## Acceptance evidence

- The target rig preserves its intended neutral pose and deformation under tested extremes.
- Motion reads at gameplay distance with deliberate contacts, weight, arcs and timing.
- Loops preserve pose and velocity continuity without accumulated root drift.
- Transition and interruption tests leave no competing tracks or stale state.
- Target import contains the intended clips/ranges with correct scale, axes and root-motion policy.
- Motion evidence is actual playback or clearly labeled pose sampling, with untested paths disclosed.

## Diagnosis

### Foot skating

Probe: Compare displacement per cycle and support contacts.

Repair: Reconcile stride/root policy and controller speed.

Recheck: Test several speeds and loop seams.

### Exploding deformation

Probe: Inspect rest matrices, weights and armature mapping.

Repair: Correct source rig/influences without double transforms.

Recheck: Reimport and test extreme poses.

### Animation never starts

Probe: Trace asset permission, controller state and parameters.

Repair: Fix the earliest failing ownership/import boundary.

Recheck: Trigger from the real game entry point.

### Events fire twice

Probe: Trace track creation and subscriptions on repeated equip.

Repair: Give the track a single lifecycle owner.

Recheck: Equip, interrupt, unequip and respawn repeatedly.

## Deliverables

- Editable rig/actions with a pose, timing and contact sheet.
- Exported clips and an explicit target import/root-motion contract.
- Controller/layer/event integration and cleanup ownership.
- Actual playback evidence and documented publishing or rig limitations.

## Source guidance

- [Unity 6 Animation Blend Trees](https://docs.unity3d.com/6000.0/Documentation/Manual/class-BlendTree.html): Reviewed official Unity 6.0 page; verify installed controller/package.
- [Blender armature deform parenting](https://docs.blender.org/manual/en/latest/animation/armatures/skinning/parenting.html): Reference seed: current page fetch unavailable; older official indexed guidance reviewed. Inspect installed rig/export behavior.
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
