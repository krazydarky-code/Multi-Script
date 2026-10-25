# Multi-Script 6.44.0 Dev verification

All **35 targeted suites pass**, with **no environment skips** in the final results. [Machine-readable results and earlier attempts](verification-results-6.44.0.json). This is targeted coverage for this release; historical full-suite baselines are not counted as a new full run.

## Figma: executable path and boundary

The release contains a native companion plugin, loopback relay and nine-command stdio MCP launcher. Tests call the shipped native-operation handlers against a Figma API fixture: native frame/text/component-like operations, geometry and Auto Layout, font loading before text updates, read-back, SVG import, PNG export, selection and confirmed deletion. They reject Read-only writes, locked ancestors, unknown/invalid properties, external/script SVGs, stale/off-page context and permission revocation during font loading. Quoted internal SVG gradient links remain valid.

The shipped plugin iframe UI connects to the **real Python HTTP listener and actual stdio MCP launcher**, pairs with its real one-use code, creates native frame/text nodes through the API fixture, reads them back and tests permission revocation/disconnect. The test grants Chrome's local-network-access permission for the fixture's Figma origin, simulating an explicit user grant. An initial denied-loopback request exposed this requirement; the product now shows actionable guidance instead of only “Failed to fetch.” Browser security is not disabled. [Plugin UI screenshot](verification-6.44.0/Figma-companion-6.44.png).

Real bridge-manager tests launch the actual Figma MCP child, discover all nine schemas on server `figma`, route calls and preserve its disconnected-file state. HTTP/service tests cover Origin/Host/token checks, code replay, Read/Edit, single claims, result receipts, timeouts and no replay. Figma writes, including official write names, are classified as non-idempotent after a server crash.

**Live boundary:** navigation reached Figma login. Authenticated testing was declined, so actual Figma import/manifest acceptance, native fonts/rendering, account edit rights and host network policy remain scratch-file checks for the user. No signed-in Figma edit is claimed. Use [Figma setup](FIGMA.md); a running MCP process is not sufficient evidence of a paired editable file.

## ClickUp and provider error recovery

The full current manifest chain passes a private Brain fixture round trip with the **real Python catalog, skill retrieval and SVG generation**, startup, chips, Ultra/Critic instructions, a queued follow-up, native-step isolation and uncertain-result acknowledgement protection. Separate tests exercise visible versus hidden AI scopes, nested team/human composer exclusion, native-tool/citation exclusion, a 2.5-second quiet period, exact text send, last-moment generation checks and changed-editor/chat rejection.

An actionable native error panel no longer terminates the local wait while the provider is still generating. Once generation ends and the error remains, the task is paused/unverified, Stop is removed and Resume is restored. The existing failed-response/retry tests continue to pass. The bridge also now **preserves MCP isError**, fixing a path that could turn native tool failures into successful receipts; the actual manager test checks it with an unpaired Figma write.

**Live boundary:** ClickUp navigation reached login. Its authenticated private Brain DOM, current account/model behavior and real task execution are not live certified. Team-channel/comment fallbacks remain closed. [Setup and limits](CLICKUP.md).

## Provider benchmarks and Ultra

The redesigned evidence view covers **16 providers** with consistent rows, search and current-provider filters, expandable limits and a read-only local readiness check. It removes hard-coded “Smart/Speed/Stability” scores and averages. Browser tests cover filters, diagnostics without sending a prompt and geometry at 1100/500/390px. [Evidence view](verification-6.44.0/Provider-evidence-6.44.png).

All **12 Ultra manuals** have six detailed phases: inspect/design/build/integrate/verify/failures. Tests cover every manual/phase, aliases, bounded relevant excerpts, full and individual-section retrieval, unknown IDs/sections, Code-compatible local routing and immediate disabling on effort demotion. Existing Ultra integration tests retain the final slider stop, selected styling, task scope, research and prompt-budget boundaries. The instruction text is in-context guidance, not model-weight training or extra execution permission. [Manual system](ULTRA_MANUALS.md).

## Broader checks

- **504 controls** operated across Notion/Claude settings, all themes × sizes/scales × tabs, bar options, resets, narrow viewports and hostile stored preferences.
- The theme matrix passes **324 combinations**, **18,762** computed contrast checks, **228** compositor-pixel samples and **42** live-scene/motion cases.
- All **16 provider-browser fixtures / 513 assertions** pass; the transport matrix additionally sends exact multiline Unicode through all 16 real adapters.
- Vani generation lifecycle and real-runtime round trips, Venice Classic round trips, workspace/co-work/skills flows, current phone remote, content-chain load order, engine setup/prefs, native-host/schema repair and bridge built-ins/wire checks pass.
- Current bridge/product/adapter/plugin/asset versions, deterministic Dev/bundle generation, unchanged Public bytes and private-data exclusions pass. Local engine preferences are now excluded explicitly.

Individual suite logs are in `docs/verification-6.44.0/`. These use deterministic provider/model/editor fixtures where stated; they do not prove every live provider/account/paid model, OS, physical device or native editor playtest. No zero-bug/perfect-compatibility claim is made.

## Release artifacts

Dev **6.44.0** is the rolling/current build. Public **6.42.0** is the unchanged checksum-pinned older companion, bundled alongside it. Final archive checks run after packaging and record CRC/SHA/size, current source bytes, actual Dev policy execution, sanitized config and exact nested bundle contents separately from this source QA report.
