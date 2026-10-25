# Multi-Script 6.28.2 - Godot builders, Blender props, Native Toolcraft skills, Audio + NPC tools

Fully additive: no existing tool name, JSON schema or default changed. New modules load defensively
(`engine_toolkit.PRO_ERRORS` lists any that fail to import; the rest keep working).

## Chat bar nudge sliders (fix)
- Root cause: while a slider was dragged the open menu was re-anchored to the moving bar every frame, so the slider ran away from the pointer. The menu is now anchored to the un-nudged position and fades while dragging.
- Nudge works in every dock (Auto / Float / Window; it was dimmed in Auto), is stored per site (`barOffsetBy`), clamped to the window (the label shows when it hits the edge), saved debounced, with "+12 px" read-outs, double-click / Home / Delete reset and a Reset nudge button.
- `tests/test_chatbar_nudge.js`: Notion + Claude x float/window/auto in real Chromium.

## Fazbear's theme (live) + secret Backstage tab (revamped)
- 21st theme (menu and chat bar): wall with swaying stage spotlights, black/white checkered bands aligned top and bottom, party bunting, blurry drifting pizza drawings, purple glow that deepens toward the lower settings, optional camera-static / flicker.
- **Picking it is now an event**: red stage curtains part on a "Welcome to Fazbear's - Pizza & Prize Corner" sign (skipped when motion is reduced/none), then a greeting toast; the very first time, the Backstage tab pulses to give the secret away.
- **Backstage tab**: stage cast accents (Freddy, Bonnie, Chica, Foxy, Mangle + unlockable Puppet, Springtrap, Golden, Fredbear), pizza count / drift speed / blur / tile size / glow, spotlights, flicker, camera static, jumpscare-flash opt-out, a 30-minute night shift, Phone Guy calls (real feature hints) and achievements.
- **The secret is now a game**: a "STAFF ONLY" door needs a keycard (answer 3 Phone Guy calls, or find the eyes). Inside is a **Security Office** - five nights of power management (doors A/D, lights Q/E, camera C and cams 1-4; Bonnie and Chica walk the halls, Foxy sprints if you stop watching the Cove, Freddy comes when the power dies). Every night starts with a Phone Guy briefing tied to a real Multi-Script feature. Clearing nights unlocks cast members and achievements; clearing Night 1 also opens Golden. It lasts about 84 s per night, runs locally, has no sound, and the jumpscare is a short shake you can switch off.
- Pure game engine in `ZSExtras.FNAF_OFFICE` (no DOM); `tests/test_fnaf_office_engine.js` checks power, doors, lights, cams, Foxy, Freddy and the difficulty curve; `tests/test_fnaf_theme.js` drives the whole UI in Chromium (intro, keycard, win/loss, keys, abandon, leaving mid-night, motion, reset, hostile storage).

## Settings sweep
- `tests/test_settings_sweep.js` operates every control on every tab (Notion + Claude), every theme x narrow/wide x scale, small viewports, bar options and hostile storage. Fix: very long MCP server names/URLs no longer stretch the menu sideways.

## Godot (now 40 native tools)
- `ms_godot_gameplay_kit` - 27 systems in 2D/3D as GDScript + prefab scene: player_third_person, player_first_person, player_platformer, player_topdown, camera_follow, camera_shake, health_component, hitbox, hurtbox, collectible, checkpoint, kill_zone, moving_platform, projectile, shooter, enemy_ai, spawner, level_rules, interactable, door, state_machine, inventory, day_night_cycle, floating_text, game_manager, save_system, scene_transition. Missing input actions are defined and autoloads registered.
- `ms_godot_building_generator` - house, cottage, shop, tower, barn, warehouse, castle keep, ... with gabled/hip/flat/stepped roofs, door side, lit windows, colliders.
- `ms_godot_path_builder` - road, path, fence, rail, bridge, wall, pipe along Path3D with lamps/stones.
- `ms_godot_scatter` - 10 reusable prop scenes, rect/circle areas, optional physics snapping to a ground scene with slope limits.
- `ms_godot_model_tools` - headless scene editing: stats, array, mirror, align, distribute, group/ungroup, randomize, rename, colliders, visibility_range, set_material, center_pivot, static. `dry_run` supported.
- Also in this line: `ms_godot_level_blockout`, `ms_godot_terrain_generate`, `ms_godot_scene_audit`, `ms_godot_shader_create` (18 shaders), UI kit scripts.

## Blender
- `ms_blender_prop_generator` - 26 prop kinds (trees, rocks, crates, barrels, fences, furniture, lamps, weapons, columns, arches, stairs, wells, tents, towers, bridges, ...) with material slots, scale, seed, bevel, smooth shading.

