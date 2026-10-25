# Multi-Script feature history

Older "What's new" sections moved here from the README (newest first). Per-version notes: `docs/release-notes/`.

## What's new in 6.25.0

- **Chat bar docking fixed on Notion AI** (empty-chat layout no longer strands the bar mid-page) with validated composer geometry and fallbacks.
- **Customizable chat bar**: dock (Auto/Floating/Window), alignment, width, nudge, style, size, status line, per-item toggles, reset (Settings → Chat bar).
- **Rebuilt menu**: category rail, search, accordions, smoother animations.
- **Claude** provider hardened (load-order crash fixed) and described in AI sites.

## What's new in 6.24.0

- **The terminal icon runs the bridge.** (`Start.bat` is back as a no-setup fallback — see Step 3.) Click the terminal icon in the chat bar and the bridge starts (and starts by itself when an AI site opens). The caret beside it opens a top-down **Running** menu: bridge, every MCP server, and any engine app (Roblox Studio, Unity, Godot, Blender). One-time setup: run `Setup.bat` (Windows) or `MacOS_Setup.command` once — browsers cannot launch programs by themselves, so this registers the small Native Messaging host that the icon talks to.
- **JSON-schema errors repaired at the source.** Tool arguments are now fixed against the live schema (`runtime/schema_repair.py`): numeric strings, boolean words, `{x,y,z}` objects, envelopes like `{"arguments": {...}}`, near-miss key names, enum case, clamped ranges. Every repair is reported back to the model instead of failing the call. The chat parser also recovers curly-quoted and single-quoted JSON.
- **109 more native engine tools** — Blender 30, Roblox 27, Unity 31, Godot 21 (`ms_blender_*`, `ms_roblox_*`, `ms_unity_*`, `ms_godot_*`). They are translated onto each engine's own MCP server and appear only for engines you have configured. Blender now has a launcher (`runtime/launch_blender_mcp.py`) like the other engines.
- **Notion AI.** The bar lines up with the composer's text column and follows resizes. A **Notion** settings tab detects which models are enabled in agent mode (including Opus 5.5 / Sonnet 5.5 and their effort levels), switches model and effort through Notion's own picker, and gives a *rough* "prompts left" estimate for a trial. See *Notion AI setup* below for what is measured and what is estimated.
- **Settings reorganised:** Studio (what gets built and how), Agent (autonomy, verification, recovery, pacing), Notion, Interface, Engines (Bridge first), AI sites, Help.

## Notion bar auto-width

The bar now follows the exact live rectangle of Notion’s “Ask anything” composer instead of inheriting the wider surrounding action rail. Width-aware controls compact from the measured composer width, so the bar remains flush with both sides through resize and sidebar changes.

## Notion AI chat and guided setup

Multi-Script now injects on Notion’s current `app.notion.com/chat` surface. The built-in Notion launcher opens the real AI chat instead of the old workspace root that could lead to Connectors. After updating, reload the extension once so the browser grants the new host permission.

The settings menu has a dedicated **Setup** category with live bridge/editor/composer checks, exact installation and editor-connection steps, a copyable checklist, Notion-specific routing guidance, and a map of every settings category.

## Claude provider from the PlazCode reference

Claude on claude.ai and claude.com is now a first-class Multi-Script provider. Its adapter was selectively adapted from PlazCode’s GPL provider code and generalized for Multi-Script’s multi-engine bridge. It receives the same provider-independent enhancer, effort, pacing, recovery, verification, trust, skills, and tools as every other site. The PlazCode IDE, desktop executable, AgentScript runtime, and branding are not included.

## Universal prompt and effort harness

Prompt enhancement now uses the same shared implementation on all ten supported AI providers. Its review setting opens an editable preflight dialog instead of sending automatically: add the enhanced brief, continue with the original request, or cancel. Engine facts, live-tool facts, task-shaped approach, and original-first ordering are independent working controls.

Execution effort is also provider-neutral: Adaptive, Quick, Standard, Deep, and Maximum tune requested implementation depth without claiming to alter a site's hidden reasoning setting. Notion AI carries the choice inside Multi-Script's prompt-only startup harness, separate from its preferred-model request.

## MCP catalog integrity

The bridge exposes the existing 230 direct tools plus each server’s live native tool catalog. Multi-Script discovers the real schemas through `list_commands`, `ms_engine_catalog`, generic server routing, and MCP resources instead of adding duplicate wrappers for capabilities that are already advertised by the connected server.

## Roblox Schema Conformance

