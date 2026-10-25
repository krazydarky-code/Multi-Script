# Gameplay rules, feel, state and systemic integration

Detailed project-aware guidance, not weight training or permissions. Apply only relevant parts; preserve user scope, existing style and architecture. Inspect/review-only tasks remain read-only. Retrieve once, execute the authorized slice, reuse unchanged evidence and avoid guidance/discovery loops.

## Inspect

1. Trace the existing input-to-action path, controller/state machine, domain services and authority. Identify which component commits damage, progression, inventory or other consequential state.

2. Define the player's desired action and the observable success condition. Separate gameplay requirements from presentation requests and preserve functioning adjacent mechanics.

3. Inspect timing, cooldowns, collision/hit queries, resource costs, interruption and reset. Record units and coordinate spaces rather than copying constants from another game.

4. Inspect data configuration, spawn/respawn, equipment, save/load and multiplayer assumptions. Find the ownership boundary for timers, subscriptions and temporary actors.

5. Reproduce normal play and the concrete failure before changing code. Read actual logs and state; a missing query result does not establish that the mechanic is absent.

6. Check advertised engine tools and test/play access. Distinguish authored source, instantiated scene state and observed gameplay before planning a delivery claim.

**Phase exit:** Input, rules, authority, timing and lifecycle ownership are mapped.

## Design

1. Write a compact rules table: action preconditions, accepted input, authority checks, state transition, cost, consequence, feedback and recovery. Define invalid/duplicate actions explicitly.

2. Choose the smallest complete vertical slice that demonstrates the requested feel and rules. Implement one full interaction before generalizing an ability framework or plugin architecture.

3. Specify timing in meaningful phases such as start, active, recovery and cancel. Define which changes can interrupt the action and how ownership returns to normal play.

4. Choose data-driven parameters for values that designers actually tune. Preserve existing module interfaces and avoid moving every constant into a new configuration system without need.

5. Plan event contracts between gameplay, animation, VFX, audio and UI. Consequences need one authority; cosmetic layers should be replaceable without changing the rules.

6. Define acceptance scenarios for normal use, invalid input, latency/duplicate delivery, death, respawn and repeated activation. Keep tests aligned with player-visible outcomes.

**Phase exit:** Accepted/rejected/duplicate action rules and a complete vertical slice are specified.

## Build

1. Implement the accepted action through input, validation, transition, consequence and feedback. Read back authoritative state after the change instead of relying on a visual animation alone.

2. Use the existing controller/state owner and explicit transition guards. Prevent overlapping actions from committing incompatible state or leaving controls permanently disabled.

3. Validate quantities, identity, ownership, distance, resource availability and timing on the owning side. Reject malformed and stale requests before changing state.

4. Keep physics queries and damage windows deliberate, with correct filters, spaces and deduplication of targets. Do not let one multi-part hit apply damage repeatedly unintentionally.

5. Implement cancellation and cleanup for timers, listeners, temporary hitboxes, actors and cosmetic handles. Reset movement/input overrides even when an action fails halfway through.

6. Give repeated consequential requests an idempotency or reconciliation story. A delayed acknowledgement must not charge the resource or award the reward twice.

7. Tune responsiveness and feedback in the real controller/camera. Separate local prediction/cosmetics from committed outcomes and reconcile rejected input visibly.

8. Keep configuration and names compatible with existing scenes/saves. Apply small reversible changes and retain a known-good reproduction or fixture.

**Phase exit:** The action validates, commits, presents feedback and cleans up reliably.

## Integrate

1. Wire the mechanic to real UI, animation, sound and VFX using shared action identities/events. Do not leave placeholder feedback that implies a missing rule is implemented.

2. Integrate spawn/respawn, equip/unequip, scene transitions and save/load. Rebind only the owner that changes and prevent duplicate subscriptions after re-entry.

3. Preserve authority across clients and server or backend. Compare accepted/rejected outcomes and ensure cosmetic callbacks cannot bypass validation.

4. Connect navigation/AI and physics ownership where required. Test controller interactions such as knockback during movement or an ability while entering a menu.

5. Use task progress to record implemented paths, actual tests and blockers. A successful tool result should not mark unrelated requirements complete.

6. Document the final tunable parameters, state ownership and extension points that another developer needs, without exposing unnecessary internal process to the player.

**Phase exit:** UI/motion/audio/VFX, respawn and networking agree with the owning gameplay state.

## Verify

1. Run the primary interaction from the actual game entry point and inspect both behavior and owning state. Confirm the user-visible result agrees with the committed outcome.

2. Test invalid input, insufficient resources, out-of-range targets, stale identities and repeated rapid triggers. Confirm rejected actions do not partially mutate state.

3. Interrupt during each action phase with death, despawn, equip changes, scene unload or cancellation. Verify controls and resources return to a coherent state.

4. Test duplicate, delayed and reordered messages where networking applies, using real multi-client tools or clearly labeled fixtures. Single-client success does not prove multiplayer correctness.

5. Inspect the feel at relevant frame rates and input devices. Compare contact timing, responsiveness, camera feedback and readability at normal play speed.

