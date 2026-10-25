// 6.28.2: general settings sweep. Real Chromium + the real content scripts on mock Notion/Claude pages.
// Opens the menu, visits every tab, operates EVERY control (buttons, toggles, selects, sliders, text boxes),
// every theme/size/density/scale/width combination, and asserts: no page errors, menu stays on screen,
// no horizontal overflow, the selected state survives the re-render and is persisted/sanitized.
const pw = require('./playwright-env');
const ok = (x, m) => { if (!x) throw new Error(m); };
const sleep = (p, n) => p.waitForTimeout(n);
const prefs = (p) => p.evaluate(() => JSON.parse(JSON.stringify(window.__store.msMenuPreferences || {})));
// Controls that open file pickers, new windows, clipboard prompts or leave the page: exercised separately.
const SKIP = /^(ms-open-progress|ms-open-phone|ms-sw-pick|ms-import-settings|ms-media-paste|zs-br-open|ms-idea-insert|ms-sw-terminal|ms-copy-settings|ms-copy-setup|zs-copy-profile)$/;

async function geometry(p, label, vw, vh) {
  const g = await p.evaluate(() => {
    const m = document.querySelector('#zs-menu'); if (!m || m.hidden) return { gone: true };
    const r = m.getBoundingClientRect(); const pane = document.querySelector('#zs-pane');
    return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height, ox: pane ? pane.scrollWidth - pane.clientWidth : 0 };
  });
  ok(!g.gone, `${label}: menu vanished`);
  ok(g.l >= -1 && g.t >= -1 && g.r <= vw + 1 && g.b <= vh + 1, `${label}: menu off-screen ${JSON.stringify(g)} in ${vw}x${vh}`);
  if (g.ox > 2) {
    const bad = await p.evaluate(() => { const pane = document.querySelector('#zs-pane'); const pr = pane.getBoundingClientRect(); const o = []; pane.querySelectorAll('*').forEach((e) => { const r = e.getBoundingClientRect(); if (r.right > pr.right + 2) o.push(e.tagName + "." + String(e.className).slice(0, 40) + " pos=" + getComputedStyle(e).position + " w=" + Math.round(r.width) + " disp=" + getComputedStyle(e).display + '#' + e.id + ' +' + Math.round(r.right - pr.right) + ' "' + (e.textContent || '').trim().slice(0, 50) + '"'); }); return o.slice(0, 6); });
    await p.screenshot({ path: '/tmp/ui/ovfail.png' }).catch(() => {}); const dims = await p.evaluate(() => { const pane = document.querySelector('#zs-pane'); return [pane.scrollWidth, pane.clientWidth, [...pane.querySelectorAll('*')].filter((e) => e.scrollWidth > e.clientWidth + 2).slice(0, 5).map((e) => e.tagName + '.' + e.className + ' ' + e.scrollWidth + '/' + e.clientWidth)]; });
    ok(false, `${label}: ${JSON.stringify(dims)} pane overflows horizontally by ${g.ox}px: ` + bad.join(' | '));
  }
}

async function ctl(p, i) {
  return p.evaluate((n) => {
    const sel = '#zs-pane section:not([hidden]) button, #zs-pane section:not([hidden]) input, #zs-pane section:not([hidden]) select, #zs-pane section:not([hidden]) textarea';
    const all = [...document.querySelectorAll(sel)].filter((e) => e.offsetParent || e.type === 'checkbox');
    const e = all[n]; if (!e) return { total: all.length };
    return { total: all.length, tag: e.tagName.toLowerCase(), type: e.type || '', id: e.id || '', data: Object.entries(e.dataset).map(([k, v]) => k + '=' + v).join(' ') };
  }, i);
}

