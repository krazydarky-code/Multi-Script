# Blender Workspace Â· Multi-Script

Blender Workspace is a dedicated model and animation tab with a Three.js viewport, a lil-gui inspector and a real Blender engine running in the background. It saves genuine `.blend` projects. It does not require a Blender desktop window, a BlenderMCP add-on or a separate Node installation for users.

## Set it up

1. Update Multi-Script in your usual permanent folder and run **Setup.bat**. Keep your private settings and `runtime/studio-data` when updating.
2. On Windows, setup reuses a compatible installed Blender or prepares the pinned portable Blender 4.5 LTS runtime. The first Windows x64 download is about 380 MiB and needs about 2.2 GB of free space during preparation. The cache is shared across Multi-Script updates, outside the release folder.
3. Start the Multi-Script bridge. Click the **cube icon in the Multi-Script chatbar**, or open the extension popup and choose **Open Blender Workspace**. The advanced Settings â†’ Engines shortcut also remains available.
4. Choose **New project**, give it a name, and wait for **Blender workspace ready**. If setup was offline, **Prepare Blender** finishes the runtime download here.
5. Return to your provider chat, open a fresh conversation, and use **Start Blender agent**. Ask it to inspect the workspace and build your model or animation. You can keep the workspace tab open, or let the AI work while it is closed.

Windows x64 and ARM64 have automatic portable preparation. macOS/Linux can use an installed Blender. Set `MS_BLENDER_PATH` before starting the bridge to select a particular Blender executable. This release was tested with real Blender **4.5.15 LTS on Windows x64**; other OS/runtime combinations need their own live verification. Setup failure is reported and can be retried; it does not claim an engine is ready without starting it.

## Use the workspace

- **Viewport:** orbit by dragging, pan with right-drag, scroll to zoom. **Frame all** or F fits the scene. G, R and S select the move, rotate and scale gizmo.
- **Outliner and inspector:** select an object, edit its native Blender position, rotation, scale or first material's base color. Inspector values use Blender's Z-up coordinates. Viewport gizmos convert their Y-up world matrices back to Blender, including parented transforms.
- **Animation:** choose an exported clip and play or scrub the timeline. Scrubbing also sets the real Blender frame. Insert a keyframe for the selected object's location, rotation and scale, or enable **Auto-key** while changing transforms. The AI can create rigs, skin weights, actions, shape keys and more through real `bpy` operations.
- **AI rendering:** the AI produces a real Cycles CPU image at the current frame, using the scene camera or a temporary preview camera. An unlit scene without an explicitly configured world gets temporary preview lights. The camera and render settings are restored afterwards. This is separate from the browser preview; the workspace has no Render button.
- **Import:** copy a `.blend` or self-contained `.glb` into the owned project. Browser import is capped at 50 MB. Importing a `.blend` replaces the current project's scene; your original input file is not overwritten. Back up or export the current project first when needed. Automatic execution of embedded Blender scripts is disabled.
- **Deliverables:** download the actual `.blend`, a `.glb` or an `.fbx` export. The project auto-saves after successful edits. Export and read back assets in the destination engine to verify its import, rig, material and animation requirements.

The viewport represents exported glTF content. Procedural materials, simulations, volumes, compositor effects, unsupported constraints or engine-specific shading may not look identical there. Use a Blender render for shading evidence and the destination engine for final runtime verification. Nothing in the UI labels a preview as a verified engine import.

## AI tools and the selected target

`ms_blender_workspace` exposes **status**, **snapshot**, **execute**, **render**, **export** and **frame**. An execute call accepts real Python using `bpy`; its result includes actual output and the updated scene. A render returns a real PNG image to the provider when its transport supports images.

The existing typed `ms_blender_*` toolset also works:

- `target: "auto"` follows the workspace's **AI target** switch.
- `target: "workspace"` explicitly uses headless Blender.
- `target: "connected"` explicitly uses the existing desktop Blender MCP connection.
- `workspace_project` can pin an expected project id, preventing a stale call from editing a project switched in another window.

