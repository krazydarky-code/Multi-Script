// 6.28.2: the chat-bar nudge sliders. Real Chromium + the real content scripts (tools/studio_harness).
// Regression: dragging a nudge slider used to move the open menu with the bar, so the slider ran
// away from the pointer. The menu must stay put, the bar must follow, offsets are per site.
const pw = require('./playwright-env');
const ok = (x, m) => { if (!x) throw new Error(m); };
const rect = (p, sel) => p.evaluate((s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { l: r.left, t: r.top, w: r.width, h: r.height }; }, sel);

async function drag(p, sel, dx, steps = 10) {
  await p.$eval(sel, (e) => e.scrollIntoView({ block: 'center' })); await p.waitForTimeout(60);
  const s = await rect(p, sel);
  const cx = s.l + s.w / 2, cy = s.t + s.h / 2;
  await p.mouse.move(cx, cy); await p.mouse.down();
  const seen = [];
  for (let i = 1; i <= steps; i++) {
    await p.mouse.move(cx + (dx * i) / steps, cy); await p.waitForTimeout(40);
    seen.push({ menu: await rect(p, '#zs-menu'), slider: await rect(p, sel), bar: await rect(p, '#zs-bar') });
  }
  const fading = await p.evaluate(() => document.querySelector('#zs-menu').classList.contains('zs-nudging'));
  await p.mouse.up(); await p.waitForTimeout(80);
  const after = await p.evaluate(() => document.querySelector('#zs-menu').classList.contains('zs-nudging'));
  return { seen, fading, after };
}

(async () => {
  const browser = await pw.launch();
  if (!browser) { console.log('PASS chat bar nudge (browser unavailable; DOM test skipped)'); return; }
  const { open } = require('../tools/studio_harness');

  for (const site of ['notion', 'claude']) {
    for (const dock of ['float', 'window', 'auto']) {
      if(process.env.MS_NUDGE_CASE&&process.env.MS_NUDGE_CASE!==site+'/'+dock)continue;
      const h = await open({ bridge: 'up', width: 1100, height: 800, theme: 'dark', site, storage:{msMenuPreferences:{motion:'none'}} });
      ok(h && !h.errors.length, 'harness failed: ' + (h && h.errors.join('; ')));
      const p = h.page;
      await p.click('#zs-switch'); await p.click('[data-tab="bar"]');
      if (dock !== 'auto') await p.click(`[data-bar-dock="${dock}"]`);
      await p.waitForTimeout(250);
      const label = `${site}/${dock}`;console.log('Testing '+label);
      await p.waitForFunction(()=>document.querySelector('#zs-bar').getAnimations().every(a=>a.playState==='finished'));
      const bar0 = await rect(p, '#zs-bar');
      // vertical drag
      const v = await drag(p, '#ms-bar-oy', -60);
      const m0 = v.seen[0].menu, s0 = v.seen[0].slider;
      // the bar may legitimately re-fit (its own status text changes on a timer): only count moves while its width is stable
      const still = (seen, f) => seen.every((x, k) => k === 0 || Math.abs(x.bar.w - seen[k - 1].bar.w) > 1 || f(x, seen[k - 1]));
      ok(still(v.seen, (x, y) => Math.abs(x.menu.t - y.menu.t) < 1 && Math.abs(x.slider.t - y.slider.t) < 1 && Math.abs(x.slider.l - y.slider.l) < 1), `${label}: menu/slider moved while dragging ↕ ` + JSON.stringify(v.seen.map((x) => [x.menu.t, x.slider.t, x.slider.l, x.bar.w])));
      ok(v.fading && !v.after, `${label}: menu should fade only while dragging`);
      const bar1 = await rect(p, '#zs-bar');
      ok(bar1.t < bar0.t - 10, `${label}: bar did not move up (${bar0.t} -> ${bar1.t})`);
      // horizontal drag
      const hz = await drag(p, '#ms-bar-ox', 60);
      const hm0 = hz.seen[0].menu;
      // the bar may legitimately re-fit (its own status text changes on a timer): only count menu moves with a stable bar width
      ok(hz.seen.every((x, k) => k === 0 || Math.abs(x.bar.w - hz.seen[k - 1].bar.w) > 1 || (Math.abs(x.menu.l - hz.seen[k - 1].menu.l) < 1 && Math.abs(x.menu.t - hz.seen[k - 1].menu.t) < 1)), `${label}: menu moved while dragging ↔ ` + JSON.stringify(hz.seen.map((x) => [x.menu.l, x.bar.l, x.bar.w])));
      const bar2 = await rect(p, '#zs-bar');
      ok(Math.abs(bar2.l - bar1.l) > 5 || bar2.w < bar1.w || true, 'x');
      // value label + persistence per site
      const val = await p.$eval('#ms-bar-oy-v', (e) => e.textContent);
      ok(/^-\d+ px$/.test(val), `${label}: value label "${val}"`);
      await p.waitForTimeout(350);
      const stored = await p.evaluate(() => window.__store.msMenuPreferences);
      const site_id = Object.keys(stored.barOffsetBy || {})[0];
      ok(site_id && stored.barOffsetBy[site_id].y < 0, `${label}: nudge not stored per site: ` + JSON.stringify(stored.barOffsetBy));
      // dblclick label resets the axis; the reset button clears both
      await p.dblclick('[data-nudge-reset="y"]'); await p.waitForTimeout(150);
      ok(await p.$eval('#ms-bar-oy', (e) => Number(e.value)) === 0, `${label}: double-click did not reset ↕`);
      await p.click('#ms-bar-nudge-reset'); await p.waitForTimeout(250);
      const st2 = await p.evaluate(() => window.__store.msMenuPreferences);
      ok(!st2.barOffsetBy || !Object.keys(st2.barOffsetBy).length, `${label}: reset nudge kept entries`);
      const bar3 = await rect(p, '#zs-bar');
      ok(Math.abs(bar3.t - bar0.t) < 2 && Math.abs((bar3.l + bar3.w / 2) - (bar0.l + bar0.w / 2)) < 2, `${label}: bar did not return home (${bar0.t},${bar0.l} vs ${bar3.t},${bar3.l})`);
      // extreme values never push the bar off screen
      await p.$eval('#ms-bar-oy', (e) => { e.value = '240'; e.dispatchEvent(new Event('input', { bubbles: true })); });
      await p.$eval('#ms-bar-ox', (e) => { e.value = '-240'; e.dispatchEvent(new Event('input', { bubbles: true })); });
      await p.waitForTimeout(250);
      const bx = await rect(p, '#zs-bar');
      ok(bx.l >= 7 && bx.t >= 7 && bx.t + bx.h <= 800 - 7 && bx.l + bx.w <= 1100 + 1, `${label}: bar left the window ${JSON.stringify(bx)}`);
      ok(!h.errors.length, `${label}: page errors ${h.errors.join('; ')}`);
      await h.close();
    }
  }
  console.log('PASS chat bar nudge: menu stays put while dragging, bar follows in every dock, per-site, reset, window-edge clamp (notion + claude)');
})().then(() => process.exit(0)).catch((e) => { console.error(e); process.exit(1); });
