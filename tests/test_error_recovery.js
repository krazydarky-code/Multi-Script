// SPDX-License-Identifier: GPL-3.0-or-later
// Error-recovery policy regression. Pure logic (core/resilience.js) driven
// directly: this is the gate that decides whether an unattended run keeps going
// through a stall or stops honestly, so every branch is asserted explicitly.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const ZSResilience = new Function(fs.readFileSync(path.join(root, 'extension/core/resilience.js'), 'utf8') + ';return ZSResilience;')();
const ok = (c, m) => { if (!c) throw new Error(m); };

// ── Levels exist with the documented shape ────────────────────────────────
ok(ZSResilience.LEVEL_IDS.join(',') === 'off,standard,persistent', `unexpected levels: ${ZSResilience.LEVEL_IDS}`);
for (const id of ZSResilience.LEVEL_IDS) {
  const L = ZSResilience.LEVELS[id];
  ok(typeof L.label === 'string' && L.label.length > 0, `level ${id} has no label`);
  ok(Array.isArray(L.backoffMs), `level ${id} has no backoff array`);
  if (L.maxRetries > 0) ok(L.backoffMs.length > 0, `level ${id} retries but never backs off`);
}
ok(ZSResilience.LEVELS.persistent.maxRetries > ZSResilience.LEVELS.standard.maxRetries, 'persistent must retry more than standard');

// ── Off really is off: a failure ends the run, it is never silently retried ─
for (const kind of ['empty', 'timeout', 'parse_error', 'send_failed']) {
  const d = ZSResilience.decide('off', kind, { attempt: 0, consecutive: 0 });
  ok(d.action === 'stop', `off level retried a ${kind} (${d.action})`);
  ok(d.reason === 'recovery-off', `off level gave an odd reason for ${kind}: ${d.reason}`);
}

// ── Standard recovers from a one-off, then gives up ──────────────────────
const L = ZSResilience.LEVELS.standard;
for (const kind of ['empty', 'timeout']) {
  const first = ZSResilience.decide('standard', kind, { attempt: 0, consecutive: 0 });
  ok(first.action === 'retry', `standard did not retry the first ${kind}`);
  ok(first.delayMs === L.backoffMs[0], `first ${kind} retry used the wrong backoff (${first.delayMs})`);
  ok(first.feedback.includes('Nothing from it was executed'), `${kind} feedback must say nothing ran`);
  ok(first.feedback.includes('exactly ONE plain-text JSON object'), `${kind} feedback must restate the JSON contract`);
  const last = ZSResilience.decide('standard', kind, { attempt: L.maxRetries - 1, consecutive: 0 });
  ok(last.action === 'retry', `standard gave up one retry early on ${kind}`);
  const spent = ZSResilience.decide('standard', kind, { attempt: L.maxRetries, consecutive: 0 });
  ok(spent.action === 'stop', `standard kept retrying ${kind} past its budget`);
  ok(spent.reason.endsWith('budget-spent'), `unexpected give-up reason: ${spent.reason}`);
  ok(spent.attemptsLeft === 0, 'spent budget must report zero attempts left');
}
// The backoff escalates and then repeats its last value (never grows forever).
const b0 = ZSResilience.decide('standard', 'empty', { attempt: 0, consecutive: 0 }).delayMs;
const b1 = ZSResilience.decide('standard', 'empty', { attempt: 1, consecutive: 0 }).delayMs;
ok(b1 > b0, 'backoff must escalate');
const bBig = ZSResilience.decide('persistent', 'empty', { attempt: ZSResilience.LEVELS.persistent.maxRetries - 1, consecutive: 0 });
ok(bBig.action === 'retry' && bBig.delayMs === ZSResilience.LEVELS.persistent.backoffMs.slice(-1)[0],
  'the last in-budget retry must use the final backoff value');
// The backoff ladder must never go backwards.
const ladder = ZSResilience.LEVELS.persistent.backoffMs;
for (let i = 1; i < ladder.length; i++) ok(ladder[i] >= ladder[i - 1], 'backoff ladder must be non-decreasing');

