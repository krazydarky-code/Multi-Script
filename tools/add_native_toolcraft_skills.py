#!/usr/bin/env python3
"""Idempotently adds the 6.28.2 "Native Toolcraft" skill pack (48 skills) to runtime/skills.json, skill-packs.json,
capability-index.json and product-manifest.json. Every skill names the real ms_<engine>_* native tools it drives and
the generator refuses to run if a referenced tool is not registered."""
import copy, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RT = os.path.join(ROOT, "runtime")
sys.path.insert(0, RT)
import engine_toolkit as T  # noqa: E402

PACK, DOMAIN, ADDED = "native-toolcraft-expansion", "native-toolcraft", "6.28.2"

# slug, name, description, role, tools, specific steps (3), when
S = {
"godot": [
 ("building-generator", "Godot building generation", "Generate lit, enterable, collision-ready buildings (house, tower, barn, castle keep...) as reusable scenes instead of hand-placing boxes.", "implementation",
  ["ms_godot_building_generator", "ms_godot_scene_audit"], ["Pick the building kind, footprint, floors and roof style from the brief, then generate it as a saved scene.", "Place instances in the level scene and vary seed, size and wall colour so a district does not look cloned.", "Validate the scene loads headless and that doors face the intended approach path."], "A level needs houses, towers, forts or a village and the user wants real geometry, not placeholder cubes."),
 ("path-fence-builder", "Godot roads, fences and bridges", "Draw roads, paths, fences, rails, bridges, walls and pipes along a curve with Path3D, CSG and lamp or post spacing.", "implementation",
  ["ms_godot_path_builder", "ms_godot_scatter"], ["Define waypoints from the layout, choose smooth or closed curves and the kind (road, fence, bridge...).", "Add lamps or stones along the path and keep post spacing consistent with the player scale.", "Read the Curve3D back and confirm start and end land on the intended anchors."], "Anything linear must follow terrain or connect two places: roads, fences, rope bridges, pipelines."),
 ("scatter-dressing", "Godot scatter and scene dressing", "Dress a level with trees, rocks, bushes, crates and grass using seeded area scatter that can snap to physics ground and align to slope normals.", "polish",
  ["ms_godot_scatter", "ms_godot_terrain_generate"], ["Choose the prop set and density per zone; keep clearings around spawn, paths and landmarks.", "Use ground_scene snapping so props sit on the terrain and use align_to_normal only for rocks and logs.", "Check reuse: props are saved as scenes, not duplicated resources, and the count fits the weakest platform."], "The world looks empty, flat or repetitive and needs believable dressing."),
 ("model-editing", "Godot model and node editing", "Bulk-edit imported or generated models headless: stats, array, mirror, align, distribute, group, rename, colliders, visibility ranges, materials and pivots.", "polish",
  ["ms_godot_model_tools", "ms_godot_scene_audit"], ["Run stats first to know triangle counts, bounds and node classes.", "Apply the smallest set of edits (array, mirror, align, colliders, visibility_range) with dry_run before saving.", "Re-run stats and validate the scene so nothing broke."], "A scene needs repeated, mirrored or re-organised geometry, collision generation or LOD distances."),
 ("gameplay-kit", "Godot gameplay kit prefabs", "Drop proven gameplay building blocks (controllers, cameras, health, pickups, checkpoints, enemies, doors, inventory, save, scene transitions) as scripts plus prefab scenes with inputs and autoloads wired.", "implementation",
  ["ms_godot_gameplay_kit", "ms_godot_input_map", "ms_godot_autoload"], ["List kinds, pick the controller and supporting parts for the genre in 3D or 2D.", "Generate with define_inputs and register_autoload where needed, then attach to the player or level.", "Playtest headless and confirm the ready path runs with no script errors."], "The project needs a working player, camera, combat, interaction or persistence loop quickly and safely."),
 ("ui-kit-screens", "Godot UI kit screens", "Build themed menus, HUDs, settings, dialogs and inventories with Control containers, anchors and scripts that react to input and resolution.", "design",
  ["ms_godot_ui_kit", "ms_godot_resource_create", "ms_godot_input_map"], ["Choose the screen set and a single theme (colours, fonts, spacing) before generating.", "Generate screens with container layouts, focus order and gamepad navigation.", "Validate at two aspect ratios and verify buttons emit the expected signals."], "The game needs a main menu, pause, HUD, settings, shop, dialogue or inventory UI."),
 ("terrain-blockout", "Godot terrain and level blockout", "Create heightmap terrain from presets and block out 3D, top-down or platformer levels from ASCII maps before art.", "design",
  ["ms_godot_terrain_generate", "ms_godot_level_blockout"], ["Pick a terrain preset or ASCII map that matches the intended play flow and scale.", "Generate, then query heights at key points to place spawn, goals and landmarks.", "Playtest the blockout for pacing and sight-lines before dressing."], "A new level or map needs layout, height variation and measurable scale."),
 ("shader-library", "Godot shader library", "Create parsed-and-verified spatial, canvas and sky shaders (toon, water, dissolve, hologram, outline, wind, glow...) and matching materials.", "polish",
  ["ms_godot_shader_create", "ms_godot_resource_create"], ["Select the shader preset and expose only meaningful uniforms with ranges.", "Create the shader and the ShaderMaterial resource and assign it.", "Confirm the shader compiles in the real engine and check cost on the weakest target."], "A distinctive look, water, dissolve, outline or stylised material is required."),
 ("environment-lighting", "Godot environment and lighting", "Set sky, fog, glow, tonemapping, SSAO and sun or day-night lighting so a scene reads at first view.", "polish",
  ["ms_godot_environment", "ms_godot_gameplay_kit"], ["Choose the mood and time of day, then apply a WorldEnvironment preset.", "Tune sun angle and shadows to reveal the landmarks and path.", "Provide a low-tier fallback that disables SSAO, SDFGI and volumetric fog."], "The scene looks flat, washed out or default-lit."),
 ("sprite-animation", "Godot 2D sprite and animation", "Slice sprite sheets into SpriteFrames, create AnimationPlayer tracks and wire states for 2D characters, effects and UI.", "implementation",
  ["ms_godot_sprite_animation", "ms_godot_animation_create", "ms_godot_particles"], ["Slice sheets with exact frame counts and set looping per clip.", "Create animation tracks for non-sprite properties (position, modulate, scale).", "Check play order, loop points and signal events on a short playtest."], "A 2D character, pickup or effect needs animation."),
 ("audio-export", "Godot audio buses and export", "Define audio buses with effects and export presets for each target platform with correct filters and resources.", "validation",
  ["ms_godot_audio_bus_layout", "ms_godot_export_presets", "ms_godot_project_setting"], ["Create Master, Music, SFX and UI buses with sensible volumes and effects.", "Create export presets per platform and set include filters and icons.", "Validate the project and read presets back before claiming the build is ready."], "Audio mixing or a release build for desktop, web or mobile is requested."),
 ("project-audit-loop", "Godot project audit loop", "Validate scenes, scripts, inputs, autoloads and references in the real engine and fix the dominant defect first.", "validation",
  ["ms_godot_scene_audit", "ms_godot_validate_project", "ms_godot_script_check", "ms_godot_find_references"], ["Run validate_project and script_check to capture the exact errors.", "Run scene_audit in fix mode for missing inputs and unused resources, then fix the rest by hand.", "Re-run the validators until clean and report what remains."], "Anything was generated, imported or refactored and must be proven to load."),
],
"unity": [
 ("building-generator", "Unity building generation", "Generate multi-floor buildings with roofs, windows and doors as prefabs rather than placing cubes by hand.", "implementation",
  ["ms_unity_building_generator", "ms_unity_prefab"], ["Pick kind, footprint, floors and roof from the brief and generate with a stable name.", "Save as a prefab and instantiate variants with different seeds and colours.", "Check colliders, static flags and batching for the whole district."], "A scene needs houses, towers, forts or a village."),
 ("path-fence-builder", "Unity roads, fences and bridges", "Lay roads, fences, walls, rails, bridges and lamp rows along waypoints with consistent spacing.", "implementation",
  ["ms_unity_path_builder", "ms_unity_scatter"], ["Define waypoints and choose the kind; smooth the curve where players walk.", "Add lamps and stones along the path; keep spacing relative to the character scale.", "Verify the endpoints and that colliders do not block the intended route."], "A linear structure must connect or surround areas."),
 ("scatter-dressing", "Unity scatter and dressing", "Populate areas with trees, rocks, crates and props using seeded scatter that snaps to ground.", "polish",
  ["ms_unity_scatter", "ms_unity_terrain_generate"], ["Choose props per zone and keep clearings around spawn and paths.", "Snap to the terrain and align only rocks and logs to normals.", "Count draw calls and use static batching or GPU instancing for the weakest target."], "A world looks empty or repetitive."),
 ("model-editing", "Unity model editing", "Array, mirror, align, distribute, group, rename, add colliders and set materials on selected objects with undo-safe edits.", "polish",
  ["ms_unity_model_tools", "ms_unity_scene_audit"], ["Inspect statistics and bounds first.", "Apply the smallest edit set and use dry_run on large selections.", "Re-audit the scene for missing components and duplicates."], "Models or props need bulk layout and collision fixes."),
 ("gameplay-kit", "Unity gameplay kit", "Generate compile-ready controllers, cameras, health, pickups, enemies and interaction scripts with prefabs and inputs.", "implementation",
  ["ms_unity_gameplay_kit", "ms_unity_script_check"], ["List kinds and choose the controller and supporting parts for the genre.", "Generate scripts and prefabs, then attach them to the player or level.", "Check compilation and play the scene for console errors."], "A working gameplay loop is required fast and safely."),
 ("ui-kit-screens", "Unity UI kit screens", "Build Canvas-based menus, HUDs and dialogs with anchors, layout groups, scalers and event wiring.", "design",
  ["ms_unity_ui_kit", "ms_unity_ui"], ["Choose the screen set and one theme.", "Generate with CanvasScaler reference resolution and safe-area handling.", "Check at two aspect ratios and verify EventSystem and button events."], "The project needs menus, HUD, settings, shop or dialogue."),
 ("terrain-blockout", "Unity terrain and blockout", "Create terrain from presets and block out levels before art; query heights to place gameplay anchors.", "design",
  ["ms_unity_terrain_generate", "ms_unity_level_blockout"], ["Pick a preset or ASCII layout that fits the play flow.", "Generate and place spawn, goals and landmarks using sampled heights.", "Play the blockout to validate pacing and sight-lines."], "A level needs a layout with real height and scale."),
 ("material-lighting", "Unity materials and lighting", "Create materials for the active render pipeline and apply lighting presets and post settings that fit the mood.", "polish",
  ["ms_unity_material", "ms_unity_lighting_preset", "ms_unity_graphics"], ["Detect the render pipeline before choosing shaders.", "Apply a lighting preset and tune sun, ambient and fog.", "Verify materials render (no pink) and fallbacks exist for low tiers."], "A scene looks default-lit or materials are broken."),
 ("animation-controller", "Unity animation setup", "Create animation clips and Animator controllers with parameters, transitions and blend setups.", "implementation",
  ["ms_unity_animation_clip", "ms_unity_animator_controller"], ["Define the clips and loop flags.", "Build the controller with parameters and transitions with sensible exit times.", "Test transitions in play mode and read back the controller."], "A character, door or prop needs animation states."),
 ("navmesh-ai", "Unity navigation", "Bake NavMesh surfaces, add agents and verify paths for enemies and NPCs.", "implementation",
  ["ms_unity_navmesh", "ms_unity_physics"], ["Mark walkable and non-walkable geometry.", "Bake and add agents with sane radius and speed.", "Test a path between two points and fix gaps."], "NPCs or enemies must move through the level."),
 ("particles-vfx", "Unity particle effects", "Create fire, smoke, magic, impact and ambient particle systems with budgeted counts.", "polish",
  ["ms_unity_particle_effect", "ms_unity_camera"], ["Pick the effect and tune colour, lifetime and emission.", "Place it at gameplay anchors, not randomly.", "Cap max particles and test on the weakest tier."], "An effect is needed to sell an action or atmosphere."),
 ("project-audit-loop", "Unity project audit loop", "Audit scenes, scripts, console and tests, then fix the dominant defect first.", "validation",
  ["ms_unity_scene_audit", "ms_unity_console", "ms_unity_run_tests", "ms_unity_profiler"], ["Read the console and audit the scene.", "Fix compile errors and missing references first.", "Run tests and profile before reporting."], "Anything was generated or refactored and must be proven to run."),
],
"roblox": [
 ("building-generator", "Roblox building generation", "Generate multi-floor buildings with foundations, windows, lintels and doors as Models inside Studio.", "implementation",
  ["ms_roblox_building_generator", "ms_roblox_model_tools"], ["Choose kind, size and floors and generate at an exact position and rotation.", "Group, name and anchor the model; keep parts within the part-count budget.", "Verify the model exists with expected children via a read-back."], "A map needs houses, shops, towers or a village."),
 ("path-fence-builder", "Roblox roads, fences and bridges", "Lay paths, fences, rails, walls and bridges along waypoints with consistent spacing and collisions.", "implementation",
  ["ms_roblox_path_builder", "ms_roblox_scatter"], ["Define waypoints and the kind; keep widths sized for avatars.", "Add lamps or stones and check Humanoid traversal.", "Read back and confirm endpoints and anchored state."], "Linear structures connect or enclose areas."),
 ("scatter-dressing", "Roblox scatter and dressing", "Populate zones with trees, rocks, bushes and props via seeded scatter with raycast ground snapping.", "polish",
  ["ms_roblox_scatter", "ms_roblox_terrain_generate"], ["Choose props and density per zone; keep spawn and paths clear.", "Snap to terrain with raycasts and vary scale and rotation.", "Watch instance counts and streaming impact."], "A map feels empty or repetitive."),
 ("model-editing", "Roblox model editing", "Bulk-edit parts: arrays, mirrors, alignment, distribution, grouping, renaming, anchoring and material sets.", "polish",
  ["ms_roblox_model_tools", "ms_roblox_measure", "ms_roblox_transform"], ["Measure bounds and counts first.", "Apply the smallest edit set; wrap risky changes in ChangeHistory.", "Re-measure and compare."], "Parts need bulk layout or cleanup."),
 ("gameplay-kit", "Roblox gameplay kit", "Install server-authoritative gameplay modules: checkpoints, pickups, kill bricks, spawners, doors and leaderboards.", "implementation",
  ["ms_roblox_gameplay_kit", "ms_roblox_script_manage", "ms_roblox_playtest"], ["List kinds and pick the loop pieces for the genre.", "Install with remotes validated server-side.", "Playtest and read output for errors."], "A playable loop is required quickly and safely."),
 ("ui-kit-screens", "Roblox UI kit and audit", "Build responsive ScreenGuis (menus, HUD, shop) with UDim2 scale layout and audit them for overflow.", "design",
  ["ms_roblox_ui_kit", "ms_roblox_ui_audit"], ["Choose the screen set and one theme.", "Generate with scale-based sizes, constraints and safe-area handling.", "Run ui_audit at phone, tablet and desktop sizes."], "The game needs menus, HUD, shop or dialogs."),
 ("terrain-blockout", "Roblox terrain and blockout", "Generate Terrain from presets and block out levels with parts before final art.", "design",
  ["ms_roblox_terrain_generate", "ms_roblox_terrain", "ms_roblox_level_blockout"], ["Pick a preset or ASCII map matching the play flow.", "Generate and sample heights to place spawn and goals.", "Playtest the blockout for pacing."], "A new map needs layout and height variation."),
 ("lighting-atmosphere", "Roblox lighting and atmosphere", "Set Lighting, Atmosphere, Sky and post effects so first view reads clearly.", "polish",
  ["ms_roblox_lighting", "ms_roblox_post_processing", "ms_roblox_camera"], ["Choose a mood and time of day.", "Tune Atmosphere density, Bloom and ColorCorrection modestly.", "Provide a low-quality fallback."], "The place looks flat or default-lit."),
 ("animation-tween", "Roblox tweens and keyframes", "Create TweenService sequences and KeyframeSequences for doors, platforms, pickups and characters.", "implementation",
  ["ms_roblox_tween_animation", "ms_roblox_keyframe_sequence", "ms_roblox_constraint_preset"], ["Define start and end states with easing.", "Use constraints for physical motion and tweens for scripted motion.", "Playtest for jitter and network ownership issues."], "Objects or characters need motion."),
 ("effects", "Roblox particles and effects", "Create particle emitters and beams for fire, smoke, magic and impacts with budgets, then validate the cost in a playtest.", "validation",
  ["ms_roblox_particle_effect", "ms_roblox_attributes"], ["Pick the effect and tune lifetime and rate.", "Attach to anchors, not floating parts.", "Cap rates for mobile."], "An action or ambience needs VFX."),
 ("collision-physics", "Roblox collision and physics", "Set collision groups, constraints and anchored state so physics behaves predictably, then optimise anchored/CanCollide flags and verify with a playtest.", "optimization",
  ["ms_roblox_collision_groups", "ms_roblox_constraint_preset", "ms_roblox_optimize"], ["Define groups and which collide.", "Apply constraint presets and confirm limits.", "Optimise anchored and CanCollide flags."], "Physics is flaky or too expensive."),
 ("project-audit-loop", "Roblox place audit loop", "Audit world stats, scripts and output, then fix the dominant defect first.", "validation",
  ["ms_roblox_world_stats", "ms_roblox_script_inventory", "ms_roblox_playtest", "ms_roblox_changes"], ["Collect world stats and script inventory.", "Fix output errors first, then performance outliers.", "Playtest again and review the change list."], "Anything was generated or refactored and must be proven to run."),
],
"blender": [
 ("building-modeling", "Blender building modelling", "Generate parametric buildings with separate material slots and ground-centred origins.", "implementation",
  ["ms_blender_building", "ms_blender_uv_unwrap", "ms_blender_mesh_stats"], ["Choose style, footprint, floors and roof.", "Generate, unwrap and check material slots.", "Check triangle count against the target engine."], "Architecture is needed as a clean mesh."),
 ("prop-modeling", "Blender prop modelling", "Model trees, rocks, furniture, weapons, fences and structures from bmesh primitives with named material slots.", "implementation",
  ["ms_blender_prop_generator", "ms_blender_modifier_stack", "ms_blender_assign_material"], ["Pick the prop kind and size; set seed for variation.", "Add bevel and smooth shading only where needed.", "Check dimensions and material slots, then export."], "A game asset set is needed quickly with consistent scale."),
 ("level-blockout", "Blender level blockout", "Create blockouts from ASCII maps with grouped meshes per material for fast engine import.", "design",
  ["ms_blender_level_blockout", "ms_blender_export"], ["Draw the map with walls, floors and doors.", "Generate and check scale against the character.", "Export for the engine and playtest the layout."], "A level layout must be validated before art."),
 ("terrain-environment", "Blender terrain and environment", "Generate terrain with noise, erosion and material splits, plus world lighting.", "design",
  ["ms_blender_terrain", "ms_blender_world", "ms_blender_scatter"], ["Pick a terrain preset and scale.", "Add the world and scatter vegetation.", "Check polygon budget and export."], "Landscapes or backdrops are needed."),
 ("material-authoring", "Blender procedural materials", "Create procedural PBR materials (wood, metal, stone, fabric, water...) with real node trees.", "polish",
  ["ms_blender_procedural_material", "ms_blender_create_material", "ms_blender_assign_material"], ["Choose the material and scale.", "Create and assign to slots.", "Preview render and check export-friendliness."], "Surfaces look flat or default."),
 ("rigging-weights", "Blender rigging", "Build armatures with controls, parent meshes with weights and read the rig back.", "implementation",
  ["ms_blender_armature_rig", "ms_blender_rig_info", "ms_blender_shape_keys"], ["Choose a rig template and scale it to the mesh.", "Parent with automatic weights.", "Pose-test extremes and fix deformation."], "A character or creature must move."),
 ("animation-motion", "Blender animation", "Create motion presets, actions and keyframes with easing and cyclic loops.", "implementation",
  ["ms_blender_motion_preset", "ms_blender_animation_actions", "ms_blender_keyframes"], ["Choose the preset and cycle length.", "Name actions for engine import.", "Check loops for popping."], "Props, logos or characters need animation."),
 ("mesh-cleanup-lod", "Blender cleanup and LODs", "Clean topology, merge doubles, fix normals and generate LODs for game budgets.", "optimization",
  ["ms_blender_mesh_cleanup", "ms_blender_lod_generate", "ms_blender_mesh_stats"], ["Run stats first.", "Clean, then generate LODs with ratios.", "Compare silhouettes and counts."], "A mesh is heavy, dirty or inconsistent."),
 ("scene-render", "Blender studio and render", "Set up turntables, three-point lighting and renders for previews.", "polish",
  ["ms_blender_scene_studio", "ms_blender_render_settings", "ms_blender_render"], ["Frame the subject with a studio rig.", "Choose engine and samples.", "Render and inspect."], "A showcase image or turntable is needed."),
 ("vfx-presets", "Blender VFX", "Create particle VFX presets (fire, smoke, sparks, magic) for previews and baking.", "polish",
  ["ms_blender_vfx_preset", "ms_blender_physics"], ["Choose the effect and size.", "Tune emission and lifetime.", "Bake or render a preview."], "Effects or simulations are needed."),
 ("curves-paths", "Blender curves and paths", "Create curves for roads, rails, cables and camera paths with bevel and resample.", "implementation",
  ["ms_blender_curve_path", "ms_blender_modifier_stack"], ["Place control points and choose the profile.", "Convert to mesh when needed.", "Check normals and UVs."], "Linear structures or flythroughs are needed."),
 ("export-pipeline", "Blender export pipeline", "Export to glTF, FBX or OBJ with correct scale, axes, materials and naming for each engine.", "validation",
  ["ms_blender_export", "ms_blender_mesh_stats", "ms_blender_scene_summary"], ["Check units, scale and applied transforms.", "Export with the engine preset.", "Re-import or inspect the file for correctness."], "Assets must move into Unity, Godot or Roblox."),
],
}


