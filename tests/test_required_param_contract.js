// SPDX-License-Identifier: GPL-3.0-or-later
// Required-parameter contract regression (Roblox + Godot + Unity + Blender).
//
// WHY THIS FILE EXISTS
// A live session produced a loop of bad calls:
//
//   ERROR calling 'multi_edit': multi_edit: invalid parameters:
//   parameters.edits[0].old_string is required
//
// The command name was right, the edit was otherwise fine - the model just
// dropped ONE required nested field, then could not work out which, and started
// emitting malformed JSON instead. Two defects made that possible:
//
//   1. The tool's note described how `old_string` should MATCH (byte-for-byte,
//      watch unicode, ...) but never showed the required call SHAPE. A model
//      skimming for "what do I write" skips prose and omits the field.
//   2. The bridge's validator rejects arguments BEFORE the tool runs and returns
//      ok:false. That path got a bare "Read the error carefully", while only the
//      ok:true server-complaint path had been made corrective.
//
// So this file pins: (a) every structured tool LEADS its note with a copyable
// envelope, (b) the validator error names the exact nested path AND shows the
// shape, and (c) the non-Roblox engines' required params and code-transfer
// envelopes are exactly right - the part the user has never been able to test.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };

const ZSEngine = new Function(read('extension/core/engines.js') + ';return ZSEngine;')();
const ZS = new Function('ZSEngine', read('extension/core/config.js') + ';return ZS;')(ZSEngine);
const ZSParse = new Function(read('extension/core/parser.js') + ';return ZSParse;')();
const mainSrc = read('extension/core/main.js');
const cfgSrc = read('extension/core/config.js');

// The exact validator message the bridge produces (runtime/bridge.py
// _normalize_tool_arguments -> "…: invalid parameters: <path> is required").
const V = (tool, detail) => `${tool}: invalid parameters: ${detail}`;

// ── 1. Every structured tool LEADS with a copyable envelope ─────────────
// These are the tools whose params are an array-of-objects or several required
// fields at once - i.e. the ones a model cannot get right by guessing.
const STRUCTURED = [
  // Roblox
  "multi_edit", "execute_luau", "script_read", "script_search", "script_grep",
  "inspect_instance", "search_game_tree", "start_stop_play", "wait_job_finished",
  "user_keyboard_input", "user_mouse_input",
  // Godot
  "add_node", "create_scene", "load_sprite", "save_scene", "get_project_info",
  "list_projects", "export_mesh_library", "get_uid",
  // Unity
  "manage_scene", "manage_gameobject", "manage_components", "manage_asset",
  "manage_editor", "read_console", "create_script", "script_apply_edits",
  "validate_script", "get_sha",
  // Blender
  "execute_blender_code",
];
for (const t of STRUCTURED) {
  const tpl = ZSEngine.templateFor(t);
  ok(tpl && tpl.length > 20, `${t} must have a required-shape template`);
  ok(tpl.startsWith('{"command":"' + t + '"'), `${t}'s template must be a copyable envelope for ${t}: ${tpl.slice(0, 60)}`);
  ok(tpl.includes('"params":{'), `${t}'s template must carry a params object`);
  const note = ZS.toolNote(t);
  ok(note.startsWith("REQUIRED SHAPE (copy this, fill the values): "),
    `${t}'s note must LEAD with the shape, not bury it after prose`);
  ok(note.includes(tpl), `${t}'s leading line must be the actual envelope`);
}

// ── 2. The template must be VALID JSON once placeholders are filled ─────
// A template that does not parse is worse than none: it teaches a broken call.
// Placeholders are the only non-JSON parts, so substituting them must yield
// parseable JSON for every engine.
const fill = (t) => t.replace(/<SID>/g, "s-1").replace(/<PROJ>/g, "C:/proj")
  .replace(/<exact current text, copied from script_read>/g, "return 1")
  .replace(/<replacement text>/g, "return 2")
  .replace(/<id from generate_procedural_model>/g, "gen-1");
