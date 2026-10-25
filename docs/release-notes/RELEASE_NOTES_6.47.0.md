# Multi-Script 6.47.0 Dev

The Roblox companion is rebuilt as a dark, studded Studio Workbench with Overview, Toolset, Console and Guide tabs. A master checkbox and 26 individual selections control Read/Project/Full tools. Native Studio MCP health is shown separately from companion access.

Tool details now resolve actual advertised native, toolkit and companion schemas, including execute_luau. Unambiguous tool-name argument aliases and the run_lua spelling are recovered. Chat studio hides and blocks engine operations; Build software uses its selected desktop folder without requiring Studio. Companion tools are discoverable even if native MCP is offline.

Full-tier script editing preserves the current editor buffer. Large source writes stage UTF-8 chunks before one commit, reject concurrent user edits and support explicit uncertain-commit status recovery. Oversized schema inputs are rejected instead of silently clipped. Native/provider/compiler limits still apply; use coherent modules for large code.

The execution console exposes actual receipt status/output to the AI with permission-aware redaction. A green chip does not prove that a game is finished. Notion now sends once and pauses on uncertain acknowledgement rather than replaying tool results. Its saved model preference cannot select or unlock a backend model.

See [Roblox setup](../ROBLOX_PLUGIN.md), [copyable workspace/media setup posts](../MODES_AND_MEDIA.md), [phone tutorial](../DISCORD_PHONE_TUTORIAL.md) and [updates](../UPDATES.md). Install Dev. Public 6.42.0 stays frozen inside the bundle. Refresh provider tabs after updating; replace the Studio plugin from this Dev package and restart Studio.

[QA scope and executed checks](../QA_6.47.0.md). Native Studio and authenticated provider accounts are not certified by fixture tests. No claim of zero bugs, unlimited code execution or independent AI hosting in Studio is made.
