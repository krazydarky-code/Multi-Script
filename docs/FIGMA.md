# Connect Figma and create native designs

Included in **6.44.0 Dev**. Use the extension and runtime from this same edition.

## Bundled Multi-Script companion

1. Start the current bridge. In **Settings → Engines → Engine setup guides → Figma**, click **Use bundled launcher**, then **Add addon** and restart the bridge/MCP servers. The command is `launch_figma_mcp.py`, server ID `figma`. Alternatively run `python configure_engine.py figma` from the runtime directory, then restart the bridge.
2. Open **Figma desktop** and an editable Figma Design file. Use a scratch page for the first test.
3. In Figma, choose **Plugins → Development → Import plugin from manifest**, select this package’s `figma-plugin/manifest.json`, then run **Multi-Script Figma Companion**. If Figma requires a manifest ID assigned to you, create a new local development plugin and retain its generated ID while using this package’s main/UI/network fields. This is a development plugin, not a published Figma marketplace listing.
4. Open Multi-Script’s bridge terminal. The Figma server prints an eight-digit pairing code, valid for five minutes and one connection. Enter it in the plugin, choose **Read only** or **Read and edit current page**, then click **Connect this file**. Keep the plugin open.
5. Start an engine-enabled Multi-Script conversation. If Roblox is offline, use the available-engine start path with the Figma server connected; an engine-free chat intentionally cannot edit Figma.
6. Ask the model to call `figma_status` and `figma_get_document` first. `connected: true` and `permission: edit` are required for native changes. A running MCP process alone does not prove an editable file is connected.

If a browser/OS asks for local-device or loopback access, allow it for this local companion. If the web plugin iframe blocks localhost, use Figma desktop; this integration cannot override the host’s network policy. Do not disable browser security or expose the port outside your computer. The listener binds only `127.0.0.1:17616`; its packaged UI/manifest use that port.

## Prove the editing path

Send this in the started Multi-Script chat:

```text
Use the connected Figma companion. Check figma_status and inspect the current page first. In a new scratch frame, create a 390×720 inventory panel with native text and a native button/component. Preserve the rest of the page. Read the real node IDs and properties back, then export the frame as PNG for visual inspection. Report any unverified visual or host behavior honestly.
```

The model discovers exact schemas with `list_commands` for server `figma`. The companion provides:

| Command | Result |
| --- | --- |
| `figma_status` | Paired file/page, freshness and permission |
| `figma_get_document` / `figma_get_node` | Bounded native hierarchy, selection and property read-back |
| `figma_create_node` | Native frame, component, rectangle, ellipse or text |
| `figma_update_node` | Allowlisted geometry, text, fill/stroke and Auto Layout properties |
| `figma_import_svg` | Editable vector import from bounded SVG source; scripts/external resources rejected |
| `figma_export_node` | Real PNG/SVG export from the native node |
| `figma_set_selection` | Selection/focus within the current page |
| `figma_delete_node` | Unlocked scene-node deletion with `confirm: true`; no page/document deletion |

Use the actual returned IDs as parent/target IDs; never invent them. Text fonts load before changing characters/font size. Locked nodes/ancestors and other pages are rejected. Permission and context are rechecked after asynchronous font loading. Capture and inspect the result after native changes; a successful create call does not certify appearance or integration into a game.

Read mode permits inspection, export and selection/focus. Edit mode additionally permits native content changes. There is no arbitrary JavaScript/eval endpoint. The companion does not create entire files, upload marketplace assets, publish plugins or bypass Figma edit/seat permissions.

## Disconnect and recover

Use **Disconnect** in the plugin or stop the Figma MCP server. Restart that server for a new pairing code. Opening a different page invalidates pending commands; inspect the new target before acting again. If a request times out, an edit may have happened: read back the file before retrying. Claimed commands are never replayed automatically. Existing-node native updates can be partial if the host rejects a property after another property changed; inspect before recovery.

The pairing token is held only in memory. The relay exposes pairing, polling and result receipts over loopback HTTP; only stdio MCP can enqueue operations. It permits Figma/opaque plugin origins, requires an exact Host, bounds requests/handlers and rate-limits pairing attempts. Do not share the short-lived terminal pairing code or include it in support screenshots.

## Official Figma MCP is a separate connection

Figma’s [official tools](https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/) include read tools and remote write tools such as `use_figma`. Availability depends on the connected client, account/seat and live server catalog. The [official remote setup](https://developers.figma.com/docs/figma-mcp-server/remote-server-installation/) uses HTTP/OAuth. A raw HTTP URL is not a stdio launch command in Multi-Script’s add-on field. Use an appropriately configured stdio adapter if choosing that separate connection; do not infer write access from a read-only third-party Figma server.

This release’s bundled path is the local native companion above. Its actual signed-in Figma application host remains unverified here because live account testing was declined. The automated test uses the shipped plugin UI, actual HTTP and stdio MCP with a Figma API fixture; it does not certify the real editor, fonts or rendering.