for (const t of STRUCTURED) {
  const j = fill(ZSEngine.templateFor(t));
  let parsed = null;
  try { parsed = JSON.parse(j); } catch (e) { throw new Error(`${t}'s template is not valid JSON after filling: ${e.message}\n${j}`); }
  ok(parsed.command === t, `${t}'s template command must equal the tool name`);
  ok(parsed.params && typeof parsed.params === "object", `${t}'s template must have a params object`);
}
// Roblox templates must also be parseable by the REAL parser the loop uses,
// with studio_id supplied - otherwise the template teaches a call the transport
// rejects.
for (const t of ["multi_edit", "execute_luau", "inspect_instance", "script_read", "start_stop_play"]) {
  const calls = ZSParse.parseToolCalls(fill(ZSEngine.templateFor(t)));
  ok(calls.length === 1 && calls[0].tool === t,
    `${t}'s template must round-trip through the real parser (got ${calls.length} calls)`);
}

// ── 3. The multi_edit template carries what the error complained about ───
// This is the literal regression: the model omitted edits[0].old_string.
const meTpl = ZSEngine.templateFor("multi_edit");
ok(meTpl.includes('"edits":[{'), "multi_edit's template must show edits as an ARRAY of objects");
for (const f of ["file_path", "old_string", "new_string"]) {
  ok(new RegExp('"' + f + '"').test(meTpl), `multi_edit's template must include ${f}`);
}
ok(/"old_string":"(?!")/.test(meTpl) && /"new_string":"(?!")/.test(meTpl),
  "old_string and new_string must both be present as values (not omitted or null)");
// [schema] file_path is a TOP-LEVEL multi_edit param. It shipped INSIDE the edit
// object for several releases, so assert the nesting explicitly - a bare
// "file_path appears somewhere" check would not catch a regression.
const meObj = JSON.parse(meTpl.replace(/<[^>]*>/g, 'X'));
ok(typeof meObj.params.file_path === 'string' && meObj.params.file_path.length > 0,
  "multi_edit's file_path must be a TOP-LEVEL params field");
ok(meObj.params.edits.every((e) => !('file_path' in e)),
  "multi_edit's edits[] entries must NOT carry file_path (it is a params field, not an edit field)");
// The note must still explain HOW old_string matches - the template leads, the
// prose follows; neither replaces the other.
const meNote = ZS.toolNote("multi_edit");
ok(/byte-for-byte/.test(meNote), "the multi_edit prose about exact matching must survive");
ok(/script_read the file FIRST/.test(meNote), "the multi_edit script_read-first rule must survive");
ok(/WATCH FOR BAD UNICODE/.test(meNote), "the multi_edit unicode warning must survive");
ok(/old_string:"" /.test(meNote) || /old_string:""/.test(meNote),
  "the multi_edit create-script case (empty old_string) must survive");

// ── 4. The validator rejection path is CORRECTIVE, not generic ──────────
// Reproduce the handler's parsing of the bridge's exact message. This mirrors
// extension/core/main.js; section 5 asserts the two stay in step.
function validatorFeedback(tool, vErr) {
  const badParam = /invalid parameters:\s*(.+)$/i.exec(vErr);
  if (!badParam) return null;
  const detail = badParam[1].trim();
  const missing = /^(.+?)\s+is required[.!]?$/i.exec(detail);
  const tpl = ZSEngine.templateFor(tool);
  const shapeLine = tpl ? `\nThe required shape for '${tool}' is:\n${tpl}` : "";
  if (missing) {
    const p = missing[1].trim();
    // Deliberately NOT ^-anchored - the array access is mid-path in the real
    // message ("parameters.edits[0].old_string"). See section 5.
    const nested = /(?:^|\.)([A-Za-z0-9_]+)\[\d+\]\.([A-Za-z0-9_]+)$/.exec(p);
    const where = nested
      ? `'${nested[2]}' must be present on EVERY object inside the '${nested[1]}' array - it is a nested field, not a top-level one.`
      : `'${p}' must be present.`;
    return `ERROR calling '${tool}': the command was NOT run - its arguments were rejected before execution because ${p} is required.\n${where}\nDo NOT rename the command and do NOT change anything else: re-send the SAME command with '${p}' added to the params you already wrote (keep every other value as it was).${shapeLine}\nRaw: ${vErr}`;
  }
  return `ERROR calling '${tool}': the command was NOT run - its arguments were rejected: ${detail}.\nFix only what the message names, then re-send the SAME command.${shapeLine}\nRaw: ${vErr}`;
}