// ── A run of failures stops even while retries remain (no infinite loop) ─
const capped = ZSResilience.decide('persistent', 'empty', { attempt: 0, consecutive: ZSResilience.LEVELS.persistent.maxConsecutive });
ok(capped.action === 'stop', 'a long failure streak must stop the loop');
ok(capped.reason === 'too-many-consecutive-failures', `unexpected streak reason: ${capped.reason}`);
const nearCap = ZSResilience.decide('persistent', 'empty', { attempt: 0, consecutive: ZSResilience.LEVELS.persistent.maxConsecutive - 1 });
ok(nearCap.action === 'retry', 'the last allowed failure in a streak must still retry');

// ── Site refusals (6.28.3): wait the site out and re-send the SAME message ──
// DeepSeek "Messages too frequent. Try again later." was the real case: the old
// single nudge was itself another message and deepened the limit.
{
  const off1 = ZSResilience.decide('off', 'rate', { attempt: 0, raw: 'x' });
  ok(off1.action === 'stop', 'off level must not retry a site refusal');
  for (const level of ['standard', 'persistent']) {
    for (const kind of ['rate', 'busy']) {
      const first = ZSResilience.decide(level, kind, { attempt: 0, raw: 'RESULT', jitter: 0 });
      ok(first.action === 'resend', `${level}/${kind} must re-send the same message`);
      ok(first.delayMs >= ZSResilience.SITE_BACKOFF[kind][0], `${level}/${kind} must wait the backoff`);
      const budget = ZSResilience.SITE_RETRIES[level][kind];
      ok(budget >= 1 && budget <= 5, `${level}/${kind} must allow recovery while bounding repeated provider refusals`);
      const last = ZSResilience.decide(level, kind, { attempt: budget, raw: 'RESULT' });
      ok(last.action === 'stop', `${level}/${kind} must stop when its budget is spent`);
      // A long failure streak elsewhere must NOT block site recovery.
      const streak = ZSResilience.decide(level, kind, { attempt: 0, consecutive: 999, raw: 'R' });
      ok(streak.action === 'resend', 'site recovery has its own budget');
    }
    const nudge = ZSResilience.decide(level, 'busy', { attempt: 0 });
    ok(nudge.action === 'retry' && nudge.feedback.includes('site itself reported'), 'no message to re-send -> honest busy nudge');
  }
  ok(ZSResilience.decide('standard', 'rate', { attempt: 0, raw: 'x', minDelayMs: 90000 }).delayMs >= 90000, 'rate floor is honoured');
  const C = ZSResilience.classifyNotice;
  ok(C('Messages too frequent. Try again later.').kind === 'rate', 'DeepSeek rate notice');
  ok(C('Too many requests. Wait a moment and try again.').kind === 'rate', '429 notice');
  ok(C('The server is busy. Please try again later.'), 'busy notice');
  ok(C("You've reached your usage limit. Upgrade to continue.").kind === 'quota', 'quota notice');
  ok(C('Something went wrong').kind === 'busy', 'generic error');
  ok(C('Your daily limit resets in 2 hours; 80% remains.') === null,'Informational reset text is not an exhausted quota');
  ok(C('Your usage limit is 100 messages per day.') === null,'A normal usage information label is not a refusal');
  ok(C('Usage limit reached.').kind === 'quota' && ZSResilience.isExplicitProviderLimit('Usage limit reached.'),'A genuine exhausted usage limit still pauses');
  ok(!ZSResilience.isExplicitProviderLimit('Slow down decorative motion for readability.'),'Ordinary creative advice is not a provider throttle');
  ok(ZSResilience.isExplicitProviderLimit('Messages too frequent. Try again later.'),'Explicit provider throttle remains detectable');
  ok(C('PONG') === null && C('Here is the script you asked for.') === null, 'normal text is not a notice');
  ok(C('x'.repeat(400) + ' too many requests') === null, 'long text is never a notice');
  let f = 0; for (let i = 0; i < 6; i++) f = ZSResilience.nextRateFloor(f);
  ok(f === 90000, 'rate floor caps at 90s');
  let g = 90000; for (let i = 0; i < 60; i++) g = ZSResilience.decayRateFloor(g);
  ok(g === 0, 'rate floor decays to zero after clean sends');
}

