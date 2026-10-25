# Multi-Script 6.19.1 — Notion Chat

## Notion AI appears in new chats again

Notion's current AI chat lives at `https://app.notion.com/chat`. That host was missing from the extension's content-script and host-permission lists even though the adapter itself documented the app.notion.com surface. The result was a total non-injection: no Multi-Script bar in a new chat.

This release adds app.notion.com consistently to the manifest, background status broadcasts, popup detection, and one-click repair path. The Notion switcher now opens the real chat route instead of the old notion.so workspace root, which could lead to Connectors/settings. The adapter also recognizes the current “Ask anything” composer wording.

After installing this release, reload Multi-Script once at `chrome://extensions` or `edge://extensions` so the browser grants the new app.notion.com host permission.

## In-settings setup tutorial

A new **Setup** category explains the whole product path inside the menu:

1. Extract and load the extension.
2. Start the local bridge.
3. Connect Roblox Studio, Unity, Godot, Blender, or another real MCP server.
4. Open the correct AI chat, including the exact Notion URL.
5. Start a session and verify it with a small read-only request.

The tutorial includes live bridge/editor/composer status, a setup check, a copyable checklist, direct navigation to Engines setup, and a category map.

## MCP catalog correction

The catalog remains at the existing 230 direct tools. The two redundant MCP prompt wrappers proposed in 6.19.0 were removed; connected servers remain authoritative through their live advertised native tools, schemas, catalogs, routing, and resources.

## PlazCode-derived provider improvement, without the IDE

Multi-Script now supports Claude directly on claude.ai and claude.com. The provider adapter was adapted from PlazCode 1.18.74’s GPL-3.0 implementation, then renamed, generalized from Roblox-only wording to Multi-Script’s multi-engine bridge, and wired into the same enhancer, effort, pacing, recovery, verification, trust, menu, and tool pipeline as every other provider.

No PlazCode IDE, desktop executable, AgentScript workspace runtime, branding, or desktop UI is included. Attribution and licensing are recorded in `docs/THIRD_PARTY_NOTICES.md`.
