# Multi-Script 6.40.0 — workspace and failure-recovery verification

**48/48 scripts passed: 31 JavaScript/browser suites and 17 Python suites.** Both editions are built from this source after the regression run. Test filenames with earlier version numbers are maintained regression suites, executed against 6.40.0. Detailed operation and integration boundaries: [workspace guide](WORKSPACE_REVAMP_6.40.md).

## What changed and what was exercised

- All 904 skill entries have versioned project-aware execution/verification contracts. Actual skill retrieval retains these contracts, quality gates, related skills and native engine/output contracts instead of discarding them. The real catalogue supports offset pagination and favorite-ID filtering. The complete catalogue suite retrieves every built-in and exercises recommendation logic; the new suite checks every execution contract. Browser checks use the actual Python built-ins for browse, preview, favorites, custom installation/removal and a custom skill's adaptation contract.
- Co-work has an explicitly enabled, bounded follow-up queue adapted from upstream GPL source's source. Tests exercise ordered tool-result piggybacking, accepted-send receipts, idle sends, Stop/pause, context changes, message-budget deferral, interrupted-send restoration and no replay after uncertainty. The shipped Venice content chain sends a queued user request with one real tool result; a deliberately dropped second acknowledgement retains its follow-up as paused/unconfirmed. The local skill and SVG creation tools are real; the model/native editor side remains a fixture.
- Task-board tests cover legacy database migration without deleting old rows, dependency gating/cycles, parent/child resource conflicts, disjoint projects, concurrent claims, ownership, lease expiration, progress, history, completion and reopening. Browser checks create/filter/read history and edit owned scope through actual runtime calls. Claim checks coordinate tasks, not filesystem/editor writes.
- Settings browser checks cover grouped navigation, page headings, section jumps, keyboard arrows, global search exposing collapsed controls, preserved drafts, dark/light layouts and a 390 px viewport. Existing Ultra tests cover native slider selection/demotion, persistence/reset, theme/portal behavior, reduced motion and forced colors. Existing live-theme tests cover nine chatbar scenes.
- The user's Arena screenshot was reproduced as a browser fixture with partial prose followed by the observed native generation-error text and Retry/Clear controls outside markdown. The full Arena adapter and shared loop pause with task-unverified status, send no replacement prompt/tool, retain earlier individual call evidence and explicitly resume only after native Retry clears the error. Quoted error UI in model markdown does not trigger the probe. Structured JSON tool failures classify as errors while zero counts and arbitrary nested data do not. Startup discovery chips use the actual result. A provider startup error cannot become ready. A model's terminal text after failed calls prompts a review of results rather than asserting resolution.
- Existing 6.38/6.39 transport, settings acknowledgement, startup discovery, pacing/leases/cooldowns, tool schema, parser, local workspace, recording and edition regression coverage passed. All 16 provider content chains load, and the complete worker/imports pacing handler is evaluated. All 15 original adapter files preserve their implementation, normalizing only the Notion product version marker; the new error handling is shared.

## Evidence boundaries

Browser fixtures execute the actual extension code and local built-ins, but do not prove the selected model obeyed every skill or a native editor playtest occurred. The Arena error fixture is based on the supplied screenshot; this turn did not verify its live authenticated DOM or every provider error layout. Green chips mean individual call results, not full-task verification. Queue receipts mean accepted delivery, not completed goals. Resource claims are coordination, not source merge or file-lock enforcement.

The live Venice guest protocol/tool round trip was performed during 6.38.0; it is not relabeled as a fresh paid-model test. DeepSeek V4.1 Flash Uncensored selection, authenticated Vani/ClickUp behavior, live uploads and native Roblox/Unity/Godot/Blender execution remain unverified. See [provider verification](PROVIDER_QA_6.40.md). Skill improvements are in-context methods; they do not train model weights or grant absent tools/entitlements.

