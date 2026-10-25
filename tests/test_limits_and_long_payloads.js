// Optional Limits setting + tailored parse errors + long-payload plumbing.
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
let stored = {}; const listeners = [];
const chrome = { storage: { local: { get: (k, cb) => cb(stored), set: (o) => { Object.assign(stored, o); } }, onChanged: { addListener: (f) => listeners.push(f) } } };
// Content scripts share one global scope (parser.js before/after config.js), so load both together.
const [ZS, ZSParse] = new Function('chrome', read('extension/core/parser.js') + '\n' + read('extension/core/config.js') + ';return [ZS, ZSParse];')(chrome);
const MAIN = read('extension/core/main.js');
let failed = 0;
const t = (name, fn) => { try { fn(); console.log('  ok  ' + name); } catch (e) { failed++; console.log('  FAIL ' + name + ': ' + e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m || 'assertion failed'); };

// ── limits module ──
t('defaults preserve current behaviour (auto / salvage on)', () => {
  const L = ZS.limits.get(); ok(L.resultMode === 'auto' && L.sendMode === 'auto' && L.salvage === true, JSON.stringify(L));
  ok(ZS.limits.sendOverride('x'.repeat(300000)) === null, 'auto must fall through to provider logic');
  ok(ZS.limits.sendBudget(90000) === 90000 && ZS.limits.sendBudget(0) === Infinity);
});
t('sanitize rejects junk and clamps sizes', () => {
  const s = ZS.limits.sanitize({ resultMode: 'weird', resultChars: 3, sendMode: 'custom', sendChars: 1e12, salvage: 0 });
  ok(s.resultMode === 'auto' && s.resultChars === ZS.limits.MIN && s.sendChars === ZS.limits.MAX && s.salvage === true, JSON.stringify(s));
  ok(ZS.limits.sanitize('x').sendMode === 'auto' && ZS.limits.sanitize(null).salvage === true);
  ok(ZS.limits.sanitize({ salvage: false }).salvage === false);
});
t('"off" never clips; "custom" clips to the chosen size with a visible note', () => {
  const big = 'a'.repeat(250000);
  ZS.limits.set({ sendMode: 'off' });
  ok(ZS.limits.sendOverride(big) === big && ZS.limits.sendBudget(90000) === Infinity);
  ZS.limits.set({ sendMode: 'custom', sendChars: 20000 });
  const c = ZS.limits.sendOverride(big);
  ok(c.length <= 20000 + 50 && /Limits setting/.test(c) && c.startsWith('aaaa') && c.endsWith('aaaa'), 'len ' + c.length);
  ok(ZS.limits.sendOverride('short') === 'short' && ZS.limits.sendBudget(90000) === 20000);
});
t('settings persist to storage and reload via onChanged', () => {
  ZS.limits.set({ resultMode: 'custom', resultChars: 42000, salvage: false });
  ok(stored.msLimitSettings && stored.msLimitSettings.resultChars === 42000);
  ZS.limits.apply(null); ok(ZS.limits.get().resultMode === 'auto');
  listeners.forEach((f) => f({ msLimitSettings: { newValue: stored.msLimitSettings } }, 'local'));
  ok(ZS.limits.get().resultChars === 42000 && ZS.limits.salvageAllowed() === false);
  ZS.limits.apply(null);
});

// ── providers honour the override and are safe without ZS ──
for (const p of ['arena', 'chatgpt', 'claude', 'deepseek', 'gemini', 'qwen']) {
  t(`${p}: truncateForSend defers to Limits (and tolerates a missing ZS)`, () => {
    const src = read(`extension/providers/${p}.js`).replace(/\r\n?/g, '\n');
    const m = /function truncateForSend\(text\) \{\n([^\n]*)\n/.exec(src);
    ok(m && /typeof ZS !== "undefined" && ZS\.limits/.test(m[1]) && /sendOverride/.test(m[1]), 'override line missing');
    const line = m[1];
    const f = new Function('ZS', `return function(text){ ${line} return "AUTO"; }`);
    ok(f(undefined)('x') === 'AUTO', 'must fall through without ZS');
    ZS.limits.set({ sendMode: 'off' }); ok(f(ZS)('y'.repeat(500000)).length === 500000, 'off should pass through'); ZS.limits.apply(null);
  });
}
t('notion typeAndSend honours the Limits override', () => {
  ok(/ZS\.limits\.sendOverride\(String\(text\)\)/.test(read('extension/providers/notion.js')));
});

// ── paginateResult honours result mode ──
t('paginateResult: auto pages, off passes through, custom pages at your size', () => {
  const src = MAIN.slice(MAIN.indexOf('const PAGED = {'), MAIN.indexOf('// Fingerprint of an APPENDING multi_edit'));
  ok(src.length > 500, 'paginate source not found');
  const mk = (P) => new Function('P', 'ZS', 'diag', 'bareToolName', 'ZSExtras', src + ';return paginateResult;')(P, ZS, () => {}, (x) => x, undefined);
  const text = Array.from({ length: 4000 }, (_, i) => 'line ' + i + ' ' + 'z'.repeat(40)).join('\n');
  ZS.limits.apply(null);
  ok(mk({ resultCharBudget: 50000, resultLineBudget: 500 })(text, 'x').includes('page 1/'), 'auto should page');
  ok(mk({})(text, 'x') === text, 'no budget + auto = untouched');
  ZS.limits.set({ resultMode: 'off' }); ok(mk({ resultCharBudget: 50000 })(text, 'x') === text, 'off must not page');
  ZS.limits.set({ resultMode: 'custom', resultChars: 30000 }); const r = mk({})(text, 'x');
  ok(/page 1\/\d+/.test(r) && r.length < 31000, 'custom should page a provider without a budget; len ' + r.length);
  ZS.limits.apply(null);
});

// ── 6.28.2 revamp: resultCap interplay, bridge limit, exemption of instructions, summary, wiring ──
t('resultCap: pages never exceed what the send step can carry', () => {
  ZS.limits.apply(null);
  ok(ZS.limits.resultCap(50000, 90000) === 50000 && ZS.limits.resultCap(0, 0) === 0, 'auto unchanged');
  ZS.limits.set({ sendMode: 'custom', sendChars: 20000 });
  ok(ZS.limits.resultCap(50000, 90000) === 16000, 'auto result + custom send must fit: ' + ZS.limits.resultCap(50000, 90000));
  ok(ZS.limits.resultCap(0, 0) === 16000, 'providers without a page budget now page under a custom send cap');
  ZS.limits.set({ resultMode: 'custom', resultChars: 500000 });
  ok(ZS.limits.resultCap(0, 0) === 16000, 'custom result larger than the send cap is reduced');
  ZS.limits.set({ sendMode: 'auto' });
  ok(ZS.limits.resultCap(0, 90000) === 86000, 'custom result larger than the site cap is reduced: ' + ZS.limits.resultCap(0, 90000));
  ok(ZS.limits.resultCap(0, 0) === 500000, 'unknown site cap leaves the custom size alone');
  ZS.limits.set({ resultMode: 'off', sendMode: 'custom' }); ok(ZS.limits.resultCap(50000, 90000) === 0, 'off = never split');
  ZS.limits.apply(null);
});
t('bridgeLimit: auto keeps the bridge default, custom/off stop the bridge clip', () => {
  ZS.limits.apply(null); ok(ZS.limits.bridgeLimit() === null);
  ZS.limits.set({ resultMode: 'custom' }); ok(ZS.limits.bridgeLimit() === 0);
  ZS.limits.set({ resultMode: 'off' }); ok(ZS.limits.bridgeLimit() === 0); ZS.limits.apply(null);
});
t('custom message cap never clips Multi-Script\'s own instructions', () => {
  ZS.limits.set({ sendMode: 'custom', sendChars: 5000 });
  const sys = ZS.SYS_MARKER + '\n' + 'rule '.repeat(20000);
  ok(ZS.limits.sendOverride(sys) === null, 'instructions fall through');
  ok(ZS.limits.sendOverride('x'.repeat(30000)).length < 5200, 'ordinary text is still clipped');
  ZS.limits.set({ sendMode: 'off' }); ok(ZS.limits.sendOverride(sys) === sys); ZS.limits.apply(null);
});
t('describe: plain-language lines + warnings for risky combinations', () => {
  const d = (o) => ZS.limits.describe(ZS.limits.sanitize(o));
  ok(d({}).every((x) => x.level === 'info') && d({}).length === 2, 'auto has no warnings');
  ok(d({ resultMode: 'off' }).some((x) => x.level === 'warn' && /still applies/.test(x.text)), 'off + auto warns');
  ok(d({ resultMode: 'off', sendMode: 'off' }).some((x) => /No limits anywhere/.test(x.text)));
  ok(d({ sendMode: 'custom', sendChars: 6000 }).some((x) => x.level === 'warn' && /small/.test(x.text)));
  ok(d({ resultMode: 'custom', resultChars: 90000, sendMode: 'custom', sendChars: 30000 }).some((x) => /smaller than your message cap/.test(x.text)));
  ok(d({ salvage: false }).some((x) => /reported to the model/.test(x.text)));
});
t('paginateResult under a custom send cap: first page fits the cap, even for providers with no budget', () => {
  const src = MAIN.slice(MAIN.indexOf('const PAGED = {'), MAIN.indexOf('// Fingerprint of an APPENDING multi_edit'));
  const P = {};
  const fn = new Function('P', 'ZS', 'diag', 'bareToolName', 'ZSExtras', src + ';return paginateResult;')(P, ZS, () => {}, (x) => x, undefined);
  const text = Array.from({ length: 6000 }, (_, i) => 'row ' + i + ' ' + 'q'.repeat(60)).join('\n');
  ZS.limits.set({ sendMode: 'custom', sendChars: 20000 });
  const r = fn(text, 'x'); ok(/page 1\/\d+/.test(r) && r.length <= 20000, 'len ' + r.length);
  ZS.limits.apply(null);
});
t('the Limits wiring reaches every layer', () => {
  ok(/resultLimit: ZS\.limits \? ZS\.limits\.bridgeLimit\(\)/.test(MAIN), 'main.js passes resultLimit');
  ok(/result_limit: msg\.resultLimit/.test(read('extension/background.js')), 'background forwards it');
  ok(/apply_result_limit\(result_limit\)/.test(read('runtime/bridge.py')) && /msg\.get\("result_limit"\)/.test(read('runtime/bridge.py')), 'bridge applies it');
  ok(/ZS\.limits\.send\(\)\.mode === "custom"[^\n]*sendOverride\(String\(text\)\)/.test(MAIN), 'central custom clip for every provider');
  ok(/id="ms-lim-summary"/.test(MAIN) && /id="ms-lim-reset"/.test(MAIN) && /refreshLimitsSummary/.test(MAIN), 'summary + reset in the settings UI');
  ok(/limits:ZS\.limits\.get\(\)/.test(MAIN) && /ZS\.limits\.set\(raw\.limits\)/.test(MAIN), 'backup/restore');
});

// ── replay guard fingerprint ──
t('appendEditFingerprint: identical appends match, real edits are exempt', () => {
  const src = MAIN.slice(MAIN.indexOf('function appendEditFingerprint'), MAIN.indexOf('async function runTool('));
  const fp = new Function('bareToolName', src + ';return appendEditFingerprint;')((x) => String(x).replace(/^ms_/, ''));
  const a = { file_path: 'game.SSS.A', edits: [{ old_string: '', new_string: 'print(1)' }] };
  ok(fp('multi_edit', a) && fp('multi_edit', a) === fp('multi_edit', JSON.parse(JSON.stringify(a))));
  ok(fp('multi_edit', a) !== fp('multi_edit', { file_path: 'game.SSS.B', edits: a.edits }));
  ok(fp('multi_edit', { file_path: 'x', edits: [{ old_string: 'a', new_string: 'b' }] }) === '', 'targeted edit is idempotent-safe');
  ok(fp('execute_luau', a) === '' && fp('multi_edit', null) === '');
  ok(/A\.recentEdits/.test(MAIN), 'runTool guard not wired');
});

// ── parser diagnosis + tailored feedback ──
const call = (code) => '{"command":"execute_luau","params":{"code":' + JSON.stringify(code) + ',"datamodel_type":"Edit"}}';
const lua = Array.from({ length: 800 }, (_, i) => `local v${i} = "str \\"q\\" ${i}"  -- note\nprint(v${i})`).join('\n');
t('diagnose: valid big payload parses and is reported valid', () => {
  const raw = call(lua); ok(raw.length > 30000);
  ok(ZSParse.diagnose(raw).kind === 'valid', ZSParse.diagnose(raw).kind);
  const calls = ZSParse.parseToolCalls(raw); ok(calls.length === 1 && calls[0].arguments.code === lua, 'round-trip');
});
t('diagnose: cut-off / trailing / raw newline / smart quote / none', () => {
  const raw = call(lua);
  ok(ZSParse.diagnose(raw.slice(0, raw.length - 30)).kind.startsWith('cut-off'), ZSParse.diagnose(raw.slice(0, 30000)).kind);
  ok(ZSParse.diagnose(raw + ' and then some words').kind === 'trailing-text', ZSParse.diagnose(raw + ' x').kind);
  ok(ZSParse.diagnose('{"command":"execute_luau","params":{"code":"a\nb"}}').kind === 'raw-newlines');
  ok(ZSParse.diagnose('{\u201ccommand\u201d:\u201cget_studio_state\u201d}').kind === 'smart-quotes');
  ok(ZSParse.diagnose('just chatting').kind === 'no-object');
});
t('parseError: generic with no args, tailored with raw', () => {
  const generic = ZS.FEEDBACK.parseError('malformed', 'execute_luau');
  const raw = call(lua); const cut = raw.slice(0, raw.length - 200);
  const tailored = ZS.FEEDBACK.parseError('unclosed', 'execute_luau', cut);
  ok(typeof generic === 'string' && generic.length > 50);
  ok(/cut off|cut-off|stopped/i.test(tailored) && /ms_stage_code/.test(tailored), tailored.slice(0, 300));
  ok(tailored !== generic);
  ok(/execute_luau|ms_run_staged_luau/.test(tailored));
});
t('salvage respects the setting and diag is wired', () => {
  ok(/ZS\.limits\.salvageAllowed\(\)\) \? ZSParse\.salvageCutOff/.test(MAIN));
  ok(/diag\("parse\.diagnose"/.test(MAIN));
  ok(/ms_stage_code/.test(MAIN) && /ms-lim-send/.test(MAIN) && /limits:ZS\.limits\.get\(\)/.test(MAIN) && /ZS\.limits\.set\(raw\.limits\)/.test(MAIN), 'settings UI / backup not wired');
});

console.log(failed ? `\n${failed} FAILED` : '\nall passed');
process.exit(failed ? 1 : 0);