The Roblox tool templates and notes are a **mirror** of the live `StudioMCP` server — a copyable JSON envelope leads each tool's note so the model never has to guess a required field. Nine of those shapes had been written from memory rather than read from the server's published parameter schema, and several were wrong: the model copied the example, the server rejected it, and the rejection looked like a product bug.

They are now read from the real schema. `generate_mesh` takes **`textPrompt`** (not `prompt`); `wait_job_finished` takes **`jobId`** (not `generation_id`); `screen_capture` **requires `capture_id`**; `search_game_tree` **requires `datamodel_type`**; `script_grep` takes **`query`** while `script_search` takes **`keywords`**; `insert_asset`'s **`assetId` is a string** and `assetName` names the instance; `multi_edit`'s **`file_path` is a top-level params field**, not a field inside each edit; `generate_procedural_model` defaults to **`async:true`** and returns a `jobId`; `character_navigation` is `datamodel_type:"Client"` plus `instance_path` or `x`/`y`/`z`.

Two **silent duplicate-key bugs** were fixed — in a JavaScript object literal the last duplicate wins and `node --check` cannot see it, so `search_game_tree` and the `generate_mesh` / `generate_procedural_model` notes each shipped twice with dead text behind the live copy. A source-level duplicate-key scanner now runs as a permanent gate.

Coverage is now complete: every native tool ships a required-shape template, the full Roblox build surface (`insert_asset`, `search_asset`, `get_console_output`, `screen_capture`, `generate_mesh`, `generate_procedural_model`, `search_game_tree`) has curated notes, and `ROBLOX_GLOBAL_TOOLS` declares which tools take **no** `studio_id` so a model cannot invent one on `list_roblox_studios` — the single most likely first call of a session. `tests/test_roblox_schema_conformance.js` pins every corrected name so a future edit cannot drift back to a guess.

## Native Engine Command Layer

The JSON transport stays for **every** engine — MCP is JSON-RPC and every tool declares JSON-Schema'd parameters, so a second wire format would only fork the parser, camouflage and parse-error paths. What was actually broken was the engine-specific **vocabulary**, and that is what this release fixes.

The clearest example is Unity: it is **action-dispatch**. There is no `get_hierarchy` tool — there is `manage_scene` with an `action` string. A model that had just worked on Roblox wrote `{"command":"get_hierarchy"}`, the old build answered "unknown command", and the model concluded the engine could not do it. That call is now repaired in place to `{"command":"manage_scene","params":{"action":"get_hierarchy"}}`. Genuinely ambiguous actions are never guessed: the model is told the candidate tools and asked to pick.

- **`core/engines.js`** — a pure, unit-tested registry of non-Roblox native tools: real names, exact required parameter spellings, action vocabularies, chip categories and curated per-tool notes. Godot's 14 tools and parameters come from the published package's `inputSchema`; Unity's 33 tools and 132 actions from the vendored v10.2.0 reference; every fact is attributed in the source.
- **Godot** keeps its flat tool set but now teaches the traps: `projectPath` is the absolute folder *containing* `project.godot` (13 of 14 tools need it), `list_projects` is the exception and takes `directory`, and you must `stop_project` or the next run fails with "already running".
- **Curated notes for every engine.** `TOOL_NOTES` used to be Roblox-only, so non-Roblox engines got zero curated guidance. `ZS.toolNote()` now merges the Roblox notes with the registry's, and `list_commands` shows them.
- **The prompt is engine-aware.** A Godot-only session is told "NO Roblox Studio is connected in this session", is no longer told to write project memory into `game.ServerStorage` (which does not exist outside Roblox), and gets the real Godot parameter rules. With no engine information the prompt is byte-identical to before.
- Engine-aware chips (a Godot `run_project` reads as an action, a Blender viewport capture as a screen) and an engine-aware offline note that no longer sends a Godot user to open Roblox Studio.

## Reply Pacing and Unattended Recovery

The agentic loop now has a real reply-pacing engine instead of a fixed 200 ms settle: Off / Brisk / Human-like / Cautious / Custom modes with a randomised inter-turn band, an occasional longer break, an optional typing cadence, and a per-error cooldown so a retry can never deepen a rate limit. The gap is measured since the last send, so a slow reply or an image upload is never double-taxed, and the bar shows the wait so a deliberate gap never looks like a hang. Pacing can be **scoped to one site only** — slow down on the site that flags you, keep everything else instant — and the menu's **Test pacing** button runs the same engine over a simulated session and reports the real numbers on your machine.

