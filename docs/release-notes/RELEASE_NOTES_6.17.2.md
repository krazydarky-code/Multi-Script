# Multi-Script 6.17.2 — Release Notes

**Theme: stop the bad-call loop.** A live session was stuck emitting `BAD JSON`
and accumulating more errors than before. Three separate causes, all fixed, plus
a full audit of the engines nobody had been able to test.

---

## What you reported

```
ERROR calling 'multi_edit': multi_edit: invalid parameters:
parameters.edits[0].old_string is required
```

…over and over, degrading into malformed JSON. The command name was right and
the edit was otherwise fine — the model just dropped one required nested field,
could not work out which one, and then fell apart.

You were also right that it got **worse than before**. It did, and that was my
fault. Here is exactly how.

---

## Root cause 1 — the note never showed the call shape

The `multi_edit` note was **1470 characters** explaining how `old_string` must
MATCH — byte-for-byte, watch out for unicode, here is the create-file case — and
**not one line showing what a call looks like.**

A model skimming for "what do I write" reads prose, finds qualifications instead
of a shape, and omits a field. Documentation about *matching* is not
documentation about *calling*.

**Fix.** Every structured tool's note now **leads** with a literal copyable
envelope:

```
REQUIRED SHAPE (copy this, fill the values):
{"command":"multi_edit","params":{"datamodel_type":"Edit","studio_id":"<SID>",
 "edits":[{"file_path":"game.ServerScriptService.Main",
           "old_string":"<exact current text, copied from script_read>",
           "new_string":"<replacement text>"}]}}
```

The original prose is not deleted or rewritten — it follows the template. The
shape leads because the shape is what gets copied.

## Root cause 2 — the rejection path was not corrective

There are **two** error paths, and only one had ever been improved:

| Path | Source | Old message |
|---|---|---|
| `ok:true` | server ran and complained | *(already made corrective)* |
| **`ok:false`** | **bridge validator rejected the args before running** | **`"Read the error carefully, fix the call or try a different approach."`** |

`invalid parameters: …` comes down the **second** path. A generic shrug is
actively harmful here: it does not say the command never ran, does not say which
field was missing, and does not say the tool name was fine — which is precisely
the information the model was missing when it started renaming things and
producing garbage.

**Fix.** That path now says all of it:

```
ERROR calling 'multi_edit': the command was NOT run - its arguments were rejected
before execution because parameters.edits[0].old_string is required.
'old_string' must be present on EVERY object inside the 'edits' array - it is a
nested field, not a top-level one.
Do NOT rename the command and do NOT change anything else: re-send the SAME
command with 'parameters.edits[0].old_string' added to the params you already
wrote (keep every other value as it was).
The required shape for 'multi_edit' is:
{"command":"multi_edit","params":{ ... }}
Raw: multi_edit: invalid parameters: parameters.edits[0].old_string is required
```

## Root cause 3 — the regression I introduced in 6.17.1

The `studio_id` fix appended a multi-line `STUDIO ID:` paragraph to **every**
place-scoped note. That bloated each note and pushed the call shape — when there
was one — out of reading position. Your instinct was exactly right.

**Fix.** The long paragraph is now a short one-line suffix, and the required
shape leads. The contract itself is unchanged and still fully enforced.

## Bug in my own first fix

The nested-path detector I shipped was `^`-anchored:

```js
/^([A-Za-z0-9_]+)\[\d+\]\.([A-Za-z0-9_]+)$/   // never matches the real path
```

The real path is `parameters.edits[0].old_string` — the array access is in the
**middle**, so it must be matched in the middle. The correction silently never
fired. The required-field matcher was also lazy (`+?`), truncating the path to
`parameters`. Both fixed, both now pinned by a test.

---

## Godot / Unity / Blender audited end-to-end

You said you had not tested these. Neither had the code, in the ways that matter.
Auditing found **16 tools with required parameters and no template at all**, so
their notes could not lead with a copyable shape by construction:

- **Godot:** `run_project`, `launch_editor`, `update_project_uids` — added.
- **Unity:** `manage_prefabs`, `manage_material`, `manage_texture`, `manage_ui`,
  `manage_camera`, `manage_graphics`, `manage_packages`, `manage_physics`,
  `manage_probuilder`, `manage_profiler`, `unity_reflect`, `unity_docs`,
  `batch_execute` — added, each carrying an action verified against that tool's
  real action vocabulary.

**One genuine mis-declaration:** `read_console` was registered as a flat tool
while its own note called it `ACTION-DISPATCH` and `ACTION_OWNERS` listed its
actions. Upstream really does take `action="get"` / `action="clear"`, so its
required `action` parameter was never enforced. Now corrected.

**Code transfer.** Code moves as a JSON **string** (`params.code` for
`execute_luau` / `execute_blender_code`, `params.contents` for Unity
`create_script`, `old_string`/`new_string` for `script_apply_edits`), so escaping
is the transfer mechanism — an unescaped `"` is the observed way a C# payload
breaks. The `create_script` and `script_apply_edits` templates now demonstrate
escaped quotes and escaped newlines in real C#, and the test proves a multi-line
C# payload and a Python payload both round-trip **byte-for-byte** through the
real parser.

---

## Verification

- **32/32** JavaScript tests (was 31 — added `test_required_param_contract.js`).
- **28/28** Python tests.
- `tools/release_check.py` **PASS**.
- Nothing good was replaced: every original Roblox `TOOL_NOTES` entry, the Godot
  and Unity orchestrator rules, the `multi_edit` unicode warning and the
  create-script case are asserted present **verbatim**, with new text added
  rather than substituted.

The new test asserts, per engine, that every tool with required parameters ships
a template that parses as JSON, names the tool itself, and carries each required
parameter — so this class of gap cannot silently return.

---

## Upgrading

Replace the extension and restart the bridge. No settings change and no
re-pairing required. The `studio_id` behaviour from 6.17.1 is unchanged.
