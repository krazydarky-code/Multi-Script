# Multi-Script 6.26.0

- ChatGPT reliability: paged tool results (`more_output`), compact `list_commands` index with `names`/`query` filters, stronger ChatGPT rules (no Canvas / code interpreter / refusals). Same paging for Claude and Gemini.
- Multiple engines in one session, routed with `_server`.
- Start marker renamed to `⟦MS-SYS⟧` / `⟦MS-RE⟧`; legacy markers still accepted.
- Software Builder (W.I.P.): 16 `ms_ws_*` bridge tools, folder picker or auto-created project folder, 11 templates, optional command running with safety gate.
- Game ideas settings tab (engine-aware; Blender → asset brief).
- Game Idea Bot production pass: generated briefs now include player fantasy, design pillars, first-ten-minute onboarding, complete-system expectations, accessibility, scope cuts and observable acceptance tests; Blender briefs add a staged asset workflow and mandatory export re-import validation.
- Game Idea Bot provider-form hotfix: Generate, scope, Copy and Put in chat are explicit non-submit buttons; the click handler also cancels provider form submission, validates the generated result, restores its busy state, exposes failures instead of dying silently, and updates an accessible live status. All overlay buttons are now normalized centrally so the same form-submit bug cannot migrate to another settings control.
- New provider-neutral MCP helpers: `ms_request_blueprint`, `ms_tool_workflow` and `ms_completion_gate` turn weak prompts into reversible project-aware briefs, select only genuinely advertised native tools, and block completion until concrete evidence covers the acceptance criteria.
- Prompt enhancer weak-request pass: the original request still survives verbatim and all existing modes/toggles remain, while short prompts gain project-preserving smart defaults and a stricter quality gate without invented specifics.
- Skill recommendation now expands everyday weak-prompt language, ranks against steps/gates/capability metadata, and returns a more diverse production stack across the complete 800-skill catalogue.
- Offline tool/schema audits no longer terminate merely because WebSockets has not been installed; actually starting the bridge still reports the exact Setup/install action.
- 8 new themes (Classic Roblox, Roblox Dark, Terminal, Sunset, Ocean, Paper, animated Aurora and Lava) and custom PNG/JPG/GIF/WebP backgrounds.
- Cleanup: removed `tools/archive/`, README reorganised (history → `docs/FEATURE_HISTORY.md`), new `docs/ARCHITECTURE.md`.
- Windows process reliability: free-threaded Python 3.13 child launchers run with the GIL enabled; MCP servers receive a graceful stdin close before forced tree termination; failed handshakes are cleaned up; intentional stops no longer print false crash errors.
- Chatbar state fix: Stop remains hidden until an agent is actually running.
- Start-without-engine isolation: engine-free and Software Builder chats now enforce their execution boundary at dispatch time, so connected Roblox, Unity, Godot, or Blender instances cannot be modified accidentally.
- Software Builder settings redesign: theme/accent-aware toggle buttons, clearer workspace choices, stronger primary actions, PC-bridge status, capability check, restart/reconnect, and terminal shortcuts.
- Local bridge compatibility: workspace calls are capability-gated before dispatch, stale registered bridge copies get an actionable version/path diagnosis instead of repeated unknown-tool errors, and the PC folder picker no longer runs until configuration succeeds.
- Software Builder launch detection now queries the bridge's live, unfiltered tool catalogue instead of the chat mode's filtered tool snapshot, eliminating false “needs the bridge” warnings while the terminal is online.
- Graph Memory transport: valid memory replies now resolve in the extension worker; stale bridges show a precise update/restart instruction instead of the misleading “unknown message type” loop.
- Fresh-chat startup claims are released after every bootstrap attempt, so switching from a completed chat to another provider root/new chat can start normally instead of falsely reporting that the new chat already received the startup prompt.
- Settings controls: native checkmarks were replaced by consistent theme/accent-aware switch buttons across the settings, memory, and terminal panels.
- Release consistency: packaging now derives its version from the extension manifest, and stale 6.25 metadata is rejected by the release gate.
- Notion AI behaviour unchanged.

## 6.26.0 hotfix — stale bridge, engine switches, script transfer, background running

- **Fixed: "Connected to bridge v6.25.0, but this process does not expose the Software Builder tools".** An older bridge process (previous download, another folder, a forgotten window) kept the port, so the new extension talked to the old bridge. Stop/Restart and `Setup.bat` only recognised a bridge started from the *same* folder, and Setup only started a bridge when the port was free. Now:
  - the launcher's **Restart/Stop** stop *any* Multi-Script bridge on the port (matched by command line, from any folder) and refuse politely (`port_busy`) when a non-Multi-Script program owns it;
  - `Setup.bat` replaces a stale bridge, starts this folder's bridge and **verifies its version**; `Start.bat` / `MacOS_Start.command` replace a stale bridge instead of leaving it;
  - the extension replaces a bridge that is older than itself automatically (max 3 tries, respects Stop) and the diagnosis names the folder the stale bridge runs from; the bridge now reports its folder and pid;
  - new `runtime/bridge_status.py` (exit 0 current / 1 none / 2 stale / 3 foreign).
