// SPDX-License-Identifier: GPL-3.0-or-later
// Media relay (browser side) contract.
//
// This module is the one place a content script hands a user's own file to the
// local bridge. The rules that matter are therefore about SAFETY and HONESTY:
//
//   1. an unsupported or oversized file is refused BEFORE it is uploaded
//   2. the bridge's response is mapped into the providers' exact payload shape
//   3. the bytes actually shipped are the bytes actually read
//   4. a video that yields no frames is reported honestly, not as success
//   5. a dead bridge surfaces as an actionable sentence, never a hang
//   6. the manifest is ADDITIVE - the user's own words are never replaced
//   7. the module and the bridge agree on the routes, port and caps
//
// The module talks to the network through `fetch` and reads files through
// `FileReader`. Both are stubbed so the whole flow runs in-process.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');

let passed = 0;
const ok = (c, m) => { if (!c) throw new Error(m); };

// ── harness ──────────────────────────────────────────────────────────────
let requests = [];
let fetchImpl = null;

function makeFile(name, type, size) {
  return { name, type, size, __marker: Buffer.from('bytes:' + name).toString('base64') };
}

globalThis.FileReader = class {
  readAsDataURL(file) {
    this.result = 'data:' + (file.type || 'application/octet-stream') + ';base64,' + file.__marker;
    // Content scripts observe FileReader resolving asynchronously; match that so
    // the module's await ordering is genuinely exercised.
    setTimeout(() => this.onload && this.onload(), 0);
  }
};
globalThis.fetch = async (url, init) => {
  requests.push({ url, method: (init && init.method) || 'GET', body: init && init.body });
  return fetchImpl(url, init);
};
const last5 = (route) => requests.filter((r) => r.url.endsWith(route)).pop();

function jsonResponse(status, obj) {
  return { ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(obj) };
}

function happyBridge(prepareOverride) {
  return async (url) => {
    if (url.endsWith('/media/stage')) {
      return jsonResponse(200, { ok: true, item: { id: 'abc123', kind: 'image', mime: 'image/png', name: 'shot.png', bytes: 66 } });
    }
    if (url.endsWith('/media/prepare')) {
      const base = {
        id: 'abc123', kind: 'image', mime: 'image/png', name: 'shot.png', bytes: 66,
        payloads: [{ kind: 'image', mime: 'image/png', name: 'shot.png', dataUrl: 'data:image/png;base64,QUJD' }],
        manifest: 'MEDIA RELAY\nThe user attached an image file.\n- name: shot.png',
        note: 'one image is ready to paste into the composer',
      };
      return jsonResponse(200, { ok: true, prepared: Object.assign(base, prepareOverride || {}) });
    }
    if (url.endsWith('/media/release')) return jsonResponse(200, { ok: true, released: 1 });
    return jsonResponse(404, { error: 'not found' });
  };
}

const ZSMediaRelay = new Function(read('extension/core/media-relay.js') + ';return ZSMediaRelay;')();

const tests = [];
const t = (name, fn) => tests.push({ name, fn });

// ── 1. classification & refusals happen before any upload ────────────────
t('an unsupported or oversized file is refused before it is uploaded', () => {
  ok(ZSMediaRelay.classify(makeFile('a.png', 'image/png', 10)) === 'image', 'png must classify as image');
  ok(ZSMediaRelay.classify(makeFile('a.mp4', 'video/mp4', 10)) === 'video', 'mp4 must classify as video');
  ok(ZSMediaRelay.classify(makeFile('a.exe', 'application/octet-stream', 10)) === 'unknown', 'exe must be unknown');
  ok(ZSMediaRelay.classify(makeFile('a.webm', '', 10)) === 'video', 'extension fallback for webm');
  const big = makeFile('big.mp4', 'video/mp4', ZSMediaRelay.MAX_UPLOAD_BYTES + 1);
  ok(/accepts up to/.test(ZSMediaRelay.rejectionFor(big) || ''), 'oversized must be refused with the limit in words');
  ok(ZSMediaRelay.rejectionFor(makeFile('a.exe', '', 10)) !== null, 'unknown type must be refused');
  ok(ZSMediaRelay.rejectionFor(makeFile('a.png', 'image/png', 0)) !== null, 'empty must be refused');
  ok(ZSMediaRelay.rejectionFor(makeFile('a.png', 'image/png', 10)) === null, 'a good file must pass');
});