// (a) the reported failure, exactly. THIS session's live error was:
//     ERROR calling 'multi_edit': multi_edit: invalid parameters:
//     parameters.edits[0].old_string is required
const f1 = validatorFeedback("multi_edit", V("multi_edit", "parameters.edits[0].old_string is required"));
ok(f1, "the multi_edit validator error must be recognised");
ok(f1.includes("parameters.edits[0].old_string"), "must name the exact nested path - not just 'edits'");
ok(/\bEVERY\b/.test(f1) && /'edits' array/.test(f1),
  "must explain it applies to EVERY object in the array (so a 2nd edit fixing `where` alone is wrong)");
ok(/old_string/.test(f1), "must name the field the model actually dropped");
ok(/NOT run|never executed/i.test(f1), "must make clear the command never executed");
ok(f1.includes("Do NOT rename the command"), "must stop the model renaming the tool (the hyphen drift)");
ok(f1.includes(ZSEngine.templateFor("multi_edit")), "must include the copyable required shape");
ok(!/Read the error carefully/.test(f1), "must NOT fall back to the generic advice");
// (b) other nested fields and depths
const f2 = validatorFeedback("multi_edit", V("multi_edit", "parameters.edits[1].new_string is required"));
ok(f2.includes("parameters.edits[1].new_string") && f2.includes("nested field"), "must handle any array index");
// (c) a top-level field on a nested tool must NOT claim it is nested
const f3 = validatorFeedback("multi_edit", V("multi_edit", "parameters.edits is required"));
ok(f3.includes("'parameters.edits' must be present."), "top-level missing must not be described as nested");
ok(!f3.includes("EVERY object inside"), "top-level missing must not mention array items");
// (d) a non-'is required' validator failure still gets the shape and the fix-only guidance
const f4 = validatorFeedback("run_project", V("run_project", "parameters.projectPath must be a string"));
ok(f4.includes("parameters.projectPath must be a string"), "must quote the real complaint");
ok(f4.includes(ZSEngine.templateFor("run_project")), "must still show the shape when one exists");
ok(!/Read the error carefully/.test(f4), "must not use the generic advice");
// (e) an unrecognised error still falls through to the old generic text
ok(validatorFeedback("multi_edit", "kaboom") === null, "unrecognised errors must fall through");

// ── 5. main.js actually wires this handler ──────────────────────────────
ok(/invalid parameters:/.test(mainSrc), "main.js must detect the bridge validator error");
ok(/the command was NOT run - its arguments were rejected before execution/.test(mainSrc),
  "main.js must state the command never ran");
ok(/it is a nested field, not a top-level one/.test(mainSrc),
  "main.js must explain nested fields");
ok(/Do NOT rename the command/.test(mainSrc), "main.js must stop the model renaming the tool");
ok(/ZSEngine\.templateFor/.test(mainSrc), "main.js must show the required shape from the registry");
ok(/Read the error carefully, fix the call or try a different approach/.test(mainSrc),
  "the generic fallback must survive for genuinely unrecognised errors");

// ── 6. Godot: required params and code transfer ─────────────────────────
// The user has never been able to test this, so assert it literally.
const GODOT_REQ = {
  launch_editor: ["projectPath"], run_project: ["projectPath"], get_debug_output: [],
  stop_project: [], get_godot_version: [], list_projects: ["directory"],
  get_project_info: ["projectPath"], create_scene: ["projectPath", "scenePath"],
  add_node: ["projectPath", "scenePath", "nodeType", "nodeName"],
  load_sprite: ["projectPath", "scenePath", "nodePath", "texturePath"],
  export_mesh_library: ["projectPath", "scenePath", "outputPath"],
  save_scene: ["projectPath", "scenePath"], get_uid: ["projectPath", "filePath"],
  update_project_uids: ["projectPath"],
};
const godot = ZSEngine.ENGINES.godot.tools;
ok(Object.keys(godot).length === Object.keys(GODOT_REQ).length,
  `Godot tool count drifted: ${Object.keys(godot).length} vs ${Object.keys(GODOT_REQ).length}`);
