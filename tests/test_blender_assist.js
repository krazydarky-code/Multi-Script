// 6.28.1: opt-in Blender asset tasks in the prompt enhancer and an opt-in
// Blender asset plan in the Game Idea Bot.
const fs = require('fs');
const enhSrc = fs.readFileSync('extension/core/enhancer.js', 'utf8');
const extSrc = fs.readFileSync('extension/core/extras.js', 'utf8');
const mainSrc = fs.readFileSync('extension/core/main.js', 'utf8');
const ZSEnhance = new Function(enhSrc + ';return ZSEnhance;')();
const ZSExtras = new Function(extSrc + ';return ZSExtras;')();
const ok = (x, m) => { if (!x) throw new Error(m); };

// ── Enhancer: off by default, nothing changes ────────────────────────────
const req = 'build me a small castle level with a door that opens';
const offRun = ZSEnhance.enhance(req, { engines: ['roblox'] }, { mode: 'balanced' });
ok(offRun.enhanced && !/BLENDER ASSET TASKS/.test(offRun.text), 'Blender tasks must be off by default');
ok(!ZSEnhance.DEFAULT_SETTINGS.blenderAssist, 'blenderAssist must default to false');

// ── Enhancer: enabled → Blender tasks appear, for every strength ─────────
for (const mode of ['light', 'balanced', 'thorough']) {
  const r = ZSEnhance.enhance(req, { engines: ['roblox', 'blender'] }, { mode, blenderAssist: true });
  ok(r.enhanced, mode + ': enhancement lost when Blender is enabled');
  ok(r.text.includes('BLENDER ASSET TASKS:'), mode + ': Blender task section missing');
  ok(r.text.includes('import'), mode + ': import/verify task missing');
  const level = ZSEnhance.LEVELS[mode];
  const added = r.text.split('---')[1] || '';
  ok(added.length <= level.maxExtra + ZSEnhance.BLENDER_BONUS + ZSEnhance.MARKER.length + 2,
    mode + ': added text exceeded cap + Blender bonus (' + added.length + ')');
  // The section must survive whole - never truncated mid-line.
  ok(/player or camera view/.test(r.text), mode + ': Blender section was truncated');
}

// ── Enhancer: honesty rules still hold with Blender on ───────────────────
for (const mode of ['light', 'balanced', 'thorough']) {
  const r = ZSEnhance.enhance(req, { engines: ['roblox', 'blender'] }, { mode, blenderAssist: true });
  ok(!/\b\d+\s*(studs?|px|units?)\b/i.test(r.text), mode + ': invented a measurement');
  ok(!/#[0-9a-f]{6}\b/i.test(r.text), mode + ': invented a colour');
  ok(!/low-poly|neon|medieval|battle pass/i.test(r.text), mode + ': invented an art direction');
}

// ── Enhancer: question/lookup intents never get asset tasks ──────────────
for (const q of ['explain how the door script works', 'where is the spawn point']) {
  const r = ZSEnhance.enhance(q, { engines: ['blender'] }, { mode: 'thorough', blenderAssist: true });
  ok(!r.enhanced || !/BLENDER ASSET TASKS/.test(r.text), 'asset tasks leaked into a question/lookup: ' + q);
}

// ── Enhancer: connected vs not connected phrasing ────────────────────────
const conn = ZSEnhance.enhance(req, { engines: ['roblox', 'blender'] }, { mode: 'balanced', blenderAssist: true });
ok(/Blender is connected/.test(conn.text), 'connected Blender should be named as connected');
const disc = ZSEnhance.enhance(req, { engines: ['roblox'] }, { mode: 'balanced', blenderAssist: true });
ok(/not connected right now/.test(disc.text) && /Settings > Engines/.test(disc.text), 'disconnected Blender must say how to connect it');

// ── Enhancer: sanitize + describe round-trip ─────────────────────────────
ok(ZSEnhance.sanitize({ blenderAssist: 1 }).blenderAssist === true, 'sanitize must coerce blenderAssist');
ok(ZSEnhance.sanitize(null).blenderAssist === false, 'sanitize default must be false');
ok(/Blender asset tasks/.test(ZSEnhance.describe({ mode: 'balanced', blenderAssist: true })), 'describe() must mention Blender when on');
ok(!/Blender asset tasks/.test(ZSEnhance.describe({ mode: 'balanced' })), 'describe() must not mention Blender when off');
ok(!/Blender asset tasks/.test(ZSEnhance.describe({ mode: 'off', blenderAssist: true })), 'describe(off) must stay untouched');

// ── Enhancer: idempotence + settings survival ────────────────────────────
const twice = ZSEnhance.enhance(conn.text, { engines: ['blender'] }, { mode: 'thorough', blenderAssist: true });
ok(!twice.enhanced && twice.skipped === 'already-enhanced', 'second pass must stay a no-op');

// ── Game Idea Bot: option off by default ─────────────────────────────────
const plain = ZSExtras.gameIdea({ engine: 'roblox', genre: 'platformer', scope: 'slice', seed: 'bl-opt' });
ok(!/BLENDER ASSET PLAN/.test(plain.prompt), 'asset plan must be off by default');
ok(plain.production.blenderAssetPlan === 0, 'metadata must report no plan by default');

// ── Game Idea Bot: enabled → the brief enlarges with concrete tasks ──────
const withBl = ZSExtras.gameIdea({ engine: 'roblox', genre: 'platformer', scope: 'slice', seed: 'bl-opt', blender: true });
ok(/BLENDER ASSET PLAN \(models generated in Blender\):/.test(withBl.prompt), 'asset plan section missing');
ok(withBl.prompt.length > plain.prompt.length, 'enabling Blender must enlarge the prompt');
ok(/hero subject/.test(withBl.prompt) && /modular environment kit/.test(withBl.prompt), 'plan must model the hero and the world');
ok(/glTF\/FBX/.test(withBl.prompt) && /re-import/.test(withBl.prompt), 'plan must include export + re-import verification');
ok(/author hero meshes in the connected Blender/.test(withBl.prompt), 'enabling the option must also add the tech bullet even when Blender is not connected');
ok(withBl.production.blenderAssetPlan === 5, 'metadata must count the plan tasks');
// The plan must reuse THIS idea's own content.
ok(withBl.prompt.includes(withBl.concept.setting), 'plan must build the kit for the idea setting');

// ── Game Idea Bot: seeded determinism with the option on ─────────────────
const a = ZSExtras.gameIdea({ engine: 'unity', seed: 'bl-seed', blender: true });
const b = ZSExtras.gameIdea({ engine: 'unity', seed: 'bl-seed', blender: true });
ok(a.prompt === b.prompt, 'seeded generation must stay deterministic with Blender on');

// ── Game Idea Bot: Blender-as-engine path is unchanged ───────────────────
const blEngine = ZSExtras.gameIdea({ engine: 'blender', seed: 'asset-seed', blender: true });
ok(blEngine.prompt.includes('PRODUCTION WORKFLOW:') && !/BLENDER ASSET PLAN/.test(blEngine.prompt),
  'Blender asset brief must not gain a duplicate plan');

// ── UI wiring ────────────────────────────────────────────────────────────
ok(/id="ms-enhance-blender"/.test(mainSrc) && /blenderAssist:\s*ba\.checked/.test(mainSrc),
  'enhancer panel Blender toggle is not wired');
ok(/id="ms-idea-blender"/.test(mainSrc) && /ideaOpts\.blender\s*=\s*ib\.checked/.test(mainSrc),
  'ideas panel Blender toggle is not wired');
ok(/ideaOpts\s*=\s*\{[^}]*blender:\s*false/.test(mainSrc), 'ideaOpts must default blender to false');

console.log('PASS Blender assist: enhancer tasks + game-idea asset plan (opt-in, capped, honest, deterministic)');
