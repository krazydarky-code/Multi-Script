# Multi-Script 6.42 verification

**160 / 160 unique regression suites returned success** (100 JavaScript, 60 Python). All registered tests were executed. Earlier failures exposed stale version/theme assertions, an unwanted empty skill add-on on Original Prompt, and cross-theme chatbar text contrast; those were corrected and rerun. The latest result per test is retained in [the machine-readable report](verification-results-6.42.json). This is bounded verification, not a claim of zero bugs across all account states.

## Exercised behavior

- All 16 shipped provider chains: real parser/role/chip handling, all six effort settings, Critic and skill UI; 64 exact provider-send assertions. No paid model is impersonated or unlocked.
- Vani guest-style and authenticated-style DOM fixtures: visible “Stop it”, 8-second frozen readiness/command replies, native-finish gating, a 2.5-second quiet interval, reused-node readiness and a generation race during composer fill. The actual dispatcher is observed; no tool executes or feedback is sent while native generation remains active. One readiness reply starts the chat without an unsolicited correction.
- Real full startup/skill retrieval/SVG generation through the Python runtime for Vani and Venice Classic/Agentic; uncertain acknowledgements pause without replay.
- Two distinct provider content chains: tab discovery through the new worker module, remote startup/cancel, shared SQLite claims, acknowledged task delivery, explicit background opt-in, bounded local brief reads, duplicate receipt suppression, stale-context rejection and mobile layout. The actual service worker additionally tests discovery routing and invalid-target response.
- Shared-board migration, dependency/resource concurrency, ownership leases, acceptance check validation, evidence/blocker completion gates and reopened dependencies. Queue edit/reorder/correction/goal semantics, pause-on-edit, context binding and timestamps.
- All 904 built-in workflow contracts/tool references plus project-derived methods, engine/scope activation, disabled skill suppression, Markdown/text/JSON import and an actual user send with the enhancer and Critic off.
- Ultra remains the final slider stop. Task-specific delivery contracts, bounded methods, demotion, Critic independence, live scenes, forced colors, reduced motion and persistence are covered.
- Code Flight: actual icon pixels, declared resource access for every provider origin, collision/scoring and a real animation-loop gate pass, separate best scores, malformed saved state, touch/keyboard controls, hidden-canvas render shutdown, document visibility pause/resume and teardown.
- The complete settings sweep operated **496 controls** on Notion/Claude, all **31 themes** across sizes/tabs, independent bar options, resets, hostile storage and small viewports. New theme brand/idea/Ultra text meets 4.5:1 contrast against opposite light/dark menu configurations after transition settlement.
- Existing workspace/native transport, registry/schema/parameter checks, Lua/Luau execution/compilation where available, engine facade tests and package release gates remain passing.

## Limits

The provider response model is deterministic in browser fixtures. These tests cannot certify every authenticated Vani layout, paid DeepSeek model, rate limit, account entitlement or future provider DOM update. Previous live observations and the Crax DNS failure remain documented in [provider QA](PROVIDER_QA_6.41.md); this release does not claim a new all-provider live-account run.

Native Blender `bpy` and Unity compilation require the actual editors and are explicitly skipped here. Godot binary availability and POSIX-only integration have explicit environment boundaries. Mock engine tests do not count as native playtests. Skill/Ultra instructions improve in-context behavior and cannot guarantee model compliance. Checklists record reported verification. Remote phone pairing is not implemented; no LAN control listener is enabled.

## Visual evidence

[Terminal flight](verification-6.42/Code-Flight-terminal-6.42.0.png), [running flight](verification-6.42/Code-Flight-running-6.42.0.png), [Orbit](verification-6.42/Code-Flight-orbit-6.42.0.png), [Daybreak](verification-6.42/Code-Flight-dawn-6.42.0.png), [phone layout](verification-6.42/Code-Flight-mobile-6.42.0.png), [co-work](verification-6.42/Co-work-6.42.0.png), [provider sessions](verification-6.42/Provider-sessions-mobile-6.42.0.png), [skills](verification-6.42/Skills-6.42.0.png), [Ultra](verification-6.42/Ultra-6.42.0.png).

Run `python tools/verify.py all --output test-results` to reproduce. Optional dependencies/toolchains and native-editor availability affect skips. Use `tools/build_release.py` for both source editions; its release gate validates manifest references, syntax, provenance and catalogue contracts. Final ZIPs are independently checked for SHA/CRC, source-byte equality, stable extension identity, clean configuration, private-data exclusions and actual packaged edition policies.
