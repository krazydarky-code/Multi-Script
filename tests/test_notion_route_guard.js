// SPDX-License-Identifier: GPL-3.0-or-later
// Notion route-guard regression: an ordinary workspace page must be REFUSED.
//
// WHY THIS FILE EXISTS
// A live session showed the Multi-Script bar floating in the MIDDLE of an empty
// Notion page - no composer anywhere, just the bar anchored to some unrelated
// container, vertically centred.
//
// The cause was self-inflicted: init() unconditionally set the route-guard
// override (`_explicitOpen = true`). The core initializes the provider on EVERY
// notion.so / notion.com page, so arming the override there disabled the route
// guard on all of them. On an ordinary document page the adapter then resolved
// an unrelated element as the composer frame and anchored the bar to it.
//
// The guard's whole purpose is to stop the adapter typing into a normal Notion
// page editor. This file pins that it still does, while a genuine AI surface is
// still recognised wherever it lives.
const pw = require('./playwright-env');
const fs = require('fs'), path = require('path');
const NAME = 'Notion route guard';
pw.guard(NAME);
const root = path.resolve(__dirname, '..');
const notionSrc = fs.readFileSync(path.join(root, 'extension/providers/notion.js'), 'utf8');

// ── 1. Source invariants ────────────────────────────────────────────────────
// init() must NOT arm the override. (It is armed only by an explicit open.)
const initBody = notionSrc.slice(notionSrc.indexOf('init({ diag: d } = {})'), notionSrc.indexOf('allItems, isUserItem'));
if (/_explicitOpen\s*=\s*true/.test(initBody)) {
  throw new Error("init() must not arm the route-guard override - the core initializes the provider on every notion page");
}
if (!/surfaceOk = \(\) => isAiSurface\(\) \|\| _explicitOpen \|\| hasAiSurfaceEvidence\(\)/.test(notionSrc)) {
  throw new Error('surfaceOk() must combine the route guard, an explicit open, and AI-composer evidence');
}
if (!/function hasAiSurfaceEvidence\(\)/.test(notionSrc)) {
  throw new Error('hasAiSurfaceEvidence() must exist - it is what recognises an AI surface off the /ai route');
}
// The override must still be armed by the explicit recovery action.
const openBody = notionSrc.slice(notionSrc.indexOf('async function openAIChat()'), notionSrc.indexOf('async function openNewChat()'));
if (!/_explicitOpen\s*=\s*true/.test(openBody)) {
  throw new Error('openAIChat() must still arm the override - that is the explicit user action');
}
// Alignment invariants: the provider must expose a derived inset, and the core
// must actually apply it in anchored mode (a provider method nobody calls is the
// exact shape of the bug being fixed).
if (!/function barInset\(/.test(notionSrc)) {
  throw new Error('notion.js must expose barInset() so the bar lines up with the composer text column');
}
if (!/barAnchor, barInset/.test(notionSrc)) {
  throw new Error('barInset must be exported from the notion provider');
}
const mainSrc = fs.readFileSync(path.join(root, 'extension/core/main.js'), 'utf8');
if (!/P\.barInset && P\.barInset\(\)/.test(mainSrc)) {
  throw new Error('placeBar must consult P.barInset() in anchored mode, or the provider inset is dead code');
}
const cssSrc = fs.readFileSync(path.join(root, 'extension/overlay.css'), 'utf8');
if (!/#zs-bar\.zs-bar-anchored\.zs-prov-notion\s*\{/.test(cssSrc)) {
  throw new Error('overlay.css must carry a notion anchored-bar rule (the measured-inset fallback)');
}

(async () => {
  const browser = await pw.launch();
  if (!browser) pw.skip(NAME, 'no Chromium available');
  const code = notionSrc + '\nwindow.__P=ZSProvider;';

  // ── 2. An ORDINARY Notion page must be refused ────────────────────────────
  // A page editor (content-editable-leaf), plus the usual chrome. No AI
  // placeholder, no Agent transcript anchor. Nothing here is an AI surface.
  {
    const page = await browser.newPage();
    await page.setContent(`<!doctype html><style>body{margin:0}main{height:900px;width:700px}
      .page-editor,.notion-page-content{display:block;width:660px;height:120px}
      .page-editor{outline:none}</style>
      <aside class="sidebar"><button>Home</button><button>Search</button><button>New chat</button></aside>
      <main><div class="notion-page-content">
        <div class="page-editor" contenteditable="true" role="textbox" data-block-id="b1">ordinary page text</div>
        <div class="page-editor" contenteditable="true" role="textbox" data-block-id="b2">second block</div>
      </div></main>
      <button id="model" aria-label="Model selector">Auto</button>`);
    await page.addScriptTag({ content: code });
    const r = await page.evaluate(() => {
      const P = window.__P;
      P.init();
      const self = P.selfTest();
      return { surface: self.surface, guardMatched: self.routeGuardMatched, evidence: self.evidence,
               editor: P.getEditor() ? P.getEditor().getAttribute('data-block-id') : null,
               frame: !!P.composerFrame(), items: P.allItems().length, ready: self.ready };
    });
    if (r.editor) throw new Error('an ordinary Notion page editor must NEVER be adopted as the AI composer: ' + JSON.stringify(r));
    if (r.surface) throw new Error('an ordinary Notion page must not report as an AI surface: ' + JSON.stringify(r));
    if (r.evidence) throw new Error('an ordinary Notion page has no AI-composer evidence: ' + JSON.stringify(r));
    if (r.frame) throw new Error('no composer frame may be resolved on an ordinary page (this is what anchored the bar mid-page): ' + JSON.stringify(r));
    if (r.ready) throw new Error('an ordinary Notion page must not report ready: ' + JSON.stringify(r));
    await page.close();
  }

  // ── 3. A genuine AI surface OFF the /ai route must still be recognised ────
  // This is the case the override existed for: an embedded/hosted Agent whose
  // URL is not literally /ai. Evidence - not the route - must carry it.
  {
    const page = await browser.newPage();
    await page.setContent(`<!doctype html><style>body{margin:0}
      .composer{display:block;width:600px;height:90px}</style>
      <div class="composer" data-testid="agent-composer">
        <div id="ed" contenteditable="true" role="textbox" data-placeholder="Do anything with AI&#8230;" aria-label="Message Notion AI"></div>
        <button id="send" type="submit" aria-label="Send message">Send</button>
      </div>`);
    await page.addScriptTag({ content: code });
    const r = await page.evaluate(() => {
      const P = window.__P;
      P.init();
      const self = P.selfTest();
      return { surface: self.surface, guardMatched: self.routeGuardMatched, evidence: self.evidence,
               editor: P.getEditor() ? P.getEditor().id : null, frame: !!P.composerFrame(), ready: self.ready };
    });
    if (r.guardMatched) throw new Error('the route guard genuinely does not match here - evidence is doing the work: ' + JSON.stringify(r));
    if (!r.evidence) throw new Error('the AI placeholder must register as AI-composer evidence: ' + JSON.stringify(r));
    if (!r.surface) throw new Error('an AI composer off the /ai route must still be accepted: ' + JSON.stringify(r));
    if (r.editor !== 'ed') throw new Error('the AI composer must be resolved: ' + JSON.stringify(r));
    if (!r.frame) throw new Error('a composer frame must be resolved on a real AI surface: ' + JSON.stringify(r));
    if (!r.ready) throw new Error('a real AI surface must report ready: ' + JSON.stringify(r));
    await page.close();
  }

  // ── 4. The Agent transcript anchor alone is enough evidence ───────────────
  {
    const page = await browser.newPage();
    await page.setContent(`<!doctype html><style>body{margin:0}
      .row{display:flex;width:600px;height:60px}.row.a{justify-content:flex-start}
      .composer{display:block;width:600px;height:90px}</style>
      <div class="transcript">
        <div class="row a" data-agent-service-scroll-anchor="msg:1">an answer</div>
      </div>
      <form class="composer"><div id="ed" contenteditable="true" role="textbox"></div>
      <button id="send" type="submit" aria-label="Send message">Send</button></form>`);
    await page.addScriptTag({ content: code });
    const r = await page.evaluate(() => {
      const P = window.__P;
      P.init();
      const self = P.selfTest();
      return { surface: self.surface, evidence: self.evidence, anchors: self.agentRows, editor: P.getEditor() ? P.getEditor().id : null };
    });
    if (!r.evidence) throw new Error('an Agent transcript anchor must register as evidence: ' + JSON.stringify(r));
    if (!r.surface) throw new Error('an Agent transcript must be accepted as an AI surface: ' + JSON.stringify(r));
    await page.close();
  }

  // ── 5. ALIGNMENT: the frame must be the composer CARD, not the page column ──
  // The "doesn't line up with the Notion chatbar" report. A rounded AI card sits
  // inside a much wider page column; docking the bar to the column put it far
  // wider than the composer, and its content against the card's rounded corner
  // while the placeholder sat further in. The frame must be the inner card and
  // barInset() must report enough inset to line the bar's content up with the
  // card's text column.
  {
    const page = await browser.newPage();
    await page.setContent(`<!doctype html><style>body{margin:0}
      .page-column{display:block;width:960px;height:700px;padding:0 180px}
      .ai-card{display:block;width:600px;height:120px;padding:12px 28px;border-radius:24px;background:#fff}
      #ed{display:block;width:540px;height:44px;outline:none}</style>
      <div class="page-column">
        <div class="ai-card">
          <div id="ed" contenteditable="true" role="textbox" data-placeholder="Do anything with AI&#8230;"></div>
          <button id="send" type="submit" aria-label="Send message">Send</button>
        </div>
      </div>`);
    await page.addScriptTag({ content: code });
    const r = await page.evaluate(() => {
      const P = window.__P;
      P.init();
      const frame = P.composerFrame();
      const inset = P.barInset ? P.barInset() : null;
      const card = document.querySelector('.ai-card').getBoundingClientRect();
      const fr = frame ? frame.getBoundingClientRect() : null;
      return {
        cardW: Math.round(card.width), frameW: fr ? Math.round(fr.width) : null,
        framePadded: frame ? Math.round(parseFloat(getComputedStyle(frame).paddingLeft) || 0) : null,
        inset,
      };
    });
    if (r.frameW === null) throw new Error('an AI card must resolve a composer frame: ' + JSON.stringify(r));
    // The card is 600px + 56px of padding = 656px border-box; the column is 960.
    // Anything close to the column width means we docked to the wrong element.
    if (r.frameW > 760) {
      throw new Error('the composer frame must be the AI CARD, not the 960px page column (got ' + r.frameW + 'px): ' + JSON.stringify(r));
    }
    if (r.frameW < 500) {
      throw new Error('the composer frame must be the card, not the bare editor (got ' + r.frameW + 'px): ' + JSON.stringify(r));
    }
    if (!r.inset || r.inset.left < 20) {
      throw new Error('barInset() must report the card inset so the bar lines up with the text column: ' + JSON.stringify(r));
    }
    if (Math.abs(r.inset.left - r.inset.right) > 2) {
      throw new Error('barInset() must be symmetric for a symmetric card: ' + JSON.stringify(r));
    }
    await page.close();
  }

  // ── 6. CURRENT LARGE COMPOSER: tall editor + tall card is legitimate ─────
  {
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1200, height: 900 });
    await page.setContent(`<!doctype html><style>body{margin:0;background:#191919}
      .card{position:absolute;left:330px;top:180px;width:660px;height:520px;box-sizing:border-box;
        padding:20px;border:1px solid #34343a;border-radius:22px;background:#1d1d22}
      #ed{display:block;width:618px;height:410px;color:white;outline:none}
      button{position:absolute;right:20px;bottom:16px}</style>
      <div class="card"><div id="ed" contenteditable="true" role="textbox" data-placeholder="Ask anything"></div>
      <button aria-label="Send message">Send</button></div>`);
    await page.addScriptTag({ content: code });
    const r = await page.evaluate(() => {
      const P = window.__P; P.init();
      const g = P.barGeometry();
      return g && { mode:g.mode, top:Math.round(g.top), h:Math.round(g.height) };
    });
    if (!r || r.mode !== 'card' || r.top !== 180 || r.h < 500) {
      throw new Error('large Notion composer must dock to its card top: ' + JSON.stringify(r));
    }
    await page.close();
  }

  // ── 7. BOTTOM-ROW CANVAS: deterministic, reserve-free geometry ────────────
  {
    const page = await browser.newPage();
    await page.setViewportSize({ width: 900, height: 650 });
    await page.setContent(`<!doctype html><style>body{margin:0;background:#191919}
      .canvas{position:absolute;left:37px;top:26px;width:762px;height:300px;box-sizing:border-box;
        padding:16px 20px;border:1px solid #38383c;border-radius:17px;background:#202020}
      .lower{position:absolute;left:12px;right:12px;bottom:10px;height:48px}
      #ed{position:absolute;left:0;right:0;top:0;height:22px;outline:none}
      button{position:absolute;right:0;bottom:0}</style>
      <div class="canvas"><div class="lower">
        <div id="ed" contenteditable="true" role="textbox" data-placeholder="Ask Notion AI"></div>
        <button aria-label="Send message">Send</button>
      </div></div>`);
    await page.addScriptTag({ content: code });
    const r = await page.evaluate(() => {
      const P = window.__P; P.init();
      const rows = Array.from({length: 30}, () => P.barGeometry()).map((g) =>
        g && [g.mode, Math.round(g.left), Math.round(g.top), Math.round(g.width), g.reserve === null]);
      return { rows, canvasPadding: document.querySelector('.canvas').style.paddingTop };
    });
    const sig = new Set(r.rows.map(JSON.stringify));
    if (sig.size !== 1 || !r.rows[0] || r.rows[0][0] !== 'editor' ||
        r.rows[0][1] !== 37 || r.rows[0][3] !== 762 || r.rows[0][4] !== true ||
        r.canvasPadding !== '') {
      throw new Error('bottom-row Notion canvas geometry must stay stable and reserve-free: ' + JSON.stringify(r));
    }
    await page.close();
  }

  await browser.close();
  console.log('PASS Notion route guard: an ordinary workspace page is refused (no editor, no frame, not ready), while a genuine AI surface is still recognised off the /ai route via placeholder or transcript evidence, the override is armed only by the explicit open action, and the composer frame resolves to the AI card with a matching content inset');
})().catch((e) => { console.error(e); process.exit(1); });
