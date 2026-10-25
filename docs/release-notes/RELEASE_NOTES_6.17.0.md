# Multi-Script 6.17.0 — Native Engine Command Layer

## The transport question, answered

**The JSON transport stays exactly as it is for every engine — including the
non-Roblox ones.** A second wire format for Godot/Unity/Blender would be a
regression, not an improvement, for three concrete reasons:

1. **MCP *is* JSON.** The Model Context Protocol is JSON-RPC, and every MCP tool
   declares its parameters as a JSON Schema. The transport is already the native
   format of the thing on the other end. Any other encoding would be a
   translation layer we would have to write, maintain and debug.
2. **One transport means one parser, one camouflage path, one error path.** The
   parser, the `###LUA###` fallback, the cut-off salvage, the "malformed
   envelope" nudges, the chip masking and the parse-error recovery are all keyed
   off one shape. A per-engine dialect would fork every one of those, and the
   failure modes would multiply instead of the capability.
3. **A different format cannot fix the actual problem.** The engines were not
   failing because JSON is wrong. They were failing because their *vocabulary*
   is different, and the extension was teaching one vocabulary — Roblox's.

So what actually made non-Roblox engines "not work properly" was three things,
all of which this release fixes:

| Engine | Correct command shape | The mistake the old build invited |
| --- | --- | --- |
| **Roblox Studio** | `{"command":"execute_luau","params":{"code":"…","datamodel_type":"Edit"}}` — one flat tool per action | *(unchanged — keep the JSON)* |
| **Unity MCP** | `{"command":"manage_scene","params":{"action":"get_hierarchy","page_size":50}}` — **action-dispatch**: ONE tool, an `action` string selects the operation | The model writes `{"command":"get_hierarchy"}` — the *action* where the *tool* belongs. This is the single most common Unity failure, and the old build answered "unknown command", which reads to the model as "this engine cannot do that" and derails the task. |
| **Godot MCP** | `{"command":"run_project","params":{"projectPath":"/abs/folder/with/project.godot"}}` — flat, but **camelCase `projectPath`** required on 13 of the 14 tools | `path`, `project_path`, `projectDir`, a relative path, the `project.godot` file itself, or a `res://` path. Also: `list_projects` takes **`directory`**, not `projectPath`. |
| **Blender MCP** | `{"command":"execute_blender_code","params":{"code":"…"}}` — code execution | An unescaped `"` inside the Python breaks the JSON envelope, so the command silently never runs. |

The table above is the answer to "what should the transport commands be". They
are still JSON — but the *commands inside them* are now the engine's real ones.

## What changed

### A native-tool registry for every non-Roblox engine (`core/engines.js`)

A pure, dependency-free registry (no DOM, no `chrome.*`, injectable — unit-tested
in plain node) holding, per engine: the real tool names, their **required
parameter spellings**, their action vocabularies, their chip category, and a
curated usage note per tool.

Every fact is attributed in the source, so nothing is a guess:

- **`[schema]`** — read out of the *published* package build. The 14 Godot tools
  and their exact required parameters were extracted from
  `npm pack @coding-solo/godot-mcp@0.1.1` → `build/index.js` `inputSchema`
  blocks, and the test asserts them literally, so a future edit cannot invent a
  tool or rename a parameter.
- **`[ref]`** — read out of the vendored upstream reference in `vendor/`
  (33 Unity tools, 132 actions, from
  `vendor/CoplayDev-unity-mcp/.../tools-reference.md`).
- **`[live]`** — recorded from an actual observed failure in this codebase.
- If a fact cannot be attributed, it is not in the registry.

### The action-dispatch repair — the Unity fix

`runTool` now detects the classic failure and repairs it in place:

- `{"command":"get_hierarchy"}` where `get_hierarchy` is **not** an advertised
  tool but **is** an action of exactly one advertised tool → rewritten to
  `{"command":"manage_scene","params":{"action":"get_hierarchy"}}`, with a toast
  so the user sees what happened.
- Ambiguous actions (`get_info`, `create`, `screenshot`, `ping` are each owned by
  two or more Unity tools) are **never guessed** — the model is told the
  candidates and asked to pick, e.g. *"'get_info' is an ACTION, not a command,
  and 2 tools accept it: manage_asset, manage_prefabs."*
