// SPDX-License-Identifier: GPL-3.0-or-later
// One-shot / unattended autonomy regression. Two halves:
//  1. the PROMPT (config.js) really tells the model to stop asking questions and
//     keep working until the spec is done;
//  2. the CORE (main.js) actually injects it and has the loop-side machinery
//     (pacing, recovery, verification parking) that makes an unattended run
//     survivable;
//  3. the MANIFEST loads the new modules before the core on every provider.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const ZS = new Function(read('extension/core/config.js') + ';return ZS;')();
const ok = (c, m) => { if (!c) throw new Error(m); };

// ── 1. Prompt ─────────────────────────────────────────────────────────────
ok(ZS.AUTONOMY_IDS.join(',') === 'guided,oneShot', `unexpected autonomy levels: ${ZS.AUTONOMY_IDS}`);
for (const id of ZS.AUTONOMY_IDS) {
  const l = ZS.AUTONOMY_LEVELS[id];
  ok(l && typeof l.label === 'string' && typeof l.hint === 'string', `autonomy level ${id} is incomplete`);
}
const ask=ZS.autonomyPrompt('guided','DeepSeek');
ok(ask.includes('MULTI-SCRIPT ASK MODE')&&ask.includes('continue independent inspection')&&ask.includes('Do not invent user approval'),'guided mode asks crucial questions while preserving independent work and approval boundaries');
const one = ZS.autonomyPrompt('oneShot', 'DeepSeek');
for (const phrase of ['NO QUESTIONS', 'NO DEAD TURNS', 'KEEP GOING UNTIL DONE', 'DRIVE THE WHOLE SPEC', 'RECOVER SILENTLY', 'STOP ONLY FOR THE IRREVERSIBLE', 'FINISH WITH EVIDENCE']) {
  ok(one.includes(phrase), `one-shot prompt is missing the "${phrase}" rule`);
}
ok(one.includes('DeepSeek'), 'the one-shot prompt must name the provider it runs on');
ok(/exactly one plain-text JSON command/.test(one), 'one-shot must restate the single-command rule');
// It must not license destructive freedom.
ok(/destructive|irreversible/.test(one) && /costs money|credentials/.test(one), 'one-shot must keep the irreversible-choice guard');
ok(ZS.sanitizeAutonomy('oneShot') === 'oneShot', 'sanitizeAutonomy must keep a valid level');
ok(ZS.sanitizeAutonomy('nonsense') === 'guided', 'sanitizeAutonomy must fall back to guided');
ok(ZS.sanitizeAutonomy(undefined) === 'guided', 'sanitizeAutonomy must handle undefined');

// ── 2. Core wiring ────────────────────────────────────────────────────────
const main = read('extension/core/main.js');
const coreChecks = [
  ['autonomy into the system prompt', 'ZS.autonomyPrompt(autonomyLevel'],
  ['autonomy setting + persistence', 'zsAutonomyLevel'],
  ['one-shot raises the recovery floor', 'setResilienceSettings({ level: "persistent" })'],
  ['pacing applied before every send', 'await paceBeforeSend('],
  ['interruptible paced sleep', 'async function paceSleep(ms)'],
  ['send index / last send / last error tracked', 'A.lastSendAt = Date.now()'],
  ['recovery decision layer wired in', 'ZSResilience.decide(rlevel()'],
  ['bounded parse-error recovery', 'recoverFrom("parse_error"'],
  ['timeout + empty recovery instead of ending the loop', 'if (await recoverFrom(res.kind)) continue'],
  ['transient site-busy recovery', 'res.kind === "busy"'],
  ['consecutive-failure counters reset on success', 'resetFails()'],
  ['human verification parking', 'async function awaitHumanVerification(reason)'],
  ['verification gate in the loop', 'awaitHumanVerification("loop")'],
  ['verification gate before a send', 'awaitHumanVerification("submit")'],
  ['verification gate at startup', 'awaitHumanVerification("startup")'],
  ['a refusing typeAndSend cannot kill the loop', 'send.typeAndSendError'],
  ['widened persistent patience windows', 'const RB = rbudgets()'],
  ['pacing shown in the bar', 'pacingUntil'],
  ['settings UI for pacing', 'data-pace-mode'],
  ['per-site pacing scope toggle', 'ms-pace-scope'],
  ['in-menu pacing self-check', 'ms-pace-test'],
  ['settings UI for recovery', 'data-recovery'],
  ['settings UI for autonomy', 'data-autonomy'],
  ['pacing + recovery in the settings backup', 'errorRecovery:ZSResilience.sanitize'],
  ['pacing + recovery in diagnostics', 'errorRecoverySummary'],
  ['reset restores pacing + recovery + autonomy', 'autonomyLevel="guided"'],
];
for (const [what, needle] of coreChecks) ok(main.includes(needle), `core is missing ${what} (expected "${needle}")`);
// The old fixed-jitter experiment must be gone - it is superseded by ZSPace.
ok(!main.includes('HUMANIZE_SEND'), 'the superseded HUMANIZE_SEND toggle is still present');
ok(!main.includes('jitterBeforeSend'), 'the superseded jitterBeforeSend is still present');

