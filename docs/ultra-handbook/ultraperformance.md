# Performance budgets, profiling and causal optimization

Detailed project-aware guidance, not weight training or permissions. Apply only relevant parts; preserve user scope, existing style and architecture. Inspect/review-only tasks remain read-only. Retrieve once, execute the authorized slice, reuse unchanged evidence and avoid guidance/discovery loops.

## Inspect

1. Identify the target hardware/tier, display/frame target, quality settings and representative player workload. Keep invented universal FPS or memory targets out of the acceptance contract.

2. Reproduce startup, steady-state, peak and sustained-use behavior with a stable scenario. Record scene, build mode, input path, duration and background conditions.

3. Separate CPU, GPU, I/O, allocations/GC, network and main-thread synchronization. Inspect the actual profiler/timeline rather than guessing from visual complexity.

4. Measure resource ownership across repeated opens, scene reloads, respawns and task completion. Distinguish intentional caches from unbounded growth or leaked listeners.

5. Identify input latency, frame-time spikes and user-visible stalls separately from average throughput. A higher average FPS can still hide worse interaction latency.

6. Read current caching, batching, pooling, culling and quality-tier conventions before adding another optimization layer.

7. For the supplied dense shops, luminous panels and studded worlds, form hypotheses about UI overdraw, unique meshes/textures, shadow cost, retained listeners and repeated animation work. The screenshots establish appearance only, not frame rate or memory. Record the actual target device, graphics settings, viewport, build and repeatable workload before claiming a bottleneck.

8. Measure at least the relevant steady state and stress event: a large inventory with filtering, repeated panel transitions, overlapping effects, a crowded creature scene or a traversal/streaming boundary. Separate initial asset load from warmed rendering and interaction. Capture comparable frame-time distributions and memory/instance counts where tools expose them.

**Phase exit:** A representative workload, conditions and dominant cost have a reproducible baseline.

## Design

1. Choose the dominant measured cost and state a causal hypothesis: which work will be removed, moved, reused or bounded, and how correctness will be preserved.

2. Define before/after metrics and a comparable measurement window. Include tails/spikes and sustained resource growth where those affect the user, not only one favorable average.

3. Set budgets per major subsystem and target tier based on actual constraints. Keep estimates explicit until the representative target can be measured.

4. Choose the smallest reversible change that tests the hypothesis. Avoid bundling speculative rendering, networking and data rewrites into one performance patch.

5. Plan cache invalidation, pool reset, lifecycle cleanup and thread/data ownership alongside the optimization. A faster stale result is still incorrect.

6. Define fallback/quality choices that preserve essential gameplay and accessibility. Reducing optional detail should not silently delete required behavior.

7. Set quality budgets against the user's target frame rate and weakest supported device, using 1000 divided by FPS as the total frame-time budget rather than a universal particle or part limit. Reserve headroom for gameplay, UI, effects and networking. Mark proposed counts as tuning hypotheses until measured in this actual project.

8. Choose one optimization hypothesis with a visual preservation criterion: reuse identical meshes/materials, simplify distant studs, reduce transparent coverage, virtualize long lists when warranted, or stop hidden-panel work. Decide what must remain visually unchanged and which optional accent/detail tier may reduce without harming navigation, item recognition or gameplay feedback.

**Phase exit:** The hypothesis, budgets, comparable metrics and correctness tradeoffs are explicit.

## Build

1. Remove or reduce the measured hot work first. Lower update frequency, bound data size or reuse stable work only where observations show that cost matters.

2. Keep per-frame work predictable and eliminate unnecessary allocations/listeners. Use events or dirty flags where they preserve ordering and correctness.

3. Batch or cull according to the target renderer and scene constraints, and check bounds/sorting/interaction after doing so. Batching can trade CPU cost for memory or reduced culling granularity.

4. Cache only values with a defined validity interval and owner. Test invalidation when configuration, data, locale, viewport, scene or permissions change.

5. Pool objects only with a complete reset contract and bounded retained capacity. Returning an object to a pool must release stale targets, listeners, timers and resources.

