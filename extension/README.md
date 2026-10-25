# Multi-Script browser extension 6.41.0

This folder is the browser half of Multi-Script. It adds the control center to supported AI chat sites and communicates with the local loopback bridge.

## Install from the full release
1. Extract the complete Multi-Script release.
2. Run `Setup.bat` / `MacOS_Setup.command` once, then use the terminal icon in the chat bar to start the bridge.
3. Open `chrome://extensions` or `edge://extensions`.
4. Enable Developer mode and choose **Load unpacked**.
5. Select this `extension` folder.

See [`../docs/INSTALL.md`](../docs/INSTALL.md) for the full editor/MCP setup.

## Store package

## Privacy and safety
The extension stores preferences locally and connects to `127.0.0.1`. Read [`../docs/PRIVACY.md`](../docs/PRIVACY.md) and [`../docs/SECURITY.md`](../docs/SECURITY.md) before publishing.

## Development
Provider adapters live in `providers/`; shared parsing, prompting, UI, and session behavior live in `core/`. Run `node test-parser.js` here and `python tools/release_check.py` from the project root before packaging.

For this revamp, use either the Dev or Public full package and load its extension/ directory. Store-only packaging is not supplied; both ZIPs include the bridge. See the root README for edition limits and upgrade steps.
