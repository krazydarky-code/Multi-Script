// SPDX-License-Identifier: GPL-3.0-or-later
// JSON-only transport contract. The extension can read exactly ONE thing out of
// a model's reply: a plain-text {"command":…,"params":{…}} object. This test
// pins that contract end to end - the prompt that teaches it, the reminder that
// re-anchors it mid-session, the parser that reads it, and the core guards that
// make a nearly-right envelope still work. Roblox is the strictest consumer, and
// Godot is the engine this release focuses on, so both are exercised.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const ZS = new Function(read('extension/core/config.js') + ';return ZS;')();
const ZSParse = new Function(read('extension/core/parser.js') + ';return ZSParse;')();
const ok = (c, m) => { if (!c) throw new Error(m); };

// ── 1. The prompt states the contract, unmistakably ──────────────────────
const prompt = ZS.buildSystemPrompt({ siteName: 'DeepSeek' });
ok(prompt.includes('JSON-ONLY CONTRACT'), 'the system prompt must carry an explicit JSON-only contract');
for (const rule of [
  'exactly ONE plain-text JSON object',
  'No nesting wrappers',
  'Do NOT emit your own native tool-call syntax',
  'ONE object per reply',
  'Roblox Studio is the strictest consumer',
  'datamodel_type of exactly "Edit", "Server" or "Client"',
  'params.edits as a JSON ARRAY of objects',
  'Same rule for Godot',
]) ok(prompt.includes(rule), `the JSON contract is missing: "${rule}"`);
// The legacy fenced-block transport must never be advertised again.
ok(!prompt.includes('every command goes inside a fenced code block'), 'a legacy fenced-code transport is still advertised');
ok(!prompt.includes('SPECIAL FORMAT FOR execute_luau'), 'a legacy execute_luau special format is still advertised');

// ── 2. The periodic reminder re-anchors the same contract ────────────────
const reminder = ZS.toolsReminder([{ name: 'execute_luau', description: 'x', inputSchema: { properties: { code: { type: 'string' } } } }]);
ok(reminder.includes('exactly ONE plain-text JSON object'), 'the reminder must restate the JSON-only rule');
ok(reminder.includes('no XML/DSML/function-call'), 'the reminder must explicitly forbid native markup');
ok(reminder.includes('One command per reply'), 'the reminder must restate the one-command rule');
ok(reminder.includes('execute_luau'), 'the reminder must still list the live commands');

// ── 3. Godot guidance is concrete and uses the same envelope ─────────────
ok(prompt.includes('godot-mcp-orchestrator'), 'the Godot orchestrator skill must be referenced');
for (const rule of ['get_godot_version', 'get_project_info', 'run_project', 'get_debug_output', 'stop_project', 'case-sensitive']) {
  ok(prompt.includes(rule), `the Godot guidance is missing: ${rule}`);
}

// ── 4. The parser reads the live command shapes, Roblox and Godot ────────
const live = [
  '{"command":"list_commands","params":{}}',
  '{"command":"get_studio_state","params":{}}',
  '{"command":"script_read","params":{"target_file":"game.ServerScriptService.Main"}}',
  '{"command":"execute_luau","params":{"code":"return game.PlaceId","datamodel_type":"Edit"}}',
  '{"command":"multi_edit","params":{"datamodel_type":"Edit","edits":[{"file_path":"game.Workspace.A","old_string":"","new_string":"return 1"}]}}',
  '{"command":"run_project","params":{"projectPath":"/home/me/game/project.godot"}}',
  '{"command":"get_debug_output","params":{}}',
];
for (const text of live) {
  const calls = ZSParse.parseToolCalls(text);
  ok(calls.length === 1, `expected exactly one call from ${text}, got ${calls.length}`);
  ok(!!calls[0].tool, `no tool name parsed from ${text}`);
  ok(calls[0].arguments && typeof calls[0].arguments === 'object', `no params object parsed from ${text}`);
}
// A nested array-of-objects param survives intact (Roblox multi_edit).
const me = ZSParse.parseToolCalls('{"command":"multi_edit","params":{"datamodel_type":"Edit","edits":[{"file_path":"game.Workspace.A","old_string":"","new_string":"local a = {\\"x\\":1}"}]}}')[0];
ok(me.arguments.edits.length === 1 && me.arguments.edits[0].file_path === 'game.Workspace.A', 'multi_edit edits array was mangled');
ok(me.arguments.edits[0].new_string.includes('"x"'), 'escaped quotes inside a code string were mangled');

// ── 5. Core guards: a nearly-right envelope still runs ───────────────────
const main = read('extension/core/main.js');
ok(main.includes('tool.unwrapEnvelope'), 'the core must unwrap a double-wrapped envelope');
ok(/if \(_depth < 3/.test(main), 'the envelope unwrap must be depth-bounded so it cannot recurse');
ok(main.includes('args.datamodel_type = "Edit"'), 'execute_luau must default datamodel_type to Edit');
ok(main.includes('args.datamodel_type = "Client"'), 'the player-input tools must default datamodel_type to Client');
ok(main.includes('ZS.toolsReminder(scoped)'), 'the periodic reminder must still be injected');
// The wrong-key / raw-arguments / DSML cases must all be caught and nudged.
for (const guard of ['cmd.wrongKey', 'reason: "envelope"', 'reason: "luaOpener"', 'DSML_RE']) {
  ok(main.includes(guard) || read('extension/core/parser.js').includes(guard), `missing malformed-envelope guard: ${guard}`);
}
// The native markup dialect is normalised, never advertised.
ok(ZSParse.DSML_RE.test('<|DSML|>tool_calls>'), 'the native markup dialect must still be detectable');
const nativeMarkup = [
  '<|DSML|>tool_calls>',
  '<|DSML|>invoke name="script_read">',
  '<|DSML|>parameter name="target_file" string="true">game.Workspace.A</|DSML|>parameter>',
  '</|DSML|>invoke>',
  '</|DSML|>tool_calls>',
].join('\n');
const normalized = ZSParse.parseNativeToolMarkup(nativeMarkup);
ok(normalized.length === 1 && normalized[0].tool === 'script_read' && normalized[0].arguments.target_file === 'game.Workspace.A',
  'a native-markup tool call must still be normalised into one call');
ok(!prompt.includes('DSML') || !/use\s+<\|DSML\|>/i.test(prompt), 'the native markup dialect must never be taught to a model');

console.log('PASS JSON-only transport contract: prompt + reminder rules, 7 live Roblox/Godot envelopes parsed, nested edits array and escaped quotes intact, double-envelope unwrap, engine defaults, malformed-envelope guards');
