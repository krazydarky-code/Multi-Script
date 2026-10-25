// SPDX-License-Identifier: GPL-3.0-or-later
// Non-Roblox engine command layer regression.
//
// The transport is plain JSON for every engine (MCP is JSON-RPC; every tool takes
// JSON-schema'd params), so what this file pins is the VOCABULARY: the exact tool
// names and required parameter spellings, the action-dispatch indirection that
// Unity needs, the curated usage notes, the engine-aware prompt, and the repair
// that stops the classic Unity failure ("get_hierarchy" written as a command).
//
// The Godot tool list and its required parameters below are copied from the
// PUBLISHED package (npm pack @coding-solo/godot-mcp@0.1.1, build/index.js
// inputSchema). They are asserted literally on purpose: if a future edit invents a
// tool or renames a parameter, this fails instead of shipping a hallucinated API.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };

const ZSEngine = new Function(read('extension/core/engines.js') + ';return ZSEngine;')();
const ZS = new Function('ZSEngine', read('extension/core/config.js') + ';return ZS;')(ZSEngine);
const ZSParse = new Function(read('extension/core/parser.js') + ';return ZSParse;')();

// ── 1. Godot: exact tool set and required params [schema] ────────────────
const GODOT_EXPECTED = {
  launch_editor: ["projectPath"],
  run_project: ["projectPath"],
  get_debug_output: [],
  stop_project: [],
  get_godot_version: [],
  list_projects: ["directory"],
  get_project_info: ["projectPath"],
  create_scene: ["projectPath", "scenePath"],
  add_node: ["projectPath", "scenePath", "nodeType", "nodeName"],
  load_sprite: ["projectPath", "scenePath", "nodePath", "texturePath"],
  export_mesh_library: ["projectPath", "scenePath", "outputPath"],
  save_scene: ["projectPath", "scenePath"],
  get_uid: ["projectPath", "filePath"],
  update_project_uids: ["projectPath"],
};
const godot = ZSEngine.ENGINES.godot.tools;
ok(Object.keys(godot).length === Object.keys(GODOT_EXPECTED).length,
  `Godot tool count drifted: ${Object.keys(godot).length} vs ${Object.keys(GODOT_EXPECTED).length}`);
for (const [name, req] of Object.entries(GODOT_EXPECTED)) {
  ok(godot[name], `Godot tool missing from the registry: ${name}`);
  ok(JSON.stringify(godot[name].req) === JSON.stringify(req),
    `Godot required params drifted for ${name}: ${JSON.stringify(godot[name].req)} vs ${JSON.stringify(req)}`);
  ok(ZSEngine.noteFor(name).length > 40, `Godot tool ${name} has no curated note`);
}
// The two traps that actually break real calls.
ok(ZSEngine.noteFor("list_projects").includes("directory") && ZSEngine.noteFor("list_projects").includes("NOT projectPath"),
  'the list_projects note must call out that it takes `directory`, not projectPath');
ok(/ABSOLUTE path of the folder that CONTAINS project\.godot/.test(ZSEngine.noteFor("run_project")),
  'the run_project note must spell out what projectPath has to be');
ok(/stop_project/.test(ZSEngine.noteFor("run_project")), 'the run_project note must tell the model to stop the project afterwards');

