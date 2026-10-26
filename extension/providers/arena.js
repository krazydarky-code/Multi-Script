// SPDX-License-Identifier: GPL-3.0-or-later
// providers/arena.js - the Arena (arena.ai) provider.
// Exports the same ZSProvider interface as providers/deepseek.js; the core
// (core/main.js) is provider-agnostic. To DISABLE Arena support, remove this
// file from manifest.json (and its URL from background.js PROVIDER_URLS).
//
// Arena DOM notes (validated live, 2026-06, on /text/direct):
//  - Next.js / React + Tailwind app. The message list is a single
//    <ol class="… flex-col-reverse …">; each turn is a direct child
//    <div class="mx-auto max-w-[800px] …"> holding a <div class="prose"> body.
//    A trailing <div class="h-0"> spacer is also a child (skipped).
//  - CRITICAL: the list is flex-col-reverse, so DOM order is NEWEST-FIRST.
//    allItems() REVERSES the DOM children so the rest of the provider/core sees
//    the usual chronological (oldest-first) order and lastAssistant() = last.
//  - A user turn's container carries `justify-end`; an assistant turn's does not
//    and its header reads "Response provided by <vendor>" ABOVE the .prose body
//    (we read ONLY .prose, so that header never counts as model output).
//  - Fenced code is a REAL <pre> (textContent preserves newlines - no
//    CodeMirror/Monaco), wrapped in a <div class="not-prose">. Multi-Script's
//    command markers/JSON survive intact in textContent.
//  - The composer is a real <textarea> inside a <form> (the ONLY form textarea;
//    other page textareas are recaptcha/aria-hidden). We set its .value via the
//    native setter + input event, then click the submit button.
//  - The primary button carries aria-label "Send message" (idle) and is replaced
//    by an aria-label "Stop generation" button for the WHOLE generation.
//  - Conversation URL is /c/<uuid>; a fresh chat is /text/direct (no id yet).
// eslint-disable-next-line no-unused-vars
const ZSProvider = (() => {
  "use strict";
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let diag = () => {}; // injected by core via init()
  // Discover open shadow surfaces when DOM subtrees arrive, not by scanning
  // every syntax-highlight span for every composer/Stop lookup.
  const shadowRoots=new Set();let shadowReady=false;
  function discoverShadows(node){
    if(!node?.querySelectorAll)return;
    const visit=el=>{if(el.shadowRoot&&!shadowRoots.has(el.shadowRoot)){shadowRoots.add(el.shadowRoot);discoverShadows(el.shadowRoot);surfaceObserver?.observe(el.shadowRoot,{childList:true,subtree:true,characterData:true});}};
    const irrelevant=el=>el.matches?.('.prose,pre,code,#zs-root,#zs-bar,.zs-chip');
    if(node.nodeType===1){if(irrelevant(node)||node.closest('.prose,pre,code,#zs-root,#zs-bar,.zs-chip'))return;visit(node);}
    const walker=document.createTreeWalker(node,NodeFilter.SHOW_ELEMENT,{acceptNode:el=>irrelevant(el)?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
    for(let el=walker.nextNode();el;el=walker.nextNode())visit(el);
  }
  const proseTextCache=new WeakMap();
  function surfaceChanges(records){for(const record of records){
    const el=record.target.nodeType===1?record.target:record.target.parentElement;
    if(el?.closest('#zs-root,#zs-bar,.zs-chip'))continue;
    const prose=el?.closest('.prose');if(prose)proseTextCache.delete(prose);
    if(record.type==='childList')for(const node of record.addedNodes)if(node.nodeType===1)discoverShadows(node);
  }}
  const surfaceObserver=typeof MutationObserver==='function'?new MutationObserver(surfaceChanges):null;
  surfaceObserver?.observe(document.documentElement,{childList:true,subtree:true,characterData:true});
  function flushSurfaces(){surfaceChanges(surfaceObserver?.takeRecords?.()||[]);if(!shadowReady||!surfaceObserver){shadowReady=true;discoverShadows(document);}}
  function deepQueryAll(selector,root=document){
    flushSurfaces();const out=[...root.querySelectorAll(selector)];
    for(const shadow of shadowRoots){if(!shadow.host.isConnected){shadowRoots.delete(shadow);continue;}if(root===document||root.contains(shadow.host))out.push(...shadow.querySelectorAll(selector));}
    return out;
  }
  const deepQuery = (selector) => deepQueryAll(selector)[0] || null;
  // Identity of the last image set we STAGED into the composer. The core reuses
  // the same array reference across submitAndGetBase's up-to-4 typeAndSend
  // retries, so keying on it makes the attach idempotent (see typeAndSend) - a
  // genuinely new capture arrives as a new array and attaches normally.
  let _attachedImages = null;
  let lastTextRoute=null;

  const S = {
    list: "ol.flex-col-reverse",
    box: ".prose",                 // markdown body (both user + assistant turns)
    // A/B comparison CAROUSEL: some replies render not as a normal mx-auto turn
    // but as an Embla carousel (region) holding TWO candidate slides side by side
    // (slide A = first in DOM, slide B = second). The container is a `w-full`
    // direct child of the <ol> WITHOUT `mx-auto`, so domTurns() used to skip it
    // entirely - the reply turn was never counted and the core waited out the full
    // NO_TURN_GRACE (≈30s) for nothing. We detect the carousel by its stable ARIA
    // and always read candidate A's .prose (matches the "Continuer avec A" commit).
    carousel: '[role="region"][aria-roledescription="carousel"]',
    slide: '[aria-roledescription="slide"]',
    codeWrap: "div.not-prose",     // fenced-code wrapper inside .prose
    sendAria: /^(?:send(?: message| prompt)?|submit(?: message)?|envoyer(?: le message)?|trimite(?: mesajul)?)$/i,
    stopAria: /stop generation|arr[êe]ter/i,
    errorSurfaces:
      '[role="alert"],[class*="toast"],[class*="error"],[class*="alert"],[data-sonner-toast]',
  };

  const RE = {
    contextLimit: new RegExp(
      [
        "conversation.{0,20}(too long|trop long)",
        "context.{0,20}(limit|exceeded|d\\u00e9pass\\u00e9)",
        "please.{0,30}(start|cr\\u00e9er).{0,20}(new|nouveau).{0,20}(chat|conversation)",
        "(token|context).{0,10}limit",
        "message.{0,20}too.{0,10}long",
        "maximum.{0,20}context",
        "this conversation has reached",
      ].join("|"),
      "i"
    ),
    tooLong: /conversation .{0,20}(too long|getting too long|trop longue)/i,
    busy: /something went wrong|une erreur s.est produite|try again later|réessayer plus tard|rate limit|too many requests/i,
  };

  // Arena streams with a hard stop-button signal for the WHOLE generation, so
  // idle windows can be tight (mirrors Gemini, not DeepSeek's reasoning phase).
  const timings = {
    GEN_IDLE_MS: 1500,
    REASON_IDLE_MS: 12000,
    WARMUP_MS: 45000,
    REASON_NOREPLY_MS: 90000,
    STABLE_MS: 9000,
    RESPONSE_TIMEOUT_MS: 300000,
  };

  // Optional saved preference metadata, never model selection or routing.
  // Preferences are off until the user explicitly chooses one in this version.
  const AUTO_ROUTING_PROFILES = {
    opus55:{label:"Claude Opus 5.5 · Direct Max",requestedModel:"Claude Opus 5.5",availability:"arena-dependent",description:"Default model-targeted profile. Ask Direct Max for the exact real Claude Opus 5.5 on every turn when legitimately available."},
    opus5:{label:"Claude Opus 5 · Direct Max",requestedModel:"Claude Opus 5",availability:"arena-dependent",description:"Ask Direct Max for the exact real Claude Opus 5 on every turn, with honest fallback only when unavailable."},
    gpt56:{label:"GPT-5.6 Sol · Direct Max",requestedModel:"GPT-5.6 Sol",availability:"arena-dependent",description:"Ask Direct Max for the exact real GPT-5.6 Sol on every turn when Arena exposes it."},
    kimi3:{label:"Kimi K3 · Direct Max",requestedModel:"Kimi K3",availability:"arena-dependent",description:"Ask Direct Max for the exact real Kimi K3 on every turn when available."},
    luna:{label:"GPT-6 Luna · Direct Max",requestedModel:"GPT-6 Luna",availability:"future",description:"Future-ready exact-model request on every turn, with honest fallback until Arena offers it."},
    directmax:{label:"Direct Max · Untargeted Auto",requestedModel:"Arena Direct Max adaptive routing",availability:"arena-dependent",description:"Optional untargeted mode. Let Direct Max choose any available model from the current capability mix."},
  };
  const ARENA_PROFILE_KEY="zs.arena.autoRoutingProfile";
  // An explicitly stored empty string is a real off mode: no starter routing block
  // and no per-turn Direct Max envelope. The normal engine/chat-only bootstrap remains.
  const ARENA_OPT_IN_KEY=ARENA_PROFILE_KEY+'.explicit6497';
  function getAutoRoutingProfile(){try{if(localStorage.getItem(ARENA_OPT_IN_KEY)!=='true')return '';const x=localStorage.getItem(ARENA_PROFILE_KEY);return AUTO_ROUTING_PROFILES[x]?x:'';}catch{return '';}}
  function setAutoRoutingProfile(id){const safe=AUTO_ROUTING_PROFILES[id]?id:'';try{localStorage.setItem(ARENA_PROFILE_KEY,safe);localStorage.setItem(ARENA_OPT_IN_KEY,'true');}catch{}return safe;}
  function autoRoutingProfiles(){return Object.entries(AUTO_ROUTING_PROFILES).map(([id,x])=>({id,...x,description:"Saved preference metadata only. Choose an available model with Arena’s own selector; this setting cannot select or force a backend."}));}
  function getStartupProfilePrompt(){
    const id=getAutoRoutingProfile(),p=AUTO_ROUTING_PROFILES[id];if(!p)return "";
    return `[ARENA MODEL PREFERENCE — METADATA ONLY]\nSaved preference: ${p.requestedModel}. Arena's actual selector/router controls the backend. This extension preference does not select, pin or change it. Do not impersonate a requested model, try to route yourself, or spend the reply discussing identity. Use the actual selected backend, preserve the real tool transport and continue the user's task. Select a specific available model through Arena's own selector when the user wants that choice.`;
  }

  function _arenaCapabilities(text){
    const x=String(text||"").toLowerCase(),out=[];
    const add=(name,re)=>{if(re.test(x))out.push(name);};
    add("native-tool-execution",/mcp|tool|command|schema|engine|studio|unity|godot|blender|roblox/);
    add("coding-architecture",/code|script|program|debug|api|network|database|shader|algorithm|architecture/);
    add("quantitative-reasoning",/math|equation|calculate|probability|physics|balance|budget|optimi[sz]|profile/);
    add("visual-spatial",/image|vision|model|mesh|texture|material|animation|rig|ui|gui|vfx|lighting|scene/);
    add("research-currentness",/research|search|latest|current|documentation|compare|source|verify/);
    add("creative-production",/create|design|build|make|style|story|audio|sound|music|level|game/);
    add("long-context-integration",/project|existing|continue|integrat|migration|cross.engine|full|complete/);
    add("verification-critique",/test|verify|validate|evidence|review|audit|bug|regression|quality/);
    return out.length?out:["general-reasoning"];
  }
  function prepareOutboundPrompt(text){
    text=String(text??"");const id=getAutoRoutingProfile(),p=AUTO_ROUTING_PROFILES[id];
    if(!p||!text.trim()||/^\s*(Output of |ERROR\b|\[MULTI-SCRIPT VERIFICATION)/.test(text)||text.includes('[ARENA MODEL PREFERENCE — METADATA ONLY]'))return text;
    return text+'\n\n'+getStartupProfilePrompt()+'\nCapability needs: '+_arenaCapabilities(text).join(', ')+'. This is task context, not model selection.';
  }

  function routingProfileDiagnostics(){const id=getAutoRoutingProfile(),p=AUTO_ROUTING_PROFILES[id],caps=["native-tool-execution","coding-architecture","quantitative-reasoning","visual-spatial","research-currentness","creative-production","long-context-integration","verification-critique"];return p?{provider:"arena",profile:id,requestedModel:p.requestedModel,promptReady:true,routing:"prompt-only",perTurnRouting:false,perTurnPreference:true,modelTargeted:false,modelPinned:false,dynamicCapabilities:caps,automaticPicker:false,accessBypass:false}:{provider:"arena",profile:"",promptReady:false,routing:"disabled",normalStartup:true,perTurnRouting:false,modelTargeted:false,modelPinned:false,dynamicCapabilities:[],automaticPicker:false,accessBypass:false};}


  // ── Turn classification ───────────────────────────────────────────────────
  // A turn = a direct child of the message <ol> that carries `mx-auto` and a
  // .prose body (the trailing .h-0 spacer has neither). User turns are right-
  // aligned (`justify-end`); everything else is an assistant turn.
  const listEl = () =>
    document.querySelector(S.list) ||
    [...document.querySelectorAll("ol")].find((o) => o.querySelector(S.box)) ||
    null;

  // True when a turn is an A/B comparison carousel (two candidate slides). Such a
  // turn carries no `mx-auto` but holds the carousel region, so we must accept it
  // explicitly or it is never counted as a reply.
  const isCarouselItem = (c) => !!c && !!c.querySelector(S.carousel);

  function domTurns() {
    const ol = listEl();
    if (!ol) return [];
    return [...ol.children].filter(
      (c) =>
        (c.classList.contains("mx-auto") || isCarouselItem(c)) &&
        c.querySelector(S.box)
    );
  }

  // The markdown body we read for a turn. For a comparison carousel we ALWAYS read
  // candidate A = the FIRST slide's .prose (deterministic and consistent with the
  // "Continuer avec A" commit the loop performs); for a normal turn it is just the
  // turn's .prose. Routing every read through this keeps stream/parse/mask aligned
  // on a single candidate so a 2-slide carousel can never desync the loop.
  function proseOf(item) {
    if (!item) return null;
    const slide = item.querySelector(S.slide);
    return slide ? slide.querySelector(S.box) : item.querySelector(S.box);
  }

  // A carousel container is never right-aligned, so it classifies as assistant.
  const isUserItem = (item) => !!item && item.classList.contains("justify-end");
  const isAssistantItem = (item) => !!item && !isUserItem(item);

  // ── Chip anchor ───────────────────────────────────────────────────────────
  // The turn root (`.mx-auto`) opens with a sticky model-name header, so pinning
  // the chip at item.firstChild parks it ABOVE the reply. Redirect it into the
  // reply's own column instead: proseOf(item) is the markdown body (candidate A's
  // for an A/B carousel) and its parent `.flex.flex-col.gap-3` holds only that
  // body - appending there (chipAppend) drops the chip directly UNDER the reply
  // text (parity with Qwen/Kimi/GLM; verified live it sits below .prose). The
  // copy/vote action bar lives higher up the tree, OUTSIDE this column, so a
  // plain append never sinks below it and no chipTrailRef is needed. React
  // reconciles this subtree on stream updates, but ensureOwnedChip rebuilds the
  // chip from its stored opts after each wipe (same as the other providers).
  function chipAnchor(item) {
    if (!item) return item;
    const prose = proseOf(item);
    return (prose && prose.parentElement) || item;
  }

  // ── A/B "battle" resolution ───────────────────────────────────────────────
  // Arena periodically turns a reply into an A/B comparison: TWO candidates
  // stream side by side with "Continuer avec A / Ignorer / Continuer avec B"
  // controls. We always commit candidate A ("Continuer avec A"): the chosen reply
  // then lands in the message <ol> as a normal turn, and the rest of the loop
  // parses it with zero special-casing (chip / masking just work).
  // We do NOT use "Ignorer" (skip): skip is a flaky, heavily rate-limited backend
  // call ("Too many requests" → "Failed to skip battle") that stalled the loop.
  // Exact label match only, so a control that merely contains the words isn't hit.
  const CONT_A_RE = /^\s*(continuer avec a|continue with a)\s*$/i;
  // Any committing click is a backend call that can be throttled. enforceComposer
  // runs this every sweep (mutations + the 1.5s tick), so we (1) click at most
  // once per BATTLE_COOLDOWN_MS and (2) never click while a throttle toast shows:
  // clicking again only deepens the limit. The cooldown still retries a genuinely
  // pending battle, but slowly enough never to trip the limiter.
  const THROTTLE_RE =
    /too many requests|trop de requ[êe]tes|rate.?limit|failed to (skip|continue|vote)|impossible/i;
  const BATTLE_COOLDOWN_MS = 6000;
  let _battleAt = 0, _battleClicks = 0, _throttleLogged = false;
  function actionThrottled() {
    for (const el of document.querySelectorAll(S.errorSurfaces)) {
      if (el.offsetParent === null) continue;
      if (THROTTLE_RE.test(el.innerText || "")) return true;
    }
    return false;
  }
  function resolveBattle() {
    if(stopButton())return false; // Never vote while a candidate is still generating.
    if (Date.now() - _battleAt < BATTLE_COOLDOWN_MS) return false;
    if (actionThrottled()) {
      // Log the back-off only on the rising edge so the breadcrumb log isn't
      // flooded every sweep while the throttle toast lingers.
      if (!_throttleLogged) { _throttleLogged = true; diag("arena.battle_throttled", { clicks: _battleClicks }); }
      return false;
    }
    _throttleLogged = false;
    for (const b of document.querySelectorAll("button")) {
      if (b.offsetParent === null) continue;
      if (b.disabled || b.getAttribute("aria-disabled") === "true") continue;
      if (CONT_A_RE.test(b.textContent || "") || CONT_A_RE.test(ariaOf(b))) {
        _battleAt = Date.now();
        _battleClicks++;
        diag("arena.battle_pick_a", { n: _battleClicks, label: (b.textContent || "").trim().slice(0, 24) });
        try { b.click(); } catch {}
        return true;
      }
    }
    return false;
  }

  // Walk the tree skipping the core's chip (and any extra excluded subtree).
  function textWithout(root, excludeSel) {
    if (!root) return "";
    flushSurfaces();const skip=excludeSel&&excludeSel!=='.zs-chip'?'.zs-chip, '+excludeSel:'.zs-chip';
    let cache=surfaceObserver?proseTextCache.get(root):null;if(cache?.has(skip))return cache.get(skip);
    if(!cache){cache=new Map();if(surfaceObserver)proseTextCache.set(root,cache);}
    if(!root.querySelector(skip)){const text=root.textContent||'';cache.set(skip,text);return text;}
    let t = "";
    const walk = (n) => {
      if (n.nodeType === 3) { t += n.nodeValue; return; }
      if (n.nodeType !== 1) return;
      if (n.matches && n.matches(skip)) return;
      for (const c of n.childNodes) walk(c);
    };
    walk(root);
    cache.set(skip,t);return t;
  }

  // Assistant signature text = ONLY the .prose body (excludes the "Response
  // provided by …" header so a vendor name can never look like model output).
  function itemText(item) {
    if (!item) return "";
    const md = proseOf(item);
    return md ? textWithout(md) : "";
  }
  function classifyText(item, excludeSel) {
    if (!item) return "";
    const md = proseOf(item);
    if (!md || (excludeSel && md.closest(excludeSel))) return "";
    return textWithout(md, excludeSel);
  }

  // ── DOM primitives ──────────────────────────────────────────────────────
  // The list is flex-col-reverse (newest-first in the DOM); reverse so the core
  // sees the usual chronological order and lastAssistant() = the latest reply.
  const allItems = () => domTurns().reverse();
  const recentItems = (limit=4) => {
    const list=listEl(),out=[];if(!list)return out;
    for(const item of list.children){if((item.classList.contains('mx-auto')||isCarouselItem(item))&&item.querySelector(S.box))out.push(item);if(out.length>=limit)break;}
    return out.reverse();
  };
  const assistantItems = () => allItems().filter(isAssistantItem);
  const assistantCount = () => assistantItems().length;
  const userCount = () => allItems().filter(isUserItem).length;

  // The composer textarea = the ONLY <textarea> inside a <form> (other page
  // textareas are recaptcha/aria-hidden). Scope away Multi-Script's own settings
  // textarea (#zs-root) so the send hooks' "not on a chat page" guard holds on
  // login/OAuth pages that have no site composer.
  const getEditor = () => {
    for (const e of deepQueryAll("form textarea, textarea[data-testid*=composer], textarea[aria-label*=message i]")) {
      if (!e.closest('#zs-root,#zs-bar,[hidden],[inert],[aria-hidden="true"]')&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'){
        if(!activeUnsupportedMode())lastTextRoute=location.pathname;
        return e;
      }
    }
    return null;
  };
  const editorText = () => {
    const e = getEditor();
    if (!e) return "";
    return e.value != null ? e.value : e.textContent || "";
  };

  const lastAssistant = () => {
    // Native order is newest-first. A live read need not enumerate history.
    const list=listEl();if(!list)return null;
    for(const item of list.children)if(isAssistantItem(item)&&(item.classList.contains('mx-auto')||isCarouselItem(item))&&item.querySelector(S.box))return item;
    return null;
  };

  // Stable per-NODE identity for the latest assistant turn. The core prefers this
  // over assistantCount() to decide a fresh reply exists: count-based detection is
  // unreliable across an A/B battle (the reply renders in a carousel and the count
  // doesn't cleanly cross the send-time baseline), so without an id the core fell
  // back to counts and waited out the full 30s NO_TURN_GRACE after every battle.
  // A WeakMap assigns each turn element a monotonic id the first time it's seen;
  // a genuinely new reply node therefore yields a new id immediately.
  const _idMap = new WeakMap();
  let _idSeq = 0;
  function lastAssistantId() {
    const it = lastAssistant();
    if (!it) return null;
    let id = _idMap.get(it);
    if (!id) { id = ++_idSeq; _idMap.set(it, id); }
    return id;
  }

  const chatIsEmpty = () => allItems().length === 0;
  // A genuinely fresh chat: the /text/* route with the composer rendered and no
  // turns. An existing conversation is /c/<id>, so it never gates.
  const isFreshChat = () =>
    chatIsEmpty() && /^\/text\//.test(location.pathname) && !!getEditor();

  // The whole composer the Start gate hides as one unit = the <form>.
  const composerFrame = () => {
    const ed = getEditor();
    return ed ? ed.closest("form") : null;
  };

  // Arena is a React app that reconciles the composer subtree, so we must NOT
  // insert #zs-bar into it (the diff could nest the composer inside the bar, as
  // seen on Kimi/GLM). barAnchor() returns the rounded composer CARD; the core
  // (placeBar anchored branch) keeps the bar in #zs-root, hugs the card's top
  // edge at full width and reserves the strip with padding-top.
  function barAnchor() {
    const ed = getEditor();
    if (!ed) return null;
    let n = ed;
    for (let i = 0; i < 10 && n; i++) {
      if ([...n.classList].some((c) => c.startsWith("rounded"))) return n;
      n = n.parentElement;
    }
    return ed.closest("form");
  }

  // ── Input lock ────────────────────────────────────────────────────────────
  // The textarea is real: `readonly` blocks the user but is IGNORED by the
  // native prototype setter used in setTextareaValue(), so our own injections
  // keep working. getEditor() keys off the <form>, not the placeholder, so the
  // placeholder swap below is safe.
  function setInputLock(on) {
    const ed = getEditor();
    if (!ed) return;
    if (on) {
      if (!ed.dataset.zsPlaceholder) ed.dataset.zsPlaceholder = ed.getAttribute("placeholder") || "";
      ed.setAttribute("readonly", "");
      ed.setAttribute("placeholder", "⏳ Agent working… please wait");
    } else {
      ed.removeAttribute("readonly");
      if (ed.dataset.zsPlaceholder != null) ed.setAttribute("placeholder", ed.dataset.zsPlaceholder);
    }
  }

  // ── Action button (send / stop) ───────────────────────────────────────────
  const ariaOf = (b) => b.getAttribute("aria-label") || "";
  const allButtons = () => deepQueryAll("button");
  const sendButton = () => {
    const frame=composerFrame();if(!frame)return null;
    return [...frame.querySelectorAll('button')].find(b=>b.offsetParent!==null&&!b.closest('#zs-root,#zs-bar')&&!S.stopAria.test(ariaOf(b))&&(S.sendAria.test(ariaOf(b))||b.type==='submit'))||null;
  };
  const stopButton = () =>
    allButtons().find((b) => S.stopAria.test(ariaOf(b)) && b.offsetParent !== null) || null;

  // ── Generation detection ──────────────────────────────────────────────────
  // The stop button is present for the entire generation (validated). Growth
  // tracking is a belt-and-braces fallback for the start/end instants and a
  // guard against a wedged stop button (same defensive pattern as Gemini).
  function streamText(item) {
    if (!item) return "";
    const md = proseOf(item);
    return md ? textWithout(md, ".zs-chip") : "";
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

  const WEDGE_MS = 10000;
  let _stopSince = 0;
  function genActive() {
    // Stable candidate A cannot finish a native two-response comparison.
    if(comparisonPending())return true;
    sampleStream();
    const stop = !!stopButton();
    const now = Date.now();
    if (stop) {
      if (!_stopSince) _stopSince = now;
      return (now - _streamAt < WEDGE_MS) || (now - _stopSince < 2000);
    }
    _stopSince = 0;
    return grewWithin(timings.GEN_IDLE_MS);
  }
  const isGenerating = () => comparisonPending() || !!stopButton() || genActive();
  const isBusyNow = isGenerating;
  const isHardGenerating = () => !!stopButton();

  // Arena exposes no reliable per-turn "stopped" marker → never halted; and no
  // truncation Continue button.
  const turnHalted = () => false;
  const findContinueBtn = () => null;
  const clickContinueBtn = () => false;

  function snapshot() {
    try {
      const it = lastAssistant();
      if (!it) return { th: 0, rp: 0 };
      const md = proseOf(it);
      return { th: 0, rp: md ? (md.textContent || "").length : 0 };
    } catch { return {}; }
  }

  function readAssistant() {
    const item = lastAssistant();
    if (!item) return { present: false, reply: "", thinking: "", item: null };
    const md = proseOf(item);
    return {
      present: true,
      reply: md ? textWithout(md, ".zs-chip").trim() : "",
      thinking: "",
      item,
    };
  }

  async function waitFor(pred, timeout) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      if (pred()) return true;
      await sleep(120);
    }
    return false;
  }

  // ── Sending ───────────────────────────────────────────────────────────────
  // Arena's composer hard-caps the message at 120000 chars: past that the submit
  // button stays disabled forever (validated live 2026-06), so a large tool
  // result (e.g. a 144 KB http_get dump) silently wedges the loop in the input
  // box. We truncate outgoing text to a safe margin below the cap, keeping the
  // head AND tail so neither the start nor the end of a result is lost, and we
  // mark the gap so the model knows content was dropped. Arena-only: other
  // providers have their own (or no) limits and are left untouched.
  const SEND_CAP = 120000;   // composer hard limit
  const SEND_MAX = 118000;   // leave margin for the truncation marker
  function truncateForSend(text) {
    { const o = (text && typeof ZS !== "undefined" && ZS.limits) ? ZS.limits.sendOverride(text) : null; if (o !== null) return o; }
    if (!text || text.length <= SEND_CAP) return text;
    const omitted = text.length - SEND_MAX;
    const marker =
      `\n\n[…Multi-Script: result truncated to fit Arena's input limit - ` +
      `${omitted} of ${text.length} characters omitted…]\n\n`;
    const budget = SEND_MAX - marker.length;
    const headLen = Math.floor(budget * 0.85);
    const tailLen = budget - headLen;
    return text.slice(0, headLen) + marker + text.slice(text.length - tailLen);
  }

  // React-controlled <textarea>: set .value via the native prototype setter so
  // React's onChange fires, dispatch an input event, wait for the submit button
  // to re-enable, then click it (Enter would insert a newline).
  function setTextareaValue(el, v) {
    const proto = window.HTMLTextAreaElement && window.HTMLTextAreaElement.prototype;
    const setter = proto && Object.getOwnPropertyDescriptor(proto, "value");
    if (setter && setter.set) setter.set.call(el, v);
    else el.value = v;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // Short safety net only: the CORE owns the long verification wait (see
  // awaitHumanVerification in core/main.js, which parks with a visible banner and
  // auto-resumes). This guard exists purely so a challenge that appears in the
  // instant between the core's check and the actual send cannot be typed into.
  async function waitForHumanVerification(timeoutMs = 60000) {
    if (!captchaPresent()) return true;
    const started = Date.now();
    const challenge = detectChallenge();
    diag("arena.human_verification.wait", { timeoutMs, kind: challenge ? challenge.kind : null });
    while (captchaPresent() && Date.now() - started < timeoutMs) await sleep(400);
    const cleared = !captchaPresent();
    diag("arena.human_verification.done", { cleared, waitedMs: Date.now() - started });
    return cleared;
  }

  function comparisonPending(){
    const heading=[...document.querySelectorAll('h1,h2,h3,h4,[role="heading"]')].some(el=>el.offsetParent!==null&&!el.closest('.prose,#zs-root')&&/^which response do you prefer\??$/i.test((el.textContent||'').trim()));
    return heading||allButtons().some(b=>b.offsetParent!==null&&CONT_A_RE.test(b.textContent||''));
  }
  async function waitForSendReady({cancelled=()=>false,onWait=()=>{}}={}){
    const until=Date.now()+180000;let announced=false;
    while(isHardGenerating()||comparisonPending()){
      if(cancelled())return false;
      if(!announced){announced=true;onWait('Arena is still responding or waiting for a response selection. No follow-up has been sent.');}
      if(!isHardGenerating())resolveBattle();
      if(Date.now()>=until)return false;
      await sleep(250);
    }
    return !cancelled();
  }
  let sendInFlight=false,internalSend=false;
  async function restoreReferenceChat(controls){
    const mode=activeUnsupportedMode();if(mode?.aria!=='Image')return;
    if(!controls.referenceTask||!hasPendingAttachment())throw Object.assign(Error('Arena is in Image Arena. Return to Text Arena for this tool conversation; the draft and references are preserved.'),{retryable:false,sendState:'not-sent'});
    const visible=b=>b.offsetParent!==null&&b.getClientRects().length&&!b.closest('#zs-root,#zs-bar,[hidden],[inert],[aria-hidden="true"]')&&getComputedStyle(b).visibility!=='hidden';
    const exit=allButtons().find(b=>visible(b)&&/^(?:exit (?:image arena|image mode)|back to text arena|switch to text arena|use text arena)$/i.test((ariaOf(b)||b.textContent||'').trim()))||allButtons().find(b=>visible(b)&&ariaOf(b)==='Image'&&(b.getAttribute('aria-pressed')==='true'||/bg-surface-tertiary|bg-surface-raised-alt/.test(b.className)));
    if(!exit)throw Object.assign(Error('Arena switched the reference upload to Image Arena. Use its Exit Image Arena / Text Arena control, then retry the preserved draft.'),{retryable:false,sendState:'not-sent'});
    const count=pendingCount(),expectedRoute=lastTextRoute;exit.click();
    if(!await waitFor(()=>!activeUnsupportedMode(),2500)||expectedRoute&&location.pathname!==expectedRoute||count>0&&!hasPendingAttachment())throw Object.assign(Error('Arena could not restore the text conversation with its reference intact. No message was submitted; inspect the draft and reference.'),{retryable:false,sendState:'not-sent'});
    diag('arena.referenceTextRestored',{attachments:pendingCount()});
  }
  async function typeAndSend(text, images,controls={}) {
    const fail=(message,state='not-sent')=>Object.assign(Error(message),{retryable:false,sendState:state});
    if(sendInFlight)throw fail('Arena already has a send in progress.');
    sendInFlight=true;let clicked=false;
    try{
    if (!(await waitForHumanVerification()))
      throw new Error("Arena requires human verification. Complete the CAPTCHA manually, then retry; Multi-Script does not bypass verification challenges.");
    await restoreReferenceChat(controls);
    if(!await waitForSendReady(controls))throw fail('Arena is still responding or awaiting a response choice. No message was sent.');
    let editor = getEditor();
    if (!editor) throw new Error("Arena input box not found");
    const frame=composerFrame(),route=location.pathname;
    const expected=truncateForSend(String(text).replace(/\r\n?/g,'\n'));
    const normalize=t=>String(t).replace(/\r\n?/g,'\n').trimEnd();
    const check=()=>{
      if(controls.cancelled?.())throw fail('Arena send cancelled.',clicked?'unconfirmed':'not-sent');
      if(!clicked&&location.pathname!==route)throw fail('Arena chat changed. Draft preserved.');
      if(!clicked&&getEditor()!==editor){const next=getEditor();if(!editor.isConnected&&next&&frame?.isConnected&&frame.contains(next)&&normalize(editorText())===normalize(expected))editor=next;else throw fail('Arena composer changed. Draft preserved.');}
    };
    editor.focus();
    setTextareaValue(editor, expected);check();
    if (images && images.length) tagImages(images);
    diag("arena.tas.enter", {
      textLen: (text || "").length,
      imgId: images ? images.__zsId : null,
      imgCount: images ? images.length : 0,
      attachedId: _attachedImages ? _attachedImages.__zsId : null,
      sameSet: images === _attachedImages,
      pendingBefore: pendingCount(),
    });
    // The send button being ENABLED is Arena's own "ready to accept a send"
    // signal. CRITICAL for images: in an A/B battle the button stays DISABLED
    // while the SECOND candidate keeps streaming, but the core (which tracks
    // candidate A, already finished) calls us during that window. The button is
    // Arena's truth here, so we WAIT on it rather than on our own generation
    // heuristics. We wait BEFORE staging the image so a not-yet-sendable image is
    // never left visible/stranded in the composer (the reported "phantom" that
    // the next capture then inherited). Enabling also needs text present (set
    // above). Long window covers a slow second candidate.
    const sendReady = () => {
      check();
      const b = sendButton();
      return !!b && !isHardGenerating() && !b.disabled && b.getAttribute("aria-disabled") !== "true";
    };
    const ready1 = await waitFor(sendReady, 60000);
    if(!ready1){const error=new Error("Arena send control is not ready; no submit was attempted.");error.retryable=false;error.sendState="not-sent";throw error;}
    diag("arena.tas.ready", { ready: ready1 });
    // Attach last. Retain existing user references and do not stage the same
    // image set twice if it is already present after an interrupted preparation.
    if (images && images.length && images !== _attachedImages) {
      try {
        const ok = await attachImages(images);
        if(!ok)throw fail('Arena did not accept the image attachment. Draft preserved.');
        if (ok) _attachedImages = images;
        diag("arena.tas.attached", { imgId: images.__zsId, ok, pendingAfter: pendingCount() });
      } catch (e) { diag("arena.tas.attachErr", { msg: String(e && e.message || e) });throw e; }
      await restoreReferenceChat({...controls,referenceTask:true});
      // Native ingestion can disable Send for several seconds.
      if(!await waitFor(sendReady,60000))throw fail('Arena is still processing the reference upload. The draft and attachments are preserved; no submit was attempted.');
    } else {
      diag("arena.tas.skipAttach", { reason: !images || !images.length ? "no-images" : "same-set", imgId: images ? images.__zsId : null });
    }
    // Click once and confirm the cleared composer/new user turn. An uncertain
    // click preserves the draft and stops automatic replay.
    const beforeUsers=userCount();
    if(!sendReady()){const error=new Error('Arena send control changed before dispatch; no submit was attempted.');error.retryable=false;error.sendState='not-sent';throw error;}
    if(normalize(editorText())!==normalize(expected))throw fail('Arena did not retain the complete task. Nothing was sent.');
    clicked=true;internalSend=true;try{sendButton().click();}finally{internalSend=false;}
    const sent=await waitFor(()=>{check();return getEditor()===editor&&!editorText().trim()||userCount()>beforeUsers;},8000);
    diag("arena.tas.sent", {sent,editorLen:editorText().length,pendingAfterSend:pendingCount()});
    if(!sent){const error=new Error('Arena submit was attempted but no new turn or generation acknowledged it. Inspect the conversation before retrying.');error.retryable=false;error.sendState='unconfirmed';throw error;}
    _attachedImages=null;
    }catch(error){if(error.sendState)throw error;throw fail(error.message||String(error),clicked?'unconfirmed':'not-sent');}
    finally{sendInFlight=false;}
  }

  // Arena shows "Generating…" for a beat BEFORE the native "Stop generation"
  // button mounts (it only appears once the stream starts). A Stop click landing
  // in that window found no button to click, so the native generation ran on
  // (the loop halted, but the model kept streaming a turn). Click now if present;
  // otherwise poll briefly and click the instant the button appears, so the stop
  // is never swallowed by that gap.
  let _stopPoll = null;
  function stopGeneration() {
    if (_stopPoll) { clearInterval(_stopPoll); _stopPoll = null; }
    const b = stopButton();
    if (b) { try { b.click(); } catch {} return; }
    const t0 = Date.now();
    _stopPoll = setInterval(() => {
      const btn = stopButton();
      if (btn) { try { btn.click(); } catch {} clearInterval(_stopPoll); _stopPoll = null; return; }
      // Hard cap so the timer never lingers (a fresh Stop click restarts it). We
      // do NOT gate on genActive() here: during the pre-stream "Generating…" gap
      // there's no stop button AND no grown text yet, so genActive() is false -
      // the very window we must keep polling through.
      if (Date.now() - t0 > 8000) { clearInterval(_stopPoll); _stopPoll = null; }
    }, 120);
  }

  // ── Chat-mode gate (Direct only) ──────────────────────────────────────────
  // Arena has four chat modes (the conversation-mode dropdown): Direct (1 model),
  // Battle Mode (2 anonymous models → always an A/B comparison), Side by Side
  // (2 chosen models → also A/B), and Agent Mode (autonomous, single model).
  // Multi-Script only supports DIRECT. Battle / Side by Side force a fresh A/B
  // comparison on EVERY turn. Agent Mode is a SEPARATE app (route /agent, a
  // TipTap/ProseMirror contenteditable composer with NO <form>, and NO <ol>
  // message list) on which every DOM assumption here breaks - getEditor() returns
  // null so the bar can't even anchor; supporting it would be a full port, so it
  // stays gated. The mode dropdown's trigger is a `button[role="combobox"]` whose
  // visible text IS the current mode name; we read it to gate Start. Detection
  // fails OPEN (unknown → allow) so a DOM reskin never wrongly blocks the default.
  const MODE_RE = /\b(direct|battle|agent|side by side)\b/i;
  const SUPPORTED_MODES = new Set(["direct"]);
  function currentMode() {
    for (const c of document.querySelectorAll('button[role="combobox"]')) {
      if (c.offsetParent === null) continue;
      const m = (c.textContent || "").trim().toLowerCase().match(MODE_RE);
      if (m) return m[1];
    }
    return null; // unknown
  }
  // ── Unsupported composer modes (Build Apps / Web Search / Generate Image) ──
  // The composer's "Code", "Search" and "Image" buttons each switch the WHOLE
  // app from the plain chat route (/text/*) to their own route (/code/*,
  // /search/*, /image/*), where a turn no longer produces a normal .prose chat
  // reply but a different output surface (an app-build canvas, a web-search
  // result card, a generated-image card). Every DOM/stream assumption in this
  // provider breaks there and the loop wedges, so all three are gated exactly
  // like an unsupported chat mode. Primary signal is the route (set the instant
  // the button is pressed); the button's active background is a fallback in
  // case Arena ever toggles one without a route change (validated live: the
  // active button carries a literal `bg-surface-tertiary` class, absent when
  // idle - the OTHER `hover:bg-*` classes always present don't match this
  // substring check). Detection fails CLOSED for safety only on a positive match.
  const UNSUPPORTED_MODES = [
    { route: /^\/code\//, aria: "Code", label: "Build Apps", tip: "the <b>Code</b> button" },
    { route: /^\/search\//, aria: "Search", label: "Web Search", tip: "the <b>Search</b> (globe) button" },
    { route: /^\/image(?:\/|$)/, aria: "Image", label: "Generate Image", tip: "the <b>Image</b> button" },
  ];
  function activeUnsupportedMode() {
    for (const m of UNSUPPORTED_MODES) {
      if (m.route.test(location.pathname)) return m;
      for (const b of document.querySelectorAll(`button[aria-label="${m.aria}"]`)) {
        if (b.offsetParent === null) continue;
        if (b.getAttribute("aria-pressed") === "true") return m;
        if (/bg-surface-tertiary|bg-surface-raised-alt/.test(b.className)) return m;
      }
    }
    return null;
  }

  // True unless we POSITIVELY detect an unsupported mode (Battle / Side by Side)
  // or one of the composer's Build Apps / Web Search / Generate Image modes.
  const isSupportedMode = () => {
    if (activeUnsupportedMode()) return false;
    const m = currentMode();
    return m === null || SUPPORTED_MODES.has(m);
  };

  // ── One-shot: restore Direct on page load ──────────────────────────────────
  // Arena sometimes reloads into Battle mode (e.g. after a login/OAuth round-trip
  // bounces the tab), which Multi-Script can't drive. We nudge the mode dropdown
  // back to Direct ONCE per page load - never on a sweep, so a user who later
  // deliberately picks another mode is not fought (the mode guard/warning still
  // covers that case). We only touch the plain chat route and only when the
  // dropdown is on a non-Direct mode. Runs from init() with a retry window long
  // enough for the composer to mount after a post-login redirect.
  // The option label is glued to its description ("DirectChat with 1 model at a
  // time"), so a trailing \b after "direct" never matches - anchor on the prefix.
  function pickDirectOption() {
    for (const o of document.querySelectorAll('[role="option"]')) {
      if (o.offsetParent === null) continue;
      if (/^\s*direct/i.test(o.textContent || "")) { try { o.click(); } catch {} return true; }
    }
    return false;
  }
  async function restoreDirectOnce() {
    if (activeUnsupportedMode()) return; // Build Apps / Search / Image route - leave alone
    let combo = null;
    for (let i = 0; i < 60 && !combo; i++) { // up to ~15s for post-login load
      combo = [...document.querySelectorAll('button[role="combobox"]')].find((x) => x.offsetParent !== null) || null;
      if (!combo) await sleep(250);
    }
    if (!combo || /direct/i.test(combo.textContent || "")) return; // gone or already Direct
    // Open the dropdown only if it is closed - clicking an already-open combobox
    // would toggle it shut and there would be no option to pick.
    if (combo.getAttribute("aria-expanded") !== "true") { try { combo.click(); } catch {} }
    const ok = await waitFor(pickDirectOption, 2000);  // click the Direct option when it renders
    diag("arena.restore_direct", { ok, was: (combo.textContent || "").trim().slice(0, 24) });
    if (!ok && combo.getAttribute("aria-expanded") === "true") { try { combo.click(); } catch {} } // reclose on failure
  }

  // Visible mode guard for the Multi-Script bar (core renderBar reads this every
  // sweep). Returns a warning string while an unsupported mode (Battle / Side by
  // Side / Agent) is selected, "" when Direct (or mode unknown → fail open so a
  // DOM reskin never nags on the supported default). The core turns this into a
  // red warning state and disables Start until the user switches to Direct.
  function modeWarning() {
    const um = activeUnsupportedMode();
    if (um)
      return `Turn off <b>${um.label}</b> (${um.tip} in the composer) - ` +
        `Multi-Script only works in plain chat. ${um.label} mode uses a different ` +
        `output surface and breaks the agent loop.`;
    if (isSupportedMode()) return "";
    const m = currentMode();
    const name = m ? m.charAt(0).toUpperCase() + m.slice(1) : "another mode";
    return `Switch the mode dropdown to <b>Direct</b> - Multi-Script only works in ` +
      `Direct mode (current: <b>${name}</b>).`;
  }

  // A bot-check challenge is on screen (Cloudflare Turnstile / hCaptcha /
  // reCAPTCHA / Arkose FunCaptcha / DataDome / PerimeterX / GeeTest, or a plain
  // "verify you are human" interstitial). The core reads this to pause, move the
  // Multi-Script bar out of the way (the anchored bar is transparent but still a
  // real, full-width element over the composer's top edge, so it silently eats
  // clicks on the challenge's "Valider" button even though nothing is visible),
  // tell the user what to do, and then RESUME BY ITSELF once the challenge
  // clears. Solving, token-injecting, outsourcing or otherwise bypassing the
  // challenge is never attempted. In the enabled "Assist" mode the core may also
  // dispatch ONE trusted click on the provider's OWN widget via
  // assistChallengeClick() - never a token read, never an API call, never a
  // retry. See core/verification.js for why that is the honest boundary.
  //
  // Selector coverage is deliberately broad because Arena's provider can change
  // without notice; the TEXT probe below is the second, independent signal, so a
  // reskin that drops a class still gets caught by the wording on screen.
  const CAPTCHA_SEL =
    'iframe[src*="challenges.cloudflare.com"],' +
    'iframe[src*="turnstile"],' +
    'iframe[src*="hcaptcha.com"],' +
    'iframe[src*="recaptcha"],' +
    'iframe[src*="arkoselabs"],' +
    'iframe[src*="funcaptcha"],' +
    'iframe[src*="datadome"],' +
    'iframe[src*="captcha-delivery"],' +
    'iframe[src*="perimeterx"],' +
    'iframe[src*="perimeterx.net"],' +
    'iframe[src*="px-cdn"],' +
    'iframe[src*="px-captcha"],' +
    'iframe[src*="human-challenge"],' +
    'iframe[src*="geetest"],' +
    '.cf-turnstile,.cf-challenge,.cf-challenge-running,' +
    '.h-captcha,.g-recaptcha,.grecaptcha-badge,' +
    '.geetest_holder,#px-captcha,#captcha-container,[data-testid*="captcha" i]';
  // Wording a bot-check interstitial shows. Kept to phrases that do not appear
  // in ordinary chat content, and always paired with a visibility + size test.
  const CHALLENGE_TEXT_RE =
    /verify (?:you are|that you are) (?:a )?human|are you a robot|checking your browser|just a moment|unusual traffic|complete the security check|human verification|bot check|security check required|veuillez (?:v[ée]rifier|confirmer)|v[ée]rification humaine|je ne suis pas un robot/i;
  // The element kinds a challenge interstitial is actually rendered in. Scoped
  // so a model QUOTING the phrase inside a chat reply can never trip it.
  const CHALLENGE_HOSTS = '[role="alertdialog"],[role="dialog"],main > div,body > div,form,#challenge,#challenge-stage';
  // Truly on-screen? offsetParent ignores visibility:hidden / opacity:0, so we
  // must walk ancestors. This is what excludes Arena's ALWAYS-present reCAPTCHA
  // v3 badge (a 256x60 .grecaptcha-badge kept at visibility:hidden), which used
  // to false-positive and hide the bar on every page. An actual interactive
  // challenge (Turnstile / hCaptcha checkbox) is visible, sized, and in-viewport.
  function reallyVisible(el) {
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.display === "none" || s.visibility === "hidden" || parseFloat(s.opacity) === 0) return false;
    }
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 40) return false; // tiny badge, not a challenge
    return r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  }
  // Which challenge is on screen, if any. Returns { kind, hint } or null.
  // `kind` is a stable machine id (diagnostics / tests), `hint` is the short
  // human line the core shows in its banner.
  function detectChallenge() {
    for (const el of document.querySelectorAll(CAPTCHA_SEL)) {
      if (el.closest("#zs-root")) continue;
      if (!reallyVisible(el)) continue;
      // Identify the challenge from EVERYTHING the element exposes, not just its
      // src: a provider that renders Turnstile inline (a styled <div> with no
      // iframe yet) still carries the class, and the hint is what the user reads
      // in the banner. Falls back to a generic id rather than guessing.
      const sig = [
        (el.getAttribute && el.getAttribute("src")) || "",
        // getAttribute("class") rather than .className: on SVG elements
        // className is an SVGAnimatedString object, not a string, so a class-based
        // challenge id would be lost there.
        (el.getAttribute && el.getAttribute("class")) || (typeof el.className === "string" ? el.className : ""),
        el.id || "",
        (el.getAttribute && el.getAttribute("data-testid")) || "",
        (el.getAttribute && el.getAttribute("data-sitekey")) || "",
      ].join(" ").toLowerCase();
      const kind = /cloudflare|turnstile|cf-challenge/.test(sig) ? "cloudflare-turnstile"
        : /hcaptcha|h-captcha/.test(sig) ? "hcaptcha"
        : /recaptcha|g-recaptcha/.test(sig) ? "recaptcha"
        : /arkose|funcaptcha/.test(sig) ? "arkose"
        : /datadome|captcha-delivery/.test(sig) ? "datadome"
        : /perimeterx|px-captcha|px-cdn|human-challenge/.test(sig) ? "perimeterx"
        : /geetest/.test(sig) ? "geetest"
        : "embedded-challenge";
      return { kind, hint: `a ${kind.replace(/-/g, " ")} widget is on the page` };
    }
    // Second, independent signal: the wording of an interstitial, which survives
    // a class-name reskin. Requires a visible, prominent, chat-free host element
    // so model output quoting the phrase is never mistaken for a challenge.
    for (const el of document.querySelectorAll(CHALLENGE_HOSTS)) {
      if (el.closest("#zs-root") || el.closest(S.list)) continue;
      if (el.childElementCount > 12) continue; // a whole page, not a check card
      if (!reallyVisible(el)) continue;
      const t = (el.innerText || "").trim();
      if (t.length > 400 || t.length < 8) continue;
      if (!CHALLENGE_TEXT_RE.test(t)) continue;
      return { kind: "text-challenge", hint: `the page says: "${t.split("\n")[0].slice(0, 90)}"` };
    }
    return null;
  }
  function captchaPresent() {
    try { return !!detectChallenge(); } catch { return false; }
  }
  // One-line description of what was detected, for the core's verification
  // banner. Empty when nothing is on screen.
  function verificationHint() {
    const d = detectChallenge();
    return d ? d.hint : "";
  }
  // ── Assisted first-click ────────────────────────────────────────────────
  // The closest thing to "keeping it running" that is NOT a bypass. On a
  // checkbox-style challenge (Cloudflare Turnstile in managed mode, hCaptcha
  // passive) the widget presents a real checkbox and a single trusted click is
  // exactly what a human does - nothing is read, forged, harvested or injected.
  // We click the widget's own host element and STOP there: if the provider then
  // renders a puzzle or asks for more, no amount of scripted clicking is
  // legitimate, and we hand it back to the human.
  //
  // Deliberately NOT done here (and asserted absent by test): reading or writing
  // any token field, calling grecaptcha/hcaptcha execute APIs, postMessage into
  // the challenge iframe, or contacting any third-party solving service. Those
  // are the things that get accounts closed.
  function challengeClickTarget() {
    // Only the challenge HOSTS that are safe to click: the widget container,
    // never an inner control we cannot verify. A real iframe cannot be
    // scripted from here anyway (cross-origin), so for iframe-based challenges
    // this resolves to the visible host box, which is what a human aims at.
    const sel =
      '.cf-turnstile,' +
      '.h-captcha,' +
      '.g-recaptcha:not(.grecaptcha-badge),' +
      '#px-captcha,' +
      '#captcha-container,' +
      '[data-testid*="captcha" i],' +
      'iframe[src*="challenges.cloudflare.com"],' +
      'iframe[src*="hcaptcha.com"],' +
      'iframe[src*="recaptcha"]';
    for (const el of document.querySelectorAll(sel)) {
      if (el.closest("#zs-root")) continue;
      // The always-present reCAPTCHA v3 badge is not an interactive challenge.
      if (el.classList && el.classList.contains("grecaptcha-badge")) continue;
      if (!reallyVisible(el)) continue;
      return el;
    }
    return null;
  }
  // Perform ONE trusted click on the provider's own challenge widget. Returns a
  // small result object for diagnostics: { clicked, reason, tag }. Never throws
  // and never retries - a repeat click is exactly what makes this look scripted.
  function assistChallengeClick() {
    let el = null;
    try { el = challengeClickTarget(); } catch { el = null; }
    if (!el) return { clicked: false, reason: "no-widget" };
    try {
      const r = el.getBoundingClientRect();
      // Aim at the widget's visual centre - for a checkbox widget that is the
      // box itself, which is the whole gesture a human makes.
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const base = { bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy };
      // A full pointer + mouse sequence reads as a real interaction, rather
      // than a bare synthetic click that some widgets ignore.
      if (typeof PointerEvent === "function") {
        el.dispatchEvent(new PointerEvent("pointerdown", { ...base, pointerId: 1, isPrimary: true, button: 0 }));
      }
      el.dispatchEvent(new MouseEvent("mousedown", { ...base, button: 0 }));
      if (typeof PointerEvent === "function") {
        el.dispatchEvent(new PointerEvent("pointerup", { ...base, pointerId: 1, isPrimary: true, button: 0 }));
      }
      el.dispatchEvent(new MouseEvent("mouseup", { ...base, button: 0 }));
      el.dispatchEvent(new MouseEvent("click", { ...base, button: 0 }));
      // NOTE: stop here. No token read, no API call, no retry, no loop.
      return { clicked: true, tag: el.tagName ? el.tagName.toLowerCase() : "el" };
    } catch (e) {
      return { clicked: false, reason: "click-failed", detail: String(e && e.message || e) };
    }
  }

  // A modal dialog (login / create-account / consent) is open over the page.
  // Arena renders these as Radix dialogs = a visible [role="dialog"]. While one is
  // up, the anchored Multi-Script bar (a real, full-width element hugging the
  // composer's top edge) sits ON TOP of the modal and silently intercepts clicks
  // on its buttons - e.g. "Continue with Google" at sign-in. The core hides the
  // bar whenever this is true (same get-out-of-the-way path as captchaPresent).
  // reallyVisible() ignores display:none / detached closed dialogs, so a chat page
  // with no open modal never matches. Our own UI lives in #zs-root and is skipped.
  function overlayBlocking() {
    for (const d of document.querySelectorAll('[role="dialog"]')) {
      if (d.closest("#zs-root")) continue;
      if (reallyVisible(d)) return true;
    }
    return false;
  }

  // No model/tier to enforce (Direct/Max + model picker left to the user); the
  // only requirement is a supported chat mode (Direct or Agent). Also resolve any
  // A/B battle the instant its "Continuer avec A" button appears (this runs every
  // sweep), so the comparison commits to candidate A and the loop reads a single
  // normal reply.
  function enforceComposer() {
    // While a challenge is up the page is not ours to drive: clicking an A/B
    // "Continuer avec A" button would be an interaction with a page the site has
    // explicitly frozen for verification. Skip every write until it clears.
    if (!captchaPresent()) resolveBattle();
    return { ready: isSupportedMode() };
  }
  async function ensureComposerReady(reason) {
    const supported = isSupportedMode();
    const challenge = detectChallenge();
    const humanVerificationRequired = !!challenge;
    diag("mode_ready", { reason, provider: "arena", mode: currentMode(), supported, humanVerificationRequired, challenge: challenge ? challenge.kind : null });
    // Never automate, solve, token-inject, or bypass a challenge. The core parks
    // until the user clears it and then continues the same turn (see
    // awaitHumanVerification in core/main.js).
    if (humanVerificationRequired) return { ready: false, humanVerificationRequired: true, verificationKind: challenge.kind, verificationHint: challenge.hint };
    return { ready: supported && !!getEditor(), humanVerificationRequired: false };
  }

  // ── Error / limit detection (site chrome only, never model output) ───────
  function scanError() {
    try {
      for (const el of document.querySelectorAll(S.errorSurfaces)) {
        if (el.offsetParent === null) continue;
        if (el.closest(S.list)) continue; // inside a chat turn ⇒ model content
        const t = (el.innerText || "").trim();
        if (t.length > 8 && t.length < 600 && RE.contextLimit.test(t)) return t.slice(0, 240);
      }
    } catch {}
    if (!getEditor()) return "The input box disappeared (session ended?).";
    return null;
  }
  const isTooLongMsg = (text) => RE.tooLong.test(text);
  const isBusyMsg = (text) => RE.busy.test(text);

  // ── Image attachment (validated live 2026-07 on /text/direct) ─────────────
  // Arena's composer <form> holds ONE always-mounted hidden `input[type=file]`
  // (accept image/png,jpeg,webp, multiple). Setting its `.files` + dispatching
  // `change` stages the image and mounts a preview card - a synthetic paste is
  // NOT needed (and React ignores it here), so we drive the input directly like
  // GLM. The July layout kept a local blob preview until Send. Current layouts
  // may ingest files asynchronously or switch into Image Arena: a preview is
  // attachment evidence, while native send readiness is checked separately.
  function fileFromImage(img, i) {
    const mime = img.mimeType || "image/jpeg";
    const bin = atob(img.data);
    const arr = new Uint8Array(bin.length);
    for (let j = 0; j < bin.length; j++) arr[j] = bin.charCodeAt(j);
    const ext = mime.includes("png") ? "png" : mime.includes("webp") ? "webp" : "jpg";
    return new File([arr], `zeroscript_${Date.now()}_${i}.${ext}`, { type: mime });
  }
  // The PENDING preview: each staged image mounts as
  // `.flex.flex-wrap.gap-2 > div.group > img` (alt = filename, blob: src) INSIDE
  // the composer <form>. A SENT image renders inside the chat <ol> turn instead
  // (outside the form), so scoping to the form naturally excludes history and a
  // leftover from a previous capture never reads as "already pending".
  const pendingPreview = () => {
    const frame = composerFrame();
    return frame ? frame.querySelector('.flex.flex-wrap.gap-2 img,[data-testid="attachment-preview"] img,[data-testid="file-preview"] img,[data-attachment-id] img') : null;
  };
  const hasPendingAttachment = () => !!pendingPreview();
  // How many staged preview cards are currently in the composer (diagnostics).
  const pendingCount = () => {
    const frame = composerFrame();
    return frame ? frame.querySelectorAll('.flex.flex-wrap.gap-2 img,[data-testid="attachment-preview"] img,[data-testid="file-preview"] img,[data-attachment-id] img').length : 0;
  };
  // Stamp a stable id on an images array so the diag trace can tell which SET is
  // being (re)attached across the core's retries (same array = same id).
  let _imgSeq = 0;
  function tagImages(images) {
    if (images && images.__zsId == null) {
      try { Object.defineProperty(images, "__zsId", { value: ++_imgSeq, enumerable: false }); } catch { images.__zsId = ++_imgSeq; }
    }
    return images;
  }
  function fileInputEl() {
    const frame = composerFrame();
    return frame ? frame.querySelector('input[type="file"]') : null;
  }
  async function attachImages(images) {
    const inp = fileInputEl();
    if (!inp || !images || !images.length) return false;
    const dt = new DataTransfer();
    images.forEach((img, i) => { try { dt.items.add(fileFromImage(img, i)); } catch {} });
    if (!dt.items.length) return false;
    try {
      inp.files = dt.files;
      inp.dispatchEvent(new Event("change", { bubbles: true }));
    } catch { return false; }
    diag("attach.set", { count: dt.items.length });
    const ok = await waitFor(hasPendingAttachment, 15000);
    diag("attach.preview", { ok });
    return ok;
  }
  function clearAttachments() {
    try {
      const frame = composerFrame();
      if (!frame) return;
      // Each staged card carries a per-card `button[aria-label="Remove file"]`.
      frame.querySelectorAll('.flex.flex-wrap.gap-2 button[aria-label="Remove file"]')
        .forEach((d) => { try { d.click(); } catch {} });
    } catch {}
  }

  // /text/* = a fresh chat with no conversation id yet → "" (transient, never
  // persisted as "started"). A real conversation is /c/<uuid>.
  const conversationKey = () => (/^\/text\//.test(location.pathname) ? "" : location.pathname);

  // ── User-send interception ────────────────────────────────────────────────
  function installSendHooks(handlers) {
    document.addEventListener(
      "keydown",
      (e) => {
        if(internalSend)return;
        if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
        const editor = getEditor();
        if (!editor || !editor.contains(e.target)) return;
        if (editorText().trim() === "") return;
        if (handlers.isBlocked()) {e.preventDefault();e.stopImmediatePropagation();handlers.onBlockedAttempt?.();return;}
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
        if(internalSend)return;
        if (!getEditor()) return;
        const btn = e.target && e.target.closest && e.target.closest("button");
        if (!btn) return;
        if (S.stopAria.test(ariaOf(btn))) { handlers.onNativeStop(); return; }
        if (!S.sendAria.test(ariaOf(btn))) return;
        if (btn.disabled || btn.getAttribute("aria-disabled") === "true") return;
        if (handlers.isBlocked()) {e.preventDefault();e.stopImmediatePropagation();handlers.onBlockedAttempt?.();return;}
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
  // Arena renders each fenced code block as a real <pre> wrapped in a
  // <div class="not-prose"> (markers/JSON intact in textContent). Hide every
  // such wrapper carrying a command shape, plus any bare top-level block holding
  // an inline command. React recreates the rendered subtree on stream settle and
  // on the next send (wiping per-element .zs-tool-hide), so also mark the turn
  // (its identity survives - the chip is anchored at item level) with
  // .zs-cmd-mask; the overlay.css rule keeps recreated code wrappers hidden.
  const CMD_SHAPE = /"(?:command|tool)"\s*:\s*"|###\s*lua|###mcp_tool###|<\/?\s*[|｜].*dsml/i;
  function findToolBlockSpot(item /*, chip */) {
    const md = proseOf(item);
    if (!md) return null;
    let hidAny = null;
    // 1. Fenced code wrappers carrying a command.
    md.querySelectorAll(S.codeWrap).forEach((cw) => {
      if (cw.closest(".zs-chip")) return;
      if (CMD_SHAPE.test(cw.textContent || "")) {
        cw.classList.add("zs-tool-hide");
        item.classList.add("zs-cmd-mask");
        hidAny = hidAny || { parent: cw.parentElement, ref: cw };
      }
    });
    // 2. Bare top-level blocks with an inline command (no code wrapper inside).
    [...md.children].forEach((el) => {
      if (el.classList.contains("zs-chip") || el.querySelector(S.codeWrap)) return;
      const t = el.textContent || "";
      if ((t.length < 600 && CMD_SHAPE.test(t)) || (t.length > 8 && /^\s*\{\s*"(?:c|t)/.test(t))) {
        el.classList.add("zs-tool-hide");
        item.classList.add("zs-cmd-mask");
        hidAny = hidAny || { parent: el.parentElement, ref: el };
      }
    });
    return hidAny;
  }

  return {
    id: "arena",
    displayName: "Arena",
    providerHardening: "shadow-dom+semantic-controls+verification-safe",
    // Arena's chat composer accepts image uploads (hidden `input[type=file]` in
    // the form → staged preview card → uploaded on send; see attachImages). The
    // underlying model varies per selection, but the vision-capable ones DO read
    // the attached image - confirmed LIVE 2026-07 (Anthropic via "Max" described
    // a probe image correctly). So screen_capture is exposed here (main.js
    // BLOCKED_TOOLS gate). Note: a model the user has picked that lacks vision
    // will simply ignore the image; there's no per-model signal to gate on.
    supportsVision: true,
    timings,
    // React reconciles a turn's content subtree on every update, wiping a chip
    // placed inside it. Anchor chips at the turn-element level instead
    // (redirected into the reply column by chipAnchor).
    chipAtItemLevel: true,
    chipAnchor,
    // Arena writes narration THEN the tool call at the end of the turn, so trail
    // the chip after the reply text (chipAppend) rather than pinning it above the
    // model-name header - it then sits BELOW the reply, like the other providers.
    // No chipTrailRef: the reply column holds only the .prose body, so a plain
    // append lands the chip right under it; ensureOwnedChip re-asserts it across
    // React's re-renders of the reply subtree.
    chipAppend: true,
    // No unstableWarning chip: the live mode guard (modeWarning) already shows a
    // visible, reactive warning + disables Start whenever a non-Direct mode is
    // selected, which covers the only Arena caveat that chip used to flag.
    // Turn elements are not virtualized away here, so assistantCount() reliably
    // increases for every new reply - the core's watcher uses this to refuse
    // finalizing before this send's reply turn exists.
    reliableCounts: true,
    init({ diag: d } = {}) { if (d) diag = d; try { restoreDirectOnce(); } catch {} },
    // turns
    allItems, isUserItem, isAssistantItem, itemText, classifyText,
    assistantCount, userCount, lastAssistant, lastAssistantId, readAssistant,
    streamLen, snapshot, recentItems,
    // composer / state
    getEditor, editorText, chatIsEmpty, isFreshChat, composerFrame, barAnchor,
    setInputLock, typeAndSend, stopGeneration, waitForSendReady,
    isGenerating, isBusyNow, isHardGenerating, strictGeneration:true, waitingForUser:()=>comparisonPending()&&!isHardGenerating(),
    enforceComposer, ensureComposerReady, modeWarning, captchaPresent, waitForHumanVerification, overlayBlocking,
    detectChallenge, verificationHint, challengeClickTarget, assistChallengeClick,
    turnHalted, findContinueBtn, clickContinueBtn,
    scanError, isTooLongMsg, isBusyMsg,
    // actions
    attachImages, clearAttachments, conversationKey,
    getStartupProfilePrompt, getAutoRoutingProfile, setAutoRoutingProfile, autoRoutingProfiles, routingProfileDiagnostics, prepareOutboundPrompt,
    installSendHooks, findToolBlockSpot,
  };
})();