Failures are now recoverable rather than terminal. Off / Standard / Persistent levels handle empty replies, timeouts, malformed commands, swallowed sends and transient "server is busy" notices with escalating backoff, bounded both per failure and across a consecutive run, and a persistent run widens the patience windows for slow replies, warm-ups, reasoning phases and still-streaming command blocks. A retry only ever re-asks the model and always states that nothing ran.

## One-shot design specs

Paste a design specification and walk away. One-shot mode forbids clarifying questions and dead turns, requires the whole spec to be driven to completion, requires silent self-recovery from hiccups, and restricts stopping to choices that are destructive, paid, credentialed or genuinely contradictory. It ends with one short evidence-based report. Selecting it also raises the Persistent-recovery and Human-like-pacing floors.

## Arena verification and Notion reliability

Bot-check detection on Arena now covers Turnstile, hCaptcha, reCAPTCHA, Arkose, DataDome, PerimeterX and GeeTest plus an independent text probe, each requiring real visibility, real size and a chat-free host. Multi-Script never solves, token-injects, outsources or bypasses a challenge: it pauses, gets its bar out of the way, tells you what to do, and resumes by itself when the check clears — at startup, mid-loop and mid-send. Notion gains broader stop matching, a three-strategy verified send with composer-clear confirmation, and an unsettled-read signal that prevents false malformed-command verdicts.

## JSON-only transport, Godot first-class

Every engine is governed by an explicit JSON-only contract: one plain-text `{"command":…,"params":{…}}` object, no fences, no XML/DSML/function-call markup, no wrapper keys, one command per reply, with exact `execute_luau` and `multi_edit` parameter shapes. The core additionally unwraps a double-wrapped envelope instead of refusing an obvious call.

Godot is a first-class target. The bundled launcher now **auto-detects the Godot editor** (env overrides, then the usual Windows/macOS/Linux install locations, then PATH) and sets `GODOT_PATH` for the server, reports what it found on stderr, never writes to the MCP stdout channel, and forwards Ctrl+C instead of orphaning the child. In-chat guidance is concrete: `get_godot_version`, then `get_project_info` for the exact absolute project path, inspect before writing, run / read `get_debug_output` / stop cleanly, and case-sensitive path handling.

## Arena Profiles and Engine-Free Studio

Arena Direct/Max now has prompt-only starter profiles with Claude Opus 5.5 as the default preferred-model request. The request asks Arena Max/Auto to use the real model when legitimately available and falls back honestly; Multi-Script never clicks Arena’s picker or bypasses plans, quotas, verification, access controls, or availability. The front bar now offers Start without engine on fresh Notion and Arena chats and supports direct startup with whichever native MCP editors are actually connected—Roblox Studio, Unity, Godot, Blender, or other servers. Chat Studio retains the full specialist mesh and starter profile without pretending engine edits occurred. Animation, VFX, and texture/art specialists now carry explicit live-tool creation, integration, profiling, runtime playback, import/export, and evidence standards across all engines, with special Roblox rig/contact/state-machine coverage.

## Portable Settings and Capability Assurance

Multi-Script can now copy and restore a versioned, validated settings backup covering appearance, every provider’s behavior, usage optimization, specialist depth, custom instructions, and Notion’s preferred-model request. Credentials, API keys, MCP launch commands, and runtime state are deliberately excluded. Imported values are sanitized before atomic persistence. A new settings invariant ensures rewrite, speed, compactness, and creative-surface preferences change workflow mechanics without lowering correctness, native integration, specialist contribution, or the professional completion floor. This reinforces Multi-Script as a broad ZeroScript evolution across providers and MCP engines rather than a Notion-only patch.

## Settings and MCP Compatibility

All menu settings are now treated as product behavior rather than decoration: appearance values and per-provider behavior are validated when loaded, effective settings are included in privacy-safe diagnostics, and a Reset agent behavior action restores rewriting, production checks, creative routing, specialist depth, and usage optimization without deleting appearance, custom instructions, secrets, or MCP servers. Onboarding now describes Roblox Studio, Unity, Godot, Blender, and arbitrary configured MCP tools. Multi-Script explicitly extends the original ZeroScript foundation across providers and MCP servers; Notion compatibility remains prompt-only and does not bypass subscriptions, Business trials, model-picker restrictions, access controls, or provider plan limits.

## Product Release Hardening

Prompt rewriting is now explicitly independent from capability enhancement. Off preserves the exact submitted wording, Suggest can offer an optional rewrite without blocking work, and Automatic silently clarifies reversible details. In every mode, the relevant skills, direct tools and virtual specialists remain active and improve the real project. Every catalogue entry now carries a seven-part product release gate and defect-priority order covering real artifact completion, integration, complete states, measured weakest-target budgets, clean native validation, final read-back, honest limitations and rollback.

