# Multi-Script 6.38.0 — verification and compatibility repair

**43/43 test scripts passed:** 27 JavaScript/browser suites and 16 Python suites. Additional visual checks passed for the actual Agent Critic/Ultra controls and the direct New idea bar in dark and light themes. Test filenames containing earlier version numbers are maintained regression suites rerun against 6.38.0. The complete background worker and its imports were evaluated; its actual pacing-message handler persisted leases and returned an explicit error on simulated storage failure. Legacy Studio visibility settings migrate to New idea and remain editable.

## What was repaired

- Critic is a persistent Agent prompt add-on with one to three review passes. It reaches every user task prompt with the enhancer off, on already-detailed prompts, and after choosing original wording. It preserves the request and does not send separate Critic messages after completion. Disabled means no Critic add-on. The obsolete Critic loop and Studio popover were removed.
- Ultra derives maximum relevant skill coverage and rigorous verification even from a saved focused profile. Its task prompt requests research of relevant games and art/UI references, source URLs, a consistent style bible, reference captures when possible, actual project screenshots, asset integration, real builds/playtests and visual comparisons. These are instructions to the active model; they cannot unlock absent tools or prove a model followed them without execution evidence.
- Startup retains the original ordinary-JSON local-tool protocol, includes a final startup-only instruction, and handles up to six safe catalog/skill discovery rounds. A valid first skill command is executed and its real result returned, rather than silently discarded. Startup cannot execute an unsolicited file edit or project action.
- Loading saved autonomy settings no longer marks them dirty. Settings changes use a compact update instead of reinjecting all craft packs; live installed-skill updates are retained. A settings payload is acknowledged only after an accepted send and only if its snapshot still matches, so edits made while a send is pending are not lost. Optional prompt rewriting and Agent add-ons share one held send, including Stop/navigation cancellation during the asynchronous pacing handshake. Bootstrap-only instructions are excluded from periodic task reminders.
- Venice Agentic selectors were inspected live. Its user content also contains an assistant-content class, so explicit outer role boundaries are used. Only the final answer is parsed; native reasoning and tool-step panels cannot become local commands. Classic Chat is retained.
- Error cooldowns are measured from the error and no longer subtracted against a much earlier send. The worker shares leases, minimum post-send gaps and cooldowns across provider tabs, persists state across worker wakes and expires abandoned leases. Visible retry-after hints extend backoff. Quota/access notices stop automated sends; a deliberate new user submission, Start or New idea action can resume. Rate/outage retries are bounded, zero budgets stay zero, and an uncertain attempted send is not replayed automatically. A failed tool-result send pauses the loop and automatic reminders rather than waiting for an impossible reply. Ordinary motion advice and informational reset/usage labels are not treated as provider refusals.
- A real WebSocket test exposed a blocked log-reader executor thread on disconnect. Log queue reads now have a bounded timeout and the handler awaits cancellation, allowing a clean disconnect/shutdown without leaking a permanently blocked worker.

## Evidence and its limits

The supplied 6.36.1 ZIP was extracted separately for comparison. All 15 original native provider adapter files retain the same logic; Notion's product-version marker is updated. Changes to startup, prompt add-ons, pacing and the agent loop are shared. Every one of the 16 content-script provider chains loads without a temporal-dead-zone error or missing binding. Original adapter comparison does not prove that a third party has not changed its live authenticated DOM.

Live Venice guest Agentic Chat returned MULTISCRIPT_AGENTIC_READY, emitted ordinary JSON for ms_list_skills, and consumed the result executed by the actual Python runtime, returning MULTISCRIPT_AGENTIC_TOOL_RESULT_OK_3. This was a browser-driven protocol check. The fully automatic shipped content-script chain was then tested separately against the observed Agentic DOM with deterministic provider responses: startup → real skill query → real catalog result → task with Critic/Ultra → actual skill retrieval → actual SVG creation → final response. The generated SVG files were opened and checked. Native tool-panel JSON was excluded. A deliberately unacknowledged send was clicked only once. A separate loopback WebSocket test used the real runtime handler for catalog, skill query/retrieval and SVG generation, and exited cleanly after disconnecting.

The guest account exposed no paid model picker. **The exact DeepSeek V4.1 Flash Uncensored model, paid-model behavior, live image uploads and real Roblox/Unity/Godot/Blender editing were not verified.** The adapter preserves the model selected in Venice. The automated provider model and native-editor connection in the end-to-end test are fixtures; the local skill and artifact tools are real. Vani/ClickUp authenticated support and Crax reachability retain the boundaries in the provider report. No claim is made that every provider/account or every native tool was tested live.

