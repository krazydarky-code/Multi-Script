# Multi-Script 6.24.0 — release notes

## Highlights

- **Terminal icon = the bridge.** `start.bat` and `MacOS_Start.command` are removed. The chat-bar terminal icon starts, stops and restarts `runtime/bridge.py` through a Chrome Native Messaging host (`runtime/native_host.py`) and shows its live log; the caret opens a **Running** list (bridge, MCP servers, engine apps). The bridge starts automatically when an AI site opens (switchable, and a manual Stop is respected). One-time setup: `Setup.bat` / `MacOS_Setup.command` → `runtime/install_native_host.py`.
- **JSON-schema errors.** `runtime/schema_repair.py` repairs arguments against the live tool schema before validation (numeric strings, booleans, vectors, envelopes, renamed keys, enum case, clamping) and reports each repair. The page parser recovers curly-quoted / single-quoted JSON.
- **Native engine toolkit (109 tools).** Blender 30, Roblox 27, Unity 31, Godot 21, surfaced only for engines with a configured MCP server, with the same schema repair as every other tool. Blender gets a launcher (`launch_blender_mcp.py`).
- **Notion AI.** Bar aligned to the composer's text column and resize-aware; a Notion settings tab with model detection (agent mode), model + effort selection through Notion's picker (verified against the label), and a rough trial/credit estimator (`core/notion-usage.js`).
- **Settings reorganised** into Studio / Agent / Notion / Interface / Engines (Bridge first) / AI sites / Help; changing a setting no longer bounces you to another tab.

## Honest limits

- Browsers cannot start programs on their own: the one-time `Setup.bat` / `MacOS_Setup.command` step is required for the icon to run the bridge.
- Notion's DOM is hashed and changes often. Model detection/selection is matched on roles and text and was verified against a faithful mock of the picker, not against live Notion. Selection reports `verified` only when Notion's label changed to match.
- Notion has no public credit price or trial API. "Prompts left" is an estimate from your own counts and readings (default weights until you give it two readings) and is always shown as a range.
- The engine toolkit was verified against mocks (mock `bpy`, a Luau VM mock of the Roblox API, a temporary Godot project, a fake Unity MCP) rather than live editors.

## Verification

`python tools/release_check.py`, then the suites in `.github/workflows/ci.yml`; new: `test_engine_toolkit.py`, `test_schema_repair_and_native_host.py` (starts the real bridge through the host), `test_notion_usage.js`, `test_parser_repair.js`, `test_studio_ui.js` (real Chromium against a mock Notion page).
