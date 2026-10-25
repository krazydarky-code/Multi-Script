# Multi-Script 6.43.0 Dev verification

All **34 targeted suites passed**, with **no environment skips** in the final results. [Machine-readable results and earlier attempts](verification-results-6.43.0.json). This is a targeted run; the historical full 6.42 baseline is not relabelled as a new full test run.

## Task progress

The real parser/agent-loop browser test consumes model JSON, executes local progress calls, sends feedback and retains a blocked step after a final “All done” model claim. Only the separate project-tool call increments execution/error counters; checklist reporting does not. Evidence is required before reported completion; stale run IDs, duplicate step IDs, dropped scope and invalid restoration are rejected. Reopening clears old evidence.

The full paired-browser flow also checks the current run ID in the actual task addon, a prefixed local command in Code/Software mode, schema visibility in the Multi-Script catalog and rejection of a previous workspace run. The progress tool stays local to the content script rather than introducing a bridge engine/file endpoint.

## Phone control

The shipped HTTP frontend runs in a separate ordinary Chromium phone page at 390px against a real Python HTTP listener. A trusted desktop click enables the listener, the phone uses the one-time code, authenticates with its HttpOnly cookie, reads progress and queues a follow-up through the real coordinator and content-script queue handlers. Pause/resume, Stop, the stopped status, device revocation and listener shutdown are exercised. The desktop provider session itself is a deterministic browser fixture; no real provider account is driven by this test.

Service tests cover disabled defaults, rejected public/wildcard addresses, owning-profile checks, Host/Origin/CSP boundaries, authentication, pairing replay/expiry/attempt limits, device expiry/revocation, opaque context identifiers, stale snapshots, allowlisted actions and at-most-once command claim. The worker test covers serialized polls, exact target context, rejected dispatch and receipt-only retry after a connection failure. A separate real WebSocket test runs the shipped bridge handler and rejects missing/provider/web origins and invalid identities; only the pinned extension origin can administer the remote.

The phone listener uses unencrypted HTTP on an explicitly selected trusted LAN interface and starts disabled. It exposes bounded status and guarded browser actions, not direct engine/workspace RPC. Hardware pairing across a physical phone, router/client isolation and Windows firewall configuration remain user-network checks; they are not certified by a loopback browser test. [Setup and limits](PHONE_CONTROL.md).

## UI, themes and regressions

- The run monitor passes **12 desktop/mobile cases** across Cobalt, Porcelain, Ember, Tidal, Starlight and Daybreak, including 4.5:1 checked text contrast, bounded geometry, theme-colored progress, Escape/focus return, hidden-provider-bar behavior and separation from settings.
- The broader theme matrix passes **324 combinations**, **18,762** computed contrast checks, **228** compositor-pixel contrast samples and **42** live-scene/motion checks across independent menus/bars, both docks, composer portals and narrow views in Notion/Claude fixtures.
- The settings sweep operates controls, every theme/size/scale across settings pages, bar options, stored-value sanitation and narrow layouts. Run-monitor navigation is covered by the dedicated panel tests because it intentionally closes settings.
- The provider-browser matrix passes all **16 provider fixtures / 513 assertions**. Vani generation lifecycle, provider pacing, content-chain load order, Ultra, co-work dispatch/queue/evidence, workspace workflows and Code/Software isolation have targeted regression coverage.
- Vani and Venice Agentic round trips run the current manifest's content chain with the real Python catalog, skill retrieval and SVG creation, preserving native-step isolation and avoiding replay after uncertain acknowledgement. Provider model/native-editor behavior in those tests remains simulated.

Checks caught and corrected the progress tool's catalog/server and Code-mode allowlists before release. The minimal DOM load shim now supports the standard append API. The general sweep distinguishes intentional panel navigation, and the older skill-import test waits for asynchronous file parsing before inspecting its preview.

## Evidence and release

[Desktop checklist](verification-6.43.0/Task-monitor-desktop.png) · [Narrow checklist](verification-6.43.0/Task-monitor-mobile.png) · [Desktop pairing panel](verification-6.43.0/Phone-pairing-desktop.png) · [Phone dashboard](verification-6.43.0/Phone-remote-paired.png). All screenshots show local test fixtures, not private provider conversations. Individual suite logs are in `docs/verification-6.43.0/`.

Dev **6.43.0** is the rolling build; Public **6.42.0** remains the exact checksum-pinned older companion. Temporary archive tests cover deterministic Dev/bundle generation, sanitized configuration, private-data exclusions and rejection of altered/missing/wrong-identity or non-older Public archives. Final archive CRC/SHA/source/edition/bundle checks are recorded separately after packaging. This release does not claim zero bugs, live coverage of every account/model or new native editor playtests.
