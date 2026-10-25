// SPDX-License-Identifier: GPL-3.0-or-later
// Content-script LOAD contract regression.
//
// 6.17.3 shipped a total blackout: on every site (arena.ai, DeepSeek, ChatGPT,
// Gemini, Kimi, GLM, Meta, Qwen, Notion) NOTHING mounted - no panel, no Start
// button. The cause was a temporal-dead-zone ReferenceError:
//
//     let verificationSettings = ZSVerify.DEFAULT_SETTINGS;
//     A.verifyState = ZSVerify.initialState();   // <-- `const A` declared ~170
//     A.verifyCount = 0;                          //     lines LATER
//
// `const`/`let` are hoisted but stay in the temporal dead zone until their
// declaration executes, so reading OR writing a property on `A` before
// `const A = {…}` runs throws `Cannot access 'A' before initialization`. The
// whole content-script IIFE dies, every provider, before any UI exists.
//
// A syntax check (`node --check`) does NOT catch this - the file parses fine.
// Only EVALUATING the concatenated chain in one shared scope does, which is
// exactly what Chrome does with multiple content_scripts. This test does that.
//
// It also guards a second class of bug: any top-level statement that touches a
// later-declared binding, not just `A`. The TDZ proof below is generic.
const fs = require('fs'), path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };

let passed = 0;
const t = (name, fn) => { fn(); passed++; console.log('  ok  ' + name); };

// ── Minimal DOM/browser shims ────────────────────────────────────────────
// Enough for the modules' LOAD-TIME bodies (they read chrome.runtime, arm
// timers, and inspect a few prototypes). Deliberately thin: this is a
// load-order test, not a DOM test.
function makeStyle() {
  return new Proxy({}, {
    get: (o, k) => (k === 'setProperty' || k === 'removeProperty' || k === 'getPropertyValue')
      ? () => '' : (o[k] !== undefined ? o[k] : ''),
    set: (o, k, v) => { o[k] = v; return true; },
  });
}
function makeEl() {
  const el = {
    style: makeStyle(), dataset: {},
    classList: { add() {}, remove() {}, contains() { return false; }, toggle() {} },
    appendChild() { return el; }, replaceChildren() {}, append() {}, prepend() {}, insertBefore() {}, replaceChild() {}, removeChild() {},
    setAttribute() {}, getAttribute() { return null; }, removeAttribute() {}, hasAttribute() { return false; },
    addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; }, remove() {},
    querySelector() { return makeEl(); }, querySelectorAll() { return []; },
    attachShadow() { return makeEl(); }, cloneNode() { return makeEl(); },
    focus() {}, blur() {}, click() {}, scrollIntoView() {},
    getBoundingClientRect: () => ({ top: 0, left: 0, right: 0, bottom: 0, width: 100, height: 20, x: 0, y: 0 }),
    get firstChild() { return null; }, get lastChild() { return null; },
    get childNodes() { return []; }, get children() { return []; },
    get parentNode() { return null; }, get nextSibling() { return null; },
    innerHTML: '', textContent: '', innerText: '', value: '', checked: false,
    hidden: false, disabled: false, id: '', tagName: 'DIV', offsetWidth: 100, offsetHeight: 20,
  };
  return el;
}

