# Multi-Script 6.28.0 — Effortless engine setup, bar themes, four new themes

The polish release: setup does the boring parts for you, the chat bar gets its
own look, and a long-standing ported-bar colour bug is gone for good.

## Setup that sets itself up

- `Setup.bat` / `Setup.sh` now run a new **engine extras** step
  (`runtime/setup_engines.py`): it installs **uv/uvx** when missing (Unity and
  Blender need it), **downloads the BlenderMCP add-on** into
  `runtime/addons/blender-mcp-addon.py`, and **adds the bundled Blender
  launcher to config.json** automatically. Every step is best-effort with
  exact manual commands printed when offline - setup never fails because of it.
- Blender setup is now: run Setup → open Blender → install the downloaded
  add-on file → N-panel → BlenderMCP → Connect. The in-app guide
  (Settings → Engines → Engine setup guides) reflects the shorter path.

## Chat bar themes (new setting)

- Settings → Chat bar → Look → **Theme**: the bar can follow the menu theme
  (default) or wear any of the 20 themes on its own - Classic Roblox menu with
  a Matrix bar is now a valid life choice.
- **Fixed the Classic Roblox / Roblox 2017 bar bug**: when the bar docks
  inside a provider's composer it leaves `#zs-root`, where the theme's
  variables stop applying - the page's own colours leaked in and light themes
  rendered light text on a light bar. Every bar theme now defines its full
  variable set on the bar node itself, with explicit brand/status/version
  colours per theme. Applies wherever the bar lives.

## Four new themes

- **Sakura** (light, blossom pink), **Crimson** (dark red),
  **Nebula (live)** (animated purple/teal drift), **Matrix (live)**
  (animated terminal green). Live themes respect Settings → Motion: none.

## Bridge: environment diagnostics + stale-bridge warning

- The Running tab gains a **This PC** row: Python version, uvx (Unity/Blender
  prerequisite), npx (Godot prerequisite) and the Blender add-on - so "why is
  my engine down" is answered at a glance instead of guessed.
- New **Update pending** warning when the running bridge is older than the
  extension (the classic "updated the files but the old bridge still holds the
  port" trap): it tells you to press Restart or re-run Setup.
- Diagnostics are computed once a minute and cached; status pushes stay cheap.

## Provider compatibility audit

- New automated audit loads all 10 provider adapters (Notion AI, ChatGPT,
  Claude, Gemini, DeepSeek, Kimi, GLM, Qwen, Arena, Meta AI) with a stubbed DOM
  and asserts the full 38-member interface floor, clean parse, and no leftover
  TODOs. All 10 pass; the two MAIN-world helper scripts are parse-checked.
  (Live-site selector drift can only be confirmed on the real sites; the audit
  guards everything that can be guarded offline.)

## Enhancer 2.3 + bigger idea pools

- New audio constraint: seamless loops, ambience mixed under UI/gameplay,
  volume settings respected.
- Game Idea Bot pools grew again (settings, hooks, protagonists, threats,
  signature actions, economies, art styles) on top of 6.27.1's fused premises.

## Compatibility

Fully additive. Reload the extension and restart the bridge after updating;
re-run Setup once so the new engine extras step runs.
