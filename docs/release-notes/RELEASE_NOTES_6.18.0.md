# Multi-Script 6.18.0 — "Anchor"

Two fixes, one theme: **things that were floating free are now properly anchored.**

## The settings menu was sliding off the left of the screen

> *"bro its MISALLIGNED, half of the settings menu is out the edge of the screen, cant you see?"*

You were right, and the first thing worth saying is what the bug actually *was* — because the obvious
reading of the symptom points the wrong way.

`#zs-root` is the extension's host element. It is `position: fixed` with **no inset**, so it pins
itself at the viewport origin `(0,0)` and every child that is in normal flow is laid out against the
*viewport* — not against the bar, not against the composer.

`#zs-menu` was `position: relative`. So it sat in that flow, and a `right:` on it measured the gap to
the **screen's** right edge.

Meanwhile the placement code in `placeBar()` fed it this:

```js
menuEl.style.right = Math.round(window.innerWidth - br.right) + "px";
```

…where `br` is the **bar's** bounding rect. On a wide composer the bar stops well short of the right
edge of the window — that gap is the page gutter, a few hundred pixels. So the panel was told to sit
*"the width of the page gutter"* in from the screen's right edge, and then its own 370px of flow width
pushed it further left again. Nothing clamped it. Half the panel went off-screen, exactly as the
screenshot showed.

The tell was that the **bar itself was always fine** — a width probe rendered it cleanly at 720 / 560 /
480 / 400px, truncating gracefully every time. The bar was never the problem; the menu was measuring
against the wrong box.

### What changed

- **The popover is now genuinely viewport-fixed.** `#zs-menu` is `position: fixed`, so a `right:` on it
  means what the placement code already computes — distance to the viewport edge — instead of being
  reinterpreted by a flow-positioned ancestor.
- **One placement helper replaced four copies.** The math was duplicated in all four branches of
  `placeBar()` (in-flow mount, anchored, detached float, editor-float), each independently setting
  `right` / `bottom` / `maxHeight`. They now all call a single `placeMenu(anchorRight, anchorTop)`.
- **Both edges are clamped.** The panel hugs the anchor's right edge *and* is clamped into the
  viewport, so it can never leave the screen regardless of where the composer sits — left-of-centre,
  full-bleed, or on a 360px-wide window.
- **Width is clamped to the viewport too.** The configured width (310 / 370 / 440 / 520px) is capped at
  `100vw - 16px`, and the later `#zs-root #zs-menu` rule — which was re-widening it back to a raw
  370px and defeating the earlier clamp — now clamps as well.
- **Height follows the space actually available** above the anchor, with a 140px floor.

`tools/render_menu_probe.js` replays the real CSS and the real math across nine geometries — including
a deliberately absurd gutter, a 360px viewport and a bar pushed to the far left — and asserts the
panel's left edge is never negative. 39/39 checks.

## Notion AI: hardened detection, ported from upstream GPL source

upstream GPL source (1.18.74) is a derivative of Multi-Script with a considerably more mature Notion adapter —
2,492 lines against our 466. The parts worth taking were the detection and transcript logic, so those
were merged in; the IDE and `.exe` were left alone.

**Adopted:**

- **A route-surface guard.** Only `/ai` and `/chat/…` are AI surfaces. This is the single most valuable
  thing in the file: it is what stops the adapter from ever typing into a normal Notion page editor.
- **A scored, memoised editor resolver** with negative caching, ranking candidates on tag, editability,
  placeholder text and the presence of a nearby send control. A bare search input scores ~4; a real
  composer clears the threshold of 9.
- **Exact live control selectors** (`agent-send-message-button` / `agent-chat-send-button`) and dual
  transcript anchors, so detection survives Notion's hashed class names.

**Corrected on merge** — the ported logic was too strict in three places, and each one would have made
the adapter *worse* than the file it replaced:

- **The route guard was rejecting surfaces it should accept.** `openAIChat()` returned early whenever
  the guard matched, so if the guard passed but the scorer could not yet qualify the editor — a
  late-mounting composer, a shadow-hosted one — the recovery action silently did nothing. There is now
  an explicit-open override, armed *only* by a deliberate action (`init()` or `openAIChat()`), never
  from ambient page state, and cleared on a real navigation. The guard keeps its teeth; the explicit
  request now gets an answer.
- **Shadow DOM broke both the scorer and the frame resolver.** `parentElement` walks stop dead at a
  shadow host, so a composer inside one could not see its own `<form>` or Send button and never cleared
  the score threshold. Both walks now climb through the host chain.
- **The transcript lost its legacy path.** The ported `rawAgentRows()` only knew the new
  `data-agent-service-scroll-anchor`; builds using the `data-testid` message pattern would have shown an
  empty conversation. Anchored rows are still preferred, with the block structure and then the
  semantic-turn selector as fallbacks.
- **`ready` required `contenteditable="true"`.** Notion ships `plaintext-only`, so a perfectly usable
  composer reported not-ready.

`selfTest()` now reports the effective surface alongside the raw guard result
(`routeGuardMatched` / `explicitOpen`), so a misdetection is diagnosable from the panel instead of
being a silent `false`.

## Also in this release

- The Roblox Studio companion plugin, the bridge, and every versioned surface move to 6.18.0.
- `tools/validate_6_18_0_artifacts.py` now also asserts the popover invariants — viewport-fixed,
  width-clamped, and no rule reverting it to flow positioning — so the misalignment cannot come back
  unnoticed.
