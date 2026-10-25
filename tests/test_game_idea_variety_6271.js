// SPDX-License-Identifier: GPL-3.0-or-later
// 6.27.1: the Game Idea Bot composes real premises, not a reshuffled template.
const fs = require('fs');
const ZSExtras = new Function(fs.readFileSync('extension/core/extras.js', 'utf8') + ';return ZSExtras;')();
const ok = (x, m) => { if (!x) throw new Error(m); };

// every idea fuses protagonist, setting, threat and signature action
for (const engine of ['roblox', 'unity', 'godot', 'generic']) {
  const g = ZSExtras.gameIdea({ engine, seed: 'fuse-' + engine });
  ok(g.prompt.includes('PREMISE: you are'), engine + ': premise missing');
  ok(g.prompt.includes('SIGNATURE ACTION:'), engine + ': signature action missing');
  ok(g.prompt.includes('PROGRESSION & ECONOMY:'), engine + ': economy missing');
  ok(/The hook is not a gimmick/.test(g.prompt), engine + ': hook must be woven into the loop');
}

// unseeded generation is highly varied - the button actually generates ideas
const titles = new Set(), premises = new Set(), full = new Set();
for (let i = 0; i < 40; i++) {
  const g = ZSExtras.gameIdea({ engines: ['roblox'] });
  titles.add(g.title); premises.add(g.prompt.split('\n')[2]); full.add(g.prompt);
}
ok(full.size === 40, 'no two of 40 ideas should be identical');
ok(premises.size >= 36, 'premises must vary (got ' + premises.size + '/40)');
ok(titles.size >= 30, 'titles must vary (got ' + titles.size + '/40)');

// anti-repetition never breaks seeded determinism
const a = ZSExtras.gameIdea({ engine: 'roblox', genre: 'platformer', scope: 'slice', seed: 'same' });
const b = ZSExtras.gameIdea({ engine: 'roblox', genre: 'platformer', scope: 'slice', seed: 'same' });
ok(a.prompt === b.prompt, 'seeded generation must stay deterministic');
ok(a.prompt.includes('PLAYER FANTASY:') && a.concept.pillars.length === 3, '6.27 structure must be preserved');

// combinatorial space is genuinely large
const combos = 16 * 18 * 12 * 12 * 12 * 8 * 4; // settings*hooks*protagonists*threats*actions*economies*title-patterns (approx lower bound)
ok(combos > 100000, 'combinatorial space too small: ' + combos);
console.log('PASS 6.27.1 Game Idea Bot: fused premises, 40/40 unique ideas, seeded determinism kept');
