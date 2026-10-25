const fs = require('fs');
const path = require('path');
const pw = require('./playwright-env');
const main = fs.readFileSync(path.join(__dirname, '..', 'extension/core/main.js'), 'utf8');
const ok = (x, m) => { if (!x) throw new Error(m); };

for (const needle of [
  '<button type="button" id="ms-idea-go"',
  '<button type="button" id="ms-idea-copy"',
  '<button type="button" id="ms-idea-insert"',
  'e.preventDefault(); e.stopPropagation();',
  'generator returned an incomplete idea',
  'role="status" aria-live="polite"',
  'function neutralizeFormButtons(scope)',
  'neutralizeFormButtons(menuEl)',
]) ok(main.includes(needle), 'missing Game Idea UI guard: ' + needle);

(async () => {
  const browser = await pw.launch();
  if (!browser) {
    console.log('PASS Game Idea UI guards (browser unavailable; DOM test skipped)');
    return;
  }
  const {open} = require('../tools/studio_harness');
  const h = await open({bridge:'up', width:900, height:760, theme:'dark'});
  ok(h && !h.errors.length, 'harness failed: ' + (h && h.errors.join('; ')));
  await h.page.click('#zs-switch');
  await h.page.click('[data-tab="ideas"]');
  // Reparent the entire extension root into a form to reproduce providers whose
  // composer/docking container makes untyped overlay buttons submit the chat.
  await h.page.evaluate(() => {
    const form = document.querySelector('form');
    window.__ideaSubmits = 0;
    form.addEventListener('submit', e => { e.preventDefault(); window.__ideaSubmits++; });
    form.appendChild(document.querySelector('#zs-root'));
  });
  await h.page.click('#ms-idea-go');
  const state = await h.page.evaluate(() => ({
    submits: window.__ideaSubmits,
    title: document.querySelector('#ms-idea-title').textContent,
    prompt: document.querySelector('#ms-idea-out').value,
    disabled: document.querySelector('#ms-idea-go').disabled,
    copyDisabled: document.querySelector('#ms-idea-copy').disabled,
  }));
  ok(state.submits === 0, 'Generate submitted the provider chat form');
  ok(state.title && !/error/i.test(state.title), 'idea title missing: ' + state.title);
  ok(state.prompt.length > 300 && state.prompt.includes('ACCEPTANCE TESTS:'), 'idea prompt missing');
  ok(!state.disabled && !state.copyDisabled, 'buttons did not recover/enable');
  ok(!h.errors.length, 'page errors: ' + h.errors.join('; '));
  await h.close();
  console.log('PASS Game Idea button works inside provider forms without submitting chat');
})().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });