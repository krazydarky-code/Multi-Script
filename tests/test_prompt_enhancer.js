// SPDX-License-Identifier: GPL-3.0-or-later
// Auto prompt enhancer contract.
//
// The enhancer rewrites the user's own words before they are sent. That is a
// dangerous thing to do carelessly, so the invariants here are about SAFETY
// first and usefulness second:
//
//   1. the original request always survives verbatim
//   2. nothing is invented that the user did not imply
//   3. it is OFF by default and never fires twice on the same text
//   4. it never grows the prompt past its own cap
//   5. a fact that is not known is not stated
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };

let passed = 0;
const t = (name, fn) => { fn(); passed++; console.log('  ok  ' + name); };

const ZSEnhance = new Function(read('extension/core/enhancer.js') + ';return ZSEnhance;')();
const on = (mode, extra) => Object.assign({ mode, preview: true }, extra || {});

// ── 1. off by default, and off really means off ──────────────────────────
t('the enhancer is off by default and changes nothing when off', () => {
  ok(ZSEnhance.DEFAULT_SETTINGS.mode === 'off', 'default mode must be off');
  const r = ZSEnhance.enhance('make me a sword', {}, null);
  ok(r.enhanced === false && r.text === 'make me a sword', 'off mode must return the input byte-for-byte');
  ok(ZSEnhance.sanitize({ mode: 'nonsense' }).mode === 'off', 'an unknown mode must fall back to off');
});

// ── 2. the user's own words always survive ───────────────────────────────
t('the original request survives verbatim in every mode', () => {
  const req = 'Make the door open when the player touches it';
  for (const mode of ['light', 'balanced', 'thorough']) {
    const r = ZSEnhance.enhance(req, { engines: ['roblox'] }, on(mode));
    ok(r.text.includes(req), `${mode}: the original request was lost`);
    ok(r.enhanced === true, `${mode}: should have enhanced`);
  }
});

// ── 3. idempotent: never stack a second brief ────────────────────────────
t('enhancing an already-enhanced prompt is a no-op', () => {
  const first = ZSEnhance.enhance('add a coin', { engines: ['roblox'] }, on('balanced'));
  const second = ZSEnhance.enhance(first.text, { engines: ['roblox'] }, on('balanced'));
  ok(second.enhanced === false, 'a second pass must not enhance');
  ok(second.skipped === 'already-enhanced', 'a second pass must say why');
  ok(second.text === first.text, 'a second pass must return the text unchanged');
});

