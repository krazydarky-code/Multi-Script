const fs = require('fs');
const src = fs.readFileSync('extension/core/extras.js', 'utf8');
const ZSExtras = new Function(src + ';return ZSExtras;')();
const ok = (x, m) => { if (!x) throw new Error(m); };

for (const engine of ['roblox', 'unity', 'godot']) {
  const a = ZSExtras.gameIdea({ engine, genre: 'platformer', scope: 'slice', seed: 'production-seed' });
  const b = ZSExtras.gameIdea({ engine, genre: 'platformer', scope: 'slice', seed: 'production-seed' });
  ok(a.prompt === b.prompt, `${engine}: seeded generation must be deterministic`);
  ok(a.prompt.includes('PLAYER FANTASY:'), `${engine}: player fantasy missing`);
  ok(a.prompt.includes('DESIGN PILLARS:'), `${engine}: design pillars missing`);
  ok(a.prompt.includes('FIRST 10 MINUTES:'), `${engine}: onboarding arc missing`);
  ok(a.prompt.includes('SYSTEMS & CONTENT:'), `${engine}: production systems missing`);
  ok(a.prompt.includes('UX & ACCESSIBILITY:'), `${engine}: accessibility missing`);
  ok(a.prompt.includes('SCOPE CONTROL:'), `${engine}: cut order missing`);
  ok(a.prompt.includes('ACCEPTANCE TESTS:'), `${engine}: acceptance tests missing`);
  ok(a.concept && a.concept.pillars.length === 3, `${engine}: structured concept metadata missing`);
}
let combinations = 0;
for (const engine of ['auto', 'roblox', 'unity', 'godot', 'blender', 'generic'])
  for (const genre of Object.keys(ZSExtras.GENRES))
    for (const scope of Object.keys(ZSExtras.SCOPES))
      for (const twist of [true, false]) {
        const idea = ZSExtras.gameIdea({ engine, engines: ['roblox', 'godot'], genre, scope, twist,
          seed: `${engine}-${genre}-${scope}-${twist}` });
        ok(idea && idea.title && idea.prompt && idea.prompt.length > 300,
          `empty idea for ${engine}/${genre}/${scope}/${twist}`);
        combinations++;
      }
const blender = ZSExtras.gameIdea({ engine: 'blender', seed: 'asset-seed' });
ok(blender.prompt.includes('PRODUCTION WORKFLOW:'), 'Blender production workflow missing');
ok(blender.prompt.includes('QUALITY GATES:'), 'Blender quality gates missing');
ok(blender.prompt.includes('re-import'), 'Blender re-import validation missing');
ok(blender.production && blender.production.reimportRequired, 'Blender production metadata missing');
console.log(`PASS production-grade deterministic Game Idea Bot briefs (${combinations} combinations)`);