// ── 2. Unity: action-dispatch integrity [ref] ────────────────────────────
const unity = ZSEngine.ENGINES.unity.tools;
ok(Object.keys(unity).length >= 30, `Unity tool count looks wrong: ${Object.keys(unity).length}`);
const dispatchTools = Object.entries(unity).filter(([, v]) => v.dispatch).map(([k]) => k);
ok(dispatchTools.length >= 15, `expected many action-dispatch Unity tools, found ${dispatchTools.length}`);
for (const t of dispatchTools) {
  const acts = ZSEngine.actionsOf(t);
  ok(acts.length > 0, `action-dispatch tool ${t} has no actions registered`);
  ok(ZSEngine.noteFor(t).includes("ACTION-DISPATCH"), `${t} must carry an ACTION-DISPATCH note`);
}
// INTERNAL CONSISTENCY: no action may point at a tool that is not in the registry.
for (const [action, owners] of Object.entries(ZSEngine.ACTION_OWNERS)) {
  for (const o of owners) ok(unity[o], `action "${action}" points at unknown tool "${o}"`);
}
// Flat tools must NOT be flagged as dispatch, or we would demand a bogus action.
for (const t of ["create_script", "validate_script", "refresh_unity", "run_tests", "get_sha", "batch_execute", "find_gameobjects"]) {
  ok(!unity[t].dispatch, `${t} must not be action-dispatch`);
  ok(ZSEngine.actionsOf(t).length === 0, `${t} must have no registered actions`);
}
ok(ZSEngine.ENGINES.unity.actions, 'the Unity engine record must expose its action vocabulary');
ok(ZSEngine.noteFor("manage_scene").includes("ACTION-DISPATCH"), 'manage_scene must explain the dispatch shape');
ok(ZSEngine.noteFor("manage_scene").includes("get_hierarchy"), 'manage_scene must name its common actions');
ok(ZSEngine.noteFor("read_console").includes("ONLY way to see them"), 'read_console must say it is the only way to see errors');
ok(ZSEngine.noteFor("run_tests").includes("does NOT wait") && ZSEngine.noteFor("run_tests").includes("get_test_job"),
  'run_tests must explain the job-polling pattern');

// ── 3. resolveAction: the repair that fixes the classic Unity failure ────
const advertise = (...names) => (n) => names.includes(n);
const liveUnity = Object.keys(unity);
const hasUnity = advertise(...liveUnity);
{
  // Unambiguous action, single owner advertised -> repaired.
  const r = ZSEngine.resolveAction("play", {}, advertise("manage_editor"));
  ok(r.ok && r.tool === "manage_editor" && r.action === "play", `play was not repaired: ${JSON.stringify(r)}`);
  ok(r.params.action === "play", 'the repaired call must carry the action');
  // Genuinely ambiguous -> refuse with candidates, never guess.
  const amb = ZSEngine.resolveAction("get_info", {}, advertise("manage_asset", "manage_prefabs"));
  ok(!amb.ok && amb.reason === "ambiguous", `get_info should be ambiguous: ${JSON.stringify(amb)}`);
  ok(amb.candidates.length === 2 && amb.candidates.includes("manage_asset") && amb.candidates.includes("manage_prefabs"),
    `ambiguous candidates wrong: ${JSON.stringify(amb.candidates)}`);
  // Ambiguous in the registry but only ONE owner live -> resolved.
  const one = ZSEngine.resolveAction("get_info", {}, advertise("manage_prefabs"));
  ok(one.ok && one.tool === "manage_prefabs", `single live owner should resolve: ${JSON.stringify(one)}`);
  // A real tool is never "repaired".
  const isTool = ZSEngine.resolveAction("manage_scene", {}, hasUnity);
  ok(!isTool.ok && isTool.reason === "is-tool", 'a real tool must not be treated as an action');
  // Unknown name stays unknown.
  const unk = ZSEngine.resolveAction("definitely_not_a_thing", {}, hasUnity);
  ok(!unk.ok && unk.reason === "unknown", 'an unknown name must stay unknown');
  // A known action whose owner is NOT advertised must not invent the tool.
  const noOwner = ZSEngine.resolveAction("play", {}, advertise("manage_scene"));
  ok(!noOwner.ok && noOwner.reason === "unknown", 'an action must never resolve to an unadvertised tool');
  // Existing params survive, and a stale action key cannot override the repair.
  const keep = ZSEngine.resolveAction("save", { path: "Assets/Scenes/Main.unity", action: "wrong" }, advertise("manage_scene"));
  ok(keep.ok && keep.params.path === "Assets/Scenes/Main.unity" && keep.params.action === "save",
    `params must survive the repair and the action must win: ${JSON.stringify(keep.params)}`);
  // Roblox tool names must never be mangled by the repair.
  for (const n of ["execute_luau", "multi_edit", "inspect_instance", "list_commands"]) {
    const r2 = ZSEngine.resolveAction(n, {}, advertise("execute_luau", "multi_edit", "inspect_instance", "list_commands"));
    ok(!r2.ok, `Roblox tool ${n} must never be rewritten`);
  }
  // An action that collides with a Roblox tool name is left alone.
  ok(ZSEngine.resolveAction("save", {}, advertise("save")).reason === "is-tool", 'a name that IS an advertised tool must never be rewritten');
}
// resolveAction must never throw on hostile input.
for (const bad of [null, undefined, "", "   ", "a/b", "a.b", 42, {}, []]) {
  ZSEngine.resolveAction(bad, {}, hasUnity);
  ZSEngine.resolveAction("play", bad, hasUnity);
}
ZSEngine.resolveAction("play", {}, null);

