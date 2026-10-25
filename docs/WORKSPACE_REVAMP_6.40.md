# Multi-Script 6.40 — skills, co-work and settings

## Skills that adapt to the project

All 904 bundled skills now contain a versioned execution workflow: what to inspect, how to apply the method, a domain-specific verification path, role-specific delivery expectations, ownership/handoff, evidence categories and bounded recovery. Discovery remains read-only. Fallback specialist domains select applicable craft rules from their actual name/tags. These workflows guide the active model; they do not train weights or implement tools.

`ms_get_skill` previously discarded important metadata. It now returns the execution workflow, quality gates, related skills, domain/role and engine/output contracts with an optional project goal. Custom installed workflows receive the same adaptation wrapper. `ms_list_skills` supports offset pagination and optional favorite-ID filtering without dumping the entire catalogue.

Settings → Skills exposes the real catalogue: search, engine filter, pagination, favorites, full preview and Apply to project. Applying a workflow loads its actual content, includes its project-aware contract, and uses the existing Agent prompt/send path. While the agent is busy, an enabled follow-up queue can accept it. Custom workflow authoring uses a name, engine and instructions; advanced JSON import/publishing remains available. Install/remove updates the browser selection and the next acknowledged settings refresh. Favorites remain browser-local; runtime skills remain in the bridge's data directory.

## Co-work

The Live session section has an explicit opt-in queue for additional user requests. It preserves order and unfinished goals, appending requests at a tool-result boundary when the full message fits. Otherwise requests wait for an idle visible task send. Existing shared pacing, drafts, Stop, provider quotas and delivery acknowledgements remain authoritative. Queue state is stored in this tab's session storage. It is locked to the originating provider/chat/engine/workspace context. Stop pauses it. Unconfirmed sends stay paused for inspection/removal and are never automatically replayed; reloads convert interrupted sends to unconfirmed. Recent receipts indicate accepted sends, not completed goals.

The Shared tasks section is a persistent local board with Ready & waiting, In progress and Completed columns. Tasks include project, priority, acceptance criteria, resource paths and dependency IDs. Scope can be edited before claiming. Dependencies must complete before a claim. Claim transactions reject overlapping resource paths within a project, including parent/child paths and wildcard scope. Windows separators and case are normalized. Claims expire after 30 minutes; progress updates renew them. Completion/release ends the lease. Completed tasks can be reopened; history records the last 50 changes per task. Completion in the UI requires a progress/evidence note, while existing tool clients remain compatible.

These are coordination checks, not filesystem/editor locks or an automatic source merge service. Each actual provider tab works through its own connected tools. No other account is silently controlled. Existing database task rows migrate in place with empty resource/dependency defaults; no task data is deleted. Empty resource scope remains compatible but is explicitly shown as unscoped.

## Settings organization

The existing setting keys and category IDs remain valid. Navigation is grouped under Workspace, Agent, Connections, Appearance and Support. Each page has a title, description and section jumps. Keyboard arrows/Home/End navigate categories. Search spans all categories, reveals matching collapsed controls and provides Clear search. Shared theme tokens, SVG navigation, cards and field controls apply in dark/light and narrow layouts. Ultra remains the final native slider position and Critic remains an Agent setting. Existing live scenes and chatbar preferences continue to apply.

## Provider failure and truthful status

The supplied Arena screenshot shows partial assistant text followed by an actionable native Retry/Clear generation-error panel. A screenshot-shaped browser fixture reproduces this distinction. Such a panel outside model markdown takes precedence over partial prose or tool JSON: Multi-Script pauses, labels the task unverified, pauses queued follow-ups and does not replay the last prompt or tool. After using the site's Retry and clearing its error, Resume response reads the recovered response without another send. Quoted error examples in model markdown do not trigger this path. The probe covers the observed Retry/Clear pattern; it is not a claim that every provider error layout has been verified live.

Structured tool failures (`ok:false`, `success:false`, `isError:true`, failed status, explicit error/errorCount) are classified as failed chips instead of successful JSON results. Arbitrary nested project/source data and zero error counts are not recursively misclassified. Startup discovery chips use their actual result. Green checks mean an individual call returned, not that the entire task is finished. If a model ends its response after failed calls, the bar asks to review results rather than confirming resolution. Native provider failure during startup cannot mark the session ready.

## Source integration

upstream GPL source 1.24.19 `core/cowork.js` informed the bounded queue, receipts and context-aware delivery implementation; `core/skills-ui.js` informed project adaptation of reference skills. Both were rewritten into Multi-Script's existing runtime/transport and visual system, using Multi-Script symbols. The GPL license/provenance remain in `legal/upstream-gpl`; no separately licensed art, SyphoDev pack, alternate tool server, IDE binary or provider-specific approval policy was imported. See `THIRD_PARTY_NOTICES.md`.