for (const [n, req] of Object.entries(GODOT_REQ)) {
  ok(godot[n], `Godot tool missing: ${n}`);
  ok(JSON.stringify(godot[n].req) === JSON.stringify(req), `Godot required params drifted for ${n}`);
}
// Every Godot template must use `projectPath` (camelCase) - not `path`/`project_path`.
for (const t of Object.keys(GODOT_REQ)) {
  const tpl = ZSEngine.templateFor(t);
  if (!tpl) continue;
  ok(!/"path":/.test(tpl) && !/project_path/.test(tpl), `${t}'s template must not use a wrong path spelling`);
  if (GODOT_REQ[t].includes("projectPath")) ok(tpl.includes('"projectPath"'), `${t}'s template must carry projectPath`);
}
// COVERAGE: every Godot tool that REQUIRES a param must ship a template, or the
// note cannot lead with a copyable shape and the model is back to guessing.
// (run_project had no template until this test caught it.)
for (const [n, req] of Object.entries(GODOT_REQ)) {
  if (req.length === 0) continue;
  ok(ZSEngine.templateFor(n), `Godot tool '${n}' requires params, so it MUST have a template`);
  const parsed = JSON.parse(fill(ZSEngine.templateFor(n)));
  ok(parsed.command === n, `${n}'s template must name the tool itself`);
  for (const p of req) {
    ok(Object.prototype.hasOwnProperty.call(parsed.params, p),
      `${n}'s template is missing required param '${p}'`);
  }
}
// list_projects is the documented exception: it takes `directory`.
ok(ZSEngine.templateFor("list_projects").includes('"directory"'), "list_projects must take directory, not projectPath");

// ── 7. Unity: action-dispatch templates and the repair ─────────────────
const unityTools = ZSEngine.ENGINES.unity.tools;
const DISPATCH = Object.entries(unityTools).filter(([, s]) => s.dispatch).map(([n]) => n);
ok(DISPATCH.length >= 15, `Unity must have its action-dispatch family tools (got ${DISPATCH.length})`);
// A dispatched tool's template MUST put the operation in params.action.
// read_console belongs here: upstream takes action="get"/"clear" (it was
// mis-declared as a flat tool until this test caught the inconsistency).
for (const t of ["manage_scene", "manage_gameobject", "manage_components", "manage_asset", "manage_editor", "read_console"]) {
  const tpl = ZSEngine.templateFor(t);
  ok(tpl, `${t} must have a template`);
  ok(/"action":/.test(tpl), `${t}'s template must carry params.action`);
  ok(JSON.parse(fill(tpl)).params.action, `${t}'s template must set a real action value`);
  ok(ZSEngine.isDispatchTool(t), `${t} must be classified as action-dispatch`);
  ok(ZSEngine.actionsOf(t).length > 0, `${t} must expose its action list`);
  ok(JSON.stringify(unityTools[t].req) === JSON.stringify(["action"]),
    `${t} must REQUIRE the action param, like every other dispatch tool`);
}
// COVERAGE: every Unity tool that requires a param must ship a template too.
for (const [n, spec] of Object.entries(unityTools)) {
  if (!spec.req || spec.req.length === 0) continue;
  ok(ZSEngine.templateFor(n), `Unity tool '${n}' requires params, so it MUST have a template`);
  const parsed = JSON.parse(fill(ZSEngine.templateFor(n)));
  for (const p of spec.req) {
    ok(Object.prototype.hasOwnProperty.call(parsed.params, p),
      `${n}'s template is missing required param '${p}'`);
  }
}
// A dispatch tool's template must never carry a bogus action it does not accept.
for (const t of DISPATCH) {
  const tpl = ZSEngine.templateFor(t);
  if (!tpl) continue;
  const act = JSON.parse(fill(tpl)).params.action;
  ok(ZSEngine.actionsOf(t).includes(act),
    `${t}'s template action '${act}' must be one of its real actions (${ZSEngine.actionsOf(t).join(", ")})`);
}
// The classic failure: an action written as if it were a tool. Use an action
// with exactly ONE owner, so the repair is unambiguous and must succeed.
const live = new Set(["manage_scene", "manage_prefabs", ...DISPATCH]);
const single = Object.entries(ZSEngine.ACTION_OWNERS)
  .find(([a, o]) => o.length === 1 && o[0] === "manage_scene" && live.has("manage_scene"));
ok(single, "manage_scene must own at least one exclusive action");
const r1 = ZSEngine.resolveAction(single[0], {}, (n) => live.has(n));
ok(r1.ok && r1.tool === "manage_scene" && r1.params.action === single[0],
  `the exclusive action '${single[0]}' must repair to manage_scene with the action inside params`);