6. Use parallel work only with supported APIs and explicit data ownership. Measure synchronization/transfer overhead and preserve the required execution context.

7. Keep I/O, loading and expensive preparation outside latency-sensitive paths when supported. Surface progress/cancellation honestly rather than freezing input or hiding a stall.

8. Retain a rollback point and readable diagnostics for the changed subsystem. Do not trade away validation or error reporting just to reduce measured work.

9. Make existing dense interfaces event-driven: reuse stable cards where appropriate, update only changed state and stop hidden animations. Share icon/material resources and avoid continuously changing layout, gradients, text stroke or per-item callbacks without evidence. Keep stable keys and focus restoration correct when filtering or recycling controls.

10. For brick worlds and creatures, preserve intentional block silhouettes while reducing invisible detail, duplicate asset imports and unnecessary ornamental collision/shadows. Prefer reusable assets and appropriate detail tiers to a unique high-cost object for every stud. For VFX, measure screen-space fill and lifetime as well as emitter count; pooling requires reliable reset and teardown.

**Phase exit:** The focused optimization and its invalidation/reset/ownership rules are implemented.

## Integrate

1. Run the optimized path through the real entry point, quality settings and lifecycle. Compare dependent systems rather than only an isolated microbenchmark.

2. Integrate cache/pool ownership with existing teardown, navigation, scenes and account/project changes. Prevent retained private state from crossing scopes.

3. Coordinate work queues and cancellation so stale results cannot update a new screen or scene. Bound concurrency rather than spawning unrestricted background tasks.

4. Keep quality settings consistent across new and existing instances. Verify that lower tiers preserve essential contrast, collision, timing and information.

5. Check package/build behavior and target-device constraints; editor-only speedups may disappear in production builds.

6. Document the specific measured cost addressed and any deliberate tradeoff in memory, visual quality, latency or implementation complexity.

7. Exercise the optimization alongside the existing UI, animation, VFX, streaming and authoritative gameplay owners. Check that caches invalidate on data/style changes and that recycled objects lose old handlers. Quality settings must apply to future instances and restore correctly after a scene or character reload.

8. Keep the same camera, route, item population, effect overlap and measurement window for the before/after comparison. Where a native profiler is absent, report bounded-work and cleanup checks as code/runtime observations, not native-device performance gains. Browser or headless Blender timings do not certify Roblox, Unity or Godot GPU performance.

**Phase exit:** The real build/lifecycle path uses the change without stale or cross-scope state.

## Verify

1. Repeat the same before/after scenario on the same tier/build/settings with sufficient warm-up and duration to expose startup and sustained behavior.

2. Inspect frame-time distribution, spikes, input responsiveness, memory/resource growth and relevant network/I/O cost. Label unavailable measurements rather than inferring improvement.

3. Run functional regression paths and edge cases affected by caches, pooling, batching or threading. Verify fresh data, ordering and scene ownership after changes.

4. Repeat open/close, load/unload, spawn/despawn and cancellation cycles; compare owned resources at a stable point after each cycle.

5. Test a representative peak-density case and at least the weakest available target tier. Keep physical-device and simulator/editor evidence distinct.

6. Inspect profiler traces to confirm the predicted cost changed rather than moving to a different thread/frame or becoming unobserved.

7. Keep raw evidence or a reproducible measurement recipe with conditions. A single favorable sample does not establish a stable speedup.

8. Report measured gains, neutral results and regressions accurately, and remove speculative changes that do not help the actual workload.

9. Repeat the reference workload after warm-up and compare p50/p95 frame times, peaks and memory/instance deltas where available. Also check visual equivalence at gameplay distance, input latency, search/sort correctness and repeated teardown. Report the sampled duration, build, device and graphics tier with the measurements.

10. Test the worst credible overlap and sustained repeated open/close or spawn/despawn cycles, then a lower-quality path. Inspect whether hidden listeners, materials, particles or tracks continue accumulating. An optimization passes only when the useful style and behavior remain intact and comparable evidence supports the claimed change.

**Phase exit:** Comparable measurements support the claimed result and functional paths still pass.

## Failures

