// SPDX-License-Identifier: GPL-3.0-or-later
// providers/superapp.js — SuperApp (superapp.chat)
// Multi-Script provider interface as chatgpt.js / promptql.js. To disable,
// remove this file from manifest.json, background.js PROVIDER_URLS, popup.js
// SUPPORTED_HOSTS and main.js AI_SITES.
//
// SuperApp is an Expo / React-Native-Web app (team chat + AI). Its CSS class
// names are generated (css-xxxx / r-xxxx) and change every build, so this
// adapter is built on things that survive builds (from the shipped bundle,
// 1.212.0): RN testIDs → data-testid ("rich-message-input",
// "rich-composer-accessories", "rich-message-edit-composer"), the tiptap
// composer (.eti-editor / .ProseMirror) or the legacy RN <textarea>, the
// "Send" accessibility label, and a STRUCTURAL message list: the scroll
// container above the composer, rows ordered by on-screen position (RN
// FlatLists are often inverted in the DOM).
// Turn ownership: rows containing text WE sent (or that the user sent through
// the composer) are user turns; any later non-trivial row is the AI turn.
// Counts are monotonic (every row gets a data-zs-key the first time it is
// seen) so list virtualisation never makes them go backwards.
// 6.29.1: merged with the 6.29.0 "defensive" rewrite — keeps its no-throw
// guarantee (every read-only export is wrapped and degrades to a safe value),
// its diagnostics() report and its sign-in gate detection (ensureComposerReady
// returns needsAuth, scanError explains it), on top of the bundle-grounded
// selectors and the sent-text ledger above.
// NOT live-validated with a signed-in account — every miss is logged via
// diag("superapp.*") and diagnostics() shows exactly what was (not) found.
const ZSProvider = (() => {
  "use strict";
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const waitFor = async (fn, ms) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      try { const v = fn(); if (v) return v; } catch {}
      await sleep(80);
    }
    try { return fn(); } catch { return null; }
  };

  let diag = () => {};
  const wire = { stream: '', running: false, text: '', thinking: '', id: '', error: '', turn: 0, receivedAt: 0, connected: false };
  const wireNodes = new Map();
  const wireRoles = new Map();
  function wireNode() {
    if (!wire.id || !wire.text) return null;
    let node = wireNodes.get(wire.id);
    if (!node) {
      node = document.createElement('article');
      node.dataset.msSuperappId = wire.id;
      node.setAttribute('data-message-author-role', 'assistant');
      node.style.display = 'none';
      (document.body || document.documentElement).appendChild(node);
      wireNodes.set(wire.id, node);
      if (wireNodes.size > 40) { const key = wireNodes.keys().next().value; wireNodes.get(key).remove(); wireNodes.delete(key); }
    }
    node.textContent = wire.text;
    return node;
  }
  if (typeof window.addEventListener === 'function') window.addEventListener('message', event => {
    if (event.source !== window || event.origin !== location.origin || event.data?.source !== 'ms-superapp-wire-v1') return;
    const value = event.data.value;
    if (!value || typeof value.type !== 'string') return;
    if (value.type === 'local_send') {
      wire.stream = String(value.stream || ''); wire.turn++;
      Object.assign(wire, { running: true, text: '', thinking: '', id: '', error: '', connected: true, receivedAt: Date.now() });
      remember(value.text); return;
    }
    if (value.type === 'wire_closed') { wire.connected = false; return; }
    if (!wire.stream || (value.stream && value.stream !== wire.stream)) return;
    if (value.type === 'new_message' && value.id && ['user', 'assistant'].includes(value.role)) {
      wireRoles.set(String(value.id), value.role);
      if (wireRoles.size > 500) wireRoles.delete(wireRoles.keys().next().value);
    }
    wire.receivedAt = Date.now(); wire.connected = true;
    if (value.error) { wire.error = String(value.error).slice(0, 600); wire.running = false; }
    if (value.running) wire.running = true;
    if (value.reasoning) wire.thinking = String(value.reasoning).slice(-12000);
    if (value.role === 'assistant' && typeof value.text === 'string') {
      wire.id = String(value.id || wire.id || ('wire:' + wire.stream + ':' + wire.turn));
      wire.text = value.snapshot ? value.text : wire.text + value.text;
      wire.text = wire.text.slice(0, 1500000);
      wireNode();
    }
    if (value.final && value.role !== 'user') { wire.running = false; wire.thinking = ''; }
  });
  const timings = {
    GEN_IDLE_MS: 2200,
    REASON_IDLE_MS: 20000,
    WARMUP_MS: 60000,
    REASON_NOREPLY_MS: 180000,
    STABLE_MS: 9000,
    RESPONSE_TIMEOUT_MS: 420000,
  };

  const S = {
    composerRoot: '[data-testid="rich-message-input"], [data-testid="rich-composer-accessories"]',
    editRoot: '[data-testid="rich-message-edit-composer"], [data-testid="message-edit-source"]',
    editor: '.eti-editor [contenteditable="true"], .eti-editor.ProseMirror, .tiptap.ProseMirror[contenteditable="true"], .ProseMirror[contenteditable="true"], [data-zs-locked="1"], textarea, [contenteditable="true"][role="textbox"], [contenteditable="true"]',
    send: '[aria-label="Send"], [aria-label^="Send" i], [data-testid*="send" i], button[type="submit"]',
    stop: '[aria-label^="Stop" i], [aria-label*="stop generating" i], [data-testid*="stop" i], [title^="Stop" i]',
    working: '[aria-busy="true"], [role="progressbar"]',
    codeWrap: "pre, code",
    attachInput: 'input[type="file"]',
    errorSurfaces: '[role="alert"], [aria-live="assertive"], [aria-live="polite"], [data-testid="router_error_message"]',
    retry: '[data-testid="router_error_retry"]',
    authGate: '#auth0-lock-container, form[action*="auth.superapp.chat" i], a[href*="auth.superapp.chat" i], input[type="password"], input[type="email"], input[autocomplete="email"]',
  };
  const AUTH_LABEL = /^(log ?in|sign ?in|sign ?up|continue with (google|microsoft|apple|email)|get started)$/i;

  const SEND_MAX_CHARS = 60000;
  const SEND_MAX_LINES = 3000;
  const CMD_SHAPE = /"(?:command|tool)"\s*:\s*"|###\s*lua|###mcp_tool###/i;

  const RE = {
    contextLimit: /task[_ -]*context.{0,40}limit|conversation.{0,20}(too long|limit)|context (window|length).{0,20}(exceeded|limit)|maximum.{0,16}(length|context)|too many tokens/i,
    tooLong: /message.{0,20}too long|over the (character|token) limit|exceeds? the (maximum|limit)/i,
    busy: /too many requests|rate.?limit|try again (later|in a moment)|something went wrong|temporarily unavailable|overloaded|at capacity|network error|failed to (send|generate)|an error occurred|out of credits|usage limit|upgrade (your plan|to continue)/i,
    continueBtn: /^(continue|continue generating|resume)$/i,
    stopLabel: /^(stop|stop generating|stop response|stop task|cancel)$/i,
    working: /^(thinking|thinking\.\.\.|working|working…|working\.\.\.|generating|typing)\b/i,
    header: /^\s*[^\n]{1,60}?\s+(\d{1,2}:\d{2}\s*(AM|PM)?|just now|yesterday|today|\d+\s*(m|min|h|s) ago)\s*$/i,
    timeOnly: /^\s*(\d{1,2}:\d{2}\s*(AM|PM)?|just now|today|yesterday|edited)\s*$/i,
    separator: /^\s*(today|yesterday|new messages?|unread( messages?)?|(mon|tues|wednes|thurs|fri|satur|sun)day(,\s*\w+\s+\d{1,2}(st|nd|rd|th)?)?|(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(st|nd|rd|th)?(,?\s*\d{4})?)\s*$/i,
  };

  const visible = (el) => { if (!el || !el.getBoundingClientRect) return false; const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4; };
  const ours = (el) => !!(el && el.closest && el.closest("#rs-root, .zs-chip, #zs-overlay, [id^='zs-']"));
  const norm = (s) => String(s || "").replace(/\s+/g, "");

  // ── sent-text ledger (turn ownership) ─────────────────────────────────────
  const LEDGER_KEY = "zsSuperappSent";
  let ledger = [];
  try { ledger = JSON.parse(sessionStorage.getItem(LEDGER_KEY) || "[]"); } catch { ledger = []; }
  function remember(text) {
    const n = norm(text);
    if (n.length < 2) return;
    ledger.push(n.slice(0, 160));
    if (ledger.length > 200) ledger = ledger.slice(-200);
    try { sessionStorage.setItem(LEDGER_KEY, JSON.stringify(ledger)); } catch {}
  }
  function matchesSent(rowNorm) {
    if (!rowNorm) return false;
    for (let i = ledger.length - 1; i >= 0; i--) {
      const s = ledger[i];
      const probe = s.slice(0, Math.min(60, s.length));
      if ((probe.length >= 20 && rowNorm.includes(probe)) || rowNorm === s) return true;
    }
    return false;
  }

  // ── text helpers ──────────────────────────────────────────────────────────
  function textWithout(root, excludeSel) {
    if (!root) return "";
    let t = "";
    const walk = (n) => {
      if (n.nodeType === 3) { t += n.nodeValue; return; }
      if (n.nodeType !== 1) return;
      if (excludeSel && n.matches && n.matches(excludeSel)) return;
      if (n.classList && (n.classList.contains("zs-chip") || n.classList.contains("zs-tool-hide"))) return;
      if (n.tagName === "BUTTON" || n.tagName === "SVG" || n.tagName === "svg" || n.tagName === "IMG" || n.tagName === "STYLE" || n.tagName === "SCRIPT") return;
      if (n.getAttribute && n.getAttribute("aria-hidden") === "true") return;
      if (n.tagName === "BR") { t += "\n"; return; }
      const block = /^(P|DIV|LI|PRE|H1|H2|H3|H4|H5|H6|TR|ARTICLE|SECTION|BLOCKQUOTE|UL|OL|TABLE)$/.test(n.tagName);
      if (block && t && !t.endsWith("\n")) t += "\n";
      for (const c of n.childNodes) walk(c);
      if (block && t && !t.endsWith("\n")) t += "\n";
    };
    walk(root);
    return t.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  }
  // Drop the "Name · 10:42 AM" header / reaction / "edited" noise of a row.
  function stripChrome(t) {
    const lines = String(t || "").split("\n");
    while (lines.length > 1 && (RE.header.test(lines[0]) || RE.timeOnly.test(lines[0]) || (lines[0].trim().length <= 40 && RE.timeOnly.test(lines[1] || "")))) {
      if (lines[0].trim().length <= 40 && RE.timeOnly.test(lines[1] || "")) lines.splice(0, 2); else lines.shift();
    }
    while (lines.length > 1 && RE.timeOnly.test(lines[lines.length - 1])) lines.pop();
    return lines.join("\n").trim();
  }

  // ── composer ──────────────────────────────────────────────────────────────
  const inEdit = (el) => !!(el && el.closest && el.closest(S.editRoot));
  function getEditor() {
    const all = [...document.querySelectorAll(S.editor)].filter((n) => visible(n) && !ours(n) && !inEdit(n) &&
      !(n.tagName === "TEXTAREA" && (n.readOnly || n.disabled)) &&
      !(n.closest && n.closest('[data-testid^="sentry-feedback"], [data-testid="feedback-form-modal"], [role="search"]')));
    if (!all.length) return null;
    const inRoot = all.filter((n) => n.closest(S.composerRoot));
    let pool = inRoot.length ? inRoot : all;
    // Prefer a message-shaped placeholder ("Send a message...", "Ask anything").
    const msg = pool.filter((n) => /message|ask|send|reply|write|type/i.test((n.getAttribute("placeholder") || n.getAttribute("aria-label") || n.getAttribute("data-placeholder") || (n.querySelector && n.querySelector("[data-placeholder]") && n.querySelector("[data-placeholder]").getAttribute("data-placeholder")) || "")));
    if (msg.length) pool = msg;
    try { pool.sort((a, b) => a.getBoundingClientRect().bottom - b.getBoundingClientRect().bottom); } catch {}
    return pool[pool.length - 1];
  }
  const isTA = (ed) => !!(ed && ed.tagName === "TEXTAREA");
  const edValue = (ed) => (ed ? (isTA(ed) ? ed.value : ed.textContent) || "" : "");
  const editorText = () => edValue(getEditor());
  function composerBox() {
    const ed = getEditor();
    if (!ed) return null;
    const root = ed.closest(S.composerRoot);
    if (root) return root.closest('[data-testid="rich-message-input"]') || root;
    // Walk up until the box also holds a button (send/attach) but stays small.
    let n = ed.parentElement;
    for (let i = 0; n && i < 8; i++, n = n.parentElement) {
      const r = n.getBoundingClientRect();
      if (r.height > window.innerHeight * 0.6) break;
      if (n.querySelector('button, [role="button"]')) return n;
    }
    return ed.parentElement;
  }
  const composerFrame = () => composerBox();
  const barAnchor = () => composerBox();

  let _locked = false;
  function setInputLock(on) {
    _locked = on;
    const ed = getEditor();
    if (!ed) return;
    if (isTA(ed)) { ed.readOnly = !!on; }
    else ed.setAttribute("contenteditable", on ? "false" : "true");
    if (on) ed.setAttribute("data-zs-locked", "1"); else ed.removeAttribute("data-zs-locked");
  }

  const clickable = 'button, [role="button"]';
  const labelOf = (b) => ((b.getAttribute && (b.getAttribute("aria-label") || b.getAttribute("title"))) || b.textContent || "").trim();
  function nearComposer(b) {
    const box = composerBox();
    if (!box) return false;
    if (box.contains(b)) return true;
    const r = b.getBoundingClientRect(), c = box.getBoundingClientRect();
    return r.top >= c.top - 80 && r.bottom <= c.bottom + 80 && r.left >= c.left - 40 && r.right <= c.right + 80;
  }
  function stopButton() {
    for (const b of document.querySelectorAll(S.stop)) if (visible(b) && !ours(b) && nearComposer(b)) return b.closest(clickable) || b;
    for (const b of document.querySelectorAll(clickable)) if (visible(b) && !ours(b) && RE.stopLabel.test(labelOf(b)) && nearComposer(b)) return b;
    return null;
  }
  function sendButton() {
    const box = composerBox();
    if (!box) return null;
    const scope = box.parentElement || box;
    for (const b of scope.querySelectorAll(S.send)) {
      if (!visible(b) || ours(b)) continue;
      const c = b.closest(clickable) || b;
      if (!stopButton() || c !== stopButton()) return c;
    }
    // Fallback: the right-most enabled button on the composer's row.
    const btns = [...scope.querySelectorAll(clickable)].filter((b) => visible(b) && !ours(b) && nearComposer(b) && !RE.stopLabel.test(labelOf(b)));
    if (!btns.length) return null;
    btns.sort((a, b) => a.getBoundingClientRect().right - b.getBoundingClientRect().right);
    const last = btns[btns.length - 1];
    return /send|submit|arrow/i.test(labelOf(last) + " " + (last.innerHTML || "").slice(0, 400)) ? last : null;
  }
  const btnDisabled = (b) => !!(b && (b.disabled || b.getAttribute("aria-disabled") === "true"));

  // ── message list (structural) ─────────────────────────────────────────────
  let _listCache = null, _listAt = 0;
  function messageList() {
    if (_listCache && document.contains(_listCache) && Date.now() - _listAt < 1500) return _listCache;
    const box = composerBox();
    const cb = box ? box.getBoundingClientRect() : { top: window.innerHeight, left: 0, right: window.innerWidth };
    let best = null, bestScore = 0;
    for (const el of document.querySelectorAll("div, main, section, [role='list'], [role='log']")) {
      if (ours(el) || (box && (box.contains(el) || el.contains(box) && el === box))) continue;
      const st = getComputedStyle(el);
      if (!/(auto|scroll)/.test(st.overflowY)) continue;
      const r = el.getBoundingClientRect();
      if (r.height < 120 || r.width < 240) continue;
      if (r.top > cb.top) continue;                       // must sit above the composer
      const overlap = Math.max(0, Math.min(r.right, cb.right) - Math.max(r.left, cb.left));
      if (overlap < Math.min(200, (cb.right - cb.left) * 0.5)) continue;   // same column as composer (not the sidebar)
      const score = overlap * r.height + (el.getAttribute("role") === "log" || el.getAttribute("role") === "list" ? 1e7 : 0);
      if (score > bestScore) { bestScore = score; best = el; }
    }
    _listCache = best; _listAt = Date.now();
    return best;
  }
  function rowContainer(list) {
    // Descend through single-child wrappers to the element holding the rows.
    let n = list;
    for (let d = 0; n && d < 8; d++) {
      const kids = [...n.children].filter((k) => !ours(k)&&(visible(k)||k.classList.contains('zs-hidden')) && (k.textContent || "").trim());
      if (kids.length >= 2) {
        // A list of 2 where one is a tiny header and the other wraps everything
        // is still a wrapper: keep descending into the big one.
        const big = kids.filter((k) => k.getBoundingClientRect().height > n.getBoundingClientRect().height * 0.8);
        if (kids.length === 2 && big.length === 1 && big[0].children.length >= 2) { n = big[0]; continue; }
        return n;
      }
      if (kids.length === 1) n = kids[0]; else return n;
    }
    return n;
  }
  let _seq = 0;
  const keyOf = (row) => {
    if (!row) return null;
    let k = row.getAttribute('data-message-id') || row.getAttribute('data-ms-superapp-id') || row.getAttribute("data-zs-key");
    if (!k) { k = "sa" + (++_seq) + "_" + Date.now().toString(36); row.setAttribute("data-zs-key", k); }
    return k;
  };
  function rawRows() {
    const list = messageList();
    if (!list) return [];
    const host = rowContainer(list);
    if (!host) return [];
    const rows = [...host.children].filter((r) => (visible(r)||r.classList.contains('zs-hidden')) && !ours(r));
    try {if(rows.some(r=>!visible(r))){if(getComputedStyle(host).flexDirection==='column-reverse')rows.reverse();}else rows.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top); } catch {}
    return rows;
  }
  const rowText = (row) => stripChrome(textWithout(row));
  function isNoise(row) {
    const t = (row.innerText || row.textContent || "").trim();
    if (!t) return !row.querySelector("img, video, pre, code");
    if (t.length <= 40 && RE.separator.test(t)) return true;
    return false;
  }
  const roleCache = new WeakMap();
  function roleOf(row) {
    const messageId = row.getAttribute('data-message-id') || row.getAttribute('data-ms-superapp-id');
    if (messageId && wireRoles.has(messageId)) return wireRoles.get(messageId);
    const explicit = row.getAttribute('data-message-author-role') || row.getAttribute('data-role') || row.getAttribute('data-author-role');
    if (explicit === 'user' || explicit === 'assistant') return explicit;
    const fingerprint = norm(row.textContent || '').slice(0, 160);
    const known = roleCache.get(row);
    if (known?.fingerprint === fingerprint && known.role === 'user') return 'user';
    const n = norm(row.innerText || "");
    if (matchesSent(n)) { roleCache.set(row, { role: 'user', fingerprint }); return "user"; }
    // SuperApp marks the viewer's own rows in some layouts (right-aligned
    // bubbles). Use alignment as a secondary cue for rows we did not send.
    try {
      const list = messageList(), lr = list && list.getBoundingClientRect(), rr = row.getBoundingClientRect();
      const inner = row.querySelector("div div") || row;
      const ir = inner.getBoundingClientRect();
      if (lr && ir.width < lr.width * 0.75 && ir.left - lr.left > lr.width * 0.3 && rr.right >= lr.right - 40) { roleCache.set(row, { role: 'user', fingerprint }); return "user"; }
    } catch {}
    return "assistant";
  }
  const seenUser = new Set(), seenAsst = new Set();
  function allItems() {
    const rows = rawRows().filter((r) => !isNoise(r));
    for (const r of rows) {
      const k = keyOf(r);
      if (roleOf(r) === "user") { seenUser.add(k); seenAsst.delete(k); }
      else if (!seenUser.has(k)) seenAsst.add(k);
    }
    return rows;
  }
  const isUserItem = (item) => !!item && roleOf(item) === "user";
  const isAssistantItem = (item) => !!item && roleOf(item) !== "user" && !isNoise(item);
  // Only rows AFTER our first user turn count as AI replies in a shared room.
  function assistantItems() {
    const rows = allItems();
    let firstUser = rows.findIndex(isUserItem);
    if (firstUser < 0) firstUser = rows.length ? -1 : 0;
    return rows.filter((r, i) => i > firstUser && isAssistantItem(r));
  }
  const assistantCount = () => { assistantItems(); return seenAsst.size; };
  const userCount = () => { allItems(); return seenUser.size; };
  const lastAssistant = () => {
    if (wire.id && wire.text) {
      const actual = Array.from(document.querySelectorAll('[data-message-id]')).find(n => n.getAttribute('data-message-id') === wire.id);
      return actual || wireNode();
    }
    if (wire.stream && wire.receivedAt && wire.running) return null;
    const rows = allItems();
    const last = rows[rows.length - 1];
    if (!last || !isAssistantItem(last)) return null;
    return last;
  };
  const lastAssistantId = () => { const l = lastAssistant(); return l ? keyOf(l) : null; };

  function replyText(item, extraSkip) {
    if (!item) return "";
    if (item.getAttribute('data-ms-superapp-id') === wire.id) return wire.text;
    const t = rowText(item);
    if (extraSkip) { return stripChrome(textWithout(item, extraSkip)); }
    return t;
  }
  function itemText(item) { return replyText(item); }
  function classifyText(item, excludeSel) { return replyText(item, excludeSel); }
  function thinkingText(item) {
    if (wire.running && wire.receivedAt) return wire.thinking || 'SuperApp is working';
    if (!item) return "";
    const t = (item.innerText || "").trim();
    const first = t.split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 4);
    for (const l of first) if (RE.working.test(l)) return l;
    const w = item.querySelector(S.working);
    return w ? ((w.textContent || "working").trim() || "working") : "";
  }

  const chatIsEmpty = () => rawRows().filter((r) => !isNoise(r)).length === 0;
  const isFreshChat = () => chatIsEmpty() && !!getEditor();
  const conversationKey = () => { try { return location.pathname && location.pathname.length > 1 ? location.pathname : ""; } catch { return ""; } };

  // ── generation state ──────────────────────────────────────────────────────
  let _streamMax = -1, _streamAt = 0, _streamItem = null;
  function streamText(item) {
    if (!item) return "";
    const r = replyText(item), th = thinkingText(item);
    return th ? th + "\n" + r : r;
  }
  const streamLen = (item) => streamText(item === undefined ? lastAssistant() : item).length;
  function sampleStream() {
    const item = lastAssistant();
    const len = streamText(item).length;
    const now = Date.now();
    if (item !== _streamItem || len < _streamMax - 400) {
      const first = _streamMax < 0;
      _streamItem = item; _streamMax = len; _streamAt = first ? 0 : now; return;
    }
    if (len > _streamMax) { _streamMax = len; _streamAt = now; }
  }
  function isGenerating() {
    if (wire.receivedAt && wire.stream && Date.now() - wire.receivedAt < timings.RESPONSE_TIMEOUT_MS) return wire.running;
    sampleStream();
    if (stopButton()) return true;
    const last = lastAssistant();
    if (last && thinkingText(last)) return true;
    return _streamMax > 1 && Date.now() - _streamAt < timings.GEN_IDLE_MS;
  }
  const isBusyNow = () => isGenerating();
  const isHardGenerating = () => wire.running || !!stopButton();
  function snapshot() {
    try { const it = lastAssistant(); return it ? { th: thinkingText(it).length, rp: replyText(it).length } : { th: 0, rp: 0 }; } catch { return {}; }
  }
  function readAssistant() {
    const item = lastAssistant();
    if (!item) return { present: false, reply: "", thinking: "", item: null };
    return { present: true, reply: replyText(item), thinking: thinkingText(item), item };
  }

  // ── sending ───────────────────────────────────────────────────────────────
  function truncateForSend(text) {
    { const o = (text && typeof ZS !== "undefined" && ZS.limits) ? ZS.limits.sendOverride(text) : null; if (o !== null) return o; }
    if (!text) return text;
    let s = String(text);
    if (s.length > SEND_MAX_CHARS) s = s.slice(0, SEND_MAX_CHARS) + "\n…[truncated]";
    const lines = s.split("\n");
    if (lines.length > SEND_MAX_LINES) s = lines.slice(0, SEND_MAX_LINES).join("\n") + "\n…[truncated]";
    return s;
  }
  function setNativeValue(el, value) {
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, "value") || Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    desc.set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
  function clearCE(ed) {
    try {
      ed.focus();
      const range = document.createRange(); range.selectNodeContents(ed);
      const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
      document.execCommand("delete");
    } catch {}
  }
  async function fillEditor(ed, text) {
    const want = norm(text);
    ed.focus();
    if (isTA(ed)) {
      setNativeValue(ed, text);
      await sleep(60);
      if (norm(ed.value).length >= want.length * 0.98) return true;
      // Some RN TextInputs ignore synthetic value sets: type it.
      ed.select(); document.execCommand("insertText", false, text);
      await sleep(60);
      return norm(ed.value).length >= want.length * 0.98;
    }
    clearCE(ed);
    try {
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      ed.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    } catch {}
    await sleep(80);
    const got = () => norm(ed.textContent);
    if (got() && got().length >= want.length * 0.98) return true;
    clearCE(ed);
    const lines = String(text).split("\n");
    for (let i = 0; i < lines.length; i++) {
      if (lines[i]) document.execCommand("insertText", false, lines[i]);
      if (i < lines.length - 1) document.execCommand("insertLineBreak");
      if (i && i % 40 === 0) await sleep(0);
    }
    await sleep(40);
    return got().length >= want.length * 0.98;
  }
  function closePopups() {
    try {
      if (document.querySelector('[data-testid$="mention-suggestions"], [role="listbox"], .tippy-box, [data-tippy-root]')) {
        const ed = getEditor();
        ed && ed.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true }));
      }
    } catch {}
  }
  function pressEnter(ed) {
    const o = { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true };
    ed.dispatchEvent(new KeyboardEvent("keydown", o));
    ed.dispatchEvent(new KeyboardEvent("keypress", o));
    ed.dispatchEvent(new KeyboardEvent("keyup", o));
  }
  async function typeAndSend(text, images) {
    text = truncateForSend(text);
    let ed = getEditor();
    if (!ed) { await waitFor(() => getEditor(), 5000); ed = getEditor(); }
    if (!ed) { diag("superapp.noEditor", { url: location.pathname }); throw new Error("SuperApp message box not found"); }
    const relock = _locked;
    if (relock) setInputLock(false);
    try {
      const ok = await fillEditor(ed, text);
      if (!ok) diag("superapp.fillShort", { want: text.length, got: edValue(ed).length, ta: isTA(ed) });
      if (!norm(edValue(ed))) throw new Error("SuperApp composer did not accept the text");
      const turnBeforeSend = wire.turn;
      remember(text);
      if (images && images.length) { try { await attachImages(images); } catch {} }
      closePopups();
      const btn = await waitFor(() => { const b = sendButton(); return b && !btnDisabled(b) ? b : null; }, images && images.length ? 20000 : 2500);
      if (btn) btn.click(); else pressEnter(ed);
      let sent = await waitFor(() => wire.turn > turnBeforeSend || !norm(editorText()) || !!stopButton(), 3000);
      if (!sent) {
        const e2 = getEditor(); if (e2) { e2.focus(); pressEnter(e2); }
        sent = await waitFor(() => wire.turn > turnBeforeSend || !norm(editorText()) || !!stopButton(), 3000);
        if (!sent) { diag("superapp.sendStuck", { btn: !!btn, ta: isTA(ed) }); throw new Error('SuperApp did not acknowledge the message. Check the composer before retrying.'); }
      }
    } finally {
      if (relock) setInputLock(true);
    }
  }
  function stopGeneration() { const b = stopButton(); if (b) try { b.click(); } catch {} }

  function fileFromImage(img, i) {
    const mime = img.mimeType || "image/jpeg";
    const bin = atob(img.data);
    const arr = new Uint8Array(bin.length);
    for (let j = 0; j < bin.length; j++) arr[j] = bin.charCodeAt(j);
    return new File([arr], `multiscript_${Date.now()}_${i}.${mime.includes("png") ? "png" : "jpg"}`, { type: mime });
  }
  async function attachImages(images) {
    const ed = getEditor();
    if (!ed || !images || !images.length) return false;
    const dt = new DataTransfer();
    images.forEach((img, i) => { try { dt.items.add(fileFromImage(img, i)); } catch {} });
    if (!dt.items.length) return false;
    const box = composerBox();
    const input = (box && box.parentElement && box.parentElement.querySelector(S.attachInput)) || document.querySelector(S.attachInput);
    if (input) { try { input.files = dt.files; input.dispatchEvent(new Event("change", { bubbles: true })); } catch {} }
    else ed.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    await sleep(1500);
    return true;
  }
  function clearAttachments() {}

  function describeDom() {
    const ed = getEditor(), list = messageList();
    return {
      editor: ed ? (ed.tagName + (ed.className && typeof ed.className === "string" ? "." + ed.className.split(/\s+/).slice(0, 3).join(".") : "")) : null,
      placeholder: ed ? (ed.getAttribute("placeholder") || ed.getAttribute("aria-label") || "") : "",
      composerRoot: !!(ed && ed.closest(S.composerRoot)),
      send: !!sendButton(), stop: !!stopButton(),
      list: !!list, rows: rawRows().length, user: seenUser.size, ai: seenAsst.size,
    };
  }
  async function ensureComposerReady(reason) {
    let ed = getEditor();
    if (!ed) { await waitFor(() => getEditor(), 6000); ed = getEditor(); }
    const gate = !ed && authGate();
    diag("mode_ready", { reason, provider: "superapp", ready: !!ed, authGate: gate, dom: describeDom() });
    return gate ? { ready: false, needsAuth: true } : { ready: !!ed };
  }
  function enforceComposer() { return { ready: !!getEditor() }; }

  let contextResumeUntil = 0;
  function scanError() {
    if (wire.error && !(RE.contextLimit.test(wire.error) && Date.now() < contextResumeUntil)) return wire.error;
    try {
      if (authGate()) return "SuperApp is signed out (session expired?) - sign in at superapp.chat in this tab, then press Retry.";
      for (const el of document.querySelectorAll(S.errorSurfaces)) {
        if (!visible(el) || ours(el)) continue;
        const t = (el.innerText || "").trim();
        if (Date.now() >= contextResumeUntil && t.length > 8 && t.length < 600 && RE.contextLimit.test(t)) return t.slice(0, 240);
      }
    } catch {}
    return "";
  }
  const isTooLongMsg = (t) => RE.tooLong.test(t || "");
  const isBusyMsg = (t) => RE.busy.test(t || "");
  const turnHalted = () => false;
  function clickRetry() {
    const last = lastAssistant();
    let b = last && [...last.querySelectorAll(clickable)].find((x) => /^(retry|try again|regenerate)$/i.test(labelOf(x)));
    b = b || document.querySelector(S.retry);
    if (b && visible(b)) { try { b.click(); return true; } catch {} }
    return false;
  }
  const findContinueBtn = () => {
    for (const b of document.querySelectorAll(clickable)) if (visible(b) && !ours(b) && RE.continueBtn.test(labelOf(b))) return b;
    return null;
  };
  const clickContinueBtn = () => { const b = findContinueBtn(); if (b) { contextResumeUntil = Date.now() + 20000; wire.error = ""; b.click(); return true; } return false; };

  function installSendHooks(handlers) {
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
      const ed = getEditor();
      if (!ed || !(ed === e.target || ed.contains(e.target))) return;
      const txt = editorText();
      if (txt.trim() === "") return;
      if (handlers.isBlocked()) return;
      if (!handlers.isStarted()) { if (!chatIsEmpty()) return; handlers.onBlockedAttempt(); return; }
      remember(txt);
      handlers.onUserMessage(assistantCount());
    }, true);
    document.addEventListener("click", (e) => {
      if (!getEditor()) return;
      const btn = e.target && e.target.closest && e.target.closest(clickable);
      if (!btn) return;
      const stop = stopButton();
      if (stop && (btn === stop || stop.contains(btn))) { if (handlers.onNativeStop) handlers.onNativeStop(); return; }
      const send = sendButton();
      if (!send || !(btn === send || send.contains(btn))) return;
      if (handlers.isBlocked()) return;
      if (!handlers.isStarted()) { if (!chatIsEmpty()) return; handlers.onBlockedAttempt(); return; }
      remember(editorText());
      handlers.onUserMessage(assistantCount());
    }, true);
  }

  function findToolBlockSpot(item) {
    if (!item) return null;
    let hid = null;
    item.querySelectorAll("pre").forEach((pre) => {
      if (pre.closest(".zs-chip")) return;
      if (CMD_SHAPE.test(pre.textContent || "")) { pre.classList.add("zs-tool-hide"); hid = hid || { parent: pre.parentElement, ref: pre }; }
    });
    return hid;
  }

  // ── sign-in gate ──────────────────────────────────────────────────────────
  // Signed out, superapp.chat shows a landing / "Log in" screen (Auth0 lives on
  // auth.superapp.chat). Only meaningful when there is no composer.
  function authGate() {
    if (getEditor()) return false;
    for (const n of document.querySelectorAll(S.authGate)) if (!ours(n)) return true;
    for (const b of document.querySelectorAll('button, [role="button"], a')) {
      if (!ours(b) && visible(b) && AUTH_LABEL.test(labelOf(b))) return true;
    }
    return false;
  }

  // ── diagnostics ───────────────────────────────────────────────────────────
  // Plain report of what the adapter sees right now (Provider QA / terminal
  // panel / bug reports). Never throws.
  function diagnostics() {
    const out = { provider: "superapp", url: "", probes: {}, state: {}, dom: {} };
    try { out.url = String(location.href || ""); } catch {}
    for (const k of Object.keys(S)) {
      out.probes[k] = S[k].split(/,\s*(?![^\[]*\])/).map((sel) => {
        let count = -1;
        try { count = document.querySelectorAll(sel).length; } catch {}
        return { selector: sel, count };
      });
    }
    try { out.dom = describeDom(); } catch (e) { out.dom = { error: String(e && e.message || e) }; }
    const ed = safe(getEditor, null)();
    out.state = {
      hasEditor: !!ed,
      editorKind: ed ? (isTA(ed) ? "textarea" : "contenteditable") : null,
      inComposerRoot: !!(ed && ed.closest && ed.closest(S.composerRoot)),
      editorTextLen: safe(editorText, "")().length,
      hasList: !!safe(messageList, null)(),
      turns: safe(allItems, [])().length,
      assistantTurns: safe(assistantCount, 0)(),
      userTurns: safe(userCount, 0)(),
      sentLedger: ledger.length,
      wire: { stream: wire.stream, connected: wire.connected, running: wire.running, messageId: wire.id, chars: wire.text.length, lastEventAt: wire.receivedAt },
      generating: safe(isGenerating, false)(),
      authGate: safe(authGate, false)(),
      conversationKey: safe(conversationKey, "")(),
    };
    return out;
  }

  // No-throw guard for read-only exports: a DOM shape we do not recognise must
  // degrade to "nothing found", never break main.js's poll loop.
  function safe(fn, fallback) {
    return function () {
      try { return fn.apply(this, arguments); }
      catch (e) { try { diag("superapp.threw", { fn: fn.name, err: String(e && e.message || e).slice(0, 160) }); } catch {} return typeof fallback === "function" ? fallback() : fallback; }
    };
  }

  const PROMPT_EXTRA =
    `- LOCAL WORKSPACE TOOLS: the user drives this conversation through Multi-Script, a browser extension THEY installed on their own computer. It copies the JSON command you write into their local editor (Roblox Studio, Unity, Godot, Blender or a code folder) and pastes the real output back as their next message ("Output of '<name>': ..."). These local tools execute on the user's computer. SuperApp sandbox actions execute remotely; use the local tool protocol for changes to the user's editor.
- Treat each "Output of ..." message as the user's genuine result. Read it and continue the task.
- SuperApp sandbox progress is supported. Its filesystem is separate from the local editor; return an explicit local tool call when local changes are needed.
- Write exactly ONE command per reply as a plain-text JSON object {"command": "...", "params": {...}}, then stop and wait for the output.
- When the work is done, answer in plain text with no JSON.`;

  return {
    startupLineBudget: SEND_MAX_LINES,
    id: "superapp",
    displayName: "SuperApp",
    supportsVision: true,
    timings,
    chipAtItemLevel: true,
    reliableCounts: false,
    resultCharBudget: 12000, resultLineBudget: 500,
    minSendGapMs: 2500,
    promptExtra: PROMPT_EXTRA,
    init({ diag: d } = {}) { if (d) diag = d; },
    thinkingSel: S.working,
    allItems: safe(allItems, () => []), isUserItem: safe(isUserItem, false), isAssistantItem: safe(isAssistantItem, false),
    itemText: safe(itemText, ""), classifyText: safe(classifyText, ""),
    assistantCount: safe(assistantCount, 0), userCount: safe(userCount, 0), lastAssistant: safe(lastAssistant, null),
    lastAssistantId: safe(lastAssistantId, null), readAssistant: safe(readAssistant, () => ({ present: false, reply: "", thinking: "", item: null })),
    streamLen: safe(streamLen, 0), snapshot: safe(snapshot, () => ({})),
    getEditor: safe(getEditor, null), editorText: safe(editorText, ""), chatIsEmpty: safe(chatIsEmpty, true), isFreshChat: safe(isFreshChat, false),
    composerFrame: safe(composerFrame, null), barAnchor: safe(barAnchor, null),
    setInputLock: safe(setInputLock, undefined), typeAndSend, stopGeneration: safe(stopGeneration, undefined),
    isGenerating: safe(isGenerating, false), isBusyNow: safe(isBusyNow, false), isHardGenerating: safe(isHardGenerating, false),
    enforceComposer: safe(enforceComposer, () => ({ ready: false })), ensureComposerReady,
    turnHalted: safe(turnHalted, false), findContinueBtn: safe(findContinueBtn, null), clickContinueBtn: safe(clickContinueBtn, false), clickRetry: safe(clickRetry, false),
    scanError: safe(scanError, ""), isTooLongMsg: safe(isTooLongMsg, false), isBusyMsg: safe(isBusyMsg, false),
    attachImages, clearAttachments: safe(clearAttachments, undefined), conversationKey: safe(conversationKey, ""),
    installSendHooks, findToolBlockSpot: safe(findToolBlockSpot, null),
    diagnostics,
    _debug: { describeDom, messageList, rawRows, authGate },
  };
})();