// ── 4. nothing is invented ───────────────────────────────────────────────
t('the enhancer invents no specifics', () => {
  const r = ZSEnhance.enhance('make a sword', {}, on('thorough'));
  // It may ASK the model to choose a size; it must not state one.
  ok(!/\b\d+\s*(studs?|px|units?)\b/i.test(r.text), 'the enhancer must not invent a measurement');
  ok(!/#[0-9a-f]{6}\b/i.test(r.text), 'the enhancer must not invent a colour');
  ok(/pick a sensible value/i.test(r.text) || /state it/i.test(r.text),
    'when a value is needed it should ask the model to choose and state one');
});

// ── 5. a stated specific suppresses the "choose one" nudge ───────────────
t('a user-supplied specific is respected, not second-guessed', () => {
  const r = ZSEnhance.enhance('make the part 12 studs wide and red', {}, on('thorough'));
  ok(!/pick a sensible value/i.test(r.text),
    'a request that already states sizes/colours must not be told to pick its own');
});

// ── 6. unknown facts are omitted, not guessed ────────────────────────────
t('an unknown environment produces no environment block', () => {
  const r = ZSEnhance.enhance('add a jump pad', {}, on('balanced'));
  ok(!/ENVIRONMENT:/.test(r.text), 'no engines known -> no ENVIRONMENT section');
  ok(!/Connected engine/i.test(r.text), 'must not claim a connection that was not reported');
  // And the honest alternative when we KNOW the check ran and found none:
  const r2 = ZSEnhance.enhance('add a jump pad', { engines: [], enginesChecked: true }, on('balanced'));
  ok(/No engine is connected/i.test(r2.text), 'a checked-and-empty result should say so');
});

// ── 7. the cap holds ─────────────────────────────────────────────────────
t('the added text never exceeds the level cap', () => {
  for (const mode of ['light', 'balanced', 'thorough']) {
    const r = ZSEnhance.enhance('x', { engines: ['roblox', 'unity'] }, on(mode));
    const level = ZSEnhance.LEVELS[mode];
    const addedPart = r.text.split(ZSEnhance.MARKER)[1] || '';
    ok(addedPart.length <= level.maxExtra + ZSEnhance.MARKER.length + 2,
      `${mode}: added text (${addedPart.length}) exceeded the cap (${level.maxExtra})`);
  }
});

// ── 8. a long, already-structured request is left alone ──────────────────
t('an already-detailed request is not rewritten', () => {
  const long = 'Please implement a shop system. ' .repeat(60);
  const r = ZSEnhance.enhance(long, { engines: ['roblox'] }, on('thorough'));
  ok(r.enhanced === false, 'a long request must be left as-is');
  ok(r.skipped === 'already-detailed', 'and should report why');
});

// ── 9. intent classification drives the done-criteria ────────────────────
t('intent is classified and selects the matching done-criteria', () => {
  const cases = [
    ['the script is broken, fix it', 'fix'],
    ['build me a castle', 'build'],
    ['change the colour to blue', 'change'],
    ['explain how this loop works', 'explain'],
    ['find every use of RemoteEvent', 'find'],
    ['the game is laggy, optimise it', 'optimise'],
  ];
  for (const [text, expect] of cases) {
    const got = ZSEnhance.classifyIntent(text);
    ok(got === expect, `"${text}" classified as ${got}, expected ${expect}`);
  }
  // "fix" beats "build" when both verbs appear.
  ok(ZSEnhance.classifyIntent('make it stop crashing') === 'fix',
    'a build verb inside a repair request must not win');
});

// ── 10. constraint rules fire on the words that matter ───────────────────
t('relevant constraints are surfaced, irrelevant ones are not', () => {
  const ui = ZSEnhance.enhance('build a shop menu', {}, on('balanced'));
  ok(/resolution|device/i.test(ui.text), 'UI work should ask about target sizes');
  const net = ZSEnhance.enhance('sync the score between players', {}, on('balanced'));
  ok(/authority|server/i.test(net.text), 'networking work should ask about authority');
  const plain = ZSEnhance.enhance('build a castle', {}, on('balanced'));
  ok(!/resolution|authority/i.test(plain.text), 'unrelated constraints must not be added');
  // At most three constraints, however many keywords match.
  const multi = ZSEnhance.enhance('make a mobile ui that saves data and is secure and fast', {}, on('thorough'));
  const constraintSection = (multi.text.match(/CONSTRAINTS:\n([\s\S]*?)(?:\n\n[A-Z][A-Z -]+:|$)/) || [,''])[1];
  const bullets = (constraintSection.match(/^- /gm) || []).length;
  ok(bullets <= 3, `constraint list must be capped at 3, got ${bullets}`);
});

// ── 11. describe() is truthful ───────────────────────────────────────────
t('describe() reflects the real settings', () => {
  ok(/Off/.test(ZSEnhance.describe(null)), 'off must be described as off');
  const s = ZSEnhance.describe({ mode: 'balanced', preview: true });
  ok(/Balanced/.test(s) && /review/i.test(s), 'preview mode must be stated');
  const auto = ZSEnhance.describe({ mode: 'balanced', preview: false });
  ok(/Sends automatically/i.test(auto), 'non-preview mode must be stated');
});

// ── 12. provider-neutral domain strategy and independent fact toggles ─────
t('domain strategy is provider-neutral and fact toggles are real', () => {
  const ui = ZSEnhance.enhance(
    'fix the code for the settings menu layout and keyboard focus',
    { engines: ['unity'], toolCount: 12, toolNames: ['manage_editor', 'manage_scene'] },
    { ...on('thorough'), injectApproach: true, injectToolFacts: true }
  );
  ok(ui.domains.includes('ui') && ui.domains.includes('code'), 'UI/code domains should both be detected');
  ok(/keyboard|focus/i.test(ui.text) && /manage_editor/.test(ui.text), 'approach and live tool facts should be included');
  const noTools = ZSEnhance.enhance(
    'fix the settings menu layout',
    { engines: ['unity'], toolCount: 12, toolNames: ['manage_editor'] },
    { ...on('thorough'), injectToolFacts: false }
  );
  ok(!/12 command|manage_editor/.test(noTools.text), 'tool facts toggle must suppress count and names');
  ok(!/deepseek|chatgpt|notion|gemini/i.test(ui.text), 'enhancement must not depend on a provider');
});

// ── 13. weak prompts gain safe execution structure, not invented style ────
t('weak prompts receive reversible project-aware defaults and a strict quality gate', () => {
  const r = ZSEnhance.enhance('make my game cool', { engines: ['roblox'] }, on('thorough'));
  ok(r.requestProfile && r.requestProfile.weak, 'weak request profile must be exposed');
  ok(r.added.includes('smart-defaults') && r.added.includes('quality-gate'), 'missing weak-prompt structure');
  ok(/preserve its established architecture/i.test(r.text), 'must inspect and preserve project conventions');
  ok(/No placeholders|native read-back/i.test(r.text), 'must require a real completed result');
  ok(!/low-poly|neon|medieval|battle pass/i.test(r.text), 'must not invent an art direction or product design');
});

console.log(`\ntest_prompt_enhancer: ${passed} sections passed`);
