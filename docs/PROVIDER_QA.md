# Provider QA — Multi-Script 6.30.0

Supported AI websites: Arena, ChatGPT, Claude, DeepSeek, Gemini, GLM, Kimi, Meta AI,
Notion AI, PromptQL, Qwen, and SuperApp.

The automated matrix executes four supported command envelopes for each of **230**
direct Multi-Script tools on every provider contract, then tests four namespaced MCP
probes per provider — **11,088 parser/tool-routing envelopes** across **12** adapters —
in addition to the malformed-input fuzz cases, generic round trips, provider adapter
loading, bridge handler coverage, and engine-specific tests. Two adapters
(`chatgpt-cm`, `qwen-net`) run in the page's MAIN world by design and are parse-checked
rather than driven; the other ten are loaded with a stubbed DOM and asserted against the
full 38-member interface floor (`tests/test_provider_interface_628.js`).

Arena received a live public-page smoke test on `/text/direct`: Direct mode, composer,
Max selector, file control, and send control were present. Full account-bound model
execution can vary by login, quota, model, region, and live anti-abuse checks.

## SuperApp (superapp.chat) — defensive adapter

SuperApp's web client is an Expo / React Native Web bundle behind Auth0 whose class
names are hashed at build time, so its adapter cannot rely on any literal selector
surviving a deploy. It is written to **degrade, not throw**:

- Every lookup is an **ordered candidate list** (`SEL` in `extension/providers/superapp.js`)
  followed by a structural heuristic that only needs the visible shape of a chat page —
  a scrollable transcript plus a `contenteditable` (or `textarea`) composer. A miss is
  recorded and skipped; no path throws.
- A turn's role marker is looked for **on the row itself and in its subtree**, because
  RNW commonly puts the hook on the row (`message-row-user`) rather than on a child.
- When *no* role marker exists anywhere, the adapter reports an honest `userCount()` of
  `0` and treats every markerless turn as assistant-owned. It never fabricates human /
  model turns by alternation — reply extraction is the only thing Multi-Script truly
  needs from a turn.
- `diagnostics()` returns which candidate matched each slot, which fell through, every
  probe's live match count, and the current page state (editor kind, turn counts,
  auth-gate presence, conversation key). Copy it from the terminal panel when reporting
  a SuperApp issue — it is the difference between "it does not work" and a fix.
- If the Auth0 gate is on screen instead of the composer, `ensureComposerReady()`
  reports `needsAuth` and `scanError()` says so in plain words instead of silently
  failing every send.

`tests/test_superapp_provider.js` drives the adapter against four synthetic DOMs —
explicit `data-testid` hooks, a fully hashed page, an auth gate, and an empty page — and
asserts the correct degraded behaviour plus registration in all five places. Because the
site is unverified against a signed-in session, that test is what guarantees a future DOM
change can never turn a miss into a thrown exception.

## Platform coverage

6.29.0 added a `macos-latest` leg to CI next to `ubuntu-latest`, so the POSIX code paths
are actually exercised rather than merely present: Roblox Studio detection by bundle name,
port ownership resolved from the process name, signal-driven teardown of the bridge and
its MCP children, OS-aware engine preferences, and desktop window enumeration that
degrades honestly on Wayland. `tests/test_studio_port_posix.py`,
`tests/test_engine_prefs_platform.py`, `tests/test_bridge_diagnostics.py` and
`tests/test_desktop_vision.py` gate that split and run on both legs.

## CAPTCHA and bot checks

Multi-Script does not bypass or solve challenges. When a supported site displays a
visible Cloudflare Turnstile, hCaptcha, or reCAPTCHA challenge, Multi-Script hides its
overlays, pauses startup/sending, lets the user complete the challenge, and resumes after
it clears. Hidden reCAPTCHA badges do not trigger a false pause.
