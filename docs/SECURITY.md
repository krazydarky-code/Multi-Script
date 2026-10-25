# Security policy

## Supported version
Security fixes are provided for the latest published Multi-Script release.

## Reporting
Report security issues privately to the release maintainer. Do not open a public issue containing credentials, private workspace content, exploit details, or unredacted logs. Include the Multi-Script version, operating system, browser, affected provider/engine, reproduction steps, and sanitized diagnostics.

## Trust boundaries
- The engine/workspace bridge binds to loopback only. Do not expose port 17613 to a LAN or the public internet. The optional, separate phone listener is described below.
- Multi-Script can modify connected projects. Use source control and backups.
- Only install MCP servers from sources you trust. Review commands, environment variables, and licenses.
- Generated files and AI changes require normal code review and testing.
- Notion Auto routing requests cannot prove the hidden backend model identity.

## Optional LAN phone remote (6.43 Dev)

Phone control is disabled at startup and requires explicit desktop enablement. Only the pinned installed extension origin may administer it over the bridge; the provider/model tool catalog exposes no enable/pair operation. Desktop mutation buttons require trusted user interaction. The separate listener binds one selected private IPv4 interface (default port 17615); wildcard/public bindings are rejected. The engine/plugin ports remain unchanged.

Phone pairing uses a random eight-digit single-use code, two-minute expiry and per-IP attempt limits. Up to four devices receive a random 256-bit session token via HttpOnly/SameSite=Strict cookie, expire after one hour and can be revoked. Authentication and request state are in memory. Requests require the exact bound Host and same-origin POSTs, bounded JSON, allowlisted actions and a fresh, exact target context. CSP disallows framing and external scripts; responses are not cached. Handlers and request queues are bounded.

Follow-ups, queue pause/resume and Stop route through existing supported-provider tab validation, context checks and request receipts. Commands are claimed once and never automatically replayed after uncertain delivery; a missing acknowledgement is shown as unconfirmed. Revocation cancels unclaimed requests; an already-dispatched action/tool can still finish. No direct file, engine or arbitrary-code endpoint is exposed by the phone listener.

HTTP on the local network is **not encrypted**. Use only trusted Wi-Fi/LAN, allow only the needed private-network firewall access and never port-forward the listener. Remote control depends on an awake computer and connected desktop browser. [Setup and limitations](PHONE_CONTROL.md).

## Figma companion (6.44 Dev)

The optional Figma MCP process starts a separate loopback-only HTTP listener on port 17616. It accepts a one-use, five-minute pairing code with bounded attempts and an in-memory bearer session. Host and Figma/plugin Origin checks, bounded bodies/handlers, context checks and result receipts protect the local channel. Only stdio MCP can enqueue jobs; the HTTP surface only pairs, polls, disconnects and returns authenticated results. No arbitrary script evaluation, generic file access or network enqueue endpoint is exposed.

Both relay and plugin enforce Read/Edit and current-page context. The plugin rejects locked nodes/ancestors, off-page changes, unknown properties and script/external-resource SVG content; it rechecks access after asynchronous font loading. Disconnect/page/permission changes cancel pending work. Timed-out/claimed edits are never replayed automatically, and MCP `isError` is preserved through the bridge. Inspect actual results after uncertain or partial native failures.

Figma/Chrome may require explicit local-device/loopback permission; host network policy cannot be bypassed by the extension. Prefer Figma desktop and follow [setup](FIGMA.md). The plugin is a local development integration, not a published or Figma-certified marketplace plugin. Do not expose the listener or share its short-lived terminal code.

## Roblox companion execution
- Companion execution is Off by default and must be enabled inside Roblox Studio for each session.
- Read, Project, and Full tiers limit tool exposure; the bridge and plugin both enforce the required tier.
- The loopback plugin session uses an ephemeral in-memory bearer token. Jobs cannot be enqueued through HTTP.
- The companion exposes only curated handlers and never evaluates arbitrary Lua. Full access can edit source and delete instances, so use it only for trusted prompts and keep source control enabled.
- Disable elevated tools in the widget when finished. Tokens are invalidated on disable or plugin unload.