// ── 4. Categories and notes route by engine, and unknown stays unknown ──
ok(ZSEngine.categoryFor("run_project") === "generate", 'Godot run_project should read as an action');
ok(ZSEngine.categoryFor("get_debug_output") === "read", 'Godot get_debug_output should read as a read');
ok(ZSEngine.categoryFor("get_viewport_screenshot") === "screen", 'Blender viewport capture should read as a screen');
ok(ZSEngine.categoryFor("manage_camera") === "screen", 'Unity manage_camera should read as a screen');
ok(ZSEngine.categoryFor("totally_unknown_tool") === null, 'an unknown tool must have no opinion');
ok(ZSEngine.noteFor("totally_unknown_tool") === "", 'an unknown tool must have no note');
ok(ZSEngine.engineOfTool("unity/manage_scene") === "unity", 'a server-prefixed name must still resolve');
ok(ZSEngine.engineOfTool("nope") === null, 'an unknown tool has no engine');
ok(ZSEngine.displayName("godot") === "Godot" && ZSEngine.displayName("unknownthing") === "unknownthing",
  'displayName must fall back to the raw id');

// ── 5. Prompt rules per engine ───────────────────────────────────────────
ok(ZSEngine.rulesFor([]) === "", 'no engines must add no rules');
ok(ZSEngine.rulesFor(["roblox"]) === "", 'Roblox alone must add no engine rules (its rules live in the shared prompt)');
ok(ZSEngine.rulesFor(["godot"]).includes("projectPath"), 'the Godot rule must name projectPath');
ok(ZSEngine.rulesFor(["unity"]).includes("ACTION-DISPATCH"), 'the Unity rule must explain action dispatch');
ok(ZSEngine.rulesFor(["unity"]).includes("manage_scene"), 'the Unity rule must name the family tools');
ok(ZSEngine.rulesFor(["blender"]).includes("JSON-escaped"), 'the Blender rule must warn about escaping');
ok(ZSEngine.rulesFor(["mystery"]).includes("DISCOVERY-FIRST"), 'an unknown engine must get the discovery rule');
ok(ZSEngine.rulesFor(["roblox", "godot", "unity"]).includes("projectPath"), 'mixed sessions must include the non-Roblox rules');
ok(ZSEngine.rulesFor(["godot", "godot"]).split("GODOT:").length === 2, 'duplicate ids must not duplicate the rule');

// ── 6. config integration: notes, categories, engine-aware prompt ────────
// The note LEADS with the copyable envelope (so a skimming model still gets the
// required shape), and the original Roblox prose follows it intact.
ok(ZS.toolNote("execute_luau").startsWith("REQUIRED SHAPE (copy this, fill the values):"),
  'structured tools must lead with the copyable required shape');
ok(ZS.toolNote("execute_luau").includes("Use `return`"), 'Roblox notes must still win for Roblox tools');
ok(ZS.toolNote("run_project").includes("projectPath"), 'engine notes must be reachable through ZS.toolNote');
ok(ZS.toolNote("unknown_thing") === "", 'ZS.toolNote must return empty for an unknown tool');
ok(ZS.toolCategory("execute_luau") === "edit" && ZS.toolCategory("run_project") === "generate",
  'ZS.toolCategory must cover Roblox and engine tools');
