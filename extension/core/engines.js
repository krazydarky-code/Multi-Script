// SPDX-License-Identifier: GPL-3.0-or-later
// core/engines.js - native-tool knowledge for every engine EXCEPT Roblox Studio.
//
// WHY THIS EXISTS
// Roblox Studio's MCP exposes one flat tool per action, so the JSON transport
// alone is enough: {"command":"execute_luau","params":{...}}. The other engines
// do not look like that, and the difference - not the transport - is what makes
// them "not work properly":
//
//   * Unity MCP is ACTION-DISPATCH. There is no `get_hierarchy` tool; there is
//     `manage_scene` with an `action` string. A model that has just learned
//     Roblox's shape writes {"command":"get_hierarchy"} and gets "unknown
//     command". This is the single most common Unity failure, and resolveAction
//     below repairs it automatically.
//   * Godot MCP is flat BUT camelCase with `projectPath` required everywhere, and
//     `list_projects` takes `directory` instead. `path`, `project_path` and
//     `projectDir` all fail.
//   * Blender MCP is code-execution based, so the failure mode is a JSON-escape
//     bug inside a long code string, not a wrong tool name.
//
// So the TRANSPORT stays plain JSON everywhere (MCP itself is JSON-RPC, and every
// tool takes JSON-schema'd params - a second wire format would only add parser
// surface and split the camouflage/parse-error handling). What changes per engine
// is the VOCABULARY: the exact tool names, the required parameter spellings, the
// action-dispatch indirection, and the curated gotchas.
//
// PURITY: no DOM, no chrome.*, no timers. Everything here is data + pure
// functions so it is unit-testable in plain node (tests/test_engine_tool_layer.js).
//
// PROVENANCE - how each fact below was established, so nothing is a guess:
//   [schema]  read out of the shipped package build (Godot 0.1.1, read from the
//             published tarball's build/index.js inputSchema blocks)
//   [ref]     read out of the vendored upstream reference in vendor/
//   [live]    recorded from an actual observed failure in this codebase
// If a fact cannot be attributed, it is not here.
// eslint-disable-next-line no-unused-vars
const ZSEngine = (() => {
  "use strict";

  // ── Godot (npx @coding-solo/godot-mcp@0.1.1) ─────────────────────────────
  // [schema] 14 tools, verified from the published package. projectPath is
  // camelCase and REQUIRED on every project-scoped tool; list_projects is the one
  // exception and takes `directory`.
  const GODOT_TOOLS = {
    launch_editor: { req: ["projectPath"], cat: "tool" },
    run_project: { req: ["projectPath"], cat: "generate" },
    get_debug_output: { req: [], cat: "read" },
    stop_project: { req: [], cat: "edit" },
    get_godot_version: { req: [], cat: "read" },
    list_projects: { req: ["directory"], cat: "read" },
    get_project_info: { req: ["projectPath"], cat: "read" },
    create_scene: { req: ["projectPath", "scenePath"], cat: "edit" },
    add_node: { req: ["projectPath", "scenePath", "nodeType", "nodeName"], cat: "edit" },
    load_sprite: { req: ["projectPath", "scenePath", "nodePath", "texturePath"], cat: "edit" },
    export_mesh_library: { req: ["projectPath", "scenePath", "outputPath"], cat: "generate" },
    save_scene: { req: ["projectPath", "scenePath"], cat: "edit" },
    get_uid: { req: ["projectPath", "filePath"], cat: "read" },
    update_project_uids: { req: ["projectPath"], cat: "edit" },
  };
  // Required-shape templates for the non-Roblox engines, same reasoning as
  // ROBLOX_TEMPLATES: Unity is ACTION-DISPATCH and Godot is camelCase with
  // projectPath everywhere, and both are easy to get wrong from prose alone.
  // `PROJ` stands for the absolute project folder; Unity's `act` shows the
  // action-as-param shape that is the single most common Unity mistake.
  const ENGINE_TEMPLATES = {
    launch_editor:
      '{"command":"launch_editor","params":{"projectPath":"<PROJ>"}}',
    run_project:
      '{"command":"run_project","params":{"projectPath":"<PROJ>"}}',
    update_project_uids:
      '{"command":"update_project_uids","params":{"projectPath":"<PROJ>"}}',
    create_scene:
      '{"command":"create_scene","params":{"projectPath":"<PROJ>","scenePath":"res://scenes/Main.tscn"}}',
    add_node:
      '{"command":"add_node","params":{"projectPath":"<PROJ>","scenePath":"res://scenes/Main.tscn","nodeType":"Node2D","nodeName":"Player"}}',
    load_sprite:
      '{"command":"load_sprite","params":{"projectPath":"<PROJ>","scenePath":"res://scenes/Main.tscn","nodePath":"/root/Main/Player","texturePath":"res://art/player.png"}}',
    save_scene:
      '{"command":"save_scene","params":{"projectPath":"<PROJ>","scenePath":"res://scenes/Main.tscn"}}',
    get_project_info:
      '{"command":"get_project_info","params":{"projectPath":"<PROJ>"}}',
    list_projects:
      '{"command":"list_projects","params":{"directory":"C:/games"}}',
    export_mesh_library:
      '{"command":"export_mesh_library","params":{"projectPath":"<PROJ>","scenePath":"res://scenes/Assets.tscn","outputPath":"res://assets.meshlib"}}',
    get_uid:
      '{"command":"get_uid","params":{"projectPath":"<PROJ>","filePath":"res://scenes/Main.tscn"}}',
    // Godot: the three zero-required-param tools. They still get a template
    // because a model that has been writing projectPath on every other call
    // invents one here too - and `stop_project` with a stray projectPath is a
    // rejected call. Showing the minimal correct envelope prevents that.
    stop_project:
      '{"command":"stop_project","params":{}}',
    get_debug_output:
      '{"command":"get_debug_output","params":{}}',
    get_godot_version:
      '{"command":"get_godot_version","params":{}}',
    // Unity: the action goes INSIDE params.action. This is the template that
    // fixes "get_hierarchy is not a tool".
    manage_scene:
      '{"command":"manage_scene","params":{"action":"get_hierarchy","page_size":50}}',
    manage_gameobject:
      '{"command":"manage_gameobject","params":{"action":"create","name":"Player","primitive_type":"Capsule"}}',
    manage_components:
      '{"command":"manage_components","params":{"action":"add","target":"Player","component_type":"Rigidbody"}}',
    manage_asset:
      '{"command":"manage_asset","params":{"action":"search","path":"Assets/","search_pattern":"Player"}}',
    manage_editor:
      '{"command":"manage_editor","params":{"action":"play"}}',
    manage_prefabs:
      '{"command":"manage_prefabs","params":{"action":"get_info","prefab_path":"Assets/Prefabs/Player.prefab"}}',
    manage_material:
      '{"command":"manage_material","params":{"action":"create","name":"NewMat","path":"Assets/Materials/NewMat.mat"}}',
    manage_texture:
      '{"command":"manage_texture","params":{"action":"create","name":"NewTex","path":"Assets/Textures/NewTex.png","width":512,"height":512}}',
    manage_ui:
      '{"command":"manage_ui","params":{"action":"get_visual_tree","path":"Assets/UI/Main.uxml"}}',
    manage_camera:
      '{"command":"manage_camera","params":{"action":"screenshot","include_image":true}}',
    manage_graphics:
      '{"command":"manage_graphics","params":{"action":"pipeline_get_info"}}',
    manage_packages:
      '{"command":"manage_packages","params":{"action":"list_packages"}}',
    manage_physics:
      '{"command":"manage_physics","params":{"action":"raycast","origin":{"x":0,"y":1,"z":0},"direction":{"x":0,"y":-1,"z":0},"max_distance":100}}',
    manage_probuilder:
      '{"command":"manage_probuilder","params":{"action":"get_mesh_info","gameobject_name":"Platform"}}',
    manage_profiler:
      '{"command":"manage_profiler","params":{"action":"get_frame_timing"}}',
    unity_reflect:
      '{"command":"unity_reflect","params":{"action":"get_type","type_name":"UnityEngine.Transform"}}',
    unity_docs:
      '{"command":"unity_docs","params":{"action":"lookup","query":"Rigidbody AddForce"}}',
    batch_execute:
      '{"command":"batch_execute","params":{"commands":[{"tool":"manage_scene","params":{"action":"get_hierarchy"}},{"tool":"read_console","params":{"action":"get"}}]}}',
    read_console:
      '{"command":"read_console","params":{"action":"get"}}',
    find_gameobjects:
      '{"command":"find_gameobjects","params":{"search_term":"Player"}}',
    create_script:
      '{"command":"create_script","params":{"path":"Assets/Scripts/PlayerController.cs","contents":"using UnityEngine;\\n\\npublic class PlayerController : MonoBehaviour\\n{\\n    void Start() { Debug.Log(\\"ready\\"); }\\n}\\n"}}',
    script_apply_edits:
      '{"command":"script_apply_edits","params":{"path":"Assets/Scripts/PlayerController.cs","edits":[{"old_string":"void Start() {\\n}","new_string":"void Start() {\\n    Debug.Log(\\"ready\\");\\n}"}]}}',
    validate_script:
      '{"command":"validate_script","params":{"uri":"Assets/Scripts/PlayerController.cs"}}',
    get_sha:
      '{"command":"get_sha","params":{"uri":"Assets/Scripts/PlayerController.cs"}}',
    // Unity flat tools that were shipping without a copyable shape. Each one is
    // a real step in the change -> verify cycle, so a malformed call breaks the
    // loop at exactly the point the model is trying to prove its work.
    set_active_instance:
      '{"command":"set_active_instance","params":{"instance_path":"C:/Projects/MyGame"}}',
    refresh_unity:
      '{"command":"refresh_unity","params":{}}',
    apply_text_edits:
      '{"command":"apply_text_edits","params":{"uri":"Assets/Scripts/PlayerController.cs","edits":[{"old_string":"void Start() {\\n}","new_string":"void Start() {\\n    Debug.Log(\\"ready\\");\\n}"}]}}',
    delete_script:
      '{"command":"delete_script","params":{"uri":"Assets/Scripts/OldController.cs"}}',
    execute_menu_item:
      '{"command":"execute_menu_item","params":{"menu_path":"GameObject/Create Empty"}}',
    run_tests:
      '{"command":"run_tests","params":{"mode":"EditMode"}}',
    get_test_job:
      '{"command":"get_test_job","params":{"job_id":"<id returned by run_tests>"}}',
    find_in_file:
      '{"command":"find_in_file","params":{"uri":"Assets/Scripts/PlayerController.cs","pattern":"Debug.Log"}}',
    execute_custom_tool:
      '{"command":"execute_custom_tool","params":{"tool_name":"<name advertised by the project>","parameters":{}}}',
    // Blender: Python in a JSON string. The escaped quotes are the whole point of
    // showing this - an unescaped " is the observed failure mode.
    execute_blender_code:
      '{"command":"execute_blender_code","params":{"code":"import bpy\\nprint(len(bpy.data.objects))"}}',
    get_object_info:
      '{"command":"get_object_info","params":{"object_name":"Cube"}}',
    // Blender read-back. get_viewport_screenshot returns an IMAGE this assistant
    // cannot see (same trap as Roblox screen_capture) - the template exists so
    // the call shape is right, and the note says plainly not to interpret it.
    get_scene_info:
      '{"command":"get_scene_info","params":{}}',
    get_viewport_screenshot:
      '{"command":"get_viewport_screenshot","params":{"max_size":800}}',
  };

  const GODOT_NOTES = {
    launch_editor:
      "projectPath is REQUIRED and must be the ABSOLUTE path of the folder that CONTAINS project.godot - " +
      "not the project.godot file itself, not a res:// path, not a relative path. " +
      'Example: {"command":"launch_editor","params":{"projectPath":"C:/games/MyGame"}}.',
    run_project:
      "Runs the project in debug mode and streams output. projectPath is REQUIRED and must be the ABSOLUTE path of " +
      "the folder that CONTAINS project.godot - not the project.godot file itself, not a res:// path, not a relative " +
      "path. There is no separate scene argument - to run a specific scene, set it as the main scene in the project " +
      "first, or open it in the editor. After it starts, call get_debug_output to read the console, and ALWAYS call " +
      "stop_project when you are done or the next run can fail with 'already running'.",
    get_debug_output:
      "Takes NO parameters. Returns the console output and errors from the running project. This is the ONLY " +
      "way to see Godot runtime errors, so call it after every run_project and after any scene change.",
    stop_project:
      "Takes NO parameters. Call it after EVERY run_project - a project left running holds the project folder " +
      "and makes the next run_project or launch_editor fail. Do not skip it because the run looked successful.",
    get_godot_version:
      "Takes NO parameters. Call this ONCE at the start of a Godot session to confirm the server found a real " +
      "Godot binary; if it errors, GODOT_PATH is not set on the user's machine and every other tool will fail.",
    list_projects:
      "Takes `directory` (NOT projectPath) - an absolute folder to scan for Godot projects. Use it to find the " +
      "project path when the user has not given you one. Returns the projects found under that folder.",
    get_project_info:
      "projectPath is the absolute folder containing project.godot. Returns the project metadata. Call this " +
      "before changing anything: it is the authoritative source for the path you must reuse in every later call.",
    create_scene:
      "Requires projectPath AND scenePath. scenePath is the scene's path INSIDE the project and should end in " +
      '.tscn, e.g. "res://scenes/Level1.tscn" or "scenes/Level1.tscn" - do not pass an absolute OS path here. ' +
      "projectPath stays the absolute folder on disk.",
    add_node:
      "Requires projectPath, scenePath, nodeType AND nodeName. nodeType must be a real Godot class name " +
      "(Node2D, Sprite2D, CharacterBody2D, Control, Label, Camera2D, ...) - not a made-up name. Use the " +
      "scene's root node name as the parent to attach at the top level.",
    load_sprite:
      "Requires projectPath, scenePath, nodePath AND texturePath. nodePath identifies the existing Sprite2D node " +
      "inside the scene; texturePath is the texture's path inside the project (res://...). The sprite node must " +
      "already exist - use add_node first if it does not.",
    export_mesh_library:
      "Requires projectPath, scenePath AND outputPath. Exports the scene as a MeshLibrary resource for GridMap. " +
      "outputPath is where the .tres/.res is written inside the project.",
    save_scene:
      "Requires projectPath AND scenePath. Scene edits made through add_node/load_sprite are NOT durable until " +
      "you call save_scene - always save, then re-read with get_project_info or the editor to confirm.",
    get_uid:
      "Godot 4.4+ only. Requires projectPath and filePath; returns the file's UID. On older Godot this tool is " +
      "not available - do not rely on it for a project you have not version-checked with get_godot_version.",
    update_project_uids:
      "Godot 4.4+ only. Requires projectPath. Resaves resources to refresh UID references - use it after moving " +
      "or renaming files on disk, which otherwise leaves broken references.",
  };

  // ── Unity (CoplayDev unity-mcp v10.2.0) ─────────────────────────────────
  // [ref] tool names and action vocabularies read from
  // vendor/CoplayDev-unity-mcp/unity-mcp-skill/references/tools-reference.md.
  // Mixed model: some tools are flat (create_script, validate_script, run_tests)
  // and the rest are action-dispatch. ACTION_OWNERS is the reverse index that
  // makes the repair in resolveAction possible.
  const UNITY_TOOLS = {
    batch_execute: { req: ["commands"], cat: "tool" },
    set_active_instance: { req: [], cat: "tool" },
    refresh_unity: { req: [], cat: "edit" },
    manage_scene: { req: ["action"], cat: "tool", dispatch: true },
    find_gameobjects: { req: [], cat: "read" },
    manage_gameobject: { req: ["action"], cat: "edit", dispatch: true },
    manage_components: { req: ["action"], cat: "edit", dispatch: true },
    create_script: { req: [], cat: "edit" },
    script_apply_edits: { req: [], cat: "edit" },
    apply_text_edits: { req: [], cat: "edit" },
    validate_script: { req: [], cat: "read" },
    get_sha: { req: [], cat: "read" },
    delete_script: { req: [], cat: "edit" },
    manage_asset: { req: ["action"], cat: "edit", dispatch: true },
    manage_prefabs: { req: ["action"], cat: "edit", dispatch: true },
    manage_material: { req: ["action"], cat: "edit", dispatch: true },
    manage_texture: { req: ["action"], cat: "edit", dispatch: true },
    manage_ui: { req: ["action"], cat: "edit", dispatch: true },
    manage_editor: { req: ["action"], cat: "tool", dispatch: true },
    execute_menu_item: { req: [], cat: "edit" },
    read_console: { req: ["action"], cat: "read", dispatch: true },
    run_tests: { req: [], cat: "generate" },
    get_test_job: { req: [], cat: "read" },
    find_in_file: { req: [], cat: "read" },
    execute_custom_tool: { req: [], cat: "tool" },
    manage_camera: { req: ["action"], cat: "screen", dispatch: true },
    manage_graphics: { req: ["action"], cat: "generate", dispatch: true },
    manage_packages: { req: ["action"], cat: "tool", dispatch: true },
    manage_physics: { req: ["action"], cat: "generate", dispatch: true },
    manage_probuilder: { req: ["action"], cat: "edit", dispatch: true },
    manage_profiler: { req: ["action"], cat: "read", dispatch: true },
    unity_reflect: { req: ["action"], cat: "read", dispatch: true },
    unity_docs: { req: ["action"], cat: "read", dispatch: true },
  };
  // action -> owning tool(s). Built from the reference doc. An action listed
  // under TWO owners is genuinely ambiguous and resolveAction refuses to guess.
  const UNITY_ACTION_OWNERS = (() => {
    const m = {};
    const add = (tool, actions) => {
      for (const a of actions) (m[a] = m[a] || []).push(tool);
    };
    add("manage_scene", ["create", "get_active", "get_build_settings", "get_hierarchy", "load", "save", "scene_view_frame", "screenshot"]);
    add("manage_gameobject", ["create", "delete", "duplicate", "look_at", "modify", "move_relative"]);
    add("manage_components", ["add", "remove", "set_property"]);
    add("manage_asset", ["create", "create_folder", "delete", "duplicate", "get_info", "move", "rename", "search"]);
    add("manage_prefabs", ["create_from_gameobject", "get_hierarchy", "get_info", "modify_contents"]);
    add("manage_material", ["assign_material_to_renderer", "create", "get_material_info", "set_material_color", "set_material_shader_property", "set_renderer_color"]);
    add("manage_texture", ["apply_gradient", "apply_pattern", "create"]);
    add("manage_ui", ["attach_ui_document", "create", "create_panel_settings", "get_visual_tree", "read", "update"]);
    add("manage_editor", ["add_layer", "add_tag", "close_prefab_stage", "deploy_package", "open_prefab_stage", "pause", "play", "remove_layer", "remove_tag", "restore_package", "save_prefab_stage", "set_active_tool", "stop"]);
    add("read_console", ["clear", "get"]);
    add("manage_camera", ["add_extension", "create_camera", "ensure_brain", "force_camera", "list_cameras", "ping", "release_override", "screenshot", "screenshot_multiview", "set_aim", "set_blend", "set_body", "set_noise", "set_priority"]);
    add("manage_graphics", ["bake_create_light_probe_group", "bake_create_reflection_probe", "bake_start", "bake_status", "feature_add", "feature_list", "feature_reorder", "feature_toggle", "ping", "pipeline_get_info", "pipeline_set_quality", "stats_get", "stats_get_memory", "volume_add_effect", "volume_create", "volume_create_profile", "volume_get_info", "volume_list_effects", "volume_set_effect"]);
    add("manage_packages", ["add_package", "add_registry", "list_packages", "remove_package", "search_packages", "status"]);
    add("manage_physics", ["add_joint", "apply_force", "assign_physics_material", "configure_joint", "configure_rigidbody", "create_physics_material", "get_collision_matrix", "get_settings", "linecast", "overlap", "ping", "raycast", "raycast_all", "set_collision_matrix", "set_settings", "shapecast", "simulate_step", "validate"]);
    add("manage_probuilder", ["auto_smooth", "center_pivot", "create_shape", "duplicate_and_flip", "extrude_faces", "get_mesh_info", "ping", "select_faces", "validate_mesh", "weld_vertices"]);
    add("manage_profiler", ["frame_debugger_disable", "frame_debugger_enable", "frame_debugger_get_events", "get_counters", "get_frame_timing", "get_object_memory", "memory_compare_snapshots", "memory_list_snapshots", "memory_take_snapshot", "ping", "profiler_set_areas", "profiler_start", "profiler_status", "profiler_stop"]);
    add("unity_reflect", ["get_member", "get_type", "search"]);
    add("unity_docs", ["get_doc", "get_manual", "get_package_doc", "lookup"]);
    return m;
  })();
  const UNITY_NOTES = {
    manage_scene:
      "ACTION-DISPATCH: there is no separate tool per scene operation. The command is always `manage_scene` and " +
      'the operation goes in params.action. Correct: {"command":"manage_scene","params":{"action":"get_hierarchy"}}. ' +
      'WRONG: {"command":"get_hierarchy"} - that is an ACTION, not a tool, and will be rejected as an unknown command. ' +
      "Common actions: get_hierarchy, get_active, create, load, save, screenshot, scene_view_frame, get_build_settings. " +
      "get_hierarchy is PAGINATED (page_size default 50, max 500) - pass the cursor back to page through a large scene.",
    manage_gameobject:
      'ACTION-DISPATCH: {"command":"manage_gameobject","params":{"action":"create", ...}} - not a `create_gameobject` tool. ' +
      "Actions: create, modify, delete, duplicate, move_relative, look_at. Set properties through the tool's own " +
      "properties argument, not by inventing extra top-level params.",
    manage_components:
      'ACTION-DISPATCH: {"command":"manage_components","params":{"action":"add"|"remove"|"set_property", ...}}. ' +
      "The component type is a real Unity class name (Rigidbody, BoxCollider, MeshRenderer, ...).",
    manage_asset:
      'ACTION-DISPATCH: {"command":"manage_asset","params":{"action":"search"|"create"|"create_folder"|"move"|' +
      '"rename"|"duplicate"|"delete"|"get_info", ...}}. Asset paths start with "Assets/".',
    manage_prefabs:
      'ACTION-DISPATCH: actions create_from_gameobject, get_hierarchy, get_info, modify_contents.',
    manage_material:
      'ACTION-DISPATCH: actions create, assign_material_to_renderer, set_material_color, set_renderer_color, ' +
      "get_material_info, set_material_shader_property. Set the shader property by its EXACT name (e.g. _BaseColor, " +
      "_Metallic) - a wrong name silently does nothing.",
    manage_texture:
      'ACTION-DISPATCH: actions create, apply_gradient, apply_pattern. This generates textures procedurally in Unity.',
    manage_ui:
      'ACTION-DISPATCH: actions create, update, read, get_visual_tree, attach_ui_document, create_panel_settings. ' +
      "This is UI Toolkit (UXML/USS), not the legacy uGUI Canvas - do not expect Canvas/Image components here.",
    manage_editor:
      'ACTION-DISPATCH: actions play, pause, stop, add_tag, remove_tag, add_layer, remove_layer, set_active_tool, ' +
      "open_prefab_stage, close_prefab_stage, save_prefab_stage, deploy_package, restore_package. " +
      "After script changes, wait for compilation (refresh_unity) BEFORE entering play mode, and ALWAYS leave the " +
      "editor in a clean state (stop play mode) when you are finished.",
    read_console:
      'ACTION-DISPATCH: actions get, clear. Use action "get" to read compile errors and runtime exceptions - this ' +
      "is the ONLY way to see them, so call it after every script change and after every play-mode test.",
    run_tests:
      "Starts a Unity Test Runner job and returns a job id immediately - it does NOT wait. Poll get_test_job until it " +
      "reports finished, then read the result. Do not assume the tests passed just because the call returned.",
    get_test_job:
      "Polls a test job started by run_tests. Pass the job id returned by run_tests.",
    script_apply_edits:
      "Preferred over apply_text_edits for structured C# edits. Read the file's current content first - the edit " +
      "anchors must match the file EXACTLY, byte for byte.",
    validate_script:
      "Checks a script for compile errors WITHOUT changing the project. Run it after create_script/script_apply_edits " +
      "and before entering play mode.",
    get_sha:
      "Returns the current hash of a script. Call it BEFORE and AFTER an edit to prove the file actually changed - " +
      "cheap, and it catches a silently-no-op edit.",
    manage_camera:
      'ACTION-DISPATCH: actions screenshot, screenshot_multiview, create_camera, list_cameras, force_camera, set_aim, ' +
      'set_body, set_blend, set_noise, set_priority, ensure_brain, release_override, add_extension, ping. ' +
      "For visual evidence use screenshot with include_image:true - the image comes back in the tool result.",
    manage_graphics:
      'ACTION-DISPATCH: actions volume_create, volume_add_effect, volume_set_effect, pipeline_get_info, ' +
      "pipeline_set_quality, feature_add, feature_list, feature_toggle, feature_reorder, stats_get, stats_get_memory, " +
      "bake_start, bake_status, bake_create_light_probe_group, bake_create_reflection_probe, volume_get_info, " +
      "volume_list_effects, volume_create_profile, ping.",
    manage_physics:
      'ACTION-DISPATCH: actions raycast, raycast_all, linecast, overlap, shapecast, simulate_step, add_joint, ' +
      "configure_joint, configure_rigidbody, create_physics_material, assign_physics_material, get_settings, " +
      "set_settings, get_collision_matrix, set_collision_matrix, apply_force, validate, ping.",
    manage_probuilder:
      'ACTION-DISPATCH: actions create_shape, select_faces, extrude_faces, weld_vertices, auto_smooth, center_pivot, ' +
      "duplicate_and_flip, get_mesh_info, validate_mesh, ping. Validate the mesh before exporting it to another engine.",
    manage_profiler:
      'ACTION-DISPATCH: actions profiler_start, profiler_stop, profiler_status, profiler_set_areas, get_frame_timing, ' +
      "get_counters, get_object_memory, memory_take_snapshot, memory_list_snapshots, memory_compare_snapshots, " +
      "frame_debugger_enable, frame_debugger_disable, frame_debugger_get_events, ping.",
    manage_packages:
      'ACTION-DISPATCH: actions list_packages, add_package, remove_package, search_packages, add_registry, status.',
    unity_reflect:
      'ACTION-DISPATCH: actions get_type, get_member, search. Use this to CHECK that a Unity API actually exists ' +
      "before writing code against it, instead of guessing a member name.",
    unity_docs:
      'ACTION-DISPATCH: actions lookup, get_doc, get_manual, get_package_doc. Use it to read the real Unity API docs ' +
      "rather than recalling them.",
    batch_execute:
      "Runs several Unity commands in ONE round trip. Use it for a sequence of independent edits instead of many " +
      "separate calls - much faster, and it keeps the editor from being touched between steps.",
    set_active_instance:
      "Targets a specific Unity Editor instance when more than one is connected. Call it first in a multi-instance setup.",
    create_script:
      "Creates a NEW .cs file at an Assets/ path. `contents` is the whole C# source as a JSON STRING - every " +
      'quote must be escaped as \\" and every newline as \\n. An unescaped quote is the classic failure here. ' +
      "After creating, call refresh_unity and wait for compilation, then validate_script, then read_console.",
    apply_text_edits:
      "Edits an existing file with anchored old_string/new_string pairs, applied IN ORDER and atomically (all " +
      "succeed or none). The anchors must match the file's CURRENT bytes exactly - read the file first and copy the " +
      "text verbatim. Preferred over rewriting a whole file: a smaller anchor keeps the change reviewable and " +
      "avoids clobbering unrelated edits.",
    delete_script:
      "Deletes a .cs file. Irreversible, and any scene object referencing the deleted class loses its behaviour - " +
      "confirm nothing still points at it (find_in_file, find_gameobjects) before deleting rather than after.",
    execute_custom_tool:
      "Runs a project-provided custom tool by name. The set is not fixed: run list_commands for the unity server " +
      "and use ONLY a tool name it actually advertises - do not invent one.",
    refresh_unity:
      "Forces Unity to refresh/recompile. Call it after writing or editing scripts and WAIT for it before entering " +
      "play mode or reading the console - otherwise you read the pre-compile state.",
    execute_menu_item:
      "Runs a Unity menu command by its exact path, e.g. \"File/Save Project\". Use it only when no dedicated tool " +
      "covers the action; the menu path must match the installed Unity version exactly.",
    find_gameobjects:
      "Finds GameObjects by name/path/component. Use it to get the exact object identity before modifying anything - " +
      "never assume a name from the user's description.",
    find_in_file:
      "Searches inside project files. Cheaper than reading whole scripts when you only need to confirm where " +
      "something is defined.",
  };

  // ── Blender ──────────────────────────────────────────────────────────────
  // [live] execute_blender_code is the tool this codebase has actually seen fail
  // (an unescaped " inside a Python string broke the JSON envelope). Blender MCP
  // servers differ, so the rule is deliberately discovery-first: we do NOT invent
  // tool names beyond the one we have evidence for.
  const BLENDER_TOOLS = {
    execute_blender_code: { req: ["code"], cat: "edit" },
    get_scene_info: { req: [], cat: "read" },
    get_object_info: { req: [], cat: "read" },
    get_viewport_screenshot: { req: [], cat: "screen" },
  };
  const BLENDER_NOTES = {
    execute_blender_code:
      "Runs Python inside Blender. The code goes in params.code as a JSON STRING, so every quote and newline inside " +
      'the Python MUST be JSON-escaped (\\" and \\n) - an unescaped " breaks the whole envelope and the command ' +
      "never runs. Prefer bpy.ops/bpy.data APIs and assign results to variables you can read back. " +
      "Blender runs headless in some setups, so do not depend on UI-only operators. " +
      "FORM SELECTION - read before adding any primitive: a sphere is almost never the right primitive. A limb, " +
      "shaft, pipe, neck, finger or barrel is a CYLINDER (taper the top loop - real limbs are not uniform). A plate, " +
      "housing, crate, screen, panel or machine part is a BOX - and you must subdivide and bevel its edges, because " +
      "a hard 90-degree corner catches no light and reads as programmer art. Anything that follows a path - cable, " +
      "hose, rope, vine, pipe run, tail, antenna - is a BEZIER CURVE swept with a bevel object and converted to mesh, " +
      "not a row of cylinders and not a sphere. Anything whose identity lives in its outline - gear, bracket, beam, " +
      "blade, key - is an EXTRUDED 2D PROFILE. Use bpy.ops.mesh.primitive_uv_sphere_add ONLY for things that are " +
      "genuinely spherical: an eyeball, a ball joint, a planet, a ball, a berry, a knob, a rivet head, a dome. " +
      "If you find yourself scaling a sphere on one axis to make it read as something else, that is the tell that " +
      "you chose the wrong primitive - delete it and build the right form. Call ms_form_guidance with " +
      'action="audit" and your part list before you build, and it will catch a sphere that should have been a ' +
      "cylinder or a box. For organic masses, metaballs are a blocking tool only - remesh and retopologise before " +
      "calling them done.",
    get_scene_info:
      "Read this BEFORE editing: it is the authoritative list of what is actually in the scene. Do not assume object " +
      "names from the user's description. On a model you (or another pass) built, also check the object TYPE mix: a " +
      "poly count spread dominated by low-poly UV spheres is the signature of a placeholder model that still needs " +
      "rebuilding, not detailing.",
    get_object_info:
      "Returns one object's transform, mesh and material data. Use it to verify scale, pivots and axes before export. " +
      "Also read the vertex count against the object's role: a limb carrying the vertex count of a default UV sphere " +
      "(482 verts at 32 segments) has almost certainly been left as one unmodified sphere.",
    get_viewport_screenshot:
      "Returns a rendered image of the viewport. Use it for visual evidence of a model, and note that the result " +
      "carries an image - a text-only assistant receives a text visual digest of it instead.",
  };

  // ── Roblox Studio: the `studio_id` contract ──────────────────────────────
  // [live] Roblox's official Studio MCP requires a `studio_id` argument on EVERY
  // tool that touches a place. Recorded straight out of this repo's own bridge log
  // (runtime/logs/bridge_debug.log):
  //
  //   -> tool  execute_luau(code, datamodel_type, studio_id)
  //   <- execute_luau (0.0s): execute_luau: invalid parameters: parameters.studio_id is required
  //   [roblox] stderr: WARN ... sent a request without studio_id but multiple studios are connected
  //
  // The last line is the whole reason this bug is INTERMITTENT rather than total:
  // the proxy SILENTLY auto-selects a Studio when exactly ONE is attached, so the
  // omission goes unnoticed, and then breaks the moment a second Studio window (or
  // a second `StudioMCP` process) is connected. That makes it invisible in a
  // single-Studio test and certain in a real multi-window session - which is
  // exactly why it needs documenting rather than only validating.
  //
  // `execute_luau` is the tool this repo has actually seen reject the call, but the
  // requirement is per-SERVER, not per-tool: any place-scoped Roblox tool takes it.
  const ROBLOX_STUDIO_ID = "studio_id";
  // Kept SHORT on purpose. This is appended to EVERY place-scoped note, so the
  // long version below (ROBLOX_NOTE, stated ONCE in the prompt) does not belong
  // here: repeating a paragraph on 16 tools bloated every note and pushed the
  // actual call SHAPE away from where the model reads it - which is how a model
  // ends up emitting "edits[0].old_string is required" (observed live).
  const ROBLOX_STUDIO_ID_SUFFIX =
    " Needed: params." + ROBLOX_STUDIO_ID + ' (exact "id" from list_roblox_studios).';
  const ROBLOX_NOTE =
    "Roblox Studio's MCP takes a " + ROBLOX_STUDIO_ID + " parameter on every place-scoped command " +
    "(execute_luau, multi_edit, script_read, script_search, script_grep, inspect_instance, search_game_tree, " +
    "get_studio_state, get_console_output, user_keyboard_input, user_mouse_input, start_stop_play, " +
    "wait_job_finished, insert_asset, search_asset, screen_capture). Omit it and the call fails with " +
    '"invalid parameters: parameters.studio_id is required". Run list_roblox_studios FIRST and copy the exact ' +
    '"id" of the Studio you mean into params.' + ROBLOX_STUDIO_ID + '. When only ONE Studio is open the proxy ' +
    "auto-selects it, so an omission looks harmless - but with TWO or more Studios connected every command that " +
    "drops it is rejected, so always pass it explicitly. Example: " +
    '{"command":"execute_luau","params":{"code":"return game.PlaceId","datamodel_type":"Edit","studio_id":"<id from list_roblox_studios>"}}.';

  // ── Required-shape templates ─────────────────────────────────────────────
  // A copyable envelope for the tools whose params are STRUCTURED (an array of
  // objects, or several required fields at once). These lead the tool's note, so
  // the model sees the exact required shape BEFORE any prose about semantics.
  //
  // This exists because of a real failure: `multi_edit` kept coming back as
  // "parameters.edits[0].old_string is required". The note described how
  // old_string SHOULD match (byte-for-byte, watch unicode, ...) but never showed
  // the call, so a model skimming for "what do I write" produced an edits entry
  // without old_string. Prose about a parameter cannot substitute for showing it.
  // `SID` stands for the studio_id the model must substitute.
  const ROBLOX_TEMPLATES = {
    // [schema] file_path is a TOP-LEVEL param of multi_edit; each entry of the
    // `edits` array holds only old_string / new_string (+ optional replace_all).
    // This template shipped with file_path INSIDE the edit object for several
    // releases - a shape the server rejects, which is precisely the
    // "parameters.edits[0].old_string is required"-class failure this whole
    // template mechanism was built to prevent.
    multi_edit:
      '{"command":"multi_edit","params":{"datamodel_type":"Edit","studio_id":"<SID>","file_path":"game.ServerScriptService.Main","edits":[{"old_string":"<exact current text, copied from script_read>","new_string":"<replacement text>"}]}}',
    // Creating a script is the one case where old_string is a deliberate empty
    // string - the highest-value variant to show, because it is the exception to
    // "old_string must be present and match".
    execute_luau:
      '{"command":"execute_luau","params":{"code":"return game.PlaceId","datamodel_type":"Edit","studio_id":"<SID>"}}',
    user_keyboard_input:
      '{"command":"user_keyboard_input","params":{"datamodel_type":"Client","studio_id":"<SID>","actions":[{"action":"keyPress","key_code":"Return"}]}}',
    user_mouse_input:
      '{"command":"user_mouse_input","params":{"datamodel_type":"Client","studio_id":"<SID>","actions":[{"action":"mouseButtonClick","mouse_button":"left","x":400,"y":300}]}}',
    inspect_instance:
      '{"command":"inspect_instance","params":{"path":"Workspace.Model.Part","studio_id":"<SID>"}}',
    script_read:
      '{"command":"script_read","params":{"target_file":"game.ServerScriptService.Main","studio_id":"<SID>"}}',
    script_search:
      '{"command":"script_search","params":{"keywords":"RunService","studio_id":"<SID>"}}',
    search_game_tree:
      '{"command":"search_game_tree","params":{"datamodel_type":"Edit","path":"Workspace","studio_id":"<SID>"}}',
    start_stop_play:
      '{"command":"start_stop_play","params":{"is_start":true,"studio_id":"<SID>"}}',
    wait_job_finished:
      '{"command":"wait_job_finished","params":{"jobId":"<jobId from an async call>","studio_id":"<SID>"}}',
    get_studio_state:
      '{"command":"get_studio_state","params":{"studio_id":"<SID>"}}',
    script_grep:
      '{"command":"script_grep","params":{"query":"Humanoid","studio_id":"<SID>"}}',
    // Build-surface tools. Provenance [schema]: the shapes below were read from
    // the live Roblox MCP server's published parameter schemas. The earlier
    // versions of these were GUESSED and several were wrong in ways that fail
    // silently or produce a confusing error:
    //   - generate_mesh wants `textPrompt`, NOT `prompt` (it also has a separate
    //     `async` flag and an optional `size`/`segmentation`/`partNames`).
    //   - generate_procedural_model wants `prompt` AND defaults to async - the
    //     server itself recommends async:true, so the template shows it.
    //   - insert_asset takes assetId as a STRING (a numeric-looking string),
    //     not a Number - passing 123456789 is coerced, but the schema is string.
    //   - screen_capture REQUIRES capture_id; without it the call is rejected.
    //   - wait_job_finished takes `jobId`, not `generation_id`.
    //   - search_game_tree REQUIRES datamodel_type ('Edit' in edit mode;
    //     'Edit' is rejected during playtest).
    insert_asset:
      '{"command":"insert_asset","params":{"assetId":"123456789","assetName":"Wooden Crate","assetType":"Model","parentPath":"game.Workspace","studio_id":"<SID>"}}',
    search_asset:
      '{"command":"search_asset","params":{"query":"wooden crate","assetType":"Model","maxResults":5,"studio_id":"<SID>"}}',
    get_console_output:
      '{"command":"get_console_output","params":{"studio_id":"<SID>"}}',
    screen_capture:
      '{"command":"screen_capture","params":{"capture_id":"ScreenCapture_1","studio_id":"<SID>"}}',
    generate_mesh:
      '{"command":"generate_mesh","params":{"textPrompt":"a low-poly wooden crate","segmentation":"auto","studio_id":"<SID>"}}',
    generate_procedural_model:
      '{"command":"generate_procedural_model","params":{"prompt":"a small stone watchtower","async":true,"studio_id":"<SID>"}}',
    // PROVENANCE [schema]: shapes below were read from the live Roblox MCP
    // server's published parameter schemas, not guessed. These are NOT in
    // ROBLOX_PLACE_TOOLS (they are global or a different family), so they take
    // no entry in that Set - but the ones that DO carry studio_id still need it.
    list_roblox_studios:
      '{"command":"list_roblox_studios","params":{}}',
    character_navigation:
      '{"command":"character_navigation","params":{"datamodel_type":"Client","studio_id":"<SID>","instance_path":"game.Workspace.Part"}}',
    skill:
      '{"command":"skill","params":{"skill_name":"rbx-docs-search","studio_id":"<SID>"}}',
  };
  // Tools that take NO studio_id, stated once so a model does not invent one.
  const ROBLOX_GLOBAL_TOOLS = ["list_roblox_studios", "subagent"];

  // ── Generic rules for any other MCP server ───────────────────────────────
  // [ref] runtime/mcp-presets.json explicitly says not to guess package names or
  // commands for Unreal/other servers, so the only honest guidance is discovery.
  const GENERIC_RULES =
    "DISCOVERY-FIRST: this server's command set is NOT documented in this prompt. Run list_mcp_servers, then " +
    "list_commands with that server's id, and use ONLY the exact tool names and parameter keys it advertises. " +
    "Never guess a tool name from another engine's vocabulary (Roblox names like execute_luau/multi_edit do not " +
    "exist here, and Unity's action names like get_hierarchy are not tools). If a tool's schema shows an `action` " +
    "parameter, the action goes INSIDE params.action - it is not a tool name of its own.";

  // ── Engine records ───────────────────────────────────────────────────────
  const ENGINES = {
    godot: {
      id: "godot",
      label: "Godot",
      tools: GODOT_TOOLS,
      notes: GODOT_NOTES,
      // Kept tight: the detail lives in the per-tool notes shown by list_commands.
      rules:
        "GODOT: flat tool set (one tool per action), all parameter names camelCase. Every project-scoped tool needs " +
        "params.projectPath = the ABSOLUTE path of the folder CONTAINING project.godot (never the .godot file, never " +
        "res://, never a relative path); list_projects is the one exception and takes params.directory. Scene paths " +
        "inside the project (scenePath, texturePath, outputPath) are project-relative and end in .tscn/.png/.tres. " +
        "Confirm the server with get_godot_version, learn the real path with get_project_info, and reuse that EXACT " +
        "string in every later call (Godot paths are case-sensitive on Linux and macOS). Inspect before writing: " +
        "get_project_info and get_scene_info-style reads first, edits after. After any change: save_scene, then " +
        "run_project, then get_debug_output to read the console, then ALWAYS stop_project - a project left running " +
        "blocks the next launch. Godot 4.4+ only: get_uid and update_project_uids.",
    },
    unity: {
      id: "unity",
      label: "Unity",
      tools: UNITY_TOOLS,
      notes: UNITY_NOTES,
      actions: UNITY_ACTION_OWNERS,
      rules:
        "UNITY: ACTION-DISPATCH. Most operations are NOT their own tool - the command is the family tool " +
        '(manage_scene, manage_gameobject, manage_components, manage_asset, manage_prefabs, manage_material, ' +
        "manage_texture, manage_ui, manage_editor, manage_camera, manage_graphics, manage_physics, manage_probuilder, " +
        "manage_profiler, manage_packages, unity_reflect, unity_docs, read_console) and the operation goes in " +
        'params.action, e.g. {"command":"manage_scene","params":{"action":"get_hierarchy"}}. Writing ' +
        '{"command":"get_hierarchy"} is WRONG - that is an action, not a tool. A handful of tools ARE flat ' +
        "(create_script, script_apply_edits, apply_text_edits, validate_script, get_sha, delete_script, " +
        "find_gameobjects, find_in_file, refresh_unity, set_active_instance, execute_menu_item, run_tests, " +
        "get_test_job, batch_execute, execute_custom_tool). Workflow: discover the current state (find_gameobjects, " +
        "manage_scene get_hierarchy, read_console) BEFORE editing; after any script change call refresh_unity and " +
        "wait for compilation, then validate_script and read_console; use get_sha before/after an edit to prove it " +
        "changed; run_tests returns a job id - poll get_test_job; leave the editor with play mode stopped.",
    },
    blender: {
      id: "blender",
      label: "Blender",
      tools: BLENDER_TOOLS,
      notes: BLENDER_NOTES,
      rules:
        "BLENDER: authoring engine, usually driven by executing Python (execute_blender_code) plus scene/object " +
        "inspection. Read the scene before editing, and keep every code payload JSON-escaped. " +
        "MODEL FORM DISCIPLINE: choose the primitive per feature, never by habit, and never default to a sphere. " +
        "Cylinder for limbs, shafts, pipes, necks, fingers and barrels; beveled box for plates, housings, crates, " +
        "screens and machine parts; a swept Bezier curve for anything path-like (cable, hose, rope, vine, tail); " +
        "an extruded 2D profile for anything defined by its outline (gear, bracket, beam, blade). A sphere is correct " +
        "for genuinely round things only - eyeballs, ball joints, planets, balls, berries, knobs, domes. Scaling a " +
        "sphere on one axis to imitate a limb or a plate is the exact failure to avoid: it yields visible faceting, " +
        "impossible topology and a model that reads as a placeholder. Consult ms_form_guidance (action=\"classify\" " +
        "for one feature, action=\"audit\" with your part list before building) rather than guessing. " +
        "For a delivery into another engine, export FBX or glTF/GLB and then import through the TARGET engine's own " +
        "tools - never claim the asset arrived because a file exists. Verify scale, pivots, axes, UVs and material " +
        "assignment on the imported result. Tool names vary between Blender MCP servers, so confirm them with " +
        "list_commands rather than assuming.",
    },
    unreal: {
      id: "unreal",
      label: "Unreal Engine",
      tools: {},
      notes: {},
      rules:
        "UNREAL: the server's command set is not documented in this prompt. Run list_mcp_servers and list_commands " +
        "with its server id first and use only what it advertises. Verify by compiling, reading the Output Log, " +
        "opening the map and running PIE before claiming a change.",
    },
    figma: {
      id: "figma",
      label: "Figma",
      tools: {},
      notes: {},
      rules:
        "FIGMA: discover the live schemas. For the Multi-Script companion, call figma_status and figma_get_document first; a running MCP process does not prove the plugin is paired or Edit is enabled. Create native frames/components/text/vectors with figma_create_node/figma_import_svg, update via figma_update_node, then read real node IDs back and export a capture with figma_export_node. Never execute arbitrary plugin JavaScript or edit a different page. For an official remote MCP, use only its advertised read/write tools and actual seat permissions. If no live editable connection exists, report the blocker or provide an importable SVG and label it accurately.",
    },
  };

  // ── Lookup indexes ───────────────────────────────────────────────────────
  // bare tool name -> engine id (built once; first engine wins, which is safe
  // because the engine vocabularies do not overlap in practice).
  const TOOL_ENGINE = (() => {
    const m = new Map();
    for (const [id, e] of Object.entries(ENGINES)) {
      for (const t of Object.keys(e.tools || {})) if (!m.has(t)) m.set(t, id);
    }
    return m;
  })();
  // action -> [owning tools] across every engine that has an action vocabulary.
  const ACTION_OWNERS = (() => {
    const m = {};
    for (const e of Object.values(ENGINES)) {
      for (const [action, owners] of Object.entries(e.actions || {})) {
        m[action] = m[action] || [];
        for (const o of owners) if (!m[action].includes(o)) m[action].push(o);
      }
    }
    return m;
  })();

  const bare = (n) => String(n || "").split("/").pop().split(".").pop();
  const normalize = (n) => bare(n).toLowerCase();

  function engineOfTool(name) {
    return TOOL_ENGINE.get(normalize(name)) || null;
  }
  function displayName(id) {
    const e = ENGINES[id];
    return e ? e.label : (id ? String(id) : "MCP server");
  }
  function knownEngines() {
    return Object.keys(ENGINES);
  }
  function toolSpec(name) {
    const id = engineOfTool(name);
    return id ? (ENGINES[id].tools[normalize(name)] || null) : null;
  }
  // Curated usage note for a non-Roblox tool, or "" when we have none.
  function noteFor(name) {
    const id = engineOfTool(name);
    if (!id) return "";
    return (ENGINES[id].notes || {})[bare(name)] || "";
  }
  // A copyable required-shape envelope for a tool, or "" when the tool's params
  // are simple enough that the schema line already says everything. Covers Roblox
  // (structured arrays / several required fields) and the non-Roblox engines
  // (Unity action-dispatch, Godot camelCase paths, Blender code strings).
  function templateFor(name) {
    const b = bare(name);
    return ROBLOX_TEMPLATES[b] || ENGINE_TEMPLATES[b] || "";
  }
  // Chip category for a non-Roblox tool, or null when we have no opinion (the
  // caller then keeps its existing heuristic).
  function categoryFor(name) {
    const spec = toolSpec(name);
    return spec && spec.cat ? spec.cat : null;
  }
  // Actions a given action-dispatch tool accepts (for the "action is required"
  // error), or [] when the tool is not action-dispatch.
  function actionsOf(toolName) {
    const t = normalize(toolName);
    const out = [];
    for (const [action, owners] of Object.entries(ACTION_OWNERS)) if (owners.includes(t)) out.push(action);
    return out.sort();
  }
  const isDispatchTool = (toolName) => !!((toolSpec(toolName) || {}).dispatch);

  // ── The Unity repair ─────────────────────────────────────────────────────
  // A model that has learned Roblox's shape writes the ACTION where the TOOL
  // belongs: {"command":"get_hierarchy","params":{}}. If `name` is not an
  // advertised tool but IS a known action of exactly ONE advertised tool, rewrite
  // it into the correct envelope. If several tools own that action the call is
  // genuinely ambiguous and we refuse rather than guess - the caller turns that
  // into a clear "did you mean manage_scene or manage_prefabs?" error.
  //
  // hasTool: predicate (name) => boolean over the LIVE advertised catalogue, so a
  // stale entry in this file can never invent a tool the server does not expose.
  function resolveAction(name, params, hasTool) {
    const n = normalize(name);
    if (typeof hasTool !== "function" || hasTool(name)) return { ok: false, reason: "is-tool" };
    const owners = ACTION_OWNERS[n];
    if (!owners || !owners.length) return { ok: false, reason: "unknown" };
    const live = owners.filter((t) => hasTool(t));
    if (!live.length) return { ok: false, reason: "unknown" };
    if (live.length > 1) return { ok: false, reason: "ambiguous", candidates: live.slice().sort(), action: n };
    const p = (params && typeof params === "object") ? { ...params } : {};
    // Never let a stray `action` already in params override the one we resolved.
    p.action = n;
    return { ok: true, tool: live[0], action: n, params: p };
  }

  // Prompt rules for the engines that are actually connected. `ids` may be empty
  // (engine-free session) or contain ids we do not know (a custom MCP server) -
  // unknown ids get the generic discovery rule instead of silence.
  function rulesFor(ids) {
    const list = Array.isArray(ids) ? ids.map((x) => String(x).toLowerCase()) : [];
    const seen = new Set();
    const out = [];
    for (const id of list) {
      if (seen.has(id)) continue;
      seen.add(id);
      const e = ENGINES[id];
      if (e && e.rules) out.push(e.rules);
      else if (id && id !== "roblox") out.push(`OTHER MCP SERVER "${id}": ${GENERIC_RULES}`);
    }
    return out.join("\n");
  }

  // One-line description of an engine for the prompt/UI.
  function summary(ids) {
    const list = (Array.isArray(ids) ? ids : []).filter(Boolean).map((x) => String(x).toLowerCase());
    if (!list.length) return "";
    return list.map((id) => `${id}=${displayName(id)}`).join(", ");
  }

  // ── Roblox studio_id resolution ──────────────────────────────────────────
  // Tools that are place-scoped on Roblox's server, i.e. the ones that need
  // studio_id. Kept as a Set so the caller can decide per call instead of
  // blanket-injecting into tools that would reject an unknown property.
  const ROBLOX_PLACE_TOOLS = new Set([
    "execute_luau", "multi_edit", "script_read", "script_search", "script_grep",
    "inspect_instance", "search_game_tree", "get_studio_state", "get_console_output",
    "user_keyboard_input", "user_mouse_input", "start_stop_play", "wait_job_finished",
    "insert_asset", "search_asset", "screen_capture",
  ]);

  // Does this tool need a studio_id?
  function needsStudioId(name) {
    return ROBLOX_PLACE_TOOLS.has(normalize(name));
  }

  // Fill in `studio_id` from the known connected Studios, when - and ONLY when -
  // that is unambiguous. `studios` is the list of {id, ...} the bridge reported.
  //
  // Returns {ok, params, applied, reason}:
  //   * applied:true  - we injected the single known Studio id
  //   * reason:"already"      - params already carried one; leave it alone
  //   * reason:"not-roblox"   - tool does not take studio_id
  //   * reason:"none-known"   - no Studio id learned yet (caller should tell the
  //                             model to run list_roblox_studios)
  //   * reason:"ambiguous"    - several Studios connected and the model did not
  //                             say which one; NEVER guess, return the candidates
  //
  // Guessing here would be worse than failing: the proxy would happily run the
  // edit against the WRONG place, and the user would see a different project
  // mutated with no error at all. So ambiguity is a refusal, not a coin flip.
  function withStudioId(name, params, studios) {
    const p = (params && typeof params === "object") ? { ...params } : {};
    if (!needsStudioId(name)) return { ok: false, params: p, applied: false, reason: "not-roblox" };
    if (p[ROBLOX_STUDIO_ID] !== undefined && p[ROBLOX_STUDIO_ID] !== null && String(p[ROBLOX_STUDIO_ID]).trim() !== "") {
      return { ok: true, params: p, applied: false, reason: "already" };
    }
    const list = (Array.isArray(studios) ? studios : [])
      .map((s) => (typeof s === "string" ? { id: s } : s))
      .filter((s) => s && typeof s.id === "string" && s.id.trim());
    if (!list.length) return { ok: false, params: p, applied: false, reason: "none-known" };
    if (list.length > 1) {
      return { ok: false, params: p, applied: false, reason: "ambiguous", candidates: list.map((s) => s.id) };
    }
    p[ROBLOX_STUDIO_ID] = list[0].id;
    return { ok: true, params: p, applied: true, reason: "applied", studioId: list[0].id };
  }

  // Pull Studio ids out of any tool result that mentions them. Used to learn the
  // id passively from list_roblox_studios / get_studio_state instead of forcing
  // an extra round trip. Tolerant of the wrapper key ("studios" / "studios_info"
  // / a bare array) because the shape differs between Studio builds.
  function studiosFromBody(body) {
    if (!body) return [];
    let v = body;
    if (typeof v === "string") {
      const t = v.trim().replace(/^Output of '[^']*':\s*/, "");
      if (!/^[[{]/.test(t)) return [];
      try { v = JSON.parse(t); } catch { return []; }
    }
    const out = [];
    const push = (x) => {
      if (!x) return;
      if (typeof x === "string") { if (x.trim()) out.push({ id: x.trim() }); return; }
      if (typeof x === "object" && typeof x.id === "string" && x.id.trim()) out.push({ id: x.id.trim() });
    };
    if (Array.isArray(v)) { v.forEach(push); return out; }
    if (typeof v !== "object") return out;
    // Look at the known wrapper keys first, then any array-valued key.
    for (const k of ["studios", "studios_info", "studio", "instances", "items"]) {
      const val = v[k];
      if (Array.isArray(val)) { val.forEach(push); if (out.length) return out; }
      else if (val) { push(val); if (out.length) return out; }
    }
    for (const val of Object.values(v)) if (Array.isArray(val)) val.forEach(push);
    return out;
  }

  return {
    ENGINES, ACTION_OWNERS, GENERIC_RULES,
    ROBLOX_NOTE, ROBLOX_STUDIO_ID, ROBLOX_PLACE_TOOLS, ROBLOX_STUDIO_ID_SUFFIX,
    ROBLOX_TEMPLATES, ENGINE_TEMPLATES, ROBLOX_GLOBAL_TOOLS,
    knownEngines, displayName, engineOfTool, toolSpec,
    noteFor, categoryFor, actionsOf, isDispatchTool, templateFor,
    resolveAction, rulesFor, summary,
    needsStudioId, withStudioId, studiosFromBody,
  };
})();