- The owner must be **currently advertised**, so a stale registry entry can never
  invent a tool the server does not expose.
- Roblox tool names are never touched, and a name that *is* a real tool is never
  rewritten.

Plus: an action-dispatch tool called with no `action` now returns the valid
action list instead of forwarding a call that fails vaguely.

### Curated notes now exist for non-Roblox tools

`TOOL_NOTES` was Roblox-only, so every other engine got **zero** curated
guidance. `ZS.toolNote()` now merges the Roblox notes with the registry's, and
`list_commands` plus the periodic reminder attach them. These are the tested
gotchas a schema cannot convey: Godot's `projectPath` must be the absolute folder
*containing* `project.godot`; always `stop_project` or the next run fails with
"already running"; Unity's `read_console` is the *only* way to see compile
errors; `run_tests` returns a job id and does **not** wait; Blender code payloads
must be JSON-escaped.

### The prompt is now engine-aware

The shared system prompt was Roblox-first, which actively misled non-Roblox
sessions. `buildSystemPrompt({ engines })` now takes the live connected-engine
list and computes three things from it:

- **The connection paragraph.** A Godot-only session no longer says *"the user's
  open Roblox Studio place is always connected by default"* — it says **"NO Roblox
  Studio is connected in this session"**, names the engines that are, and warns
  that Roblox commands cannot run here and would waste a turn.
- **The project-memory section.** Project memory lives in
  `game.ServerStorage.Multi-Script.Memory`, which only exists inside a Roblox
  place. A Godot session was being told to create it — a command that cannot run,
  followed by losing the memory anyway. Outside Roblox it is now replaced with
  honest continuity guidance.
- **The first-action instruction.** The "if Roblox comes back Studio-offline"
  branch only applies when Roblox is actually connected; otherwise the model is
  told what to do when *any* engine reports a connection error.

Only connected engines get a rules block, and an unknown MCP server gets a
discovery-first rule rather than silence. **With no engine information the prompt
is byte-identical to before** (asserted by the test), so nothing regresses for
existing setups.

### Engine-aware chips and offline messages

`toolCategory` now asks the registry before its keyword heuristics, so a Godot
`run_project` reads as an action and a Blender viewport capture reads as a screen
capture instead of every non-Roblox tool collapsing into "generate". The
bridge-offline note no longer tells a Godot-only user to go and open Roblox
Studio.

## Verification

`tests/test_engine_tool_layer.js` (new, browser-free) pins:

- the **14 Godot tools and their exact required parameters**, asserted literally
  against the published schema — including that `list_projects` takes
  `directory` and not `projectPath`;
- **33 Unity tools and 132 actions**, with **dispatch integrity**: every action
  must point at a registered tool, every dispatch tool must have actions, and no
  flat tool may be flagged as dispatch;
- the repair across all four outcomes — unambiguous, ambiguous (with
  candidates), unknown, and "the owner is not advertised" — plus that it never
  mangles a Roblox tool name, never rewrites a name that *is* a tool, preserves
  the caller's other params, and cannot be made to throw by hostile input;
- the engine-aware prompt across **five engine combinations** (legacy, Roblox-only,
  Godot-only, mixed, unknown server), including that Roblox-only is
  byte-identical to the legacy prompt and that the JSON-only contract survives
  every combination;
- that the Roblox JSON transport still parses unchanged.

All 29 node gates and the full Python suite pass; `tools/release_check.py`
passes. The six real-browser gates (Arena verification, Arena routing, Notion
DOM) pass in Chromium.

## Honest limitations

- The Unity action vocabulary is read from the vendored v10.2.0 reference. If
  upstream adds an action, the repair simply will not fire for that action (the
  model gets the old "unknown command" answer) — it can never invent one. Re-vendor
  the reference to extend it.
- Godot's 14 tools are pinned to `@coding-solo/godot-mcp@0.1.1`. A different
  Godot MCP server has different tools; the registry then contributes nothing and
  the discovery-first rule takes over.
- Blender MCP servers differ substantially. Only `execute_blender_code` and the
  three common read/capture tools are registered, because those are the ones this
  project has evidence for.
- None of this replaces `list_commands`. The live catalogue is always the source
  of truth; the registry only supplies the vocabulary, the parameter spellings and
  the gotchas that the catalogue does not explain.
