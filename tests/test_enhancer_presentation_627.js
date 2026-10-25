// SPDX-License-Identifier: GPL-3.0-or-later
// 6.27: gameplay domain was dead code; world/game builds lacked a first-view gate.
const fs = require('fs'), path = require('path');
const read = (p) => fs.readFileSync(path.join(path.resolve(__dirname, '..'), p), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };
const ZSEnhance = new Function(read('extension/core/enhancer.js') + ';return ZSEnhance;')();
const on = (mode, extra) => Object.assign({ mode, preview: true }, extra || {});

// gameplay domain is now real and drives the vertical-slice default
const game = ZSEnhance.enhance('make me a game', { engines: ['roblox'] }, on('thorough'));
ok(game.domains.includes('gameplay'), 'gameplay domain must be detected');
ok(/complete playable loop/i.test(game.text), 'gameplay approach line missing');
ok(/vertical slice/i.test(game.text), 'weak game prompts must get the vertical-slice default');
ok(/first view/i.test(game.text) && /flat slab/i.test(game.text), 'world first-view quality gate missing');

// the flat-world gate also fires on world-domain requests
const world = ZSEnhance.enhance('build me a world map with terrain', {}, on('thorough'));
ok(world.domains.includes('world') && /real player camera/i.test(world.text), 'world requests must be camera-verified');

// non-game requests are untouched
const castle = ZSEnhance.enhance('build a castle', {}, on('balanced'));
ok(!castle.domains.includes('gameplay'), 'castle is not gameplay');
ok(!/resolution|authority/i.test(castle.text), 'unrelated constraints must not appear');
const net = ZSEnhance.enhance('sync the score between players', {}, on('balanced'));
ok(!net.domains.includes('gameplay'), 'score sync is networking, not gameplay');
ok(/authority|server/i.test(net.text), 'networking constraint must still fire');

// no invented specifics and no provider names leak through the new lines
ok(!/\b\d+\s*(studs?|px|units?)\b/i.test(game.text) && !/#[0-9a-f]{6}\b/i.test(game.text), 'no invented measurements or colours');
ok(!/deepseek|chatgpt|notion|gemini|claude/i.test(game.text), 'enhancement must stay provider-neutral');
ok(!/low-poly|neon|medieval|battle pass/i.test(game.text), 'no invented art direction');

// caps still hold with the extra line present
for (const mode of ['light', 'balanced', 'thorough']) {
  const r = ZSEnhance.enhance('make me a game', { engines: ['roblox'] }, on(mode));
  const level = ZSEnhance.LEVELS[mode];
  const addedPart = r.text.split(ZSEnhance.MARKER)[1] || '';
  ok(addedPart.length <= level.maxExtra + ZSEnhance.MARKER.length + 2, mode + ' exceeded cap');
}
// idempotence unaffected
const again = ZSEnhance.enhance(game.text, { engines: ['roblox'] }, on('thorough'));
ok(again.enhanced === false && again.text === game.text, 'second pass must be a no-op');

console.log('PASS 6.27 enhancer: gameplay domain live, first-view world gate, no regressions');
