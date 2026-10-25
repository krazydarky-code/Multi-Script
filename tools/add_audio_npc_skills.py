#!/usr/bin/env python3
"""Idempotently adds the 6.28.2 "Audio + NPC" skill pack to runtime/skills.json, skill-packs.json, capability-index.json and
product-manifest.json. Every skill names the real ms_<engine>_* tools it drives; the generator refuses to run if a referenced tool is
not registered. Re-running replaces the pack's own skills (and nothing else)."""
import copy, json, os, sys
if "--force" not in sys.argv:
    sys.exit("This pack was removed in the catalogue prune (6.48.2). Pass --force to re-add it.")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RT = os.path.join(ROOT, "runtime")
sys.path.insert(0, RT)
import engine_toolkit as T  # noqa: E402

PACK, DOMAIN, ADDED = "audio-npc-expansion", "native-audio-npc", "6.28.2"
K, A, M, B, MN, MG = ("ms_roblox_audio_kit", "ms_roblox_audio_tools", "ms_roblox_npc_manage", "ms_roblox_npc_builder", "ms_roblox_npc_behavior", "ms_roblox_gameplay_kit")

# slug, name, description, role, tools, steps, when
S = {
"roblox": [
 ("audio-mixer-ducking", "Roblox audio mixer and ducking", "Install a SoundGroup mixer (Master > Music/SFX/UI/Ambience/Voice) with a ducking API so dialogue and stingers lower the music cleanly.", "implementation",
  [K, A], ["List the existing SoundGroups and Sounds first so nothing is duplicated.", "Install the mixer kit and route every existing Sound into a group with audio_tools assign_group.", "Use the generated duck API for dialogue, boss intros and UI stingers; keep ducking short (0.3-1 s)."], "A place has sounds but no volume control, or music and effects fight each other."),
 ("audio-api-sfx", "Roblox audio API and sound effects", "Add a single server/client audio module (play, play3D, random variation, pitch jitter, cooldowns) instead of scattered Sound:Play() calls.", "implementation",
  [K, A, "ms_roblox_script_manage"], ["Check which audio systems already exist (audio_tools list).", "Install audio_api with the real sound ids passed through options; never invent asset ids.", "Replace direct :Play() calls in gameplay scripts with the API and read back the scripts."], "Gameplay scripts need consistent hit, pickup, UI or ability sounds."),
 ("ambience-reverb-zones", "Roblox ambience and reverb zones", "Place trigger zones that crossfade ambient loops and switch reverb (cave, hall, outdoors) as the player moves.", "polish",
  [K, A, "ms_roblox_measure"], ["Measure the regions that need distinct acoustics (caves, interiors, water).", "Install ambient_zones and reverb_zones with those regions and the real sound ids.", "Walk each boundary in a playtest and confirm the fades have no clicks or overlaps."], "A world feels flat or silent, or interiors sound like exteriors."),
 ("dynamic-music", "Roblox dynamic music", "Install a music player that crossfades by game state (explore, combat, boss, victory) with a jukebox and a low-health layer.", "implementation",
  [K, A], ["Define the states and which track plays in each; keep every state a loopable track.", "Install music_player (and jukebox / low_health when wanted) with the ids passed as options.", "Test transitions in both directions and check that nothing restarts when the state does not change."], "The game has more than one mood or needs a player-facing music selection."),
 ("footsteps-ui-sounds", "Roblox footsteps and UI sounds", "Material-aware footsteps for the local character and hover/click/open sounds for GUI buttons.", "polish",
  [K, "ms_roblox_ui_kit"], ["Decide which floor materials need distinct steps (grass, stone, wood, metal, water).", "Install footsteps and ui_sounds with one sound id per material/event.", "Check the footstep rate matches walk and run speed and that UI sounds fire once per click."], "Movement or menus feel silent and unresponsive."),
 ("spatial-3d-audio", "Roblox 3D emitters and triggers", "Attach positional emitters to props and fire one-shot sounds from touch/prompt triggers with sensible roll-off ranges.", "polish",
  [K, A, "ms_roblox_attributes"], ["List the props that should be audible from a distance (machines, fires, waterfalls).", "Install emitter_3d and audio_trigger with realistic min/max distances.", "Run audio_tools audit with apply to normalise roll-off and clamp volumes."], "Sounds should come from places in the world, not from the whole screen."),
 ("audio-audit-fix", "Roblox audio audit and fixes", "Audit every Sound for missing ids, missing groups, 2D sounds that should be 3D and extreme volumes, then apply the safe fixes.", "validation",
  [A, K, "ms_roblox_playtest"], ["Run audit without apply and read the findings by severity.", "Apply the fixes (assign_group, rolloff_3d, clamp_volume, fix_ids) and re-run audit.", "Playtest and read Output for audio load failures before reporting."], "A place sounds wrong, is too loud, or Output shows asset load errors."),
 ("npc-design-builder", "Roblox NPC design and building", "Build a humanoid NPC from a preset (villager, guard, merchant, quest giver, zombie, skeleton, robot, boss, child) with nameplate, tags and grounded placement.", "implementation",
  [B, M], ["Pick the NPC's role and preset, then decide name, title and outfit from the brief.", "Build it at an exact position, grounded, inside an NPC folder.", "Inspect it with npc_manage and fix collisions, anchoring or floating before adding behaviour."], "The game needs characters that are not the player."),
 ("npc-patrol-wander", "Roblox NPC patrol and wander", "Give NPCs believable idle life: wander around a home point or patrol waypoints with pauses and pathfinding fallbacks.", "implementation",
  [MN, M, "ms_roblox_measure"], ["Measure the walkable area or the waypoint positions.", "Install wander or patrol behaviour with the points and speeds.", "Playtest and check that NPCs neither stand still nor walk through walls."], "Town or camp NPCs should move without looking scripted."),
 ("enemy-ai-combat", "Roblox enemy AI (melee, ranged, flee)", "Install chase-and-attack, ranged-attack and flee behaviours with server-side damage, cooldowns and respawn.", "implementation",
  [MN, B, MG], ["Choose the enemy archetype and tune range, damage, cooldown and health.", "Build the NPC, install enemy_melee or enemy_ranged, and link rewards if the game has an economy.", "Playtest fights: confirm damage is server-side and enemies respawn once."], "The game has hostile NPCs."),
 ("merchant-quest-dialogue", "Roblox merchants, quests and dialogue", "Prompt-based dialogue, merchants that sell items and quest givers that track objectives, with inputs validated on the server.", "implementation",
  [MN, B, "ms_roblox_ui_kit"], ["Write the dialogue lines and the shop/quest data first (short, in character).", "Install dialogue, merchant or quest_giver on the NPC with that data.", "Playtest buying, refusing and finishing a quest; confirm remotes validate every argument."], "Players need to talk to, trade with or take jobs from NPCs."),
 ("npc-crowds-spawners", "Roblox NPC crowds and spawners", "Fill streets and arenas with varied NPCs and keep enemy waves alive with a capped spawner that clones a template.", "optimization",
  [M, MN, "ms_roblox_optimize"], ["Decide the crowd size per zone from the weakest-device budget.", "Use spawn_crowd for ambience and the spawner behaviour for waves with a hard alive-cap.", "Playtest on a low-quality setting and reduce counts until the frame rate holds."], "A scene needs many NPCs without hand-placing each one."),
 ("npc-audit-optimisation", "Roblox NPC audit and optimisation", "Find NPCs with no humanoid, no root part, floating, unanchored or missing behaviour tags, then repair and snap them to the ground.", "optimization",
  [M, "ms_roblox_optimize", "ms_roblox_playtest"], ["Run npc_manage audit without apply and list the findings.", "Apply the safe fixes and snap_to_ground for floating NPCs.", "Playtest and confirm NPCs stand, move and respond."], "NPCs fall through the floor, float, or do nothing."),
 ("npc-audio-voice", "Roblox NPC barks and audio feedback", "Give NPCs 3D footsteps, greeting barks and hit/death sounds that respect the mixer groups.", "polish",
  [K, A, MN], ["List which NPC events deserve sound (greet, notice, hit, death).", "Install emitter_3d / audio_trigger for barks and wire the ids through options.", "Audit the result so every NPC sound is 3D, grouped and not clipped."], "NPCs feel lifeless or silent."),
],
"godot": [
 ("audio-manager-buses", "Godot AudioManager and buses", "Install an AudioManager autoload that creates Music/SFX/UI/Ambience buses, pools sounds, crossfades music, ducks and saves volumes.", "implementation",
  ["ms_godot_audio_kit", "ms_godot_audio_bus_layout", "ms_godot_autoload"], ["Check project.godot for an existing audio autoload before adding another.", "Install audio_manager with the sound names in options.sounds (res:// paths only).", "Call it from gameplay scripts and confirm the buses exist in the Audio panel."], "A Godot project plays sounds from many scripts or has no volume settings."),
 ("spatial-audio-footsteps", "Godot positional audio and footsteps", "Add a 2D/3D positional sound pool and distance-paced footsteps for CharacterBody nodes.", "polish",
  ["ms_godot_audio_kit", "ms_godot_gameplay_kit"], ["Pick 2D or 3D to match the player controller.", "Install sfx_pool and footsteps; assign stream arrays in the Inspector.", "Check steps stop in the air and speed up with running."], "Movement and impacts should be heard from where they happen."),
 ("ambience-music-ui", "Godot ambience, playlists and UI sounds", "Ambience zones that fade with the player, a shuffled music playlist and automatic button sounds.", "polish",
  ["ms_godot_audio_kit", "ms_godot_ui_kit", "ms_godot_scene_audit"], ["List the zones and moods the game needs.", "Install ambience_zone scenes, music_playlist and ui_sounds with the right resources.", "Run scene_audit and confirm the player is in the 'player' group."], "A level needs atmosphere or menus need feedback."),
 ("npc-brain-navigation", "Godot NPC brains and navigation", "CharacterBody NPCs with idle/wander/patrol/follow/guard/flee/enemy_melee, navmesh pathing and straight-line fallback.", "implementation",
  ["ms_godot_npc_kit", "ms_godot_gameplay_kit", "ms_godot_level_blockout"], ["Pick the behaviour per NPC and any patrol waypoints in global coordinates.", "Install npc_brain (scene included), bake a NavigationRegion if the level has obstacles.", "Playtest chasing, leashing and take_damage hits against the player."], "A Godot game needs living NPCs or enemies."),
 ("npc-dialogue-spawners", "Godot NPC dialogue and spawners", "Talk-to dialogue with an auto-built text box and spawners that keep a capped number of NPCs alive.", "implementation",
  ["ms_godot_npc_kit", "ms_godot_input_map", "ms_godot_ui_kit"], ["Write the lines first and keep each under two sentences.", "Install dialogue (defines the interact input) and npc_spawner with the NPC scene.", "Verify interact works only near the NPC and the spawner never exceeds max_alive."], "NPCs must talk or appear over time."),
],
"unity": [
 ("audio-mixer-scripts", "Unity audio manager and mixer scripts", "Write a compile-checked AudioManager (pooled sources, music crossfade, AudioMixer exposed parameters, saved volumes) with the native script tools.", "implementation",
  ["ms_unity_create_script", "ms_unity_script_check", "ms_unity_components", "ms_unity_console"], ["Check for an existing audio manager and the project's AudioMixer assets first.", "Create the script, run script_check, and attach it to a persistent object.", "Read the console after entering play mode and fix the first error."], "A Unity project needs central audio control."),
 ("npc-ai-navmesh", "Unity NPC AI with NavMesh", "Create NPC prefabs with NavMeshAgent behaviour (patrol, chase, flee) from scripts, then bake and test the NavMesh.", "implementation",
  ["ms_unity_navmesh", "ms_unity_create_script", "ms_unity_prefab", "ms_unity_gameplay_kit"], ["Bake the NavMesh for the walkable geometry and check agent radius and height.", "Generate the NPC controller script and prefab, reusing the gameplay kit where it fits.", "Playtest a path between two points and read the console."], "Unity NPCs or enemies must move through the level."),
 ("npc-dialogue-ui", "Unity NPC dialogue UI", "Interaction prompt plus a dialogue panel built with the UI kit and a small script that reads lines from a ScriptableObject.", "design",
  ["ms_unity_ui_kit", "ms_unity_create_script", "ms_unity_asset"], ["Write the dialogue data format (ScriptableObject) before the UI.", "Build the panel with the UI kit and wire the script.", "Test with keyboard and gamepad focus."], "NPCs need to talk to the player."),
 ("audio-feedback-vfx", "Unity audio feedback and particles", "Pair hit/pickup/ambient particle effects with audio sources placed at the same anchors.", "polish",
  ["ms_unity_particle_effect", "ms_unity_components", "ms_unity_scene_audit"], ["Choose the events that need feedback.", "Create the particle effect and add an AudioSource with spatial blend and range set.", "Audit the scene for missing clips."], "Actions feel flat."),
],
"blender": [
 ("character-npc-rigging", "Blender NPC character rigging", "Prepare character meshes for NPC use: clean topology, unwrap, rig with a template, and test weights.", "implementation",
  ["ms_blender_mesh_cleanup", "ms_blender_uv_unwrap", "ms_blender_armature_rig", "ms_blender_rig_info"], ["Run mesh stats and cleanup before rigging.", "Apply a rig template scaled to the mesh and parent with automatic weights.", "Pose-test extremes and fix bad weights."], "A character model will become an NPC in a game engine."),
 ("npc-animation-set", "Blender NPC animation set", "Create idle, walk, run and attack actions with clean loops and engine-friendly names.", "implementation",
  ["ms_blender_motion_preset", "ms_blender_animation_actions", "ms_blender_keyframes", "ms_blender_export"], ["List the actions the engine expects (idle/walk/run/attack).", "Create them from motion presets and fix loop seams.", "Export with the engine preset and verify the action names."], "NPCs need a basic animation set."),
],
}