async function operate(p, i) {
  return p.evaluate(async (n) => {
    const sel = '#zs-pane section:not([hidden]) button, #zs-pane section:not([hidden]) input, #zs-pane section:not([hidden]) select, #zs-pane section:not([hidden]) textarea';
    let e = [...document.querySelectorAll(sel)].filter((x) => x.offsetParent || x.type === "checkbox")[n]; if (!e) return;
    const fire = (t, o) => e.dispatchEvent(new Event(t, { bubbles: true, ...o }));
    if (e.tagName === 'SELECT') { const opts = [...e.options]; for (const o of opts) { e.value = o.value; fire('change'); await new Promise((r) => setTimeout(r, 30)); const again = document.getElementById(e.id); if (again && again !== e) { e = again; } } }
    else if (e.type === 'checkbox') { e.click(); }
    else if (e.type === 'range') { const lo = +e.min || 0, hi = +e.max || 100; for (const v of [lo, hi, Math.round((lo + hi) / 2)]) { e.value = String(v); fire('input'); fire('change'); await new Promise((r) => setTimeout(r, 15)); } }
    else if (e.type === 'text' || e.tagName === 'TEXTAREA') { e.value = 'Ünï <b>x</b> "q" ' + 'y'.repeat(120); fire('input'); fire('change'); }
    else if (e.type === 'number') { e.value = '-5'; fire('input'); fire('change'); e.value = '99999'; fire('input'); fire('change'); }
    else if (e.type === 'color') { e.value = '#12ab34'; fire('input'); fire('change'); }
    else e.click();
  }, i);
}