ok(ZS.toolCategory("script_read") === "read", 'Roblox categories must be unchanged');

const legacy = ZS.buildSystemPrompt({ siteName: "Arena" });
const robloxOnly = ZS.buildSystemPrompt({ siteName: "Arena", engines: ["roblox"] });
const godotOnly = ZS.buildSystemPrompt({ siteName: "DeepSeek", engines: ["godot"] });
const mixed = ZS.buildSystemPrompt({ siteName: "DeepSeek", engines: ["roblox", "godot", "unity"] });
const custom = ZS.buildSystemPrompt({ siteName: "DeepSeek", engines: ["mystery-server"] });

// Backwards compatibility: with no engine information, nothing changes.
ok(legacy.includes("is always connected by default"), 'no engine info must keep the legacy Roblox-first wording');
ok(robloxOnly.includes("is always connected by default"), 'Roblox-only must keep the legacy wording');
ok(legacy === robloxOnly, 'Roblox-only must be byte-identical to the legacy prompt');

// Godot-only: no Roblox claims, real Godot rules, no Roblox-only sections.
ok(!godotOnly.includes("is always connected by default"), 'a Godot-only session must not claim Roblox is connected');
ok(godotOnly.includes("NO Roblox Studio is connected in this session"), 'a Godot-only session must say Roblox is absent');
ok(godotOnly.includes("NATIVE COMMAND RULES FOR THE CONNECTED ENGINE(S)"), 'engine rules section missing');
ok(godotOnly.includes("params.projectPath"), 'the Godot rules must reach the prompt');
ok(!godotOnly.includes("game.ServerStorage.Multi-Script.Memory is your long-term memory"),
  'a Godot-only session must not be told to write Roblox project memory');
ok(godotOnly.includes("is NOT available in this session"), 'the memory section must be replaced, not dropped');
const actGodot = godotOnly.split("YOU CAN ACT DIRECTLY")[1].split("━━━")[0];
ok(!actGodot.includes("execute_luau"), 'the Godot "act directly" text must not name Roblox commands');

// Mixed: keeps Roblox sections AND adds the others.
ok(mixed.includes("is always connected by default") || mixed.includes("is connected in this session"),
  'a mixed session must state what is connected');
ok(mixed.includes("Godot") && mixed.includes("Unity"), 'a mixed session must name every connected engine');
ok(mixed.includes("game.ServerStorage.Multi-Script.Memory"), 'Roblox project memory must survive in a mixed session');

// Unknown server: discovery rule, no invented vocabulary.
ok(custom.includes("DISCOVERY-FIRST"), 'an unknown server must get the discovery rule');

// The JSON transport itself must be UNCHANGED by any of this.
for (const p of [legacy, godotOnly, mixed, custom]) {
  ok(p.includes("JSON-ONLY CONTRACT"), 'the JSON-only contract must survive every engine combination');
  ok(p.includes("exactly ONE plain-text JSON object"), 'the single-object rule must survive');
  ok(p.includes("Same rule for Godot"), 'the Godot JSON note must survive');
  ok(!p.includes("every command goes inside a fenced code block"), 'no legacy transport may be advertised');
}
// The per-engine strictness example is now CONDITIONAL, so it is asserted per
// combination rather than for all of them: the Roblox parameter contract belongs
// to a session that has Roblox, and a Godot-only session must instead get the
// generic "use the live schema's exact REQUIRED parameter names" rule. Asserting
// the Roblox line for every combination is what let a Godot-only prompt tell the
// model about a Roblox parameter it could never use.
for (const p of [legacy, mixed]) {
  ok(p.includes("Roblox Studio is the strictest consumer"), 'a Roblox session must get the Roblox parameter contract');
  ok(p.includes("studio_id"), 'a Roblox session must be told the required studio_id parameter');
}
ok(godotOnly.includes("The connected engine is the strictest consumer"),
  'a non-Roblox session must get the generic live-schema parameter rule');
