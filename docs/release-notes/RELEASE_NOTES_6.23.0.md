# Multi-Script 6.23.0 — "Studio"

A terminal that lives in the chat bar, a settings menu you can actually navigate, and a theme
system the interface now genuinely obeys.

---

## The terminal icon now opens a terminal, in the page

The chat bar's terminal button used to be a *button that asked another process to start*. It now
opens a **terminal panel directly under the icon** — a top-down menu showing exactly what the bridge
is doing, streamed live, without leaving the chat.

- **A live log stream.** Every line the bridge writes — engine connects, MCP handshakes, tool calls,
  errors — arrives as it happens, colour-coded, with a filter bar (`All / Info / OK / Warn / Error`).
- **Per-engine service chips** showing whether each server is up and how many tools it advertises.
- **A truthful status dot and pill** — `live` / `partial` / `offline` — driven by the real connection
  state, never a guess.
- **Copy / Clear / Follow.** Clear empties the *view ring* only; `bridge_debug.log` on disk stays
  complete.
- **Autoscroll that respects you.** It follows new lines only while you are already at the bottom,
  so scrolling up to read history is never yanked away.

### Two channels, one renderer, no gaps

1. **The authenticated WebSocket** (preferred). The bridge keeps a bounded ring buffer
   (`deque(maxlen=600)`) with a monotonic sequence number and pushes new records to every subscribed
   socket in batched frames. A **cursor** makes an idle poll a no-op instead of a re-read.
2. **A loopback HTTP fallback** on port `17614` (`GET /logs?since=N`). When the socket is quiet the
   panel polls this instead, so the dot and the chips stay truthful *mid-reconnect*.

The panel keeps its own cursor, and a **bridge restart resets it**. That sounds like a detail; it is
the difference between a working terminal and one that silently appears frozen forever. The bridge
process restarts independently, and its sequence counter begins again at `1` — so a cursor left over
from the previous run points *past the end of the new ring*. The worker detects the reconnect,
broadcasts a reset, and the panel forgets what it had and re-reads. Both directions are now pinned
by tests.

### Why it shows you the command instead of spawning it

**A content script has no process API.** That is a browser guarantee, not an obstacle to route
around — a page that could spawn a process could spawn anything. So the panel's **Start bridge**
action puts the real `start.bat` command on your clipboard, explains the limitation in one plain
line, and then **watches for the bridge to answer**, reporting the moment it comes up. It never
claims to have started something it did not.

**This is why `start_launcher.bat` and `runtime/bridge_launcher.py` are gone.** That pairing needed a
second always-on localhost process, a token file on disk, and a handshake just to work around a
browser rule. Showing the command is simpler, has no attack surface, and cannot drift out of sync
with the bridge it describes. Every dangling reference — the `launcher_pair` frame, the launcher
tests, the release-note section — was removed with it.

---

## The theme bug: tokens that were never defined

The panel was written against `--ms-surface`, `--ms-ink` and `--ms-ink-3`. Those names were
**referenced in about thirty rules and defined nowhere.** Every one of those rules silently fell back
to its hardcoded hex, which meant:

- the panel **stayed dark in light mode**, because it never consulted the light ramp; and
- changing your theme or accent **did not restyle it at all** — the exact opposite of the intent.

The fix is one alias block: the `--ms-*` names now resolve to the `--mono-*` ramp, which light mode
and every named theme already redefine. The panel became theme-aware with **no JavaScript and no
per-theme CSS**, and the nine different fallback greys for a single token were collapsed to one.

The status hues are the deliberate exception. "Live" must read green and "error" must read red *under
any accent*, so those are fixed colours rather than accent-derived ones — a decision, not an
oversight.

---

## The settings menu: from one catch-all to seven named tabs

Thirteen sections had accumulated in a single **Agent** tab, in the order they happened to be
written, with *Appearance* — the thing people reach for most — buried in the middle. That is why the
menu felt disorganised: it was.

The tabs are now named for what they control:

| Tab | What lives there |
|---|---|
| **Setup** | the guided start, links, first-run checklist |
| **Appearance** | theme, accent, layout, identity, media relay |
| **Agent** | how the model behaves — provider behaviour, creative routing, skill coverage, autonomy, verification, error recovery, pacing |
| **Interface** | how a request is shaped — prompt enhancer, execution effort, surface vision, usage optimiser, audio |
| **Engines** | MCP servers, connections, addons |
| **AI sites** | provider switcher and benchmarks |
| **Help** | support, backup, troubleshooting, explainers |

Every section is assigned to exactly one real tab, and a test now fails if a section is ever left on
a tab that no longer exists — which would make it invisible rather than obviously broken.
The **default-tab preference** accepts all seven (it silently rejected the new ones at first — a real
bug the regroup exposed), and the tab strip uses `auto-fit` so it stays full at any count or width
instead of leaving a ragged row.

---

## Everything else

- **The request guard actually guards.** The panel's re-entrancy check cleared its own in-flight
  marker synchronously, so it never worked; overlapping refreshes could resolve out of order and let
  an older cursor overwrite a newer one. Now the promise is held until it settles.
- **Log lines are rendered as text, never as HTML.** They carry model and engine output, so building
  them with `innerHTML` would be an injection path. A test feeds the panel a hostile line and asserts
  it is displayed verbatim and never executed.
- **`--ms-*` token definitions, the settings regroup, and every terminal invariant** are pinned by
  `tools/validate_6_23_0_artifacts.py`.
- **`tests/test_terminal_panel.js`** drives the real panel class in a real browser: backlog, the
  incremental cursor, push dedupe, the level filter, clear-vs-reset semantics, autoscroll behaviour,
  request coalescing, and cleanup on close.

## Verification

| Suite | Result |
|---|---|
| Python (`tests/test_*.py`) | **33 passed, 0 failed** |
| JS (`tests/*.js`) | **46 passed, 0 failed** |
| Terminal panel, behavioural (`test_terminal_panel.js`) | **30 assertions passed** |
| Facade + panel contract (`test_native_facade.py`) | **101 assertions passed** |
| Schema audit | **260 schemas, 0 high-severity, 0 sentinel drift** |
| 6.23.0 artifact validator | **see `tools/validate_6_23_0_artifacts.py`** |

The `/logs` fallback was exercised against the real asyncio handler: `200` with
`{ok, lines, newest, service}`, and unknown paths `404` rather than crashing.