- **New: Settings → Engines → Active engines.** Switch Roblox Studio, Unity, Godot or Blender on/off. A switched-off engine is not started, restarted, probed or advertised, its `ms_<engine>_*` and native tools are hidden, calls are refused with an explanation, and the choice is saved (`runtime/engine-prefs.json`).
- **Fixed: scripts arriving damaged in Roblox Studio.** `execute_luau`/code tools now repair double-escaped `\n`, markdown fences, `###LUA###` markers, BOM/zero-width characters and `lines` arrays before they reach Studio; `ms_roblox_run_luau` no longer reports success output containing the word "error" as a failure.
- **Fixed: `ms_ws_*` "JSON schema" rejections.** Numeric bounds were removed from the schemas (`max_entries` minimum 10 rejected small values); arguments are accepted as numbers, floats or strings and clamped.
- **Fixed: the agent stopped re-running/sending while Roblox Studio covered the browser.** Browsers report a covered window as hidden and the loop parked on "Paused". New setting *Keep running when the browser is covered or in the background* (ON by default) with worker-timed waits so hidden-tab timer throttling does not slow the loop.
- **Fixed: "recovery budget is spent" after two retries.** Error recovery now defaults to *Persistent* (10 retries, 20 in a row) and *Standard* is 4/8.
- Tests: `test_stale_bridge_replacement.py`, `test_engine_toggles_and_code_transport.py`.


### Hotfix: screenshots/frames on every provider, schema hardening
- `screen_capture` (and any other image-returning tool or video frame) now works on EVERY provider. Assistants that can see images still receive the picture; text-only ones (Notion AI, ChatGPT free tier, text-only Qwen/DeepSeek models ...) receive a **text visual digest** (size, tone, dominant colours, an 8x6 colour grid) instead of a hard error. The user still sees the capture in the side popup.
- The bridge now supplies `capture_id` itself when the model forgets it (Roblox rejects `screen_capture` without one).
- The Media Relay falls back to copying a text description of the photo / video frames when the site cannot take attachments.
- New `tests/test_schema_fuzz_all_tools.py` mangles a valid call for all 448 advertised tools (stringified numbers/JSON, wrong key case, wrapper envelopes, extra keys, nulls, extreme numbers) and requires the repair path to accept them.

### Hotfix: prompt enhancer asks BEFORE anything is sent; tool catalogue clean-up
- **Prompt enhancer** no longer sends your original and then a second "brief". When the enhancer is on and you press Send/Enter, that send is held (on every provider), a dialog shows your original and the improved prompt (editable), and exactly one message goes out: **Send improved prompt**, **Send my original**, or close/Esc to send nothing (your text stays in the box). With "Ask me before sending" off, the improved prompt is sent automatically *instead of* the original. The chosen message stays visible in the chat.
- **Self-healing built-in calls:** every direct tool now goes through the same repair path as engine tools (stringified numbers/JSON, `Feature` vs `feature`, `{"arguments":{…}}` / `{"params":"{…}"}` envelopes that were previously silently ignored). Repair notes are carried inside JSON results so they stay valid JSON.
- **New `ms_find_tool`**: ranked plain-language search across every tool available right now, with required parameters and a copy-ready call (saves reading the ~120k-character catalogue). **New `ms_tool_stats`**: measured calls / failures / latency per tool.
- **Catalogue clean-up:** 21 near-duplicate planner tools (e.g. `ms_performance_budget_designer`, `ms_workflow_plan`, `ms_orchestrate_request`) are no longer advertised. They remain callable and answer with the tool to prefer (`RETIRED_FROM_CATALOGUE` in `bridge.py`).
- `ms_bridge_status` now also reports pid, folder, engines switched off and advertised-tool count.

### Hotfix: optional truncation (Limits), long `execute_luau` / `multi_edit` payloads, no double-applied edits
- **New setting: Settings → Agent → Limits & truncation.** Truncation is now optional and adjustable. *Tool results* (paged with `more_output`) and *messages typed into the chat box* can each be **Automatic** (the per-site defaults, unchanged), **Custom size** (your own character cap, 5,000 – 5,000,000) or **No limit**. A third switch controls whether a command whose last closing braces were cut off by the site is auto-closed. Saved in `chrome.storage` (`msLimitSettings`) and included in the settings backup. Covers ChatGPT, Claude, Gemini, DeepSeek, Qwen, Arena and Notion AI. "No limit" can make a huge paste slow or refuse to send on some sites - that is why the defaults stay Automatic.
- Bridge side: `MS_TOOL_RESULT_LIMIT` (environment variable, default 60000, `0` = never clip) controls the cut applied to one native engine result.
- **Fixed: the real reason a large command was rejected is now reported.** "…not one complete plain-text JSON object" was one generic message for every failure. The extension now diagnoses the reply (`ZSParse.diagnose`: cut off / cut off inside a string / text after the object / curly quotes / raw line breaks / bad escapes) and tells the model exactly what happened and what to do; the diagnosis is also written to the log (`parse.diagnose`).
- **New tools for very large scripts:** `ms_stage_code` (upload code in chunks), `ms_run_staged_luau` (run the assembled code) and `ms_write_staged` (save it to a script with one `multi_edit`; refuses to apply the identical text twice within 2 minutes). No single message has to carry the whole payload.
- **Fixed: edits applied twice** (e.g. `print(1)print(1)`). The bridge used to silently re-send a mutating native call (`multi_edit`, `execute_luau`, `insert_asset`, `generate_*`, `start_stop_play`, `user_*_input`) after the server dropped mid-call, and script output that merely contained "not connected…" could trigger a retry. Mutating calls are now never re-sent automatically (the model is told to inspect state first), long output is never mistaken for a connection notice, and the extension refuses an identical appending `multi_edit` repeated within 60 seconds of a success.
- Tests: `test_limits_and_long_payloads.js`, `test_staged_and_replay_guards.py`.

