// SPDX-License-Identifier: GPL-3.0-or-later
// SuperApp provider contract test (6.29.1).
//
// Part A (no browser, tiny fake DOM): the adapter must NEVER throw on a page it
// does not recognise - sign-in gate and empty page - and it must be registered
// in all five places.
// Part B (real headless Chromium, when available): DOM shapes taken from the
// shipped superapp.chat web bundle (1.212.0) - the legacy RN <textarea>
// composer and the rich tiptap composer (data-testid="rich-message-input",
// .eti-editor .ProseMirror), "Name 10:01 AM" row headers, date separators, an
// inverted (column-reverse) list, an open message-edit composer that must be
// ignored, and a full send -> reply round trip with sent-text ledger ownership.
const fs = require('fs'), path = require('path'), vm = require('vm');
const root = path.resolve(__dirname, '..');
const src = fs.readFileSync(path.join(root, 'extension/providers/superapp.js'), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };

// ── a tiny DOM good enough for querySelector / closest / innerText ───────────
let SEQ = 0;
function el(tag, attrs = {}, children = [], text = "") {
  const node = {
    tagName: tag.toUpperCase(), nodeType: 1, _id: ++SEQ,
    attrs: { ...attrs }, children: [], parentElement: null,
    classList: { _s: new Set(String(attrs.class || "").split(/\s+/).filter(Boolean)),
      contains(c) { return this._s.has(c); }, add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); } },
    style: {}, scrollHeight: 400,
  };
  Object.defineProperty(node, "className", { get: () => [...node.classList._s].join(" "), set: (v) => { node.classList._s = new Set(String(v).split(/\s+/).filter(Boolean)); } });
  node.childNodes = [];
  // Text lives in real TEXT nodes, not just a `textContent` property: the
  // adapter (like every other one) walks childNodes to strip reasoning/UI
  // chrome out of a turn, so the fixture must imitate that shape.
  Object.defineProperty(node, "textContent", {
    get: () => node.childNodes.map((c) => (c.nodeType === 3 ? c.nodeValue : c.textContent)).join(""),
    set: (v) => {
      node.childNodes = node.childNodes.filter((c) => c.nodeType !== 3);
      if (v !== "" && v != null) node.childNodes.unshift({ nodeType: 3, nodeValue: String(v), parentElement: node });
    },
  });
  Object.defineProperty(node, "innerText", { get: () => node.textContent });
  node.getAttribute = (k) => (k in node.attrs ? node.attrs[k] : null);
  node.setAttribute = (k, v) => { node.attrs[k] = String(v); };
  node.removeAttribute = (k) => { delete node.attrs[k]; };
  node.hasAttribute = (k) => k in node.attrs;
  node.appendChild = (c) => { c.parentElement = node; node.children.push(c); node.childNodes.push(c); return c; };
  node.click = () => { node._clicked = true; };
  node.focus = () => { node._focused = true; };
  node.dispatchEvent = () => true;
  node.getBoundingClientRect = () => ({ width: 320, height: 120, top: 10, left: 10, bottom: 130, right: 330 });
  for (const c of children) node.appendChild(c);
  if (text !== "") node.textContent = text;
  node.contains = function (o) { let p = o; while (p) { if (p === this) return true; p = p.parentElement; } return false; };
  node.closest = function (sel) { let p = this; while (p) { if (matches(p, sel)) return p; p = p.parentElement; } return null; };
  node.querySelectorAll = function (sel) { const out = []; walk(this, (n) => { if (n !== this && matches(n, sel)) out.push(n); }); return out; };
  node.querySelector = function (sel) { const a = this.querySelectorAll(sel); return a.length ? a[0] : null; };
  node.matches = function (sel) { return matches(this, sel); };
  return node;
}
function walk(root, fn) { for (const c of root.children) { fn(c); walk(c, fn); } }

