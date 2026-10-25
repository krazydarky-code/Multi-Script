# Multi-Script 6.15.0 — Universal Capability Visibility

- Added `list_multiscript_capabilities`, a compact provider-visible index for all 210 direct commands, 800 skills, 300 internal specialists, and native MCP sources.
- Added the `multiscript` capability source to `list_mcp_servers`; native engine counts are now explicitly identified as only native counts.
- `list_commands` now begins with the Multi-Script capability index so providers cannot miss it when long schemas are truncated.
- Added `list_commands {"server":"multiscript"}` and `server:"all"` routing.
- Multi-Script direct commands remain visible and callable when Roblox, Unity, or another native editor is registered but disconnected. Cached commands from an offline native editor are hidden to prevent false execution.
- Skills and specialists remain retrieved on demand to preserve context, but their counts and discovery commands are always visible.
