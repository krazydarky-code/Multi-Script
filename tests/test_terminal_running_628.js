// SPDX-License-Identifier: GPL-3.0-or-later
// 6.28: Running tab shows environment diagnostics and a stale-bridge warning.
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', 'extension/core/terminal.js'), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };
for (const needle of [
  'svc.environment',
  'uvx ✓', 'needed by Unity/Blender', 'needed by Godot', 'Blender add-on',
  'Update pending', 'extensionVersion', 'press Restart (or run Setup once)',
]) ok(src.includes(needle), 'terminal.js missing: ' + needle);
// the environment is part of the repaint signature so changes re-render
ok(/svc\.environment \? \[svc\.environment\.python/.test(src), 'environment must be in the repaint sig');
console.log('PASS 6.28 Running tab: environment row + stale-bridge warning wired');
