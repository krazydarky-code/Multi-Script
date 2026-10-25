# Multi-Script 6.17.1 — Roblox Studio `studio_id` Contract

## What was reported

Two errors, from the same session:

```
ERROR: the Multi-Script command did not run because it was not one complete plain-text
JSON object. Reply with exactly one object and nothing else: {"command": "exact_name",
"params": { ...all parameters... }}. Do not use code fences, XML-like tags, ...
```

```
ERROR in execute_luau: execute_luau: invalid parameters: parameters.studio_id is required

Check your Lua syntax, make sure you use 'return' to output values (not 'print()'), and
that all APIs you call exist in the current Roblox Studio context.

Fix the code and retry.
```

These are the **same bug**, not two. The second is the cause; the first is the symptom.

## Root cause

Roblox's official Studio MCP requires a `studio_id` argument on **every** place-scoped
command. Studio `6.17.0` and earlier never mentioned it — not in the system prompt, not in
`TOOL_NOTES`, not in the argument normalisation. So the model never sent it, and the server
rejected the call.

It was found in this repo's own log rather than guessed. `runtime/logs/bridge_debug.log`:

```
-> tool  execute_luau(code, datamodel_type, studio_id)
<- execute_luau (0.0s): execute_luau: invalid parameters: parameters.studio_id is required
[roblox] stderr: WARN ... sent a request without studio_id but multiple studios are connected
```

That last line is the whole reason the failure looked **intermittent**:

| Studios attached | What the proxy does with a missing `studio_id` |
| --- | --- |
| exactly one | silently auto-selects it — the omission is harmless |
| two or more | rejects every command that omits it |

So a single-Studio test reproduces nothing, and a real multi-window session fails constantly.

## Why the first error followed

When `execute_luau` was rejected, the model was told to "check the command's parameters with
`list_commands`". On arena.ai and DeepSeek that catalogue is large enough to be truncated, so
the model could not find the missing parameter, could not fix the call, and fell back to
reasoning in prose — producing the non-JSON reply. Fixing the parameter fixes both.

## The fix

**1. The parameter is now documented in all three surfaces the model reads**

- the system prompt's `JSON-ONLY CONTRACT`, including the `execute_luau` example
- the required-parameter marker in `list_commands` (no `?`)
- an appended `STUDIO ID:` note on every place-scoped tool

The note explains *why* it looks optional, because that is what makes a model skip it:

```
STUDIO ID: this command also needs params.studio_id - copy the exact "id" from
list_roblox_studios. Omitting it fails with "parameters.studio_id is required" whenever more
than one Studio is open (with exactly one open the proxy silently auto-selects it, which is
why the failure looks intermittent).
```

**2. Auto-fill, and a refusal instead of a guess**

| Situation | Behaviour |
| --- | --- |
| one Studio known, model omitted the id | inject it silently |
| model supplied an id | never overwritten |
| **several** Studios, no explicit choice | **refuse** and list the candidates |
| nothing learned yet | refuse and name `list_roblox_studios` |
| tool is not place-scoped | untouched |

Refusing the ambiguous case is deliberate. Guessing would let the proxy run the edit against
the **wrong place**, and the user would see a different project mutated with no error at all —
strictly worse than a clear failure.

**3. The id is learned eagerly, on the backend**

The extension reads the id out of any answer that mentions it, and the bootstrap now probes
`list_roblox_studios` **once** before the model's first command. That probe costs no model turn
and shows no message — it is the specific gap that made Roblox fail on arena.ai and DeepSeek,
where the model goes straight to a command without discovering the catalogue first. It is
best-effort: if it fails, the prompt still tells the model to discover the id itself.

**4. The error is now corrective**

A missing `studio_id` no longer forwards the raw server text and points at a truncated
catalogue. It names the parameter, explains the asymmetry, quotes the known id, and says to
retry the **same** command:

```
ERROR calling 'execute_luau': execute_luau: invalid parameters: parameters.studio_id is required
studio_id is REQUIRED on every Roblox place-scoped command (execute_luau, multi_edit,
script_read, inspect_instance, search_game_tree, ...). It only looks optional because with
exactly ONE Studio open the server silently auto-selects it; with two or more attached, every
command that omits it is rejected. The Studio id known this session: 8521cfad-... - use that one.
Retry the SAME command with "studio_id" added to params - keep every other parameter exactly as it was.
```

## Also fixed: four pre-existing engine leaks

Found while testing the engine-aware prompt. None were introduced by 6.17.x — they were live
in 6.15.0:

| Leak | Effect on a Godot-only session |
| --- | --- |
| Roblox example envelope shown as the JSON format example | model tries `execute_luau` |
| `multi_edit needs "datamodel_type"` as the required-param example | wrong vocabulary |
| "BUILD UI/OBJECTS FIRST … create instances with `execute_luau`" | wrong tool, wrong engine |
| "Prefer DIRECT ROBLOX STUDIO implementation" in the creative-surface rule | points at a disconnected engine |

Each now has an engine-neutral equivalent. A non-Roblox prompt carries no copyable Roblox
envelope.

## What was verified as NOT replaced

The user asked specifically whether working parameter setups were discarded. They were not.
`tests/test_roblox_studio_id.js` asserts these are present **verbatim**, with the new text
appended rather than substituted:

- the original Godot rule (`ms_get_skill` → `godot-mcp-orchestrator`, `get_godot_version`,
  `get_project_info`, `run_project`, `get_debug_output`, `stop_project`)
- the original Unity rule (`ms_get_skill` → `unity-mcp-orchestrator`, `ms_list_resources`,
  `ms_read_resource`)
- `ALWAYS pass a timeout to WaitForChild`
- `WATCH FOR BAD UNICODE in old_string`
- all four Roblox `TOOL_NOTES` (`execute_luau`, `multi_edit`, `inspect_instance`, `script_read`)

The 6.17.0 engine layer **appends** a `NATIVE COMMAND RULES FOR THE CONNECTED ENGINE(S)`
section below the existing rules; it never replaces them.

## Testing

- **New:** `tests/test_roblox_studio_id.js` — 29 assertions covering the contract, the
  classification of every place-scoped tool (and that non-place tools are excluded), each
  fill-in outcome, all four observed JSON shapes for learning, that prose is never mined for
  ids, the prompt/notes coverage per engine combination, and the verbatim survival of every
  pre-existing note.
- **Updated:** `tests/test_engine_tool_layer.js` — the per-engine strictness example is now
  asserted per combination instead of for all of them, and a Godot-only prompt is asserted to
  contain **no** `studio_id` and **no** copyable Roblox envelope. This is the assertion that
  caught the leaks above.
- **Full suite:** 30/30 Node tests pass.

## Files changed

| File | Change |
| --- | --- |
| `extension/core/engines.js` | `ROBLOX_NOTE`, `ROBLOX_PLACE_TOOLS`, `needsStudioId`, `withStudioId`, `studiosFromBody` |
| `extension/core/config.js` | `FEEDBACK.studioId`; `studio_id` in the prompt contract + `execute_luau` example + per-tool notes; engine-conditional examples, build rule, creative-surface rule and parameter example |
| `extension/core/main.js` | `A.studios` state; `withStudioId` fill-in; passive learning; backend `list_roblox_studios` boot probe; corrective required-param error |
| `tests/test_roblox_studio_id.js` | new |
| `tests/test_engine_tool_layer.js` | per-engine assertions |
| 12 version files | `6.17.0` → `6.17.1` |