// Minimal CSS matcher: comma groups, descendant combinators, tag / .class /
// [attr] / [attr*="v"] / [attr="v" i] / :not(). Enough for the adapter's table.
function matches(node, sel) {
  if (!node || node.nodeType !== 1) return false;
  return sel.split(",").map((s) => s.trim()).filter(Boolean).some((one) => matchChain(node, one));
}
function matchChain(node, sel) {
  const parts = sel.split(/\s+(?![^\[]*\])/).filter(Boolean);
  let cur = node;
  for (let i = parts.length - 1; i >= 0; i--) {
    if (!matchSimple(cur, parts[i])) return false;
    if (i > 0) { cur = cur.parentElement; if (!cur) return false; }
  }
  return true;
}
function matchSimple(node, s) {
  if (!node || node.nodeType !== 1) return false;
  const notMatch = s.match(/:not\(([^)]*)\)/);
  const core = s.replace(/:not\([^)]*\)/g, "");
  if (notMatch && matchSimple(node, notMatch[1])) return false;
  const attrRe = /\[([^\]]+)\]/g; let m;
  while ((m = attrRe.exec(core))) {
    const body = m[1];
    const ci = /\si$/.test(body);
    let k, op, v;
    const eq = body.match(/^([\w-]+)(\*?=)(.*)$/);
    if (eq) { k = eq[1]; op = eq[2]; v = eq[3].replace(/^["']|["']$/g, ""); }
    else { k = body.replace(/\s*i$/, ""); op = ""; }
    const have = node.getAttribute(k);
    if (have === null) return false;
    if (op === "=") { if (ci ? have.toLowerCase() !== v.toLowerCase() : have !== v) return false; }
    else if (op === "*=") {
      const h = ci ? have.toLowerCase() : have, n = ci ? v.toLowerCase() : v;
      if (!h.includes(n)) return false;
    }
  }
  const tag = core.match(/^([a-zA-Z][\w-]*)/);
  if (tag && node.tagName !== tag[1].toUpperCase()) return false;
  const cls = [...core.matchAll(/\.([\w-]+)/g)].map((x) => x[1]);
  for (const c of cls) if (!node.classList.contains(c)) return false;
  if (tag || cls.length || attrRe.lastIndex !== 0 || /\[/.test(core)) return true;
  return !core;
}

// ── build the four DOMs ─────────────────────────────────────────────────────
function domRich() {
  const body = el("body");
  const list = el("div", { role: "log", class: "scroller" });
  const u = el("div", { "data-testid": "message-row-user" }, [], "hello there");
  const a = el("div", { "data-testid": "message-row-assistant" });
  const md = el("div", { class: "markdown-body" }, [], "Sure. Running the tool now.");
  a.appendChild(md);
  list.appendChild(u); list.appendChild(a);
  const comp = el("div", { "data-testid": "composer" });
  const ed = el("div", { contenteditable: "true", role: "textbox" }, [], "");
  comp.appendChild(ed);
  comp.appendChild(el("button", { "data-testid": "send-button" }));
  body.appendChild(list); body.appendChild(comp);
  return body;
}
function domHashed() {
  // No data-testid anywhere: only the structural shape of a chat page.
  const body = el("body");
  const wrap = el("div", { class: "x1a2b3c scroller", style: {} });
  wrap.scrollHeight = 900;
  const r1 = el("div", { class: "r1 a b" }, [], "user question text");
  const r2 = el("div", { class: "r2 c d" }, [], "assistant answer text");
  wrap.appendChild(r1); wrap.appendChild(r2);
  const bar = el("div", { class: "x9z8y7 inputBarLike" });
  const ed = el("div", { contenteditable: "true" }, [], "");
  bar.appendChild(ed);
  body.appendChild(wrap); body.appendChild(bar);
  return body;
}
function domAuthGate() {
  const body = el("body");
  body.appendChild(el("input", { type: "email", name: "email" }));
  body.appendChild(el("div", { id: "auth0-lock-container" }, [], "Sign in to SuperApp"));
  return body;
}

function sandboxFor(body) {
  const listeners = [];
  const document = {
    body, documentElement: body,
    querySelector: (s) => body.querySelector(s),
    querySelectorAll: (s) => body.querySelectorAll(s),
    addEventListener: (t, fn) => listeners.push([t, fn]),
    createRange: () => ({ selectNodeContents() {}, setStart() {}, setEnd() {} }),
    execCommand: () => true,
  };
  const sb = {
    console,
    document,
    window: { getSelection: () => ({ removeAllRanges() {}, addRange() {} }), HTMLTextAreaElement: { prototype: { value: "" } }, HTMLInputElement: { prototype: { value: "" } } },
    navigator: { userAgent: "test" },
    location: { href: "https://superapp.chat/chat/abc", pathname: "/chat/abc" },
    File: function () {}, DataTransfer: function () { this.items = { add() {}, length: 0 }; this.setData = () => {}; this.files = []; },
    ClipboardEvent: function () {}, KeyboardEvent: function () {}, Event: function () {}, CustomEvent: function () {},
    MutationObserver: function () { this.observe = () => {}; },
    getComputedStyle: () => ({ display: "block", visibility: "visible", overflowY: "auto" }),
    requestAnimationFrame: () => 0, setTimeout: () => 0, setInterval: () => 0,
    clearTimeout: () => {}, clearInterval: () => {}, atob: () => "",
    Element: function () {}, Node: function () {}, URL, Intl,
  };
  sb.globalThis = sb;
  return sb;
}
function load(body) {
  const sb = sandboxFor(body);
  vm.createContext(sb);
  vm.runInContext(src + "\n;globalThis.__P = ZSProvider;", sb);
  return sb.__P;
}

// ── 3. auth gate: no composer, honest degraded report ───────────────────────
{
  const P = load(domAuthGate()); P.init({ diag: () => {} });
  ok(P.getEditor() === null, "auth: there really is no composer");
  let threw = false;
  try { P.readAssistant(); P.allItems(); P.snapshot(); P.stopGeneration(); P.setInputLock(true); P.enforceComposer(); P.clickRetry(); P.clearAttachments(); } catch (e) { threw = true; }
  ok(!threw, "auth: no getter throws on a composer-less page");
  const d = P.diagnostics();
  ok(d.state.hasEditor === false, "auth: diagnostics says no editor");
  ok(d.state.authGate === true, "auth: diagnostics flags the auth gate");
  ok(/signed out|session expired/i.test(P.scanError()), "auth: scanError explains the gate, got " + JSON.stringify(P.scanError()));
  console.log("  ok  auth-gate DOM: ready:false, authGate flagged, zero throws");
}

// ── 4. empty DOM: every export is safe to call ──────────────────────────────
{
  const P = load(el("body")); P.init({ diag: () => {} });
  const floor = ["allItems", "assistantCount", "userCount", "chatIsEmpty", "isFreshChat", "classifyText",
    "clickContinueBtn", "clickRetry", "composerFrame", "barAnchor", "conversationKey", "editorText",
    "enforceComposer", "findContinueBtn", "findToolBlockSpot", "getEditor", "isAssistantItem",
    "isBusyMsg", "isBusyNow", "isGenerating", "isHardGenerating", "isTooLongMsg", "isUserItem",
    "itemText", "lastAssistant", "lastAssistantId", "readAssistant", "scanError", "snapshot",
    "streamLen", "turnHalted"];
  for (const m of floor) {
    ok(typeof P[m] === "function", "empty: missing " + m);
    let err = null;
    try { P[m](); } catch (e) { err = e; }
    ok(!err, "empty: " + m + "() threw: " + (err && err.message));
  }
  ok(P.allItems().length === 0, "empty: no turns");
  ok(P.chatIsEmpty() === true, "empty: chat is empty");
  ok(P.getEditor() === null, "empty: no editor");
  ok(P.timings && P.timings.RESPONSE_TIMEOUT_MS > 0, "empty: timings present");
  ok(typeof P.promptExtra === "string" && /ONE command per reply/.test(P.promptExtra), "empty: promptExtra contract");
  console.log("  ok  empty DOM: all 31 safe-call members return without throwing");
}

// ── 5. registration is complete in all five places ─────────────────────────
{
  const manifest = JSON.parse(fs.readFileSync(path.join(root, "extension/manifest.json"), "utf8"));
  ok(manifest.host_permissions.some((h) => /superapp\.chat/.test(h)), "manifest host_permissions");
  const blocks = manifest.content_scripts.filter((b) => b.js.includes("providers/superapp.js"));
  ok(blocks.length === 1, "exactly one content_scripts block");
  ok(blocks[0].matches.every((m) => /superapp\.chat/.test(m)), "block matches superapp.chat");
  ok(blocks[0].js.includes("core/main.js"), "core/main.js in the block");
  ok(blocks[0].js.indexOf("providers/superapp.js") < blocks[0].js.indexOf("core/main.js"), "adapter before main");
  const bg = fs.readFileSync(path.join(root, "extension/background.js"), "utf8");
  ok(/PROVIDER_URLS = \[[^\]]*superapp\.chat/.test(bg), "background.js PROVIDER_URLS");
  const popup = fs.readFileSync(path.join(root, "extension/popup.js"), "utf8");
  ok(/SUPPORTED_HOSTS = \[[\s\S]*?"superapp\.chat"/.test(popup), "popup.js SUPPORTED_HOSTS");
  const main = fs.readFileSync(path.join(root, "extension/core/main.js"), "utf8");
  ok(/name: "SuperApp"/.test(main), "core/main.js AI_SITES");
  const cfg = fs.readFileSync(path.join(root, "extension/core/config.js"), "utf8");
  ok(/"?id"?\s*:\s*"superapp"/.test(cfg) && /superapp:/.test(cfg), "core/config.js benchmarks + economy");
  console.log("  ok  registered in manifest, background, popup, main AI_SITES, config");
}


// ── Part B: real Chromium against bundle-shaped DOMs ────────────────────────
(async () => {
  const pw = require('./playwright-env');
  const browser = await pw.launch();
  if (!browser) { console.log("PASS SuperApp provider contract (Part A); Part B skipped - no browser"); return; }
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  const boot = async (html) => {
    await page.setContent(html);
    await page.addScriptTag({ content: src + "\n;window.__P = ZSProvider; ZSProvider.init({ diag: () => {} });" });
  };
  const LIST = (rows, reverse) => `<div id="list" style="overflow-y:auto;height:560px;width:900px;${reverse ? "display:flex;flex-direction:column-reverse" : ""}"><div id="rows" style="${reverse ? "display:flex;flex-direction:column-reverse" : ""}">${rows}</div></div>`;
  const row = (who, t, txt) => `<div><div>${who} ${t}</div><div>${txt}</div></div>`;
  const SEND_SIM = `<script>
    function zsSim(get, set){ document.getElementById('send').onclick=()=>{ const v=get(); if(!v.trim())return; const rows=document.getElementById('rows');
      const add=(h)=>{const d=document.createElement('div'); d.innerHTML=h; window.__REV ? rows.insertBefore(d, rows.firstChild) : rows.appendChild(d); return d;};
      const u=add('<div>Remy 10:02 AM</div><div></div>'); u.lastChild.textContent=v; set('');
      setTimeout(()=>{ add('<div>SuperApp 10:02 AM</div><div>{"command":"read_file","params":{"path":"a.lua"}}</div>'); },250); }; }
  </script>`;

  // B1. legacy RN textarea composer
  await boot(`<body style="margin:0"><div style="display:flex;flex-direction:column;height:760px">
    ${LIST(`<div><div>Today</div></div>${row("Remy", "10:01 AM", "hello build me a thing please")}${row("SuperApp", "10:01 AM", "Sure - what engine?")}`)}
    <div data-testid="rich-message-input" style="width:900px"><textarea placeholder="Send a message..." id="ta" style="width:700px;height:40px"></textarea><button aria-label="Send" id="send">S</button></div>
    </div>${SEND_SIM}<script>zsSim(()=>document.getElementById('ta').value, v=>{document.getElementById('ta').value=v;});</script></body>`);
  let r = await page.evaluate(async () => {
    const P = window.__P, o = {};
    o.ed = P.getEditor() && P.getEditor().id; o.items0 = P.allItems().length; o.reply0 = P.readAssistant().reply;
    o.a0 = P.assistantCount();
    await P.typeAndSend("Output of 'list': 3 files");
    await new Promise((res) => setTimeout(res, 700));
    o.a1 = P.assistantCount(); o.u1 = P.userCount(); o.reply1 = P.readAssistant().reply; o.ta = document.getElementById('ta').value;
    o.lastIsUser = P.isUserItem(P.allItems()[P.allItems().length - 2]);
    o.diag = P.diagnostics().state; o.ready = await P.ensureComposerReady("test");
    return o;
  });
  ok(r.ed === "ta", "B1: textarea composer found");
  ok(r.items0 === 2, "B1: date separator ignored, 2 turns, got " + r.items0);
  ok(r.reply0 === "Sure - what engine?", "B1: header stripped from reply, got " + JSON.stringify(r.reply0));
  ok(r.ta === "", "B1: composer cleared after send");
  ok(r.lastIsUser, "B1: our sent text is a user turn (ledger)");
  ok(r.a1 > r.a0, "B1: assistant count grew after the reply (" + r.a0 + " -> " + r.a1 + ")");
  ok(/read_file/.test(r.reply1), "B1: reads the new reply, got " + JSON.stringify(r.reply1));
  ok(r.diag.hasEditor && r.diag.editorKind === "textarea" && r.diag.hasList && !r.diag.authGate, "B1: diagnostics state " + JSON.stringify(r.diag));
  ok(r.ready.ready === true && !r.ready.needsAuth, "B1: ensureComposerReady ready");
  console.log("  ok  B1 legacy textarea composer: rows, headers, send round-trip, ledger ownership");

  // B2. rich tiptap composer + inverted list + open edit composer (must be ignored)
  await boot(`<body style="margin:0"><script>window.__REV=1</script><div style="display:flex;flex-direction:column;height:760px">
    ${LIST(`${row("SuperApp", "9:00 AM", "second (newest)")}${row("SuperApp", "8:59 AM", "first (oldest)")}`, true)}
    <div data-testid="rich-message-edit-composer"><div class="eti-editor"><div class="tiptap ProseMirror" contenteditable="true" id="edit">old message</div></div></div>
    <div data-testid="rich-message-input" style="width:900px"><div data-testid="rich-composer-accessories"></div><div class="eti-editor"><div class="tiptap ProseMirror" contenteditable="true" id="pm" style="min-height:40px;width:700px"></div></div><button aria-label="Send" id="send">S</button></div>
    </div>${SEND_SIM}<script>zsSim(()=>document.getElementById('pm').textContent, v=>{document.getElementById('pm').textContent=v;});</script></body>`);
  r = await page.evaluate(async () => {
    const P = window.__P, o = {};
    o.ed = P.getEditor() && P.getEditor().id;
    o.reply0 = P.readAssistant().reply;
    await P.typeAndSend("Output of 'x': ok");
    await new Promise((res) => setTimeout(res, 700));
    o.reply1 = P.readAssistant().reply; o.u = P.userCount(); o.pm = document.getElementById('pm').textContent; o.edit = document.getElementById('edit').textContent;
    o.kind = P.diagnostics().state.editorKind;
    return o;
  });
  ok(r.ed === "pm", "B2: rich composer chosen over the edit composer, got " + r.ed);
  ok(r.reply0 === "second (newest)", "B2: inverted list ordered by screen position, got " + JSON.stringify(r.reply0));
  ok(r.pm === "" && r.edit === "old message", "B2: sent through the main composer only");
  ok(r.u >= 1 && /read_file/.test(r.reply1), "B2: round trip on the rich composer, got " + JSON.stringify(r));
  ok(r.kind === "contenteditable", "B2: diagnostics editorKind");
  console.log("  ok  B2 rich tiptap composer: edit composer ignored, inverted list, send round-trip");

  // B3. signed-out landing page
  await boot(`<body><h1>SuperApp</h1><button>Log in</button><button>Sign up</button></body>`);
  r = await page.evaluate(async () => {
    const P = window.__P;
    const t0 = Date.now(); const ready = await P.ensureComposerReady("test");
    return { ready, err: P.scanError(), gate: P.diagnostics().state.authGate, ms: Date.now() - t0, items: P.allItems().length };
  });
  ok(r.ready.ready === false && r.ready.needsAuth === true, "B3: needsAuth, got " + JSON.stringify(r.ready));
  ok(/signed out/i.test(r.err) && r.gate === true && r.items === 0, "B3: scanError + diagnostics explain the gate");
  console.log("  ok  B3 signed-out page: needsAuth + explanation, no throw");

  await boot(`<body><div data-testid="rich-message-input"><textarea style="width:700px;height:50px"></textarea></div><div role="alert">Task_context limit reached</div><button id="continue">Continue</button></body>`);
  r=await page.evaluate(()=>{
    const P=window.__P;
    const before=P.scanError();
    const clicked=P.clickContinueBtn();
    return {before,clicked,after:P.scanError()};
  });
  ok(/Task_context/.test(r.before)&&r.clicked&&!r.after,"B4: context-limit Continue suppresses the stale error surface");
  console.log("  ok  B4 Task_context limit + native Continue recovery");
  await page.close(); await browser.close();
  console.log("PASS SuperApp provider contract: Part A (no-throw + registration) + Part B (4 real-browser DOM scenarios)");
})().catch((e) => { console.error("FAIL", e && e.stack || e); process.exit(1); });
