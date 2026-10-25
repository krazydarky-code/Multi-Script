# Multi-Script 6.36.0 — Code mode, Software Builder revamp, perfect tool schemas, bar theme fix

## Chat bar / theme fix
- Some normal themes made the chips, status text and chat bar unreadable: a light bar theme (Frost, Paper, Sakura, Classic Roblox) on a dark site, or a dark one (Graphite, Ink, Midnight, Mono, the scene themes) on a light site, put dark ink on a dark composer (or light ink on a light one).
- Root cause: the page light/dark detector matched Multi-Script's own `zs-light` class as a page hint, so once a light menu theme was picked the page was "light" forever.
- Fixed: our own `zs-*`/`ms-*` classes are ignored by the detector, and a bar whose theme disagrees with the page now paints its own themed surface (`data-ms-bar-clash`). Verified headlessly on dark and light pages for all 25 themes.

## Software Builder → Software Builder & Code mode
- **Mode** in Settings: *Build software* (scaffold, build, package a new app) or *Code mode*, a general coding agent for ANY folder on your PC that works with every provider. The bar button becomes `‹› Code`.
- **Add-ons** per session: Skills & review (Multi-Script's general skill, critic and memory tools, on by default), Game engines (also allow connected Roblox/Unity/Godot/Blender tools) and Other MCP servers.
- **27 workspace tools** (was 16). New: `ms_ws_glob`, `ms_ws_read_many`, `ms_ws_outline` (symbols for 15 languages), `ms_ws_patch` (multi-file unified diffs with context matching), `ms_ws_replace` (project-wide, dry run by default), `ms_ws_undo` (every write/edit/patch/replace/delete is journaled), `ms_ws_diff`, `ms_ws_git` (read-only actions always; writes need Run commands; injection-safe argv), `ms_ws_check` (typecheck + lint + test in one call), `ms_ws_http` (localhost only), `ms_ws_plan`.
- `ms_ws_edit`: tolerates CRLF files and trailing whitespace, adds line-range edits, `dry_run` diffs and fuzzy "closest line" hints. `ms_ws_search`: case-sensitivity, sub-folder and context lines. `ms_ws_run`: `env`, CI-safe environment, and background processes are stopped as a whole process tree.
- Build recipes add `lint`, `format` and `typecheck` (npm/pnpm/yarn, Python ruff/pyflakes/mypy, dotnet, cargo, go) plus Godot and static web projects.
- New prompts for both modes: explore → plan → read → smallest change → `ms_ws_check` → report with `ms_ws_diff`.

## Tool schemas
- New `runtime/schema_perfect.py` normalises EVERY advertised schema at publish time, including the live ones the engines' MCP servers report: arrays get `items` (OpenAI rejects arrays without them), missing types, legacy type names, draft-3 `required: true`, required names that aren't properties, duplicate enums and min > max are all repaired. It never removes a property or loosens an enum.
- Engine-aware parameter docs fill missing descriptions with the right units and axes per engine (Roblox studs, Y-up; Unity metres, Y-up, left-handed; Godot metres, Y-up, res:// paths; Blender metres, Z-up). Undocumented parameters went from 1,904 to 391 of 2,936.
- Audit across 461 tools: 33 structural defects found, 0 remain. Handler/schema mismatches fixed: `timeout_seconds` is now declared on `ms_blender_render`, `ms_blender_run_python` and `ms_roblox_run_luau` (with the real clamps), `location` on `ms_blender_physics` and `preview_script` on `ms_godot_model_tools`; `ms_form_guidance.parts` gets a real item schema.

## Tests
- New `tests/test_workspace_636.py` (38 end-to-end checks of every workspace tool) and `tests/test_code_mode_636.js`.
- Updated stale counts in older tests (tool count 259 → 270, themes 13 → 17).