// ── 2. relayFile maps the bridge into the providers' payload shape ───────
t('relayFile maps the bridge response into the providers payload shape', async () => {
  fetchImpl = happyBridge();
  const r = await ZSMediaRelay.relayFile(makeFile('shot.png', 'image/png', 66));
  ok(r.ok === true, 'a happy relay must succeed');
  ok(r.kind === 'image', 'kind must be image');
  ok(r.payloads.length === 1, 'one payload expected');
  const p = r.payloads[0];
  // Providers consume {mimeType, data} with BARE base64 (no data: prefix).
  ok(p.mimeType === 'image/png', 'payload mimeType must be carried');
  ok(p.data === 'QUJD', 'payload data must be bare base64, got ' + JSON.stringify(p.data));
  ok(r.manifest.length > 0, 'the manifest must be carried');
});

// ── 3. the staged bytes are what the module actually read ────────────────
t('the bytes shipped to the bridge are the bytes read from the file', async () => {
  fetchImpl = happyBridge();
  requests = [];
  await ZSMediaRelay.relayFile(makeFile('shot.png', 'image/png', 66));
  const staged = last5('/media/stage');
  ok(staged, 'the stage route must be called');
  const body = JSON.parse(staged.body);
  ok(body.name === 'shot.png' && body.mime === 'image/png', 'the name and mime must be sent');
  ok(body.dataUrl === Buffer.from('bytes:shot.png').toString('base64'), 'the base64 payload must be exact');
  ok(!String(body.dataUrl).startsWith('data:'), 'the data: prefix must not be forwarded');
  // The module's own ordering is part of the contract: stage, then prepare.
  const order = requests.map((r) => r.url.replace(/^.*\/media\//, ''));
  ok(order[0] === 'stage' && order[1] === 'prepare', 'stage must precede prepare, got ' + order.join(','));
});

// ── 4. a video with no frames is an honest partial, not a success ────────
t('a video that yields no frames is reported honestly', async () => {
  fetchImpl = happyBridge({
    kind: 'video', mime: 'video/mp4', name: 'glitch.mp4',
    payloads: [],
    note: 'no frames were extracted because ffmpeg is not installed; the manifest below still describes the clip',
    manifest: 'MEDIA RELAY\nThe user attached a video file.\n- relay note: no frames were extracted because ffmpeg is not installed',
  });
  const r = await ZSMediaRelay.relayFile(makeFile('glitch.mp4', 'video/mp4', 1000));
  ok(r.ok === false, 'a frame-less video must NOT report success');
  ok(r.kind === 'video', 'the kind is still video');
  ok(/ffmpeg is not installed/.test(r.emptyReason), 'the real reason must be surfaced');
  ok(r.payloads.length === 0, 'no payloads must be claimed');
  ok(/video file/.test(r.manifest), 'the manifest must still describe the clip');
  ok(/ffmpeg/.test(r.manifest), 'the manifest must carry the reason too');
  ok(/ffmpeg/.test(ZSMediaRelay.describeOutcome(r)), 'the user-facing line must carry the real reason');
});

// ── 5. a dead bridge is an actionable sentence, not a hang ──────────────
t('a dead bridge surfaces as an actionable sentence', async () => {
  fetchImpl = async () => { throw new TypeError('Failed to fetch'); };
  let msg = '';
  try { await ZSMediaRelay.relayFile(makeFile('shot.png', 'image/png', 66)); }
  catch (e) { msg = String(e.message || e); }
  ok(/bridge/i.test(msg), 'the error must name the bridge: ' + msg);
  ok(/start|running/i.test(msg), 'the error must say what to do: ' + msg);
});

// ── 6. a bridge-side refusal is forwarded verbatim ──────────────────────
t('a bridge-side refusal is forwarded verbatim', async () => {
  fetchImpl = async () => jsonResponse(400, { error: 'that file is not a supported photo or video' });
  let msg = '';
  try { await ZSMediaRelay.relayFile(makeFile('shot.png', 'image/png', 66)); }
  catch (e) { msg = String(e.message || e); }
  ok(/not a supported photo or video/.test(msg), 'the bridge sentence must survive: ' + msg);
});

// ── 7. the manifest is additive, never a replacement ────────────────────
t('the manifest is additive and never replaces the user words', () => {
  const user = 'look at this HUD and tell me what is wrong';
  const out = ZSMediaRelay.withManifest(user, { manifest: 'MEDIA RELAY\n- name: hud.png' });
  ok(out.startsWith(user), 'the user text must lead');
  ok(out.includes('MEDIA RELAY'), 'the manifest must be appended');
  ok(ZSMediaRelay.withManifest(user, null) === user, 'no media must leave the text byte-identical');
  ok(ZSMediaRelay.withManifest(user, { manifest: '' }) === user, 'an empty manifest must leave the text alone');
});

// ── 8. settings default safely and the port override is validated ───────
t('settings default safely and the port override is validated', () => {
  const d = ZSMediaRelay.sanitizeSettings(null);
  ok(d.enabled === true, 'the relay defaults on');
  ok(d.sendManifest === true, 'the manifest defaults on');
  ok(ZSMediaRelay.sanitizeSettings({ enabled: 0 }).enabled === false, 'falsy must coerce to false');
  ok(ZSMediaRelay.DEFAULT_PORT === 17614, 'the default companion port is PORT+1');
  ZSMediaRelay.setPort('not-a-port');
  ok(typeof ZSMediaRelay.stats === 'function', 'the module survives a bad port');
  ZSMediaRelay.setPort(null);
});

// ── 9. stats() degrades gracefully against a dead bridge ────────────────
t('stats() degrades gracefully against a dead bridge', async () => {
  fetchImpl = async () => { throw new TypeError('Failed to fetch'); };
  ok((await ZSMediaRelay.stats()) === null, 'stats must return null, not throw, when the bridge is down');
  fetchImpl = async () => jsonResponse(200, { items: 0, maxItemBytes: 25165824 });
  const s2 = await ZSMediaRelay.stats();
  ok(s2 && s2.maxItemBytes === 25165824, 'stats must pass through a live response');
});

// ── 10. release() is best-effort and never throws ───────────────────────
t('release() is best-effort and never throws', async () => {
  fetchImpl = async () => { throw new TypeError('Failed to fetch'); };
  ok(await ZSMediaRelay.release('abc') === false, 'a dead bridge must report false, not throw');
  fetchImpl = happyBridge();
  ok(await ZSMediaRelay.release('abc') === true, 'a live bridge must report true');
});

// ── 11. the module and the bridge agree on the contract ─────────────────
t('the module and the bridge agree on routes, loopback and caps', () => {
  const src = read('extension/core/media-relay.js');
  ok(/\/media\/stage/.test(src) && /\/media\/prepare/.test(src) && /\/media\/release/.test(src),
    'every route the module calls must be spelled out');
  ok(/127\.0\.0\.1/.test(src), 'the relay must target loopback only');
  ok(!/0\.0\.0\.0/.test(src), 'the relay must never target a wildcard address');
  const py = read('runtime/media_relay.py');
  ok(/MAX_ITEM_BYTES\s*=\s*24 \* 1024 \* 1024/.test(py), 'the bridge item cap must be 24 MB');
  // The module's own upload ceiling must be BELOW the bridge's, so a file the
  // module accepts is never refused by the bridge for size alone.
  ok(ZSMediaRelay.MAX_UPLOAD_BYTES < 24 * 1024 * 1024, 'the client cap must sit under the bridge cap');
  const bpy = read('runtime/bridge.py');
  for (const route of ['/media/stats', '/media/list', '/media/stage', '/media/prepare', '/media/release', '/media/clear']) {
    ok(bpy.includes('"' + route + '"'), 'the bridge must serve ' + route);
  }
  ok(/ms_media_relay/.test(bpy), 'the bridge must expose ms_media_relay to the model');
});

(async () => {
  for (const { name, fn } of tests) {
    await fn();
    passed++;
    console.log('  ok  ' + name);
  }
  console.log('\ntest_media_relay_js: %d sections passed', passed);
})().catch((e) => { console.error('\nFAIL: ' + (e && e.message || e)); console.error(e); process.exit(1); });