// ── 3. Manifest: new modules load before the core, on every provider ─────
const manifest = JSON.parse(read('extension/manifest.json'));
const coreSections = manifest.content_scripts.filter((s) => (s.js || []).includes('core/main.js'));
ok(coreSections.length >= 9, `expected the core on every provider, found ${coreSections.length}`);
for (const s of coreSections) {
  const js = s.js;
  const iMain = js.indexOf('core/main.js');
  const iPace = js.indexOf('core/pacing.js');
  const iRes = js.indexOf('core/resilience.js');
  ok(iPace !== -1 && iRes !== -1, `a core content script does not load the new modules: ${JSON.stringify(js)}`);
  ok(iPace < iMain && iRes < iMain, `pacing/resilience must load BEFORE main.js: ${JSON.stringify(js)}`);
  ok(js.indexOf('core/config.js') < iPace, 'config.js must still load first');
}

// ── 3b. No OTHER file may list the core scripts without the new modules ──
// popup.js reinjects the content scripts to repair a Notion tab that never got
// them. If that list drifts from content_scripts, the injected main.js throws on
// load ("ZSPace is not defined") and the repair leaves the tab more broken than
// it found it - silently. So it must derive the list from the manifest, and its
// fallback must still contain every core module in the right order.
{
  const popup = read('extension/popup.js');
  ok(popup.includes('notionInjection'), 'popup.js must derive the reinjection list from the manifest');
  ok(popup.includes('getManifest().content_scripts'), 'popup.js must read content_scripts from the manifest');
  for (const f of ['core/config.js', 'core/parser.js', 'providers/notion.js', 'core/tool-routing.js', 'core/pacing.js', 'core/resilience.js', 'core/main.js']) {
    ok(popup.includes(`"${f}"`), `popup.js fallback is missing ${f}`);
  }
  ok(popup.indexOf('"core/pacing.js"') < popup.indexOf('"core/main.js"'), 'popup.js fallback must list pacing before main');
  ok(popup.indexOf('"core/resilience.js"') < popup.indexOf('"core/main.js"'), 'popup.js fallback must list resilience before main');
  ok(popup.includes('"overlay.css"'), 'popup.js must still reinject the stylesheet');
  // And no other source may hardcode the core list without the new modules.
  const offenders = [];
  for (const rel of ['extension/popup.js', 'extension/background.js']) {
    const src = read(rel);
    for (const m of src.matchAll(/\[[^\[\]]*core\/main\.js[^\[\]]*\]/g)) {
      const list = m[0];
      if (list.includes('core/main.js') && !(list.includes('core/pacing.js') && list.includes('core/resilience.js'))) offenders.push(`${rel}: ${list}`);
    }
  }
  ok(offenders.length === 0, `a script list omits the new core modules:\n${offenders.join('\n')}`);
}

// ── 4. The core really resolves the autonomy level it was given ──────────
const paceSettings = { mode: 'human' };
const persist = ZS.autonomyPrompt('oneShot', 'Arena');
ok(persist.length > 1500, 'the one-shot block must be substantial enough to matter');
ok(persist.split('\n').length >= 9, 'the one-shot block must be structured, not one long line');
ok(!/ask the user/i.test(persist.split('NO QUESTIONS')[1].split('NO DEAD TURNS')[0]), 'the NO QUESTIONS rule must not hedge');

console.log('PASS one-shot autonomy: prompt rules (no questions, no dead turns, drive the whole spec, recover silently), core wiring (pacing, bounded recovery, verification parking, settings + backup + diagnostics), and manifest load order on all 9 providers');
