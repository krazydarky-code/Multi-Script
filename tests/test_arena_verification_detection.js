// SPDX-License-Identifier: GPL-3.0-or-later
// Headless verification of Arena's bot-check DETECTION.
//
// The Playwright gate (tests/test_arena_human_verification.js) is the real-browser
// check, but it cannot run without a browser download. This test covers the same
// logic with a tiny hand-rolled DOM instead, so the detection rules are verified
// on every machine and in CI without any dependency:
//   - a genuinely interactive challenge is detected (widget AND text probe);
//   - Arena's ALWAYS-present hidden reCAPTCHA v3 badge is NOT (the regression
//     that used to hide the bar on every page);
//   - tiny, off-screen, oversized and in-chat matches are NOT;
//   - nothing in the file solves, token-injects, outsources or bypasses a
//     challenge, and the guard strings the release gate requires are present.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const src = fs.readFileSync(path.join(root, 'extension/providers/arena.js'), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };

// ── Minimal DOM ───────────────────────────────────────────────────────────
// Only what arena.js's detection path touches: tag/id/class/attribute matching
// (including [attr*="x" i] and one `parent > child` level), closest(), ancestor
// computed styles, bounding rects and viewport bounds.
const VIEW = { w: 1200, h: 800 };
function matchesSimple(el, sel) {
  let rest = sel.trim();
  const tagM = /^([a-zA-Z][\w-]*)/.exec(rest);
  if (tagM) {
    if (el.tagName !== tagM[1].toUpperCase()) return false;
    rest = rest.slice(tagM[1].length);
  }
  const tokenRe = /(#[\w-]+)|(\.[\w-]+)|(\[[^\]]+\])/g;
  let t;
  while ((t = tokenRe.exec(rest))) {
    const tok = t[0];
    if (tok[0] === '#') { if (el.id !== tok.slice(1)) return false; continue; }
    if (tok[0] === '.') { if (!el.classes.has(tok.slice(1))) return false; continue; }
    const am = /^([\w-]+)\s*(\*?=)?\s*"([^"]*)"\s*(i?)$/.exec(tok.slice(1, -1));
    if (!am) return false;
    const [, name, op, val, flags] = am;
    const actual = el.getAttribute(name);
    if (actual == null) return false;
    if (op === '*=') {
      const a = flags === 'i' ? actual.toLowerCase() : actual;
      const b = flags === 'i' ? val.toLowerCase() : val;
      if (!a.includes(b)) return false;
    } else if (op === '=' && actual !== val) return false;
  }
  return true;
}
function matchesCompound(el, compound) {
  const parts = compound.split('>').map((s) => s.trim());
  if (parts.length === 2) {
    return matchesSimple(el, parts[1]) && !!el.parentElement && matchesSimple(el.parentElement, parts[0]);
  }
  return parts.length === 1 ? matchesSimple(el, compound) : false;
}
const matchesAny = (el, sel) => sel.split(',').map((s) => s.trim()).filter(Boolean).some((s) => matchesCompound(el, s));