def load(name):
    with open(os.path.join(RT, name), encoding="utf-8") as f:
        return json.load(f)


def save(name, data):
    with open(os.path.join(RT, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)


def build():
    T.ensure_loaded()
    skills, packs, cap = load("skills.json"), load("skill-packs.json"), load("capability-index.json")
    tpls = {}
    for k, v in skills.items():
        if v.get("capabilityDomain") == "studio-craft" and v.get("engine") in S and v["engine"] not in tpls:
            tpls[v["engine"]] = v
    new, by_engine = {}, {}
    for eng, rows in S.items():
        for slug, name, desc, role, tools, steps, when in rows:
            sid = f"{eng}-native-{slug}"
            for t in tools:
                if t not in T.REGISTRY:
                    raise SystemExit(f"{sid}: unknown tool {t}")
            rec = copy.deepcopy(tpls[eng])
            rec.update({
                "name": name, "description": desc, "engine": eng, "category": rec.get("category", "studio-craft"),
                "tags": [eng, "native-tools", "toolcraft", slug.split("-")[0]], "capabilityDomain": DOMAIN, "capabilityRole": role,
                "whenToUse": when,
                "steps": ["Inspect the open project and the current state of what you are about to change (read before write)."] + steps + [
                    "Drive the work through the real native tools: " + ", ".join(tools) + " (use each tool's live schema; do not invent parameters).",
                    "Read the result back with the matching list/get tool and fix the first defect before polishing.",
                    "Report what exists now, what was verified and any remaining limits."],
                "deliverables": ["The requested result exists in the real project", "Native read-back or validation evidence", "Notes on seeds, parameters and how to regenerate"],
                "qualityGates": ["Uses the native ms_* tools instead of hand-written one-off code when one fits", "Result loads with no engine errors", "Looks intentional rather than template-generated (vary seed, size, colour)", "Fits the weakest-target budget", "State read back before claiming success"],
                "relatedSkills": [f"{eng}-native-{r[0]}" for r in rows if r[0] != slug][:4],
                "nativeTools": tools,
            })
            rec["engineExecutionContract"]["engine"] = eng
            new[sid] = rec
            by_engine.setdefault(eng, []).append(sid)
    skills.update(new)
    save("skills.json", skills)
    ids = list(new)
    packs[PACK] = {"name": "Native Toolcraft Expansion (6.28.2)", "description": f"{len(ids)} engine skills that drive the real ms_<engine>_* native toolkits for building, modelling, scattering, UI, terrain, animation, materials and audits across Roblox, Unity, Godot and Blender.",
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
    pm_path = os.path.join(RT, "product-manifest.json")
    pm = load("product-manifest.json")
    pm.setdefault("catalogue", {})["skills"] = len(skills)
    save("product-manifest.json", pm)
    return len(new), len(skills)


if __name__ == "__main__":
    n, total = build()
    print(f"added/updated {n} skills; total {total}")