function buildShims() {
  const rootEl = makeEl();
  rootEl.documentElement = rootEl;
  const sandbox = {};
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.console = console;
  sandbox.location = { hostname: 'arena.ai', href: 'https://arena.ai/c/test', origin: 'https://arena.ai' };
  sandbox.addEventListener = () => {};
  sandbox.removeEventListener = () => {};
  sandbox.setTimeout = () => 0;
  sandbox.clearTimeout = () => {};
  sandbox.setInterval = () => 0;
  sandbox.clearInterval = () => {};
  sandbox.requestAnimationFrame = () => 0;
  sandbox.cancelAnimationFrame = () => {};
  sandbox.performance = { now: () => Date.now(), mark() {}, measure() {} };
  sandbox.getComputedStyle = () => makeStyle();
  sandbox.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
  sandbox.document = {
    hidden: false, readyState: 'loading', title: 'Arena', cookie: '',
    documentElement: rootEl, head: makeEl(), body: makeEl(),
    createElement: () => makeEl(), createElementNS: () => makeEl(),
    createTextNode: () => makeEl(), createDocumentFragment: () => makeEl(),
    getElementById: () => makeEl(), querySelector: () => makeEl(), querySelectorAll: () => [],
    addEventListener: () => {}, removeEventListener: () => {}, execCommand: () => true,
  };
  sandbox.chrome = {
    runtime: {
      getManifest: () => ({ version: '6.17.4' }), id: 'test',
      onMessage: { addListener() {} },
      sendMessage: (m, cb) => { if (cb) cb({}); },
      lastError: null, getURL: (p) => p,
    },
    storage: { local: { get: (k, cb) => { if (cb) cb({}); }, set() {}, remove() {} }, onChanged: { addListener() {} } },
    i18n: { getMessage: (k) => k },
  };
  sandbox.MutationObserver = class { observe() {} disconnect() {} takeRecords() { return []; } };
  sandbox.ResizeObserver = class { observe() {} disconnect() {} };
  sandbox.IntersectionObserver = class { observe() {} disconnect() {} unobserve() {} };
  sandbox.CustomEvent = class { constructor(t, o) { this.type = t; Object.assign(this, o || {}); } };
  sandbox.Event = class { constructor(t) { this.type = t; } };
  sandbox.MouseEvent = class { constructor(t, o) { this.type = t; Object.assign(this, o || {}); } };
  sandbox.KeyboardEvent = sandbox.MouseEvent;
  sandbox.PointerEvent = sandbox.MouseEvent;
  sandbox.DOMParser = class { parseFromString() { return makeEl(); } };
  sandbox.XMLHttpRequest = class { open() {} send() {} setRequestHeader() {} addEventListener() {} };
  sandbox.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('') });
  sandbox.AudioContext = class {
    constructor() { this.state = 'running'; this.destination = {}; this.currentTime = 0; }
    createOscillator() { return { connect() {}, start() {}, stop() {}, frequency: { setValueAtTime() {}, value: 440 }, type: 'sine' }; }
    createGain() { return { connect() {}, gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {}, linearRampToValueAtTime() {}, value: 1 } }; }
    resume() { return Promise.resolve(); }
  };
  for (const n of ['Element', 'HTMLElement', 'Node', 'HTMLTextAreaElement', 'HTMLInputElement',
                   'HTMLDivElement', 'HTMLButtonElement', 'HTMLAnchorElement', 'HTMLImageElement', 'HTMLIFrameElement']) {
    sandbox[n] = class {};
  }
  for (const p of [sandbox.HTMLTextAreaElement, sandbox.HTMLInputElement]) {
    Object.defineProperty(p.prototype, 'value', {
      get() { return this._v || ''; }, set(v) { this._v = v; }, configurable: true,
    });
  }
  sandbox.HTMLElement.prototype.attachShadow = function () { return makeEl(); };
  return sandbox;
}

// Load one manifest block the way Chrome does: separate <script> files, but a
// SINGLE shared top-level scope. Concatenating into one evaluated program is the
// faithful model - separate top-level `const`s in one scope, which is what makes
// a cross-file TDZ error possible in the first place.
function loadBlock(blockIndex) {
  const manifest = JSON.parse(read('extension/manifest.json'));
  const files = manifest.content_scripts[blockIndex].js;
  const parts = files.map((f) => {
    const full = path.join(root, 'extension', f);
    ok(fs.existsSync(full), `manifest references a missing file: ${f}`);
    return '/*==== ' + f + ' ====*/\n' + fs.readFileSync(full, 'utf8');
  });
  const src = parts.join('\n;\n');
  const sandbox = buildShims();
  const ctx = vm.createContext(sandbox);
  // new Function-style eval inside the context, sharing one scope.
  vm.runInContext('(function(){\n' + src + '\n})();', ctx, { filename: 'block-' + blockIndex + '.js' });
  return { files, ctx };
}

// ── 1. Every site block loads without a load-time throw ──────────────────
// This is the test that would have caught 6.17.3 before it shipped.
const manifest = JSON.parse(read('extension/manifest.json'));
const blocks = manifest.content_scripts;

t('every content_scripts block loads in one shared scope (no TDZ / no throw)', () => {
  for (let i = 0; i < blocks.length; i++) {
    const js = blocks[i].js || [];
    // Blocks that only inject a tiny standalone helper do not load core/main.js;
    // they are still load-checked for their own sake.
    let err = null;
    try { loadBlock(i); } catch (e) { err = e; }
    ok(!err, `content_scripts[${i}] (${js.join(' -> ')}) threw at load: ${err && err.message}`);
  }
});

// ── 2. The 6.17.3 regression, reproduced and pinned ──────────────────────
// Prove that touching a later-declared const at top level DOES throw in this
// harness - otherwise the passing test above would be vacuous.
t('the harness actually detects a top-level TDZ violation (guard is not vacuous)', () => {
  const sandbox = buildShims();
  const ctx = vm.createContext(sandbox);
  let threw = false;
  try {
    vm.runInContext('(function(){ A.x = 1; const A = { y: 2 }; })();', ctx, { filename: 'tdz-probe.js' });
  } catch (e) { threw = /before initialization/i.test(e.message); }
  ok(threw, 'harness failed to reproduce a deliberate TDZ error - the load test cannot be trusted');

  // And the exact shape 6.17.3 shipped (assign before `const A`).
  const sb2 = buildShims();
  const ctx2 = vm.createContext(sb2);
  let threw2 = false;
  try {
    vm.runInContext('(function(){ const V = { initialState: () => ({}) }; A.verifyState = V.initialState(); const A = {}; })();', ctx2, { filename: 'tdz-probe2.js' });
  } catch (e) { threw2 = /before initialization/i.test(e.message); }
  ok(threw2, 'the 6.17.3 bug shape no longer reproduces - update this test');
});

