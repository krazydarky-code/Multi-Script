# Multi-Script 6.27.0 — Presentation Craft: no more flat, empty worlds

6.27 targets the most common weak-provider failure head-on: a technically
"working" build that is visually empty — flat baseplate, default sky and
lighting, a few scattered props, no landmark, nothing to actually play. That
result now fails Multi-Script's own gates instead of being reported as done.

## What changed

- **24 new Presentation Craft skills** (`presentation-*`, 824 skills total):
  first-view composition, terrain height language, landmark wayfinding, sky &
  atmosphere pass, lighting value structure, palette discipline, dressing
  density, scale references, silhouette readability, environmental
  storytelling, ambient audio, VFX restraint, water/foliage life, path flow,
  day-night states, material consistency, prop clustering, horizon interest,
  spawn arrival, camera-verified beauty shots, low-tier fallback look, flat
  scene rescue, playable-loop completeness, and a presentation scorecard.
  Every skill is cross-engine (`general`), carries the full studio contract
  (steps, quality gates, release gate, evidence policy), and cross-links into
  the existing library so recommendations and meshes pick it up.

- **Two new bridge tools** (work with every provider, no engine required):
  - `ms_presentation_pass` — turns "the world looks flat" into a concrete,
    engine-aware pass: what to set for terrain, sky, lighting/atmosphere
    (with engine-specific guidance for Roblox Lighting/Atmosphere/Sky, Unity
    volumes, Godot WorldEnvironment, Blender world+lights), dressing density,
    scale, a per-tier performance budget, and camera-verified acceptance
    criteria. It never invents an art style; it makes the decisions explicit.
  - `ms_vertical_slice_gate` — audits a build or plan against the eight
    playable-loop elements (entry, objective, interaction, feedback, success,
    failure, reward, restart), flags stubbed features, and refuses to call a
    world with no loop "done".

- **Prompt enhancer 2.1**:
  - Fixed a dead branch: the `gameplay` domain was referenced by the
    weak-prompt defaults but no rule ever produced it, so "make me a game"
    never received the playable-loop guidance. It does now.
  - World/gameplay requests gain a first-view quality gate: terrain or height
    variation instead of one flat slab, one clear landmark, tuned lighting
    with sky and atmosphere, dressing that sells scale, verified from the real
    player camera — not the editor top view.

## Compatibility

- All provider adapters unchanged; the extension, bridge, plugin and catalogues
  move to 6.27.0 together (reload the extension and restart the bridge).
- The new tools are additive; every existing tool, skill id, marker and
  settings key behaves as before. The full test suite (Node + Python) passes.

## Upgrade

Reload the extension in `chrome://extensions` and restart the bridge. Then, on
any provider: "this world looks flat — run ms_presentation_pass and fix it".