def load(name):
    with open(os.path.join(RT, name), encoding="utf-8") as fh:
        return json.load(fh)


def save(name, data):
    with open(os.path.join(RT, name), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)


def build():
    T.ensure_loaded()
    skills, packs, cap = load("skills.json"), load("skill-packs.json"), load("capability-index.json")
    old = set(packs.get(PACK, {}).get("skills", []))
    for sid in old:
        skills.pop(sid, None)
    tpls = {}
    for v in skills.values():
        if v.get("capabilityDomain") == "studio-craft" and v.get("engine") in S and v["engine"] not in tpls:
            tpls[v["engine"]] = v
    new, by_engine = {}, {}
    for eng, rows in S.items():
        for slug, name, desc, role, tools, steps, when in rows:
            sid = f"{eng}-audionpc-{slug}"
            for t in tools:
                if t not in T.REGISTRY:
                    raise SystemExit(f"{sid}: unknown tool {t}")
            rec = copy.deepcopy(tpls[eng])
            rec.update({
                "name": name, "description": desc, "engine": eng, "category": rec.get("category", "studio-craft"),
                "tags": [eng, "native-tools", "audio" if "audio" in slug or "music" in slug or "footsteps" in slug or "ambience" in slug else "npc", slug.split("-")[0]],
                "capabilityDomain": DOMAIN, "capabilityRole": role, "whenToUse": when,
                "steps": ["Inspect the open project and the current state of what you are about to change (read before write)."] + steps + [
                    "Drive the work through the real native tools: " + ", ".join(tools) + " (use each tool's live schema; do not invent parameters or asset ids).",
                    "Read the result back with the matching list/inspect/audit action and fix the first defect before polishing.",
                    "Report what exists now, what was verified and any remaining limits (for example sound ids the user still has to supply)."],
                "deliverables": ["The requested result exists in the real project", "Native read-back or audit evidence", "Notes on the options used and how to regenerate or tweak them"],
                "qualityGates": ["Uses the native ms_* tools instead of hand-written one-off code when one fits", "Result loads with no engine errors", "No invented asset ids: missing sounds are reported, not faked",
                                 "Works for late joiners, respawn and the weakest target device", "State read back before claiming success"],
                "relatedSkills": ([f"{eng}-audionpc-{r[0]}" for r in rows if r[0] != slug] + sorted(k for k in skills if k.startswith(f"{eng}-native-")))[:4],
                "nativeTools": tools,
            })
            rec["engineExecutionContract"]["engine"] = eng
            new[sid] = rec
            by_engine.setdefault(eng, []).append(sid)
    skills.update(new)
    save("skills.json", skills)
    ids = list(new)
    packs[PACK] = {"name": "Audio + NPC Expansion (6.28.2)", "description": f"{len(ids)} engine skills for audio systems (mixers, music, ambience, footsteps, audits) and NPCs (building, AI, dialogue, merchants, crowds, audits) that drive the real ms_<engine>_* tools.",
                   "addedIn": ADDED, "count": len(ids), "skills": ids}
    packs["totalSkills"] = len(skills)
    save("skill-packs.json", packs)
    for eng, sids in by_engine.items():
        e = cap["engines"].setdefault(eng, {"skillCount": 0, "domains": {}})
        e["domains"][DOMAIN] = {"skillIds": sids, "roles": {}}
        for sid in sids:
            e["domains"][DOMAIN]["roles"].setdefault(new[sid]["capabilityRole"], []).append(sid)
        e["skillCount"] = sum(len(d["skillIds"]) for d in e["domains"].values())
    cap["totalSkills"] = len(skills)
    save("capability-index.json", cap)
    pm = load("product-manifest.json")
    pm.setdefault("catalogue", {})["skills"] = len(skills)
    save("product-manifest.json", pm)
    return len(new), len(skills)


if __name__ == "__main__":
    n, total = build()
    print(f"added/updated {n} skills; total {total}")
