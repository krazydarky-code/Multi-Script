// 6.28.2: the live "Fazbear's" theme + its secret Backstage tab. Real Chromium + the real content scripts.
const pw = require('./playwright-env');
const ok = (x, m) => { if (!x) throw new Error(m); };
const sleep = (p, n) => p.waitForTimeout(n);
const store = (p) => p.evaluate(() => JSON.parse(JSON.stringify(window.__store.msMenuPreferences || {})));
const tabs = (p) => p.$$eval('.zs-menu-tabs button', (b) => b.map((x) => x.dataset.tab));
const setRange = (p, sel, v) => p.$eval(sel, (e, val) => { e.value = String(val); e.dispatchEvent(new Event('input', { bubbles: true })); }, v);

(async () => {
  const browser = await pw.launch();
  if (!browser) { console.log('PASS fnaf theme (browser unavailable; DOM test skipped)'); return; }
  const { open } = require('../tools/studio_harness');

  for (const site of ['notion', 'claude']) {
    const h = await open({ bridge: 'up', width: 1100, height: 900, theme: 'dark', site });
    ok(h && !h.errors.length, 'harness failed: ' + (h && h.errors.join('; ')));
    const p = h.page;
    await p.click('#zs-switch'); await sleep(p, 200);
    ok(!(await tabs(p)).includes('backstage'), `${site}: Backstage visible before the theme is on`);
    ok(!(await p.$('.ms-fnaf-layer')), `${site}: fnaf layer exists before the theme is on`);
    await p.click('[data-tab="look"]'); await p.click('[data-theme="fnaf"]'); await sleep(p, 500);
    ok(await p.$('#zs-menu .ms-fnaf-layer'), `${site}: fnaf layer missing`);
    await p.waitForSelector('#zs-menu .ms-fnaf-intro', { timeout: 1500 }).catch(() => {});
    ok(await p.$('#zs-menu .ms-fnaf-intro'), `${site}: selecting the theme should play the curtain intro`);
    ok(await p.$('#zs-menu .ms-fnaf-spot'), `${site}: spotlight layer missing`);
    ok((await tabs(p)).includes('backstage'), `${site}: Backstage tab did not appear`);
    ok(await p.$eval('#zs-root, [data-ms-theme]', (e) => e.dataset.msTheme === 'fnaf'), `${site}: data-ms-theme not fnaf`);

    // tile bands must share one grid so tiles line up (same size + the same horizontal origin)
    const bands = await p.evaluate(() => {
      const g = (s) => { const e = document.querySelector('#zs-menu .ms-fnaf-' + s); const c = getComputedStyle(e); const r = e.getBoundingClientRect(); return { size: c.backgroundSize, pos: c.backgroundPositionX, l: r.left, w: r.width, t: r.top, h: r.height }; };
      const m = document.querySelector('#zs-menu').getBoundingClientRect();
      return { top: g('top'), bottom: g('bottom'), m: { l: m.left, w: m.width, t: m.top, h: m.height } };
    });
    ok(bands.top.size === bands.bottom.size, `${site}: band tile sizes differ ${bands.top.size} vs ${bands.bottom.size}`);
    ok(bands.top.pos === bands.bottom.pos && Math.abs(bands.top.l - bands.bottom.l) < 1 && Math.abs(bands.top.w - bands.bottom.w) < 1, `${site}: band columns misaligned ${JSON.stringify([bands.top, bands.bottom])}`);
    ok(bands.top.t <= bands.m.t + 1 && bands.bottom.t + bands.bottom.h >= bands.m.t + bands.m.h - 1, `${site}: bands not flush with the menu top/bottom`);

    // Backstage
    await p.click('[data-tab="backstage"]'); await sleep(p, 250);
    const pizzas = () => p.$$eval('.ms-fnaf-pizzas > *', (a) => a.length);
    const n0 = await pizzas(); ok(n0 > 0, `${site}: no pizzas by default`);
    await setRange(p, '#ms-fz-pizzas', 0); await sleep(p, 400);
    ok((await pizzas()) === 0, `${site}: pizzas slider 0 should remove pizzas`);
    await setRange(p, '#ms-fz-pizzas', 9); await sleep(p, 400);
    ok((await pizzas()) === 9, `${site}: pizzas slider 9 gave ${await pizzas()}`);
    await setRange(p, '#ms-fz-blur', 5); await setRange(p, '#ms-fz-speed', 150); await setRange(p, '#ms-fz-glow', 40); await sleep(p, 450);
    let s = await store(p);
    ok(s.fnaf.pizzas === 9 && s.fnaf.blur === 5 && s.fnaf.speed === 150 && s.fnaf.glow === 40, `${site}: fnaf sliders not persisted ` + JSON.stringify(s.fnaf));
    ok(await p.$eval('#ms-fz-pizzas-v', (e) => e.textContent.trim() === '9'), `${site}: slider label`);

    // tile size
    await p.click('[data-fz-tile="32"]'); await sleep(p, 300);
    ok(await p.$eval('#zs-menu', (e) => e.style.getPropertyValue('--fz-tile') === '32px'), `${site}: tile size`);
    ok(await p.$('[data-tab="backstage"].active, .zs-menu-tabs button.active[data-tab="backstage"]'), `${site}: Backstage tab lost after rebuild`);

    // cast -> accent
    const acc0 = await p.evaluate(() => getComputedStyle(document.querySelector('#zs-root,[data-ms-theme]')).getPropertyValue('--ms-accent').trim());
    const castIds = await p.$$eval('[data-fz-cast]:not([disabled])', (a) => a.map((x) => x.dataset.fzCast));
    ok(castIds.length >= 3, `${site}: expected unlocked cast members`);
    const other = castIds.find((c) => c !== (s.fnaf.cast)) ;
    await p.click(`[data-fz-cast="${other}"]`); await sleep(p, 300);
    const acc1 = await p.evaluate(() => getComputedStyle(document.querySelector('#zs-root,[data-ms-theme]')).getPropertyValue('--ms-accent').trim());
    ok(acc0 !== acc1, `${site}: cast did not change the accent (${acc0})`);
    ok(await p.$('[data-fz-cast="golden"][disabled]'), `${site}: Golden should be locked at first`);
    for (const id of ['puppet', 'springtrap', 'fredbear']) ok(await p.$(`[data-fz-cast="${id}"][disabled]`), `${site}: ${id} should be locked until the office nights are cleared`);
    ok(await p.$('#ms-fz-office-wrap .ms-fz-door') && !(await p.$('#ms-fz-office')), `${site}: Security Office must be locked behind the keycard`);

    // toggles
    await p.click('label:has([data-fz-toggle=\"staticFx\"])'); await p.click('label:has([data-fz-toggle=\"flicker\"])'); await sleep(p, 400);
    s = await store(p);
    const cls = await p.$eval('#zs-menu', (e) => ({ st: e.classList.contains('ms-fnaf-static'), fl: e.classList.contains('ms-fnaf-flicker') }));
    ok(cls.st === s.fnaf.staticFx && cls.fl === s.fnaf.flicker, `${site}: toggles/classes out of sync ` + JSON.stringify([cls, s.fnaf]));

    // depth follows scroll
    await p.click('[data-tab="backstage"]'); await sleep(p, 100);
    await p.$eval('#zs-pane', (e) => { e.scrollTop = 0; });
    await p.waitForFunction(() => parseFloat(document.querySelector('#zs-menu').style.getPropertyValue('--fz-depth')) <= 0.02, null, { timeout: 4000 }).catch(() => {}); await sleep(p, 100);
    const d0 = await p.$eval('#zs-menu', (e) => parseFloat(e.style.getPropertyValue('--fz-depth')));
    await p.$eval('#zs-pane', (e) => { e.scrollTop = e.scrollHeight; });
    await p.waitForFunction(() => parseFloat(document.querySelector('#zs-menu').style.getPropertyValue('--fz-depth')) > 0.8, null, { timeout: 4000 }).catch(() => {}); await sleep(p, 100);
    const d1 = await p.$eval('#zs-menu', (e) => parseFloat(e.style.getPropertyValue('--fz-depth')));
    ok(d0 <= 0.05 && d1 > 0.8, `${site}: purple depth does not follow scroll (${d0} -> ${d1})`);

    // Phone Guy
    const calls0 = (await store(p)).fnaf.calls;
    await p.click('#ms-fz-answer'); await sleep(p, 2800);
    const txt = await p.$eval('#ms-fz-call', (e) => e.textContent.trim());
    ok(txt.length > 20 && !/^Press the button/.test(txt), `${site}: Phone Guy said nothing`);
    await sleep(p, 400);
    ok((await store(p)).fnaf.calls === calls0 + 1, `${site}: call counter`);

    // two more calls -> keycard -> Security Office opens
    for (let i = 0; i < 2; i++) {
      await p.waitForFunction(() => !document.querySelector('#ms-fz-answer').disabled, null, { timeout: 8000 });
      await p.click('#ms-fz-answer'); await sleep(p, 300);
    }
    await p.waitForSelector('#ms-fz-office', { timeout: 9000 });
    s = await store(p);
    ok(s.fnaf.calls === 3 && s.fnaf.office.ach.includes('keycard'), `${site}: keycard not granted after 3 calls ` + JSON.stringify(s.fnaf));
    ok(await p.$('[data-fz-ctl="doorL"]') && await p.$('[data-fz-cam="cove"]') && await p.$('#ms-fz-o-start'), `${site}: Security Office controls missing`);

    // easter egg unlocks Golden
    for (let i = 0; i < 5; i++) { await p.click('#ms-fz-eyes'); await sleep(p, 60); }
    await sleep(p, 500);
    s = await store(p);
    ok(s.fnaf.golden === true && s.fnaf.cast === 'golden', `${site}: eyes easter egg did not unlock Golden ` + JSON.stringify(s.fnaf));
    ok(!(await p.$('[data-fz-cast="golden"][disabled]')), `${site}: Golden still locked in the UI`);
    ok((await store(p)).fnaf.office.ach.includes('golden_eyes'), `${site}: eyes achievement missing`);

    // night shift toggle
    await p.click('label:has([data-fz-toggle=\"shift\"])'); await sleep(p, 400);
    ok((await store(p)).fnaf.shift === true, `${site}: shift toggle`);
    await sleep(p, 1300);
    ok(/AM$/.test(await p.$eval('#ms-fz-clock', (e) => e.textContent.trim())), `${site}: shift clock`);

    // motion none disables the drifting pizzas
    await p.click('[data-tab="look"]'); await p.click('[data-motion="none"]'); await sleep(p, 300);
    const anim = await p.$eval('.ms-fnaf-pizzas > *', (e) => getComputedStyle(e).animationName);
    ok(anim === 'none', `${site}: motion none should stop the pizzas (animation: ${anim})`);
    await p.click('[data-motion="full"]'); await sleep(p, 200);
    ok((await p.$eval('.ms-fnaf-pizzas > *', (e) => getComputedStyle(e).animationName)) !== 'none', `${site}: motion full should animate pizzas`);

    // Reset Backstage
    await p.click('[data-tab="backstage"]'); await sleep(p, 150);
    await p.click('#ms-fz-reset'); await sleep(p, 500);
    s = await store(p);
    ok(s.fnaf.golden === false && s.fnaf.calls === 0 && s.fnaf.pizzas > 0, `${site}: reset backstage ` + JSON.stringify(s.fnaf));

    // switching away removes layer + tab, falls back to Look
    await p.click('[data-tab="look"]'); await p.click('[data-theme="midnight"]'); await sleep(p, 500);
    ok(!(await tabs(p)).includes('backstage'), `${site}: Backstage tab remained after leaving the theme`);
    ok(!(await p.$('#zs-menu .ms-fnaf-layer')), `${site}: fnaf layer remained after leaving the theme`);
    ok(!(await p.$eval('#zs-menu', (e) => e.classList.contains('ms-fnaf-on'))), `${site}: ms-fnaf-on remained`);
    // leaving while on Backstage falls back to Look
    await p.click('[data-theme="fnaf"]'); await sleep(p, 300); await p.click('[data-tab="backstage"]'); await sleep(p, 150);
    await p.click('[data-tab="look"]'); await p.click('[data-theme="graphite"]'); await sleep(p, 300);
    ok(!(await tabs(p)).includes('backstage'), `${site}: Backstage visible again`);

    // bar theme
    await p.click('[data-tab="bar"]'); await p.selectOption('#ms-bar-theme', 'fnaf'); await sleep(p, 400);
    ok((await store(p)).barTheme === 'fnaf', `${site}: bar theme fnaf not stored`);
    ok(await p.$eval('#zs-bar', (e) => /fnaf/.test(e.outerHTML.slice(0, 600)) || getComputedStyle(e).backgroundImage !== 'none'), `${site}: bar not themed`);
    ok(!h.errors.length, `${site}: page errors ` + h.errors.join('; '));
    await h.close();
  }

  // hostile / legacy storage is sanitized and never breaks the menu
  const h = await open({ bridge: 'up', width: 1100, height: 900, theme: 'dark', storage: { msMenuPreferences: { theme: 'fnaf', fnaf: { cast: '<script>', pizzas: 9999, speed: -4, blur: 'x', tile: 99, glow: 1e9, golden: 'yes', nights: -3, calls: 'NaN', shift: 1 } } } });
  const p = h.page;
  await p.click('#zs-switch'); await sleep(p, 500);
  const pc = await p.$$eval('.ms-fnaf-pizzas > *', (a) => a.length);
  ok(pc >= 0 && pc <= 14, 'pizza count not clamped: ' + pc);
  await p.click('[data-tab="backstage"]'); await sleep(p, 200);
  const f = await p.evaluate(() => ({ pz: +document.querySelector('#ms-fz-pizzas').value, sp: +document.querySelector('#ms-fz-speed').value, bl: +document.querySelector('#ms-fz-blur').value, gl: +document.querySelector('#ms-fz-glow').value, tile: document.querySelector('#zs-menu').style.getPropertyValue('--fz-tile'), locked: !!document.querySelector('[data-fz-cast][disabled]'), html: document.querySelector('#zs-menu').innerHTML.includes('<script>') }));
  ok(f.pz <= 14 && f.sp >= 25 && f.sp <= 200 && f.bl >= 0 && f.bl <= 8 && f.gl >= 0 && f.gl <= 100, 'hostile values not clamped ' + JSON.stringify(f));
  ok(['18px', '24px', '32px'].includes(f.tile) && !f.html, 'hostile tile/cast not sanitized ' + JSON.stringify(f));
  ok(!h.errors.length, 'hostile storage produced errors: ' + h.errors.join('; '));
  await h.close();
  // Security Office game: driven with a fake clock + stubbed RNG so it is deterministic
  for (const site of ['notion', 'claude']) {
    const g = await open({ bridge: 'up', width: 1100, height: 900, theme: 'dark', site, storage: { msMenuPreferences: { theme: 'fnaf', fnaf: { calls: 3, office: { cleared: 0 } } } } });
    ok(g && !g.errors.length, `${site}: office harness failed`);
    const q = g.page;
    await q.click('#zs-switch'); await sleep(q, 400);
    await q.click('[data-tab="backstage"]'); await sleep(q, 200);
    ok(await q.$('#ms-fz-office'), `${site}: office should be open with a keycard in storage`);
    await q.evaluate(() => { window.__rnd = Math.random; Math.random = () => 0.99; });
    await q.clock.install();
    // Test the game timer rather than replaying 12,000 decorative RAF frames.
    // Real-time theme animation/layout is covered earlier in this same suite.
    await q.evaluate(()=>{window.requestAnimationFrame=fn=>setTimeout(()=>fn(performance.now()),1000);window.cancelAnimationFrame=clearTimeout;});
    await q.click('#ms-fz-o-start'); await sleep(q, 100);
    const st = () => q.$eval('#ms-fz-office', (e) => e.dataset.state);
    ok((await st()) === 'run', `${site}: night did not start`);
    ok(/first night/.test(await q.$eval('#ms-fz-o-msg', (e) => e.textContent)), `${site}: Phone Guy night-1 briefing missing`);
    const power = async () => parseInt((await q.$eval('#ms-fz-o-power', (e) => e.textContent)).replace(/\D/g, ''), 10);
    await q.clock.runFor(5000);
    const p1 = await power(); ok(p1 < 100 && p1 > 90, `${site}: power should drain slowly (${p1})`);
    const use = () => q.$$eval('#ms-fz-o-use i.on', (a) => a.length);
    ok((await use()) === 1, `${site}: base usage should be 1`);
    await q.click('[data-fz-ctl="doorL"]'); ok((await use()) === 2, `${site}: door adds usage`);
    ok(await q.$eval('[data-fz-ctl="doorL"]', (e) => e.getAttribute('aria-pressed') === 'true'), `${site}: door pressed state`);
    await q.click('[data-fz-ctl="lightL"]'); ok(/Empty hallway/.test(await q.$eval('#ms-fz-o-view', (e) => e.textContent)), `${site}: light view`);
    await q.click('[data-fz-ctl="lightR"]');
    ok(await q.$eval('[data-fz-ctl="lightL"]', (e) => e.getAttribute('aria-pressed') === 'false'), `${site}: lights should be exclusive`);
    await q.click('[data-fz-cam="cove"]'); ok(/Cove/.test(await q.$eval('#ms-fz-o-view', (e) => e.textContent)) && (await q.$eval('#ms-fz-screen', (e) => e.dataset.mode)) === 'cam', `${site}: camera view`);
    await q.focus('#ms-fz-office'); await q.keyboard.press('a'); ok(await q.$eval('[data-fz-ctl="doorL"]', (e) => e.getAttribute('aria-pressed') === 'false'), `${site}: key A should toggle the left door`);
    await q.keyboard.press('c'); ok((await q.$eval('#ms-fz-screen', (e) => e.dataset.mode)) !== 'cam', `${site}: key C should toggle the camera off`);
    for (const id of ['doorL', 'doorR', 'lightL', 'lightR', 'cam']) if (await q.$eval(`[data-fz-ctl="${id}"]`, (e) => e.getAttribute('aria-pressed') === 'true')) await q.click(`[data-fz-ctl="${id}"]`);
    await q.clock.runFor(100000); await sleep(q, 100);
    ok((await st()) === 'won', `${site}: night should be won (state ${await st()})`);
    let sv = JSON.parse(JSON.stringify(await q.evaluate(() => window.__store.msMenuPreferences)));
    ok(sv.fnaf.office.cleared === 1 && sv.fnaf.office.wins === 1 && sv.fnaf.golden === true && sv.fnaf.office.ach.includes('first_night'), `${site}: win not recorded ` + JSON.stringify(sv.fnaf));
    ok((await q.$$eval('.ms-fz-ach.got', (a) => a.length)) >= 1 && /Next night/.test(await q.$eval('#ms-fz-o-start', (e) => e.textContent)), `${site}: win UI`);
    ok((await q.$$eval('#ms-fz-o-sel option', (a) => a.length)) === 2, `${site}: night 2 should be selectable`);
    ok(!(await q.$('[data-fz-cast="golden"][disabled]')), `${site}: Golden should open after clearing Night 1`);
    // night 2 with everyone moving every tick and a player who does nothing: a loss
    await q.evaluate(() => { Math.random = () => 0; });
    await q.click('#ms-fz-o-start'); await sleep(q, 100);
    ok((await st()) === 'run', `${site}: night 2 did not start`);
    await q.clock.runFor(90000); await sleep(q, 100);
    ok((await st()) === 'dead', `${site}: an idle player should lose (state ${await st()})`);
    ok(await q.$('.ms-fz-face'), `${site}: game-over screen missing`);
    sv = JSON.parse(JSON.stringify(await q.evaluate(() => window.__store.msMenuPreferences)));
    ok(sv.fnaf.office.deaths === 1 && sv.fnaf.office.cleared === 1, `${site}: loss not recorded ` + JSON.stringify(sv.fnaf.office));
    // abandon and restart never leaves a runaway timer
    await q.click('#ms-fz-o-start'); await sleep(q, 100); ok((await st()) === 'run', `${site}: restart`);
    await q.click('#ms-fz-o-start'); await sleep(q, 150);
    ok((await q.$eval('#ms-fz-office', (e) => e.dataset.state)) === 'idle', `${site}: abandon should return to idle`);
    // leaving the theme mid-night stops the game without errors
    await q.click('#ms-fz-o-start'); await sleep(q, 100);
    await q.click('[data-tab="look"]'); await q.click('[data-theme="midnight"]'); await sleep(q, 300);
    await q.clock.runFor(5000);
    ok(!g.errors.length, `${site}: office produced page errors ` + g.errors.join('; '));
    await g.close();
  }
  console.log('PASS fnaf theme (layer, aligned tile bands, Backstage tab gating, pizzas, depth, cast, Phone Guy, keycard, Security Office game, curtain intro, easter egg, motion, reset, bar theme; notion + claude)');
  process.exit(0);
})().catch((e) => { console.error('FAIL', e.message); process.exit(1); });
