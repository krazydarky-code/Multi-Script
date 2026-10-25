// SPDX-License-Identifier: GPL-3.0-or-later
// Pure-logic gate for the Notion model catalog + trial/credit estimator.
const fs = require('fs'), path = require('path');
const U = new Function(fs.readFileSync(path.join(__dirname, '../extension/core/notion-usage.js'), 'utf8') + ';return ZSNotionUsage;')();
let n = 0; const ok = (c, m) => { if (!c) { console.error('FAIL ' + m); process.exit(1); } n++; console.log('PASS ' + m); };
const DAY = U.DAY, T0 = Date.UTC(2026, 0, 10, 12);

// ── names, versions, efforts ────────────────────────────────────────────────
const models = U.parseModels([{ text: 'Claude Opus 5.5 New — most capable', selected: true }, { text: 'Claude Opus 5' }, { text: 'Claude Sonnet 5.5' }, { text: 'GPT-5.6 Sol Upgrade' }, { text: 'Gemini 3 Pro' }, { text: 'More models' }, { text: 'Auto' }]);
ok(models.length === 6 && !models.some((m) => /more/i.test(m.name)), 'picker rows parse; "More models" is not a model');
ok(U.findModel(models, 'opus 5.5').name === 'Claude Opus 5.5' && U.findModel(models, 'Opus 5').name === 'Claude Opus 5', 'Opus 5 and Opus 5.5 are never confused');
ok(U.findModel(models, 'sonnet').name === 'Claude Sonnet 5.5', 'partial names resolve');
ok(U.findModel(models, 'gpt-5.6 sol') === null && U.findModel(models, 'gpt-5.6 sol', { enabledOnly: false }).enabled === false, 'a locked model is reported locked, not selectable');
ok(models.find((m) => /Gemini/.test(m.name)).name === 'Gemini 3 Pro', '"Pro" stays part of a model name');
ok(['low', 'Medium', 'HIGH', 'extra high', 'Max', 'x-high'].map(U.normEffort).join() === 'low,medium,high,xhigh,max,xhigh', 'effort labels normalise');
ok(U.pickEffort(['low', 'high'], 'medium') === 'high' && U.pickEffort(['low', 'medium'], 'max') === 'medium' && U.pickEffort([], 'high') === null, 'nearest available effort (higher on ties), none when absent');
ok(U.promptWeight('Claude Opus 5.5', 'high') > U.promptWeight('Claude Sonnet 5.5', 'high') && U.promptWeight('Claude Haiku', 'low') < U.promptWeight('Claude Sonnet 5.5', 'low'), 'Opus > Sonnet > Haiku per prompt, effort scales it');

// ── page text ───────────────────────────────────────────────────────────────
let sc = U.scanText('Trial ends in 5 days · 1,250 credits left', T0);
ok(sc.daysLeft === 5 && sc.creditsRemaining === 1250, 'reads "N days" and "N credits left"');
sc = U.scanText('Used 300 of 1000 AI credits', T0);
ok(sc.creditsRemaining === 700 && sc.creditsTotal === 1000, 'reads "used of total" credits');
sc = U.scanText('Your trial ends Jan 20', T0);
ok(Math.round((sc.trialEndsAt - T0) / DAY) === 10, 'reads an end date');
ok(Object.keys(U.scanText('Welcome back!')).length === 0, 'unrelated text reads as nothing');

// ── estimator ───────────────────────────────────────────────────────────────
let s = U.defaults();
ok(/Add your credits/.test(U.estimate(s, T0).summary), 'no data → asks for input instead of inventing a number');
s = U.setTrial(s, { daysLeft: 10, now: T0 });
ok(Math.round(U.daysLeft(s, T0)) === 10 && s.plan === 'trial', 'trial days set');
ok(U.estimate(s, T0).promptsLeft === null && /10 trial days/.test(U.estimate(s, T0).summary), 'days alone: no fake prompt count');
// 20 prompts over 2 days, then a pace-based projection
for (let i = 0; i < 20; i++) s = U.recordPrompt(s, { model: 'Claude Sonnet 5.5', effort: 'medium', now: T0 - 2 * DAY + i * (DAY / 10) });
let e = U.estimate(s, T0);
ok(e.byTime > 0 && e.limitedBy === 'time' && e.confidence === 'low', 'pace projection until the trial ends: ' + e.summary);
// credits: first reading, 10 prompts, second reading → unit cost learned
s = U.observeCredits(s, 1000, T0);
const w = U.promptWeight('Claude Sonnet 5.5', 'medium');
for (let i = 0; i < 10; i++) s = U.recordPrompt(s, { model: 'Claude Sonnet 5.5', effort: 'medium', now: T0 + (i + 1) * 60000 });
s = U.observeCredits(s, 1000 - 10 * w * 4, T0 + 20 * 60000); // each weight-unit really costs 4 credits
ok(Math.abs(s.unit - 4) < 0.01 && s.unitSamples === 1, 'credit cost per weight-unit is learned from two readings: ' + s.unit.toFixed(2));
e = U.estimate(s, T0 + 20 * 60000, { model: 'Claude Sonnet 5.5', effort: 'medium' });
ok(Math.abs(e.byCredits - Math.floor((1000 - 10 * w * 4) / (4 * w))) <= 1, 'prompts left on credits = credits / learned cost: ' + e.byCredits);
const eo = U.estimate(s, T0 + 20 * 60000, { model: 'Claude Opus 5.5', effort: 'high' });
ok(eo.byCredits < e.byCredits / 3, 'Opus 5.5 High burns the allowance several times faster than Sonnet Medium');
ok(e.range && e.range[0] <= e.promptsLeft && e.range[1] >= e.promptsLeft, 'estimate is a range, not a point');
// prompts sent after the last reading reduce the credits shown
const before = U.estimate(s, T0 + 21 * 60000).creditsLeft;
s = U.recordPrompt(s, { model: 'Claude Sonnet 5.5', effort: 'medium', now: T0 + 22 * 60000 });
ok(U.estimate(s, T0 + 23 * 60000).creditsLeft < before, 'credits shown drop as prompts are sent');
ok(U.estimate(s, T0 + 23 * 60000).creditsLeft >= 0, 'never negative');
// sanitising hostile storage
const bad = U.sanitize({ prompts: [{ t: 'x' }, { t: 5, w: 1e9 }], unit: -3, models: [null, { name: 'A', efforts: ['HIGH', 'nope'] }], selected: { model: 5, effort: 'zzz' } });
ok(bad.unit > 0 && bad.prompts.length === 1 && bad.prompts[0].w <= 100 && bad.models.length === 1 && bad.models[0].efforts.join() === 'high' && bad.selected.effort === '', 'corrupt storage is sanitised');
ok(U.sanitize(JSON.parse(JSON.stringify(s))).prompts.length === s.prompts.length, 'state round-trips through JSON');
ok(U.chipText(s, T0 + 23 * 60000).length < 60, 'chip text stays short');
s = U.applyScan(s, { creditsRemaining: 500, daysLeft: 3 }, T0 + 30 * 60000);
ok(Math.round(U.daysLeft(s, T0 + 30 * 60000)) === 3 && s.creditsRemaining === 500, 'a page scan updates trial days and credits');
console.log(`PASS notion usage estimator (${n} checks)`);
