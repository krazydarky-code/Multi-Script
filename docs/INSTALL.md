# Install Multi-Script 6.49.9 Dev

Use the **Dev** ZIP inside the combined Bundle. Dev is the primary, current build.
The bundled Public 6.42.0 ZIP is a frozen older companion and lacks current fixes.
Extract one edition only and keep its extension and local runtime together.

## Requirements
- Windows 10/11 or macOS/Linux
- Python 3.9+
- Chromium-based browser with unpacked extensions enabled
- At least one supported editor/MCP connection

## 1. Extract everything
Do not run the launcher from inside the ZIP preview. Extract the complete `Multi-Script` folder first.

## 2. One-time setup (registers the terminal launcher)
- Windows: double-click `Setup.bat`.
- macOS: control-click `MacOS_Setup.command`, choose Open, and approve it once (or, in Terminal: `xattr -dr com.apple.quarantine . && bash Setup.sh`).
- Linux: run `bash Setup.sh`.
- No setup possible (Flatpak/Snap browser, locked-down machine)? `Start.bat` (Windows) / `MacOS_Start.command` (macOS) / `bash Start.sh` (macOS + Linux) runs the bridge in its own window.

Run this after loading the extension (step 3) so Setup can find its ID. Afterwards the **terminal icon in the
Multi-Script chat bar** starts, stops and monitors the bridge - there is no start script to keep open. The bridge
binds only to `127.0.0.1:17613`. Manual fallback: `python runtime/bridge.py`.

## 3. Load the browser extension
1. Open `chrome://extensions` or `edge://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select the extracted `Multi-Script/extension` folder.
5. Pin Multi-Script to the toolbar.


## 4. Connect an editor
Open Roblox Studio, Unity, or Godot with its MCP integration enabled. Multi-Script's Engines tab distinguishes a running server from an attached editor.

## 5. Verify
Open a supported AI site, open Multi-Script, and confirm the bridge is online. On Notion AI, use **Check selection** before starting a new chat.

## Updating
For this first manual upgrade, stop sessions/the bridge and back up the complete
existing folder. Copy the new Dev files into that same permanent folder, then
restore your private `runtime/config.json` from the backup. Keep `.env`, engine
preferences and private studio-data. Run Setup, reload the extension and refresh
provider tabs. Keep the same browser profile and extension identity. The
[update guide](UPDATES.md) gives the manual steps and the later in-extension flow.

## Keyless local audio and optional ElevenLabs setup

Local procedural sound generation works immediately with no account, network call, quota, or API key. It is the default for UI sounds, impacts, stylized effects, ambience, loops, and rapid iteration.

Optional cloud setup for more complex natural material:

1. Create an ElevenLabs API key.
2. Run `python runtime/configure_elevenlabs.py`.
3. Paste the key into the hidden terminal prompt.
4. Restart the bridge.
5. Ask the AI to create a sound effect or ambience. Multi-Script generates the file directly and imports it through the connected engine workflow.

The key remains local and must not be committed or pasted into chat. ElevenLabs quota and licensing terms apply.

## Troubleshooting: "Connected to bridge v6.25.0, but this process does not expose the Software Builder tools"

An **older bridge is still running** and holds port 17613, so the new extension is talking to the old program.

1. Click **Restart** in the message (or the terminal icon → Restart). It now stops every Multi-Script bridge on the port, including copies from other folders, and starts the current one.
2. Still there? Run `Setup.bat` from the **new** Multi-Script folder. It replaces the old bridge, re-points the browser launcher at this folder and prints the version that is really running.
3. Check by hand: `python runtime/bridge_status.py` (0 = current, 2 = stale bridge, 3 = another program owns the port).
4. Reload the extension in `chrome://extensions` and refresh the AI chat tab.

## Switching engines on/off

Settings → **Engines** → *Active engines*. A switched-off engine is not started or probed, its tools are hidden from the AI, and the choice is remembered across restarts (`runtime/engine-prefs.json`).

## Truncation, long scripts and "not one complete plain-text JSON object"

- Settings → **Agent → Limits & truncation** lets you switch result paging and the chat-box message clip to *Automatic*, a *Custom size* or *No limit*.
- A rejected command now says why (cut off after N characters, text after the object, curly quotes, raw line breaks...). A **cut off** reply means the site stopped generating - ask the model to send the code in pieces with `ms_stage_code`, then `ms_run_staged_luau` / `ms_write_staged`.
- Mutating calls (`multi_edit`, `execute_luau`...) are never re-sent automatically after a connection drop. If a result says "may or may not have been applied", read the script first.
- Debug: the extension log (`parse.diagnose`) records the kind, length and tail of every rejected reply.