ok(!godotOnly.includes("studio_id"), 'a Godot-only session must never be told about studio_id');
// `execute_luau` DOES legitimately appear once - in the deliberate "NO Roblox
// Studio is connected ... Do NOT write Roblox commands (execute_luau, multi_edit,
// ...)" warning, which is exactly what stops the model reaching for Roblox. What
// must NOT appear is a Roblox command SHOWN AS AN EXAMPLE the model could copy.
ok(godotOnly.includes("Do NOT write Roblox commands"),
  'a Godot-only session must still warn against Roblox commands');
ok(!/"command":\s*"execute_luau"/.test(godotOnly),
  'a Godot-only session must not be shown a copyable Roblox example envelope');
ok(/"command":\s*"run_project"/.test(godotOnly),
  'a Godot-only session must be shown a copyable Godot example envelope instead');

// ── 7. The Roblox JSON transport still parses exactly as before ─────────
for (const text of [
  '{"command":"list_commands","params":{}}',
  '{"command":"execute_luau","params":{"code":"return game.PlaceId","datamodel_type":"Edit"}}',
  '{"command":"multi_edit","params":{"datamodel_type":"Edit","edits":[{"file_path":"game.Workspace.A","old_string":"","new_string":"return 1"}]}}',
]) {
  const calls = ZSParse.parseToolCalls(text);
  ok(calls.length === 1 && !!calls[0].tool, `the Roblox envelope stopped parsing: ${text}`);
}
// And the engine commands ride the SAME envelope.
for (const text of [
  '{"command":"run_project","params":{"projectPath":"/home/me/game"}}',
  '{"command":"manage_scene","params":{"action":"get_hierarchy","page_size":50}}',
  '{"command":"get_debug_output","params":{}}',
]) {
  const calls = ZSParse.parseToolCalls(text);
  ok(calls.length === 1 && !!calls[0].tool, `an engine envelope does not parse: ${text}`);
}

// ── 8. Core wiring ──────────────────────────────────────────────────────
const main = read('extension/core/main.js');
for (const [what, needle] of [
  ['engine list from the bridge', 'function connectedEngineIds()'],
  ['engines passed into the prompt', 'engines: activeEngineIds()'],
  ['engine notes used by list_commands', 'ZS.toolNote ? ZS.toolNote(bareToolName(t.name))'],
  ['action-dispatch repair', 'ZSEngine.resolveAction(name, args'],
  ['repair is logged', 'tool.actionRepair'],
  ['ambiguous action refusal', 'is an ACTION, not a command, and'],
  ['missing-action error', 'needs params.action'],
  ['engine-aware offline note', 'function bridgeOfflineFeedback()'],
]) ok(main.includes(needle), `core is missing ${what} ("${needle}")`);
ok(!/const name = call\.tool;/.test(main), 'runTool must be able to reassign the tool name for the repair');

// engines.js must load before config.js and main.js on every provider.
const manifest = JSON.parse(read('extension/manifest.json'));
for (const s of manifest.content_scripts.filter((x) => (x.js || []).includes('core/main.js'))) {
  const iE = s.js.indexOf('core/engines.js'), iC = s.js.indexOf('core/config.js'), iM = s.js.indexOf('core/main.js');
  ok(iE !== -1, `engines.js is not loaded for a provider: ${JSON.stringify(s.js)}`);
  ok(iE < iC && iE < iM, `engines.js must load before config.js and main.js: ${JSON.stringify(s.js)}`);
}
const popup = read('extension/popup.js');
ok(popup.includes('"core/engines.js"'), 'the popup fallback injection list must include engines.js');

console.log('PASS non-Roblox engine command layer: 14 verified Godot tools + exact params, 33 Unity tools with 132 actions and ' +
  'dispatch integrity, action repair (unambiguous/ambiguous/unknown/never-mangles-Roblox), engine-aware prompt for 5 engine ' +
  'combinations, JSON transport unchanged for Roblox');
