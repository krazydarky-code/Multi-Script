# Multi-Script 6.47.0 verification

The release gate checks source syntax, matching versions, catalogs, manifest chains and packaging exclusions. CI runs 51 targeted suites and rejects environment skips. Its downloadable receipt identifies the exact tested main commit and workflow run; publishing requires that commit to pass.

New coverage executes the shipped Roblox plugin in a Lua VM with Roblox API fixtures. It checks all four tabs and 26 tool toggles, editor-buffer writes, concurrent update cancellation, Source redaction, UTF-8 paging/staging, incomplete/duplicate/conflicting transfers and Edit-mode/permission guards. Native scheduling and rendering are not emulated. Twelve browser design previews use labels constructed by the shipped Lua at 340/430/760px; they are not native Studio screenshots.

A real loopback HTTP server tests bridge-to-plugin job polling/results, automatic Unicode chunks, single commit, execution receipts, authenticated large result uploads, invalid registration isolation, per-tool selection and heartbeat retention. Studio operations at the far end are fixtures.

Notion and Vani load their shipped content-script chains for schema inspection, native/companion discovery, Chat studio isolation and desktop workspace execution without Studio. Their full round trips use actual Python skill retrieval and SVG generation, deterministic model replies and observed DOM shapes. Notion's unconfirmed send is attempted once. Existing coverage includes Venice Agentic/Classic, private ClickUp, all 16 provider browser/transport fixtures and Vani generation settling.

Other regressions cover all 904 skill contracts and 278 built-in schemas, six effort levels, bounded reads/failures, research/full-method requirements, progress/evidence, HTTP phone pairing/control, Figma contracts, provider errors, schema repair and updater signature/download/rollback. Local theme and settings sweeps check the revised workspace/media help.

After publication, verify the actual public HTTPS feed/signature, ZIP hashes and a checksum-pinned 6.46.0 installation upgrading to 6.47.0 in a temporary folder while retaining private configuration, custom skills and engine preferences. Preserve frozen Public 6.42.0 byte-for-byte.

Live native Studio/Blender/gameplay, every account/model, provider quota, asset upload permission, physical phone and firewall are outside these fixture checks. The console exposes real receipts, not model vision or hidden thinking. Provider/native compiler limits remain in force.

Implementation follows [Roblox's editor service contract](https://create.roblox.com/docs/reference/engine/classes/ScriptEditorService) and [source guidance](https://create.roblox.com/docs/reference/engine/classes/Script/Source). Notion preference messaging follows its [actual model controls](https://www.notion.com/en-gb/help/manage-ai-models-and-member-credit-spend).
