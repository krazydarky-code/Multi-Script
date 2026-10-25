# Multi-Script 6.17.4 - Load Regression Fix

**Released:** 2026-09-30
**Supersedes:** 6.17.3 (do not ship - total blackout)

## The bug

On **every** supported site - arena.ai, DeepSeek, ChatGPT, Gemini, Kimi, GLM,
Meta, Qwen, Notion - the extension loaded and then did nothing. No panel, no
Start button, no menu. Not a partial failure: **no UI at all**.

6.17.3 added this near the top of `extension/core/main.js`:

```js
let verificationSettings = ZSVerify.DEFAULT_SETTINGS;
A.verifyState = ZSVerify.initialState();   // ← `const A = {…}` is ~170 lines BELOW
A.verifyCount = 0;
```

`const` and `let` are **hoisted but not initialized**. Between the top of the
scope and the declaration line, the binding sits in the *temporal dead zone*,
and any read *or write* throws:

```
ReferenceError: Cannot access 'A' before initialization
```

Because this ran at top level of the content-script IIFE, the throw happened
before any UI was built. The whole IIFE aborted, every time, on every site.

## The fix

The two fields now live **inside** the `A` literal, where they belong and where
they are guaranteed initialized before anything touches them:

```js
const A = {
  …
  verifyState: ZSVerify.initialState(),
  verifyCount: 0,
};
```

No behaviour changed. The verification assistant works exactly as designed in
6.17.3 - this only repairs the wiring that prevented it from loading at all.

## Why the test suite missed it

`node --check` parses `main.js` **fine**. A temporal-dead-zone error is a
*runtime* condition, not a syntax error. It only appears when the code is
**evaluated**, and specifically when the concatenated content-script chain is
evaluated in **one shared scope** - which is exactly how Chrome runs multiple
`content_scripts` entries on the same page.

The previous suite always loaded modules **individually** (via
`new Function(src + ';return X;')`), so a cross-file TDZ error was structurally
invisible.

## New regression gate

`tests/test_content_script_load_contract.js` closes that hole. It:

1. reads `extension/manifest.json` and, for **every** `content_scripts` block,
   concatenates its `js` files in order and evaluates them in a single shared
   `vm` context with a DOM shim - the faithful model of how Chrome loads them;
2. asserts **no block throws at load time** (this is the test that would have
   caught 6.17.3 before shipping);
3. includes a **deliberate TDZ probe** and asserts it *does* throw, proving the
   load check cannot pass vacuously;
4. statically asserts `core/main.js` performs no **top-level** `A.<field> = …`
   assignment before `const A = {` (depth-tracked, so a nested assignment inside
   a function body is correctly ignored);
5. asserts the `A` literal still declares `verifyState` / `verifyCount`;
6. asserts every block loading `core/main.js` also loads `core/verification.js`
   (which `main.js` dereferences at load);
7. verifies `core/verification.js` exposes its full export surface standalone.

It is wired into `.github/workflows/ci.yml` and enforced by
`tools/release_check.py`, which now also fails the build on a top-level
pre-declaration `A` assignment.

## Verified

- All **11** manifest blocks load clean, across all 9 providers.
- Re-introducing the two offending lines reproduces
  `Cannot access 'A' before initialization`; removing them loads clean -
  causality confirmed, not assumed.
- `tools/release_check.py` → PASS (800 skills, 57 JS files, manifest + docs).
- Full node and python suites green.

## Upgrade note

If you installed 6.17.3, **update to 6.17.4**. There is no setting you can
toggle to work around 6.17.3 - the script never finished loading.
