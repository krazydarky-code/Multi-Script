// SPDX-License-Identifier: GPL-3.0-or-later
// 6.36: Code mode + add-ons, workspace tool catalogue, and the bar theme/page clash fix.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const main = fs.readFileSync(path.join(root, 'extension/core/main.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'extension/overlay.css'), 'utf8');
const X = new Function(fs.readFileSync(path.join(root, 'extension/core/extras.js'), 'utf8') + ';return ZSExtras;')();
const ok = (c, m) => { if (!c) throw new Error(m); };
const d = X.sanitizeSoftware({});
ok(d.mode === 'build' && d.addons.skills === true && d.addons.engines === false && d.addons.mcp === false, 'defaults');
const c = X.sanitizeSoftware({ enabled: true, mode: 'code', addons: { engines: true, mcp: 'yes' } });
ok(c.mode === 'code' && c.addons.engines === true && c.addons.mcp === false, 'sanitize addons');
ok(X.sanitizeSoftware({ mode: 'evil' }).mode === 'build', 'bad mode rejected');
const p = X.softwarePrompt('DeepSeek', c);
ok(p.includes('CODE MODE') && p.includes('ms_ws_check') && p.includes('ENGINES ADD-ON') && !p.includes('ms_ws_create_project'), 'code prompt');
const b = X.softwarePrompt('DeepSeek', X.sanitizeSoftware({ enabled: true }));
ok(b.includes('SOFTWARE BUILDER') && b.includes('ms_ws_create_project') && !b.includes('ENGINES ADD-ON'), 'build prompt');
ok(X.softwareAllows(c, 'ms_ws_patch', 'zeroscript') && !X.softwareAllows(c, 'ms_ws_configure', 'zeroscript'), 'ws tools');
ok(X.softwareAllows(c, 'ms_critic_review', 'zeroscript') && X.softwareAllows(c, 'get_scene', 'unity'), 'skills + engines add-ons');
ok(!X.softwareAllows(X.sanitizeSoftware({ addons: { skills: false } }), 'ms_critic_review', 'zeroscript'), 'skills off');
ok(!X.softwareAllows(d, 'get_scene', 'unity') && !X.softwareAllows(d, 'ms_roblox_build_part', 'zeroscript'), 'engines off by default');
ok(!X.softwareAllows(d, 'x', 'github') && X.softwareAllows(X.sanitizeSoftware({ addons: { mcp: true } }), 'x', 'github'), 'mcp add-on');
const rt = fs.readFileSync(path.join(root, 'runtime/software_workspace.py'), 'utf8');
for (const [n] of X.WS_TOOLS) ok(rt.includes(`"name": "${n}"`), 'runtime missing ' + n);
for (const n of ['data-sw-mode', 'ms-sw-ad-skills', 'ms-sw-ad-engines', 'ms-sw-ad-mcp', 'softwareAllowsTool', 'mode: s.mode === "code"', '‹› Code'])
  ok(main.includes(n), 'main.js missing ' + n);
// bar clash fix
ok(main.includes('bar.dataset.msBarClash') && main.includes('filter((c) => !/^zs-|^ms-/.test(c))'), 'clash flag + page hint fix');
ok(css.includes('[data-ms-bar-clash="1"]') && css.indexOf('[data-ms-bar-clash="1"]') < css.indexOf('/* Distinctive bar looks */'), 'clash css before distinctive looks');
console.log('PASS 6.36 Code mode, add-ons, workspace catalogue and bar clash fix');