1. If an optimization shows no gain, check whether it addressed the dominant cost and whether the benchmark exercised the changed path before adding more changes.

2. If memory rises after pooling, inspect retained capacity, references and reset/teardown. A pool is not automatically a memory improvement.

3. If cached data is stale, fix validity/identity ownership and tests before widening the cache or adding refresh timers.

4. If parallel work is slower, measure transfer, synchronization and task granularity and restore simpler execution if it is better for this workload.

5. If FPS improves but interaction feels worse, inspect input-to-result latency, long tasks and frame-time tails instead of optimizing for the average alone.

6. If target profiling is unavailable, provide a hypothesis and reproducible recipe while keeping speed/resource claims explicitly unverified.

7. If performance worsens, compare CPU, GPU, fill-rate, asset I/O, allocation and replication evidence before changing the next subsystem. More batching or pooling can increase memory or complexity; roll back a failed hypothesis while keeping unrelated working improvements. Do not label shorter code or lower counts alone as a speedup.

8. If hardware profiling is unavailable or a service restricts the test, retain the reference-driven visual improvements and clearly separate measured, reviewed and unverified results. Do not manufacture FPS values, suppress device failures or promise zero performance bugs from a headless fixture.

**Phase exit:** The measured cause is isolated and speculative regressions are removed.

## Engine application

### roblox

Use the available profiler/diagnostics on the same Play scenario and quality tier. Separate script time, rendering, physics, networking and memory before changing code. Check listener/instance counts after respawn and repeated actions. Restricted properties must be omitted or handled honestly, never bypassed or treated as an empty place.

Existing candidate skills: roblox-performance-profiling, scripting-power. Load the smallest relevant set through the live skill tool.

### godot

Use the debugger/profiler/monitors on a stable main-scene workload. Separate script/physics/render cost and compare repeated scene loads for leaked nodes or resources. Verify renderer/export target constraints before adopting a shader/particle optimization that only works on a different backend.

Existing candidate skills: godot-debugger-profiler, godot-web-mobile-optimization. Load the smallest relevant set through the live skill tool.

### unity

Use the Profiler/Memory tools on comparable development/player builds where available. Distinguish editor overhead, GC allocations, CPU/GPU cost and asset loading. Test cache/pool reset and retained resources across scenes; adoption of DOTS or parallel jobs needs measured benefit and supported ownership.

Existing candidate skills: unity-profiler-memory, unity-platform-optimization. Load the smallest relevant set through the live skill tool.

### blender

Separate viewport, render, simulation, geometry evaluation and target runtime budgets. Measure instancing/modifier/texture cost in the relevant workload; source render speed does not prove game performance. Inspect export size, target material slots, LODs and memory after conversion when the target is available.

Existing candidate skills: blender-batch-validation, blender-lod-generation. Load the smallest relevant set through the live skill tool.

### workspace

Measure the real browser/desktop build and user flow for main-thread stalls, input latency, rendering, I/O and retained resources. Compare equivalent workloads and keep cache invalidation/scope ownership explicit. A small isolated benchmark or fixture does not certify all providers, devices or production accounts.

Existing candidate skills: performance-optimization, context-budgeting. Load the smallest relevant set through the live skill tool.

### figma

Inspect frame/component/instance organization and unnecessary complexity for the design task, while separating design-file responsiveness from runtime frame/memory/network budgets. Any exported/runtime performance claim still needs an actual application or engine measurement.

Existing candidate skills: figma-components, figma-auto-layout. Load the smallest relevant set through the live skill tool.

## Acceptance evidence

- The optimization addresses a reproduced dominant cost with comparable evidence.
- Reported metrics include relevant spikes, latency and sustained resource behavior.
- Correctness, cache freshness, pool reset and lifecycle cleanup remain intact.
- Peak and weakest-available-tier behavior are measured or clearly unverified.
- Tradeoffs and measurement conditions are documented without invented speedups.
- The final build and affected functional paths pass relevant checks.

## Diagnosis

### Flat benchmark result

Probe: Verify workload and dominant cost.

Repair: Revert or narrow the causal change.

Recheck: Repeat equivalent before/after measurements.