// ── parse_error carries the caller's exact feedback and detected name ────
const pe = ZSResilience.decide('standard', 'parse_error', { attempt: 0, consecutive: 0, name: 'multi_edit', feedback: 'ERROR: fix your JSON' });
ok(pe.action === 'retry' && pe.feedback === 'ERROR: fix your JSON', 'parse_error must pass the caller feedback through unchanged');
const peDefault = ZSResilience.decide('standard', 'parse_error', { attempt: 0, consecutive: 0, name: 'multi_edit' });
ok(peDefault.feedback.includes('multi_edit'), 'the default parse feedback must name the detected command');
ok(peDefault.feedback.includes('NOT executed'), 'the default parse feedback must be explicit that nothing ran');
const peNoName = ZSResilience.decide('standard', 'parse_error', { attempt: 0, consecutive: 0 });
ok(!peNoName.feedback.includes('undefined'), 'an unknown command name must not leak "undefined"');
ok(!/The command name detected was/.test(peNoName.feedback), 'an unknown command name must omit the name clause entirely');
ok(peNoName.feedback.includes('{"command": "exact_name"'), 'the default parse feedback must still show the required envelope');

// ── send_failed re-sends the SAME text, it never invents a prompt ────────
const sf = ZSResilience.decide('standard', 'send_failed', { attempt: 0, consecutive: 0 });
ok(sf.action === 'resend', `send_failed must resend, got ${sf.action}`);
ok(sf.feedback === '', 'send_failed must not fabricate a model-facing message');

// ── Verification and environment outages PARK, they never retry ──────────
for (const kind of ['verification', 'bridge_offline']) {
  for (const level of ZSResilience.LEVEL_IDS) {
    const d = ZSResilience.decide(level, kind, { attempt: 0, consecutive: 0 });
    ok(d.action === 'wait', `${kind} at level ${level} must wait, got ${d.action}`);
    ok(d.delayMs === 0, `${kind} must not impose its own delay`);
  }
}
ok(ZSResilience.decide('persistent', 'terminal', {}).action === 'stop', 'a terminal condition must stop');
ok(ZSResilience.decide('persistent', 'nonsense', {}).action === 'stop', 'an unknown condition must stop, never loop');

// ── Budgets widen for a persistent run, and never shrink below the base ──
const bs = ZSResilience.budgets('standard'), bp = ZSResilience.budgets('persistent');
for (const k of ['preStartSilentMs', 'warmupMs', 'reasonNoReplyMs', 'openBlockGraceMs', 'verificationWaitMs']) {
  ok(bp[k] >= bs[k], `persistent ${k} must be at least the standard value`);
}
ok(bp.autoContinue === true && bs.autoContinue === false, 'only persistent should auto-continue');
ok(ZSResilience.budgets('persistent').verificationWaitMs >= 300000, 'verification waits must be generous enough for a real user');

// ── Settings: sanitisation, per-provider level, bad input safety ─────────
const s = ZSResilience.sanitize({ level: 'nope', perProvider: { arena: 'persistent', deepseek: 'bogus', 'bad id': 'off' } });
ok(s.level === ZSResilience.DEFAULT_SETTINGS.level && s.level === 'persistent', 'an unknown level must fall back to the default (persistent: a long run must not die after two retries)');
ok(s.perProvider.arena === 'persistent', 'a valid per-provider level must survive');
ok(!('deepseek' in s.perProvider), 'an invalid per-provider level must be dropped');
ok(!('bad id' in s.perProvider), 'an invalid provider id must be dropped');
ok(ZSResilience.levelFor(s, 'arena') === 'persistent', 'per-provider level must win for that provider');
ok(ZSResilience.levelFor(s, 'gemini') === 'persistent', 'other providers must keep the global level');
ok(ZSResilience.levelFor({}, 'anything') === 'persistent', 'missing settings must resolve to the default');
ok(ZSResilience.levelFor(null, null) === 'persistent', 'null settings must resolve to the default');
ok(ZSResilience.LEVELS.standard.maxRetries >= 4 && ZSResilience.LEVELS.persistent.maxRetries >= 10, 'budgets must be wide enough for a long unattended run');
ok(typeof ZSResilience.describe(s, 'arena') === 'string' && ZSResilience.describe(s, 'arena').includes('Persistent'), 'describe must name the effective level');

console.log('PASS error recovery policy: off/standard/persistent, escalating backoff, per-failure + consecutive budgets, parse + send + verification branches, widened persistent budgets, sanitised settings');