// An action written as a tool whose name is ALSO a tool is left alone.
const r1b = ZSEngine.resolveAction("get_hierarchy", {}, (n) => live.has(n));
ok(!r1b.ok && r1b.reason === "ambiguous",
  "get_hierarchy really has two owners (manage_scene, manage_prefabs) - it must be refused, not guessed");
// An ambiguous action must be refused with candidates, never guessed.
const amb = Object.entries(ZSEngine.ACTION_OWNERS).find(([, o]) => o.length > 1);
if (amb) {
  const r2 = ZSEngine.resolveAction(amb[0], {}, (n) => live.has(n));
  ok(!r2.ok && r2.reason === "ambiguous", `the ambiguous action '${amb[0]}' must be refused`);
  ok(r2.candidates.length > 1, "ambiguity must list the candidate tools");
}
// A real Unity tool must never be rewritten. `hasTool` is the caller's view of
// the live server - it is what decides "is-tool", so include the flat tools too.
const realTools = new Set([...live, "create_script", "script_apply_edits", "validate_script"]);
ok(ZSEngine.resolveAction("create_script", {}, (n) => realTools.has(n)).reason === "is-tool",
  "a name that IS a live tool must never be rewritten");
ok(ZSEngine.resolveAction("create_script", {}, (n) => live.has(n)).reason !== "is-tool",
  "a flat tool the caller does not report must not be claimed as a tool");
// A Roblox tool must never be rewritten (its server is NOT action-dispatch).
ok(ZSEngine.resolveAction("execute_luau", {}, () => true).reason === "is-tool",
  "a Roblox tool must never be repaired as an action");

// ── 8. Code transfer: the JSON string escaping path ────────────────────
// Unity create_script and Blender execute_blender_code both carry CODE as a JSON
// STRING, so the escaping is the transfer mechanism. Assert the templates and the
// parser agree on that, for quotes AND newlines.
for (const t of ["create_script", "execute_blender_code", "script_apply_edits"]) {
  const tpl = ZSEngine.templateFor(t);
  ok(/\\n/.test(tpl), `${t}'s template must demonstrate escaped newlines (\\n)`);
}
ok(/\\"/.test(ZSEngine.templateFor("create_script")), "create_script must demonstrate escaped quotes");
// A code payload with BOTH a quote and a newline must survive the real parser.
const codePayload = { command: "execute_blender_code", params: { code: 'import bpy\nname = "Cube"\nprint(name)' } };
const sent = JSON.stringify(codePayload);
const back = ZSParse.parseToolCalls(sent);
ok(back.length === 1 && back[0].tool === "execute_blender_code", "an escaped Blender code payload must parse");
ok(back[0].arguments.code === codePayload.params.code,
  `the code must round-trip byte-for-byte: ${JSON.stringify(back[0].arguments.code)}`);
// Same for a Unity C# payload, which is the multi-line case.
const cs = { command: "create_script", params: { path: "Assets/Scripts/A.cs", contents: 'using UnityEngine;\npublic class A : MonoBehaviour {\n  void Start() { Debug.Log("hi"); }\n}\n' } };
const csBack = ZSParse.parseToolCalls(JSON.stringify(cs));
ok(csBack.length === 1 && csBack[0].arguments.contents === cs.params.contents,
  "a multi-line C# payload must round-trip byte-for-byte");

// ── 9. Nothing pre-existing was replaced ───────────────────────────────
ok(/GODOT MCP \(primary non-Roblox engine\): before changing a Godot project, call ms_get_skill with skill_id "godot-mcp-orchestrator"/.test(cfgSrc),
  "the original Godot orchestrator rule must survive");
ok(/UNITY MCP: before changing a Unity project, call ms_get_skill with skill_id "unity-mcp-orchestrator"/.test(cfgSrc),
  "the original Unity orchestrator rule must survive");
ok(/Only the FIRST returned value is shown/.test(cfgSrc), "the execute_luau multi-return line must survive");
ok(/ALWAYS pass a timeout to WaitForChild/.test(cfgSrc), "the WaitForChild timeout warning must survive");
ok(/Do NOT call wait_job_finished as a reflex/.test(cfgSrc), "the generate_procedural_model note must survive");

console.log("PASS required-parameter contract: every structured Roblox/Godot/Unity/Blender tool leads with a valid copyable envelope, the validator rejection names the exact nested path and shows the shape, Godot's 14 tools/params and Unity's action-dispatch repair are exact, and code payloads round-trip byte-for-byte");
