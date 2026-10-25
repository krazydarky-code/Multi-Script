# Multi-Script 6.27.1 — Engine setup guides, real idea generation, enhancer 2.2

A follow-up patch to 6.27.0 focused on the two things users hit first:
connecting an engine, and getting a genuinely fresh idea out of the Game Idea
Bot.

## Engine setup guides (Settings → Engines)

- New **Engine setup guides** section with a step-by-step card for Roblox
  Studio, Unity, Godot and Blender: what to install, exactly what to click,
  a one-line verification you can paste into chat, and a "good to know" tip
  (e.g. Blender's 9876 connection, Unity's pinned v10.2.0, Godot's
  project.godot, Studio's StudioMCP auto-discovery).
- **One-click Blender setup**: "Use bundled launcher" fills the add-on form
  with `launch_blender_mcp.py`; you only press Add addon → Restart MCP servers.
  The same fill works for Unity and Godot.
- Every card has a **Copy checklist** button for a plain-text version.

## Game Idea Bot now composes ideas

- New ideation pools (protagonists, threats, signature actions, economies)
  fuse into a real PREMISE instead of randomising a fixed skeleton; four
  combinatorial title patterns replace the two-word template.
- The signature hook is woven into the core loop instead of standing alone.
- Anti-repetition for unseeded clicks (the last few picks are skipped);
  seeded generation stays perfectly deterministic for Regenerate-from-seed.

## Prompt enhancer 2.2

- **Subjective-word translation**: "make it cool/epic/nicer" now adds a
  constraint requiring the model to translate the word into observable,
  checkable properties before building.
- **Ask-vs-default guard**: smart defaults may ask one short question when a
  missing choice is irreversible or destructive.
- **Multi-discipline sequencing**: requests touching 3+ domains get an
  inspect → core → integrate → present → verify ordering rule.
- Fixed silent truncation: the balanced/thorough caps (now 1500/2100) fit
  their own full section sets, so the quality gate and report-back sections
  survive instead of being cut mid-list.

## Compatibility

Fully additive; all providers, tools, skills and settings behave as before.
Reload the extension and restart the bridge after updating.
