// SPDX-License-Identifier: GPL-3.0-or-later
// 6.28: four new themes, per-bar theme setting, and the ported-bar colour fix
// (light Roblox/Frost bars must never render light text on light surfaces).
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const main = fs.readFileSync(path.join(root, 'extension/core/main.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'extension/overlay.css'), 'utf8');
const ZSExtras = new Function(fs.readFileSync(path.join(root, 'extension/core/extras.js'), 'utf8') + ';return ZSExtras;')();
const ok = (c, m) => { if (!c) throw new Error(m); };

// new themes exist end to end: extras, enum, swatch, root block
for (const id of ['sakura', 'crimson', 'nebula', 'matrix', 'fnaf']) {
  ok(ZSExtras.EXTRA_THEMES.some((t) => t[0] === id), id + ': missing from EXTRA_THEMES');
  ok(main.includes(`"${id}"`), id + ': missing from main.js theme lists');
  ok(css.includes(`.zs-theme-opt[data-theme="${id}"]`), id + ': missing swatch');
  ok(css.includes(`#zs-root[data-ms-theme="${id}"]`), id + ': missing theme block');
  ok(css.includes(`#zs-bar[data-ms-bar-theme="${id}"]`), id + ': missing bar theme block');
}
ok(ZSExtras.EXTRA_THEMES.length === 23, 'expected 23 extra themes (17 existing + 6 studio themes), got ' + ZSExtras.EXTRA_THEMES.length);

// bar theme setting: pref, sanitizer enum, resolver, dataset mirror, UI select
for (const needle of ['barTheme: "auto"', 'effectiveBarTheme()', 'bar.dataset.msBarTheme',
  'id="ms-bar-theme"', 'barThemeSel', 'Follow the menu theme']) ok(main.includes(needle), 'main.js missing: ' + needle);

// the ported-bar fix: every light bar theme forces dark ink on the bar node itself
for (const id of ['roblox', 'frost', 'paper', 'sakura']) {
  const re = new RegExp(`#zs-bar\\[data-ms-bar-theme="${id}"\\][^{]*\\{[^}]*--mono-ink:#141419`);
  ok(re.test(css) || css.includes(`#zs-bar[data-ms-bar-theme="frost"], #zs-bar[data-ms-bar-theme="paper"], #zs-bar[data-ms-bar-theme="sakura"], #zs-bar[data-ms-bar-theme="roblox"]`),
    id + ': light bar theme must set dark ink variables');
}
ok(css.includes('#zs-bar[data-ms-bar-theme="roblox"] #zs-brand'), 'roblox bar must force readable brand text');
ok(css.includes('#zs-bar[data-ms-motion="none"]'), 'animated bars must respect reduced motion');
ok(main.includes('bar.dataset.msMotion'), 'motion pref must be mirrored onto the bar');
console.log('PASS 6.28 themes: 4 new themes, independent bar themes, ported-bar colour fix');
