// SPDX-License-Identifier: GPL-3.0-or-later
// providers/claude.js — claude.ai / claude.com
// Multi-Script provider interface as chatgpt.js. To disable, remove this file from
// manifest.json, background.js PROVIDER_URLS, popup.js SUPPORTED_HOSTS, main.js AI_SITES.
//
// Works with EVERY Claude model the site offers. The picker is left to the user
// (Haiku / Sonnet / Opus / Fable / Mythos, any generation). Multi-Script never clicks it.
// Family is read from the picker label so timings + prompt size can adapt:
//   haiku  — compact system prompt, tighter idle windows
//   sonnet — default
//   opus / fable / mythos — long thinking / adaptive-reasoning windows
//
// Claude DOM (claude.ai / claude.com, 2026 — shared across models):
//  - User turns: [data-testid="user-message"]
//  - Assistant turns: .font-claude-response (markdown in .standard-markdown)
//  - Composer: ProseMirror contenteditable at the bottom (not inside a turn)
//  - Send: button[aria-label="Send message"] / data-testid="send-button"
//  - Stop: aria-label contains "Stop" ("Stop response" / "Stop generating")
//  - Thinking: [data-is-thinking], [class*="thinking"], [class*="extended-thinking"]
//  - Chat URL: /new, /chat/<uuid>, /project/<uuid>
const ZSProvider = (() => {
  "use strict";
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const waitFor = async (fn, ms) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      try { const v = fn(); if (v) return v; } catch {}
      await sleep(80);
    }
    return fn();
  };

  let diag = () => {};
  const timings = {
    GEN_IDLE_MS: 1600,
    REASON_IDLE_MS: 14000,
    WARMUP_MS: 45000,
    REASON_NOREPLY_MS: 90000,
    STABLE_MS: 8000,
    RESPONSE_TIMEOUT_MS: 300000,
  };

  const S = {
    user: '[data-testid="user-message"], [data-testid="user-turn"], [data-role="user"]',
    assistant: '.font-claude-response, [data-testid="assistant-message"], [data-testid="assistant-turn"], [data-testid="claude-response"], [data-role="assistant"]',
    reply: ".standard-markdown, .font-claude-response, [class*='grid-cols-1'], [data-testid='markdown']",
    // Include locked (contenteditable=false) nodes: startSession locks the
    // composer BEFORE ensureComposerReady, so requiring true would miss it and
    // the core would banner "Couldn't switch Claude into the right mode".
    editor: 'div.ProseMirror, [data-zs-locked="1"], [contenteditable][role="textbox"], div[contenteditable="true"]',
    thinking: '[data-is-thinking="true"], [data-testid*="thinking"], [class*="thinking"], [class*="extended-thinking"], [class*="Thoughts"]',
    artifact: '[data-testid="artifact"], [data-testid*="artifact"], [class*="artifact-content"], [class*="Artifact"]',
    codeWrap: "pre, .code-block, .cm-content",
    errorSurfaces: '[role="alert"], [data-testid*="error"], [class*="error-message"]',
    modelBtn: '[data-testid="model-selector"], [data-testid="model-selector-dropdown"], button[aria-haspopup="listbox"], button[aria-label*="model" i], [class*="model-selector"]',
  };

  const SEND_HARD_CAP = 120000;
  const SEND_MAX_CHARS = 100000;
  const SEND_MAX_LINES = 500;
  const INSERT_CHUNK_LINES = 25;
  const CMD_SHAPE = /"(?:command|tool)"\s*:\s*"|###\s*lua|###mcp_tool###/i;

  const RE = {
    contextLimit: /conversation.{0,20}(too long|limit)|too many (tokens|characters)|maximum.{0,16}(length|context)|context window/i,
    tooLong: /message.{0,20}too long|over the (character|token) limit/i,
    busy: /try again later|capacity|overloaded|usage limit|rate limit|something went wrong|usage cap/i,
    continueBtn: /^(continue|continue generating)$/i,
    modelFamily: /\b(mythos|fable|opus|sonnet|haiku)\b/i,
  };

  // Every current + recent Claude family. Unknown labels fall through to sonnet
  // (the site default) rather than fighting the picker.
  const MODEL_CAPS = {
    haiku:   { GEN_IDLE_MS: 1200, REASON_IDLE_MS: 8000,  WARMUP_MS: 30000, REASON_NOREPLY_MS: 45000,  STABLE_MS: 6000,  RESPONSE_TIMEOUT_MS: 180000, sysMaxChars: 12000, resendEvery: 8 },
    sonnet:  { GEN_IDLE_MS: 1600, REASON_IDLE_MS: 14000, WARMUP_MS: 45000, REASON_NOREPLY_MS: 90000,  STABLE_MS: 8000,  RESPONSE_TIMEOUT_MS: 300000, sysMaxChars: 0,     resendEvery: 0 },
    sonnet5: { GEN_IDLE_MS: 2800, REASON_IDLE_MS: 28000, WARMUP_MS: 90000, REASON_NOREPLY_MS: 240000, STABLE_MS: 14000, RESPONSE_TIMEOUT_MS: 720000, sysMaxChars: 0,     resendEvery: 0 },
    opus:    { GEN_IDLE_MS: 2000, REASON_IDLE_MS: 22000, WARMUP_MS: 60000, REASON_NOREPLY_MS: 180000, STABLE_MS: 10000, RESPONSE_TIMEOUT_MS: 600000, sysMaxChars: 0,     resendEvery: 0 },
    fable:  { GEN_IDLE_MS: 2200, REASON_IDLE_MS: 24000, WARMUP_MS: 70000, REASON_NOREPLY_MS: 210000, STABLE_MS: 12000, RESPONSE_TIMEOUT_MS: 720000, sysMaxChars: 0,     resendEvery: 0 },
    mythos: { GEN_IDLE_MS: 2200, REASON_IDLE_MS: 24000, WARMUP_MS: 70000, REASON_NOREPLY_MS: 210000, STABLE_MS: 12000, RESPONSE_TIMEOUT_MS: 720000, sysMaxChars: 0,     resendEvery: 0 },
  };

  let _family = "sonnet";
  let _modelLabel = "";
  let _sysMaxChars = 0;
  let _resendEvery = 0;

  function currentModelLabel() {
    const tryText = (el) => (el && (el.getAttribute("aria-label") || el.getAttribute("title") || el.textContent) || "").replace(/\s+/g, " ").trim();
    for (const el of document.querySelectorAll(S.modelBtn)) {
      const t = tryText(el);
      if (t && RE.modelFamily.test(t) && t.length < 80) return t;
    }
    // Fallback: any visible control whose label names a Claude family.
    for (const b of document.querySelectorAll("button, [role='button']")) {
      if (b.closest("#rs-root")) continue;
      const t = tryText(b);
      if (t && RE.modelFamily.test(t) && t.length < 64) {
        const r = b.getBoundingClientRect();
        if (r.width > 8 && r.height > 8) return t;
      }
    }
    return _modelLabel;
  }
  function familyFromLabel(label) {
    const s = String(label || "");
    if (/\bmythos\b/i.test(s)) return "mythos";
    if (/\bfable\b/i.test(s)) return "fable";
    if (/\bopus\b/i.test(s)) return "opus";
    if (/\bhaiku\b/i.test(s)) return "haiku";
    if (/\bsonnet\b/i.test(s) && /\b(4(?:\.\d+)?|[5-9](?:\.\d+)?)\b/.test(s)) return "sonnet5";
    if (/\bsonnet\b/i.test(s)) return "sonnet";
    const m = RE.modelFamily.exec(s);
    return m ? m[1].toLowerCase() : "sonnet";
  }
  function applyModelCaps(reason) {
    const label = currentModelLabel();
    const fam = familyFromLabel(label);
    const caps = MODEL_CAPS[fam] || MODEL_CAPS.sonnet;
    const changed = fam !== _family || label !== _modelLabel;
    _family = fam;
    if (label) _modelLabel = label;
    _sysMaxChars = caps.sysMaxChars;
    _resendEvery = caps.resendEvery;
    timings.GEN_IDLE_MS = caps.GEN_IDLE_MS;
    timings.REASON_IDLE_MS = caps.REASON_IDLE_MS;
    timings.WARMUP_MS = caps.WARMUP_MS;
    timings.REASON_NOREPLY_MS = caps.REASON_NOREPLY_MS;
    timings.STABLE_MS = caps.STABLE_MS;
    timings.RESPONSE_TIMEOUT_MS = caps.RESPONSE_TIMEOUT_MS;
    if (changed && label) diag("claude.model", { family: fam, label, reason: reason || "sweep" });
  }

  function truncateForSend(text) {
    { const o = (text && typeof ZS !== "undefined" && ZS.limits) ? ZS.limits.sendOverride(text) : null; if (o !== null) return o; }
    if (!text) return text;
    let s = String(text);
    const cap = _family === "haiku" ? Math.min(SEND_MAX_CHARS, 60000) : SEND_MAX_CHARS;
    if (s.length > cap) s = s.slice(0, cap) + "\n…[truncated]";
    const lines = s.split("\n");
    if (lines.length > SEND_MAX_LINES) s = lines.slice(0, SEND_MAX_LINES).join("\n") + "\n…[truncated]";
    return s;
  }

  function textWithout(root, excludeSel) {
    if (!root) return "";
    let t = "";
    const walk = (n) => {
      if (n.nodeType === 3) { t += n.nodeValue; return; }
      if (n.nodeType !== 1) return;
      if (excludeSel && n.matches && n.matches(excludeSel)) return;
      if (n.classList && n.classList.contains("zs-chip")) return;
      if (n.tagName === "BR") { t += "\n"; return; }
      if (n.classList && n.classList.contains("cm-line")) {
        for (const c of n.childNodes) walk(c);
        t += "\n";
        return;
      }
      const block = /^(P|DIV|LI|PRE|H1|H2|H3|H4|TR|ARTICLE|SECTION)$/.test(n.tagName);
      if (block && t && !t.endsWith("\n")) t += "\n";
      for (const c of n.childNodes) walk(c);
      if (block && t && !t.endsWith("\n")) t += "\n";
    };
    walk(root);
    return t.replace(/\n{3,}/g, "\n\n").trim();
  }

  // Only message bubbles — not [data-role=assistant] on a page-wide wrapper,
  // which would hide the live composer from getEditor().
  const inTurn = (el) => !!(el && el.closest(
    '[data-testid="user-message"], [data-testid="user-turn"], [data-testid="assistant-message"], [data-testid="assistant-turn"], [data-testid="claude-response"], .font-claude-response'
  ));

  function visibleComposer(n) {
    if (!n || n.closest("#rs-root")) return false;
    if (inTurn(n)) return false;
    if (n.closest("pre, .cm-editor, [data-testid='artifact']")) return false;
    return true;
  }
  function getEditor() {
    const all = [...document.querySelectorAll(S.editor)].filter((n) => n && !n.closest("#rs-root"));
    let nodes = all.filter(visibleComposer);
    if (!nodes.length) nodes = all.filter((n) => !inTurn(n));
    if (!nodes.length) nodes = all;
    if (!nodes.length) return null;
    const pm = nodes.filter((n) => (n.classList && n.classList.contains("ProseMirror")) || n.getAttribute("data-zs-locked") === "1");
    const pool = pm.length ? pm : nodes;
    try { pool.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top); } catch {}
    return pool[pool.length - 1] || pool[0] || null;
  }
  const editorText = () => {
    const e = getEditor();
    return e ? (typeof ZS!=='undefined'&&ZS.readComposer?ZS.readComposer(e):e.innerText||e.textContent||'') : '';
  };

  function docPos(a, b) {
    const r = a.compareDocumentPosition(b);
    if (r & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
    if (r & Node.DOCUMENT_POSITION_PRECEDING) return 1;
    return 0;
  }

  const allItems = () => {
    const users = [...document.querySelectorAll(S.user)];
    const asst = [...document.querySelectorAll(S.assistant)];
    const mixed = [...users, ...asst].filter((el, i, arr) => arr.indexOf(el) === i);
    mixed.sort(docPos);
    return mixed;
  };
  const isUserItem = (item) => !!(item && item.matches && item.matches(S.user));
  const isAssistantItem = (item) => !!(item && item.matches && item.matches(S.assistant));
  const assistantItems = () => allItems().filter(isAssistantItem);
  const assistantCount = () => assistantItems().length;
  const userCount = () => allItems().filter(isUserItem).length;
  const lastAssistant = () => {
    const it = assistantItems();
    return it.length ? it[it.length - 1] : null;
  };
  const itemKey = (item) => {
    if (!item || !item.getAttribute) return null;
    return item.getAttribute("data-message-id")
      || item.getAttribute("data-testid") + ":" + (item.textContent || "").slice(0, 24)
      || null;
  };
  const lastAssistantId = () => itemKey(lastAssistant());

  function replyRoot(item) {
    if (!item) return null;
    return item.querySelector(".standard-markdown")
      || item.querySelector("[data-testid='markdown']")
      || item.querySelector(".font-claude-response")
      || item;
  }
  function artifactText(item) {
    if (!item) return "";
    let t = "";
    item.querySelectorAll(S.artifact).forEach((el) => {
      if (el.closest(S.thinking)) return;
      t += "\n" + textWithout(el, S.thinking);
    });
    return t.trim();
  }
  function thinkingText(item) {
    if (!item) return "";
    const nodes = [...item.querySelectorAll(S.thinking)];
    return nodes.map((n) => textWithout(n)).join("\n").trim();
  }
  function itemText(item) {
    if (!item) return "";
    if (isAssistantItem(item)) {
      const md = replyRoot(item);
      const body = textWithout(md, S.thinking);
      const art = artifactText(item);
      return art && !body.includes(art.slice(0, 80)) ? (body + "\n" + art).trim() : body;
    }
    return textWithout(item);
  }
  function classifyText(item, excludeSel) {
    if (!item) return "";
    const skip = [S.thinking, excludeSel].filter(Boolean).join(",");
    if (isAssistantItem(item)) {
      const md = replyRoot(item);
      const body = textWithout(md, skip);
      const art = artifactText(item);
      return art && !body.includes(art.slice(0, 80)) ? (body + "\n" + art).trim() : body;
    }
    return textWithout(item, skip);
  }

  const chatIsEmpty = () => allItems().length === 0;
  const isFreshChat = () => {
    const path = (String(location.pathname || "").replace(/\/+$/, "") || "/");
    return chatIsEmpty() && /(\/(new|chat|project))?$/.test(path) && !!getEditor();
  };
  const conversationKey = () =>
    (/\/(chat|project)\//.test(location.pathname) ? location.pathname : "");

  const composerFrame = () => {
    const ed = getEditor();
    if (!ed) return null;
    return ed.closest("fieldset") || ed.closest("form") || ed.closest("[class*='composer']") || ed.parentElement;
  };
  function barAnchor() {
    const ed = getEditor();
    if (!ed) return null;
    return ed.closest("fieldset") || ed.closest("[class*='composer']") || ed.closest("form") || ed.parentElement;
  }

  let _locked = false;
  function setInputLock(on) {
    _locked = on;
    const ed = getEditor();
    if (!ed) return;
    ed.setAttribute("contenteditable", on ? "false" : "true");
    if (on) ed.setAttribute("data-zs-locked", "1");
    else ed.removeAttribute("data-zs-locked");
  }

  function visibleBtn(b) {
    if (!b || b.disabled || b.closest('#zs-root,#zs-bar,#zs-input-cover')) return false;
    if (b.getAttribute("aria-disabled") === "true") return false;
    const r = b.getBoundingClientRect();
    return r.width > 8 && r.height > 8;
  }
  function labelOf(b) {
    return ((b && (b.getAttribute("aria-label") || b.getAttribute("title") || b.textContent)) || "").toLowerCase();
  }
  function stopButton() {
    for (const s of [
      'button[data-testid="stop-button"]',
      'button[aria-label*="Stop response" i]',
      'button[aria-label*="Stop generating" i]',
      'button[aria-label*="Stop" i]',
    ]) {
      for (const b of document.querySelectorAll(s)) {
        if (visibleBtn(b) && !inTurn(b)) return b;
      }
    }
    for (const b of document.querySelectorAll("button")) {
      if (!visibleBtn(b) || inTurn(b)) continue;
      const l = labelOf(b);
      if (l.includes("stop") && (l.includes("response") || l.includes("generat") || l === "stop")) return b;
    }
    return null;
  }
  function sendButton() {
    if (stopButton()) return null;
    const sels = [
      'button[aria-label="Send message"]',
      'button[aria-label="Send Message"]',
      'button[aria-label*="Send message" i]',
      'button[data-testid="send-button"]',
    ];
    for (const s of sels) {
      for (const b of document.querySelectorAll(s)) {
        if (visibleBtn(b) && !inTurn(b) && !labelOf(b).includes("stop")) return b;
      }
    }
    const ed = getEditor();
    const root = (ed && (ed.closest("fieldset") || ed.closest("form") || ed.parentElement)) || document;
    const buttons = [...root.querySelectorAll("button")].filter((b) => visibleBtn(b) && !inTurn(b));
    for (const b of buttons) {
      const l = labelOf(b);
      if (l.includes("send") && !l.includes("stop")) return b;
    }
    return buttons.find(b=>b.type==='submit'&&!b.closest('#zs-root,#zs-bar'))||null;
  }

  function streamText(item) {
    if (!item) return "";
    const reply = itemText(item);
    const think = thinkingText(item);
    return think ? (think + "\n" + reply) : reply;
  }
  const streamLen = (item) => streamText(item === undefined ? lastAssistant() : item).length;
  let _streamMax = -1, _streamAt = 0, _streamItem = null;
  function sampleStream() {
    const item = lastAssistant();
    const len = streamText(item).length;
    const now = Date.now();
    if (item !== _streamItem || len < _streamMax - 400) {
      _streamItem = item; _streamMax = len; _streamAt = now; return;
    }
    if (len > _streamMax) { _streamMax = len; _streamAt = now; }
  }
  function isGenerating() {
    sampleStream();
    if (stopButton()) return true;
    const last = lastAssistant();
    if (last && last.querySelector('[data-is-thinking="true"], [data-thinking="true"], [data-is-streaming="true"]')) return true;
    return _streamMax > 1 && Date.now() - _streamAt < timings.GEN_IDLE_MS;
  }
  const isBusyNow = () => isGenerating();
  const isHardGenerating = () => !!stopButton();

  function snapshot() {
    try {
      const it = lastAssistant();
      if (!it) return { th: 0, rp: 0 };
      return { th: thinkingText(it).length, rp: itemText(it).length };
    } catch { return {}; }
  }
  function readAssistant() {
    const item = lastAssistant();
    if (!item) return { present: false, reply: "", thinking: "", item: null };
    return { present: true, reply: itemText(item), thinking: thinkingText(item), item };
  }

  function selectAll(ed) {
    ed.focus();
    const range = document.createRange();
    range.selectNodeContents(ed);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }
  async function typeEditorText(ed, text,controls={}) {
    selectAll(ed);
    if(String(text).length<=24000){document.execCommand('insertText',false,String(text));return;}
    const lines=String(text).split('\n'),frame=composerFrame(),route=location.pathname,normalize=t=>String(t).replace(/\u00a0/g,' ').trimEnd();let written='';
    for(let i=0;i<lines.length;i+=INSERT_CHUNK_LINES){
      if(controls.cancelled?.()||location.pathname!==route)throw Error('Claude input cancelled or chat changed before Send.');
      if(i){
        const next=getEditor();
        if(!next||normalize(editorText())!==normalize(written)||next!==ed&&(ed.isConnected||!frame?.isConnected||!frame.contains(next)))throw Error('Claude draft changed while inserting the complete message. Nothing was sent.');
        ed=next;ed.focus();let last=ed;while(last.lastChild)last=last.lastChild;
        const range=document.createRange();if(last.nodeType===3)range.setStart(last,last.nodeValue.length);else if(last.nodeName==='BR')range.setStartBefore(last);else range.selectNodeContents(last),range.collapse(false);
        range.collapse(true);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);
      }
      const chunk=lines.slice(i,i+INSERT_CHUNK_LINES).join('\n')+(i+INSERT_CHUNK_LINES<lines.length?'\n':'');
      document.execCommand('insertText',false,chunk);written+=chunk;await sleep(0);
    }
  }

  function fileFromImage(img, i) {
    const mime = img.mimeType || "image/jpeg";
    const bin = atob(img.data);
    const arr = new Uint8Array(bin.length);
    for (let j = 0; j < bin.length; j++) arr[j] = bin.charCodeAt(j);
    const ext = mime.includes("png") ? "png" : "jpg";
    return new File([arr], `orscript_${Date.now()}_${i}.${ext}`, { type: mime });
  }
  async function attachImages(images) {
    const ed = getEditor();
    if (!ed || !images || !images.length) return false;
    const dt = new DataTransfer();
    images.forEach((img, i) => { try { dt.items.add(fileFromImage(img, i)); } catch {} });
    if (!dt.items.length) return false;
    ed.focus();
    ed.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    const fileInput = document.querySelector('input[type="file"][accept*="image"]') ||
      document.querySelector('input[type="file"]');
    if (fileInput) {
      try { fileInput.files = dt.files; fileInput.dispatchEvent(new Event("change", { bubbles: true })); } catch {}
    }
    return await waitFor(() => {
      const box = composerFrame();
      return !!(box && box.querySelector("img, [class*='preview'], [class*='thumbnail'], [class*='attachment']"));
    }, 15000);
  }
  function clearAttachments() {
    try {
      const box = composerFrame();
      if (!box) return;
      box.querySelectorAll("[aria-label*='emove' i], [aria-label*='elete' i], [aria-label*='Remove'], [class*='delete'], [class*='remove']")
        .forEach((d) => { try { d.click(); } catch {} });
    } catch {}
  }

  let internalSend=false,sendInFlight=false;
  async function typeAndSend(text, images,controls={}) {
    const fail=(message,state='not-sent')=>Object.assign(Error(message),{retryable:false,sendState:state});
    if(sendInFlight)throw fail('Claude already has a send in progress.');
    let ed = getEditor();
    if (!ed) throw fail('Claude input box not found');
    if(stopButton())throw fail('Claude is still responding.');
    text = truncateForSend(String(text).replace(/\r\n?/g,'\n'));
    const relock = _locked,frame=composerFrame(),route=location.pathname;
    const normalize=t=>String(t).replace(/\r\n?/g,'\n').replace(/\u00a0/g,' ').trimEnd();
    let clicked=false;
    const check=()=>{
      if(controls.cancelled?.())throw fail('Claude send cancelled.',clicked?'unconfirmed':'not-sent');
      if(!clicked&&location.pathname!==route)throw fail('Claude chat changed. Draft preserved.');
      if(!clicked&&getEditor()!==ed){const next=getEditor();if(!ed.isConnected&&next&&frame?.isConnected&&frame.contains(next)&&normalize(editorText())===normalize(text))ed=next;else throw fail('Claude composer changed. Draft preserved.');}
    };
    sendInFlight=true;
    ed.setAttribute('contenteditable','true');
    try {
      await typeEditorText(ed, text,controls);
      check();
      if (images && images.length) {
        if(!await attachImages(images))throw fail('Claude did not accept the image attachment. Draft preserved.');
      }
      await waitFor(()=>{check();return !!sendButton();},images?.length?30000:10000);
      if(!await waitFor(()=>{check();return normalize(editorText())===normalize(text);},1500))throw fail('Claude did not retain the complete task and instructions. Nothing was sent.');
      check();if(stopButton())throw fail('Claude resumed responding before Send. Draft preserved.');
      const btn = sendButton();
      if(!btn)throw fail('Claude send control is not ready. Draft preserved.');
      const users=userCount();clicked=true;internalSend=true;
      try{btn.click();}finally{internalSend=false;}
      if(await waitFor(()=>{if(getEditor()===ed&&!editorText().trim()||userCount()>users)return true;check();return false;},8000))return true;
      throw fail('Claude Send was clicked but acknowledgement is uncertain. Check the conversation before retrying.','unconfirmed');
    }catch(error){if(error.sendState)throw error;throw fail(error.message||String(error),clicked?'unconfirmed':'not-sent');
    } finally {
      sendInFlight=false;
      if (relock) { const e2 = getEditor(); if (e2) e2.setAttribute("contenteditable", "false"); }
    }
  }
  function stopGeneration() {
    const b = stopButton();
    if (b) try { b.click(); } catch {}
  }
  function enforceComposer() {
    applyModelCaps("sweep");
    // Never refuse a sweep because the picker label is unknown — the user owns the model.
    return { ready: !!getEditor() };
  }
  async function ensureComposerReady(reason) {
    applyModelCaps(reason || "ready");
    // startSession locks the box first. Wait for the (possibly locked) composer;
    // do not gate Start on Haiku/Sonnet/Opus/Fable/Mythos — any of them is fine.
    let ed = getEditor();
    if (!ed) {
      await waitFor(() => getEditor(), 5000);
      ed = getEditor();
    }
    const ready = !!ed;
    diag("mode_ready", { reason, provider: "claude", family: _family, model: _modelLabel, ready });
    return { ready };
  }

  function scanError() {
    try {
      for (const el of document.querySelectorAll(S.errorSurfaces)) {
        if (el.offsetParent === null) continue;
        const t = (el.innerText || "").trim();
        if (t.length > 8 && t.length < 600 && RE.contextLimit.test(t)) return t.slice(0, 240);
      }
    } catch {}
    return "";
  }
  const isTooLongMsg = (t) => RE.tooLong.test(t || "");
  const isBusyMsg = (t) => RE.busy.test(t || "");
  const turnHalted = () => false;
  const findContinueBtn = () => {
    for (const b of document.querySelectorAll("button")) {
      if (visibleBtn(b) && RE.continueBtn.test((b.textContent || "").trim())) return b;
    }
    return null;
  };
  const clickContinueBtn = () => { const b = findContinueBtn(); if (b) b.click(); };

  function installSendHooks(handlers) {
    document.addEventListener("keydown", (e) => {
      if(internalSend)return;
      if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
      const ed = getEditor();
      if (!ed || !ed.contains(e.target)) return;
      if (editorText().trim() === "") return;
      if (handlers.isBlocked()) {e.preventDefault();e.stopImmediatePropagation();handlers.onBlockedAttempt?.();return;}
      if (!handlers.isStarted()) {
        if (!chatIsEmpty()) return;
        handlers.onBlockedAttempt();
        return;
      }
      handlers.onUserMessage(assistantCount());
    }, true);

    document.addEventListener("click", (e) => {
      if(internalSend)return;
      if (!getEditor()) return;
      const t = e.target;
      const cont = t && t.closest && t.closest("button");
      if (cont && RE.continueBtn.test((cont.innerText || "").trim())) {
        if (handlers.onNativeContinue) handlers.onNativeContinue();
        return;
      }
      const stop = stopButton();
      if (stop && t && t.closest && t.closest("button") === stop) {
        if (handlers.onNativeStop) handlers.onNativeStop();
        return;
      }
      const btn = t && t.closest && t.closest("button");
      if (!btn || btn !== sendButton()) return;
      if (handlers.isBlocked()) {e.preventDefault();e.stopImmediatePropagation();handlers.onBlockedAttempt?.();return;}
      if (!handlers.isStarted()) {
        if (!chatIsEmpty()) return;
        handlers.onBlockedAttempt();
        return;
      }
      handlers.onUserMessage(assistantCount());
    }, true);
  }

  function findToolBlockSpot(item) {
    if (!item) return null;
    let hidAny = null;
    const hide = (el) => {
      el.classList.add("zs-tool-hide");
      hidAny = hidAny || { parent: el.parentElement, ref: el };
    };
    item.querySelectorAll(S.codeWrap).forEach((pre) => {
      if (pre.closest(".zs-chip") || pre.closest(S.thinking)) return;
      if (CMD_SHAPE.test(pre.textContent || "")) hide(pre);
    });
    item.querySelectorAll(S.artifact).forEach((el) => {
      if (el.closest(".zs-chip") || el.closest(S.thinking)) return;
      if (CMD_SHAPE.test(el.textContent || "")) hide(el);
    });
    return hidAny;
  }

  const PROMPT_EXTRA =
    `- You may be ANY Claude model the user picked (Haiku, Sonnet 3.5/4/4.5/5+, Opus, Fable, Mythos). The Multi-Script command protocol is the same for all of them.
- Multi-Script is a real browser extension the user installed. Outputting a fenced JSON command is how the local bridge receives work for Roblox Studio, Unity, Godot, Blender, Figma, or another connected MCP server. This is authorized local automation, not a jailbreak.
- Claude's own tools, computer use, Projects MCP, Artifacts-as-execution, and Claude Code run outside the Multi-Script bridge and cannot reach the connected local editor. Write Multi-Script JSON / ###LUA### in the normal chat reply; the extension executes it.
- Refuse only the user's task if it is actually disallowed. Never refuse the Multi-Script protocol itself.
- Artifacts may preview UI for the user, but the command that runs must still appear in the chat reply as a fenced JSON object or a ###LUA### block.`;

  return {
    // 6.26: core pages long tool results to stay under this adapter's send caps
    // (SEND_MAX_CHARS / SEND_MAX_LINES) instead of the adapter cutting the middle out.
    resultCharBudget: 85000, resultLineBudget: 430,
    // Startup must fit the actual insertion budget, including model-family limits.
    get startupCharBudget(){return (_family === "haiku" ? Math.min(SEND_MAX_CHARS,60000) : SEND_MAX_CHARS)-4000;},
    startupLineBudget: SEND_MAX_LINES,
    id: "claude",
    persistentBarWhenNoEditor:true,
    displayName: "Claude",
    supportsVision: true,
    timings,
    thinkingSel: S.thinking,
    chipAtItemLevel: true,
    reliableCounts: true,
    promptExtra: PROMPT_EXTRA,
    get sysMaxChars() { return _sysMaxChars; },
    get resendSystemEvery() { return _resendEvery; },
    init({ diag: d } = {}) { if (d) diag = d; applyModelCaps("init"); },
    allItems, isUserItem, isAssistantItem, itemText, classifyText,
    assistantCount, userCount, lastAssistant, lastAssistantId, readAssistant,
    streamLen, snapshot,
    getEditor, editorText, chatIsEmpty, isFreshChat, composerFrame, barAnchor,
    setInputLock, typeAndSend, stopGeneration,
    isGenerating, isBusyNow, isHardGenerating,
    enforceComposer, ensureComposerReady,
    turnHalted, findContinueBtn, clickContinueBtn,
    scanError, isTooLongMsg, isBusyMsg,
    attachImages, clearAttachments, conversationKey,
    installSendHooks, findToolBlockSpot,
  };
})();
