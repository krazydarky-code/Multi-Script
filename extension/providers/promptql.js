// SPDX-License-Identifier: GPL-3.0-or-later
// providers/promptql.js — PromptQL (prompt.ql.app, Hasura)
// Multi-Script provider interface as chatgpt.js / claude.js. To disable, remove
// this file from manifest.json, background.js PROVIDER_URLS, popup.js
// SUPPORTED_HOSTS and main.js AI_SITES.
//
// PromptQL DOM (validated live on prompt.ql.app, 2026-10, Grok 4.5 default):
//  - Every turn: .kb-nav-thread-message-item  (data-kb-nav-id="message:<uuid>")
//      user  → contains .user-message-bubble
//      agent → contains [data-testid="agent-response-bubble"]
//  - Reply markdown: .response-output (.wmde-markdown); the agent bubble also
//    holds an avatar, model label, "Details" trace and a "Working · Ns" status,
//    which are NOT the answer and are excluded.
//  - Composer: tiptap .ProseMirror[role=textbox] inside [class*=_chatBoxPaper_]
//    (CSS-module hash suffixes change; only the stable prefix is used).
//  - Bot routing: the "@<Bot>" mention chip [data-testid="chat-box:promptql-toggle"].
//    When it is OFF the message goes to the humans in the room, not the AI —
//    the paper then lacks the _promptQLActive_ class. We switch it on.
//  - Send: Enter or the last button in the paper. Generating: the paper's last
//    button becomes [data-testid="chat-box:stop-button"]; the agent turn shows
//    [data-testid="agent-compact-status"] / "Working".
//  - Errors: [data-testid="error-message:retry-button"] (+ suspended/billing
//    [data-testid^="chat-suspended-status"]).
//  - URLs: /project/<p>/private/new (fresh) → /project/<p>/<room>/bot/<thread>.
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
  const timings = {
    GEN_IDLE_MS: 1800,
    REASON_IDLE_MS: 20000,
    WARMUP_MS: 60000,         // the agent shows "Working" a while before any text
    REASON_NOREPLY_MS: 180000,
    STABLE_MS: 10000,
    RESPONSE_TIMEOUT_MS: 420000,
  };

  const S = {
    item: ".kb-nav-thread-message-item",
    userMark: ".user-message-bubble",
    agentMark: '[data-testid="agent-response-bubble"]',
    reply: ".response-output",
    paper: '[class*="_chatBoxPaper_"]',
    editor: '.tiptap.ProseMirror, .ProseMirror[role="textbox"], [data-zs-locked="1"]',
    toggle: '[data-testid="chat-box:promptql-toggle"]',
    stop: '[data-testid="chat-box:stop-button"], [data-testid="plan-trace:stop"]',
    working: '[data-testid="agent-compact-status"], [data-testid="agent-response:status-tip"]',
    thinking: '[data-testid="agent-response:details-toggle"], [data-testid*="plan-trace"], [data-testid="chat-response:thinking-tip"], [data-testid="agent-compact-status"]',
    retry: '[data-testid="error-message:retry-button"]',
    suspended: '[data-testid^="chat-suspended-status"]',
    errorSurfaces: '[role="alert"], .mantine-Notification-root, [class*="mantine-Alert"], [data-testid^="error-message"]',
    codeWrap: "pre, .code-block, .cm-content",
    attachInput: 'input[type="file"]',
  };

  // Conservative caps until PromptQL publishes a message limit; the core pages
  // longer tool results (resultCharBudget) instead of cutting them.
  // Live test (2026-10): a 27k-char message was stored as ~10k. Longer
  // messages are therefore sent as several parts: every part but the last goes
  // to the room with the @Bot chip OFF (the bot does not answer it but reads it
  // as thread context), the last part goes to the bot.
  const SEND_MAX_CHARS = 120000;
  const SEND_MAX_LINES = 3000;
  const PART_CHARS = 9000;
  const CMD_SHAPE = /"(?:command|tool)"\s*:\s*"|###\s*lua|###mcp_tool###/i;

  const RE = {
    contextLimit: /conversation.{0,20}(too long|limit)|context (window|length).{0,20}(exceeded|limit)|maximum.{0,16}(length|context)|too many tokens/i,
    tooLong: /message.{0,20}too long|over the (character|token) limit/i,
    busy: /too many requests|rate.?limit|try again (later|in a moment)|wait a moment and try again|something went wrong|temporarily unavailable|overloaded|at capacity|network error|failed to (send|generate)|an error occurred/i,
    continueBtn: /^(continue|continue generating)$/i,
  };

  // ── text helpers ──────────────────────────────────────────────────────────
  function textWithout(root, excludeSel) {
    if (!root) return "";
    let t = "";
    const walk = (n) => {
      if (n.nodeType === 3) { t += n.nodeValue; return; }
      if (n.nodeType !== 1) return;
      if (excludeSel && n.matches && n.matches(excludeSel)) return;
      if (n.classList && n.classList.contains("zs-chip")) return;
      // "@Bot" mention chips at the start of user turns are routing, not text.
      if (typeof n.className === "string" && n.className.indexOf("_inlineChip_") !== -1) return;
      if (n.tagName === "BR") { t += "\n"; return; }
      const block = /^(P|DIV|LI|PRE|H1|H2|H3|H4|H5|TR|ARTICLE|SECTION|BLOCKQUOTE|UL|OL|TABLE)$/.test(n.tagName);
      if (block && t && !t.endsWith("\n")) t += "\n";
      for (const c of n.childNodes) walk(c);
      if (block && t && !t.endsWith("\n")) t += "\n";
    };
    walk(root);
    return t.replace(/\n{3,}/g, "\n\n").trim();
  }

  // ── turns ─────────────────────────────────────────────────────────────────
  const isUserItem = (item) => !!(item && item.querySelector && item.querySelector(S.userMark) && !item.querySelector(S.agentMark));
  const isAssistantItem = (item) => !!(item && item.querySelector && item.querySelector(S.agentMark));
  const allItems = () => [...document.querySelectorAll(S.item)].filter((i) => isUserItem(i) || isAssistantItem(i));
  const assistantItems = () => allItems().filter(isAssistantItem);
  const assistantCount = () => assistantItems().length;
  const userCount = () => allItems().filter(isUserItem).length;
  const lastAssistant = () => { const a = assistantItems(); return a.length ? a[a.length - 1] : null; };
  const itemKey = (item) => {
    if (!item || !item.getAttribute) return null;
    const k = item.getAttribute("data-kb-nav-id");
    if (k) return k;
    const b = item.querySelector("[data-block-id]");
    return b ? "block:" + b.getAttribute("data-block-id") : null;
  };
  const lastAssistantId = () => itemKey(lastAssistant());

  function replyText(item, extraSkip) {
    if (!item) return "";
    const skip = [S.thinking, extraSkip].filter(Boolean).join(",");
    const outs = [...item.querySelectorAll(S.reply)].filter((o) => !o.parentElement || !o.parentElement.closest(S.reply));
    return outs.map((o) => textWithout(o, skip)).filter(Boolean).join("\n\n").trim();
  }
  function itemText(item) {
    if (!item) return "";
    if (isAssistantItem(item)) return replyText(item);
    const bubble = item.querySelector(S.userMark);
    const r = bubble && bubble.querySelector(S.reply);
    return textWithout(r || bubble || item);
  }
  function classifyText(item, excludeSel) {
    if (!item) return "";
    if (isAssistantItem(item)) return replyText(item, excludeSel);
    const bubble = item.querySelector(S.userMark);
    const r = bubble && bubble.querySelector(S.reply);
    return textWithout(r || bubble || item, excludeSel);
  }
  function thinkingText(item) {
    if (!item) return "";
    // The live "Working" status counts as reasoning so the core waits through
    // PromptQL's tool/plan phase instead of declaring an empty turn.
    const w = item.querySelector(S.working);
    return w ? (w.textContent || "working").trim() : "";
  }

  // ── composer ──────────────────────────────────────────────────────────────
  const inTurn = (el) => !!(el && el.closest && el.closest(S.item + ", [data-testid='inline-message-editor:root']"));
  function getEditor() {
    const all = [...document.querySelectorAll(S.editor)].filter((n) => !n.closest("#rs-root") && !inTurn(n));
    if (!all.length) return null;
    const inPaper = all.filter((n) => n.closest(S.paper));
    const pool = inPaper.length ? inPaper : all;
    try { pool.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top); } catch {}
    return pool[pool.length - 1];
  }
  const editorText = () => { const e = getEditor(); return e ? (e.textContent || "") : ""; };
  const paper = () => { const e = getEditor(); return (e && e.closest(S.paper)) || null; };
  const composerFrame = () => paper() || (getEditor() && getEditor().parentElement) || null;
  const barAnchor = () => paper() || (getEditor() && getEditor().parentElement) || null;

  const chatIsEmpty = () => allItems().length === 0;
  const isFreshChat = () => chatIsEmpty() && !!getEditor() && (/\/new\/?$/.test(location.pathname) || !/\/bot\//.test(location.pathname));
  const conversationKey = () => (/\/bot\/[^/]+/.test(location.pathname) ? location.pathname : "");

  let _locked = false;
  function setInputLock(on) {
    _locked = on;
    const ed = getEditor();
    if (!ed) return;
    ed.setAttribute("contenteditable", on ? "false" : "true");
    if (on) ed.setAttribute("data-zs-locked", "1"); else ed.removeAttribute("data-zs-locked");
  }

  const visible = (b) => { if (!b) return false; const r = b.getBoundingClientRect(); return r.width > 4 && r.height > 4; };
  function stopButton() {
    for (const b of document.querySelectorAll(S.stop)) if (visible(b) && !inTurn(b)) return b;
    return null;
  }
  function sendButton() {
    const p = paper();
    if (!p) return null;
    const btns = [...p.querySelectorAll("button")].filter((b) => visible(b) && !b.getAttribute("data-testid"));
    const b = btns[btns.length - 1] || null;
    if (!b || b.matches(S.stop)) return null;
    return b;
  }
  // The AI only answers when its @mention chip is active.
  function botActive() {
    const p = paper();
    if (!p) return true;
    if (!p.querySelector(S.toggle)) return true; // DM with the bot / no chip shown
    return /_promptQLActive_/.test(p.className || "");
  }
  async function setBotActive(want) {
    if (botActive() === want) return true;
    const t = paper() && paper().querySelector(S.toggle);
    if (!t) return want;
    try { t.click(); } catch {}
    return !!(await waitFor(() => botActive() === want, 1500));
  }
  function splitParts(text) {
    const s = String(text);
    if (s.length <= PART_CHARS) return [s];
    const parts = [];
    let i = 0;
    while (i < s.length) {
      let end = Math.min(s.length, i + PART_CHARS - 120);
      if (end < s.length) { const nl = s.lastIndexOf("\n", end); if (nl > i + PART_CHARS / 2) end = nl; }
      parts.push(s.slice(i, end));
      i = end;
    }
    const n = parts.length;
    return parts.map((p, k) => k < n - 1
      ? `[Multi-Script message part ${k + 1}/${n} - context only, the bot answers after part ${n}]\n` + p
      : `[Multi-Script message part ${n}/${n} - read parts 1-${n - 1} above in this thread as ONE message, then answer]\n` + p);
  }
  async function ensureBotActive() {
    if (botActive()) return true;
    const t = paper() && paper().querySelector(S.toggle);
    if (t) { try { t.click(); } catch {} }
    const ok = await waitFor(botActive, 1500);
    diag("promptql.botToggle", { ok: !!ok });
    return !!ok;
  }

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
      // First observation of an already-finished turn is not "streaming".
      const first = _streamMax < 0;
      _streamItem = item; _streamMax = len; _streamAt = first ? 0 : now; return;
    }
    if (len > _streamMax) { _streamMax = len; _streamAt = now; }
  }
  function isGenerating() {
    sampleStream();
    if (stopButton()) return true;
    const last = lastAssistant();
    if (last && last.querySelector(S.working)) return true;
    return _streamMax > 1 && Date.now() - _streamAt < timings.GEN_IDLE_MS;
  }
  const isBusyNow = () => isGenerating();
  const isHardGenerating = () => !!stopButton();
  function snapshot() {
    try { const it = lastAssistant(); return it ? { th: thinkingText(it).length, rp: replyText(it).length } : { th: 0, rp: 0 }; } catch { return {}; }
  }
  function readAssistant() {
    const item = lastAssistant();
    if (!item) return { present: false, reply: "", thinking: "", item: null };
    let reply = replyText(item);
    // An error card inside the turn (retry button) is a site failure, not an
    // answer: surface its text so the core classifies it as "busy".
    if (!reply && item.querySelector(S.retry)) {
      const card = item.querySelector(S.retry).closest("[class*='Alert'], [class*='error'], div");
      reply = ((card && card.innerText) || "Something went wrong. Try again later.").trim().slice(0, 240);
    }
    return { present: true, reply, thinking: thinkingText(item), item };
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
  const norm = (s) => String(s || "").replace(/\s+/g, "");
  function selectAll(ed) {
    const range = document.createRange();
    range.selectNodeContents(ed);
    const sel = window.getSelection();
    sel.removeAllRanges(); sel.addRange(range);
  }
  function clearEditor(ed) {
    try { ed.focus(); selectAll(ed); document.execCommand("delete"); } catch {}
  }
  // Paste first (one transaction, no @mention / slash-menu triggers, fast for
  // big results); fall back to line-by-line insertText. Verified either way.
  async function fillEditor(ed, text) {
    ed.focus();
    clearEditor(ed);
    try {
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      ed.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    } catch {}
    await sleep(60);
    const want = norm(text);
    const got = () => norm(ed.textContent);
    if (got() && (got() === want || got().length >= want.length * 0.98)) return true;
    clearEditor(ed);
    const lines = String(text).split("\n");
    for (let i = 0; i < lines.length; i++) {
      if (lines[i]) document.execCommand("insertText", false, lines[i]);
      if (i < lines.length - 1) document.execCommand("insertLineBreak");
      if (i && i % 40 === 0) await sleep(0);
    }
    await sleep(40);
    return got().length >= want.length * 0.98;
  }
  function closeMentionPopups() {
    // tiptap suggestion menus (@ / /) can swallow Enter; Escape closes them.
    try {
      const ed = getEditor();
      if (document.querySelector(".tippy-box, [data-tippy-root], [role='listbox']")) {
        ed && ed.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true }));
      }
    } catch {}
  }

  async function typeAndSend(text, images) {
    text = truncateForSend(text);
    const parts = splitParts(text);
    if (parts.length > 1) {
      diag("promptql.parts", { n: parts.length, len: String(text).length });
      for (let k = 0; k < parts.length - 1; k++) {
        await setBotActive(false);
        await sendOne(parts[k], null);
        await waitFor(() => !norm(editorText()), 4000);
        await sleep(900);
      }
      await setBotActive(true);
      return sendOne(parts[parts.length - 1], images);
    }
    await ensureBotActive();
    return sendOne(text, images);
  }
  async function sendOne(text, images) {
    let ed = getEditor();
    if (!ed) { await waitFor(() => getEditor(), 4000); ed = getEditor(); }
    if (!ed) throw new Error("PromptQL input box not found");
    const relock = _locked;
    if (relock) ed.setAttribute("contenteditable", "true");
    try {
      const ok = await fillEditor(ed, text);
      if (!ok) { diag("promptql.fillShort", { want: text.length, got: (ed.textContent || "").length }); }
      if (!norm(ed.textContent)) throw new Error("PromptQL composer did not accept the text");
      if (images && images.length) { try { await attachImages(images); } catch {} }
      closeMentionPopups();
      // Send button first (enabled once text is in), Enter as fallback.
      const btn = await waitFor(() => { const b = sendButton(); return b && !b.disabled ? b : null; }, images && images.length ? 20000 : 2500);
      if (btn) btn.click();
      else {
        const o = { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true };
        ed.dispatchEvent(new KeyboardEvent("keydown", o));
        ed.dispatchEvent(new KeyboardEvent("keyup", o));
      }
      const sent = await waitFor(() => !norm(editorText()) || !!stopButton(), 3000);
      if (!sent) {
        const o = { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true };
        const e2 = getEditor(); if (e2) { e2.focus(); e2.dispatchEvent(new KeyboardEvent("keydown", o)); }
      }
    } finally {
      if (relock) { const e2 = getEditor(); if (e2) e2.setAttribute("contenteditable", "false"); }
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
    const input = (paper() && paper().parentElement && paper().parentElement.querySelector(S.attachInput)) || document.querySelector(S.attachInput);
    if (input) { try { input.files = dt.files; input.dispatchEvent(new Event("change", { bubbles: true })); } catch {} }
    else ed.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    return !!(await waitFor(() => document.querySelector('[data-testid="promptql-chat-box:image-upload-thumbnail"], [data-testid="promptql-chat-box:upload-preview"]'), 15000));
  }
  function clearAttachments() {
    try { document.querySelectorAll('[data-testid="promptql-chat-box:remove-attachment-btn"]').forEach((b) => b.click()); } catch {}
  }

  async function ensureComposerReady(reason) {
    let ed = getEditor();
    if (!ed) { await waitFor(() => getEditor(), 6000); ed = getEditor(); }
    const bot = ed ? await ensureBotActive() : false;
    diag("mode_ready", { reason, provider: "promptql", ready: !!ed, bot });
    return { ready: !!ed };
  }
  function enforceComposer() { return { ready: !!getEditor() }; }

  function scanError() {
    try {
      const sus = document.querySelector(S.suspended);
      if (sus && visible(sus)) return "PromptQL suspended this chat (billing/usage): " + (sus.innerText || "").trim().slice(0, 200);
      for (const el of document.querySelectorAll(S.errorSurfaces)) {
        if (!visible(el) || el.closest("#rs-root")) continue;
        const t = (el.innerText || "").trim();
        if (t.length > 8 && t.length < 600 && RE.contextLimit.test(t)) return t.slice(0, 240);
      }
    } catch {}
    return "";
  }
  const isTooLongMsg = (t) => RE.tooLong.test(t || "");
  const isBusyMsg = (t) => RE.busy.test(t || "");
  const turnHalted = () => false;
  // Site-native retry for a failed turn — the core prefers this over re-sending.
  function clickRetry() {
    const last = lastAssistant();
    const b = (last && last.querySelector(S.retry)) || document.querySelector(S.retry);
    if (b && visible(b)) { try { b.click(); return true; } catch {} }
    return false;
  }
  const findContinueBtn = () => {
    for (const b of document.querySelectorAll("button")) if (visible(b) && RE.continueBtn.test((b.textContent || "").trim())) return b;
    return null;
  };
  const clickContinueBtn = () => { const b = findContinueBtn(); if (b) { b.click(); return true; } return false; };

  function installSendHooks(handlers) {
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
      const ed = getEditor();
      if (!ed || !ed.contains(e.target)) return;
      if (editorText().trim() === "") return;
      if (handlers.isBlocked()) return;
      if (!handlers.isStarted()) { if (!chatIsEmpty()) return; handlers.onBlockedAttempt(); return; }
      handlers.onUserMessage(assistantCount());
    }, true);
    document.addEventListener("click", (e) => {
      if (!getEditor()) return;
      const btn = e.target && e.target.closest && e.target.closest("button");
      if (!btn) return;
      const stop = stopButton();
      if (stop && btn === stop) { if (handlers.onNativeStop) handlers.onNativeStop(); return; }
      if (btn !== sendButton()) return;
      if (handlers.isBlocked()) return;
      if (!handlers.isStarted()) { if (!chatIsEmpty()) return; handlers.onBlockedAttempt(); return; }
      handlers.onUserMessage(assistantCount());
    }, true);
  }

  function findToolBlockSpot(item) {
    if (!item) return null;
    let hid = null;
    item.querySelectorAll(S.codeWrap).forEach((pre) => {
      if (pre.closest(".zs-chip") || pre.closest(S.thinking)) return;
      if (CMD_SHAPE.test(pre.textContent || "")) { pre.classList.add("zs-tool-hide"); hid = hid || { parent: pre.parentElement, ref: pre }; }
    });
    return hid;
  }

  const PROMPT_EXTRA =
    `- ABOUT THIS CHAT: the user is driving this conversation through Multi-Script, a browser extension THEY installed and run on their own computer. It copies the JSON command you write into their own local editor (Roblox Studio, Unity, Godot, Blender or a code folder) and pastes the real output back as their next message ("Output of '<name>': ..."). Nothing is scraped and nothing runs on PromptQL's side - it is the same as the user copy-pasting your answer themselves, just faster.
- Treat each "Output of ..." message as the user's genuine result from their machine. Read it and continue the task.
- Do NOT use PromptQL's own data tools, query plans, Python sandbox, artifacts or database connectors for this work - they cannot reach the user's editor. Just write the command in your reply.
- Write exactly ONE command per reply as a plain-text JSON object {"command": "...", "params": {...}} (no code fence, no artifact, no extra commentary in a command turn), then stop and wait for the output.
- When the work is done, answer in plain text with no JSON.`;

  return {
    startupLineBudget: SEND_MAX_LINES,
    id: "promptql",
    displayName: "PromptQL",
    supportsVision: true,
    timings,
    thinkingSel: S.thinking,
    chipAtItemLevel: true,
    reliableCounts: true,
    resultCharBudget: 8500, resultLineBudget: 380,
    minSendGapMs: 2500,
    promptExtra: PROMPT_EXTRA,
    init({ diag: d } = {}) { if (d) diag = d; },
    allItems, isUserItem, isAssistantItem, itemText, classifyText,
    assistantCount, userCount, lastAssistant, lastAssistantId, readAssistant,
    streamLen, snapshot,
    getEditor, editorText, chatIsEmpty, isFreshChat, composerFrame, barAnchor,
    setInputLock, typeAndSend, stopGeneration,
    isGenerating, isBusyNow, isHardGenerating,
    enforceComposer, ensureComposerReady,
    turnHalted, findContinueBtn, clickContinueBtn, clickRetry,
    scanError, isTooLongMsg, isBusyMsg,
    attachImages, clearAttachments, conversationKey,
    installSendHooks, findToolBlockSpot,
  };
})();