Other runtime suites exercise all 904 skill entries, schema/parameter contracts, workspace file/edit/build/test operations, icon/UI generation, workshop HTTP authentication, co-work claims, recording with deterministic captured frames, and edition policies. Native-engine fixtures, environment skips and deterministic frame capture do not establish live editor playtests or actual OS screen-capture permission. Dark/light screenshots and all nine live chatbar scenes were checked for correct positioning and non-blank painting.

## Installation and environment

Extract one edition to a permanent folder, run Setup.bat (or the included platform setup), reload the extension and provider pages, and restart the bridge from that same package. Setup installs websockets and Pillow using its selected Python and registers that interpreter's full launcher path. The local default Python 3.15 had neither dependency when inspected; Python 3.11 had both and was used for verification. The local status port was not reachable during the read-only probe. This does not establish which interpreter an existing browser launcher uses; the new package's Setup is the concrete way to register and start its own runtime.

Dev adds no product caps. Public retains the 256 KiB workspace edit/write cap, 60-second command cap and disabled background-command option. Both preserve existing workspace, command and engine permissions. Provider quotas and account restrictions remain provider-controlled.

## Executed scripts

| Script | Result | Seconds |
|---|---|---:|
| `test_agentic_runtime_roundtrip.js` | Pass | 31.7 |
| `test_all_skills_and_tools.py` | Pass | 20.52 |
| `test_bridge_builtins.py` | Pass | 0.52 |
| `test_bridge_wire_638.py` | Pass | 1.28 |
| `test_chatbar_studio.js` | Pass | 18.62 |
| `test_code_mode_636.js` | Pass | 0.19 |
| `test_content_script_load_contract.js` | Pass | 1.11 |
| `test_creative_asset_pack_6361.py` | Pass | 0.53 |
| `test_creative_production_6361.js` | Pass | 0.25 |
| `test_critic_loop_613.py` | Pass | 0.61 |
| `test_cross_provider_tool_matrix.js` | Pass | 0.27 |
| `test_engine_schema_assurance_69.py` | Pass | 0.83 |
| `test_engine_tool_routing.js` | Pass | 0.2 |
| `test_enhancer_browser_send.js` | Pass | 16.2 |
| `test_enhancer_send_gate.js` | Pass | 0.73 |
| `test_error_recovery.js` | Pass | 0.31 |
| `test_full_spectrum_skill_mesh.py` | Pass | 0.47 |
| `test_local_memory.js` | Pass | 0.3 |
| `test_menu_settings_scope.js` | Pass | 0.19 |
| `test_model_improvement_layer.py` | Pass | 0.75 |
| `test_new_provider_transport_637.js` | Pass | 3.55 |
| `test_notion_bootstrap_once.js` | Pass | 0.25 |
| `test_notion_prompt_only_routing.js` | Pass | 1.12 |
| `test_notion_send_failfast.js` | Pass | 52.03 |
| `test_pacing_engine.js` | Pass | 0.2 |
| `test_parser_repair.js` | Pass | 0.28 |
| `test_product_manifest_plugin_613.py` | Pass | 0.19 |
| `test_prompt_enhancer.js` | Pass | 0.2 |
| `test_provider_send_budget.js` | Pass | 0.2 |
| `test_required_param_contract.js` | Pass | 0.22 |
| `test_roblox_companion.py` | Pass | 0.53 |
| `test_schema_repair_and_native_host.py` | Pass | 18.75 |
| `test_settings_customization.js` | Pass | 0.2 |
| `test_skill_tool_mesh_prompt.js` | Pass | 0.19 |
| `test_studio_craft_skills.py` | Pass | 0.16 |
| `test_studio_hub_637.py` | Pass | 1.62 |
| `test_studio_revamp_637.js` | Pass | 10.19 |
| `test_superapp_provider.js` | Pass | 9.45 |
| `test_tool_parameter_contracts.py` | Pass | 0.34 |
| `test_universal_capability_foundation.py` | Pass | 0.75 |
| `test_venice_agentic_transport.js` | Pass | 7.59 |
| `test_worker_pacing_contract.js` | Pass | 0.22 |
| `test_workspace_636.py` | Pass | 7.45 |

## Research

The original code ZIP was the primary source for startup/tool-loop behavior. [Venice Agentic Chat](https://venice.ai/chat/agent) was inspected directly. [Venice rate-limit documentation](https://docs.venice.ai/api-reference/rate-limiting) informed backoff/reset handling; its API limits are distinct from web-chat entitlements. [Venice's public DeepSeek V4.1 Flash page](https://venice.ai/models/deepseek-v4-1-flash) is not proof of availability of the separate Uncensored Agentic selection. More provider-specific evidence and limits: [provider verification](PROVIDER_QA_6.38.md).
