// Behavioural test for the Memory button's menu + controller (core/memory.js).
// Runs the real classes in a real browser against a fake worker that mimics the
// bridge's `memory` ops, so state handling, prompt injection and the menu's
// create / use / toggle / settings / browse / graph flows are exercised for real.
const pw = require('./playwright-env');
const fs = require('fs');

pw.guard('memory panel');

(async () => {
  const browser = await pw.launch();
  if (!browser) pw.skip('memory panel', 'no Chromium available');
  const page = await browser.newPage();
  await page.route('**/*', (r) => r.fulfill({ contentType: 'text/html', body: '<div id="page"></div>' }));
  await page.goto('http://ms.test/memory');
  await page.addScriptTag({ content: fs.readFileSync('extension/core/memory.js', 'utf8') });

  const out = await page.evaluate(async () => {
    const results = [];
    const ok = (name, cond, note) => results.push([name, !!cond, note === undefined ? '' : String(note)]);
    const store = {};
    window.chrome = { storage: { local: { get: (k, cb) => cb({ [k]: store[k] }), set: (o) => Object.assign(store, JSON.parse(JSON.stringify(o))) } } };

    // fake bridge
    const mems = {};
    const calls = [];
    const worker = async (m) => {
      calls.push(m.op);
      const a = m.args || {};
      if (m.op === 'list') return { ok: true, memories: Object.values(mems).map((x) => ({ id: x.id, name: x.name, nodes: x.nodes.length, edges: 0, settings: x.settings })) };
      if (m.op === 'create') { const id = a.name.toLowerCase().replace(/\W+/g, '-'); mems[id] = { id, name: a.name, nodes: [], settings: { autoRecall: true, autoCapture: true, includeEpisodes: true, maxContextChars: 3500, maxNodes: 4000 } }; return { ok: true, created: { id, name: a.name } }; }
      if (m.op === 'open') { const x = mems[a.memory]; return x ? { ok: true, active: { id: x.id, name: x.name, nodes: x.nodes.length, settings: x.settings } } : { ok: false, error: 'no memory' }; }
      if (m.op === 'context') return { ok: true, text: '- [preference] Use classic grey GUI' };
      if (m.op === 'settings') { const x = mems[a.memory]; if (a.settings) Object.assign(x.settings, a.settings); return { ok: true, settings: x.settings }; }
      if (m.op === 'graph' && a.action === 'list') return { ok: true, nodes: [{ id: 'n1', kind: 'preference', name: 'Classic GUI', text: 'grey', tags: [], links: ['-about-> MainMenu'], pinned: false, importance: 0.8 }] };
      if (m.op === 'graph') return { ok: true, nodes: [{ id: 'n1', kind: 'preference', name: 'Classic GUI', importance: 0.8 }, { id: 'n2', kind: 'entity', name: 'MainMenu', importance: 0.5 }], edges: [{ a: 'n1', b: 'n2', rel: 'about' }] };
      if (m.op === 'observe') { mems[a.memory].observed = a; return { ok: true, captured: 2 }; }
      if (m.op === 'update') return { ok: true };
      return { ok: true };
    };

    let key = '';
    let changes = 0;
    const C = new window.ZSMemory.MemoryController({ bg: worker, providerId: 'chatgpt', conversationKey: () => key, onChange: () => { changes++; } });
    await new Promise((r) => setTimeout(r, 10));
    ok('starts OFF', !C.isOn() && C.promptBlock() === '');

    const mount = document.createElement('div');
    const anchor = document.createElement('button'); anchor.id = 'zs-mem'; anchor.style.cssText = 'position:fixed;left:300px;top:400px;width:28px;height:28px';
    document.body.append(mount, anchor);
    const P = new window.ZSMemory.MemoryPanel({ mount, controller: C, anchor: () => anchor, ui: { toast: () => {}, onChange: () => {} } });
    await P.openPanel();
    const el = document.getElementById('zs-mem-panel');
    ok('panel opens and is docked', el && !el.hidden && P.isOpen());
    ok('empty state explains creating one', /No memories yet/.test(el.textContent));

    // create
    el.querySelector('[data-f="newname"]').value = 'Roblox classic gui';
    el.querySelector('[data-f="newname"]').dispatchEvent(new Event('input', { bubbles: true }));
    el.querySelector('[data-act="create"]').click();
    await new Promise((r) => setTimeout(r, 30));
    ok('create lists the new memory', /Roblox classic gui/.test(el.textContent), el.textContent.slice(0, 200));

    // use here => ON with prompt block
    el.querySelector('[data-act="use"]').click();
    await new Promise((r) => setTimeout(r, 30));
    ok('use turns memory ON', C.isOn() && C.memoryRef() === 'roblox-classic-gui');
    const block = C.promptBlock();
    ok('prompt block names the memory + tools + notes', /GRAPH MEMORY: "Roblox classic gui"/.test(block) && /ms_memory_recall/.test(block) && /classic grey GUI/.test(block), block.slice(0, 120));
    ok('state persisted for pending chat', store.msMemoryState && store.msMemoryState.pending.on === true);

    // bind to real conversation key once the chat has an id
    key = 'c/abc';
    C.bind();
    ok('pending ON follows the new chat id', C.isOn() && !!store.msMemoryState.sessions['chatgpt|c/abc'] && store.msMemoryState.pending.on === false);
    key = 'c/other';
    ok('another chat is OFF', !C.isOn());
    key = 'c/abc';
    ok('first chat still ON', C.isOn());

    // toggle off through the switch
    const sw = el.querySelector('[data-act="toggle"]');
    sw.checked = false; sw.dispatchEvent(new Event('change', { bubbles: true }));
    await new Promise((r) => setTimeout(r, 30));
    ok('switch turns OFF', !C.isOn() && C.promptBlock() === '');
    const sw2 = el.querySelector('[data-act="toggle"]');
    sw2.checked = true; sw2.dispatchEvent(new Event('change', { bubbles: true }));
    await new Promise((r) => setTimeout(r, 30));
    ok('switch turns ON with last memory', C.isOn() && C.memoryRef() === 'roblox-classic-gui');

    // settings tab
    el.querySelector('[data-tab="settings"]').click();
    await new Promise((r) => setTimeout(r, 10));
    const cb = el.querySelector('[data-set="autoCapture"]');
    cb.checked = false; cb.dispatchEvent(new Event('change', { bubbles: true }));
    await new Promise((r) => setTimeout(r, 30));
    ok('settings persisted via bridge', mems['roblox-classic-gui'].settings.autoCapture === false);
    const before = calls.filter((c) => c === 'observe').length;
    const r1 = await C.observe({ user: 'hi', assistant: 'ok', tools: [] });
    ok('auto-capture OFF => no observe call', r1 === null && calls.filter((c) => c === 'observe').length === before);
    mems['roblox-classic-gui'].settings.autoCapture = true;
    const r2 = await C.observe({ user: 'I prefer grey', assistant: 'done', tools: ['ms_roblox_ui_kit'] });
    ok('auto-capture ON => observe sent', r2 && r2.ok && mems['roblox-classic-gui'].observed.tools[0] === 'ms_roblox_ui_kit');

    // browse + graph
    el.querySelector('[data-tab="browse"]').click();
    await new Promise((r) => setTimeout(r, 60));
    ok('browse lists nodes', /Classic GUI/.test(el.textContent));
    el.querySelector('[data-tab="graph"]').click();
    await new Promise((r) => setTimeout(r, 60));
    ok('graph draws svg nodes', el.querySelectorAll('.zs-mem-graph circle').length === 2 && el.querySelectorAll('.zs-mem-graph line').length === 1);

    // tool filter helpers
    ok('isMemoryTool matches only memory tools', window.ZSMemory.isMemoryTool('ms_memory_recall') && !window.ZSMemory.isMemoryTool('ms_memory_budget_optimizer') && !window.ZSMemory.isMemoryTool('ms_sequential_thinking'));
    // XSS safety
    mems['roblox-classic-gui'].name = '<img src=x onerror=window.__xss=1>';
    await P._reload(); el.querySelector('[data-tab="memories"]').click();
    ok('names are escaped', !window.__xss && !el.querySelector('img'));
    P.close();
    ok('close hides', el.hidden && !P.isOpen());
    return results;
  });
  let failed = 0;
  for (const [name, good, note] of out) { console.log((good ? 'PASS ' : 'FAIL ') + name + (good || !note ? '' : ' :: ' + note)); if (!good) failed++; }
  await browser.close();
  console.log(`\n${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
