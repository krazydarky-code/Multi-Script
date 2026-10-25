# Multi-Script 6.29.1 — repair release

Fixes the regressions introduced while hand-editing 6.29.0 ("connection errors,
most tools don't run anymore") and makes the SuperApp provider bundle-grounded again.

## Fixed
- **Tools / connection (the main bug).** `extension/background.js` declared
  `const URL = "ws://127.0.0.1:…"`, which shadows the global `URL` class inside the
  service worker. Every `new URL(...)` (surface tools, page/workspace tools, link
  handling) threw `URL is not a constructor`, so most tools failed and the worker
  reported bridge/connection errors. Renamed back to `BRIDGE_URL`; the regression
  test that guarded this (deleted in 6.29.0) is restored.
- **Setup restarts the bridge again** even when the running one has the same
  version (files may change without a version bump). `--keep-running` still opts
  out. Restored the Edge Dev/Canary, Brave Nightly, Vivaldi Snapshot, Thorium and
  Chrome for Testing native-host registrations.
- **macOS / Linux launchers.** Executable bits restored (lost when the folder was
  zipped on Windows); `MacOS_*.command` clear the quarantine flag and fix
  permissions before delegating again; `Start.sh` exits with a message when a
  foreign process holds the bridge port instead of continuing; `Linux_Setup.sh` /
  `Linux_Start.sh` restored.
- **Line endings.** 21 source files had been converted to CRLF (breaks shebangs and
  produces noisy diffs). Normalised to LF; `.bat` files stay CRLF.

## SuperApp provider
- Back on the selectors taken from the shipped superapp.chat web bundle
  (`rich-message-input` testIDs, tiptap `.eti-editor .ProseMirror`, RN `<textarea>`,
  "Send" label, structural message list ordered by screen position, sent-text
  ledger for user-turn ownership, open message-edit composer ignored).
- Kept from 6.29.0: every read-only export is no-throw, `diagnostics()` report,
  sign-in gate detection (`ensureComposerReady` → `needsAuth`, `scanError` explains it).
- `tests/test_superapp_provider.js` now also runs real headless Chromium against
  bundle-shaped DOMs (textarea + rich composer, inverted list, full send → reply round trip).

## Kept from 6.29.0
All bridge improvements (diagnostics endpoint, POSIX process handling, signal
forwarding in launchers, platform-aware Setup/Start wording) are unchanged.

## Not live-tested
SuperApp with a signed-in account (no account available); Windows/macOS runs.
