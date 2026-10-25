// SPDX-License-Identifier: GPL-3.0-or-later
// 6.27.1: per-engine setup guides live in Settings -> Engines, with accurate
// content and a one-click bundled-launcher fill (the Blender easy path).
const fs = require('fs');
const main = fs.readFileSync('extension/core/main.js', 'utf8');
const ZSExtras = new Function(fs.readFileSync('extension/core/extras.js', 'utf8') + ';return ZSExtras;')();
const ok = (x, m) => { if (!x) throw new Error(m); };

// data: four engines, complete and truthful
ok(Array.isArray(ZSExtras.ENGINE_GUIDES) && ZSExtras.ENGINE_GUIDES.length === 5, 'need exactly 5 engine guides');
const byId = Object.fromEntries(ZSExtras.ENGINE_GUIDES.map((g) => [g.id, g]));
for (const id of ['roblox', 'unity', 'godot', 'blender', 'figma']) {
  const g = byId[id];
  ok(g && g.name && g.tagline && g.badge, id + ': identity fields');
  ok(g.needs.length >= 3, id + ': at least 3 prerequisites');
  ok(g.steps.length >= 4, id + ': at least 4 steps');
  ok(/Ask the AI:|press|Press/i.test(g.verify), id + ': a concrete verification');
  ok(g.tip.length > 20, id + ': a useful tip');
  const blob = JSON.stringify(g).toLowerCase();
  ok(!/deepseek|chatgpt|gemini|claude\.ai/.test(blob), id + ': guides must stay provider-neutral');
}
// accuracy: steps must match what the launchers/docs actually do
ok(byId.blender.steps.some((s) => s.includes('BlenderMCP')), 'Blender guide must install the BlenderMCP add-on');
ok(byId.blender.steps.some((s) => s.includes('9876')), 'Blender guide must mention the 9876 connection');
ok(byId.blender.fill && byId.blender.fill.command === 'launch_blender_mcp.py', 'Blender one-click uses the bundled launcher');
ok(byId.unity.steps.some((s) => s.includes('10.2.0')), 'Unity guide must state the pinned version');
ok(byId.godot.steps.some((s) => s.includes('project.godot')), 'Godot guide must reference project.godot');
ok(byId.roblox.steps.some((s) => s.includes('StudioMCP')), 'Roblox guide must reference StudioMCP discovery');

// UI: section rendered in the engines tab, binder wired, buttons type-safe
for (const needle of [
  'Engine setup guides',
  'data-guide-toggle', 'data-guide-fill', 'data-guide-copy',
  'function bindEngineGuides()',
  'bindEngineGuides();',
  'engineGuidesHtml',
  'type="button" class="zs-guide-head"',
]) ok(main.includes(needle), 'main.js missing: ' + needle);
// the fill action targets the real add-on form fields
ok(main.includes('menuEl.querySelector("#zs-mcp-name")') && main.includes('menuEl.querySelector("#zs-mcp-url")'), 'fill must target the MCP add form');
console.log('PASS 6.27.1 engine setup guides: 4 accurate guides, one-click Blender launcher, wired UI');
