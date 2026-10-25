// SPDX-License-Identifier: GPL-3.0-or-later
// Notion AI provider adapter.
//
// Notion ships its AI on app.notion.com as a hashed-class React bundle, and it
// has TWO entirely different editable surfaces on that origin:
//
//   1. normal page blocks  (/p/..., /<workspace>/...)  — contenteditable, but
//      pressing Enter adds a page block; this is NOT an AI composer.
//   2. the AI surface      (/ai landing, /chat/:id thread) — the real composer.
//
// Both are contenteditable, and a previous generation of this adapter selected
// page blocks after Notion's login redirect landed on /p/Welcome-to-Notion...,
// typed the whole system prompt into the document and waited forever for a
// reply. So the first thing this file does is refuse to run anywhere except the
// two genuine AI routes. A false negative yields a useful "composer not ready",
// a false positive can overwrite a user's page — the asymmetry is deliberate.
//
// Within an AI route, the composer is resolved by SCORING candidates rather
// than matching one class name, and the result is memoised per route so a long
// transcript does not force thousands of layout reads on every keystroke.
const ZSProvider = (() => {
  "use strict";
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const storageGet = (key) => { try { return globalThis.localStorage.getItem(key); } catch { return null; } };
  const storageSet = (key, value) => { try { globalThis.localStorage.setItem(key, value); return true; } catch { return false; } };
  const storageRemove = (key) => { try { globalThis.localStorage.removeItem(key); } catch {} };
  let diag = () => {};
  const timings = {
    GEN_IDLE_MS: 1800, REASON_IDLE_MS: 12000, WARMUP_MS: 45000,
    REASON_NOREPLY_MS: 90000, STABLE_MS: 9000, RESPONSE_TIMEOUT_MS: 300000,
  };

  // ── Route surface guard ─────────────────────────────────────────────────
  // Only these two route families are an AI surface. Everything else on
  // notion.com/notion.so is a document, and must never be typed into.
  const AI_LANDING_RE = /^\/ai\/?$/;
  const AI_THREAD_RE = /^\/chat(?:\/|$)/;
  const isAiLanding = () => AI_LANDING_RE.test(location.pathname || "");
  const isAiThread = () => AI_THREAD_RE.test(location.pathname || "");
  const isAiSurface = () => isAiLanding() || isAiThread();
  const routeKey = () => `${location.pathname || ""}${location.search || ""}`;
  // Escape hatch for the route guard, armed ONLY by an explicit user action
  // (openAIChat - the "Open AI chat" recovery control). Never set from ambient
  // page state on its own.
  let _explicitOpen = false;

  // Route-independent POSITIVE EVIDENCE that this page really is a Notion AI
  // surface: an Agent transcript anchor, or a composer carrying the AI
  // placeholder. This is what lets the adapter work on an AI surface that does
  // not live at exactly /ai or /chat (an embedded/hosted Agent, a rewritten
  // route) WITHOUT opening the door on an ordinary document page.
  //
  // This replaced an unconditional `_explicitOpen = true` inside init(). That was
  // a mistake: the core initializes the provider on EVERY notion.so page, so
  // arming the override there disabled the route guard everywhere. On an ordinary
  // workspace page the adapter then resolved an unrelated container, anchored the
  // bar to it, and the bar floated in the middle of an empty page - precisely the
  // misplacement that got reported. Evidence-based detection keeps the guard's
  // teeth while still recognising a genuine AI surface wherever it lives.
  function hasAiSurfaceEvidence() {
    try {
      if (document.querySelector(AGENT_ROW_SEL)) return true;
      if (document.querySelector(DIRECT_PLACEHOLDER_SEL)) return true;
      for (const el of document.querySelectorAll(EDITOR_SEL)) {
        const hint = (el.getAttribute && (el.getAttribute("placeholder") ||
          el.getAttribute("data-placeholder") || el.getAttribute("aria-placeholder") ||
          el.getAttribute("aria-label"))) || "";
        if (hint && COMPOSER_TEXT_RE.test(hint)) return true;
      }
    } catch {}
    return false;
  }
  const surfaceOk = () => isAiSurface() || _explicitOpen || hasAiSurfaceEvidence();
  // Notion treats /ai query parameters as executable launch payloads: q, aq and
  // defaultUserMessage become an auto-submitted first message, and aiAction /
  // targetConfig can launch a native workspace action. A session must begin on
  // the literal, payload-free /ai URL so its first request is our bootstrap.
  const isCleanAiLanding = () => isAiLanding() && !location.search && !location.hash;

  const visible = (el) => {
    if (!el || !el.isConnected) return false;
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") return false;
    const r = el.getBoundingClientRect();
    return !!(el.getClientRects().length || r.width || r.height);
  };
  // Cheaper single-geometry read used during candidate scanning. Off-screen
  // history, hidden measurement inputs and 1px a11y shims are all excluded.
  function candidateVisible(el) {
    if (!el || !el.isConnected || el.hidden) return false;
    try {
      const r = el.getBoundingClientRect();
      return r.width >= 80 && r.height >= 12 && r.bottom > 0 && r.top < innerHeight + 120;
    } catch { return true; }
  }

  const CONTROL_SEL = "button, [role='button']";
  const controlDisabled = (el) => !el || el.disabled === true ||
    (el.getAttribute && el.getAttribute("aria-disabled") === "true");
  const ariaOf = (el) => (el && el.getAttribute && (el.getAttribute("aria-label") || "")) || "";
  const txtOf = (el) => ((el && (el.textContent || "")) || "").trim();
  const isTextControl = (el) => !!el && /^(INPUT|TEXTAREA)$/.test(el.tagName || "");

  // Every plausible rich-text / chat composer surface, in one selector.
  const EDITOR_SEL =
    "textarea, input[type='text'], input[type='search'], [contenteditable], " +
    ".ProseMirror, .tiptap, [role='textbox']";
  // Copy Notion currently paints in the full-page AI composer. Older wordings
  // are kept because Notion A/B-tests this string.
  const COMPOSER_TEXT_RE = /(do anything with|anything with ai|ask notion ai|ask ai|ask anything|what would you like|message.*(?:ai|notion)|start typing|reply to|your message)/i;
  const DIRECT_PLACEHOLDER_SEL =
    "[data-placeholder*='do anything with' i], [aria-placeholder*='do anything with' i], " +
    "[placeholder*='do anything with' i], [aria-label*='do anything with' i], " +
    "[data-placeholder*='ask notion ai' i], [aria-placeholder*='ask notion ai' i], " +
    "[placeholder*='ask notion ai' i], [aria-label*='ask notion ai' i], " +
    "[data-placeholder*='anything with ai' i], [aria-placeholder*='anything with ai' i], " +
    "[placeholder*='anything with ai' i], [aria-label*='anything with ai' i], " +
    "[data-placeholder*='ask anything' i], [aria-placeholder*='ask anything' i], " +
    "[placeholder*='ask anything' i], [aria-label*='ask anything' i]";
  const SEND_RE = /send|submit/i;
  const STOP_RE = /(?:^|\b)(?:stop|cancel|interrupt|arr[êe]ter)(?:\b|$)/i;

  function queryAllDeep(selector, root = document) {
    const out = [], seen = new Set(), roots = [root];
    while (roots.length) {
      const cur = roots.shift(); if (!cur || seen.has(cur)) continue; seen.add(cur);
      try {
        for (const el of cur.querySelectorAll(selector)) out.push(el);
        for (const el of cur.querySelectorAll("*")) if (el.shadowRoot) roots.push(el.shadowRoot);
      } catch {}
    }
    return [...new Set(out)];
  }

  // ── Composer resolution ─────────────────────────────────────────────────
  // Memoised per route. A connected positive composer is stable for the life of
  // the route; negatives are cached briefly so a lazily mounting composer is
  // still discovered quickly without a full DOM scan on every mutation.
  let _editorCache = null, _editorAt = 0, _candAt = 0, _candCache = [];
  let _editorRoute = "", _lastEditorLogged = null;
  let _frameCache = null, _frameEditor = null, _cardCache = null, _cardEditor = null;
  let _phCache = null, _phAt = 0;

  function resetEditorCacheForRoute() {
    const key = routeKey();
    if (key === _editorRoute) return;
    // Distinguish the FIRST resolution (cache initialization, _editorRoute === "")
    // from a genuine NAVIGATION. Only a real navigation may drop the explicit-open
    // override - otherwise the very first lookup after init()/openAIChat() would
    // wipe the latch that was just armed, before it ever had a chance to work.
    const wasInitialized = _editorRoute !== "";
    _editorRoute = key;
    _editorCache = null; _editorAt = 0;
    _candCache = []; _candAt = 0;
    _phCache = null; _phAt = 0;
    _frameCache = null; _frameEditor = null; _cardCache = null; _cardEditor = null;
    _lastEditorLogged = null;
    // A new route means a new context: drop the override so the guard is fully
    // in force again on whatever page we actually landed on.
    if (wasInitialized) _explicitOpen = false;
  }
  // Transcript guard. Notion paints every historical message - including OUR
  // long bootstrap/system prompt - with block-editor nodes that are
  // [contenteditable] (often ="false"). Those must never be adopted as the
  // composer: doing so mis-sizes the "Agent is working" cover into the middle of
  // the page, hides the message text via .zs-typing, and points composerFrame()
  // at a container with no Stop/Send button, so generation is never seen and the
  // bootstrap spins on "Starting..." forever.
  function transcriptEditable(e) {
    try {
      if (!e || isTextControl(e)) return false;
      if ((e.getAttribute && e.getAttribute("contenteditable")) === "false") return true;
      if (e.closest && e.closest(AGENT_ROW_SEL)) return true;
      if (e.querySelector && e.querySelector(AGENT_ROW_SEL)) return true;
    } catch {}
    return false;
  }
  function editableNode(el) {
    if (!el) return null;
    if (el.matches && el.matches(EDITOR_SEL)) return el;
    return (el.closest && el.closest(EDITOR_SEL)) || null;
  }
  // The visible placeholder is frequently a sibling overlay rather than an
  // attribute on the editable node, so walk a few local wrappers.
  function editableNear(el) {
    if (!el) return null;
    const direct = editableNode(el);
    if (direct) return direct;
    let n = el.parentElement;
    for (let i = 0; n && i < 6; n = n.parentElement, i++) {
      const own = editableNode(n);
      if (own) return own;
      const inside = n.querySelector && n.querySelector(EDITOR_SEL);
      if (inside) return inside;
    }
    return null;
  }
  function directPlaceholderEditable() {
    if (!surfaceOk()) return null;
    let best = null, bestBottom = -Infinity;
    try {
      for (const n of document.querySelectorAll(DIRECT_PLACEHOLDER_SEL)) {
        if (n.closest && n.closest("#zs-root")) continue;
        const ed = editableNear(n);
        if (!ed || !ed.isConnected || !candidateVisible(ed) || transcriptEditable(ed)) continue;
        let bottom = 0;
        try { bottom = ed.getBoundingClientRect().bottom; } catch {}
        if (!best || bottom > bestBottom) { best = ed; bestBottom = bottom; }
      }
    } catch {}
    return best;
  }
  // Attribute/label pass first (cheap, catches plain textareas), then a bounded
  // text walk for builds that paint the copy as a plain overlay div, then focus
  // as a last signal - but only ever on an AI route.
  function placeholderEditable() {
    if (!surfaceOk()) return null;
    const now = Date.now();
    if (_phAt && now - _phAt < 900) return _phCache && _phCache.isConnected ? _phCache : null;
    _phAt = now; _phCache = null;
    try {
      // Deliberately NOT unioned with EDITOR_SEL: historical page blocks are
      // themselves contenteditable and would drag the whole transcript in.
      const nodes = document.querySelectorAll(
        "[data-placeholder], [aria-placeholder], [placeholder], [aria-label]");
      for (const n of nodes) {
        if (n.closest && n.closest("#zs-root")) continue;
        const hint = ((n.getAttribute("data-placeholder") || "") + " " +
          (n.getAttribute("aria-placeholder") || "") + " " +
          (n.getAttribute("placeholder") || "") + " " +
          (n.getAttribute("aria-label") || "")).slice(0, 180);
        if (!COMPOSER_TEXT_RE.test(hint)) continue;
        const ed = editableNear(n);
        if (ed && ed.isConnected && candidateVisible(ed) && !transcriptEditable(ed)) { _phCache = ed; return ed; }
      }
    } catch {}
    try {
      const root = document.body || document.documentElement;
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let n, seen = 0;
      while ((n = walker.nextNode()) && ++seen <= 1400) {
        const text = (n.nodeValue || "").replace(/\s+/g, " ").trim();
        if (!text || text.length > 100 || !COMPOSER_TEXT_RE.test(text)) continue;
        const ed = editableNear(n.parentElement);
        if (ed && ed.isConnected && candidateVisible(ed) && !transcriptEditable(ed) && !(ed.closest && ed.closest("#zs-root"))) {
          _phCache = ed; return ed;
        }
      }
    } catch {}
    const ae = document.activeElement;
    if (ae && ae.isConnected && !(ae.closest && ae.closest("#zs-root"))) {
      const ed = editableNode(ae);
      if (ed && candidateVisible(ed) && !transcriptEditable(ed)) { _phCache = ed; return ed; }
    }
    return null;
  }
  function editorCandidates() {
    resetEditorCacheForRoute();
    if (!surfaceOk()) return [];
    const now = Date.now();
    if (_candAt && now - _candAt < 350) return _candCache;
    // The live composer carries a strong AI placeholder. Resolve that targeted
    // path first so a normal send never inspects thousands of historical blocks.
    const direct = directPlaceholderEditable();
    if (direct) { _candAt = now; _candCache = [direct]; return _candCache; }
    const out = [];
    const push = (e) => {
      if (e && e.isConnected && !(e.closest && e.closest("#zs-root")) &&
          candidateVisible(e) && !transcriptEditable(e) && !out.includes(e)) out.push(e);
    };
    try { document.querySelectorAll(EDITOR_SEL).forEach(push); } catch {}
    try {
      let hosts = 0;
      for (const h of document.querySelectorAll("div, section, main")) {
        if (++hosts > 220) break;
        if (h.shadowRoot) h.shadowRoot.querySelectorAll(EDITOR_SEL).forEach(push);
      }
    } catch {}
    const ph = placeholderEditable();
    if (ph) push(ph);
    _candAt = now; _candCache = out;
    return out;
  }
  // Ranking. A bare "search" input scores ~4; a real composer textarea plus its
  // AI placeholder and a local send control scores 9+, which is the threshold
  // findEditorRaw enforces.
  function editorHintScore(e) {
    let s = 0;
    if (e.tagName === "TEXTAREA") s += 8;
    else if (e.tagName === "INPUT") s += 4;
    if (e.isContentEditable || (e.getAttribute && /^(true|plaintext-only)$/i.test(e.getAttribute("contenteditable") || ""))) s += 2;
    if (e.matches && e.matches(".ProseMirror, .tiptap, [role='textbox']")) s += 3;
    const ph = ((e.getAttribute && (e.getAttribute("placeholder") || "")) + " " +
                (e.getAttribute && (e.getAttribute("data-placeholder") || "")) + " " +
                (e.getAttribute && (e.getAttribute("aria-placeholder") || "")) + " " +
                (e.getAttribute && (e.getAttribute("aria-label") || ""))).slice(0, 240);
    let strongComposerHint = COMPOSER_TEXT_RE.test(ph);
    if (strongComposerHint) s += 9;
    if (/(ask|send|message|chat|\bai\b)/i.test(ph)) s += 3;
    for (let n = e.parentElement, i = 0; n && i < 6; n = n.parentElement, i++) {
      if (n.querySelector && [...n.querySelectorAll(CONTROL_SEL)].some((b) =>
        SEND_RE.test(ariaOf(b)) || SEND_RE.test(b.getAttribute("data-testid") || "") ||
        SEND_RE.test(b.title || "") || STOP_RE.test(ariaOf(b)))) { s += 5; break; }
    }
    // Shadow-boundary escape. Notion mounts the Agent composer inside an open
    // shadow root, where the form and its Send button are INVISIBLE to the
    // parentElement walk above (it stops dead at the host). Without this the
    // shadow composer scores ~5 - contenteditable(2) + role=textbox(3) - and
    // never clears the threshold, so the always-on recovery action silently did
    // nothing on exactly the surface it exists for. Walk OUT through the host
    // chain and look for composer evidence in the host's tree instead.
    if (!strongComposerHint) {
      let host = e.getRootNode && e.getRootNode();
      for (let up = 0; up < 3 && host && host.host; up++) {
        const outer = host.host;
        // The form/container that wraps the shadow host may hold the controls.
        for (let n = outer, i = 0; n && i < 4; n = n.parentElement, i++) {
          if (n.querySelector && [...n.querySelectorAll(CONTROL_SEL)].some((b) =>
            SEND_RE.test(ariaOf(b)) || SEND_RE.test(b.getAttribute("data-testid") || "") ||
            SEND_RE.test(b.title || "") || STOP_RE.test(ariaOf(b)))) { s += 5; strongComposerHint = true; break; }
          if (n.querySelector && n.querySelector("form[data-testid], form[class*='composer' i]")) { s += 5; strongComposerHint = true; break; }
        }
        if (strongComposerHint) break;
        host = outer.getRootNode && outer.getRootNode();
      }
    }
    let nearbyComposerHint = false;
    for (let n = e.parentElement, i = 0; n && i < 4; n = n.parentElement, i++) {
      // Only SHORT containers count: a huge ancestor (a transcript message, the
      // system prompt) trivially contains words like "reply to" / "your message".
      const nt = n.textContent || "";
      if (nt.length <= 400 && COMPOSER_TEXT_RE.test(nt)) {
        nearbyComposerHint = true; s += 7; break;
      }
    }
    // Notion uses content-editable-leaf-rtl for BOTH page blocks and the AI
    // composer. Without a placeholder or nearby composer copy it is a page
    // block, so penalise it hard.
    if (/content-editable-leaf/i.test(String(e.className || "")) &&
        !strongComposerHint && !nearbyComposerHint) s -= 12;
    // An assistant answer is a block-editor root; without its own composer copy
    // it is transcript, not input.
    try {
      if (!strongComposerHint && e.closest && e.closest(BLOCK_RESPONSE_ROOT_SEL)) s -= 12;
    } catch {}
    return s;
  }
  function findEditorRaw() {
    // The single most important guard in this file: never inspect a normal
    // Notion page editor. This is what fixes the /p/Welcome-to-Notion case.
    resetEditorCacheForRoute();
    if (!surfaceOk()) return null;
    const now = Date.now();
    if (_editorCache && candidateVisible(_editorCache) && !_editorCache.disabled &&
        (isTextControl(_editorCache) || _editorCache.getAttribute("contenteditable") !== "false")) return _editorCache;
    if (_editorCache) {
      _editorCache = null; _editorAt = 0;
      _frameCache = null; _frameEditor = null; _cardCache = null; _cardEditor = null;
      _candCache = []; _candAt = 0;
      _phCache = null; _phAt = 0;
    }
    if (_editorAt && now - _editorAt < 1200) return null;
    const cands = editorCandidates();
    if (!cands.length) { _editorAt = now; _editorCache = null; return null; }
    const scored = cands.map((c) => {
      let bottom = 0;
      try { bottom = c.getBoundingClientRect().bottom; } catch {}
      return { c, s: editorHintScore(c), bottom };
    });
    scored.sort((a, b) => (b.s - a.s) || (b.bottom - a.bottom));
    // Require real composer evidence.
    if (!scored.length || scored[0].s < 9) { _editorAt = now; _editorCache = null; return null; }
    const top = scored[0].c;
    _editorCache = top; _editorAt = now;
    if (_lastEditorLogged !== top) {
      _lastEditorLogged = top;
      try {
        diag("notion.editor.found", {
          tag: top.tagName, type: top.getAttribute && top.getAttribute("type"),
          editable: top.getAttribute && top.getAttribute("contenteditable"),
          role: top.getAttribute && top.getAttribute("role"),
          placeholder: top.getAttribute && (top.getAttribute("placeholder") || top.getAttribute("data-placeholder")),
          cls: String(top.className || "").slice(0, 60), hint: scored[0].s,
          cands: cands.length, path: location.pathname,
        });
      } catch {}
    }
    return top;
  }
  function getEditor() {
    const e = findEditorRaw();
    if (!e || e.disabled) return null;
    if (isTextControl(e)) return e;
    return e.getAttribute("contenteditable") !== "false" ? e : null;
  }
  const edText = (e) => { if (!e) return ""; return isTextControl(e) ? (e.value || "") : (e.textContent || ""); };
  const editorText = (el) => edText(el || findEditorRaw());

  // ── Composer frame (the box the bar docks to) ───────────────────────────
  // ALIGNMENT (the "doesn't line up with the Notion chatbar" report):
  // Notion's AI composer is a rounded card that is WIDER than the text column
  // inside it. Docking the bar to the card's outer rect put the brand hard
  // against the rounded corner while the placeholder text started ~20px further
  // in, so the bar looked bolted on rather than part of the composer. Two things
  // fix that: pick the frame whose width best matches the composer's inner
  // content column, and report the inset the core must add so the bar's own
  // padding lines up with Notion's text (see barInset below).
  // Legacy lenient frame: used for CONTROL lookups (send/stop/model buttons), where
  // a generous container is what we want. Geometry uses cardFrame() below.
  function composerFrame() {
    if (!surfaceOk()) return null;
    const e = findEditorRaw();
    if (!e) return null;
    if (_frameEditor === e && _frameCache && _frameCache.isConnected && _frameCache.contains(e)) return _frameCache;
    const er = e.getBoundingClientRect ? e.getBoundingClientRect() : null;
    // Tightest-wins: `fallback` used to be overwritten by every matching
    // ancestor, so the OUTERMOST (largest) container won - which is how an
    // unrelated page column could be adopted as the composer frame. Take the
    // closest matching ancestor instead.
    let fallback = null, chosen = null;
    for (let n = e.parentElement, i = 0; n && n !== document.body && i < 7; n = n.parentElement, i++) {
      const r = n.getBoundingClientRect ? n.getBoundingClientRect() : null;
      const sized = r && r.width >= 200 && r.height >= 54 && r.height <= 360;
      // Never grow into a container that holds the transcript.
      try { if (n.querySelector(AGENT_ROW_SEL)) break; } catch {}
      if (sized && !fallback) fallback = n;
      if (n.querySelector && n.querySelector(CONTROL_SEL) && sized) { chosen = n; break; }
    }
    // Shadow-boundary escape: the parentElement walk dies at the host, so a
    // shadow-hosted composer never reaches the <form>/Send button that lives in
    // the OUTER tree. Climb through the host chain and adopt the first ancestor
    // that actually contains controls and is composer-shaped.
    if (!chosen) {
      let host = e.getRootNode && e.getRootNode();
      for (let up = 0; up < 3 && host && host.host && !chosen; up++) {
        for (let n = host.host, i = 0; n && n !== document.body && i < 5; n = n.parentElement, i++) {
          const r = n.getBoundingClientRect ? n.getBoundingClientRect() : null;
          if (!fallback && r && r.width >= 200 && r.height >= 54 && r.height <= 360) fallback = n;
          if (n.querySelector && n.querySelector(CONTROL_SEL) && r && r.height >= 54 && r.height <= 360) { chosen = n; break; }
        }
        host = host.host.getRootNode && host.host.getRootNode();
      }
    }
    // Prefer, among the candidates we actually measured, the one whose width is
    // closest to (editor content width + the padding we will add). A frame much
    // wider than that is a page column, not the composer card, and docking to it
    // is exactly the misalignment being fixed.
    if (er && er.width > 0) {
      const want = er.width + 40; // 20px of card padding on each side
      const candidates = [chosen, fallback].filter((n) => n && n.getBoundingClientRect);
      const scored = candidates
        .map((n) => ({ n, r: n.getBoundingClientRect() }))
        .filter((x) => x.r && x.r.width >= 200 && x.r.height >= 54 && x.r.height <= 360)
        .sort((a, b) => Math.abs(a.r.width - want) - Math.abs(b.r.width - want));
      if (scored.length) chosen = scored[0].n;
    }
    _frameEditor = e;
    // Last resort is the editor's own parent (never a distant ancestor), so a
    // composer we cannot measure still yields a frame that at least CONTAINS the
    // editor rather than some unrelated page column.
    _frameCache = chosen || fallback || e.parentElement;
    return _frameCache;
  }

  // ── 6.25 rewrite: pick the composer's VISUAL CARD, validate it, and never trust
  // an oversized wrapper. The old search took the first ancestor that merely
  // "contained controls and was < 360px tall". On Notion's empty-chat state the
  // composer sits inside a tall, empty rounded wrapper (usage banner glued to its
  // top edge), and that wrapper - or a tall flex row holding the editor at its
  // bottom - was adopted, so the bar floated in the MIDDLE of an empty card
  // instead of sitting on the input. Candidates are now scored on what makes a
  // composer card a composer card (rounded + painted surface, hugging the
  // editor tightly, holding the send/attach controls, roughly editor-wide) and
  // the result is re-validated every frame by barGeometry() below.
  const FRAME_MAX_H = 420, FRAME_MIN_H = 54;
  function parentOfNode(n) {
    if (!n) return null;
    if (n.parentElement) return n.parentElement;
    const root = n.getRootNode && n.getRootNode();
    return root && root.host ? root.host : null;
  }
  function paintedSurface(n) {
    try {
      const cs = getComputedStyle(n);
      const radius = Math.max(parseFloat(cs.borderTopLeftRadius) || 0, parseFloat(cs.borderTopRightRadius) || 0);
      const m = String(cs.backgroundColor || "").match(/rgba?\(([^)]+)\)/);
      const alpha = m ? (m[1].split(",").length > 3 ? parseFloat(m[1].split(",")[3]) : 1) : 0;
      const border = ["Top", "Right", "Bottom", "Left"].some((k) => (parseFloat(cs["border" + k + "Width"]) || 0) > 0 && cs["border" + k + "Style"] !== "none");
      const shadow = cs.boxShadow && cs.boxShadow !== "none";
      return { radius, painted: alpha > 0.04 || border || !!shadow, border, shadow: !!shadow };
    } catch { return { radius: 0, painted: false }; }
  }
  function scoreFrame(n, er) {
    const r = n.getBoundingClientRect ? n.getBoundingClientRect() : null;
    if (!r || r.width < 200 || r.height < FRAME_MIN_H || r.height > FRAME_MAX_H) return -1;
    const tol = 3;
    if (r.left > er.left + tol || r.right < er.right - tol || r.top > er.top + tol || r.bottom < er.bottom - tol) return -1;
    const topGap = er.top - r.top, botGap = r.bottom - er.bottom;
    if (topGap > 120) return -1; // editor is not near the top of this box: it is a wrapper, not the card
    let sc = 0;
    const ps = paintedSurface(n);
    if (ps.radius < 5 && !ps.painted) return -1; // an unstyled box is a layout wrapper, never the visual card
    if (ps.radius >= 10) sc += 9; else if (ps.radius >= 5) sc += 4;
    if (ps.painted) sc += 6;
    try { if (n.querySelector && n.querySelector(CONTROL_SEL)) sc += 4; } catch {}
    const want = er.width + 40, dw = Math.abs(r.width - want);
    sc += Math.max(0, 8 - dw / 12);                 // width close to editor + ~20px each side
    sc += Math.max(0, 6 - (topGap + botGap) / 24);  // hugs the editor vertically
    sc -= Math.max(0, r.height - 260) / 40;         // very tall boxes are probably wrappers
    return sc;
  }
  // Current Notion empty chats can use a genuinely tall composer canvas. Keep
  // rejecting an old-style small composer inside a tall presentation wrapper,
  // but accept a tall painted card when the editor itself is tall, nearly fills
  // the width, starts near the top, and the card owns a composer control.
  function largeComposerFrame(n, er) {
    const r = n && n.getBoundingClientRect ? n.getBoundingClientRect() : null;
    if (!r || er.height < 120 || r.height <= FRAME_MAX_H ||
        r.height > Math.max(520, (innerHeight || 900) * 0.86)) return false;
    const topGap = er.top - r.top, sideL = er.left - r.left, sideR = r.right - er.right;
    if (topGap < -3 || topGap > 96 || sideL < -3 || sideR < -3 ||
        sideL > 80 || sideR > 80) return false;
    const ps = paintedSurface(n);
    if (!ps.painted || ps.radius < 8) return false;
    try { return !!(n.querySelector && n.querySelector(CONTROL_SEL)); } catch { return false; }
  }
  // notion.ai currently also ships a large empty canvas whose actual editable
  // row stays near the BOTTOM. Its lower toolbar wrappers are mounted and
  // unmounted while React measures the composer. Letting cardFrame() alternate
  // between one of those wrappers and the outer canvas made the fixed bar jump
  // between two y coordinates every frame ("twitching"). Resolve the stable
  // outer canvas explicitly and dock above the editor without mutating it.
  function bottomCanvasFrame(e, er) {
    let hit = null;
    for (let n = parentOfNode(e), i = 0; n && n !== document.body && n !== document.documentElement && i < 10; n = parentOfNode(n), i++) {
      const r = n.getBoundingClientRect ? n.getBoundingClientRect() : null;
      if (!r || r.width < 240 || r.height < 220 || r.height > Math.max(760, (innerHeight || 900) * 0.9)) continue;
      const topGap = er.top - r.top, bottomGap = r.bottom - er.bottom;
      const sideL = er.left - r.left, sideR = r.right - er.right;
      if (topGap < 120 || bottomGap < -4 || bottomGap > 120 ||
          sideL < -4 || sideR < -4 || sideL > 100 || sideR > 100) continue;
      const ps = paintedSurface(n);
      if (!ps.painted || ps.radius < 8) continue;
      try { if (!n.querySelector || !n.querySelector(CONTROL_SEL)) continue; } catch { continue; }
      hit = n; // keep climbing: prefer the stable outer visual canvas
    }
    return hit;
  }
  function cardFrame() {
    if (!surfaceOk()) return null;
    const e = findEditorRaw();
    if (!e) return null;
    if (_cardEditor === e && _cardCache && _cardCache.isConnected && _cardCache.contains(e)) {
      // Re-score cheaply if the cached box stopped being a plausible card (the
      // composer grew, Notion re-laid-out, a banner appeared).
      const er0 = e.getBoundingClientRect();
      if (scoreFrame(_cardCache, er0) >= 0) return _cardCache;
      _cardCache = null; _cardEditor = null;
    }
    const er = e.getBoundingClientRect ? e.getBoundingClientRect() : null;
    if (!er || !er.width) return null;
    let best = null, bestScore = -1;
    for (let n = parentOfNode(e), i = 0; n && n !== document.body && n !== document.documentElement && i < 10; n = parentOfNode(n), i++) {
      const sc = scoreFrame(n, er);
      if (sc > bestScore) { best = n; bestScore = sc; }
    }
    if (bestScore < 8) {
      for (let n = parentOfNode(e), i = 0; n && n !== document.body && n !== document.documentElement && i < 10; n = parentOfNode(n), i++) {
        if (largeComposerFrame(n, er)) { best = n; bestScore = 8; break; }
      }
    }
    _cardEditor = e;
    _cardCache = bestScore >= 8 ? best : null; // below this it is not a card: barGeometry() docks to the editor itself
    return _cardCache;
  }

  // The single source of truth for where the bar goes. Always validated against
  // the editor's real rectangle, so even a Notion layout we have never seen docks
  // the bar on the input rather than somewhere in the page.
  //   mode "card"   - a real composer card was found: sit at its top edge, inside it
  //   mode "editor" - no trustworthy card: sit directly above the editor row
  function barMount(){
    const e=findEditorRaw();if(!e)return null;
    const er=e.getBoundingClientRect();if(bottomCanvasFrame(e,er))return null;
    const card=cardFrame(),parent=card?.parentElement;if(!parent||parent===document.body)return null;
    const c=getComputedStyle(parent),r=card.getBoundingClientRect();
    // Add a sibling outside the native composer only in a single-column flow.
    // Row/grid layouts retain the validated geometry fallback.
    if(c.display.includes('flex')&&!c.flexDirection.startsWith('column'))return null;
    if(c.display.includes('grid')&&c.gridTemplateColumns.split(/\s+/).length>1)return null;
    if(getComputedStyle(card).position==='absolute'||getComputedStyle(card).position==='fixed')return null;
    return {parent,before:card,inside:false,width:r.width};
  }
  let _lastGeoMode = "";
  function barGeometry() {
    const e = findEditorRaw();
    if (!e) return null;
    const er = e.getBoundingClientRect();
    if (!er || !er.width) return null;
    const canvas = bottomCanvasFrame(e, er);
    if (canvas) {
      const cr = canvas.getBoundingClientRect();
      const inset = barInset(canvas) || {
        left: Math.max(12, Math.round(er.left - cr.left)),
        right: Math.max(12, Math.round(cr.right - er.right)),
      };
      _lastGeoMode = "editor";
      return {
        mode: "editor", el: canvas, reserve: null,
        left: cr.left, top: er.top, width: cr.width, height: er.height, inset,
      };
    }
    const frame = cardFrame();
    if (frame) {
      const fr = frame.getBoundingClientRect();
      const inset = barInset(frame) || { left: 20, right: 20 };
      _lastGeoMode = "card";
      return { mode: "card", dockOutside:true, el: frame, reserve: null, left: fr.left, top: fr.top, width: fr.width, height: fr.height, inset };
    }
    const pad = Math.max(0, Math.min(18, Math.round(er.left - (e.parentElement ? e.parentElement.getBoundingClientRect().left : er.left))));
    _lastGeoMode = "editor";
    return { mode: "editor", el: e, reserve: null, left: er.left - pad, top: er.top, width: er.width + pad * 2, height: er.height, inset: { left: pad, right: pad } };
  }
  function resetLayoutCache() { _frameCache = null; _frameEditor = null; _cardCache = null; _cardEditor = null; _editorAt = 0; }
  function layoutReport() {
    const e = findEditorRaw(), g = barGeometry();
    const rc = (n) => { try { const b = n.getBoundingClientRect(); return [b.left, b.top, b.width, b.height].map(Math.round); } catch { return null; } };
    return {
      surface: surfaceOk(), path: location.pathname, mode: g && g.mode,
      editor: e ? rc(e) : null, frame: g && g.el ? rc(g.el) : null,
      viewport: [innerWidth, innerHeight], geometry: g ? [g.left, g.top, g.width].map(Math.round) : null,
    };
  }

  // How far the bar's own content must be inset so it lines up with the text
  // column INSIDE the composer card. Derived from the frame's real horizontal
  // padding (plus a small optical nudge), so a Notion restyle that changes the
  // card padding is followed automatically instead of being hardcoded to one
  // number that silently rots. The CSS carries the same default for the frame we
  // cannot measure.
  function barInset(given) {
    const frame = given || cardFrame() || composerFrame();
    if (!frame) return null;
    try {
      // Best signal: where the composer's own text column really starts and ends.
      // Lining the bar up with THAT (not with a padding guess) is what makes the
      // brand dot sit exactly above the placeholder text and the last control
      // above the send button, at any composer width or Notion restyle.
      const ed = findEditorRaw(), er = ed && ed.getBoundingClientRect && ed.getBoundingClientRect();
      const fr = frame.getBoundingClientRect();
      if (er && er.width > 0 && fr.width > 0) {
        const l = er.left - fr.left, r = fr.right - er.right;
        if (l >= 4 && l <= 72 && r >= 4 && r <= 72) return { left: Math.round(l), right: Math.round(r) };
      }
    } catch {}
    try {
      const s = getComputedStyle(frame);
      const pl = parseFloat(s.paddingLeft) || 0;
      const pr = parseFloat(s.paddingRight) || 0;
      if (pl >= 4 || pr >= 4) return { left: Math.round(pl + 1), right: Math.round(pr + 1) };
    } catch {}
    return { left: 20, right: 20 };
  }
  function composerContainer() {
    const semantic = composerFrame();
    if (semantic) return semantic;
    const e = getEditor(); if (!e) return null;
    return e.closest("form,[data-testid*='composer' i],[class*='composer' i]") || e.parentElement;
  }

  // ── Send / stop controls ────────────────────────────────────────────────
  // Notion implements its composer controls as focusable DIVs with role=button
  // (live: data-testid=agent-send-message-button / agent-chat-send-button), so
  // querying only <button> strands drafts. Both stable ids are tried first.
  const controlsIn = (root) => (root ? [...root.querySelectorAll(CONTROL_SEL)] : []);
  const sendControlLike = (b) => !!b &&
    (b.getAttribute("data-testid") === "agent-send-message-button" ||
     SEND_RE.test(ariaOf(b)) || SEND_RE.test(b.getAttribute("data-testid") || "") ||
     SEND_RE.test(b.title || ""));
  const stopControlLike = (b) => {
    if (!b) return false;
    const text = txtOf(b), testId = b.getAttribute("data-testid") || "";
    return /agent-(?:stop|interrupt)/i.test(testId) ||
      STOP_RE.test(ariaOf(b)) || STOP_RE.test(testId) || STOP_RE.test(b.title || "") ||
      (STOP_RE.test(text) && text.length <= 40);
  };
  const exactSendControl = (frame, controls) =>
    (controls || controlsIn(frame)).find((b) =>
      /^(?:agent-send-message-button|agent-chat-send-button)$/.test(b.getAttribute("data-testid") || "")) || null;
  function controlAvailable(el) {
    if (!el || !el.isConnected) return false;
    if (!document.hidden) return visible(el);
    // Background tabs report a zero viewport rect even for a live composer, so
    // keep the CSS checks but omit geometry.
    try {
      const s = getComputedStyle(el);
      return s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity || 1) !== 0;
    } catch { return true; }
  }
  function sendButton() {
    if (!surfaceOk()) return null;
    const frame = composerFrame();
    if (!frame) return null; // never scan every control on a normal Notion page
    const controls = controlsIn(frame);
    const exact = exactSendControl(frame, controls);
    if (exact) return controlAvailable(exact) && !controlDisabled(exact) ? exact : null;
    const hit = controls.find((b) => sendControlLike(b) && controlAvailable(b) && !controlDisabled(b));
    if (hit) return hit;
    // Geometric fallback: the commit affordance sits to the right of the text.
    const e = findEditorRaw();
    if (!e) return null;
    const er = e.getBoundingClientRect();
    return controls.filter((b) => {
      const label = `${ariaOf(b)} ${b.title || ""} ${b.getAttribute("data-testid") || ""} ${txtOf(b)}`;
      const r = b.getBoundingClientRect();
      return !/stop|cancel|attach|plus|settings|option|filter|microphone|voice/i.test(label) &&
        controlAvailable(b) && !controlDisabled(b) &&
        r.left >= er.left + er.width * 0.55 && r.bottom >= er.top && r.top <= er.bottom + 24;
    }).sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right)[0] || null;
  }
  // A missed stop button makes the loop believe the turn ended while it is still
  // streaming, so the label test is deliberately broad and backed by testid.
  function stopButton() {
    if (!surfaceOk()) return null;
    const frame = composerFrame();
    const inFrame = frame && controlsIn(frame).find((b) => stopControlLike(b) && controlAvailable(b) && !controlDisabled(b));
    if (inFrame) return inFrame;
    // Stable-testid fallback: when the composer card could not be resolved (or
    // Notion renders Stop outside it) the Stop control is still unambiguous.
    try {
      for (const b of document.querySelectorAll("[data-testid*='agent-stop' i], [data-testid*='agent-interrupt' i]")) {
        if (!(b.closest && b.closest("#zs-root")) && controlAvailable(b) && !controlDisabled(b)) return b;
      }
    } catch {}
    return null;
  }
  // Notion mounts a "running-placeholder:" transcript row for as long as the
  // Agent is working, even before any token or Stop button is readable. Bounded
  // so a stale row can never hold the loop open forever.
  let _runPhSince = 0;
  function runningPlaceholder() {
    let found = false;
    try { found = !!document.querySelector("[data-agent-service-scroll-anchor^='running-placeholder:']"); } catch {}
    if (!found) { _runPhSince = 0; return false; }
    const now = Date.now();
    if (!_runPhSince) { _runPhSince = now; _runPhStopped = false; }
    // Notion's agent sometimes never leaves its own start-up phase: the
    // placeholder stays mounted with no text at all. After 75s of nothing,
    // stop that turn so the core's empty-turn recovery re-sends instead of
    // sitting on "Starting Up" forever. A turn that has produced text keeps
    // the longer 150s bound.
    const limit = maxLen > 0 ? 150000 : 75000;
    if (now - _runPhSince >= limit) {
      if (!_runPhStopped) {
        _runPhStopped = true;
        try { diag("notion.agentStall", { ms: now - _runPhSince, text: maxLen }); } catch {}
        try { stopGeneration(); } catch {}
      }
      return false;
    }
    return true;
  }
  let _runPhStopped = false;

  // ── Transcript ──────────────────────────────────────────────────────────
  // Stable semantic anchor from Notion's Agent bundle. Every transcript row
  // carries it while all CSS class names are hashed. User rows align flex-end,
  // assistant rows flex-start, centered rows are status/progress.
  const AGENT_ROW_SEL = "[data-agent-service-scroll-anchor]";
  // Live fallback for builds that expose no anchor: every assistant answer is a
  // self-contained block editor root with one or more [data-block-id] children.
  const BLOCK_RESPONSE_ROOT_SEL = "[data-content-editable-root='true']";
  const _alignCache = new WeakMap();
  const _endAlignedCache = new WeakMap();
  function rowAlign(row) {
    if (!row) return "";
    const inline = row.style && row.style.justifyContent;
    if (inline) return inline;
    const cached = _alignCache.get(row);
    if (cached) return cached;
    let v = "";
    try { v = getComputedStyle(row).justifyContent || ""; } catch {}
    if (v) _alignCache.set(row, v);
    return v;
  }
  function rawAgentRows() {
    if (!surfaceOk()) return [];
    let rows = [];
    try { rows = [...document.querySelectorAll(AGENT_ROW_SEL)]; } catch { return []; }
    // Tool-detail rows carry the same anchor inside a top-level message row;
    // only top-level transcript events are exposed.
    return rows.filter((r) =>
      !(r.closest && r.closest("#zs-root")) &&
      !(r.parentElement && r.parentElement.closest && r.parentElement.closest(AGENT_ROW_SEL)));
  }
  function agentMessageRows(rows = rawAgentRows()) {
    return rows.filter((r) => {
      const align = rowAlign(r);
      if (align === "flex-end") return true;      // user message
      if (align !== "flex-start") return false;   // centered status/progress
      const key = (r.getAttribute("data-agent-service-scroll-anchor") || "").toLowerCase();
      if (/^(running-placeholder|interrupting|interrupt-sent):/.test(key)) return false;
      // An assistant message mounts before its first token. Omit the empty
      // shell until text arrives; generation state still comes from Stop.
      return !!(txtOf(r) || r.querySelector("pre, code, img, [aria-label*='copy' i], [aria-label*='response' i]"));
    });
  }
  function hasEndAlignedAncestor(el) {
    const now = Date.now(), cached = _endAlignedCache.get(el);
    // A positive user-bubble alignment is stable. Recheck an initial negative
    // once after mount, since Notion can apply wrapper layout a tick later.
    if (cached && (cached.value || cached.checks >= 2 || now - cached.at < 1500)) return cached.value;
    for (let n = el, i = 0; n && n !== document.body && i < 6; n = n.parentElement, i++) {
      let jc = (n.style && n.style.justifyContent) || "", fd = (n.style && n.style.flexDirection) || "";
      try {
        const cs = getComputedStyle(n);
        if (!jc) jc = cs.justifyContent || "";
        if (!fd) fd = cs.flexDirection || "";
      } catch {}
      // A column flex-end container merely pins the transcript to the bottom;
      // only horizontal end alignment identifies a user bubble.
      if ((jc === "flex-end" || jc === "end") && !/^column/.test(fd)) {
        _endAlignedCache.set(el, { value: true, at: now, checks: (cached?.checks || 0) + 1 });
        return true;
      }
    }
    _endAlignedCache.set(el, { value: false, at: now, checks: (cached?.checks || 0) + 1 });
    return false;
  }
  function blockAssistantRoots() {
    if (!isAiThread()) return [];
    let roots = [];
    try { roots = [...document.querySelectorAll(BLOCK_RESPONSE_ROOT_SEL)]; } catch { return []; }
    const ed = findEditorRaw();
    const frame = composerFrame();
    return roots.filter((r) => {
      if (!r.isConnected || (r.closest && r.closest("#zs-root"))) return false;
      if ((ed && (r === ed || r.contains(ed) || ed.contains(r))) || (frame && frame.contains(r))) return false;
      if (r.parentElement && r.parentElement.closest(BLOCK_RESPONSE_ROOT_SEL)) return false;
      if (!r.querySelector("[data-block-id]")) return false;
      const text = r.textContent || "";
      if (!/\S/.test(text) && !r.querySelector("img, video, pre, code")) return false;
      if (hasEndAlignedAncestor(r)) return false;
      return true;
    });
  }

  const turnSelector = [
    "[data-message-author-role]", "[data-role='user']", "[data-role='assistant']",
    "[data-testid*='chat-message' i]", "[data-testid*='agent-message' i]", "[data-testid*='user-message' i]", "[data-testid*='message' i]",
    "[data-message-id]", "[data-author]", "[data-testid*='turn' i]", "[data-testid*='response' i]", "[data-testid*='prompt' i]", "article[data-role]", "[class*='chatMessage']", "[class*='agentMessage']", "[class*='message-row']",
  ].join(",");
  function roleOf(el, fallbackAlign) {
    if (!el) return "";
    if (el.dataset && el.dataset.zsRoleFallback) return el.dataset.zsRoleFallback;
    const raw = [el.getAttribute("data-message-author-role"), el.getAttribute("data-role"),
      el.getAttribute("data-testid"), el.getAttribute("data-author"), el.getAttribute("aria-label"), el.className]
      .filter(Boolean).join(" ").toLowerCase();
    if (/assistant|notion-ai|ai-response|agent-message|response|bot/.test(raw)) return "assistant";
    if (/\buser\b|human|prompt/.test(raw)) return "user";
    // No textual role: fall back to the alignment signal, which is reliable on
    // Notion's Agent transcript even when every class is hashed.
    if (fallbackAlign) {
      if (fallbackAlign === "flex-end" || fallbackAlign === "end") return "user";
      if (fallbackAlign === "flex-start" || fallbackAlign === "start") return "assistant";
    }
    return "";
  }
  let _itemsMode = "none";
  function allItems() {
    if (!surfaceOk()) { _itemsMode = "none"; return []; }
    // Route-keyed outputs first. /chat threads overwhelmingly use the agent
    // anchor; older builds fall back to the block-editor structure.
    if (isAiThread()) {
      const rows = agentMessageRows();
      if (rows.length) {
        _itemsMode = "rows";
        const seen = new Set();
        return rows.map((r) => {
          if (!r.dataset.zsRoleAlign) r.dataset.zsRoleAlign = rowAlign(r);
          return r;
        }).filter((r) => {
          if (seen.has(r)) return false; seen.add(r); return true;
        });
      }
      const blocks = blockAssistantRoots();
      if (blocks.length) { _itemsMode = "block"; return blocks; }
      _itemsMode = "none";
      return [];
    }
    // /ai landing: a brand-new chat has no turns yet.
    if (isAiLanding()) {
      _itemsMode = "landing";
      const root = composerFrame() && composerFrame().parentElement;
      if (root) {
        const raw = [...root.querySelectorAll(turnSelector)].filter(visible);
        if (raw.length) { _itemsMode = "landing-dom"; return raw; }
      }
      return [];
    }
    // Generic AI surface: an embedded/hosted Agent panel, a rewritten route, or
    // an explicit open. Not a /chat thread and not an /ai landing, so neither of
    // the branches above applies - but the transcript is still real. Use the
    // semantic turn selector (the detection Multi-Script shipped before the
    // PlazCode merge) so these surfaces keep working instead of reporting an
    // empty conversation. Prefer anchored rows when they exist, then the block
    // structure, then plain semantic turns.
    const anchored = agentMessageRows();
    if (anchored.length) {
      _itemsMode = "rows";
      const seen = new Set();
      return anchored.map((r) => {
        if (!r.dataset.zsRoleAlign) r.dataset.zsRoleAlign = rowAlign(r);
        return r;
      }).filter((r) => { if (seen.has(r)) return false; seen.add(r); return true; });
    }
    const blocks = blockAssistantRoots();
    if (blocks.length) { _itemsMode = "block"; return blocks; }
    const root = chatRoot();
    let raw = [];
    try { raw = [...root.querySelectorAll(turnSelector)]; } catch {}
    if (!raw.length && root !== document) { try { raw = [...document.querySelectorAll(turnSelector)]; } catch {} }
    const turns = raw.filter((el) => visible(el) && !(el.closest && el.closest("#zs-root")) &&
      !(el.parentElement && el.parentElement.closest(turnSelector)));
    if (turns.length) {
      _itemsMode = "turns";
      return turns.map((r) => {
        if (!r.dataset.zsRoleAlign) r.dataset.zsRoleAlign = rowAlign(r);
        return r;
      });
    }
    _itemsMode = "none";
    return [];
  }
  const roleCacheAlign = (el) => (el && el.dataset && el.dataset.zsRoleAlign) || "";
  const isUserItem = (x) => roleOf(x, roleCacheAlign(x)) === "user";
  const isAssistantItem = (x) => roleOf(x, roleCacheAlign(x)) === "assistant";
  const assistantItems = () => allItems().filter(isAssistantItem);
  const assistantCount = () => assistantItems().length;
  const userCount = () => allItems().filter(isUserItem).length;
  const lastAssistant = () => assistantItems().slice(-1)[0] || null;
  const itemKey = (x) => (x && (x.getAttribute("data-agent-service-scroll-anchor") || x.getAttribute("data-message-id") || x.getAttribute("data-block-id") || x.id)) || null;
  const lastAssistantId = () => itemKey(lastAssistant());

  function chatRoot() {
    const f = composerFrame();
    if (f && f.parentElement) return f.parentElement;
    const e = getEditor();
    if (e) {
      let cur = e.parentElement;
      for (let i = 0; cur && cur !== document.documentElement && i < 8; cur = cur.parentElement, i++) {
        if (cur.tagName === "MAIN" || cur.getAttribute("role") === "main") return cur;
      }
      return e.closest("main") || document;
    }
    return document;
  }

  const BLOCK = /^(P|DIV|PRE|LI|UL|OL|BLOCKQUOTE|H[1-6]|TABLE|TR|SECTION|ARTICLE)$/;
  function textWithout(root, excludeSel) {
    let out = "";
    const br = () => { if (out && !out.endsWith("\n")) out += "\n"; };
    const walk = (n) => {
      if (n.nodeType === 3) { out += n.nodeValue || ""; return; }
      if (n.nodeType !== 1 || (excludeSel && n.matches && n.matches(excludeSel))) return;
      if (n.tagName === "BR") { out += "\n"; return; }
      const block = BLOCK.test(n.tagName); if (block) br();
      for (const c of n.childNodes) walk(c);
      if (block) br();
    };
    if (root) walk(root);
    return out.replace(/\n{3,}/g, "\n\n").trim();
  }
  const itemText = (x) => textWithout(x, ".zs-chip");
  const classifyText = (x, excludeSel) => textWithout(x, excludeSel);
  const streamLen = (x) => itemText(x === undefined ? lastAssistant() : x).length;
  function readAssistant() {
    const item = lastAssistant();
    return item ? { present: true, reply: itemText(item), thinking: "", item } :
      { present: false, reply: "", thinking: "", item: null };
  }
  const snapshot = () => { const x = lastAssistant(); return { th: 0, rp: x ? streamLen(x) : 0 }; };

  let locked = false;
  function setInputLock(on) {
    locked = on; const e = getEditor(); if (!e) return;
    if (on) { e.setAttribute("aria-disabled", "true"); e.dataset.zsLocked = "1"; e.style.pointerEvents = "none"; }
    else { e.removeAttribute("aria-disabled"); delete e.dataset.zsLocked; e.style.pointerEvents = ""; }
  }
  function setText(e, text) {
    e.focus();
    if (isTextControl(e)) {
      const proto = e.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
      setter.call(e, text); e.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      const sel = window.getSelection(), range = document.createRange();
      range.selectNodeContents(e); sel.removeAllRanges(); sel.addRange(range);
      e.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, cancelable: true, inputType: "insertText", data: text }));
      const inserted = document.execCommand("insertText", false, text);
      if (!inserted || (e.textContent || "") !== text) e.textContent = text;
      e.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    }
  }
  // ── Sending ─────────────────────────────────────────────────────────────
  // 6.25.1 rewrite. The old path had two ways to LIE about a send:
  //   1. it typed with a synthetic `beforeinput` + execCommand + a `textContent`
  //      fallback. Notion's block editor can consume the synthetic event itself
  //      (double insert), and the textContent fallback changes the DOM behind the
  //      editor's back, so Notion's state stays "empty" and its Send button stays
  //      disabled forever;
  //   2. "composer is empty" was treated as "message accepted" - but a composer the
  //      text never reached is also empty, so a dead send reported success and the
  //      core then waited for a reply that could not exist.
  // Now: insert with several strategies, VERIFY the text is really in the editor and
  // that Notion registered it (Send enabled), and only count "composer emptied" as
  // acceptance when we had verified text in it first.
  const squash = (t) => String(t || "").replace(/\s+/g, "");
  function textLanded(e, text) {
    const got = squash(edText(e)).length, want = squash(text).length;
    if (!want) return true;
    return got >= want * 0.98 && got <= want * 1.05 + 8;
  }
  function selectAllIn(e) {
    try {
      const sel = window.getSelection(), range = document.createRange();
      range.selectNodeContents(e); sel.removeAllRanges(); sel.addRange(range);
    } catch {}
  }
  function clearEditor(e) {
    if (isTextControl(e)) { setNativeValue(e, ""); return; }
    e.focus(); selectAllIn(e);
    try { document.execCommand("delete", false); } catch {}
    if ((e.textContent || "").length) {
      try { document.execCommand("selectAll", false); document.execCommand("delete", false); } catch {}
    }
  }
  function setNativeValue(e, text) {
    const proto = e.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(e, text);
    e.dispatchEvent(new Event("input", { bubbles: true }));
  }
  // Ordered from "most like a real user" to "last resort".
  const INSERTERS = [
    { name: "insertText", run(e, text) {
      e.focus(); selectAllIn(e);
      document.execCommand("insertText", false, text);
    } },
    { name: "paste", run(e, text) {
      e.focus(); selectAllIn(e);
      const dt = new DataTransfer(); dt.setData("text/plain", text);
      e.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    } },
    { name: "beforeinput", run(e, text) {
      e.focus(); selectAllIn(e);
      const ev = new InputEvent("beforeinput", { bubbles: true, cancelable: true, inputType: "insertFromPaste", data: text });
      e.dispatchEvent(ev);
      if (!textLanded(e, text)) document.execCommand("insertText", false, text);
      e.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    } },
    { name: "textContent", run(e, text) {
      e.focus(); e.textContent = text;
      e.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    } },
  ];
  // Does a Send control exist at all (enabled or not)? Some Notion builds only
  // commit with Enter, so a missing button must not block the send.
  function sendControlPresent() {
    const frame = composerFrame();
    if (!frame) return false;
    const cs = controlsIn(frame);
    return !!(exactSendControl(frame, cs) || cs.find(sendControlLike));
  }
  // True once Notion's own state has taken the text (Send turned on).
  const registered = () => !!sendButton() || !sendControlPresent();
  async function waitRegistered(ms) {
    const end = Date.now() + ms;
    while (Date.now() < end) { if (registered()) return true; await sleep(60); }
    return registered();
  }
  let lastSendReport = null;
  async function fillComposer(e, text) {
    const report = { len: text.length, tag: e.tagName, tries: [] };
    lastSendReport = report;
    if (isTextControl(e)) {
      setNativeValue(e, text); await sleep(80);
      const ok = textLanded(e, text) && await waitRegistered(900);
      report.tries.push({ s: "native", landed: textLanded(e, text), send: !!sendButton() });
      return ok;
    }
    let fallback = null; // first strategy whose text landed even though Send stayed off
    const last = INSERTERS[INSERTERS.length - 1];
    for (const ins of INSERTERS) {
      if (ins === last) continue; // textContent is only for "nothing else put text in"
      clearEditor(e);
      let threw = "";
      try { ins.run(e, text); } catch (x) { threw = String((x && x.message) || x).slice(0, 60); }
      await sleep(120);
      const landed = textLanded(e, text);
      const reg = landed ? await waitRegistered(1100) : false;
      report.tries.push({ s: ins.name, landed, got: squash(edText(e)).length, send: !!sendButton(), reg, ...(threw ? { threw } : {}) });
      diag("notion.fill", report.tries[report.tries.length - 1]);
      if (reg) return true;
      if (landed && !fallback) fallback = ins;
    }
    if (fallback) {
      // Text can land without Send turning on when OUR send-button detection is
      // off, so keep the cleanest insertion and let Enter / click decide.
      clearEditor(e);
      try { fallback.run(e, text); } catch {}
      await sleep(120);
      report.tries.push({ s: "restore:" + fallback.name, landed: textLanded(e, text) });
      return textLanded(e, text);
    }
    clearEditor(e);
    try { last.run(e, text); } catch {}
    await sleep(120);
    report.tries.push({ s: last.name, landed: textLanded(e, text) });
    return textLanded(e, text);
  }
  function sendDiagnostics() {
    const e = findEditorRaw();
    let doc = {};
    try { doc = { focus: document.hasFocus(), hidden: document.hidden, active: document.activeElement === e }; } catch {}
    return {
      v: "6.25.1", route: routeKey(), surface: surfaceOk(), editor: !!e,
      tag: e ? e.tagName : null, edLen: e ? squash(edText(e)).length : 0,
      sendCtl: sendControlPresent(), sendOn: !!sendButton(), ...doc,
      fill: lastSendReport && lastSendReport.tries,
    };
  }
  async function typeAndSend(text) {
    const e = getEditor(); if (!e) throw new Error("Notion AI input box not found");
    const relock = locked; if (relock) { e.removeAttribute("aria-disabled"); e.style.pointerEvents = ""; }
    const _lim = (typeof ZS !== "undefined" && ZS.limits) ? ZS.limits.sendOverride(String(text)) : null;
    const body = _lim !== null ? _lim : String(text).slice(0, 90000);
    try {
      const filled = await fillComposer(e, body);
      // Text is not in the composer: stop here. Pressing Send on an empty composer
      // does nothing, and the empty box must not be mistaken for a sent message.
      if (!textLanded(e, body)) {
        try { clearEditor(e); } catch {}
        throw new Error("Notion AI composer would not take the text (" + JSON.stringify((lastSendReport && lastSendReport.tries || []).map((t) => t.s + ":" + (t.landed ? "in" : "out"))) + ").");
      }
      if (!filled) diag("notion.fill.unregistered", { send: !!sendButton() });
      // Acceptance = the composer we verified as non-empty is now empty (or was
      // swapped out by Notion for the thread view).
      const accepted = async (ms) => {
        const deadline = Date.now() + ms;
        while (Date.now() < deadline) {
          if (getEditor() !== e || !e.isConnected) return true;
          if (!squash(editorText(e))) return true;
          await sleep(100);
        }
        return false;
      };
      const key = (t, type) => e.dispatchEvent(new KeyboardEvent(type, {
        key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true, composed: true,
      }));
      // A click may reach Notion before its editor clears. Never submit the same
      // turn again through Enter/requestSubmit when that outcome is uncertain.
      const b = sendButton();
      if (b && !b.disabled && b.getAttribute("aria-disabled") !== "true") b.click();
      else { e.focus(); for (const t of ["keydown", "keypress", "keyup"]) key(e, t); }
      if (await accepted(3500)) return;
      const error = new Error("Notion send acknowledgement is unconfirmed. Check this conversation before retrying; Multi-Script will not replay the message. " + JSON.stringify(sendDiagnostics()));
      error.retryable = false; error.sendState = "unconfirmed";
      throw error;
    } finally {
      if (relock) setInputLock(true);
    }
  }
  // Notion re-renders the streamed reply subtree, so a read can legitimately
  // come back mid-render. The core consults this before firing a "malformed
  // command" verdict, so a half-rendered command is waited out instead of nagged.
  let _unsettleItem = null, _unsettleLen = -1, _unsettleAt = 0;
  function replyUnsettled(item) {
    const len = item ? streamLen(item) : 0;
    const now = Date.now();
    if (item !== _unsettleItem || len !== _unsettleLen) {
      _unsettleItem = item; _unsettleLen = len; _unsettleAt = now;
      return true;
    }
    return now - _unsettleAt < 1200;
  }
  let maxLen = 0, grewAt = 0, streamItem = null;
  function sample() {
    const x = lastAssistant(), n = streamLen(x), now = Date.now();
    if (x !== streamItem || n < maxLen - 300) { streamItem = x; maxLen = n; grewAt = now; }
    else if (n > maxLen) { maxLen = n; grewAt = now; }
  }
  function isGenerating() { sample(); return !!stopButton() || runningPlaceholder() || (maxLen > 0 && Date.now() - grewAt < timings.GEN_IDLE_MS); }
  const isBusyNow = isGenerating, isHardGenerating = isGenerating;
  const turnHalted = () => false;
  function stopGeneration() { const b = stopButton(); if (b) b.click(); }

  const chatIsEmpty = () => allItems().length === 0;
  const isFreshChat = () => chatIsEmpty() && !!getEditor();
  const coverTarget = composerFrame;
  // Anchor to the composer card itself. The old in-flow sibling inherited
  // Notion's wider horizontal action rail, so width:100% extended beyond the
  // visible Ask-anything box. Anchored mode remeasures the composer every frame
  // and follows its exact width through resizes and sidebar/layout changes.
  const barAnchor = composerFrame;
  function enforceComposer() { return { ready: !!getEditor() }; }
  async function ensureComposerReady(reason) {
    const profile = getAutoRoutingProfile();
    diag("mode_ready", { reason, provider: "notion", autoRoutingProfile: profile, routing: "prompt-only" });
    return { ready: !!getEditor(), profile, routing: { method: "prompt-only", directPickerInteraction: false } };
  }
  // Notion reuses the same URL for multiple Agent chats, so track the visible
  // non-empty -> empty transition to give every New chat a distinct bootstrap
  // identity even when the pathname does not change.
  const notionPageToken = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
  let notionChatEpoch = 0, notionHadTurns = false;
  function conversationKey() {
    const empty = chatIsEmpty();
    if (!empty) notionHadTurns = true;
    else if (notionHadTurns) { notionChatEpoch += 1; notionHadTurns = false; }
    return `${routeKey()}|${notionPageToken}|${notionChatEpoch}`;
  }
  async function openAIChat() {
    // Already on the AI surface AND the composer is resolvable: nothing to do.
    // NB the old form was `if (isAiSurface()) return !!getEditor();` - which
    // returned false the moment the route guard passed but the scorer could not
    // qualify the editor, so an on-surface-but-unresolved composer (shadow DOM,
    // mid-mount, model picker still loading) got NO recovery click at all. The
    // route guard decides *where* we may look; it must not decide that we stop.
    if (getEditor()) return true;
    // The old notion.so root now commonly opens workspace settings/Connectors.
    // On a real Notion origin, an explicit "Open AI chat" action should go to
    // the current dedicated chat route instead of hunting unrelated AI buttons.
    const host = String(location.hostname || "").toLowerCase();
    if (!isAiSurface() && (host === "app.notion.com" || /(^|\.)notion\.(?:ai|so|com)$/.test(host))) {
      try { location.assign("https://app.notion.com/chat"); return true; } catch {}
    }
    // The user explicitly asked for Notion AI: arm the guard override so a
    // surface that simply does not live at /ai returns a real answer instead of
    // a silent false. Cleared on the next route change (see resetEditorCache-
    // ForRoute) so it can never leak into a normal document page.
    _explicitOpen = true;
    const onSurface = true;
    // Ask the site to open the Agent, then wait for the composer to mount.
    const controls = queryAllDeep("button,a,[role='button'],[role='link']").filter(visible);
    const b = controls.find((x) => /notion ai|ask ai|open ai|chat with ai/i.test(`${ariaOf(x)} ${x.title || ""} ${txtOf(x)}`));
    if (b) {
      b.click();
      const deadline = Date.now() + 5000;
      while (Date.now() < deadline) { if (getEditor()) return true; await sleep(100); }
    } else if (onSurface) {
      // No launcher to click, but we are already on the surface - give a
      // late-mounting composer a chance to appear before declaring failure.
      const deadline = Date.now() + 2500;
      while (Date.now() < deadline) { if (getEditor()) return true; await sleep(100); }
    }
    return !!getEditor();
  }
  async function openNewChat() {
    const b = queryAllDeep("button,a").filter(visible).find((x) =>
      /new chat|new conversation|start over/i.test(`${ariaOf(x)} ${txtOf(x)}`));
    if (!b) return false; b.click(); await sleep(500); return true;
  }

  function scanError() {
    if (!surfaceOk()) return "Notion AI chat is not open. Open https://app.notion.com/chat and try again.";
    const root = chatRoot();
    for (const el of root.querySelectorAll("[role='alert'],[data-testid*='error' i]")) {
      const t = (el.innerText || "").trim(); if (visible(el) && t && t.length < 500) return t;
    }
    return getEditor() ? null : "Notion Agent composer not detected. Open https://app.notion.com/chat, click the “Ask anything” composer, and reload.";
  }
  const isTooLongMsg = (t) => /too long|context limit|maximum length/i.test(t || "");
  const isBusyMsg = (t) => /try again|temporarily unavailable|rate limit|too many requests/i.test(t || "");
  const findContinueBtn = () => [...document.querySelectorAll("button")].filter(visible).find((b) => /continue generating|continue/i.test(txtOf(b))) || null;
  function clickContinueBtn() { const b = findContinueBtn(); if (!b) return false; b.click(); return true; }

  function installSendHooks(h) {
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
      const ed = getEditor(); if (!ed || !(ed === e.target || ed.contains(e.target))) return;
      if (!editorText().trim() || h.isBlocked()) return;
      if (!h.isStarted()) { h.onBlockedAttempt(); return; }
      h.onUserMessage(assistantCount());
    }, true);
    document.addEventListener("click", (e) => {
      const b = e.target && e.target.closest && e.target.closest(CONTROL_SEL); if (!b) return;
      if (b === stopButton()) { h.onNativeStop(); return; }
      if (b !== sendButton() || h.isBlocked() || !editorText().trim()) return;
      if (!h.isStarted()) { h.onBlockedAttempt(); return; }
      h.onUserMessage(assistantCount());
    }, true);
  }

  function selfTest() {
    const editor = getEditor(), send = sendButton(), stop = stopButton(), root = chatRoot();
    const cands = editorCandidates();
    const result = {
      provider: "notion", url: location.href,
      route: routeKey(), surface: surfaceOk(), landing: isAiLanding(), thread: isAiThread(),
      routeGuardMatched: isAiSurface(), explicitOpen: _explicitOpen,
      evidence: hasAiSurfaceEvidence(),
      cleanLanding: isCleanAiLanding(),
      editorFound: !!editor,
      editorKind: editor ? `${editor.tagName.toLowerCase()}${editor.getAttribute("contenteditable") === "true" ? ":contenteditable" : ""}` : null,
      chatRoot: root === document ? "document" : (root.getAttribute("data-testid") || root.getAttribute("role") || root.tagName.toLowerCase()),
      sendButtonFound: !!send, stopButtonFound: !!stop,
      agentRows: rawAgentRows().length, assistantBlocks: isAiThread() ? blockAssistantRoots().length : 0,
      candidateCount: cands.length,
      userTurns: userCount(), assistantTurns: assistantCount(),
      activeAutoProfile: getAutoRoutingProfile(), profilePromptReady: !!getStartupProfilePrompt(), routing: "prompt-only",
    };
    // "Ready" = we have a surface, a resolved composer, and one of: a send
    // control, any editable contenteditable (Notion ships plaintext-only, not
    // just true), or a real text control. Requiring the literal "true" made a
    // perfectly usable plaintext-only composer report not-ready.
    const editableOk = !!editor && (
      (editor.getAttribute && editor.getAttribute("contenteditable") !== null &&
       editor.getAttribute("contenteditable") !== "false") || editor.isContentEditable ||
      isTextControl(editor));
    result.ready = result.surface && result.editorFound && (result.sendButtonFound || editableOk);
    result.recommendation = !result.surface
      ? "Not on a Notion AI route. Open https://app.notion.com/chat and reload."
      : result.ready ? "Provider controls detected."
      : "Open the Notion Agent, click its composer, then reload the page and run the self-test again.";
    return result;
  }

  const SHAPE = /"(?:command|tool)"\s*:\s*"|###\s*lua|###mcp_tool###|<\/?\s*[|｜].*dsml/i;
  function findToolBlockSpot(item) {
    if (!item) return null; let spot = null;
    for (const el of item.querySelectorAll("pre,code,p")) {
      if (el.closest(".zs-chip") || !SHAPE.test(el.textContent || "")) continue;
      el.classList.add("zs-tool-hide"); spot ||= { parent: el.parentElement, ref: el };
    }
    return spot;
  }

  // ── Model picker probe (OPT-IN: runs only when the user presses a button) ─
  // Sending a prompt NEVER touches the picker (see routingProfileDiagnostics:
  // directPickerInteraction stays false). These helpers exist so the user can ask
  // "which models does this workspace actually have in agent mode?" and "switch
  // to Opus 5.5 / High", and see an honest verified/not-verified answer. Notion's
  // markup is hashed and A/B-tested, so everything is matched on roles, ARIA and
  // visible text, never on class names.
  const MODEL_WORD = /\b(auto|claude|opus|sonnet|haiku|gpt|gemini|kimi|deepseek|o[134])\b/i;
  const ROW_SEL = '[role="menuitem"],[role="menuitemradio"],[role="menuitemcheckbox"],[role="option"]';
  const MENU_SEL = '[role="menu"],[role="listbox"],[data-radix-popper-content-wrapper],[data-radix-menu-content]';
  const usageLib = () => (typeof ZSNotionUsage !== "undefined" ? ZSNotionUsage : null);
  const menuRoots = () => queryAllDeep(MENU_SEL).filter(visible);
  const waitFor = async (fn, ms, step = 60) => {
    const end = Date.now() + ms;
    for (;;) { const v = fn(); if (v) return v; if (Date.now() > end) return null; await sleep(step); }
  };
  function pointerSequence(el) {
    for (const t of ["pointerdown", "mousedown", "pointerup", "mouseup"]) {
      try {
        const Ev = t.startsWith("pointer") && typeof PointerEvent === "function" ? PointerEvent : MouseEvent;
        el.dispatchEvent(new Ev(t, { bubbles: true, cancelable: true, composed: true, view: window, button: 0, pointerType: "mouse", isPrimary: true }));
      } catch {}
    }
  }
  function modelPickerButton() {
    if (!surfaceOk()) return null;
    const frame = composerFrame() || document;
    const score = (b) => {
      const a = ariaOf(b), t = txtOf(b); let n = 0;
      if (/model/i.test(a)) n += 5;
      if (t && t.length <= 40 && MODEL_WORD.test(t)) n += 4;
      if (b.getAttribute && b.getAttribute("aria-haspopup")) n += 2;
      return n;
    };
    const best = controlsIn(frame).filter((b) => visible(b) && !sendControlLike(b) && !stopControlLike(b))
      .map((b) => [score(b), b]).filter((x) => x[0] >= 4).sort((a, b) => b[0] - a[0])[0];
    return best ? best[1] : null;
  }
  function currentModelLabel() { const b = modelPickerButton(); return b ? (txtOf(b) || ariaOf(b)).slice(0, 60) : ""; }
  async function openModelMenu() {
    const btn = modelPickerButton();
    if (!btn) return { error: "Model picker not found. Open a Notion AI chat with its composer visible, then try again." };
    const before = new Set(menuRoots());
    const find = () => menuRoots().find((m) => !before.has(m)) || null;
    btn.click();
    let menu = await waitFor(find, 700);
    // Some menus only open on pointerdown. Try that ONLY if click did nothing, so
    // a trigger that listens to both can never open and instantly re-close.
    if (!menu) { pointerSequence(btn); menu = await waitFor(find, 900); }
    return menu ? { btn, menu } : { btn, error: "The model menu did not open." };
  }
  async function closeModelMenu(h) {
    const esc = () => new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true, cancelable: true });
    const open = () => !!h && [h.menu].concat(h.extra || []).some((m) => m && m.isConnected && visible(m));
    for (let i = 0; i < 2 && open(); i++) { (document.activeElement || document.body).dispatchEvent(esc()); await sleep(140); }
    if (open() && h.btn) { h.btn.click(); await sleep(160); }
    return !open();
  }
  function pickerRows(roots) {
    const seen = new Set(), out = [];
    for (const root of roots) for (const el of root.querySelectorAll(ROW_SEL)) {
      if (seen.has(el) || !visible(el)) continue; seen.add(el);
      const text = ((el.innerText || el.textContent || "") + "").replace(/\s+/g, " ").trim();
      if (!text || text.length > 160) continue;
      const at = (n) => el.getAttribute(n);
      out.push({ el, text, selected: at("aria-checked") === "true" || at("aria-selected") === "true" || at("data-state") === "checked",
        disabled: at("aria-disabled") === "true" || el.hasAttribute("disabled") || at("data-disabled") != null });
    }
    return out;
  }
  const isEffortRow = (r) => {
    const U = usageLib(); if (!U) return false;
    return r.text.length <= 18 && !!U.normEffort(r.text) && U.classify(r.text).id === "other";
  };
  async function expandMoreModels(h, rows) {
    const more = rows.find((r) => /^(show )?more( models?)?$|^all models?$/i.test(r.text));
    if (!more) return rows;
    more.el.click(); await sleep(380);
    const roots = [h.menu, ...menuRoots()].filter((m, i, a) => m && m.isConnected && a.indexOf(m) === i);
    h.extra = roots; // the menu may be re-rendered into a NEW node; close whichever is open
    const merged = pickerRows(roots);
    return merged.length ? merged : rows;
  }
  async function detectModels() {
    const U = usageLib();
    if (!U) return { ok: false, error: "Usage module not loaded." };
    const h = await openModelMenu();
    if (h.error) return { ok: false, error: h.error };
    try {
      const rows = await expandMoreModels(h, pickerRows([h.menu]));
      const effortRows = rows.filter(isEffortRow), modelRows = rows.filter((r) => !isEffortRow(r) && !/^(show )?more( models?)?$/i.test(r.text));
      const efforts = effortRows.map((r) => U.normEffort(r.text)).filter((e, i, a) => e && a.indexOf(e) === i);
      const models = U.parseModels(modelRows).map((m) => ({ ...m, efforts: m.enabled && U.classify(m.name).id !== "auto" ? efforts : [] }));
      const cur = effortRows.find((r) => r.selected);
      return { ok: models.length > 0, models, efforts, selectedEffort: cur ? U.normEffort(cur.text) : "", label: currentModelLabel(),
        error: models.length ? "" : "The menu opened but no model rows were recognised." };
    } finally { await closeModelMenu(h); }
  }
  async function selectModel({ model = "", effort = "" } = {}) {
    const U = usageLib();
    if (!U) return { ok: false, error: "Usage module not loaded." };
    const out = { ok: false, requested: { model, effort }, picked: "", effort: "", label: "", verified: false, error: "" };
    if (model) {
      const h = await openModelMenu();
      if (h.error) return { ...out, error: h.error };
      try {
        const rows = await expandMoreModels(h, pickerRows([h.menu]));
        const modelRows = rows.filter((r) => !isEffortRow(r));
        const found = U.findModel(U.parseModels(modelRows), model);
        const row = found && modelRows.find((r) => U.cleanName(r.text) === found.name && !r.disabled);
        if (!row) { out.error = `${model} is not enabled in this workspace's model picker (or the menu has no row for it).`; return out; }
        row.el.click(); out.picked = found.name; await sleep(320);
        // Radix-style rows act on pointer events rather than click. Retry that way
        // ONLY when the first click visibly did nothing (label unchanged, menu open).
        const shows = () => !!U.findModel([{ name: currentModelLabel(), enabled: true }], found.name);
        if (!shows() && [h.menu].concat(h.extra || []).some((m) => m && m.isConnected && visible(m))) { pointerSequence(row.el); await sleep(320); }
      } finally { await closeModelMenu(h); }
    }
    if (effort) {
      const h = await openModelMenu();
      if (!h.error) {
        try {
          const rows = pickerRows([h.menu]).filter(isEffortRow);
          const want = U.pickEffort(rows.map((r) => U.normEffort(r.text)), effort);
          const row = rows.find((r) => U.normEffort(r.text) === want);
          if (row) {
            if (!row.selected) {
              row.el.click(); await sleep(260);
              if (row.el.isConnected && row.el.getAttribute("aria-checked") === "false") { pointerSequence(row.el); await sleep(260); }
            }
            out.effort = want;
          }
          else out.error = "Notion's picker shows no effort levels for this model.";
        } finally { await closeModelMenu(h); }
      } else out.error = h.error;
    }
    out.label = currentModelLabel();
    const want = model ? U.findModel([{ name: out.label, enabled: true }], model) : true;
    out.verified = !!want && (!model || !!out.picked);
    out.ok = (!model || !!out.picked) && (!effort || !!out.effort);
    return out;
  }
  // Credits / trial days Notion happens to show on the page (banner, sidebar,
  // settings dialog). Bounded: a few hundred short nodes, never the whole page.
  function scanPageUsage() {
    const U = usageLib(); if (!U) return {};
    const texts = [];
    let budget = 600;
    for (const el of document.querySelectorAll('[role="button"],button,a,[role="status"],[role="dialog"] *,[data-testid*="trial" i],[data-testid*="credit" i],[class*="trial" i],[class*="credit" i]')) {
      if (budget-- <= 0) break;
      const t = (el.textContent || "").trim();
      if (t.length > 3 && t.length < 220 && /trial|credit|days? (left|remaining)/i.test(t)) texts.push(t);
    }
    return U.scanText(texts.join(" · "));
  }

  const AUTO_ROUTING_PROFILES = {
    opus55: { label: "Claude Opus 5.5", model: "Claude Opus 5.5", availability: "awaiting-notion", description: "Saved preference for Claude Opus 5.5. Choose the actual model in Notion; text cannot change its backend." },
    opus: { label: "Claude Opus 5", model: "Claude Opus 5", availability: "supported", description: "Saved preference for Claude Opus 5. Choose the actual model in Notion; text cannot change its backend." },
    gpt: { label: "GPT-5.6 Sol", model: "GPT-5.6 Sol", availability: "supported", description: "Saved preference for GPT-5.6 Sol. Choose the actual model in Notion; text cannot change its backend." },
    kimi: { label: "Kimi K3", model: "Kimi K3", availability: "supported", description: "Saved preference for Kimi K3. Choose the actual model in Notion; text cannot change its backend." },
    luna: { label: "GPT-6 Luna", model: "GPT-6 Luna", availability: "awaiting-notion", description: "Saved preference for GPT-6 Luna. Choose the actual model in Notion; text cannot change its backend." },
  };
  function getAutoRoutingProfile() { return storageGet("zs.notion.autoRoutingProfile") || ""; }
  function setAutoRoutingProfile(id) {
    if (!id || !AUTO_ROUTING_PROFILES[id]) storageRemove("zs.notion.autoRoutingProfile");
    else storageSet("zs.notion.autoRoutingProfile", id);
    // Auto-routing and a direct picker preference are mutually exclusive. A stale
    // direct preference otherwise reopens an unavailable picker before every send.
    storageRemove("zs.notion.modelPreference");
    return getAutoRoutingProfile();
  }
  function getStartupProfilePrompt() {
    const x = AUTO_ROUTING_PROFILES[getAutoRoutingProfile()];
    if (!x) return "";
    return `[NOTION AUTO MODEL REQUEST — PROCESS BEFORE THE NEXT BLOCK]
Saved preference metadata: ${x.model}.
Notion's actual model selector and eligible workspace plan control the backend. Multi-Script cannot select, pin or change the model by sending this text. Do not route yourself or impersonate the preference. Use the actual selected model, keep the real Multi-Script JSON transport and continue the task. Never claim a model was selected without provider confirmation.
This metadata is not a separate user task. Apply the shared Multi-Script instructions below. Local MCP commands run in the connected bridge when advertised; Notion-native workspace connectors are a separate system.`;
  }
  function autoRoutingProfiles() {
    return Object.entries(AUTO_ROUTING_PROFILES).map(([id, x]) => ({ id, label: x.label, description: x.description, model: x.model, availability: x.availability || "supported" }));
  }
  function routingProfileDiagnostics() {
    const id = getAutoRoutingProfile(), x = AUTO_ROUTING_PROFILES[id];
    const prompt = x ? getStartupProfilePrompt() : "";
    return { selected: id || "standard", label: x ? x.label : "Standard Auto", requestedModel: x ? x.model : null, promptReady: !!prompt, promptCharacters: prompt.length, strategy: "saved model preference metadata; actual Notion selector controls routing", directPickerInteraction: false, placement: "immediately after the Multi-Script session marker", includesSharedSystem: true, availability: x ? (x.availability || "supported") : "auto", fallback: x ? "Standard Auto without model imitation" : null, applies: "once at the start of each new chat" };
  }

  const PROMPT_EXTRA = `- You are running inside Notion AI through a browser extension. For project actions, emit Multi-Script JSON commands as plain fenced-code text; do not use Notion's native connectors or page-editing actions as a substitute, because those do not reach the local game-engine MCP servers.\n- Route by intent: use Multi-Script commands for local game-engine/project actions; use Notion's native page/database/search capabilities for explicit workspace tasks; for hybrid tasks, read the Notion brief first and then execute engine changes through Multi-Script. Never substitute a Notion page edit for a requested engine action.
- Treat Notion pages and workspace text as reference material unless the user explicitly asks you to edit that Notion content. Keep workspace summaries concise, preserve citations/links, and never expose private workspace context in broader outputs without explicit approval.
- A saved model preference may appear above. It does not change the backend. Use the actual selected model and the advertised Multi-Script JSON tools; do not discuss identity because of this metadata.
- COMMON NOTION EXECUTION RULES: preserve exact workspace and repository context; inspect before editing; use only discovered tool schemas; keep Multi-Script skills and connected tools available; follow the selected prompt-skills, creative-surface, usage, and validation settings; verify meaningful changes with concrete evidence; never claim a model identity that Notion does not expose.`;

  return {
    id: "notion", displayName: "Notion AI", timings, supportsVision: false, sendCharBudget: 90000,
    // Notion's React Agent surface replaces its composer wrappers during layout
    // and streaming. Use safe sibling flow mounts or reserve-free geometry.
    persistentBarWhenNoEditor: true, noEditorMessage: "Notion AI chat is not open yet.",
    reliableCounts: false, chipAtItemLevel: true, coverMaxH: 280,
    // Route gating is a first-class capability so the core can report honestly.
    isAiSurface, isAiLanding, isAiThread, isCleanAiLanding, routeKey,
    // Notion streams through a very mutation-heavy block editor; bound the work.
    sweepThrottleMs: 500, periodicSweepMs: 3000,
    init({ diag: d } = {}) {
      if (d) diag = d;
      // Do NOT arm the route-guard override here. The core initializes the
      // provider on every notion.so/notion.com page, so setting it here disabled
      // the guard everywhere and let the adapter resolve an unrelated container
      // on an ordinary workspace page (the bar then floated mid-page). Surface
      // acceptance now comes from isAiSurface(), a genuine explicit open, or
      // positive AI-composer evidence - see surfaceOk().
      try {
        document.documentElement.dataset.zsNotionVer = "6.49.9";
        new MutationObserver(() => { if (_editorCache && !_editorCache.isConnected) _editorCache = null; })
          .observe(document.documentElement, { childList: true, subtree: true });
      } catch {}
      setTimeout(() => {
        try {
          const cands = editorCandidates();
          diag("notion.providerLoaded", {
            editor: !!findEditorRaw(), items: allItems().length,
            url: routeKey(), surface: surfaceOk(), guardMatched: isAiSurface(),
            evidence: hasAiSurfaceEvidence(), landing: isAiLanding(),
            anchors: rawAgentRows().length, blockRoots: isAiThread() ? blockAssistantRoots().length : 0,
            cands: cands.length, tags: cands.map((c) => c.tagName).join(","),
          });
        } catch {}
      }, 0);
    },
    allItems, isUserItem, isAssistantItem, itemText, classifyText, assistantCount,
    userCount, lastAssistant, lastAssistantId, itemKey, readAssistant, streamLen, snapshot,
    getEditor, getEditorRaw: findEditorRaw, editorText, chatIsEmpty, isFreshChat, composerFrame, composerContainer,
    coverTarget, barMount, barAnchor, barInset, barGeometry, layoutReport, resetLayoutCache,
    setInputLock, typeAndSend, sendDiagnostics, stopGeneration, isGenerating, isBusyNow, isHardGenerating,
    replyUnsettled,
    enforceComposer, ensureComposerReady, turnHalted, findContinueBtn, clickContinueBtn,
    scanError, isTooLongMsg, isBusyMsg, openAIChat, openNewChat, conversationKey, installSendHooks,
    findToolBlockSpot, getStartupProfilePrompt, getAutoRoutingProfile,
    modelPickerButton, currentModelLabel, detectModels, selectModel, scanPageUsage,
    setAutoRoutingProfile, autoRoutingProfiles, routingProfileDiagnostics, selfTest, promptExtra: PROMPT_EXTRA,
  };
})();