// ── 3. main.js never assigns to A before A is declared ───────────────────
// A focused, source-level guard so the failure is attributable even if the
// harness is ever changed. Only TOP-LEVEL statements execute during load;
// an `A.x = …` inside a function body is harmless because the function runs
// long after `const A` initialized. So we track brace depth and only flag a
// depth-0 assignment (the IIFE body is depth 1), which is exactly the shape
// that executed at load time in 6.17.3.
t('core/main.js binds no top-level A.<field> before `const A = {`', () => {
  const lines = read('extension/core/main.js').split('\n');
  let declLine = -1;
  for (let i = 0; i < lines.length; i++) {
    if (/^\s*const A = \{/.test(lines[i])) { declLine = i; break; }
  }
  ok(declLine >= 0, 'core/main.js no longer declares `const A = {` - test needs updating');

  const offenders = [];
  let depth = 0;
  for (let i = 0; i < declLine; i++) {
    const raw = lines[i];
    // Strip line comments and string/template literals loosely so braces and
    // prose inside them cannot skew the depth count or fake a match.
    const code = raw
      .replace(/\/\/.*$/, '')
      .replace(/'(?:[^'\\]|\\.)*'/g, "''")
      .replace(/"(?:[^"\\]|\\.)*"/g, '""')
      .replace(/`(?:[^`\\]|\\.)*`/g, '``');
    // The IIFE wrapper `(() => {` opens depth 1; a statement at depth 1 is a
    // top-level statement OF the IIFE body - which is what executes at load.
    if (depth === 1 && /^\s*A\.[A-Za-z_$][\w$]*\s*=/.test(code)) offenders.push(`${i + 1}: ${raw.trim()}`);
    for (const ch of code) { if (ch === '{') depth++; else if (ch === '}') depth--; }
  }
  ok(offenders.length === 0,
    'top-level assignment to A before `const A` is declared (temporal dead zone - this kills the whole script):\n    ' +
    offenders.join('\n    '));
});

// ── 4. verification state is wired through the A literal ─────────────────
// The fix moved these two fields into the A literal; keep them there.
t('A literal declares verifyState and verifyCount', () => {
  const src = read('extension/core/main.js');
  const block = src.slice(src.indexOf('const A = {'), src.indexOf('const A = {') + 4000);
  ok(/verifyState:\s*ZSVerify\.initialState\(\)/.test(block), 'A.verifyState is not initialized in the A literal');
  ok(/verifyCount:\s*0/.test(block), 'A.verifyCount is not initialized in the A literal');
});

// ── 5. every block that loads core/main.js also loads core/verification.js ─
t('any block loading core/main.js also loads core/verification.js', () => {
  for (let i = 0; i < blocks.length; i++) {
    const js = blocks[i].js || [];
    if (js.includes('core/main.js')) {
      ok(js.includes('core/verification.js'),
        `content_scripts[${i}] loads core/main.js but not core/verification.js (main.js dereferences ZSVerify at load)`);
    }
  }
});

// ── 6. core/verification.js can be loaded standalone ─────────────────────
t('core/verification.js defines ZSVerify in one evaluated scope', () => {
  const sandbox = buildShims();
  const ctx = vm.createContext(sandbox);
  const v = vm.runInContext(
    '(function(){' + read('extension/core/verification.js') + '; return ZSVerify; })()', ctx,
    { filename: 'verification.js' });
  ok(v && typeof v === 'object', 'verification.js did not expose ZSVerify');
  // Functions.
  for (const k of ['initialState', 'noteChallenge', 'noteClean',
                   'extraDelayMs', 'escalationActions', 'sanitize', 'modeFor', 'describe']) {
    ok(typeof v[k] === 'function', `ZSVerify.${k} is missing`);
  }
  // Value exports (main.js dereferences DEFAULT_SETTINGS at load time - a
  // missing one here is what produced the 6.17.3 ReferenceError surface).
  for (const k of ['MODES', 'DEFAULT_SETTINGS', 'SLOWDOWN', 'LADDER', 'COPY']) {
    ok(v[k] && typeof v[k] === 'object', `ZSVerify.${k} is missing or not an object`);
  }
  ok(typeof v.DEFAULT_SETTINGS.mode === 'string', 'DEFAULT_SETTINGS.mode is not a string');
  const st = v.initialState();
  ok(st && typeof st === 'object' && 'floorMs' in st, 'initialState() shape changed');
});

console.log(`\ntest_content_script_load_contract: ${passed} sections passed`);