## Universal Capability Foundation

The permanent mental basis is now encoded in the runtime: skills and tools exist to improve what the active model can actually design, build, integrate, optimize, debug and verify across game development. Every direct tool, skill and virtual specialist now follows an eight-stage capability lifecycle and anti-shallow rules. Prompt brevity never lowers the quality bar, and internal guidance never counts as the finished artifact. Natural-language routing now understands broader genre intent such as RPG, horror, platformer, racing, survival, tycoon/simulator and multiplayer/mobile/style signals without creating named presets.

## Intent-to-Product Intelligence

Every one of the **232 direct tools**, **800 skills**, and **300 virtual specialists** now carries a concrete contribution contract, weak-prompt policy, cross-discipline integration responsibilities, quality dimensions, and native evidence requirement. Short prompts are interpreted as product intent—not merely rewritten. For example, “Make me realistic graphics, and a shooter game” becomes one cohesive playable vertical slice: grounded PBR materials and lighting, player controller and camera, data-driven weapon, enemy behavior, combat arena, HUD, animation/VFX/audio feedback, complete win/fail/restart states, platform inputs, performance tiers, profiler evidence, and native project read-back. Explicit user requirements and existing project conventions always override inferred defaults.

Multi-Script connects supported AI chats to Roblox Studio, Unity, Godot, Blender, Figma, and other MCP tools through a local bridge.

You describe what you want to build. The AI can inspect the connected project, use the available tools, make changes, and verify the result.

## What is included

- Browser extension for Notion AI, Claude, ChatGPT, DeepSeek, Gemini, Kimi, GLM, Qwen, Arena, and Meta AI
- Local multi-engine MCP bridge
- Built-in Roblox, Unity, and Godot launchers
- Support for Blender, Figma, Unreal, and other stdio MCP servers
- 500 reusable professional game-development skills, including 194 detailed Roblox/Unity/Godot production workflows
- Canvas/SVG UI and texture creation
- Per-provider prompt, validation, speed, and creative-routing settings

---


## Prompt-only Notion routing

Choose Claude Opus 5.5, Claude Opus 5, GPT-5.6 Sol, Kimi K3, or GPT-6 Luna from Multi-Script's own startup profile picker. On each new chat, Multi-Script sends one focused routing block before the shared system prompt. It never clicks Notion's direct model selector, making this compatible with Business Trials locked to Auto. Routing remains best-effort because only Notion controls the private backend model.

## Future-ready Claude Opus 5.5 and GPT-6 Luna profiles

Anthropic released Claude Opus 5.5 on September 22, 2026. Notion had not announced it at validation time, so Multi-Script includes honest future-ready profiles for Opus 5.5 and GPT-6 Luna. For Opus 5.5, select **Claude Opus 5.5** under **Notion Auto preferred model**. It requests the real model once at the start of each new chat when Notion makes it available; until then it falls back to Standard Auto without imitation or false identity claims.


## Blender-to-engine delivery

When Blender and a target-engine MCP are both connected and the player requests delivery, Multi-Script already uses a sequential source-to-target pipeline: inspect the target project and conventions; author geometry, UVs, materials/textures, rigs and animation in Blender; export FBX or glTF/GLB with target-specific axes, units, transforms, bones and clip settings; import through the target engine’s currently advertised native MCP tools; rebuild/assign native materials where needed; verify scale, pivots, hierarchy, skeleton/avatar mapping, clips, root motion, collisions, LODs and platform budgets; then read back the imported engine state and runtime-test it. Blender authoring and target inspection may run in parallel, but export/import and validation remain sequential. The system never claims Blender content was delivered merely because an export file exists.

## Arena Direct Max adaptive routing

Arena has provider-specific, model-targeted starter profiles separate from Notion Auto. Claude Opus 5.5 is the default; Claude Opus 5, GPT-5.6 Sol, Kimi K3 and GPT-6 Luna are selectable. Every outgoing turn carries the selected exact-model request plus its real capability mix so Arena Direct Max can route toward that model prompt by prompt. Untargeted Direct Max is optional. Multi-Script never manipulates the picker, falsely claims a backend, or bypasses access controls.

## Automatic keyless local and optional ElevenLabs sound generation

When a user asks Multi-Script to create a sound effect, ambience, Foley, UI sound, audio loop, or musical element, the bridge now generates a real local WAV by default with no account, network call, quota, or API key. It hands the asset to Roblox Studio, Unity, Godot, Blender, or another connected tool for import and runtime testing. Optional ElevenLabs remains available for complex natural material when the player explicitly configures and selects it.