class El {
  constructor(tag, opts = {}) {
    this.tagName = tag.toUpperCase();
    this.id = opts.id || "";
    this.classes = new Set(opts.classes || []);
    this.attrs = Object.assign({}, opts.attrs);
    this.children = [];
    this.parentElement = null;
    this.text = opts.text || "";
    this.rect = opts.rect || { width: 300, height: 90, top: 20, left: 20, bottom: 110, right: 320 };
    this.cs = Object.assign({ display: "block", visibility: "visible", opacity: "1" }, opts.cs);
  }
  get childElementCount() { return this.children.length; }
  get className() { return [...this.classes].join(" "); }
  get innerText() { return this.text || this.children.map((c) => c.innerText).filter(Boolean).join("\n"); }
  get isConnected() { return true; }
  getAttribute(n) {
    if (n === "class") return [...this.classes].join(" ");
    if (n === "id") return this.id || null;
    return n in this.attrs ? this.attrs[n] : null;
  }
  setAttribute(n, v) { this.attrs[n] = String(v); }
  getBoundingClientRect() { return this.rect; }
  getClientRects() { return this.rect.width ? [this.rect] : []; }
  appendChild(c) { c.parentElement = this; this.children.push(c); return c; }
  closest(sel) { let n = this; while (n) { if (matchesAny(n, sel)) return n; n = n.parentElement; } return null; }
  querySelectorAll(sel) {
    const out = [];
    const walk = (n) => { for (const c of n.children) { if (matchesAny(c, sel)) out.push(c); walk(c); } };
    walk(this);
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
function makeDocument() {
  const html = new El("html");
  const body = new El("body", { rect: { width: 1200, height: 800, top: 0, left: 0, bottom: 800, right: 1200 } });
  html.appendChild(body);
  const doc = {
    documentElement: html, body,
    querySelector: (s) => html.querySelector(s),
    querySelectorAll: (s) => html.querySelectorAll(s),
  };
  return doc;
}
// Load arena.js exactly as the extension does, with the DOM stubbed in.
function loadProvider(doc) {
  const fn = new Function(
    "document", "window", "location", "getComputedStyle", "innerWidth", "innerHeight", "localStorage",
    src + "\nreturn ZSProvider;"
  );
  return fn(
    doc,
    { HTMLTextAreaElement: function () {}, HTMLInputElement: function () {} },
    { pathname: "/text/direct", href: "https://arena.ai/text/direct", search: "", hash: "" },
    (el) => el.cs,
    VIEW.w, VIEW.h,
    { getItem: () => null, setItem: () => {}, removeItem: () => {} }
  );
}
const fresh = () => { const d = makeDocument(); return { doc: d, P: loadProvider(d) }; };

// ── 1. A clean page has no challenge ─────────────────────────────────────
{
  const { P } = fresh();
  ok(P.detectChallenge() === null, 'a clean page must report no challenge');
  ok(P.captchaPresent() === false, 'captchaPresent must be false on a clean page');
  ok(P.verificationHint() === "", 'verificationHint must be empty on a clean page');
}

// ── 2. The hidden reCAPTCHA v3 badge is NOT a challenge ──────────────────
// Arena keeps a 256x60 .grecaptcha-badge in the DOM at all times with
// visibility:hidden. Treating it as a challenge hid the bar on every page.
{
  const { doc, P } = fresh();
  doc.body.appendChild(new El("div", {
    classes: ["grecaptcha-badge"], attrs: { "data-sitekey": "x" },
    cs: { visibility: "hidden" }, rect: { width: 256, height: 60, top: 700, left: 900, bottom: 760, right: 1156 },
  }));
  ok(P.captchaPresent() === false, 'a visibility:hidden reCAPTCHA badge must not count as a challenge');
  // Same badge with opacity:0 (another way sites hide it).
  const { doc: d2, P: p2 } = fresh();
  d2.body.appendChild(new El("div", { classes: ["grecaptcha-badge"], cs: { opacity: "0" } }));
  ok(p2.captchaPresent() === false, 'an opacity:0 badge must not count as a challenge');
  // And a display:none wrapper anywhere up the chain.
  const { doc: d3, P: p3 } = fresh();
  const wrap = new El("div", { cs: { display: "none" } });
  d3.body.appendChild(wrap);
  wrap.appendChild(new El("div", { classes: ["cf-turnstile"] }));
  ok(p3.captchaPresent() === false, 'a challenge inside a display:none wrapper must not count');
}

// ── 3. Size and viewport gates ───────────────────────────────────────────
{
  const { doc, P } = fresh();
  doc.body.appendChild(new El("div", { classes: ["cf-turnstile"], rect: { width: 30, height: 20, top: 10, left: 10, bottom: 30, right: 40 } }));
  ok(P.captchaPresent() === false, 'a tiny widget must not count as a challenge');
  const { doc: d2, P: p2 } = fresh();
  d2.body.appendChild(new El("div", { classes: ["cf-turnstile"], rect: { width: 300, height: 90, top: -400, left: 20, bottom: -310, right: 320 } }));
  ok(p2.captchaPresent() === false, 'an off-screen (scrolled-away) widget must not count');
  const { doc: d3, P: p3 } = fresh();
  d3.body.appendChild(new El("div", { classes: ["cf-turnstile"], rect: { width: 300, height: 90, top: 20, left: 1400, bottom: 110, right: 1700 } }));
  ok(p3.captchaPresent() === false, 'a widget past the right edge must not count');
}

// ── 4. Real challenges ARE detected, and the kind is identified ──────────
const widgetCases = [
  ['div', { classes: ['cf-turnstile'] }, 'cloudflare-turnstile'],
  ['div', { classes: ['cf-challenge-running'] }, 'cloudflare-turnstile'],
  ['iframe', { attrs: { src: 'https://challenges.cloudflare.com/turnstile/v0/api.js' } }, 'cloudflare-turnstile'],
  ['iframe', { attrs: { src: 'https://newassets.hcaptcha.com/captcha/v1/x' } }, 'hcaptcha'],
  ['div', { classes: ['h-captcha'] }, 'hcaptcha'],
  ['iframe', { attrs: { src: 'https://www.google.com/recaptcha/api2/anchor' } }, 'recaptcha'],
  ['div', { classes: ['g-recaptcha'] }, 'recaptcha'],
  ['iframe', { attrs: { src: 'https://iframe.arkoselabs.com/x/fc/gc' } }, 'arkose'],
  ['iframe', { attrs: { src: 'https://geo.captcha-delivery.com/captcha/' } }, 'datadome'],
  ['iframe', { attrs: { src: 'https://captcha.px-cdn.net/px/captcha' } }, 'perimeterx'],
  ['div', { classes: ['geetest_holder'] }, 'geetest'],
  ['div', { attrs: { 'data-testid': 'captcha-widget' } }, 'embedded-challenge'],
  ['div', { id: 'captcha-container' }, 'embedded-challenge'],
];
for (const [tag, opts, expectKind] of widgetCases) {
  const { doc, P } = fresh();
  doc.body.appendChild(new El(tag, opts));
  const d = P.detectChallenge();
  ok(d, `challenge not detected: ${tag} ${JSON.stringify(opts)}`);
  ok(d.kind === expectKind, `wrong kind for ${tag} ${JSON.stringify(opts)}: got ${d.kind}, want ${expectKind}`);
  ok(typeof d.hint === 'string' && d.hint.length > 0, 'a detected challenge must carry a human hint');
  ok(P.captchaPresent() === true, 'captchaPresent must agree with detectChallenge');
  ok(P.verificationHint().length > 0, 'verificationHint must be populated when a challenge is present');
}

// ── 5. The TEXT probe catches a reskin with no known class ───────────────
{
  const { doc, P } = fresh();
  doc.body.appendChild(new El('div', {
    attrs: { role: 'dialog' }, text: 'Verify you are human\nComplete the security check to continue.',
    rect: { width: 420, height: 220, top: 200, left: 380, bottom: 420, right: 800 },
  }));
  const d = P.detectChallenge();
  ok(d && d.kind === 'text-challenge', `text interstitial not detected (${d && d.kind})`);
  ok(d.hint.includes('Verify you are human'), 'the hint must quote the on-screen wording');
}
// French wording, and a plain Cloudflare interstitial.
for (const text of ['Veuillez vérifier que vous êtes humain', 'Checking your browser before accessing arena.ai', 'Just a moment...', 'Unusual traffic from your network']) {
  const { doc, P } = fresh();
  doc.body.appendChild(new El('div', { attrs: { role: 'alertdialog' }, text, rect: { width: 400, height: 180, top: 120, left: 400, bottom: 300, right: 800 } }));
  ok(P.detectChallenge(), `text interstitial not detected: "${text}"`);
}

// ── 6. False-positive guards on the text probe ───────────────────────────
{
  // (a) The phrase inside a chat turn (the model quoting it) must NOT count.
  const { doc, P } = fresh();
  const list = new El('ol', { classes: ['flex-col-reverse'] });
  doc.body.appendChild(list);
  const turn = new El('div', { attrs: { role: 'dialog' }, text: 'Verify you are human', rect: { width: 500, height: 100, top: 300, left: 300, bottom: 400, right: 800 } });
  list.appendChild(turn);
  ok(P.captchaPresent() === false, 'a challenge phrase inside the chat list must not count as a challenge');
  // (b) A whole page of prose containing the phrase must NOT count.
  const { doc: d2, P: p2 } = fresh();
  const page = new El('div', { attrs: { role: 'dialog' } });
  page.text = 'Verify you are human is a common phrase. '.repeat(20);
  d2.body.appendChild(page);
  ok(p2.captchaPresent() === false, 'an over-long text block must not count as a challenge');
  // (c) A check card buried in our own UI must NOT count.
  const { doc: d3, P: p3 } = fresh();
  const zs = new El('div', { id: 'zs-root' });
  d3.body.appendChild(zs);
  zs.appendChild(new El('div', { attrs: { role: 'dialog' }, text: 'Verify you are human', rect: { width: 400, height: 200, top: 100, left: 100, bottom: 300, right: 500 } }));
  ok(p3.captchaPresent() === false, "Multi-Script's own UI must never be read as a challenge");
  // (d) Ordinary dialog copy must NOT count.
  const { doc: d4, P: p4 } = fresh();
  d4.body.appendChild(new El('div', { attrs: { role: 'dialog' }, text: 'Delete this page?', rect: { width: 400, height: 200, top: 100, left: 100, bottom: 300, right: 500 } }));
  ok(p4.captchaPresent() === false, 'an ordinary dialog must not count as a challenge');
}

// ── 7. The no-bypass contract is intact ──────────────────────────────────
const lower = src.toLowerCase();
for (const forbidden of ['2captcha', 'capsolver', 'captcha token', 'grecaptcha.execute', 'contentwindow.postmessage', 'anti-captcha', 'deathbycaptcha']) {
  ok(!lower.includes(forbidden), `a challenge-bypass implementation appeared: ${forbidden}`);
}
for (const required of ['waitForHumanVerification', 'humanVerificationRequired', 'does not bypass verification challenges', 'detectChallenge', 'verificationHint']) {
  ok(src.includes(required), `the verification guard/API is missing: ${required}`);
}
ok(/never (?:interact with it|attempted)/i.test(src), 'the no-interaction comment must remain in the provider');

console.log(`PASS Arena bot-check detection (headless): clean page, hidden badge, size/viewport gates, ${widgetCases.length} challenge widgets + 4 interstitial wordings detected, 4 false-positive guards, no bypass implementation`);
