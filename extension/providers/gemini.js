// SPDX-License-Identifier: GPL-3.0-or-later
// providers/gemini.js - the Google Gemini (gemini.google.com) provider.
// Exports the same ZSProvider interface as providers/deepseek.js; the core
// (core/main.js) is provider-agnostic. To DISABLE Gemini support, simply remove
// this file from manifest.json (and its URL from background.js PROVIDER_URLS).
//
// Gemini DOM notes (validated live, 2026-06):
//  - Angular app with SEMANTIC custom elements - far more stable than hashed
//    CSS classes: one exchange = <div.conversation-container> holding a
//    <user-query> AND a <model-response>. We treat each of those two elements
//    as one "turn item" (alternating, in DOM order), which maps 1:1 onto the
//    core's expectations.
//  - The reply markdown lives in <message-content>; thinking-model reasoning
//    lives in <model-thoughts> (absent on non-thinking models).
//  - The composer is a Quill contenteditable (.ql-editor) guarded by Trusted
//    Types CSP: innerHTML assignment THROWS. Inject text via select-all +
//    document.execCommand("insertText") - validated to update Angular state.
//  - The primary action button (in <input-area-v2>) is identified by its
//    <mat-icon fonticon>: "arrow_upward" = send (text present), "stop" =
//    generating (whole stream, start to end - no indicatorless reasoning
//    phase like DeepSeek), "mic" = idle empty. aria-labels are localized,
//    fonticon names are NOT - we anchor on fonticon.
//  - No truncation "Continue" button; no per-turn "stopped" marker we can
//    rely on → findContinueBtn/turnHalted return null/false.
// eslint-disable-next-line no-unused-vars
const ZSProvider = (() => {
  "use strict";
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let diag = () => {}; // injected by core via init()

  const S = {
    userItem: "user-query",
    assistantItem: "model-response",
    anyItem: "user-query, model-response",
    reply: "message-content",
    thinking: "model-thoughts,thinking-overlay",
    editor: ".ql-editor[contenteditable='true']",
    inputArea: "input-area-v2,input-area",
    codeWrap: "code-block",
    errorSurfaces: 'mat-snack-bar-container,[role="alert"],[class*="error-message"]',
  };

  const RE = {
    contextLimit: new RegExp(
      [
        "conversation.{0,20}(too long|trop long)",
        "context.{0,20}(limit|exceeded|d\\u00e9pass\\u00e9)",
        "limite.{0,20}(de contexte|atteinte)",
        "please.{0,30}start.{0,20}new.{0,20}(chat|conversation)",
        "(token|context).{0,10}limit",
        "maximum.{0,20}context",
      ].join("|"),
      "i"
    ),
    tooLong: /conversation .{0,20}(too long|getting too long|trop longue)/i,
    busy: /I seem to be encountering an error|se pare că.{0,60}eroare|something went wrong|une erreur s.est produite|try again later|réessayer plus tard|temporarily unavailable/i,
  };

  // Gemini streams continuously with a hard stop-icon signal for the WHOLE
  // generation (including thinking), so idle windows can be much tighter than
  // DeepSeek's. Thinking models still get generous reasoning windows.
  const timings = {
    GEN_IDLE_MS: 1500,
    REASON_IDLE_MS: 12000,
    WARMUP_MS: 45000,
    REASON_NOREPLY_MS: 90000,
    STABLE_MS: 9000,
    RESPONSE_TIMEOUT_MS: 300000,
  };

  // ── Turn classification ───────────────────────────────────────────────────
  const isUserItem = (item) => !!item && item.tagName === "USER-QUERY";
  const isAssistantItem = (item) => !!item && item.tagName === "MODEL-RESPONSE";

  // Gemini prefixes every turn's textContent with a screen-reader label
  // ("Vous avez dit" / "Gemini a dit", inside .cdk-visually-hidden). That
  // prefix broke the core's anchored matching (e.g. /^Output of '/), so ALL
  // text extraction walks the tree and skips those (and any excluded) subtrees.
  const SR_HIDDEN = ".cdk-visually-hidden, [class*='screen-reader'],button,[role='button'],.model-response-label-announcer,[hidden],[inert],[aria-hidden='true']";
  function textWithout(root, excludeSel) {
    if (!root) return "";
    const skip = SR_HIDDEN + (excludeSel ? ", " + excludeSel : "");
    let t = "";
    const walk = (n) => {
      if (n.nodeType === 3) { t += n.nodeValue; return; }
      if (n.nodeType !== 1) return;
      if (n.matches && n.matches(skip)) return;
      if(n.tagName==="BR"){t+="\n";return;}
      const block=/^(P|DIV|PRE|CODE-BLOCK|LI)$/.test(n.tagName);if(block&&t&&!t.endsWith("\n"))t+="\n";
      for (const c of n.childNodes) walk(c);
      if(block&&t&&!t.endsWith("\n"))t+="\n";
    };
    walk(root);
    return t;
  }

  // Read every native answer segment, never a draft inside thinking or a hidden
  // alternate response. Command masks belong to us and must remain readable.
  function replyBlocks(item) {
    if(!item)return [];
    const blocks=[...item.querySelectorAll(S.reply)].filter(el=>!el.closest(S.thinking+',[hidden],[inert],[aria-hidden="true"]'));
    return blocks.filter(el=>!blocks.some(parent=>parent!==el&&parent.contains(el)));
  }
  function itemText(item) {
    return isAssistantItem(item)?replyBlocks(item).map(md=>textWithout(md,'.zs-chip')).join('\n'):textWithout(item,'.zs-chip');
  }
  function classifyText(item,excludeSel) {
    return isAssistantItem(item)?replyBlocks(item).map(md=>textWithout(md,excludeSel||'.zs-chip')).join('\n'):textWithout(item,excludeSel);
  }

  // ── DOM primitives ────────────────────────────────────────────────────────
  const availableTurn=e=>{
    if(!e?.isConnected||e.closest('[hidden],[inert],[aria-hidden="true"],#zs-root'))return false;
    for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||['hidden','collapse'].includes(s.visibility))return false;}
    return true;
  };
  const allItems = () => [...document.querySelectorAll(S.anyItem)].filter(availableTurn);
  const assistantItems = () => allItems().filter(isAssistantItem);
  const assistantCount = () => assistantItems().length;
  const userCount = () => allItems().filter(isUserItem).length;
  // Scope to the SITE's composer only: skip Multi-Script's own injected UI (the
  // settings textarea #zs-set-text in #zs-root). On login/OAuth pages with no
  // site editor this returns null, keeping the "not on a chat page" guard in
  // the send hooks intact (otherwise our own textarea would defeat it and the
  // hooks could swallow the site's login button).
  const visible=e=>!!e?.isConnected&&!e.closest('[hidden],[inert],[aria-hidden="true"],#zs-root')&&!!e.getClientRects().length&&!['hidden','collapse'].includes(getComputedStyle(e).visibility);
  const getEditor = () => [...document.querySelectorAll('.ql-editor:not(.ql-clipboard),rich-textarea [role="textbox"]')].filter(e=>!e.closest(S.anyItem)&&(!e.closest('dialog,[role="dialog"]')||e.closest(S.inputArea))).find(visible)||null;
  const editorText=()=>{const e=getEditor();return e?('value' in e?e.value:typeof ZS!=='undefined'&&ZS.readComposer?ZS.readComposer(e):textWithout(e)).replace(/\u00a0/g,' ').trimEnd():'';};


  const lastAssistant = () => {
    const it = assistantItems();
    return it.length ? it[it.length - 1] : null;
  };

  // A native modal can temporarily make the transcript inert/aria-hidden.
  // That must not turn an existing conversation into a fresh-chat identity.
  const chatIsEmpty = () => !document.querySelector(S.anyItem);
  // A genuinely fresh chat: no turns rendered yet, with the composer mounted.
  // NOTE: we intentionally do NOT also require the bare "/app" route anymore -
  // Gemini's own "New chat" button clears the turn list WITHOUT resetting the
  // address bar (it keeps the PREVIOUS conversation's /app/<id> until the first
  // message is actually sent, validated live 2026-07). Gating on the URL left
  // isFreshChat() - and, transitively, conversationKey() below - still seeing
  // the OLD conversation id on a chat that was visually empty, so the
  // Multi-Script bar stuck on "Agent active" with no way to start a new session.
  const isFreshChat = () => chatIsEmpty() && !!getEditor();

  // The composer box the Start gate hides as one unit.
  const composerFrame = () => getEditor()?.closest(S.inputArea) || [...document.querySelectorAll(S.inputArea)].find(visible) || null;

  // Where the core mounts its in-flow status bar. The <input-area-v2> composer
  // sits inside a flex-COLUMN <fieldset.input-area-container>, so inserting the
  // bar right before the composer makes it span the full input width and push
  // the composer down (validated live). Returns {parent, before}.
  function barMount() {
    const ia = composerFrame();
    if (!ia) return null;
    const col = ia.parentElement; // fieldset.input-area-container (flex column)
    if (!col) return null;
    return { parent: col, before: ia, inside:false, width:ia.getBoundingClientRect().width };
  }

  // ── Input lock ────────────────────────────────────────────────────────────
  // Quill is a contenteditable: flipping contenteditable=false would also block
  // our own execCommand injection, so typeAndSend temporarily re-enables it.
  let _locked = false;
  function setInputLock(on) {
    _locked = on;
    const ed = getEditor();
    if (!ed) return;
    ed.setAttribute("contenteditable", on ? "false" : "true");
    const ph = ed.closest("rich-textarea") || ed;
    if (on) ph.setAttribute("data-zs-locked", "1");
    else ph.removeAttribute("data-zs-locked");
  }

  // ── Action button (send / stop / mic) ─────────────────────────────────────
  const iconName = (el) => {
    const i = el && el.querySelector("mat-icon");
    return i ? (i.getAttribute("fonticon") || i.getAttribute("data-mat-icon-name") || (i.textContent || "").trim()) : "";
  };
  function actionButtons() {
    const box = composerFrame();
    return box ? [...box.querySelectorAll("button")].filter((b) => visible(b)) : [];
  }
  const findButtonByIcon = (name) => actionButtons().find((b) => iconName(b) === name) || null;
  const sendButton = () => actionButtons().find(b=>["arrow_upward","send","send_spark"].includes(iconName(b))||/^(send(?: message)?|trimite(?: mesajul)?)$/i.test(b.getAttribute("aria-label")||""))||null;
  const stopButton = () => actionButtons().find(b=>["stop","stop_circle"].includes(iconName(b))||/^(stop(?: generating| response)?|oprește(?: generarea| răspunsul)?)$/i.test(b.getAttribute("aria-label")||""))||null;

  // ── Generation detection ──────────────────────────────────────────────────
  // The stop icon is present for the ENTIRE generation (validated live), which
  // makes detection far simpler than DeepSeek. Growth tracking remains as a
  // belt-and-braces fallback for the instants around start/end.
  function streamText(item) {
    if (!item) return "";
    const think = item.querySelector(S.thinking);
    return (think ? think.textContent || "" : "") + "\n" + classifyText(item,".zs-chip");
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
  const grewWithin = (ms) => _streamMax > 1 && Date.now() - _streamAt < ms;

  function genActive(){sampleStream();return !!stopButton()||!![...(lastAssistant()?.querySelectorAll('.model-response-label-announcer[aria-busy="true"],message-content [aria-busy="true"]')||[])].some(visible)||grewWithin(timings.GEN_IDLE_MS);}
  const isGenerating=genActive,isBusyNow=genActive,isHardGenerating=genActive;

  // A readable command is not a finished response while the native Stop control
  // is still present. Wait without editing the draft or cancelling Gemini.
  async function waitForSendReady({timeout=180000,cancelled=()=>false,onWait=()=>{}}={}) {
    const end=Date.now()+timeout;let notified=false;
    while(isGenerating()) {
      if(cancelled())return false;
      if(!notified){notified=true;onWait('Gemini is finishing its response. Multi-Script will continue automatically.');}
      if(Date.now()>=end)return false;
      await sleep(150);
    }
    return !cancelled();
  }

  // Gemini exposes no reliable per-turn "stopped" marker → never halted.
  const turnHalted = () => false;
  // No truncation Continue button on Gemini.
  const findContinueBtn = () => null;
  const clickContinueBtn = () => false;

  function snapshot() {
    try {
      const it = lastAssistant();
      if (!it) return { th: 0, rp: 0 };
      const think = it.querySelector(S.thinking);
      return {
        th: think ? (think.textContent || "").trim().length : 0,
        rp: classifyText(it,".zs-chip").length,
      };
    } catch { return {}; }
  }

  function readAssistant() {
    const item = lastAssistant();
    if (!item) return { present: false, reply: "", thinking: "", item: null };
    const think = item.querySelector(S.thinking);
    return {
      present: true,
      reply: classifyText(item,".zs-chip").trim(),
      thinking: think ? (think.textContent || "").trim() : "",
      item,
    };
  }

  async function waitFor(pred, timeout, cancelled) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      if(cancelled?.())throw new Error("Gemini send cancelled before submission.");
      if (pred()) return true;
      await sleep(120);
    }
    return false;
  }

  // ── Sending ───────────────────────────────────────────────────────────────
  // Gemini's composer is a Quill editor wrapped by an Angular ControlValueAccessor.
  // We run in the extension's ISOLATED world, so the page's `window.Quill`
  // (and its instance API) is NOT reachable - we can only touch the shared DOM.
  // document.execCommand("insertText") drives the browser's native editing
  // pipeline, which fires the beforeinput/input events Quill's editor listens
  // to → its model updates, .ql-blank clears, the Angular CVA syncs and the send
  // button appears. This works reliably WHEN the composer is actually visible
  // (the Start gate is removed before the loop sends), which it always is during
  // the agentic loop. A selectAll first guarantees we replace any stale content.
  // PERF + FIDELITY (measured live, 2026): a single execCommand("insertText") of a
  // MULTI-LINE string is catastrophically slow in Gemini's Quill editor - every
  // "\n" makes Quill split the content into a new <p> block and re-normalise the
  // whole document, ~80ms PER LINE (linear). A ~90-line system prompt froze the
  // composer for ~7s under the "Working…" cover (big tool outputs stalled too).
  // We instead insert each line with insertText and join them with insertLineBreak
  // (a SOFT break, like Shift+Enter): the content stays in ONE block (~3ms/line,
  // ~430ms for 150 lines) yet Gemini STILL transmits the message as real, separate
  // lines (validated: the sent turn renders one query-text-line per line). Keeping
  // real line structure matters - an earlier attempt that flattened newlines to
  // U+2028 made the image-capable "Flash" model misfire into GENERATING AN IMAGE
  // at boot, because the prompt arrived as one mangled line. The first op runs over
  // the select-all so any stale content is replaced; empty lines skip insertText
  // (an empty insertText collapses the selection and breaks the following inserts).
  // Gemini has no server-side composer cap worth hitting, but its EDITOR does:
  // the insert cost below is paid per LINE, synchronously, on the page's main
  // thread, and it degrades as the document grows. A big tool result (validated
  // live: a 2599-line http_get) froze the whole page for ~a minute - nothing
  // clickable, the "Agent is working…" cover stuck, then it resumed on its own
  // once the insert finished. So the cap here is about the DOM cost, not the
  // model's context: keep head+tail, drop the middle, and tell the model that
  // content was dropped so it does not re-run the command.
  const SEND_MAX_CHARS = 120000;
  const SEND_MAX_LINES = 1200;   // the line count is what actually hurts
  function truncateForSend(text) {
    { const o = (text && typeof ZS !== "undefined" && ZS.limits) ? ZS.limits.sendOverride(text) : null; if (o !== null) return o; }
    if (!text) return text;
    const lines = String(text).split("\n");
    if (text.length <= SEND_MAX_CHARS && lines.length <= SEND_MAX_LINES) return text;
    const marker = (what) =>
      `\n\n[…Multi-Script: result truncated (${what}) so it can be pasted into ` +
      `Gemini's composer without freezing the page. Do NOT re-run the command; ` +
      `work with the head and tail shown here…]\n\n`;
    let out, note;
    if (lines.length > SEND_MAX_LINES) {
      const head = Math.floor(SEND_MAX_LINES * 0.85);
      const tail = SEND_MAX_LINES - head;
      note = `${lines.length - SEND_MAX_LINES} of ${lines.length} lines omitted`;
      out = lines.slice(0, head).join("\n") + marker(note) + lines.slice(lines.length - tail).join("\n");
    } else {
      out = text;
    }
    if (out.length > SEND_MAX_CHARS) {
      const budget = SEND_MAX_CHARS - 300;
      const head = Math.floor(budget * 0.85);
      note = `${out.length - budget} of ${out.length} characters omitted`;
      out = out.slice(0, head) + marker(note) + out.slice(out.length - (budget - head));
    }
    diag("send.truncated", { from: text.length, to: out.length, lines: lines.length });
    return out;
  }

  // Yield to the event loop between chunks. Without this the whole insert is one
  // uninterruptible synchronous burst: the page cannot repaint or respond to a
  // click for its entire duration (the "I can't click anything anymore" report).
  // Yielding does not make the insert faster, it makes the page stay alive while
  // it happens - and lets the Stop button remain usable.
  const INSERT_CHUNK_LINES = 120;
  async function setEditorText(ed, text, controls={}) {
    text=String(text).replace(/\r\n?/g,'\n');
    ed.focus();
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(ed);
    sel.removeAllRanges();
    sel.addRange(range);
    // One browser edit lets Quill reconcile a complete document. Repeated
    // line edits can be normalized between chunks and lose the insertion point.
    // Escape every character that could introduce markup; these are text-only
    // paragraphs matching the current native editor's observed document shape.
    if(text&&text.length>0){
      const escape=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
      const html=text.split('\n').map(line=>'<p style="white-space:pre-wrap">'+(escape(line)||'<br>')+'</p>').join('');
      if(controls.cancelled?.())throw new Error('Gemini send cancelled before insertion.');
      if(document.execCommand('insertHTML',false,html)){
        await sleep(0);
        if(controls.cancelled?.()||!ed.isConnected)throw new Error('Gemini send cancelled or composer changed after insertion.');
        if(editorText()===text.replace(/\u00a0/g,' ').trimEnd())return;
        range.selectNodeContents(ed);sel.removeAllRanges();sel.addRange(range);
      }
    }
    const lines = String(text).split("\n");
    if(!text)document.execCommand("delete");
    const t0 = Date.now();
    for (let i = 0; i < lines.length; i++) {
      if(!ed.isConnected||controls.cancelled?.())throw new Error("Gemini send cancelled or composer changed before submission.");
      if (lines[i]) document.execCommand("insertText", false, lines[i]);
      if (i < lines.length - 1) document.execCommand("insertLineBreak");
      if (i && i % INSERT_CHUNK_LINES === 0) await sleep(0);
    }
    if (lines.length > INSERT_CHUNK_LINES) diag("send.insertDone", { lines: lines.length, ms: Date.now() - t0 });
  }

  let sending=false;
  const sendFailure=(message,state='not-sent')=>Object.assign(new Error(message),{retryable:false,sendState:state});
  async function typeAndSend(text, images, controls={}) {
    if(sending)throw sendFailure('A Gemini send is already in progress.');
    if(controls.cancelled?.())throw sendFailure("Gemini send cancelled before submission.");
    const ed = getEditor();
    if (!ed) throw sendFailure("Gemini input box not found");
    if(isGenerating())throw sendFailure("Gemini is still responding. Wait for it to finish before sending another message.");
    const route=location.pathname, callerCancelled=controls.cancelled;
    controls={...controls,cancelled:()=>callerCancelled?.()||getEditor()!==ed||location.pathname!==route};
    // Cap BEFORE any comparison below, so the retry path's `editorText() !== text`
    // test compares against what we actually typed.
    text = truncateForSend(String(text).replace(/\r\n?/g,'\n'));
    const relock = _locked;let clicked=false;sending=true;
    if (relock) ed.setAttribute("contenteditable", "true"); // injection needs it editable
    try {
      // submitAndGetBase RETRIES this whole function (up to 4x) when the send
      // doesn't land within its window. Naively redoing both steps every retry
      // is destructive: (1) setEditorText's select-all + insertText wipes the
      // editor's internal reference to whatever is already pending, and (2)
      // pasting again attaches ANOTHER duplicate file on top of the first
      // (validated live: 3 retries produced 3 separate attach.dispatchPaste
      // calls with 3 different files, and the model's replies stayed generic
      // - it never got one coherent image). So: only retype if the text isn't
      // already there, and only attach if nothing is pending yet.
      if (editorText() !== text) await setEditorText(ed, text, controls);
      const hasPendingAttachment = () => {
        const box = composerFrame();
        return !!(box && box.querySelector("[class*='preview'], [class*='thumbnail']"));
      };
      if (images && images.length && !hasPendingAttachment()) {
        diag("attach.beforeCall", { count: images.length });
        const ok = await attachImages(images);diag("attach.afterCall", {ok});if(!ok)throw new Error("Gemini did not accept the image attachment. No text-only substitute was sent.");
      }
      // Quiet thinking remains active; never click Stop to force another send.
      if(isGenerating())throw new Error("Gemini is still responding. Wait for it to finish before sending another message.");
      // Wait for Angular to render the send (arrow_upward) button - proof that
      // it registered the text. The Quill-API injection (see setEditorText)
      // fires text-change so this resolves; if it doesn't, the send won't work.
      // Angular needs longer to register a big paste, so scale the wait with the message size.
      const sendBtnMs = Math.min(60000, Math.max(10000, 6000 + Math.round(text.length / 2)));
      await waitFor(() => !!sendButton(), sendBtnMs,controls.cancelled);
      // Retry insertion only before a send has been attempted. A composer that was
      // wedged when setEditorText ran can swallow the insert entirely, leaving
      // an empty editor and therefore no send button - the "Start did nothing,
      // the system prompt was never sent" report. Retyping now that the stop is
      // cleared is safe: the editor is either empty or holds our own text.
      if (!sendButton() && editorText() !== text) {
        diag("send.retype", {});
        await setEditorText(ed, text, controls);
        await waitFor(() => !!sendButton(), Math.min(30000, Math.max(6000, 3000 + Math.round(text.length / 4))),controls.cancelled);
      }
      if(controls.cancelled?.())throw new Error("Gemini send cancelled before submission.");
      if(getEditor()!==ed||editorText().replace(/\r\n/g,'\n')!==String(text).replace(/\r\n/g,'\n').replace(/\u00a0/g,' ').trimEnd())throw new Error("Gemini did not retain the complete prompt. No message was sent; refresh the page and retry.");
      const btn = sendButton();
      diag("send.click", { found: !!btn, pending: hasPendingAttachment() });
      if(btn&&(btn.disabled||btn.getAttribute("aria-disabled")==="true"))throw new Error("Gemini send is disabled; check its message or quota notice.");
      if (btn) { clicked=true;btn.click(); return; }
      throw new Error("Gemini send control is unavailable. The complete draft is preserved; check sign-in, upload or quota notices before retrying.");
    } catch(error) {
      if(error.sendState)throw error;
      throw sendFailure(error.message||String(error),clicked?'unconfirmed':'not-sent');
    } finally {
      sending=false;
      if (relock) { const e2 = getEditor(); if (e2) e2.setAttribute("contenteditable", "false"); }
    }
  }

  function stopGeneration() {
    const b = stopButton();
    if (b) try { b.click(); } catch {}
  }

  // No site modes to enforce on Gemini (model picker is left to the user).
  function enforceComposer() { return { ready: true }; }
  async function ensureComposerReady(reason) {
    diag("mode_ready", { reason, provider: "gemini" });
    return { ready: !!getEditor() };
  }

  // ── Error / limit detection (site chrome only) ────────────────────────────
  function scanError() {
    try {
      for (const el of document.querySelectorAll(S.errorSurfaces)) {
        if (el.offsetParent === null) continue;
        if (el.closest(S.anyItem)) continue; // model content, not UI chrome
        const t = (el.innerText || "").trim();
        if (t.length > 8 && t.length < 600 && RE.contextLimit.test(t)) return t.slice(0, 240);
      }
    } catch {}
    if (!getEditor()) return "The input box disappeared (session ended?).";
    return null;
  }
  function responseError(){
    const item=lastAssistant(),text=item?classifyText(item,'.zs-chip').trim():'';
    return text.length<400&&/^(?:I seem to be encountering an error|se pare că.{0,60}eroare)/i.test(text)?{provider:'gemini',text}:null;
  }
  const isTooLongMsg = (text) => RE.tooLong.test(text);
  const isBusyMsg = (text) => RE.busy.test(text);

  // ── Image attachment (best effort: paste onto the composer) ──────────────
  function fileFromImage(img, i) {
    const mime = img.mimeType || "image/jpeg";
    const bin = atob(img.data);
    const arr = new Uint8Array(bin.length);
    for (let j = 0; j < bin.length; j++) arr[j] = bin.charCodeAt(j);
    const ext = mime.includes("png") ? "png" : "jpg";
    return new File([arr], `zeroscript_${Date.now()}_${i}.${ext}`, { type: mime });
  }
  async function attachImages(images) {
    const ed = getEditor();
    if (!ed) { diag("attach.noEditor"); return false; }
    if (!images || !images.length) return false;
    const dt = new DataTransfer();
    images.forEach((img, i) => { try { dt.items.add(fileFromImage(img, i)); } catch {} });
    if (!dt.items.length) { diag("attach.noDtItems"); return false; }
    diag("attach.dispatchPaste", { items: dt.items.length });
    ed.focus();
    ed.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    // An upload preview appearing in the input area is the FAST accepted-signal,
    // but it renders instantly from a local blob: URL - well before Gemini
    // finishes uploading the file to its backend. Sending while the upload's
    // own progress spinner is still up silently drops the attachment (validated
    // live: the message went out text-only and the file sat in the composer,
    // unsent, indefinitely - even though the preview had long since appeared).
    const previewOk = await waitFor(() => {
      const box = composerFrame();
      return !!(box && box.querySelector("img, [class*='preview'], [class*='thumbnail']"));
    }, 15000);
    diag("attach.previewOk", { previewOk });
    if (!previewOk) return false;
    // Gemini's uploader renders a <mat-spinner> (Angular Material) inside the
    // file-preview container while the paste is still uploading to its backend
    // - NOT mat-progress-spinner. Missing it here made the wait resolve instantly,
    // so the send fired mid-upload and the file was dropped (text went out alone,
    // the attachment stuck loading in the composer). Verified live: the mat-spinner
    // is present ~2-4s (grows with file size), then removed on completion.
    const spinnerSel = 'mat-spinner, mat-progress-spinner, progress, [role="progressbar"]';
    const hasSpinner = () => {
      const box = composerFrame();
      return !!(box && box.querySelector(spinnerSel));
    };
    // The preview wrapper and the spinner mount in the SAME Angular render, so a
    // "no spinner ⇒ done" check can win a frame before the spinner appears and
    // resolve prematurely. First give the spinner a short window to show up; if it
    // never does (tiny file, instant upload) that's fine - proceed either way.
    await waitFor(hasSpinner, 1500);
    const spinnerCleared = await waitFor(() => !hasSpinner(), 20000);
    diag("attach.spinnerCleared", { spinnerCleared });
    return spinnerCleared;
  }
  function clearAttachments() {
    try {
      const box = composerFrame();
      if (!box) return;
      box.querySelectorAll("[aria-label*='upprimer'], [aria-label*='emove'], [class*='delete'], [class*='remove']")
        .forEach((d) => { try { d.click(); } catch {} });
    } catch {}
  }


  // A conversation with NO turns rendered yet is treated as transient ("") so
  // the core never persists it - and never stays sticky on it - as "started".
  // This covers both the bare "/app" route AND Gemini's "New chat" button,
  // which clears the turn list but keeps the PREVIOUS conversation's /app/<id>
  // in the address bar until the first message is actually sent (see
  // isFreshChat() above for the full story).
  const conversationKey = () =>
    (chatIsEmpty() || /\/app\/?$/.test(location.pathname)) ? "" : location.pathname;

  // ── User-send interception ────────────────────────────────────────────────
  function installSendHooks(handlers) {
    document.addEventListener(
      "keydown",
      (e) => {
        if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
        const ed = getEditor();
        if (!ed || !ed.contains(e.target)) return;
        if (editorText().trim() === "") return;
        if (handlers.isBlocked()) return;
        if (!handlers.isStarted()) {
          if (!chatIsEmpty()) return; // existing conversation → not ours to gate
          handlers.onBlockedAttempt(); // nudge only; never block plain chat
          return;
        }
        handlers.onUserMessage(assistantCount());
      },
      true
    );

    document.addEventListener(
      "click",
      (e) => {
        if (!getEditor()) return;
        const btn = e.target?.closest?.("button");
        if(!btn||!composerFrame()?.contains(btn))return;
        if (!btn) return;
        const ic = iconName(btn);
        if (btn === stopButton()) {
          // Only a trusted user click halts the active run.
          if (!e.isTrusted) return;
          handlers.onNativeStop();
          return;
        }
        if (btn !== sendButton()) return;
        if (handlers.isBlocked()) return;
        if (!handlers.isStarted()) {
          if (!chatIsEmpty()) return;
          handlers.onBlockedAttempt(); // nudge only; never block plain chat
          return;
        }
        handlers.onUserMessage(assistantCount());
      },
      true
    );
  }

  // ── Tool-block location for camouflage ────────────────────────────────────
  // Gemini wraps each fenced code block in a <code-block> element (markers and
  // JSON survive intact in textContent), and a whole ###LUA###…###END_LUA### or
  // ###MCP_TOOL### block is ONE atomic code-block. So hiding is simple and
  // robust: hide every <code-block> in the reply whose text carries a command
  // shape, plus any bare top-level paragraph that holds an inline command (the
  // model is told to use code blocks, but this catches a stray inline one).
  // The host-walk the DeepSeek provider uses is WRONG here - it descends inside
  // a code-block, so hiding the wrapper then fails. The core anchors the chip at
  // the turn level (chipAtItemLevel), so the returned position is unused; this
  // function's real job is applying the .zs-tool-hide classes correctly.
  const CMD_SHAPE = /"(?:command|tool)"\s*:\s*"|###\s*lua|###mcp_tool###/i;
  function findToolBlockSpot(item /*, chip */) {
    const replies = replyBlocks(item);
    let hidAny = null;
    for (const mc of replies) {
      // 1. Fenced code blocks carrying a command.
      mc.querySelectorAll(S.codeWrap).forEach((cb) => {
        if (cb.closest(".zs-chip")) return;
        if (CMD_SHAPE.test(cb.textContent || "")) {
          cb.classList.add("zs-tool-hide");
          // Angular recreates <code-block> nodes (markdown settle at end of
          // stream + again when the next turn is sent), stripping the class
          // above and flashing the raw command until the next sweep. The
          // <message-content> element KEEPS its identity through those
          // re-renders (validated live), so also mark it: the overlay.css
          // rule `message-content.zs-cmd-mask code-block` keeps every
          // recreated block hidden with zero flash.
          mc.classList.add("zs-cmd-mask");
          hidAny = hidAny || { parent: cb.parentElement, ref: cb };
        }
      });
      // 2. Bare top-level blocks with an inline command (no code-block inside).
      [...mc.children].forEach((el) => {
        if (el.classList.contains("zs-chip") || el.querySelector(S.codeWrap)) return;
        const t = el.textContent || "";
        // A reply that IS the command (starts with {"command"... / {"tool"...) is hidden at any length, including
        // while it is still streaming: long execute_luau commands are thousands of characters and used to spill out.
        const startsLikeCommand = /^\s*\{\s*"(?:c|t)/.test(t) && t.length > 8;
        if ((t.length < 600 && CMD_SHAPE.test(t)) || startsLikeCommand) {
          el.classList.add("zs-tool-hide");
          hidAny = hidAny || { parent: el.parentElement, ref: el };
        }
      });
    }
    return hidAny;
  }

  return {
    // 6.26: core pages long tool results to stay under this adapter's send caps
    // (SEND_MAX_CHARS / SEND_MAX_LINES) instead of the adapter cutting the middle out.
    resultCharBudget: 100000, resultLineBudget: 1000,
    sendCharBudget: SEND_MAX_CHARS - 4000, startupCharBudget: 50000, startupLineBudget: SEND_MAX_LINES,
    id: "gemini",
    displayName: "Gemini",
    // Gemini's web model is natively multimodal (image understanding), so
    // screen_capture is safe to expose here. Other providers default this
    // to false until confirmed live (see main.js BLOCKED_TOOLS gate).
    supportsVision: true,
    timings,
    // Reasoning-area selector, exported so the CORE's raw-command-visible probes
    // exclude it (same fix as DeepSeek): Gemini's thinking models (2.5 Pro/Flash)
    // render their reasoning in <model-thoughts> and often QUOTE the command
    // JSON/###LUA### there. The camouflage never hides that quote (by design), so
    // without this exclusion the core reads it as "raw block still visible"
    // forever - the chip then FLAPS done→run→done and rebuilds on every sweep.
    thinkingSel: S.thinking,
    // Gemini (Angular) re-renders a turn's content subtree on every update,
    // wiping any chip placed inside it. Tell the core to anchor chips at the
    // turn-element level instead, where they survive those re-renders.
    chipAtItemLevel: true,
    // The "Working…" input cover overshoots the editor box by this many px on
    // each side. Gemini's Quill keeps typed text near the rounded corners, so a
    // few px of bleed hides the slivers that would otherwise peek (see placeBar /
    // inputCover). Providers with a native <textarea> omit this (default 0).
    coverPad: 8,
    // Gemini's .ql-editor rect sits a few px below the visual input-box centre,
    // so nudge the "Agent is working…" cover up to read as vertically centred.
    coverOffsetY: -6,
    // Gemini's turn elements are semantic and never virtualized away, so
    // assistantCount() reliably increases for every new reply. The core's
    // watcher uses this to refuse finalizing before this send's reply turn
    // exists (fixes premature loop.end on the previous turn's stable text).
    reliableCounts: true,
    strictGeneration: true,
    waitForSendReady,
    init({ diag: d } = {}) { if (d) diag = d; },
    // turns
    allItems, isUserItem, isAssistantItem, itemText, classifyText,
    assistantCount, userCount, lastAssistant, readAssistant,
    streamLen, snapshot,
    // composer / state
    getEditor, editorText, chatIsEmpty, isFreshChat, composerFrame, barMount,
    setInputLock, typeAndSend, stopGeneration,
    isGenerating, isBusyNow, isHardGenerating,
    enforceComposer, ensureComposerReady,
    turnHalted, findContinueBtn, clickContinueBtn,
    scanError, responseError, isTooLongMsg, isBusyMsg,
    // actions
    attachImages, clearAttachments, conversationKey,
    installSendHooks, findToolBlockSpot,
  };
})();