## Roblox audio and NPC tools (5 new tools, 47 native Roblox tools)
- `ms_roblox_audio_kit` - mixer (SoundGroups, limiter, ducking), audio API module, ambient zones, music player, footsteps, UI sounds, 3D emitters, triggers, reverb zones, jukebox, low-health muffle. Sound ids are passed in `options` (normalised to `rbxassetid://`); no audio is bundled and missing ids are reported as warnings.
- `ms_roblox_audio_tools` - list / audit (with safe fixes: assign groups, 3D roll-off, clamp volume, fix ids) / create groups, sounds and effects.
- `ms_roblox_npc_builder` - humanoid NPCs from presets (villager, guard, merchant, quest giver, zombie, skeleton, robot, boss, child) with a mannequin fallback, nameplate, tags and ground snapping.
- `ms_roblox_npc_behavior` - wander, patrol, follow, guard, melee/ranged enemies, flee, merchant, quest giver, dialogue and spawner scripts (pathfinding with fallback, server-side validation).
- `ms_roblox_npc_manage` - list / inspect / configure / crowd-spawn / remove / audit (with fixes) / snap to ground.
- Tested with generated-program syntax checks, a Luau mock and a fake-engine harness that executes the installed scripts (`tests/test_roblox_audio_npc_tools.py`). Not run in a live Studio session.

## Godot audio and NPC kits (2 new tools, 40 native Godot tools)
- `ms_godot_audio_kit` - AudioManager autoload (buses, pooled SFX, music crossfade, ducking, saved volumes), positional SFX pool, footsteps, ambience zones, playlist, UI sounds.
- `ms_godot_npc_kit` - NPC brain (7 behaviours, NavigationAgent with a straight-line fallback) plus prefab scene, dialogue text box, NPC spawner; 2D and 3D.
- Every generated script is parsed with the real GDScript 4 grammar and linted in `tests/test_godot_audio_npc_tools.py`; the `--check-only` pass runs automatically when a Godot binary is available.

## Limits (truncation) settings
- Settings > Agent > Limits now shows a plain-language summary of what the current choices mean, with a "Reset to automatic" button.
- Custom message cap no longer clips Multi-Script's own instructions, only the user's content; a single central clip covers providers without their own (Kimi, GLM, Meta).
- Result pages are never larger than what the send step can carry, "No limit" really means no paging and no clipping, and the bridge honours the chosen result limit (`result_limit`) and names Settings > Limits in its clip marker. Automatic mode is unchanged.

## Skills (824 -> 897)
- "Native Toolcraft" pack: 12 skills per engine (Roblox, Unity, Godot, Blender) that name the real `ms_<engine>_*` tools for building, modelling, UI/UX, terrain, animation, materials, effects and audit loops. Regenerate with `python3 tools/add_native_toolcraft_skills.py` (idempotent; refuses unknown tool names).

- "Audio + NPC" pack: 25 skills (14 Roblox, 5 Godot, 4 Unity, 2 Blender) for mixers, music, ambience, footsteps, audits, NPC building, AI, dialogue, crowds and audits. Regenerate with `python3 tools/add_audio_npc_skills.py`.
- Tool catalogue: `docs/TOOLS_GUIDE.md` lists every tool (regenerate with `python3 tools/gen_tools_guide.py`).

## Tests
- New `tests/test_godot_native_tools.py` (real headless Godot: every kit scene loads and runs `_ready`, all scripts parse, buildings/paths/scatter/model tools/shaders load). Blender prop tests run in `test_native_pro_tools.py`.
- Godot, Blender (bpy), Luau and Unity C# compile checks are optional and skip when the binaries are missing.

## Notion AI compatibility (loads forever / never replies)
- Root cause (mock-DOM verified, not yet confirmed on live Notion): a transcript message - including our long startup prompt - is a `[contenteditable]` block-editor node. When the live composer was not resolved by its placeholder, such a node could win the scorer, so the "Agent is working..." cover was drawn in the middle of the page, `.zs-typing` hid the message text, and Stop/Send were looked up in the wrong container - the startup then never saw a generation and sat on "Starting...".
- Fix: transcript editables (`contenteditable="false"`, inside/wrapping a `[data-agent-service-scroll-anchor]` row, assistant block roots without composer copy) are never composer candidates; "nearby composer copy" only counts in short containers (<= 400 chars); the composer frame never grows into a container holding the transcript. Also fixed a `const` reassignment in the shadow-root scoring path.
- Faster, steadier generation detection: a global `agent-stop`/`agent-interrupt` test-id fallback when the composer card cannot be resolved, and Notion's `running-placeholder:` row counts as "working" (bounded to 150 s so a stale row can never hold the loop open).
- `tests/test_notion_transcript_editable_guard.js` covers the /chat thread case.
