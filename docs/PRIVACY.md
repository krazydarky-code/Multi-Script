# Privacy

Multi-Script is a local bridge and browser extension.

## Data it handles
- Text sent to and received from supported AI chat pages
- MCP commands and results needed to operate connected local editors
- Local preferences such as menu appearance, provider modes, and Notion Auto routing choice
- Local diagnostic status such as server health and advertised tool counts

## Storage and transport
- Preferences use browser extension local storage.
- The bridge listens on loopback only (`127.0.0.1`) and writes local diagnostic logs.
- Multi-Script does not include its own analytics or telemetry service.
- Content sent to an AI provider remains subject to that provider's privacy policy.
- Third-party MCP servers may have their own network and telemetry behavior. Review them before enabling them.

## Permissions
Host permissions are limited to the supported AI sites plus localhost for the bridge. The extension uses `storage` to retain settings.

## Sensitive information
Do not place passwords, API keys, tokens, or private keys in prompts, screenshots, bug reports, or `runtime/config.json`. Use environment variables supported by the relevant MCP server.


## Workshop, co-work and recording

Custom instructions, workshop entries/ratings/feedback and co-work task notes are stored in the bridge's local `runtime/studio-data/` database. Installed custom instructions are sent to the active AI provider as part of the operating instructions. They are not model-weight training.

When you explicitly connect and publish/review through a community workshop, the skill text or feedback is sent to that configured service under your authenticated workshop identity. The included community server has no analytics, and is separate from your game-engine/workspace bridge. Its operator controls retention. The connection token stays in the local runtime connection file and is excluded from release packages and settings backups.

The screen-record tool captures the requested desktop region (or the full desktop when no region is supplied), saves a local video of at most five seconds, and returns sampled image frames to vision-capable providers. Code Flight stores only its local best score and makes no network requests.
# 6.42 local workflow state

Provider-session discovery inspects only supported provider tabs in this browser. It reads status and tab titles; Read brief explicitly retrieves bounded current-request/latest-response excerpts for local display. Assign explicitly sends the selected board task to the target model. Full conversations are not automatically broadcast. Dispatch receipts remain in tab session storage. Phone control is disabled by default; its optional 6.43 behavior is described below.

Installed-skill activation and optional chat/workspace scope are stored in browser local storage. Task prompts include only enabled engine/scope matches. Skill JSON exported through Read / export clears the local scope identity; bridge workshop publication strips browser-local activation/scope metadata. User-written skill instructions can themselves contain project information, so review the explicit export/publication content.

Co-work acceptance checks, owner-reported verification indices, blockers and evidence notes remain in the local SQLite task board. Follow-up drafts/receipts remain in this tab's session storage. Code Flight world/mode/best scores use provider-origin local storage and do not contact AI or the bridge. The bundled static icon is accessible to declared provider origins so it can render in the extension UI.

## 6.43 optional phone control and run monitor

The run monitor stores its current title, checklist, verification notes and counters in that provider tab's session storage. Its local tool reports are sent back to the active provider as tool feedback. These reports describe model-reported verification, not independently certified completion.

Explicitly enabling Phone control opens a separate HTTP listener on one selected private IPv4 address. Paired phones receive bounded provider/tab titles, task titles, steps, evidence/blockers, status and receipts. Full conversation text, the workspace path and the internal chat-context identifier are not included in the phone status snapshot; an opaque hash identifies the target context. User-written titles/evidence can still contain sensitive project information.

The phone's queued instructions travel to the desktop and then to the selected provider through the existing send queue. Pairing codes, hashed session credentials, snapshots, pending commands and receipts stay in bridge memory, are never written to logs or a database, and are cleared on disable/restart. Device authentication uses an HttpOnly, SameSite=Strict cookie that expires after one hour. The browser profile stores only a stable random owner ID locally. No cloud relay, analytics or external phone service is used.

The LAN connection uses unencrypted HTTP. Pair only on a network you trust and never port-forward it. Revoke devices or turn it off in the desktop Phone control panel. [Setup and limits](PHONE_CONTROL.md).

## 6.44 Figma, ClickUp and Ultra

The optional Figma server binds only `127.0.0.1:17616` and communicates with the explicitly paired companion plugin. The plugin exposes bounded current-page hierarchy/properties, text, selection and requested native PNG/SVG exports; those tool results can be sent to the selected AI provider. File/page names and the current context stay in the local relay. Pairing tokens and jobs are in memory; the five-minute single-use code is shown in the local bridge terminal for setup. Do not share it in logs/screenshots. Read/Edit can be changed or revoked inside the plugin. No Figma cloud token, analytics or cloud relay is introduced by the bundled companion.

ClickUp support operates only within a recognized visible private Brain scope. It excludes team/human/comment composers and does not send local commands into them. ClickUp still processes prompts/results sent to its private AI under its own account policies.

Provider benchmarks/local readiness checks read local adapter/composer/bridge status and do not send a benchmark prompt. Compatibility rows describe shipped fixture coverage and explicit live boundaries, not measured intelligence or speed. Ultra manuals are bundled instruction text selectively sent to the active provider; reading them does not change model weights or grant permissions.

