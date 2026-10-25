# Multi-Script 6.30.0

## Fixes
- **`WebSocket connection to ws://127.0.0.1:17613/ failed: ERR_CONNECTION_REFUSED`** on chrome://extensions: the background worker now probes the bridge's HTTP `/status` endpoint first and only opens the WebSocket when the bridge answers (it still tries the socket directly every 6th miss), so a stopped bridge no longer floods the Errors page.
- **`[godot] auto-restart failed: [Errno 22] Invalid argument`**: when an MCP launcher exits during startup the bridge now reports `the <id> launcher exited during startup (exit code N)` plus its last stderr lines. The real cause is usually a missing Node 18+/npx, or `GODOT_PATH` not set.
- **Setup "up · 0 tools"**: the final check now explains each case (Unity: open the editor with MCP for Unity; Blender: click Connect in the BlenderMCP panel; Godot: tools load on first use and need Node 18+ and `GODOT_PATH`; Roblox: open Studio and enable MCP).

## New
- **Sounds & alerts** (Settings → Look): ping when the AI finishes, a tick when a command runs, a low tone on errors. Master switch, per-event toggles, Ping/Soft/Arcade styles, volume, test buttons. Synthesised with WebAudio: no audio files and no network.
- **Design refresh** for the settings menu and chat bar: accent-tinted active tab, focus rings, accent-coloured sliders/checkboxes. Respects every theme.
