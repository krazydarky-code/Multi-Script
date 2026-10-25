# PlazCode source attribution

Adapted from the user-supplied **PlazCode-source-1.24.19.zip**, SHA-256 `eb8973151a0ac54a884d72d70d3669b9ede14db6000cf8d244742170e378042b`.
Upstream: PlazCode 1.24.19, distributed with GNU GPL version 3. See the preserved `LICENSE` in this folder and Multi-Script's GPL-3.0-or-later root license.

Modified 2026-10-17 for Multi-Script 6.39.0:
- `core/ultracode.js`: bounded/deduplicated task routing and efficient execution policy adapted into `extension/core/studio-workflows.js` as `ULTRA_METHODS` and `ultraMethodsPrompt`.
- `overlay.css`: selected-only violet/cyan Ultra text treatment adapted into `extension/overlay.css`, with Multi-Script selectors, native slider, independent light/dark colors, reduced-motion and forced-color support.

Product identifiers and command names are Multi-Script's. Attribution remains here and in the modified source. No upstream IDE, AgentScript runtime, DeepSeek-specific prompt, SyphoDev bundle, Check-UI modules, fonts, third-party art, executable, account configuration or credentials are included in this integration.

Modified 2026-10-17 for Multi-Script 6.40.0:
- `core/cowork.js`: bounded queue, ordered follow-ups, context ownership and accepted-send receipts adapted into `MSStudio.createCoworkQueue` with Multi-Script pacing, budget checks, Stop behavior, session persistence and no replay after uncertainty.
- `core/skills-ui.js`: reusable method adaptation policy rewritten into `runtime/skill_workflows.py`, the bundled skill execution contracts and Skills library.
Source licensing is GPL-3.0-or-later, also stated in the supplied release-tools/README.md. Product symbols are Multi-Script; attribution is retained here and in modified source.

Modified 2026-10-17 for Multi-Script 6.42.0, also inspected from the supplied `PlazCode-source-1.24.19/PlazCode/` directory:
- `core/skills-ui.js`: exact project scope, candidate/confirmed methods, text/Markdown import and adapting library methods were rewritten for Multi-Script's browser activation controls, existing workshop schemas and actual per-task prompt path. Export strips local scope. No automatic public sharing or account token workflow was imported.
- `core/cowork.js`: queue ownership and accepted-send receipts informed editable/reorderable typed follow-ups, context-checked edits and timestamped receipts. Multi-Script retains its own uncertain-send/no-replay pipeline.
- `core/task-center.js` and `core/ultracode.js`: requirement/evidence distinctions informed Multi-Script's SQLite acceptance checks, blockers and completion gate, plus its bounded Ultra delivery contract. No upstream backup/restore or merge functionality is claimed.

Code Flight's new renderer, physics, procedural backgrounds and studio themes were authored for Multi-Script, using its existing icon. The original supplied PlazCode license is preserved unmodified.


## UltraLab 1.24.20 reference adaptation (6.46.0)
The user supplied PlazCode-UltraLab-1.24.20. Its docs-lookup, studio-verify, API watchlist and build/check workflows informed Multi-Script's observed evidence gates, bounded inspection recovery and project-scoped skill resource delivery. Those mechanisms were rewritten for Multi-Script's live catalogs, session permissions and all six effort levels. No PlazCode binaries, cloud updater, mandatory GUI skin, hidden agents or publisher identity are imported. This derivative is not an official or endorsed PlazCode release. The upstream GPL and branding notice are retained beside this notice.
