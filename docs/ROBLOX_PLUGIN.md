# Multi-Script Roblox Studio Workbench — 6.49.9

## Install and connect

1. Install current Dev, run Setup from its permanent folder and start the bridge using the chatbar terminal button.
2. Copy `roblox-plugin/MultiScriptCompanion.server.lua` into Studio's local Plugins folder. Replace the previous copy and avoid duplicate plugins. Restart Studio and open your place.
3. Allow HTTP Requests if Studio prompts or blocks the connection. Open Plugins → Multi-Script Companion.
4. Check bridge/version in Overview. In Toolset, enable the checkbox and select Read, Project or Full. Full requires a second confirmation click. Deselect individual tools as needed.
5. Separately enable Studio as MCP Server in Studio's MCP settings for native execution, playtests and capture. The companion does not turn that server on.
6. Refresh the provider tab after upgrading. Start a Studio engine session in a fresh conversation. Ask for list_commands, then ms_direct_tool_details with an exact advertised tool name.

Windows plugin folder: `%LOCALAPPDATA%/Roblox/Plugins/`.
macOS plugin folder: `~/Documents/Roblox/Plugins/`.

## Four tabs

Overview shows bridge health, native MCP separately, companion permissions, inventory, selection and a non-destructive heuristic scan. A high scan score is not a playtest.

Toolset controls companion execution. Individual choices persist; permission resets to Off when Studio restarts. Availability depends on both tier and checkboxes.

| Tier | Maximum tools | Access |
| --- | ---: | --- |
| Off | 0 | Diagnostics only |
| Read | 8 | Project inspection and execution receipts; no script source |
| Project | 17 | Read plus object/property edits and checkpoints |
| Full | 26 | Project plus source editing, staged transfer, deletion and undo/redo |

Console shows actual bridge/native/companion receipts: command, duration, outcome and permitted output. The AI reads the same stream with msrb_console_read. Higher-tier output is redacted at lower tiers. This bounded history reports individual calls, not overall game completion. The AI still runs in its provider tab; this is an execution console, not a second AI host or operating-system terminal.

Guide explains connections, workspace modes, source editing, sounds and animation.

## Large source and editor changes

Prefer Full-tier msrb_replace_script for complete Script/LocalScript/ModuleScript replacement. The bridge stages sources larger than 32 KiB in UTF-8 chunks, up to 4 MiB, then requests one commit. Keep msrb_source_transfer enabled too. Incomplete staging does not edit source. An uncertain commit has an explicit status lookup; inspect it before retrying.

Source reads/edits use the current Script Editor buffer. Concurrent user edits cause refusal so the AI can re-read and merge. Reads are paged: continue using next_offset. Read-tier property inspection cannot expose Source.

Native MCP schemas, provider quotas and Luau compiler limits still apply. Reorganize large functions into coherent modules/scopes. Never split arbitrary code into independently executed fragments to conceal an incomplete operation.

## Troubleshooting

- Bridge offline: run Setup/start the bridge; check HTTP permission and matching versions.
- Native tools missing: enable Studio's official MCP server. execute_luau is native; msrb_* tools are companion tools.
- Companion tools missing: enable Toolset, select the tier, check the individual tool and refresh the catalog.
- Chat studio says no editor: that mode is intentionally engine-free. Start Studio engine mode in a fresh chat.
- Build software asks about files: select a desktop workspace in Code & Build. It works without Studio; engines are an optional add-on.
- Model says it cannot see: inspect an actual tool result. A connection label is not a screenshot. Capture requires native tools and OS permission.

## Connection and editing boundaries

The companion uses a token-authenticated loopback bridge, bounded queues and allowlisted handlers. Both sides check tiers/tool selection; mutation requires Edit mode. No arbitrary Lua evaluator is added. Keep source control/backups for important places.

References: [ScriptEditorService](https://create.roblox.com/docs/reference/engine/classes/ScriptEditorService), [Script.Source](https://create.roblox.com/docs/reference/engine/classes/Script/Source), [Studio widgets](https://create.roblox.com/docs/studio/build-studio-widgets).

Behavioral tests use Roblox API fixtures. Browser images are design previews, not native Studio screenshots. Live native Studio, upload permissions and every signed-in provider account are not certified by these tests.