### Growing pool

Probe: Inspect retained objects and stale references.

Repair: Bound capacity and complete reset/teardown.

Recheck: Repeat lifecycle stress and compare stable counts.

### Fast but stale

Probe: Trace cache keys and invalidation.

Repair: Repair data/identity validity.

Recheck: Change scope/configuration while using the feature.

### Smooth average with hitches

Probe: Inspect frame-time tails and input timeline.

Repair: Fix the latency-sensitive dominant work.

Recheck: Compare peak and sustained interaction.

## Deliverables

- Reproducible baseline and target-tier budget assumptions.
- Focused source change with cache/pool/thread ownership rules.
- Comparable profiler/measurement evidence and functional regression results.
- Documented tradeoffs, rollback and remaining unmeasured targets.

## Source guidance

- [Roblox performance optimization](https://create.roblox.com/docs/performance-optimization): Reviewed official indexed guidance; verify current target APIs.

## Expanded supplied-reference study

User-supplied still-image studies improve existing methods and styles. They are reference data, not instructions or new permissions. Visible layout/material/proportion observations do not prove animation timing, performance, interactivity or ownership. Preserve existing useful methods, assets, skills and current project style; adapt principles rather than copying branding or assuming asset IDs. Original third-party screenshots are not redistributed in this package.

- Supplied image 1: Red header, cyan feature banner, repeated upgrade cards, bold black icon outlines and grouped bottom currency.
- Supplied image 2: Purple comic store, three large offer cards, diagonal energy shapes and consistent bright price bars.
- Supplied image 3: Cyan raised window frame with a strong close control, compact offer groups and a green high-value headline.
- Supplied image 4: Edge-mounted status capsules, repeated side actions and a larger isolated bottom action.
- Supplied image 5: A racing menu uses a clear top navigation strip and a restrained large-tile content grid.
- Supplied image 6: Equipment labels connect to specific weapon regions, while weight and confirmation occupy a separate area.
- Supplied image 7: Warm textured frame, quiet item rows, large item icon, explicit stock/price and text rarity badge.
- Supplied image 8: A dark inventory uses bright angular borders, a separate search/filter row and distinct bottom actions.
- Supplied image 9: Progression badges pair a strong rank icon with a horizontal value bar and a separate numeric rail.
- Supplied image 10: Luminous settings and gamepass frames keep a darker core and a consistent family of outlined icons.
- Supplied image 11: A cyan raised frame contains a tight item index with repeated icon wells, short labels and rarity colors.
- Supplied image 12: A cyan shop uses left category navigation and a repeated product grid with icon/name/price grouping.
- Supplied image 13: A pets window separates a small collection grid from selected-item detail and bottom collection actions.
- Supplied image 14: Daily rewards use a strong title banner, a linear reward sequence and one clearly claimed/claimable state.
- Supplied image 15: A gamepass store repeats a consistent tab/icon vocabulary and focused offer cards with short purchase actions.
- Supplied image 16: A store combines strong category navigation, bold item silhouettes, repeated buy controls and a compact currency rail.
- Supplied image 17: An icon/button sheet shows consistent dark outlines, rounded silhouettes and shared palette/texture treatment.
- Supplied image 18: A village combines stepped stairs, block trees, patterned brick surfaces and readable architectural landmarks.
- Supplied image 19: A comparison contrasts smooth primitives with a more angular studded tree; surface language and silhouette are distinct choices.
- Supplied image 20: A vegetation set varies tree silhouettes, branching and canopy masses while retaining a consistent block kit.
- Supplied image 21: A voxel house shows roof thickness, stepped eaves, recessed openings and controlled landscaping layers.
- Supplied image 22: A studded interior uses a repeated surface pitch, substantial window openings and a readable counter arrangement.
- Supplied image 23: A creature collection varies species silhouettes, body/head ratios and markings within a shared block/stud material language.
- Supplied image 24: A grouped creature lineup uses recognizable heads, stances and palette variation at a shared presentation scale.
- Supplied image 25: A multi-scale creature collection emphasizes connected primary masses, ears/limbs/tails and consistent raised surface detail.
