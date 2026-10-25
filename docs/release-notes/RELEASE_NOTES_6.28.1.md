# Multi-Script 6.28.1 — Blender assist for the enhancer and Game Idea Bot

A focused feature release: both prompt generators can now commission real
Blender asset production as part of the prompt itself. Opt-in, off by
default, and fully offline like everything else they do.

## Prompt enhancer: "Add Blender asset tasks"

- New checkbox in Settings → Studio → Prompt enhancer. When enabled, every
  enhanced brief gains a **BLENDER ASSET TASKS** section: model the request's
  meshes/props as real Blender assets instead of plain engine primitives,
  keep them export-ready (naming, UVs, materials), then export, import and
  verify scale/orientation from the intended player or camera view.
- Context-aware: world and game builds also get the "assemble the
  environment from a small modular kit, not a blockout" task; media/model
  work gets the export-readiness task.
- Honest about state: when Blender is connected the brief says so; when it
  is not, the brief says to connect it (Settings → Engines) or explain why
  the asset work was skipped.
- Question/lookup requests ("explain…", "where is…") never get asset tasks.
- The enhancer's honesty rules are unchanged: no invented measurements,
  colours or art styles - the new lines are covered by the same tests.
- The opt-in section gets its own +800 character budget on top of the
  strength cap, so it is never truncated mid-task (the 6.27.1 bug class).

## Game Idea Bot: "Include a Blender asset plan"

- New checkbox in the Ideas tab. When enabled, the generated brief grows
  with a concrete five-task **BLENDER ASSET PLAN** derived from that idea's
  own content:
  1. Model the hero subject (the idea's protagonist) as a game-ready asset.
  2. Build a snap-together modular environment kit for the idea's setting.
  3. Model the signature-action prop and its key visual states.
  4. Export glTF/FBX, import into the target engine, verify scale,
     orientation, materials and pivots after re-import.
  5. Render a neutral-light preview of each finished asset for review.
- Works even when Blender is not currently connected - enabling the option
  also adds the Blender hero-mesh tech bullet to the brief.
- Choosing Blender itself as the engine keeps the dedicated asset brief
  unchanged (no duplicated plan).
- Seeded generation stays perfectly deterministic with the option on.

## Tests

- New `tests/test_blender_assist.js`: 20+ assertions covering both features -
  default-off behaviour, per-strength caps, honesty rules, intent filtering,
  connected/disconnected phrasing, seeded determinism and UI wiring.
- Full existing suite and `tools/release_check.py` pass unchanged.
