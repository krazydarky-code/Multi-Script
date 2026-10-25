# Multi-Script 6.29.0

This release is about **correctness off Windows**. macOS and Linux were supported
on paper, but several code paths only ever really ran on Windows. They now do.

## macOS

- **Roblox Studio's MCP port is no longer called a squatter.** `_port_owner_posix`
  returned an empty executable path and `check_studio_port` decided "is this
  Roblox?" from that path alone — so on a healthy Mac it reported Studio's own
  process as a foreign program and either asked you to kill it or told you to
  close it yourself, on every boot. The probe now returns the real executable
  path (`ps -p <pid> -o comm=`) and the check matches on the process name too.
- **Zombie `StudioMCP` recovery actually runs.** Three helpers killed the port
  holder with an unguarded `taskkill`, which does not exist on macOS, so the
  exception was swallowed and the zombie kept the port. They now use
  `SIGTERM` on POSIX, and `_descendant_pids` has a POSIX implementation (it was
  Windows-only, which made the ownership guard inert).
- **Stopping the bridge no longer orphans its MCP children.** The bridge had no
  `SIGTERM`/`SIGHUP` handler at all, so any `kill` left `StudioMCP`, `uvx` and
  `npx` servers running and holding ports. It now shuts its clients down
  properly.
- **Blender / Unity / Godot launchers forward signals** like the Studio launcher
  already did — previously the wrapper died and the real `uvx`/`npx` server was
  orphaned.
- **Studio detection tries every bundle name** the launcher accepts
  (`RobloxStudio`, `RobloxStudioBeta`, `Roblox`), not just the first.
- **Unity Editor is detected again** in the Running tab (the matcher only knew
  `unity.exe` / `unity hub`, never the macOS process name `Unity`).
- **The "open desktop apps" list is no longer empty.** The friendly-name map was
  keyed on `*.exe`, so on macOS and Linux every process was filtered out.

## Linux

- **The bundled `runtime/engine-prefs.json` is no longer shipped.** It recorded
  which engines *the packager's machine* had disabled — so new users got Unity,
  Godot and Blender switched off. Worse, its presence defeated the
  "Roblox Studio has no Linux build, start with it off" auto-disable, which only
  fires when the file is absent, producing a crash-loop with repeated
  "open your place in Roblox Studio" prompts. `native_host.bat`/`.sh` and
  `com.multiscript.bridge.json` (which bake in an absolute interpreter path) are
  gitignored too. `runtime/config.json` still ships — it is the default that
  declares the four engine servers, not user state.
- **Wayland is documented honestly.** Window enumeration uses `wmctrl`, which is
  X11-only; the degraded result is now labelled instead of silently returning
  process-derived pseudo-titles.

## Bridge

- **New `/diagnostics` route** — version, ports, uptime, platform, per-server
  state (with each server's last error), which engines are switched off on *this*
  machine, the environment probe (uvx / npx / Blender add-on), the catalogue
  sizes and the log tail, in one request. `bridge_status.py --json` fetches it;
  the normal status output now also prints the per-server line, so "which engine
  is down, and why" no longer needs a console screenshot.
- **Structured tool errors.** Every failed call now carries an `errorInfo` block
  with a stable code (`timeout`, `server_disconnected`, `unknown_tool`,
  `engine_disabled`, `invalid_arguments`, `permission_denied`, `tool_error`),
  whether retrying could plausibly help, and the tool that failed. The existing
  `error` / `kind` keys are untouched, so nothing that reads them changes.
- **Per-server timeouts.** `mcpServers.<id>.timeout_sec` in `config.json` gives
  one slow server (a big Unity project, a remote HTTP server) more room without
  raising the timeout for every other server. Clamped to 1–3600 s.
- **`tools/list_changed` is honoured.** A server that hot-adds or removes a tool
  now has its cache invalidated and re-listed. Previously the notification was
  dropped, so the agent kept calling tools that no longer existed and could not
  see new ones at all.

## New provider: SuperApp (superapp.chat)

- Full DOM content-script adapter (`extension/providers/superapp.js`) with the
  complete provider contract: turn detection, reply reading, composer control,
  send/stop, error scanning and the tool-block spot.
- The SuperApp web client is an Expo / React Native Web bundle behind Auth0 whose
  class names are hashed at build time, so the adapter is written **defensively**:
  every lookup is a candidate list tried in order, ending in a structural
  heuristic that only needs the visible shape of a chat page (a scrollable
  transcript plus a `contenteditable` composer). A selector miss records itself
  and moves on — it never throws.
- **Two things the test suite forced out of the design.** RNW puts the role hook
  on the row element *itself* (`message-row-user`), not only on a descendant, so
  role detection now tests the node as well as its subtree. And when *nothing* on
  the page carries a role marker, the adapter reports an honest `userCount()` of 0
  and treats every markerless turn as assistant-owned rather than inventing
  human/model turns by alternation — reply extraction is the only thing
  Multi-Script truly needs from a turn.
- A `diagnostics()` report (plus the auth-gate probe) says exactly which candidate
  matched, which fell through, and what the page actually looked like, so an
  unverified site is debuggable in the field instead of failing silently.
- Registered in all five places (manifest `host_permissions` + `content_scripts`,
  `background.js` `PROVIDER_URLS`, `popup.js` `SUPPORTED_HOSTS`, `core/main.js`
  `AI_SITES`, `core/config.js` benchmark row + usage-optimizer entry), and added
  to the cross-provider tool matrix.

## Housekeeping

- Version bumped to 6.29.0 across the manifest, bridge, product manifest, Roblox
  plugin, Notion adapter and README.
- `tests/test_unix_scripts.py` no longer fails on Windows. Two separate problems
  were fixed: the executable-bit check (Windows cannot represent the bit) is
  skipped there only, and the POSIX integration section — which executes
  `bash Setup.sh`, registers a native-messaging host and calls `os.killpg` — now
  exits cleanly with a clear message instead of raising `AttributeError`. Both
  checks stay fully strict on Linux and macOS.
- `tests/test_stale_bridge_replacement.py` no longer fails a correct bridge on a
  machine with a long `%TEMP%`. The assertion tested for the substring
  `bridge.py` inside `native_host._short()`'s *display-truncated* 140-character
  command string, which cuts the filename off on a deep temp path; it now asserts
  the real signal (a bridge holding our port from a folder that is not ours).
- New `tests/test_superapp_provider.js` drives the adapter against four synthetic
  DOMs (explicit hooks / fully hashed / auth gate / empty) and asserts the
  degraded path in each, plus complete registration — so the unverified site can
  never regress into a thrown exception.
- CI now runs the verification job on **both** `ubuntu-latest` and
  `macos-latest`, so the macOS-only paths above are actually exercised.
