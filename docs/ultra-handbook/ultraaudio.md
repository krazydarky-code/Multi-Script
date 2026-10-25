# Audio purpose, spatial behavior, mixing and lifecycle

Detailed project-aware guidance, not weight training or permissions. Apply only relevant parts; preserve user scope, existing style and architecture. Inspect/review-only tasks remain read-only. Retrieve once, execute the authorized slice, reuse unchanged evidence and avoid guidance/discovery loops.

## Inspect

1. Map each sound to a gameplay purpose: confirmation, warning, contact, ambience, music, dialogue or navigation. Identify which cues are essential and which are optional cosmetics.

2. Inspect the project's actual audio API, mixer/bus graph, listener ownership, spatial units, attenuation and streaming/import settings before adding a parallel sound manager.

3. Inventory licensed or user-provided sources, editable stems and actual engine asset identities. Record ownership/permission and avoid inventing sound IDs or claiming an unavailable upload succeeded.

4. Observe event timing and current density at quiet, typical and worst-case play. Identify masking, excessive repetition, clipping, inconsistent loudness and inaudible critical cues.

5. Inspect voice limits, looping, pooling, loading, cross-fades, cancellation and scene teardown. Find sounds or listeners that persist after their owners disappear.

6. Establish target devices, user volume/mute settings, caption/visual alternatives and what listening/capture tools are genuinely available.

**Phase exit:** Purpose, sources, routing, spatial ownership and listening limits are known.

## Design

1. Write an event-to-sound table with trigger, source, priority, spatial role, bus, variation, lifetime, cancellation and fallback. Keep authority-sensitive actions separate from local sound playback.

2. Choose a gain hierarchy and frequency roles that preserve important feedback under density. Set project-specific loudness/headroom goals from actual material and playback context rather than universal invented numbers.

3. Design transient, body and tail for action cues and compare their timing to actual contact. Use controlled variation without making semantically meaningful cues ambiguous.

4. Define loop boundaries, cross-fade behavior, music transitions and ambience zones. Specify what happens when zones overlap, the listener moves quickly or a scene unloads.

5. Choose source formats/import compression and streaming behavior appropriate to length, repetition and platform. Preserve editable high-quality source outside lossy runtime exports.

6. Plan reduced-audio, mute, dialogue/music/SFX controls and non-audio equivalents for essential information. Settings should apply to newly created voices too.

**Phase exit:** Event/mix/voice/loop/accessibility and cancellation behavior are specified.

## Build

1. Author or select the smallest coherent sound palette for the task and verify actual import/playback before creating a large library.

2. Trim unintended silence, repair loop seams and apply short intentional fades where needed. Inspect waveform/export validity separately from listening quality.

3. Route sounds through the existing buses/mixer and use consistent gain staging. Avoid multiplying several independent volume controls so settings become unpredictable.

4. Implement spatial placement, attenuation and occlusion only through supported target features. Check listener orientation and distance in the real game scale.

5. Bound simultaneous voices and define priority/stealing behavior for repeated events. Pool voices only when playback, routing, spatial state and callbacks reset reliably.

6. Coordinate sound with verified action or animation events and cancel it through the same action owner. Do not rely on arbitrary delays that drift from actual contact.

7. Implement loading and missing-permission fallback visibly in diagnostics. Do not play a different unverified sound while claiming the intended asset works.

8. Preserve editable stems/project settings and record source provenance, runtime asset path/ID and import configuration for handoff.

**Phase exit:** Actual imported source, routing, timing and resettable voice behavior exist.

## Integrate

1. Integrate sounds with the accepted gameplay event, avoiding duplicate triggers from both client and server or multiple animation listeners.

2. Connect user controls and persisted preferences through one gain/settings owner. Test toggles before and during playback, including newly spawned sounds.

3. Manage ambience/music transitions when zones overlap, scenes reload, the listener changes or the player respawns. Keep one intended listener/mix context.

4. Provide visual/caption alternatives for essential cues and avoid exposing information only through precise stereo placement or a narrow frequency band.

5. Release voices, subscriptions and temporary emitters on cancellation, owner destruction and scene unload. Distinguish a deliberate continuing tail from a leaked loop.

6. Keep authored/imported/played/listened/published states separate in progress and delivery; a successful file export does not prove runtime audibility.

**Phase exit:** Events, settings, zones and lifecycle produce one intended playback path.

## Verify

1. Listen to the actual runtime mix at quiet, normal and representative peak density where tools permit. Label physical-device and listening coverage honestly.

2. Check clipping, headroom, masking, repetition fatigue and critical cue intelligibility while UI, movement, combat and ambience are active together.

3. Move and rotate the real listener around emitters; test near/far transitions, zone overlaps, camera changes and applicable occlusion.

4. Trigger rapid repeats and overlapping events to verify voice limits, variation, stealing and clean reset. Inspect resource counts after stopping.

5. Test loop seams, cross-fades, pause/resume, scene unload and respawn. Confirm one-off tails and persistent ambience behave intentionally.

6. Test volume, mute and essential-cue alternatives with settings applied before playback and while a voice is active.