Test data uses isolated temporary Studio directories. Recording uses deterministic captured frames in its automated test. Native engine fixtures and explicitly reported environment skips do not establish actual OS capture permission or editor playtests. Both editions retain workspace/command permissions; Public retains its 256 KiB payload/60-second command/no-background caps, while Dev adds no product caps.

## Installation

Extract one complete edition into a permanent folder. Run Setup.bat (or the included platform setup), reload the extension and provider pages, then restart the bridge from that package. Keep your existing runtime/studio-data separately when replacing a release; its task database migrates in place. Distribution ZIPs exclude private Studio data, secrets, logs and generated artifacts and use example-only configuration.

## Executed scripts

| Script | Result | Seconds |
|---|---|---:|
| `test_agentic_runtime_roundtrip.js` | Pass | 30.58 |
| `test_all_skills_and_tools.py` | Pass | 20.67 |
| `test_bridge_builtins.py` | Pass | 0.5 |
| `test_bridge_wire_638.py` | Pass | 1.06 |
| `test_chatbar_studio.js` | Pass | 19.55 |
| `test_code_mode_636.js` | Pass | 0.22 |
| `test_content_script_load_contract.js` | Pass | 1.03 |
| `test_cowork_queue_640.js` | Pass | 0.22 |
| `test_creative_asset_pack_6361.py` | Pass | 0.59 |
| `test_creative_production_6361.js` | Pass | 0.28 |
| `test_critic_loop_613.py` | Pass | 0.59 |
| `test_cross_provider_tool_matrix.js` | Pass | 0.27 |
| `test_engine_schema_assurance_69.py` | Pass | 0.72 |
| `test_engine_tool_routing.js` | Pass | 0.2 |
| `test_enhancer_browser_send.js` | Pass | 15.41 |
| `test_enhancer_send_gate.js` | Pass | 0.59 |
| `test_error_recovery.js` | Pass | 0.2 |
| `test_full_spectrum_skill_mesh.py` | Pass | 0.56 |
| `test_local_memory.js` | Pass | 0.22 |
| `test_menu_settings_scope.js` | Pass | 0.22 |
| `test_model_improvement_layer.py` | Pass | 0.67 |
| `test_new_provider_transport_637.js` | Pass | 3.27 |
| `test_notion_bootstrap_once.js` | Pass | 0.2 |
| `test_notion_prompt_only_routing.js` | Pass | 1.56 |
| `test_notion_send_failfast.js` | Pass | 53.12 |
| `test_pacing_engine.js` | Pass | 0.34 |
| `test_parser_repair.js` | Pass | 0.34 |
| `test_product_manifest_plugin_613.py` | Pass | 0.19 |
| `test_prompt_enhancer.js` | Pass | 0.2 |
| `test_provider_failure_640.js` | Pass | 7.8 |
| `test_provider_send_budget.js` | Pass | 0.2 |
| `test_required_param_contract.js` | Pass | 0.22 |
| `test_roblox_companion.py` | Pass | 0.56 |
| `test_schema_repair_and_native_host.py` | Pass | 17.88 |
| `test_settings_customization.js` | Pass | 0.22 |
| `test_skill_tool_mesh_prompt.js` | Pass | 0.34 |
| `test_studio_craft_skills.py` | Pass | 0.16 |
| `test_studio_hub_637.py` | Pass | 1.56 |
| `test_studio_revamp_637.js` | Pass | 12.81 |
| `test_superapp_provider.js` | Pass | 9.0 |
| `test_tool_parameter_contracts.py` | Pass | 0.34 |
| `test_ultra_integration_639.js` | Pass | 11.03 |
| `test_universal_capability_foundation.py` | Pass | 0.77 |
| `test_venice_agentic_transport.js` | Pass | 7.41 |
| `test_worker_pacing_contract.js` | Pass | 0.24 |
| `test_workflows_cowork_640.py` | Pass | 0.59 |
| `test_workspace_636.py` | Pass | 7.41 |
| `test_workspace_ui_640.js` | Pass | 28.89 |
