// SPDX-License-Identifier: GPL-3.0-or-later
// 6.25 chat-bar regression (real Chromium + the real content-script chain):
//  - Notion Auto follows its native composer without changing native children
//  - Chat bar customisation: dock modes, alignment, style, size, hidden items, reset
//  - Claude loads (init-order crash regression) and docks above its composer
const h = require('../tools/studio_harness');
let passed = 0;
const ok = (c, m) => { if (!c) throw new Error('FAIL ' + m); passed++; console.log('PASS ' + m); };
const geo = (page) => page.evaluate(() => {
  const r = (s) => { const e = document.querySelector(s); const b = e && e.getBoundingClientRect(); return b && { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height }; };
  return { bar: r('#zs-bar'), comp: r('.composer, fieldset'), ed: r('#agent-editor, .ProseMirror'), vw: innerWidth, vh: innerHeight };
});

(async () => {
  // 1. Notion Auto follows the actual composer in the empty landing page.
  let x = await h.open({ bridge: 'up', host: 'installed', theme: 'dark', width: 1134, height: 834, layout: 'empty-tall' });
  if (!x) { console.log('SKIP chat bar studio (no browser available)'); return; }
  try {
    const g = await geo(x.page);
    ok(Math.abs(g.bar.l-g.comp.l)<=3 && g.bar.b<=g.comp.t+2,
      'Notion Auto hugs the composer');
    ok(g.bar.w <= g.comp.w + 2, 'Notion Auto matches its composer width');
    const idleStop = await x.page.evaluate(() => {
      const e = document.querySelector('#zs-stop');
      return { hidden: e.hidden, display: getComputedStyle(e).display };
    });
    ok(idleStop.hidden && idleStop.display === 'none',
      `Stop stays hidden while an engine is ready but no agent is running: ${JSON.stringify(idleStop)}`);
    ok(x.errors.length === 0, 'no page errors: ' + x.errors.join(' | ').slice(0, 160));
  } finally { await x.close(); }

  // 2. notion.ai's current large canvas keeps the editor at the bottom. The
  // bar must use one stable, reserve-free coordinate instead of alternating
  // between the outer canvas and transient lower wrappers.
  x = await h.open({ bridge: 'up', host: 'installed', theme: 'dark', width: 1134, height: 834 });
  try {
    const stable = await x.page.evaluate(async () => {
      const c = document.querySelector('.composer'), ed = document.querySelector('#agent-editor'), row = document.querySelector('.row');
      c.style.cssText += ';height:300px;position:relative';
      ed.style.cssText = 'position:absolute;left:20px;right:20px;bottom:54px;height:24px';
      row.style.cssText += ';position:absolute;left:20px;right:20px;bottom:12px';
      await new Promise((r) => setTimeout(r, 250));
      const tops = [], pads = [];
      for (let i = 0; i < 45; i++) {
        await new Promise(requestAnimationFrame);
        tops.push(Math.round(document.querySelector('#zs-bar').getBoundingClientRect().top));
        pads.push(getComputedStyle(c).paddingTop);
      }
      return { spread: Math.max(...tops) - Math.min(...tops), top: tops[0], barHeight: document.querySelector('#zs-bar').getBoundingClientRect().height, editorTop: Math.round(ed.getBoundingClientRect().top), pads:[...new Set(pads)] };
    });
    ok(stable.spread <= 1 && stable.top < stable.editorTop && stable.editorTop-stable.top<=stable.barHeight+25 && stable.pads.length === 1 && stable.pads[0] === '14px',
      `Notion bottom-row canvas stays motionless without padding feedback: ${JSON.stringify(stable)}`);
  } finally { await x.close(); }

  // 3. The same stable Auto dock is used when no painted card exists.
  x = await h.open({ bridge: 'up', host: 'installed', theme: 'dark', width: 1134, height: 834, layout: 'empty-bare' });
  try {
    const g = await geo(x.page);
    ok(Math.abs(g.bar.l-g.comp.l)<=3 && g.bar.b<=g.comp.t+2,
      'unpainted composer keeps the bar above its editor');
    ok(g.bar.w <= g.comp.w + 2, 'unpainted composer width is respected');
  } finally { await x.close(); }

  // 4. customisation through stored preferences
  const prefs = (o) => ({ msMenuPreferences: o });
  x = await h.open({ bridge: 'up', host: 'installed', theme: 'dark', width: 1134, height: 834, storage: prefs({ barDock: 'window', barAlign: 'center', barFit: 'fit' }) });
  try {
    const g = await geo(x.page);
    ok(Math.abs((g.bar.l + g.bar.r) / 2 - g.vw / 2) <= 3 && g.bar.b > g.vh - 40, 'window dock: centred pill at the bottom of the window');
    ok(g.bar.w < g.comp.w + 160 && g.bar.w < g.vw - 200, `fit width: the pill hugs its content (${Math.round(g.bar.w)}px vs composer ${Math.round(g.comp.w)}px)`);
  } finally { await x.close(); }
  x = await h.open({ bridge: 'up', host: 'installed', theme: 'dark', width: 1134, height: 834, storage: prefs({ barDock: 'float', barAlign: 'right', barFit: 'fit', barStyle: 'glass', barSize: 'roomy', barHide: ['discord', 'support', 'chatOnly'] }) });
  try {
    const g = await geo(x.page);
    ok(Math.abs(g.bar.r - g.comp.r) <= 2 && g.bar.b <= g.comp.t, 'floating dock: right-aligned pill hugging the composer from outside');
    const st = await x.page.evaluate(() => ({ h: document.querySelector('#zs-root').dataset.msHide, style: document.querySelector('#zs-root').dataset.msBarStyle, chat: getComputedStyle(document.querySelector('#zs-chat-only')).display, size: document.querySelector('#zs-action').getBoundingClientRect().height }));
    ok(/chatOnly/.test(st.h) && st.chat === 'none' && st.style === 'glass', 'hidden items and style are applied');
    ok(st.size >= 35, 'roomy size grows the controls');
  } finally { await x.close(); }

  // 5. the in-menu customiser drives the live bar
  x = await h.open({ bridge: 'up', host: 'installed', theme: 'dark', width: 1134, height: 834 });
  try {
    const { page } = x;
    await page.click('#zs-switch'); await page.click('.zs-menu-tabs button[data-tab="bar"]');
    await page.click('[data-bar-dock="window"]'); await page.waitForTimeout(250);
    let g = await geo(x.page);
    ok(g.bar.b > g.vh - 40, 'clicking Window moves the live bar to the bottom of the window');
    await page.click('[data-bar-align="right"]'); await page.waitForTimeout(250);
    g = await geo(x.page);
    ok(g.vw - g.bar.r <= 24, 'Align → Right pins it to the right edge');
    await page.evaluate(() => { const r = document.querySelector('#ms-bar-oy'); r.value = '-60'; r.dispatchEvent(new Event('input', { bubbles: true })); });
    await page.waitForTimeout(200);
    const g2 = await geo(x.page);
    ok(g2.bar.t < g.bar.t - 50, 'vertical nudge moves the bar');
    await page.evaluate(() => { const c = document.querySelector('[data-bar-item="terminal"]'); c.checked = false; c.dispatchEvent(new Event('change', { bubbles: true })); });
    await page.waitForTimeout(100);
    ok(await page.evaluate(() => getComputedStyle(document.querySelector('#zs-bridge')).display) === 'none', 'unticking Terminal hides the terminal button');
    const saved = await page.evaluate(() => new Promise((r) => chrome.storage.local.get('msMenuPreferences', (v) => r(v.msMenuPreferences))));
    ok(saved && saved.barDock === 'window' && saved.barAlign === 'right' && saved.barHide.includes('terminal'), 'bar preferences are persisted');
    await page.click('#ms-bar-reset'); await page.waitForTimeout(300);
    g = await geo(x.page);
    ok(g.bar.b <= g.comp.t + 2 && Math.abs(g.bar.l-g.comp.l)<=3 &&
      await page.evaluate(() => getComputedStyle(document.querySelector('#zs-bridge')).display) !== 'none',
      'Reset chat bar returns to the composer with every item visible');
    ok(x.errors.length === 0, 'customiser: no page errors: ' + x.errors.join(' | ').slice(0, 160));
  } finally { await x.close(); }

  // 6. Portal regression: barMount() providers move #zs-bar out of #zs-root.
  x = await h.open({ bridge: 'up', host: 'installed', theme: 'dark', width: 1134, height: 834 });
  try {
    const portal = await x.page.evaluate(() => {
      const b = document.querySelector('#zs-bar');
      document.querySelector('.composer').prepend(b);
      b.className = 'zs-bar-inline zs-bar-inside';
      const acts = document.querySelector('#zs-acts');
      const kids = [...acts.children].filter((e) => getComputedStyle(e).display !== 'none');
      const ar = acts.getBoundingClientRect();
      const ys = kids.map((e) => { const r = e.getBoundingClientRect(); return Math.round(r.top + r.height / 2); });
      return {
        parent: b.parentElement.className,
        dir: getComputedStyle(acts).flexDirection,
        spread: ys.length ? Math.max(...ys) - Math.min(...ys) : 999,
        contained: kids.every((e) => e.getBoundingClientRect().right <= ar.right + 2),
      };
    });
    ok(/composer/.test(portal.parent) && portal.dir === 'row' && portal.spread <= 2 && portal.contained,
      `provider portal keeps every chat-bar control in one contained row: ${JSON.stringify(portal)}`);
  } finally { await x.close(); }

  // 7. Claude: loads without the init-order crash, docks above its composer, switcher lists it with a description
  x = await h.open({ bridge: 'up', host: 'installed', theme: 'dark', width: 1134, height: 834, site: 'claude' });
  try {
    const g = await geo(x.page);
    ok(x.errors.length === 0, 'Claude page loads with no page errors (init-order crash regression): ' + x.errors.join(' | ').slice(0, 160));
    ok(g.bar && Math.abs(g.bar.l - g.comp.l) <= 2 && g.bar.b <= g.ed.t + 2, 'Claude: bar docks on the fieldset composer, above the editor');
    await x.page.click('#zs-switch'); await x.page.click('.zs-menu-tabs button[data-tab="sites"]');
    const row = await x.page.evaluate(() => { const r = document.querySelector('.ms-bench-card[data-provider="claude"]');return r&&{here:r.classList.contains('active'),txt:r.textContent,note:r.querySelector('p')?.textContent}; });
    ok(row && row.here && /Current provider/.test(row.txt) && row.note?.length>10, 'AI sites lists Claude as the active provider with its description');
  } finally { await x.close(); }
  // Previous Studio visibility preferences migrate to the direct New idea action.
  x = await h.open({bridge:'up',host:'installed',theme:'dark',storage:{msMenuPreferences:{barHide:['studio']}}});
  try {
    ok(!await x.page.locator('#ms-new-idea').isVisible(),'legacy hidden Studio preference hides the replacement New idea action');
    await x.page.click('#zs-switch');await x.page.click('[data-tab="bar"]');
    ok(!await x.page.locator('[data-bar-item="ideas"]').isChecked(),'visibility editor reflects migrated New idea preference');
    await x.page.locator('label').filter({has:x.page.locator('[data-bar-item="ideas"]')}).click();
    ok(await x.page.locator('#ms-new-idea').isVisible(),'New idea can be shown again after migration');
  } finally {await x.close();}
  console.log(`PASS chat bar studio (${passed} checks)`);
})().catch((e) => { console.error(e.message || e); process.exit(1); });
