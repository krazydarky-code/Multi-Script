# Authority, transactions, persistence and distributed state

Detailed project-aware guidance, not weight training or permissions. Apply only relevant parts; preserve user scope, existing style and architecture. Inspect/review-only tasks remain read-only. Retrieve once, execute the authorized slice, reuse unchanged evidence and avoid guidance/discovery loops.

## Inspect

1. Map each sender, validator, state owner, commit point and receiver. Distinguish local prediction, cosmetic events, authoritative game state and durable storage.

2. Read existing schemas, remotes/endpoints, authentication context, serialization and versioning before adding another wrapper or request type.

3. Inspect concurrency, retries, idempotency, ordering, reconnect and timeout behavior. Identify writes whose outcome can be uncertain after the transport loses acknowledgement.

4. Inspect persistence keys, ownership/session locks, atomic update patterns, migrations and failed-load handling. Never infer an empty account or place from an unavailable read.

5. Identify trust boundaries and sensitive data. Establish which identity/permissions come from the owning connection rather than from untrusted client-supplied fields.

6. Define actual provider/service quotas and test environments from official/live configuration. Keep fixture data separate from production player data and account credentials.

**Phase exit:** Sender, validator, authority, commit, persistence and uncertainty boundaries are known.

## Design

1. Write a contract for accepted inputs, validation, request identity, state transition, response and failure. Define bounds for size, frequency, lifetime and resource use.

2. Choose a single authority for each consequential state and keep cosmetic response independent. Explain how clients reconcile accepted, rejected, late and duplicate outcomes.

3. Choose retry-safe reads and idempotent or reconciled writes explicitly. A timeout after dispatch means unknown outcome until checked, not permission to repeat a purchase or reward.

4. Plan persistence updates with the actual backend's atomicity/session model. Preserve valid loaded data, unknown fields and migration rollback; do not replace a failed load with defaults and save them.

5. Plan reconnect, stale sessions, reordered messages and partial outages. Define visible pending/failure states that preserve drafts and allow a deliberate recovery.

6. Plan observability with request identities and bounded sanitized logs. Avoid recording credentials, personal data or full private payloads merely to debug a retry.

**Phase exit:** Schemas, bounds, idempotency/reconciliation and migration/reconnect contracts are explicit.

## Build

1. Validate types, finite numbers, ranges, ownership, state preconditions and applicable distance/cooldowns at the owning boundary before mutation.

2. Use server-derived identity and explicit authorization; do not trust client-provided account, player or resource ownership as proof.

3. Implement consequential state changes with the existing atomic transaction/update mechanism. Return the committed identity/version rather than only a generic success string.

4. Deduplicate repeated requests or reconcile unknown results using stable action identities. Keep retries bounded and honor actual reset hints; never turn repeated errors into an unbounded send loop.

5. Bound queues, payload sizes and per-client resources, with cancellation/expiry behavior. Reject malformed or oversized input before starting expensive work.

6. Preserve schema compatibility and unknown fields through migrations. Use isolated backups/fixtures and read back migrated values before treating the migration as safe.

7. Separate load failure, missing value and empty valid state. Keep the session read-only or explicitly blocked when the owning data cannot be safely loaded.

8. Instrument accepted/rejected/duplicate/uncertain outcomes with useful sanitized context and make user-visible pending states consistent with committed state.

**Phase exit:** The owning operation validates and commits safely with bounded resources and recovery.

## Integrate

1. Trace the complete client action through transport, handler, commit and reconciliation. Verify that UI, inventory, rewards and progression all read the same owning state.

2. Connect reconnect/session lifecycle and release locks/resources according to the actual backend contract. Do not independently add stale-lock overrides without understanding ownership.

3. Integrate schema/version handling with current clients and persisted data. Test old/new values and partial upgrades where the project supports them.

4. Apply service/account rate limits across relevant tabs, workers or clients rather than only one in-memory loop. Preserve actual cooldowns and access pauses across restarts.

5. Stop on authorization, account restriction or verification boundaries and require their legitimate resolution. Delays and prompt text do not grant access or change provider rules.

6. Keep network behavior testable through controlled delays, duplicates and failure fixtures without sending destructive or quota-exhausting traffic to live services.

**Phase exit:** Clients, backend, persistence and settings agree about committed and unknown state.

## Verify

1. Run normal accepted and rejected requests and compare authoritative read-back with client-visible state. A transport acknowledgement alone cannot prove a committed transaction.

2. Exercise malformed values, unknown identities, out-of-range quantities, stale versions, unauthorized resources and duplicate action IDs using safe fixtures.

3. Inject delay, dropped acknowledgement, reordering and disconnect/reconnect. Confirm a consequential action commits once and the client resolves its pending state accurately.

4. Test concurrent updates and session ownership conflicts through the backend's real semantics when available; label simulated concurrency separately.

5. Test failed load/save, interrupted migration and resource cleanup. Confirm valid data is preserved and no fallback defaults overwrite unknown state.

6. Verify actual reset hints, cooldown persistence and bounded retry exhaustion. Check that restarts and another tab cannot erase a real provider/account pause.