7. Compare action/contact timing using an actual recording when available. If only waveform or file checks are possible, do not describe them as listening tests.

8. Verify packaged dependencies and permissions using the target connection, and report blocked publishing or unavailable devices explicitly.

**Phase exit:** Actual mix/playback and loop/settings/spatial checks have correctly scoped evidence.

## Failures

1. For silence, trace event trigger, loading/permission, routing, gain, listener and spatial attenuation in that order before raising all volume levels.

2. For clipping or masking, inspect summed density and gain hierarchy. Reduce or reprioritize competing layers instead of compressing every bus indiscriminately.

3. For doubled playback, inspect client/server ownership and duplicate event bindings; keep one intended playback owner per audience.

4. For stuck ambience, inspect zone ownership and teardown when the listener leaves or the scene changes.

5. For wrong spatial behavior, compare listener/emitters, units and attenuation settings rather than assuming imported source audio encodes position.

6. For unavailable generation/upload/listening tools, retain usable source and clearly distinguish authored/exported artifacts from unverified target sound.

**Phase exit:** Trigger, permission, routing, gain or lifetime cause is repaired or explicitly blocked.

## Engine application

### roblox

Inspect whether the project uses classic Sound or the newer Audio API before extending routing. Confirm asset permission and actual playback, listener/spatial scale, mixer/settings and cancellation. Trigger local cosmetics for the intended audience and prevent duplicate client/server playback. Report untested listening separately from file export.

Existing candidate skills: roblox-audio-vfx-lighting, vfx-assets. Load the smallest relevant set through the live skill tool.

### godot

Inspect AudioServer buses, listener/player nodes and import looping/streaming settings. Route controls through one settings owner and test scene changes, spatial distance and overlapping cues. Missing playback tools must be labeled; a generated audio file does not prove the correct bus or actual runtime listening.

Existing candidate skills: godot-audio-buses, godot-native-audio-export. Load the smallest relevant set through the live skill tool.

### unity

Inspect AudioMixer routing, exposed settings, AudioSource/listener ownership and import load/compression choices. Bound overlapping voices, preserve mute/volume settings and test spatial behavior at project scale. Confirm actual listening/playback independently from authored clips and asset loading.

Existing candidate skills: unity-audio-mixer, unity-addressables. Load the smallest relevant set through the live skill tool.

### blender

Use Blender audio/sequencing only when it serves the requested source/cinematic workflow and the tools are advertised. Preserve source stems and intended contact timing. Target-engine spatial mixing, voice limits and user volume controls still require a separate verified integration; do not infer them from timeline playback.

Existing candidate skills: audio-design, multi-app-art-pipeline. Load the smallest relevant set through the live skill tool.

### workspace

Check actual media permissions, user-gesture/autoplay requirements, routing and application volume ownership for the target runtime. Use real audio artifacts and listening/capture tools when available. Keep exported files, playback, physical output and account generation/upload limits separately verified.

Existing candidate skills: audio-design, input-accessibility. Load the smallest relevant set through the live skill tool.

### figma

Specify event purpose, timing, priority, spatial intent and volume/accessibility requirements for the runtime. Do not imply a visual prototype proves real mixing, listening, spatial playback or engine audio integration. Preserve licensed source paths and a concrete developer handoff.

Existing candidate skills: figma-developer-handoff, figma-accessibility. Load the smallest relevant set through the live skill tool.

## Acceptance evidence

- Important cues remain intelligible at representative peak density.
- Actual routing, volume, mute and spatial behavior match the project's settings and scale.
- Loops and transitions are clean, intentional and cancelled on the correct lifecycle events.
- Repeated events respect voice/resource limits without duplicate playback.
- Essential information has an appropriate non-audio alternative.
- Listening, file validation, runtime playback and publishing evidence are labeled separately.

## Diagnosis

### No sound

Probe: Trace trigger, permission, bus gain and listener.

Repair: Repair the earliest failed boundary.

Recheck: Play from the real event at near/far distances.

### Clipped mix

Probe: Inspect summed voices and bus levels under density.

Repair: Restore gain hierarchy and headroom.

Recheck: Repeat the same peak scenario.

### Doubled impact

Probe: Compare client/server and marker subscriptions.

Repair: Keep one intended playback owner.

Recheck: Trigger, cancel and retrigger repeatedly.

### Loop continues after exit

Probe: Inspect zone and voice ownership.

Repair: Stop or hand off the owned loop explicitly.

Recheck: Leave zone, unload scene and respawn.

## Deliverables

- Event-to-sound map, mixer routing and editable source/stems.
- Verified import/runtime paths and source/permission records.
- Voice, settings, spatial and cancellation integration.
- Actual listening/playback evidence or explicit limits on available audio checks.

## Source guidance

- [Godot scene organization](https://docs.godotengine.org/en/stable/tutorials/best_practices/scene_organization.html): Reviewed official guidance; use the installed version.
- [Roblox accessibility](https://create.roblox.com/docs/production/publishing/accessibility): Reviewed official indexed guidance; check installed client support.
