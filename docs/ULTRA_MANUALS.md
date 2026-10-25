# Ultra manuals and skill application

The current catalog contains **249 skills**: the supplied v24 set of 241 unchanged definitions plus eight reviewed specialist restorations. This update does not restore the removed duplicate catalog or add execution permissions. It makes all twelve Ultra methods and existing skill usage substantially more detailed.

`runtime/ultra-handbook.json` is the canonical source for **564 phase checkpoints**, **72 phase exit criteria**, **72 final acceptance criteria**, **48 diagnostic cases**, and **72 engine-specific application notes**. All 480 previous checkpoints remain; 84 reference-informed checks extend the same craft, accessibility and QA phases. The six phases are inspect, design, build, integrate, verify and failures. Each discipline has its own concrete methods, failure probes/repairs/rechecks, deliverables, real existing skill routes and source guidance.

The supplied 25 UI, architecture, vegetation and creature images deepen the existing methods and style guidance. They do not create another manual set or style catalog. Existing studded/cartoon/minimal/tactical/fantasy/holographic guidance gains concrete hierarchy, component, silhouette, construction and verification detail. Motion and performance requirements are authored checks, not measurements inferred from still pictures. Original skills and licensed reference packs remain intact.

| Manual | Detailed guide |
|---|---|
| GUI, UX and interface craft | [ultragui](ultra-handbook/ultragui.md) |
| Animation, rigs and deformation | [ultraanimation](ultra-handbook/ultraanimation.md) |
| VFX, shaders and lighting | [ultravfx](ultra-handbook/ultravfx.md) |
| Modeling, materials and export | [ultramodelling](ultra-handbook/ultramodelling.md) |
| World building and traversal | [ultraworld](ultra-handbook/ultraworld.md) |
| Gameplay, state and feel | [ultragameplay](ultra-handbook/ultragameplay.md) |
| Audio, mixing and spatial behavior | [ultraaudio](ultra-handbook/ultraaudio.md) |
| Authority, networking and persistence | [ultranetwork](ultra-handbook/ultranetwork.md) |
| Performance and causal measurement | [ultraperformance](ultra-handbook/ultraperformance.md) |
| Software engineering and upgrades | [ultraengineering](ultra-handbook/ultraengineering.md) |
| Accessibility and input | [ultraaccessibility](ultra-handbook/ultraaccessibility.md) |
| QA, evidence and failure recovery | [ultraqa](ultra-handbook/ultraqa.md) |

## How the AI receives the detail

Startup does not send this handbook. A task carries a bounded relevance summary; Ultra exposes the local `ms_ultra_manual` read tool. Prefer the section for the active phase and reuse a loaded method. A full read remains available and returns the selected discipline's foundation, structured phase checklists, exits, diagnostics, acceptance, deliverables and skill routes. A section read returns the requested phase and relevant supporting material. Ordinary skill reads also include the expanded checks relevant to their existing manual; the existing GUI/animation skill workflows receive the deeper instructions without rewriting their original definitions.

For example, the AI can request one actual tool object:

```json
{"command":"ms_ultra_manual","params":{"action":"read","id":"ultraanimation","engine":"blender"}}
```

For a focused diagnostic question:

```json
{"command":"ms_ultra_manual","params":{"action":"read","id":"ultragui","engine":"godot","section":"failures"}}
```

The supported authoring/target contexts are Roblox, Godot, Unity, Blender, the selected software workspace, and Figma. Figma is a real design/prototype/handoff context when the connected tools permit it; it does not become a gameplay engine. A Blender source render is not target-gameplay evidence. The existing detailed Roblox GUI/animation production pack and licensed resource bindings remain available through the same scoped tool path.

## Applying existing skills

Every `ms_get_skill` result now includes `manualApplication`: the actual objective, relevant discipline, compact practical checkpoints, phase exits, engine note and precise deeper-retrieval arguments. Its default guide stays bounded. Skills selected by the director also include a compact retrieval route, so a list of IDs is not mistaken for a fully applied method.

```json
{"command":"ms_get_skill","params":{"skill_id":"figma-auto-layout","objective":"Build the requested responsive inventory menu","manual_sections":["build","integrate","verify"]}}
```

`manual_sections` is optional and separate from the existing `sections` argument used by older skills' optional rule sections. It accepts the six handbook phase names. Loading a skill does not count as implementation. Choose the smallest relevant method set, extract constraints for the actual project, apply them through authorized advertised tools, then check actual output. Reuse a loaded method while its assumptions remain valid. Do not repeatedly fetch the same manual, load every skill, invent tools, change user scope or enable a disabled skill.

Discovery, review and explanation remain read-only. A request to inspect and then implement can proceed within that authorized scope. A lower effort removes the Ultra tool/policy immediately; standard skill retrieval remains a reference workflow and does not acquire Ultra permissions. Failed reads are unknown state, never proof that a place is empty. Existing unchanged-read/failure guards, task evidence and uncertainty/no-replay protections remain.

## Maintenance and verification

Edit the canonical JSON and run `python tools/sync_ultra_handbook.py`. It validates existing skill IDs and generates the browser data plus these twelve readable guides. Browser and Python retrieval use the same pack. Metadata and tests verify all twelve disciplines, all 249 actual skill results, 72 manual/context combinations, real browser-to-Python phase retrieval, startup size, task routing, immediate demotion and read-only boundaries.

Source notes distinguish reviewed official guidance from reference seeds whose current page could not be fetched. Verify installed engine/package versions and current APIs before using specific features. The guidance is in-context instruction, not a claim to alter model weights, grant native access or guarantee output quality. Native, account-authenticated and physical-device tests still require those environments.
