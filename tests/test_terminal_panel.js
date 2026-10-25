// Behavioural test for the in-chat bridge terminal panel (core/terminal.js).
//
// The panel is the newest and most intricate piece in this release, and the
// parts that matter are all stateful: the seq cursor that makes an idle poll
// incremental, the dedupe that stops a socket push and a snapshot from
// double-printing the same line, the reset that a bridge restart must trigger,
// and the autoscroll that must not fight a user reading history. String-level
// assertions cannot check any of that, so this drives the real class in a real
// browser against a fake worker.
const pw = require('./playwright-env');
const fs = require('fs');

pw.guard('terminal panel');

(async () => {
  const browser = await pw.launch();
  if (!browser) pw.skip('terminal panel', 'no Chromium available');

  const page = await browser.newPage();
  await page.route('**/*', (r) => r.fulfill({ contentType: 'text/html', body: '<div id="page"></div>' }));
  await page.goto('http://ms.test/terminal');
  await page.addScriptTag({
    content: fs.readFileSync('extension/core/terminal.js', 'utf8') + ';window.__T=window.ZSTerminal;',
  });

  const out = await page.evaluate(async () => {
    const results = [];
    const ok = (name, cond, note) => { results.push([name, !!cond, note === undefined ? '' : String(note)]); };

    // ── a fake worker that answers terminal_snapshot from an in-memory ring ──
    // It records every `since` it was asked for, so the cursor behaviour can be
    // asserted rather than assumed.
    const ring = [];
    let seq = 0;
    const asked = [];
    const add = (msg, level) => { seq += 1; ring.push({ seq, t: '00:00:00', level: level || 'info', msg }); return seq; };

    const worker = async (m) => {
      if (m.type === 'terminal_snapshot') {
        const since = Number(m.since) || 0;
        asked.push(since);
        let lines = ring.filter((r) => r.seq > since);
        const newest = seq;
        lines = lines.slice(-(m.limit || 400));
        return { ok: true, via: 'ws', lines, newest, service: { bridgeVersion: '6.28.1', port: 17613, servers: [{ id: 'roblox', alive: true, tools: 42 }], ringSize: ring.length, ringMax: 600 } };
      }
      if (m.type === 'terminal_clear') return { ok: true };
      return { ok: false };
    };

    const mount = document.createElement('div');
    document.body.appendChild(mount);

    // The panel is created via window.ZSTerminal.TerminalPanel.
    const Panel = window.__T.TerminalPanel;
    ok('TerminalPanel is exported', typeof Panel === 'function');

    const p = new Panel({ mount, bg: worker, getStatus: () => ({ connected: true }), ui: {} });

    // ── open: paints the backlog and records the service picture ─────────────
    add('engine connect: roblox', 'ok');
    add('tool call ms_native_read', 'info');
    add('handshake failed', 'error');
    await p.openPanel();
    ok('openPanel renders', p.isOpen());
    ok('backlog rendered', p.lines.length === 3, p.lines.length);
    ok('first snapshot asked from 0', asked[0] === 0, asked[0]);
    ok('service snapshot stored', p.service && p.service.bridgeVersion === '6.28.1');
    ok('service chips painted', /roblox/.test(document.querySelector('.zs-term-services').textContent));

    // ── cursor: an idle poll must be incremental, not a re-read ──────────────
    ok('cursor advanced to newest', p.cursor === 3, p.cursor);
    await p.refresh();
    ok('idle poll asks from the cursor', asked[asked.length - 1] === 3, asked[asked.length - 1]);
    ok('idle poll adds nothing', p.lines.length === 3, p.lines.length);

    // ── a pushed line advances the cursor and does not duplicate the snapshot ─
    const s4 = add('pushed line', 'warn');
    p.push(ring.filter((r) => r.seq === s4));
    ok('push rendered', p.lines.length === 4, p.lines.length);
    ok('push advanced the cursor', p.cursor === 4, p.cursor);
    await p.refresh();
    ok('poll after push asks from the push', asked[asked.length - 1] === 4, asked[asked.length - 1]);
    ok('no duplicate after push+poll', p.lines.length === 4, p.lines.length);

    // ── the same line delivered twice (push racing a snapshot) prints once ───
    p.push(ring.filter((r) => r.seq === s4));
    ok('re-delivered push is deduped', p.lines.length === 4, p.lines.length);

    // ── level filter ────────────────────────────────────────────────────────
    p.filter = 'error';
    p._paintLines();
    const rendered = document.querySelectorAll('.zs-term-line').length;
    ok('error filter shows only the error line', rendered === 1, rendered);
    p.filter = 'all';
    p._paintLines();
    ok('all filter restores every line', document.querySelectorAll('.zs-term-line').length === 4);

    // ── lines are rendered as TEXT, never as HTML ───────────────────────────
    const evil = '<img src=x onerror="window.__XSS=1">';
    const s5 = add(evil, 'info');
    p.push(ring.filter((r) => r.seq === s5));
    ok('an HTML-looking log line is not executed', !window.__XSS);
    ok('an HTML-looking log line is shown verbatim',
      document.querySelector('.zs-term-body').textContent.includes('onerror'));

    // ── clear empties the view but keeps the cursor (bridge keeps counting) ──
    const beforeClear = p.cursor;
    p.cleared();
    ok('clear empties the view', p.lines.length === 0, p.lines.length);
    ok('clear keeps the cursor', p.cursor === beforeClear, p.cursor);
    await p.refresh();
    ok('poll after clear asks from the kept cursor', asked[asked.length - 1] === beforeClear, asked[asked.length - 1]);

    // ── reset (bridge restart) rewinds the cursor and re-reads ──────────────
    p.reset();
    ok('reset rewinds the cursor', p.cursor === 0, p.cursor);
    ok('reset drops the stale service picture', p.service === null);
    await new Promise((r) => setTimeout(r, 60));
    ok('reset re-reads from 0', asked[asked.length - 1] === 0 || p.pending === null);

    // ── autoscroll only follows when the user is at the bottom ──────────────
    // A real browser will not let scrollTop be set past the real scroll range of
    // a non-scrollable element (it clamps back to 0), so drive the handler with
    // the three values it actually reads instead of trying to scroll for real.
    p.autoscroll = true;
    const body = document.querySelector('.zs-term-body');
    let fakeTop = 800;
    Object.defineProperty(body, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(body, 'clientHeight', { value: 200, configurable: true });
    Object.defineProperty(body, 'scrollTop', { get: () => fakeTop, set: () => {}, configurable: true });
    body.dispatchEvent(new Event('scroll'));
    ok('at the bottom, autoscroll stays on', p.autoscroll === true, 'scrollTop=' + body.scrollTop);
    fakeTop = 100; // scrolled up to read history
    body.dispatchEvent(new Event('scroll'));
    ok('scrolled up, autoscroll turns off', p.autoscroll === false, 'scrollTop=' + body.scrollTop);

    // ── the request guard prevents two snapshots in flight ─────────────────
    let inflight = 0, maxInflight = 0;
    const slow = async (m) => {
      if (m.type !== 'terminal_snapshot') return { ok: true };
      inflight++; maxInflight = Math.max(maxInflight, inflight);
      await new Promise((r) => setTimeout(r, 25));
      inflight--;
      return { ok: true, via: 'ws', lines: [], newest: p.cursor, service: null };
    };
    const p2 = new Panel({ mount, bg: slow, getStatus: () => ({ connected: true }), ui: {} });
    await Promise.all([p2.refresh(), p2.refresh(), p2.refresh()]);
    ok('overlapping refreshes coalesce to one request', maxInflight === 1, maxInflight);

    // ── a dead bridge reports "down" rather than throwing ──────────────────
    // NOTE: each panel must get its OWN mount, or querySelector will find an
    // earlier panel's body and the assertions read the wrong panel's output.
    const deadMount = document.createElement('div');
    document.body.appendChild(deadMount);
    const dead = new Panel({ mount: deadMount, bg: async () => ({ ok: false, kind: 'unreachable' }), getStatus: () => ({ connected: false }), ui: {} });
    await dead.openPanel();
    ok('a dead bridge does not throw', dead._transport === 'down', dead._transport);
    ok('a dead bridge shows an empty-state, not a crash',
      /Waiting for the bridge/.test(deadMount.querySelector('.zs-term-body').textContent),
      deadMount.querySelector('.zs-term-body').textContent.slice(0, 60));

    // ── no flicker: identical data must not rebuild the DOM ───────────────────
    const stableMount = document.createElement('div');
    document.body.appendChild(stableMount);
    const sp = new Panel({ mount: stableMount, bg: worker, getStatus: () => ({ connected: true }), ui: {} });
    await sp.openPanel();
    const firstRow = stableMount.querySelector('.zs-term-line');
    await sp.refresh(); await sp.refresh();
    ok('an unchanged poll keeps the same log rows (no repaint)', firstRow && stableMount.querySelector('.zs-term-line') === firstRow);
    const chip = stableMount.querySelector('.zs-term-svc');
    sp._paintServices();
    ok('unchanged engine chips are not rebuilt', chip && stableMount.querySelector('.zs-term-svc') === chip);
    sp.showTab('running', true);
    const runRow = stableMount.querySelector('.zs-run-row');
    sp._paintRunning(); sp._paintRunning();
    ok('the Running list is not rebuilt when nothing changed', runRow && stableMount.querySelector('.zs-run-row') === runRow);
    stableMount.querySelector('.zs-term-body').scrollTop = 0;
    sp.showTab('log', true);
    await new Promise((r) => setTimeout(r, 320));
    ok('slide-in class is removed after opening (no replay on re-attach)', !stableMount.querySelector('#zs-term').classList.contains('zs-term-enter'));
    const note = () => sp.lines.filter((l) => l.level === 'note').length;
    sp._appendLocal('same note'); const n1 = note(); sp._appendLocal('same note');
    ok('an identical local note is not repeated', note() === n1);
    sp.close();

    // ── close stops the poll timer (no leak after the panel is dismissed) ───
    p.close();
    ok('close clears the poll timer', !p.pollTimer, p.pollTimer);

    return { results };
  });

  let failed = 0;
  for (const [name, cond, note] of out.results) {
    if (!cond) { failed++; console.error('  FAIL ' + name + (note ? '  [' + note + ']' : '')); }
  }
  if (failed) {
    console.error(`FAIL terminal panel: ${out.results.length - failed} passed, ${failed} failed`);
    await browser.close();
    process.exit(1);
  }
  console.log(`PASS in-chat terminal panel: ${out.results.length} behavioural assertions (backlog, incremental cursor, push dedupe, filter, text-only rendering, clear vs reset, autoscroll, request coalescing, dead bridge, timer cleanup)`);
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
