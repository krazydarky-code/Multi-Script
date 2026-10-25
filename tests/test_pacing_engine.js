// SPDX-License-Identifier: GPL-3.0-or-later
// Pacing engine regression. Pure logic, no browser: loads core/pacing.js exactly
// the way the extension does and drives it with a SEEDED rng so every assertion
// is deterministic. This is the "does the pacing actually do what the menu says"
// gate - bounds, long pauses, error cooldowns, per-provider overrides, off mode.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const ZSPace = new Function(fs.readFileSync(path.join(root, 'extension/core/pacing.js'), 'utf8') + ';return ZSPace;')();

// Mulberry32: a tiny deterministic PRNG, so a failure here is reproducible.
function rng(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const fail = (m) => { throw new Error(m); };
const ok = (c, m) => { if (!c) fail(m); };

// ── 1. Off is a real off switch ───────────────────────────────────────────
const off = ZSPace.sanitize({ mode: 'off' });
ok(ZSPace.isOff(ZSPace.profileFor(off, 'deepseek')), 'off mode must report as off');
for (let i = 0; i < 50; i++) {
  const d = ZSPace.computeDelay(off, 'deepseek', { rng: rng(i + 1), sendIndex: i, now: 0 });
  ok(d.delayMs === 0, `off mode produced a delay (${d.delayMs}) at index ${i}`);
}
ok(ZSPace.typingDelay(off, 'deepseek', 5000, { rng: rng(7) }) === 0, 'off mode must not simulate typing');

// ── 2. Human band: every ordinary gap is inside the configured band ───────
const human = ZSPace.sanitize({ mode: 'human' });
const hProfile = ZSPace.profileFor(human, 'deepseek');
ok(hProfile.min === 1500 && hProfile.max === 4500, 'human preset band changed unexpectedly');
let minSeen = Infinity, maxSeen = -Infinity;
for (let i = 0; i < 400; i++) {
  // sendIndex 1..7 only, so no long pause is folded in.
  const idx = (i % 7) + 1;
  const d = ZSPace.computeDelay(human, 'deepseek', { rng: rng(i * 31 + 5), sendIndex: idx, now: 0 });
  ok(!d.longPause, `long pause fired outside longEvery at index ${idx}`);
  ok(d.delayMs >= hProfile.min && d.delayMs <= hProfile.max,
    `gap ${d.delayMs} outside human band [${hProfile.min},${hProfile.max}]`);
  minSeen = Math.min(minSeen, d.delayMs);
  maxSeen = Math.max(maxSeen, d.delayMs);
}
ok(maxSeen - minSeen > 500, 'gaps are not actually randomised (band too narrow in practice)');

// ── 3. Determinism: same seed + same index = same gap ────────────────────
const a1 = ZSPace.computeDelay(human, 'deepseek', { rng: rng(99), sendIndex: 3, now: 0 });
const a2 = ZSPace.computeDelay(human, 'deepseek', { rng: rng(99), sendIndex: 3, now: 0 });
ok(a1.delayMs === a2.delayMs, 'pacing is not reproducible for a fixed seed');

// ── 4. The periodic long pause really happens, and only every Nth send ────
const every = hProfile.longEvery;
ok(every > 0, 'human preset must define a long-pause cadence');
const onBeat = ZSPace.computeDelay(human, 'deepseek', { rng: rng(4), sendIndex: every, now: 0 });
ok(onBeat.longPause, `no long pause at send index ${every}`);
ok(onBeat.delayMs >= hProfile.min + hProfile.longMin, 'long pause did not add the long band');
ok(onBeat.delayMs <= hProfile.max + hProfile.longMax, 'long pause exceeded the long band');
for (const idx of [1, 2, every - 1, every + 1, 2 * every - 1]) {
  const d = ZSPace.computeDelay(human, 'deepseek', { rng: rng(idx + 3), sendIndex: idx, now: 0 });
  ok(!d.longPause, `long pause fired at a non-beat index ${idx}`);
}
const twoBeats = ZSPace.computeDelay(human, 'deepseek', { rng: rng(8), sendIndex: 2 * every, now: 0 });
ok(twoBeats.longPause, 'long pause did not repeat on the second beat');

// ── 5. Error cooldown: a retry can never arrive faster than the cooldown ──
const cooldown = hProfile.errorCooldownMs;
ok(cooldown > 0, 'human preset must define an error cooldown');
const justFailed = ZSPace.computeDelay(human, 'deepseek', { rng: rng(11), sendIndex: 1, now: 1000, lastErrorAt: 1000 });
ok(justFailed.cooldownMs === cooldown, `fresh failure did not arm the full cooldown (${justFailed.cooldownMs})`);
ok(justFailed.delayMs >= cooldown, 'cooldown did not extend the delay');
const halfFailed = ZSPace.computeDelay(human, 'deepseek', { rng: rng(11), sendIndex: 1, now: 1000 + cooldown / 2, lastErrorAt: 1000 });
ok(halfFailed.cooldownMs === cooldown / 2, `cooldown did not decay (${halfFailed.cooldownMs})`);
const staleFailure = ZSPace.computeDelay(human, 'deepseek', { rng: rng(11), sendIndex: 1, now: 1000 + cooldown * 5, lastErrorAt: 1000 });
ok(staleFailure.cooldownMs === 0, 'an old failure still armed the cooldown');
const slowFailure = ZSPace.computeDelay(human, 'deepseek', {rng:rng(11),sendIndex:1,now:100000,lastSendAt:1000,lastErrorAt:100000});
ok(slowFailure.delayMs >= cooldown,'A slow response must not consume a cooldown that began at its later error');
const slowRetry = ZSPace.computeDelay(human, 'deepseek', {rng:rng(11),sendIndex:1,now:101000,lastSendAt:1000,lastErrorAt:100000});
ok(slowRetry.delayMs >= cooldown-1000,'Retry must honor the remaining error cooldown independently of the previous send');

// ── 6. Gap is measured SINCE THE LAST SEND, not as a fresh sleep ─────────
// A slow reply already consumed the gap: the next turn must not be double-taxed.
const g = ZSPace.computeDelay(human, 'deepseek', { rng: rng(21), sendIndex: 1, now: 100000, lastSendAt: 0 });
const consumed = ZSPace.computeDelay(human, 'deepseek', { rng: rng(21), sendIndex: 1, now: 100000, lastSendAt: 100000 - g.delayMs });
ok(consumed.delayMs === 0, `an already-elapsed gap still waited ${consumed.delayMs}ms`);
const partly = ZSPace.computeDelay(human, 'deepseek', { rng: rng(21), sendIndex: 1, now: 100000, lastSendAt: 100000 - Math.floor(g.delayMs / 2) });
ok(partly.delayMs > 0 && partly.delayMs < g.delayMs, `a partly-elapsed gap waited the wrong amount (${partly.delayMs} of ${g.delayMs})`);

// ── 7. Cautious is slower and does simulate typing ───────────────────────
const cautious = ZSPace.sanitize({ mode: 'cautious' });
const cProfile = ZSPace.profileFor(cautious, 'arena');
ok(cProfile.min > hProfile.min && cProfile.max > hProfile.max, 'cautious must be slower than human');
const typing = ZSPace.typingDelay({ ...cautious, typingSim: true }, 'arena', 600, { rng: rng(3) });
ok(typing > 0 && typing <= 12000, `typing delay out of range (${typing})`);
const chunks = ZSPace.typingChunks(typing, 4);
ok(chunks.length > 0 && chunks.reduce((x, y) => x + y, 0) === typing, 'typing chunks must sum to the budget');
ok(ZSPace.typingChunks(0, 4).length === 0, 'zero typing budget must produce no chunks');

// ── 8. Per-provider override ─────────────────────────────────────────────
// The whole point: "this site flags me, slow down HERE" must work even when the
// global mode is Off.
const perProvider = ZSPace.sanitize({ mode: 'off', perProvider: { arena: { mode: 'cautious' } } });
ok(ZSPace.isOff(ZSPace.profileFor(perProvider, 'deepseek')), 'global off must still apply to other providers');
const arenaProfile = ZSPace.profileFor(perProvider, 'arena');
ok(!ZSPace.isOff(arenaProfile), 'per-provider cautious must survive a global off');
ok(arenaProfile.min >= ZSPace.MODES.cautious.min, 'per-provider cautious floor not applied');
const numericOverride = ZSPace.sanitize({ mode: 'human', perProvider: { arena: { min: 9000, max: 12000 } } });
const no = ZSPace.profileFor(numericOverride, 'arena');
ok(no.min === 9000 && no.max === 12000, `numeric per-provider override ignored (${no.min}-${no.max})`);

// ── 9. Sanitisation: garbage in, safe numbers out ────────────────────────
const junk = ZSPace.sanitize({ mode: 'nonsense', typingSim: 'yes', custom: { min: -500, max: 'abc', longEvery: 9999, typingCps: 1e9, errorCooldownMs: NaN }, perProvider: { 'bad id!': { mode: 'human' }, ok_id: { mode: 'brisk' } } });
ok(junk.mode === 'human', 'unknown mode must fall back to the default');
ok(junk.custom.min === 0, 'negative min must clamp to 0');
ok(Number.isFinite(junk.custom.max), 'non-numeric max must become a finite number');
ok(junk.custom.longEvery === ZSPace.LIMITS.longEvery[1], 'longEvery must clamp to its ceiling');
ok(junk.custom.typingCps === ZSPace.LIMITS.typingCps[1], 'typingCps must clamp to its ceiling');
ok(Number.isFinite(junk.custom.errorCooldownMs) && junk.custom.errorCooldownMs >= 0 &&
   junk.custom.errorCooldownMs <= ZSPace.LIMITS.errorCooldownMs[1],
   `NaN cooldown must fall back to a finite in-range default (${junk.custom.errorCooldownMs})`);
ok(!('bad id!' in junk.perProvider), 'an invalid provider id must be dropped');
ok(junk.perProvider.ok_id && junk.perProvider.ok_id.mode === 'brisk', 'a valid provider override must survive');
const inverted = ZSPace.normalizeProfile({ min: 8000, max: 1000, longMin: 9000, longMax: 2000 }, ZSPace.MODES.human);
ok(inverted.min <= inverted.max && inverted.longMin <= inverted.longMax, 'inverted bands must be swapped, not kept');

// ── 10. A whole simulated run stays sane ─────────────────────────────────
const seq = ZSPace.planSequence(human, 'deepseek', 40, { rng: rng(1234) });
const st = ZSPace.stats(seq);
ok(st.count === 40, 'planSequence must return one gap per send');
ok(st.max <= hProfile.max + hProfile.longMax, `simulated run exceeded the ceiling (${st.max})`);
ok(st.mean >= hProfile.min && st.mean <= hProfile.max + hProfile.longMax / 2, `simulated mean out of range (${st.mean})`);
ok(st.totalMs > 0, 'simulated run must actually take time');
ok(typeof ZSPace.describe(human, 'deepseek') === 'string' && ZSPace.describe(human, 'deepseek').length > 10, 'describe must return a usable line');
ok(ZSPace.describe(off, 'deepseek').toLowerCase().includes('off'), 'describe must say when pacing is off');

console.log(`PASS reply pacing engine: off switch, ${hProfile.min}-${hProfile.max}ms band, long pause every ${every}, ${cooldown}ms error cooldown, per-provider overrides, sanitisation, deterministic under a seeded rng (mean ${st.mean}ms over 40 simulated sends)`);