6. Repeat the mechanic long enough to expose leaked instances, subscriptions or accumulating offsets. Check resource counts and logs after cleanup.

7. Rerun the original reproduction and affected neighboring mechanics after tuning. Preserve checks that expose meaningful behavior rather than tests that merely mirror the implementation.

8. Report implemented, observed and unverified paths separately, including native-editor, account or publishing limitations.

**Phase exit:** Normal, invalid, interrupted and relevant latency/device cases match committed outcomes.

## Failures

1. If the action looks correct but has no effect, trace the authority path and state commit before changing the animation or VFX.

2. If the mechanic triggers twice, inspect input binding, request identity, event subscriptions and multi-part collision before adding a large global debounce.

3. If controls stay disabled, inspect every exit/cancel/error path and ownership of movement or input overrides.

4. If clients disagree, compare committed authoritative state and reconciliation, then inspect duplication or ordering. Do not attempt to fix game rules by replicating cosmetics more frequently.

5. If tuning breaks adjacent actions, inspect shared state/parameter ownership and restore a smaller change surface.

6. If runtime execution is unavailable, deliver editable source and precise setup/testing handoff with unverified behavior clearly identified.

**Phase exit:** The failed owner/transition is repaired without masking it with cosmetic changes.

## Engine application

### roblox

Keep purchases, currency, rewards and damage under validated server authority. Reuse existing remotes/services; validate type, finite range, ownership and applicable timing/distance. Keep animation/VFX events cosmetic. Test repeated requests, reset and respawn using the real Studio context and selected studio_id.

Existing candidate skills: game-systems, roblox-character-controller, roblox-melee-combat. Load the smallest relevant set through the live skill tool.

### godot

Use the existing InputMap, CharacterBody/physics owner, signals and scene services. Keep _process/_physics_process roles and cancellation explicit. Test jump/movement/interaction from the actual main scene with correct delta/units and ensure reloads do not multiply signal bindings or autoload state.

Existing candidate skills: godot-characterbody-3d, godot-input-map. Load the smallest relevant set through the live skill tool.

### unity

Use the existing input package, controller, MonoBehaviour/service lifetime and physics authority. Separate Update/FixedUpdate behavior deliberately and avoid duplicate registration in OnEnable/OnDisable cycles. Test pooled prefabs, scene changes and repeated actions with actual Play/build entry points.

Existing candidate skills: unity-input-system, unity-physics. Load the smallest relevant set through the live skill tool.

### blender

Blender can author models, rigs, animation and scene assets for a mechanic, but it does not establish gameplay authority or a target controller. Preserve a clear handoff contract and test imported motion/collision in the actual engine when available; never present a source animation as a playable integrated mechanic.

Existing candidate skills: animation-production, multi-app-art-pipeline. Load the smallest relevant set through the live skill tool.

### workspace

Trace the actual engine/web-game input, update/physics loop, state owner and backend authority. Keep UI/cosmetic feedback separate from committed rules, preserve drafts/configuration and test the real application entry point. Do not claim desktop control or engine execution unless those tools are advertised.

Existing candidate skills: implement-feature, gameplay-systems. Load the smallest relevant set through the live skill tool.

### figma

Prototype and annotate the action/state/feedback flow with actual component variables and links when supported. Keep authoritative gameplay, persistence and networking out of the design artifact's success claim. Handoff rule/timing contracts to the real engine and verify there.

Existing candidate skills: figma-prototyping, figma-developer-handoff. Load the smallest relevant set through the live skill tool.

## Acceptance evidence

- The primary action completes a real input-to-authoritative-result path.
- Invalid and repeated input cannot partially commit or duplicate consequential state.
- All interruption and lifecycle exits restore usable controls and clean owned resources.
- Animation, UI, sound and VFX reflect the same action state and timing.
- Required multiplayer/frame-rate/device behavior has actual evidence or explicit boundaries.
- The original reproduction and affected neighboring mechanics remain correct.

## Diagnosis

### Visual hit without damage

Probe: Trace validation, hit identity and state commit.

Repair: Repair the owning gameplay path.

Recheck: Trigger with authoritative read-back.

### Repeated reward

Probe: Compare request identity and commit semantics.

Repair: Add idempotent/reconciled handling.

Recheck: Deliver duplicate and delayed results.

### Frozen movement

Probe: Inspect overrides across every exit path.

Repair: Centralize restoration with the action owner.

Recheck: Cancel, die, respawn and reload.

### Desynced clients

Probe: Compare authority and prediction state.

Repair: Fix validation/reconciliation contract.

Recheck: Test latency and rejected input.

## Deliverables

- Rules/state/timing contract and integrated gameplay source.
- Data parameters and authority/event interfaces.
- Normal, invalid, duplicate and lifecycle test evidence.
- Playable target slice or an explicitly scoped source-only handoff.

## Source guidance

- [Godot scene organization](https://docs.godotengine.org/en/stable/tutorials/best_practices/scene_organization.html): Reviewed official guidance; use the installed version.
- [Unity 6 Animation Blend Trees](https://docs.unity3d.com/6000.0/Documentation/Manual/class-BlendTree.html): Reviewed official Unity 6.0 page; verify installed controller/package.