The existing native names `execute_blender_code`, `get_scene_info`, `get_object_info` and `get_viewport_screenshot` are advertised directly for an owned headless project, even without desktop MCP configured. Connection checks and Reconnect inspect that same worker. Closing/stopping it preserves the saved AI target; **Resume Blender** reopens the same project. A new engine session can resume a saved standalone workspace without a connected game engine. A failed/stopped headless worker cannot silently redirect automatic calls to desktop Blender. Explicit desktop targeting remains available.

The current workspace target and project are included in engine sessions' instructions. Chat Studio continues to block engine execution. Switching Blender off in Engines blocks its AI tools. A desktop connection remains configured independently; a connected-target call never silently falls into the workspace.

Python execution has the local user's permissions, like the existing Blender execute-code integration. It is not a Python sandbox. The preview server binds only to `127.0.0.1`, validates the Host and Origin, uses a one-time launch key and an HttpOnly SameSite cookie, and exposes only owned project assets. Arbitrary Python execution is available through the engine tool path, not a browser API command.

## Project files and updates

Projects are stored under `runtime/studio-data/blender-workspace/projects/`. Each project contains `scene.blend`, `preview.glb`, a scene snapshot, export files and a worker log. Updates preserve `studio-data`; manual folder replacement should preserve it too. Portable binaries live in the per-user Multi-Script engine cache and are not included in the small extension ZIP.

The worker serializes operations on Blender's main thread. Typed read-only tools inspect without resaving or re-exporting the whole project. A failed Python edit reloads the last committed scene. A timeout stops the worker so it cannot continue mutating behind a second call; reopen the saved project to recover. These scene protections do not undo unrelated operating-system actions deliberately performed by Python code. Scripts can use Edit mode within an operation; successful operations return the stored project to Object mode for consistent background tools and export.

## Troubleshooting

- **Workspace does not open:** start the bridge and enable Blender in Engines. Reopen it from Multi-Script; a copied or expired one-time launch link cannot authenticate another session.
- **Runtime preparation failed:** check the displayed network/disk error. TLS and SHA-256 verification stay enabled. Retry **Prepare Blender**, or install a compatible Blender and set `MS_BLENDER_PATH`.
- **No 3D preview:** enable browser graphics acceleration/WebGL. Real Blender tools, renders and export files do not require the browser's WebGL renderer.
- **Project changed / Blender busy:** wait for the current result, inspect status and use the correct project id. Do not replay a mutation blindly.
- **Exact result differs from the preview:** inspect a real render and the exported file in the intended engine. A glTF preview is not every Blender feature reimplemented in JavaScript.

## Dependencies and verification

Three.js **0.180.0** and lil-gui **0.21.0** are bundled locally with their MIT notices; normal use does not fetch scripts from a CDN. Blender keeps its own name, license and distribution. Portable Windows downloads are pinned to the official 4.5.15 LTS asset size and SHA-256 values. TLS verification is never disabled.

Real integration tests exercise Blender Python, native toolkit routing, keyframes/animated GLB, parented coordinate conversion, rollback, persistence, Cycles PNG, three export formats and HTTP isolation. The real browser suite covers WebGL, inspector edits reaching `bpy`, animation playback, frame scrubbing, absence of the Render button, retained native rendering, downloads, reload and desktop/phone layout. These tests do not certify every add-on, shader, engine importer or authenticated AI account.

