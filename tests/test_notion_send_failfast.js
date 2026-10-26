// SPDX-License-Identifier: GPL-3.0-or-later
// 6.25.1 regression: "Notion AI doesn't send a message and Starting… loads forever".
//
// Pins, in real Chromium with the real content-script chain on a mock Notion chat:
//   1. a healthy composer starts the chat studio (text lands, Send registers, reply read);
//   2. a composer that ignores Send, or wipes the text, FAILS FAST (< 45 s) with a
//      "Message could not be sent" banner carrying composer diagnostics;
//   3. a failed send never ends in a false "Chat studio active" and never leaves the
//      bar stuck on "Starting…".
const h = require('../tools/studio_harness');
let passed = 0;
const ok = (c, m) => { if (!c) throw new Error('FAIL ' + m); passed++; console.log('PASS ' + m); };

async function run(mode, maxMs) {
  const x = await h.open({ bridge: 'up', host: 'installed', theme: 'dark', width: 1134, height: 834, layout: 'empty-tall', stateHook:true });
  if (!x) return null;
  const { page } = x;
  await page.evaluate((mode) => {
    document.querySelector('form').addEventListener('submit', (e) => e.preventDefault());
    const ed = document.getElementById('agent-editor'), send = document.getElementById('send');
    const thread = document.querySelector('.thread') || document.body;
    document.querySelectorAll('.msg').forEach((n) => n.remove());
    let state = '',sends=0;
    const sync = () => { send.disabled = !state.trim(); };
    ed.addEventListener('input', (e) => {
      if (mode === 'refuse') { ed.textContent = ''; return; }
      if (e.isTrusted) state = ed.textContent;   // like a real app: only genuine input registers
      sync();
    });
    sync();
    const turn = (cls, side, txt) => { const d = document.createElement('div'); d.className = 'msg ' + cls; d.setAttribute('data-testid',cls==='u'?'user-message':'agent-message');d.setAttribute('data-message-id',cls+Date.now()); d.setAttribute('data-agent-service-scroll-anchor', cls + Date.now()); d.style.cssText = 'display:flex;justify-content:' + side; d.textContent = txt; thread.appendChild(d); };
    send.addEventListener('click', () => {
      if (send.disabled || mode === 'dead') return;
      const step=++sends;turn('u', 'flex-end', state.slice(0, 40)); ed.textContent = ''; state = ''; sync();
      setTimeout(() => turn('a', 'flex-start', step===1?'{"command":"list_commands","params":{}}':'Ready. Studio profile loaded.'), 700);
    });
  }, mode);
  await page.waitForTimeout(300);
  await page.click('#zs-chat-only');
  const t0 = Date.now();
  let st = '';
  while (Date.now() - t0 < maxMs) {
    await page.waitForTimeout(500);
    st = await page.evaluate(() => (document.querySelector('#zs-bar')?.innerText || '').replace(/\s+/g, ' '));
    if (!await page.evaluate(()=>__qa.A.starting)) break;
  }
  const elapsed = Date.now() - t0;
  const banners = await page.evaluate(() => [...document.querySelectorAll('.zs-banner')].map((e) => e.innerText.replace(/\s+/g, ' ')));
  const out = { st, elapsed, banners, errors: x.errors };
  await x.close();
  return out;
}

(async () => {
  const good = await run('ok', 40000);
  if (!good) { console.log('SKIP notion send fail-fast (no browser available)'); return; }
  if(!/Chat studio active/.test(good.st)||good.banners.length)console.error(JSON.stringify(good));
  ok(/Chat studio active/.test(good.st) && good.banners.length === 0, 'healthy composer: chat studio starts with no warning (' + Math.round(good.elapsed / 1000) + 's)');
  for (const mode of ['dead', 'refuse']) {
    const r = await run(mode, 60000);
    ok(!/Starting/.test(r.st) && r.elapsed < 45000, `${mode}: Starting… ends in ${Math.round(r.elapsed / 1000)}s instead of spinning`);
    ok(r.banners.some((b) => /Message could not be sent/.test(b) && /Details:|Reason:/.test(b)), `${mode}: banner explains the failure and carries composer diagnostics`);
    ok(!/Chat studio active/.test(r.st), `${mode}: never reports a false "Chat studio active"`);
    ok(r.errors.length === 0, `${mode}: no page errors`);
  }
  console.log(`PASS notion send fail-fast (${passed} checks)`);
})().catch((e) => { console.error(e.message || e); process.exit(1); });