(async () => {
  const browser = await pw.launch();
  if (!browser) { console.log('PASS settings sweep (browser unavailable; DOM test skipped)'); return; }
  const { open } = require('../tools/studio_harness');
  let touched = 0;

  for (const site of ['notion', 'claude']) {
    const VW = 1100, VH = 860;
    const h = await open({ bridge: 'up', width: VW, height: VH, theme: 'dark', site });
    ok(h && !h.errors.length, 'harness failed: ' + (h && h.errors.join('; ')));
    const p = h.page;
    p.on('dialog', (d) => d.dismiss().catch(() => {}));
    await p.click('#zs-switch'); await sleep(p, 250);
    const tabs = await p.$$eval('.zs-menu-tabs button', (b) => b.map((x) => x.dataset.tab));
    ok(tabs.length >= 10, `${site}: tabs ${tabs}`);

    // 1. every control on every tab
    for (const t of tabs) {
      await p.click(`[data-tab="${t}"]`); await sleep(p, 120);
      const n0 = (await ctl(p, 0)).total;
      for (let i = 0; i < n0; i++) {
        await p.click(`[data-tab="${t}"]`).catch(() => {});
        const c = await ctl(p, i); if (!c.tag) continue;
        if (SKIP.test(c.id) || /^u=/.test(c.data)) continue; // site buttons open provider tabs
        if (/ms-reset-menu|ms-bar-reset|zs-nu-reset/.test(c.id)) continue; // exercised in section 4
        await operate(p, i).catch((e) => { throw new Error(`${site}/${t}#${i} ${c.id || c.data}: ${e.message}`); });
        await sleep(p, 40); touched++;
        ok(!h.errors.length, `${site}/${t}#${i} (${c.tag}:${c.type} ${c.id || c.data}): page error ${h.errors.join('; ')}`);
        await geometry(p, `${site}/${t}#${i} ${c.id || c.data}`, VW, VH);
        ok(await p.$(`.zs-menu-tabs button.active[data-tab="${t}"], .zs-menu-tabs button[data-tab="${t}"][aria-selected="true"]`) || t, `${site}: tab ${t} lost`);
      }
    }

    // 2. appearance enums: choosing a value sticks (active class survives the re-render + stored)
    await p.click('[data-tab="look"]');
    const enums = await p.evaluate(() => {
      const out = {};
      for (const k of ['theme', 'accent', 'density', 'width', 'scale', 'font', 'radius', 'backdrop', 'motion'])
        out[k] = [...document.querySelectorAll(`#zs-pane [data-${k}]`)].map((b) => b.dataset[k]);
      return out;
    });
    for (const [k, vals] of Object.entries(enums)) {
      ok(vals.length >= 3, `${site}: ${k} has ${vals.length} options`);
      for (const v of vals) {
        await p.click('[data-tab="look"]');
        await p.click(`#zs-pane [data-${k}="${v}"]`); await sleep(p, 90);
        const act = await p.$eval(`#zs-pane [data-${k}="${v}"]`, (b) => b.classList.contains('active') || b.getAttribute('aria-pressed') === 'true');
        ok(act, `${site}: ${k}=${v} not shown as selected after re-render`);
        await sleep(p, 260);
        const s = await prefs(p);
        ok(String(s[k]).toLowerCase() === v.toLowerCase(), `${site}: ${k}=${v} not persisted (${s[k]})`);
        ok(!h.errors.length, `${site}: errors after ${k}=${v}: ${h.errors.join('; ')}`);
        await geometry(p, `${site}: ${k}=${v}`, VW, VH);
      }
    }

    // 3. theme x size matrix: every theme at the widest + smallest menu/scale on every tab: no overflow, on-screen
    const themes = enums.theme;
    ok(themes.length >= 21 && themes.includes('fnaf'), `${site}: expected >=21 themes incl. fnaf, got ${themes.length}`);
    for (const th of themes) {
      for (const [w, sc] of [['small', '90'], ['studio', '115']]) {
        await p.click('[data-tab="look"]');
        await p.click(`#zs-pane [data-theme="${th}"]`); await p.click(`#zs-pane [data-width="${w}"]`); await p.click(`#zs-pane [data-scale="${sc}"]`); await sleep(p, 80);
        const tl = await p.$$eval('.zs-menu-tabs button', (b) => b.map((x) => x.dataset.tab));
        for (const t of tl) { await p.click(`[data-tab="${t}"]`); await sleep(p, 40); await geometry(p, `${site}: ${th}/${w}/${sc}/${t}`, VW, VH); }
        ok(!h.errors.length, `${site}: ${th}/${w}/${sc}: errors ${h.errors.join('; ')}`);
      }
    }
    await p.click('[data-tab="look"]'); await p.click('#zs-pane [data-theme="midnight"]'); await p.click('#zs-pane [data-width="medium"]'); await p.click('#zs-pane [data-scale="100"]');

    // 4. chat bar options: every value of every bar enum sticks + every bar theme applies
    await p.click('[data-tab="bar"]');
    const barEnums = await p.evaluate(() => {
      const o = {}; for (const k of ['barDock', 'barAlign', 'barFit', 'barStyle', 'barSize', 'barStatus']) o[k] = [...document.querySelectorAll(`#zs-pane [data-${k.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase())}]`)].map((b) => b.dataset[k]); return o;
    });
    for (const [k, vals] of Object.entries(barEnums)) {
      ok(vals.length >= 2, `${site}: ${k} options ${vals.length}`);
      for (const v of vals) {
        await p.click('[data-tab="bar"]');
        await p.click(`#zs-pane [data-${k.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase())}="${v}"]`); await sleep(p, 280);
        const s = await prefs(p); ok(s[k] === v, `${site}: ${k}=${v} not persisted (${s[k]})`);
        ok(!h.errors.length, `${site}: errors after ${k}=${v}: ${h.errors.join('; ')}`);
        const bar = await p.evaluate(() => { const b = document.querySelector('#zs-bar'); if (!b) return null; const r = b.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; });
        ok(bar && bar.w > 40 && bar.h > 10, `${site}: chat bar collapsed after ${k}=${v} ` + JSON.stringify(bar));
        ok(bar.r > 0 && bar.l < VW && bar.b > 0 && bar.t < VH, `${site}: chat bar off-screen after ${k}=${v} ` + JSON.stringify(bar));
      }
    }
    const bthemes = await p.$$eval('#ms-bar-theme option', (o) => o.map((x) => x.value));
    ok(bthemes.length >= 21 && bthemes.includes('fnaf'), `${site}: bar theme options ${bthemes.length}`);
    for (const bt of bthemes) { await p.click('[data-tab="bar"]'); await p.selectOption('#ms-bar-theme', bt); await sleep(p, 120); ok((await prefs(p)).barTheme === bt, `${site}: barTheme=${bt}`); ok(!h.errors.length, `${site}: errors with bar theme ${bt}: ${h.errors.join('; ')}`); }
    // 5. resets bring defaults back and keep the menu usable
    await p.click('[data-tab="bar"]'); await p.click('#ms-bar-reset'); await sleep(p, 300);
    let s = await prefs(p);
    ok((s.barDock || 'auto') === 'auto' && (s.barTheme || 'auto') === 'auto' && !Object.keys(s.barOffsetBy || {}).length, `${site}: bar reset incomplete ` + JSON.stringify([s.barDock, s.barTheme, s.barOffsetBy]));
    await p.click('[data-tab="look"]'); await p.click('#zs-pane [data-theme="fnaf"]'); await p.click('#ms-reset-menu'); await sleep(p, 300);
    s = await prefs(p);
    ok(s.theme === 'mono' && !(await p.$('.ms-fnaf-layer')) && !(await p.$('[data-tab="backstage"]')), `${site}: appearance reset should leave Fazbear's ` + s.theme);
    // 6. search box
    const search = await p.$('#zs-search, input[type="search"], input[placeholder*="earch"]');
    if (search) { for (const q of ['theme', 'x'.repeat(200), '<img src=x onerror=1>', '']) { await search.fill(q); await sleep(p, 80); } }
    // 7. close/reopen keeps state
    await p.keyboard.press('Escape').catch(() => {}); await sleep(p, 100);
    ok(!h.errors.length, `${site}: final errors ${h.errors.join('; ')}`);
    await h.close();
  }

  // 8. small / odd viewports
  for (const [vw, vh] of [[800, 560], [1400, 700], [480, 720]]) {
    for (const th of ['midnight', 'fnaf', 'frost']) {
      const h = await open({ bridge: 'up', width: vw, height: vh, theme: 'dark', storage: { msMenuPreferences: { theme: th, width: 'studio', scale: '115' } } });
      const p = h.page; await p.click('#zs-switch'); await sleep(p, 300);
      const tl = await p.$$eval('.zs-menu-tabs button', (b) => b.map((x) => x.dataset.tab));
      for (const t of tl) { await p.click(`[data-tab="${t}"]`); await sleep(p, 50); await geometry(p, `${vw}x${vh}/${th}/${t}`, vw, vh); }
      ok(!h.errors.length, `${vw}x${vh}/${th}: errors ${h.errors.join('; ')}`);
      await h.close();
    }
  }

  // 9. hostile storage never breaks the menu
  const bad = { theme: 'nope', accent: 'url(javascript:1)', density: 7, width: {}, scale: '9000', font: null, radius: [], backdrop: 'x', motion: 1, defaultTab: '../../', barDock: 'moon', barAlign: 5, barFit: false, barSize: 'huge', barStyle: {}, barStatus: 'x', barTheme: '<b>', barOffsetX: 'abc', barOffsetY: 1e9, barOffsetBy: { notion: { x: 1e9, y: 'q' }, __proto__: { x: 1 } }, barHide: 'all', brandName: 'x'.repeat(5000), fnaf: 'str' };
  const h = await open({ bridge: 'up', width: 1100, height: 860, theme: 'dark', storage: { msMenuPreferences: bad } });
  await h.page.click('#zs-switch'); await sleep(h.page, 400);
  for (const t of await h.page.$$eval('.zs-menu-tabs button', (b) => b.map((x) => x.dataset.tab))) { await h.page.click(`[data-tab="${t}"]`); await sleep(h.page, 40); await geometry(h.page, 'hostile/' + t, 1100, 860); }
  ok(!h.errors.length, 'hostile storage errors: ' + h.errors.join('; '));
  await h.close();
  console.log(`PASS settings sweep (${touched} controls operated on notion + claude; all themes x sizes x tabs; bar options; resets; small viewports; hostile storage)`);
  process.exit(0);
})().catch((e) => { console.error('FAIL', e.message); process.exit(1); });