One-time setup:

```bash
python runtime/configure_elevenlabs.py
```

Enter the API key in the hidden terminal prompt and restart the bridge. The key stays in `runtime/.env` or the `ELEVENLABS_API_KEY` environment variable and is never stored in the browser extension. ElevenLabs account quota and licensing still apply.


## Roblox Studio Professional Expansion

Roblox now has **90 virtual specialists** (up from 60) plus **24 new direct provider-model tools** for DataModel/service architecture, strict module contracts, remote security, DataStore and cross-server reliability, StreamingEnabled, Parallel Luau and Actors, network ownership, animation/character runtime, responsive UI, touch/gamepad/VR, scalable NPC pathfinding, MicroProfiler/render budgets, asset delivery, monetization, live operations, localization, accessibility, multi-client testing, and release evidence.

All **199 existing Roblox skills** and the original 60 Roblox virtual tools were upgraded to `roblox-studio-v3`: explicit server/client/editor ownership, lifecycle cleanup, respawn/late-join/streaming safety, weakest-device budgets, and Edit/Server/Client validation with clean Output and project read-back. These improve the provider model; they do not fabricate Studio commands. Real execution still uses only the connected official/live Roblox Studio MCP tools. Version 6.20 adds 24 opt-in companion tools through the Studio plugin, with Off/Read/Project/Full permission tiers, ephemeral loopback authentication, bounded jobs, and no arbitrary Lua evaluation. Official Studio MCP tools remain separate and continue to work normally.


## Multi-engine professional v3

Unity, Godot, and Blender now each have **70 virtual specialists**, with every existing profile upgraded to an engine-specific professional-v3 standard. Twelve new direct specialists cover Unity DOTS/Addressables/rendering/netcode, Godot scenes/resources/rendering/multiplayer, and Blender topology/Geometry Nodes/rigging/render-color workflows. These skills and tools improve what the active AI model already knows: they add structured craft checks, exact native-tool discipline, integration, edge-case handling, profiling, and verification so an animation, system, interface, model, or level is materially stronger than an unaided first response. They are not separate artifact generators and never replace genuine native engine execution.

Arena, ChatGPT, and DeepSeek adapters now include open-shadow-root discovery and semantic composer-control fallbacks. Arena retains strict Direct-mode readiness, deterministic A/B candidate handling, verified sends, and manual-only human-verification handling; no challenge bypass is attempted.

## 300 engine-specific virtual tools

All skills and tools improve the active AI provider model. They do not add or impersonate native engine commands; real changes are executed only through the respective engine integration’s live advertised tools.


Multi-Script includes 50 virtual tools each for Roblox Studio, Unity, Godot, and Blender. They cover UI, animation, textures, graphics, shaders, lighting, VFX, models, rigging, audio, gameplay, networking, saves, optimization, testing, and production. Automatic mode silently matches the exact prompt to the strongest tools, uses their engine-specific expertise to improve the work, and then immediately performs the actual MCP changes.

Four compact gateway commands list, match, inspect, and run the catalog without wasting model context on 300 separate schemas. The internal augmentation stays hidden, explicit prompt details remain binding, and the real engine artifact remains the deliverable.

## Automatic capability stacks

Specialized skills and tools directly improve the aspects they own. The user asks normally and Multi-Script performs the task normally; relevant techniques silently improve the design, implementation, polish, accessibility, performance, and testing. It does not make the user watch a skill-selection workflow. Complex orchestration remains available only when it genuinely helps. The real project result—not the skill call—is the deliverable.

Dedicated professional pipelines cover animation, textures and materials, art direction, UI/UX, VFX, and audio. Every one of the 800 skills is linked to at least four collaborators, producing 2,000 validated skill relationships.

## Professional handling of vague prompts

Multi-Script does not require the user to write a perfect specification. If a request is short, vague, or poorly structured, the agent uses `ms_prompt_rescue` to preserve the intent, infer conservative project-aware defaults, establish acceptance criteria, and create the smallest polished end-to-end result. It asks only when a decision is destructive, irreversible, paid, credentialed, or genuinely contradictory.

For larger requests, virtual tools cover game blueprints, vertical slices, system design, balance, multiplayer authority, save migrations, performance budgets, accessibility, content pipelines, playtests, and strict definition-of-done gates. These complement the 500 engine workflows rather than replacing real implementation in Roblox Studio, Unity, or Godot.

