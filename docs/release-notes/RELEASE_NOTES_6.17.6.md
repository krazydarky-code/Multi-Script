# Multi-Script 6.17.6 — Monochrome

A feature release: a prompt enhancer, a media relay, desktop and tab vision, nine new workflow tools,
and a full monochrome rebuild of the menu.

---

## Everything new

### 1. Auto prompt enhancer (Settings)

Turn *"make the door open when the player touches it"* into a brief the model can execute: the goal
restated, the constraints your words imply, the connected-engine facts, and what "done" means for that
kind of task. Light / balanced / thorough, or off.

- **Offline rules.** No API cost, no network round trip, nothing to leak.
- **Never contradicts you.** Your wording is preserved and sent first; the enhancer only adds.
- **Never invents specifics.** No made-up dimensions, colours or numbers.
- **Idempotent.** An already-detailed request is left alone; a second pass is a no-op.
- **Live preview** in Settings shows exactly what the model will receive.

### 2. Media relay (photo + video)

Send a screenshot, photo or clip into a chat site that has no upload button or refuses the file.

- Delivered as a **real paste** through the site's own input path — the same one your clipboard uses.
- **Videos are decoded into up to six frames** with `ffmpeg`, and say so honestly when `ffmpeg` is
  missing rather than pretending a video arrived.
- png · jpg · gif · webp · bmp · mp4 · webm · avi · mov. Drop anywhere over the composer.

### 3. Tab and desktop vision

- **See your browser tabs** — real titles, URLs and hosts; read a tab's text; focus it; open a URL; type
  into its composer.
- **See your desktop apps** — Roblox Studio, Unity, Godot, Blender, Figma, editors, browsers — with real
  window titles.
- **Text only.** No screenshots, no keystroke capture.
- **Only `http:`/`https:` can be opened.** `javascript:`, `data:`, `file:` and browser-internal schemes
  are refused.
- **Four independent grants** in Settings: see tabs · see windows · read text · type into a tab. Allow
  looking while forbidding touching.
- **Unlock full desktop vision** reports each optional package, what is already satisfied, and the exact
  command — and installs nothing itself.

### 4. Nine workflow tools

Six for Roblox Studio:

| Tool | What it is for |
|---|---|
| `ms_roblox_build_verifier` | Re-reads the live place: is what you claimed to build actually there? |
| `ms_roblox_script_audit` | Finds the mistakes that break shipped games, in real Luau source. |
| `ms_roblox_playtest_director` | Plans and optionally runs a real playtest, stopping at the first failure. |
| `ms_roblox_asset_scout` | Finds assets that already fit — without ever inventing an id. |
| `ms_roblox_scene_diff` | Snapshots a subtree and diffs two snapshots. |
| `ms_roblox_error_triage` | Ranks console errors and keeps noise separate from failures. |

Three for the agent:

| Tool | What it is for |
|---|---|
| `ms_agent_plan_then_act` | Plan first; execute only when approved. |
| `ms_agent_self_check` | Confidence derived from evidence-per-action. |
| `ms_agent_context_recall` | What is connected and staged right now. |

### 5. Monochrome UI

True black-and-white surface and ink ramps, a pointer-tracked ambient sheen, two new themes (`mono`,
`ink`), a de-saturated default accent, and a `frost` light variant. Every panel re-skinned. Built as a
non-destructive final CSS layer, so **every existing feature and element id is preserved**.

---

## The rule behind all of it

Every tool here **refuses rather than invents**.

- No engine reachable → `available: false` with the real fixes, never an empty success.
- A read that could not be performed → `unverifiable`, which is a *different answer* from
  "it does not exist".
- Console triage keeps deprecation warnings and plugin chatter out of the failure list.
- Self-check reports `unknown` rather than `high` when nothing was actually proven.

---

## Install

1. Download **`Multi-Script-6.17.6-Full.zip`** (extension + bridge together) — or
   **`Multi-Script-Extension-6.17.6.zip`** if you already have the bridge.
2. Unzip, then load the extension: `chrome://extensions` → Developer mode → **Load unpacked** →
   select the extension folder.
3. Start the bridge: `start.bat` (Windows) or `MacOS_Start.command` (macOS).
4. Open a supported chat site. Multi-Script mounts on the composer.

Already on 6.17.5? Replace the extension folder and restart the bridge. Your settings are preserved.

---

## Numbers

- Direct tools: **211 → 229**
- Skills: 800 · virtual specialists: 300 · Roblox skills: 199 · Roblox specialists: 90
- Tests: **39 JavaScript** and **30 Python**, all passing
- New gates: `test_prompt_enhancer.js`, `test_media_relay.py`, `test_media_relay_js.js`,
  `test_desktop_vision.py`, `test_roblox_workflow_tools.py`
