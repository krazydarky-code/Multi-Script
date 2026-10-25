# Multi-Script 6.17.5 — Roblox Schema Conformance

**Release type:** correctness. No behaviour was removed; a set of copyable tool shapes that had been
written from memory were corrected against the live Roblox Studio MCP server's published schemas, and
permanent gates were added so they cannot drift back.

---

## Why this release exists

Multi-Script teaches the model how to call each tool with a **required-shape template** — a literal
JSON envelope that leads the tool's note, because a model skimming prose for "what do I write" omits
required fields. For Roblox, those templates are a **mirror** of the live `StudioMCP` server.

A mirror that is wrong is worse than no mirror: the model copies the example verbatim, the server
rejects it, and the rejection reads as a product bug. Nine Roblox shapes had been written from memory
rather than read from the server's own parameter schema.

## Corrected shapes

| Tool | Was | Is |
|---|---|---|
| `generate_mesh` | `prompt` | **`textPrompt`** |
| `wait_job_finished` | `generation_id` | **`jobId`** |
| `screen_capture` | *(no capture id)* | **`capture_id`** (required) |
| `search_game_tree` | *(no datamodel_type)* | **`datamodel_type`** (required) |
| `script_grep` | `keywords` | **`query`** |
| `insert_asset` | `assetId` as Number | **`assetId` as string** + `assetName` |
| `multi_edit` | `file_path` inside each edit | **`file_path` top-level** |
| `generate_procedural_model` | *(synchronous assumed)* | **`async:true`** → returns a `jobId` |
| `character_navigation` | `path` + `destination{}` | **`datamodel_type:"Client"`** + `instance_path` or `x`/`y`/`z` |

`script_search` still takes `keywords` — the two search tools genuinely differ, which is exactly the
kind of thing a guess gets wrong.

## Two silent duplicate-key bugs

In a JavaScript object literal, a duplicated key is legal and the **last one wins**; `node --check`
cannot see it, and neither can any value-level read of the object. Two were live:

- `search_game_tree` was defined twice in `ROBLOX_TEMPLATES`.
- `generate_mesh` and `generate_procedural_model` were each defined twice in `TOOL_NOTES`
  (`core/config.js`), so the earlier, richer text in each pair was dead code.

Both are fixed, and a source-level duplicate-key scanner now runs as a permanent gate.

## Added coverage

Seven new Roblox template/note pairs for the build surface — `insert_asset`, `search_asset`,
`get_console_output`, `screen_capture`, `generate_mesh`, `generate_procedural_model`,
`search_game_tree` — plus the discovery tools `list_roblox_studios`, `character_navigation`, and
`skill`. `ROBLOX_GLOBAL_TOOLS` declares which tools take **no** `studio_id`, so a model cannot invent
one on `list_roblox_studios`, the single most likely first call of a session.

Every native tool now ships a required-shape template.

## New gates

- **`tests/test_roblox_schema_conformance.js`** (new, 6 sections) — pins every corrected parameter
  name; fails the build if a template drifts back to a guess.
- **`tests/test_engine_registry_integrity.js`** — grew a source-level **duplicate-key scanner**
  (string- and comment-aware) and a **global-vs-place-scoped** consistency section.
- **`tests/test_required_param_contract.js`** — now asserts `multi_edit`'s `file_path` **nesting**,
  not merely that the word appears somewhere in the template.
- **`tools/release_check.py`** and **`.github/workflows/ci.yml`** — both new tests are enforced.

## Docs

`docs/engine-command-reference.html`: the Roblox table corrected — real required params, the full
build surface, and the two fields (`textPrompt` / `jobId`) most likely to be guessed wrong.

## Also fixed

`tests/test_all_skills_and_tools.py` cleaned its scratch output with `shutil.rmtree`, which trips a
host bulk-delete guard above 50 paths and killed the process before its PASS line — a green test that
looked like a red one. It now unlinks file-by-file and finishes clean in ~2m40s.

## Verification

- Node suite: **36/36**
- Python suite: **29/29** (green individually; the exhaustive audit takes ~2m40s)
- `tools/release_check.py`: **PASS**
- Content-script load contract: **6/6** sections (the 6.17.4 blackout gate still holds)