Sources: [Blender downloads](https://download.blender.org/release/Blender4.5/), [official mirror checksums](https://mirror.blender.org/release/Blender4.5/blender-4.5.15.sha256), [Blender license](https://www.blender.org/about/license/), [Three.js GLTFLoader](https://threejs.org/docs/pages/GLTFLoader.html), [TransformControls](https://threejs.org/docs/pages/TransformControls.html), [lil-gui](https://lil-gui.georgealways.com/).

## Multi-Script controls inside the workspace

Expand the **Multi-Script** dock in the bottom-right corner. Select an open supported provider chat to see its current session status and reported task steps. **Open AI chat** returns to that exact tab; **Settings** opens its Multi-Script control center. Start the Blender agent and send new tasks in that provider chat. **Queue follow-up** appends your request at the next tool-result boundary; it does not send an idle chat a new task automatically. **Stop run** stops the selected session.

The provider tab must remain open. Background execution follows that chatâ€™s existing background-run setting; opening the 3D tab does not silently enable it. An unfinished native provider response stays active until the provider finishes. A plan is shown only when the AI reports one. Every action uses the selected chatâ€™s current context and dispatch receipt; switching chats or unconfirmed sends can require manual inspection.

The dock connects only in workspace tabs opened by Multi-Script, in the same browser profile. Reopen from the cube icon after updating or if the chat link is unavailable. The local Blender engine can continue working independently of the viewport.

## Connected game sessions

In the workspace **Connections** card, tick **Roblox Studio + Blender**, **Unity + Blender**, or **Godot + Blender**. Choose a saved Blender project, or keep **Current / last project**. Connect the game editor normally. In a fresh supported provider chat, press Start for that engine; Blender is prepared and verified before the startup prompt is sent. This is opt-in and respects disabled engine settings. Chat Studio stays engine-free. A running different project is never silently replaced.

The card distinguishes **Blender connected · verified**, **Blender is working**, the last real response, the selected AI chat’s actual Blender tool availability, and connected game editors. Choose the AI chat in the dock. Its access indicator also checks that it targets this same project. A remembered bridge process alone is not proof of a working editor.

## Saved models and material preview

Every successful edit saves **scene.blend** before generating its preview. If preview export fails, the native model stays saved and the interface shows the preview error. Refresh restores the saved snapshot/GLB even with the worker stopped; **Resume Blender** reopens that same project. Export the .blend for an independent native backup. **Focus selected** frames the selected object without changing the scene, useful when an existing backdrop is much larger than the model.

The viewport uses local studio lighting and exported PBR materials. Unsupported procedural base-color networks are baked to cached color textures on temporary mesh/material copies; original node shaders, UVs and selection are restored. Full procedural roughness, displacement, volumes and scene lighting can still differ. AI rendering runs actual Blender Cycles for exact scene evidence. A request for a model should produce the model; a render is separate, and verification should not leave staging objects in the saved scene.

## Send a model to your game

Use **Send to your game** in the right panel. Give the asset a name. For Unity, choose the project folder containing **Assets** and **ProjectSettings**; the workspace exports FBX into **Assets/MultiScript/Blender**. For Godot, choose the folder containing **project.godot**; GLB goes into **assets/multiscript/blender**. The remembered destination is reused. Return to the editor so its import pipeline can finish. Existing changed assets require the explicit **Replace existing asset** checkbox.

For Roblox Studio, **Prepare Roblox import** produces a pinned GLB download. Download it, then use Studio’s **File → Import** and review its importer settings. This step does not silently upload an asset to a Roblox account. The handoff exports the project scene, so remove unwanted staging before delivering an asset. Check scale, materials, rigging, collisions and animations in the target engine. The AI can use its connected engine tools to read back the import; only that evidence establishes in-engine completion.

The tool equivalent is **ms_blender_workspace** with **action=handoff**, the current **project**, **engine**, **name**, and an explicit **project_path** for the first Unity/Godot destination. The result records file bytes, hash, destination and a pinned download; **engineImportVerified** remains false until separate engine checks. Exports are serialized with native edits and cannot switch the current Blender project.

## Worker ownership and connection recovery

Each background worker follows the bridge process that owns it. If that process dies, its worker exits even during a busy operation. A lifetime project lock prevents two current workers from editing the same saved scene. Close the owning bridge/workspace before reopening a project elsewhere. This protection applies to workers launched by 6.49.7 or later; stop older installations gracefully when upgrading.

A timeout or lost/malformed response stops the worker and clears verification. An uncertain edit is never replayed automatically. Resume/reopen the same saved project, inspect its actual scene and continue from that committed state. Rendering and automatic AI render tools remain available; there is no workspace Render button.