## macOS and Linux details

| Topic | What happens |
|---|---|
| Python | 3.9+ is found automatically (Homebrew, python.org, distro). On macOS both Homebrew prefixes are searched - `/opt/homebrew/bin` (Apple Silicon) and `/usr/local/bin` (Intel) - plus the python.org framework build at `/Library/Frameworks/Python.framework/Versions/Current/bin`. Apple's `/usr/bin/python3` is a stub that pops an Xcode installer dialog instead of running, so it is skipped unless the Command Line Tools are actually installed (`xcode-select -p` succeeds). If Python is missing the script prints the exact install command for your distro (`apt`, `dnf`, `pacman`, `zypper`, `apk`, `brew`). |
| Dependency | `websockets` via `pip --user`; on "externally-managed-environment" systems a private `.venv` inside the Multi-Script folder; `--break-system-packages` only as a last resort. `Start.sh` / the native host reuse that `.venv` automatically. |
| Browsers | Per-user registration (no sudo): Chrome, Chromium, Edge, Brave, Vivaldi, Opera, Arc, Chrome/Edge/Brave Beta, Chrome Dev/Canary. Honours `$XDG_CONFIG_HOME`. A browser that is installed but never started is registered too. |
| Flatpak / Snap browsers | Cannot start the launcher (sandbox). Setup says so; run `bash Start.sh` instead. |
| Gatekeeper (macOS) | Setup clears the download quarantine flag on the folder (`xattr -dr com.apple.quarantine`). If macOS still refuses to open `.command`, run `bash Setup.sh` in Terminal. Setup also refuses to run from an App-Translocation / temporary path, because the browser registration would break as soon as the folder is cleaned. |
| Moved folder | Run `Setup.sh` again from the new location; it re-points the browser registration and replaces any bridge still running from the old one. |
| Uninstall | `bash Setup.sh --uninstall` removes the registrations and the Linux menu entry. |
| Port busy | `ZS_BRIDGE_PORT=17620 bash Setup.sh` (and the same variable for `Start.sh`). To find the holder: `lsof -nP -iTCP:17613 -sTCP:LISTEN`. |
| Stopping the bridge | `Ctrl+C`, or any `SIGTERM` (including the automatic stale-bridge replacement). The bridge now shuts its MCP children down on `SIGTERM`/`SIGHUP`, so `StudioMCP` and the `uvx`/`npx` servers are not left holding their ports. |
| Windows | `Start.bat` / `Setup.bat` still do their own thing (no `.sh` needed). |
| Logs | `logs/setup.log`, `logs/start.log`, `logs/bridge_stdout.log`, `runtime/logs/bridge_debug.log`. |
| Runtime state that must not ship | `runtime/engine-prefs.json` (which engines *this* machine disabled), `runtime/native_host.*` and `runtime/com.multiscript.bridge.json` are gitignored and never bundled. `runtime/config.json` **does** ship - it is the default that declares the four engine MCP servers. |
| Wayland (Linux) | Window enumeration uses `wmctrl` on X11, and falls back to `swaymsg` (Sway/i3) or `hyprctl` (Hyprland). Other compositors (GNOME, KDE) expose no portable window list, so windows degrade to process names and the result is explicitly marked `degraded: true` rather than guessed. |
| Roblox Studio | macOS: supported - the launcher looks for `StudioMCP` inside `RobloxStudio.app`, `Roblox.app` and the `Beta` bundles, under `/Applications` and `~/Applications`. Linux: no Studio build exists, so the Roblox engine starts switched off (unless you point `ZS_STUDIO_MCP_PATH` at one). |

For this revamp, use either the Dev or Public full package and load its extension/ directory. Store-only packaging is not supplied; both ZIPs include the bridge. See the root README for edition limits and upgrade steps.

## Optional phone control

Open the separate phone icon or Settings → Co-work → Phone control. Enable it on your trusted local network, open the displayed address on your phone and pair with the one-use code. Keep the desktop awake and browser connected. See [phone setup, controls and limits](PHONE_CONTROL.md).

## Updating later

Keep the permanent folder and browser profile. Stop active sessions, then use Settings → Help → Updates → Apply & reload extension and refresh provider tabs. This build pins the official GitHub feed/public key. Install it manually once if upgrading from an older or unconfigured version; later updates use [the in-extension flow](UPDATES.md). Never uninstall or delete settings to update.