### Hotfix: first-class macOS and Linux support
- **New `Setup.sh` / `Start.sh`** (bash 3.2-compatible, so they run on stock macOS and every Linux distro). `MacOS_Setup.command` / `MacOS_Start.command` remain and simply call them. Setup finds Python 3.9+ (Homebrew, python.org, distro; never triggers Apple's Xcode stub), installs `websockets` (falls back to a private `.venv` on externally-managed Pythons such as Debian 12 / Ubuntu 24.04), clears the macOS download-quarantine flag, refuses temporary/zipped/App-Translocated folders, registers the launcher, starts + verifies the bridge, and writes `logs/setup.log`. Options: `--no-start`, `--keep-running`, `--uninstall`, `--extension-id`, `--no-pause`. On Linux it also adds a "Multi-Script Bridge" application-menu entry. When no suitable Python exists it prints the exact install command for apt / dnf / pacman / zypper / apk / brew.
- **Browser registration** now covers Chrome, Chromium, Edge, Brave, Vivaldi plus Opera, Arc and the Beta/Dev/Canary builds, honours `$XDG_CONFIG_HOME`, and also registers browsers that are installed but were never started. Flatpak/Snap browsers (which cannot launch host programs) are detected and Setup tells you to use `bash Start.sh`.
- **Linux:** Roblox Studio has no Linux build, so the Roblox engine now starts switched off there (no endless "open Roblox Studio" prompts); extra Godot locations (Flatpak user exports, AppImages in `~/Applications`, `/opt/godot`, `~/.local/bin/godot4`).
- **macOS:** orphaned `StudioMCP` processes are cleaned up when Studio is closed (previously Windows only); the Studio MCP wrapper forwards SIGTERM so stopping the bridge no longer leaves `StudioMCP` running on macOS/Linux.
- `test_unix_scripts.py` runs the real scripts end-to-end in an isolated copy with a fake `$HOME` (registration, menu entry, bridge start/verify/stop, uninstall, no-Python and externally-managed-Python cases).

### Hotfix: DeepSeek "command ... not run" (its own DSML tool-call markup)
- **Fixed: a chip that just says `command`, spins, then turns grey "not run" (DeepSeek, Deep thinking).** DeepSeek sometimes writes its own tool-call tags (`<｜DSML｜invoke name="…">`). Only one spelling of those tags was understood - the one with a `>` right after the bars; the real forms (full-width bars, ASCII bars without the `>`, spaced renderings) parsed to *no call*, the tool name was unreadable (hence the chip label `command`), and nothing told the model, so the turn simply ended and nothing ran. Now every spelling is parsed and executed, a block that stopped before its closing tags still runs when all its values are complete (a value cut off mid-way never runs), the chip shows the real tool name, and an unreadable marker (e.g. a bare `<|DSML|>tool_calls>`) is answered with a clear "resend as one JSON command" message. A reply that is only a `{"command"…` object but cannot be read is also answered now, whatever the tool name.
- The "N tools" number in the status line is the catalogue loaded *for this chat right now*: it excludes the Memory tools while the chat's Memory switch is off, the Software Builder workspace tools outside a Software session, the 21 retired duplicates, and engines that are switched off or not connected. It is not a sign of a failed load.
- Test: `tests/test_dsml_native_markup.js`.

### Bridge-independent reliability hotfix

- Graph Memory now uses a canonical browser-local knowledge graph, so create, enable, recall, auto-capture, browse, graph, import/export, and all six `ms_memory_*` tools work even when the terminal bridge is offline or an older registered copy is still running.
- Engine on/off choices are now saved and enforced by the extension as well as the bridge. Disabled engine tools are removed from the AI catalogue and calls are refused immediately; an old bridge can no longer undo the switch or surface raw `unknown message type: set_engine` errors.
- Memory controls are explicit non-submit buttons and remain safe when injected inside provider composer forms.
- Memory UI now clearly identifies private local storage and gives useful failures instead of stale-bridge blocker messages.
