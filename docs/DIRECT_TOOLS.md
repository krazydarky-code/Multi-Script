# Multi-Script production tools — 6.36.1

Multi-Script 6.36.1 exposes **271 built-in bridge tool schemas** in the full catalogue: **231 core direct tools** plus the additional memory, assistance and workspace contracts. The product also ships **897 skills**, **300 virtual specialists**, and **24 optional Roblox companion tools**. Native Roblox, Unity, Godot, Blender and other MCP tools are discovered from the live server catalogue and are not counted as built-in tools.

## Creative Production Studio

The 6.36.1 production layer routes provider-specific art direction, asset workflow and finish-level preferences into the active session prompt. Relevant skill contracts require real implementation, integration, testing, critique, repair and native read-back—not just a plan.

Local creative asset tools include:

- `ms_create_icon_pack` — creates individual SVG icons, a sprite sheet, contact sheet and JSON manifest.
- `ms_create_canvas_ui` — creates polished SVG UI/UX screen mockups across 16 visual palettes, plus design-token and manifest files.
- `ms_create_canvas_texture` — creates reusable procedural SVG textures and decals.
- `ms_art_direction`, `ms_uiux_production`, `ms_animation_director`, `ms_texture_art_pipeline` and `ms_vfx_production` — provide discipline-specific execution contracts to be carried out with the relevant native tools.
- `ms_studio_director` and `ms_full_spectrum_skill_mesh` — select relevant skills, direct tools and virtual specialists for the actual request.

Generated source files are real local deliverables. A local SVG is not the same as a Roblox-uploaded image asset ID or a confirmed in-engine import; the agent must use the target's supported asset pipeline and verify the final assignment before claiming completion.

## Provider and execution behavior

The active provider receives the shared production contract plus a provider-specific adapter note through Multi-Script's supported session prompt path. This improves the model's instructions and tool discipline; it does not retrain model weights or assume every website exposes a native system-role API. Prompt rewriting remains independent from skill execution.

## Execution rule

The model must inspect the real project and live tool schemas, select the relevant specialists, implement the requested artifact through native tools, integrate adjacent systems, test important states, fix concrete defects and read back the final state. Tool output and project read-back are evidence; plans, generated prose and confidence are not.

For the complete live tool catalogue, see [`TOOLS_GUIDE.md`](TOOLS_GUIDE.md). For install and upgrade steps, see [`INSTALL.md`](INSTALL.md).