7. Inspect sanitized logs and error messages for enough diagnostic context without leaked credentials or private payloads.

8. Report server/backend, multi-client, production and fixture coverage separately; single-client correctness does not establish distributed correctness.

**Phase exit:** Accepted, rejected, duplicate, reordered and failed-state cases preserve authority/data.

## Failures

1. For duplicate charges/rewards, find whether duplication occurred before validation, at commit or during client reconciliation. Repair that owner rather than adding arbitrary client delays.

2. For stale state, compare versions, cache invalidation, message order and reconnect hydration; do not blindly force a refresh that loses pending work.

3. For data loss, stop writes, preserve evidence/backups and distinguish missing data from failed reads before attempting a migration or repair.

4. For repeated rate errors, inspect send ownership, retry counts and reset hints and pause unnecessary traffic. Do not evade restrictions with alternate accounts or masked requests.

5. For uncertain delivery, check authoritative request identity/state before reissuing a write. Preserve an explicit unknown result if read-back is unavailable.

6. For unavailable backend or multi-client access, deliver a precise contract and isolated fixture results while labeling live correctness unverified.

**Phase exit:** The exact validation, commit or reconciliation cause is repaired without blind replay.

## Engine application

### roblox

Keep server-side validation and one data owner. Use actual DataStore/session semantics, protect failed loads from default-save overwrite and reconcile repeatable actions. Preserve existing keys and networking wrappers. Use isolated test records; do not perform destructive persistence or receipt tests on production player data.

Existing candidate skills: roblox-remote-security, roblox-data-store-safety, roblox-profile-session-locking. Load the smallest relevant set through the live skill tool.

### godot

Inspect MultiplayerAPI authority and actual RPC settings/version before changing messages. Keep server validation, peer lifecycle, persistence and reconciliation explicit. Test connect/disconnect and delayed/duplicate state with available peers or labeled fixtures; do not infer network correctness from one editor instance.

Existing candidate skills: godot-multiplayer-api, godot-save-system. Load the smallest relevant set through the live skill tool.

### unity

Use the installed networking package and its exact authority/ownership semantics; do not assume every project uses the same Netcode version. Validate consequential requests, reconnection and save ownership. Label simulated peers versus actual multi-client/build tests and preserve serialized schema compatibility.

Existing candidate skills: unity-netcode, unity-save-system. Load the smallest relevant set through the live skill tool.

### blender

Limit Blender work to asset/source coordination and explicitly supported external tools. It is not a substitute for a game server, persistence backend or authenticated network authority. Keep paths/provenance/version handoffs and concurrent file ownership clear; validate consequential state in its real owning system.

Existing candidate skills: multi-app-art-pipeline, security-hardening. Load the smallest relevant set through the live skill tool.

### workspace

Use explicit request identities, schema validation, authenticated authority, cancellation and uncertain-write reconciliation. Preserve configuration and do not expose API secrets in generated frontend code or logs. Test backend behavior through authorized safe fixtures/accounts and respect actual provider reset/access notices.

Existing candidate skills: security-hardening, implement-feature. Load the smallest relevant set through the live skill tool.

### figma

Use Figma variables/prototypes only to illustrate pending, accepted, rejected and offline UX where supported. They are not an authenticated backend or a committed transaction. Handoff authoritative contracts and unknown-outcome recovery to the actual application/server.

Existing candidate skills: figma-developer-handoff, figma-variables. Load the smallest relevant set through the live skill tool.

## Acceptance evidence

- Consequential state has one validated authority and a visible commit/reconciliation path.
- Malformed, unauthorized, stale and duplicate input cannot commit invalid state.
- Unknown write outcomes are reconciled without blind replay.
- Failed loads, migrations and reconnects preserve valid data and ownership.
- Queues, payloads, retries and cooldown behavior are bounded and observable.
- Evidence identifies actual backend/multi-client checks separately from fixtures.

## Diagnosis

### Double commit

Probe: Trace request identity across validator and storage.

Repair: Make the owning operation idempotent/reconciled.

Recheck: Drop acknowledgements and deliver duplicates.

### Defaults overwrite saves

Probe: Compare failed read vs missing key paths.

Repair: Stop unsafe writes and preserve loaded state.

Recheck: Simulate load failure before any save.

### Endless pending

Probe: Trace timeout, cancellation and result ownership.

Repair: Resolve accepted/rejected/unknown states explicitly.

Recheck: Disconnect and reconnect during a write.

### Rate errors repeat

Probe: Inspect all senders and persisted cooldowns.

Repair: Stop automatic replay and honor provider reset.

Recheck: Retry only after a permitted explicit recovery.

## Deliverables

- Sender/validator/commit/receiver contract and versioned schemas.
- Idempotency, persistence, migration and reconnect behavior.
- Safe failure/concurrency fixtures and authoritative read-back evidence.
- Sanitized diagnostics and explicit production/account boundaries.

## Source guidance

- [Godot scene organization](https://docs.godotengine.org/en/stable/tutorials/best_practices/scene_organization.html): Reviewed official guidance; use the installed version.
