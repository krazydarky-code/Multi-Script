// SPDX-License-Identifier: GPL-3.0-or-later
// 6.28.2: the pure Security Office engine behind Fazbear's Backstage tab (no DOM, no timers).
const fs = require('fs'), path = require('path');
const ZSExtras = new Function(fs.readFileSync(path.join(__dirname, '../extension/core/extras.js'), 'utf8') + ';return ZSExtras;')();
const E = ZSExtras.FNAF_OFFICE;
const ok = (c, m) => { if (!c) throw new Error(m); };
const seeded = (a) => () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const run = (night, seed, policy) => { const r = seeded(seed), s = E.create(night); for (let i = 0; i < 2000 && !s.outcome; i++) { policy(s); E.step(s, 100, r); } return s; };

ok(E.NIGHT_MS === 84000 && E.NIGHTS === 5, 'a night is 6 hours of 14 s, five nights');
ok(E.clampNight(0) === 1 && E.clampNight(99) === 5 && E.clampNight('x') === 1, 'night clamp');
let s = E.create(1);
ok(E.usage(s) === 1, 'base usage 1');
E.toggle(s, 'doorL'); E.toggle(s, 'lightR'); ok(E.usage(s) === 3, 'doors and lights add usage');
E.toggle(s, 'lightL'); ok(s.lightL && !s.lightR, 'lights are exclusive');
E.toggle(s, 'cam'); ok(s.cam && !s.lightL, 'camera turns the lights off');
E.setCam(s, 'bogus'); ok(s.camSel === 'stage', 'unknown camera ignored'); E.setCam(s, 'cove'); ok(s.camSel === 'cove', 'camera select');
// time and power
s = E.create(1); E.step(s, 1000, () => 0.99); ok(Math.abs(s.power - 99.5) < 1e-9, 'usage-1 drain is 0.5%/s: ' + s.power);
E.step(s, 99999, () => 0.99); ok(s.t < 3000, 'a single step is capped at 1 s so a background tab cannot burn the night');
// nothing moves with a high roll and the night is won; everything moves with a low roll and an idle player loses
s = run(1, 1, () => {}); const calm = E.create(1); for (let i = 0; i < 900 && !calm.outcome; i++) E.step(calm, 100, () => 0.99);
ok(calm.outcome === 'won' && calm.hour === 6 && calm.power > 50, 'quiet night should be won with power left');
const hot = E.create(5); for (let i = 0; i < 900 && !hot.outcome; i++) E.step(hot, 100, () => 0);
ok(hot.outcome === 'dead' && ['bonnie', 'chica', 'foxy', 'freddy'].includes(hot.killer), 'idle player on night 5 must lose');
// a closed door makes the visitor retreat; an open one kills
const d = E.create(3); d.pos.bonnie = 3; d.doorL = true; for (let i = 0; i < 25; i++) E.step(d, 100, () => 0.99);
ok(d.pos.bonnie === 1 && d.flags.blocked === 1 && !d.outcome, 'closed door should repel Bonnie');
const o = E.create(3); o.pos.chica = 3; for (let i = 0; i < 60 && !o.outcome; i++) E.step(o, 100, () => 0.99);
ok(o.outcome === 'dead' && o.killer === 'chica', 'open door should let Chica in');
// Foxy: watching the Cove stalls him; running into a closed door costs power
const f = E.create(2); E.toggle(f, 'cam'); E.setCam(f, 'cove'); for (let i = 0; i < 400 && !f.outcome; i++) E.step(f, 100, () => 0);
ok(f.foxy.stage === 0, 'Foxy must not leave the Cove while watched');
const fx = E.create(2); fx.foxy.stage = 3; fx.doorL = true; for (let i = 0; i < 34; i++) E.step(fx, 100, () => 0.99);
ok(fx.flags.foxyBlocked === 1 && fx.foxy.stage === 0 && fx.power < 100 - 3, 'Foxy hits a closed door and drains power');
const fy = E.create(2); fy.foxy.stage = 3; for (let i = 0; i < 40 && !fy.outcome; i++) E.step(fy, 100, () => 0.99);
ok(fy.outcome === 'dead' && fy.killer === 'foxy', 'Foxy kills through an open left door');
// blackout: everything shuts off, Freddy arrives
const b = E.create(1); b.power = 0.05; b.doorL = b.lightR = true; E.step(b, 500, () => 0.99);
ok(b.power === 0 && !b.doorL && !b.lightR && b.flags.blackout, 'power out turns everything off');
E.toggle(b, 'doorL'); ok(!b.doorL, 'nothing can be switched on in the dark');
ok(E.view(b).mode === 'dark', 'dark view');
for (let i = 0; i < 100 && !b.outcome; i++) E.step(b, 100, () => 0.99);
ok(b.outcome === 'dead' && b.killer === 'freddy', 'Freddy comes when the power dies');
// views
const v = E.create(1); v.pos.bonnie = 3; E.toggle(v, 'lightL'); ok(/Bonnie is at the door/.test(E.view(v).lines[0]), 'light shows Bonnie at the door');
E.toggle(v, 'cam'); E.setCam(v, 'hall'); ok(E.view(v).mode === 'cam' && /Nothing|Chica|Bonnie/.test(E.view(v).lines[0]), 'cam view');
// finished games ignore further input
const w = E.create(1); w.outcome = 'won'; E.toggle(w, 'doorL'); ok(!w.doorL && E.step(w, 100) === w, 'finished games are inert');
// difficulty curve: idle fails, door-camping fails, careful play wins every night with shrinking power margins
const smart = (st) => { if (st.power > 0) { st.doorL = st.pos.bonnie === 3 || st.foxy.stage >= 3; st.doorR = st.pos.chica === 3; } };
const camp = (st) => { if (st.power > 0) { st.doorL = true; st.doorR = true; } };
let prev = 101;
for (let n = 1; n <= 5; n++) {
  let sw = 0, iw = 0, cw = 0, pw = 0; const N = 80;
  for (let i = 1; i <= N; i++) { const a = run(n, i, smart); if (a.outcome === 'won') { sw++; pw += a.power; } if (run(n, i, () => {}).outcome === 'won') iw++; if (run(n, i, camp).outcome === 'won') cw++; }
  ok(sw === N, `careful play should clear night ${n} (${sw}/${N})`);
  ok(cw === 0, `camping behind both doors must not win night ${n}`);
  ok(n === 1 ? iw < N : iw <= N * 0.1, `idle play must usually fail night ${n} (${iw}/${N})`);
  const avg = pw / N; ok(avg <= prev + 1, `power margin should shrink as nights get harder (${avg} vs ${prev})`); prev = avg;
}
ok(ZSExtras.EXTRA_THEMES.some((t) => t[0] === 'fnaf'), 'fnaf theme registered');
console.log('PASS fnaf office engine (power, doors, lights, cams, Foxy, Freddy, blackout, difficulty curve)');
