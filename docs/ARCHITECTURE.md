# Multi-Script architecture

```
AI chat site  ──(extension content script)──►  local bridge (runtime/bridge.py)  ──►  Roblox Studio / Unity / Godot / Blender
     ▲                                                     │                         └► Software workspace (runtime/software_workspace.py)
     └────────────── tool results pasted back ◄────────────┘
```

* **extension/core/config.js** – markers (`⟦MS-SYS⟧`), rules prompt, settings defaults,
  provider benchmark rows and the per-provider usage-optimizer entries.
* **extension/core/main.js** – bar UI, settings panel, session start, tool-call parsing, `runTool` (with result paging / `more_output`), the `AI_SITES` list the site menu renders.
* **extension/core/extras.js** – game-idea generator, Software Builder prompt, extra themes, background helpers.
* **extension/providers/*.js** – per-site adapters (find composer, send, read reply). Optional `resultCharBudget` / `resultLineBudget` enable paging. `promptql.js` is the reference adapter; `superapp.js` is the fully defensive one (candidate-selector table + structural fallback + a `diagnostics()` report), because superapp.chat ships a hashed Expo/RNW bundle.
* **runtime/bridge.py** – HTTP/WebSocket bridge; built-in tools, engine MCP proxies, multi-engine routing via `_server`. Serves `GET /diagnostics` (version, ports, uptime, per-server state and last error, disabled engines, catalogue sizes, environment probe, log tail) and classifies every tool failure into a stable `errorInfo.code`.
* **runtime/software_workspace.py** – `ms_ws_*` tools for the Software Builder (root-jailed file ops, run/build, snapshots, zip).
* **runtime/bridge_status.py** – status/diagnosis client; `--json` prints the full `/diagnostics` report, the human mode adds a per-server line.

Provider registration is **five places** and all five must agree or the provider is dead:
`extension/manifest.json` (`host_permissions` **and** a `content_scripts` block),
`extension/background.js` (`PROVIDER_URLS`), `extension/popup.js` (`SUPPORTED_HOSTS`),
`extension/core/main.js` (`AI_SITES`), and `extension/core/config.js`
(`PROVIDER_BENCHMARKS` row + `PROVIDER_ECONOMY` entry).

Flow: the AI writes a JSON tool call → the content script detects it → POSTs to the bridge → result (paged if long) is typed back into the chat.
