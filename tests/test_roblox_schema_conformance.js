// SPDX-License-Identifier: GPL-3.0-or-later
// Roblox required-shape conformance.
//
// WHY THIS EXISTS
// The Roblox templates in extension/core/engines.js are a MIRROR of the live
// Roblox Studio MCP server. Several of them were originally written by GUESSING
// the parameter name, and the guesses were wrong in a way that costs a full
// agent turn each:
//
//   generate_mesh        guessed `prompt`         real: `textPrompt`
//   wait_job_finished    guessed `generation_id`  real: `jobId`
//   screen_capture       omitted capture_id       real: REQUIRED
//   search_game_tree     omitted datamodel_type   real: REQUIRED
//   insert_asset         guessed Number assetId   real: string
//   generate_procedural_model  omitted async      real: server recommends async:true
//   character_navigation guessed path+destination real: datamodel_type + instance_path|x/y/z
//
// A wrong guess is worse than no template: the model copies the example,
// the server rejects it, and the failure reads as a product bug.
//
// Each entry below records the LIVE schema facts (verified against the server's
// published parameter schemas). The test asserts the template agrees. It cannot
// call the server - it pins what was observed so a future edit cannot silently
// reintroduce the guess.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };

let passed = 0;
const t = (name, fn) => { fn(); passed++; console.log('  ok  ' + name); };

const ZSEngine = new Function(read('extension/core/engines.js') + ';return ZSEngine;')();
const ZS = new Function('ZSEngine', read('extension/core/config.js') + ';return ZS;')(ZSEngine);

// Templates carry <SID>/<...> placeholders; replace them so JSON.parse succeeds
// while leaving every real key intact.
const parseTpl = (tool) => JSON.parse(String(ZSEngine.templateFor(tool)).replace(/<[^>]*>/g, 'X'));

// ── 1. required params are actually present ──────────────────────────────
// Every entry: [tool, requiredParam, ...]. A missing one -> server rejects with
// "invalid parameters: <path> is required", the exact Blender/Unity failure the
// required-param contract already covers for those engines. This is the Roblox
// half of that contract, at the TEMPLATE level (not just the note).
t('every Roblox template carries the params the server requires', () => {
  const REQ = {
    // [schema] required: ["textPrompt", "studio_id"]
    generate_mesh: ['textPrompt', 'studio_id'],
    // [schema] required: ["prompt", "studio_id"]
    generate_procedural_model: ['prompt', 'studio_id'],
    // [schema] required: ["assetId", "studio_id"]
    insert_asset: ['assetId', 'studio_id'],
    // [schema] required: ["capture_id", "studio_id"]
    screen_capture: ['capture_id', 'studio_id'],
    // [schema] required: ["jobId", "studio_id"]
    wait_job_finished: ['jobId', 'studio_id'],
    // [schema] required: ["datamodel_type", "studio_id"]
    search_game_tree: ['datamodel_type', 'studio_id'],
    // [schema] required: ["datamodel_type", "studio_id"]
    character_navigation: ['datamodel_type', 'studio_id'],
    // [schema] required: ["skill_name", "studio_id"]
    skill: ['skill_name', 'studio_id'],
    // [schema] required: ["studio_id"] (search_asset)
    search_asset: ['studio_id'],
    // [schema] required: ["studio_id"] (get_console_output)
    get_console_output: ['studio_id'],
    // [schema] required: ["code", "datamodel_type", "studio_id"]
    execute_luau: ['code', 'datamodel_type', 'studio_id'],
    // [schema] required: ["id", "studio_id"] (script_read/find uses target_file)
    script_read: ['target_file', 'studio_id'],
    // [schema] required: ["query", "studio_id"] - the field is `query`, NOT `keywords`
    script_grep: ['query', 'studio_id'],
    // [schema] required: ["keywords", "studio_id"] (script_search - this one IS keywords)
    script_search: ['keywords', 'studio_id'],
    // [schema] required: ["file_path", "edits", "datamodel_type", "studio_id"]
    multi_edit: ['file_path', 'edits', 'datamodel_type', 'studio_id'],
    // [schema] required: ["actions", "datamodel_type", "studio_id"]
    user_keyboard_input: ['actions', 'datamodel_type', 'studio_id'],
    user_mouse_input: ['actions', 'datamodel_type', 'studio_id'],
    // [schema] required: ["is_start", "studio_id"]
    start_stop_play: ['is_start', 'studio_id'],
    // [schema] required: ["path", "studio_id"]
    inspect_instance: ['path', 'studio_id'],
  };
  const bad = [];
  for (const [tool, req] of Object.entries(REQ)) {
    const tpl = ZSEngine.templateFor(tool);
    ok(tpl, `no template for ${tool}`);
    let obj;
    try { obj = parseTpl(tool); } catch (e) { bad.push(`${tool}: template is not valid JSON (${e.message})`); continue; }
    const p = obj.params || {};
    for (const r of req) if (!(r in p)) bad.push(`${tool}: template omits required param "${r}"`);
    if (obj.command !== tool) bad.push(`${tool}: template command is "${obj.command}"`);
  }
  ok(bad.length === 0, 'template/schema mismatches:\n    ' + bad.join('\n    '));
});

// ── 2. the specific guesses that were once wrong stay fixed ───────────────
t('the never-guess-this-again params are the real ones', () => {
  // generate_mesh's text field is `textPrompt`, NOT `prompt`.
  const mesh = parseTpl('generate_mesh').params;
  ok('textPrompt' in mesh, 'generate_mesh must use textPrompt');
  ok(!('prompt' in mesh), 'generate_mesh must NOT use prompt (that is the procedural model field)');
  // wait_job_finished's handle is `jobId`, NOT `generation_id`.
  const wait = parseTpl('wait_job_finished').params;
  ok('jobId' in wait, 'wait_job_finished must use jobId');
  ok(!('generation_id' in wait), 'wait_job_finished must NOT use generation_id');
  // screen_capture requires capture_id.
  ok('capture_id' in parseTpl('screen_capture').params, 'screen_capture must carry capture_id');
  // search_game_tree requires datamodel_type.
  ok(parseTpl('search_game_tree').params.datamodel_type === 'Edit',
    'search_game_tree template should show datamodel_type:"Edit" (the edit-mode value)');
  // character_navigation is datamodel_type Client + instance_path|x/y/z, not destination.
  const nav = parseTpl('character_navigation').params;
  ok(nav.datamodel_type === 'Client', 'character_navigation must be datamodel_type:"Client"');
  ok('instance_path' in nav || ('x' in nav && 'y' in nav && 'z' in nav),
    'character_navigation must carry instance_path or x/y/z');
  ok(!('destination' in nav), 'character_navigation has no `destination` param');
  // script_grep's field is `query`; script_search's is `keywords`. They look
  // interchangeable and are not - the tags/category split is a real trap.
  ok('query' in parseTpl('script_grep').params, 'script_grep must use `query`');
  ok(!('keywords' in parseTpl('script_grep').params), 'script_grep must NOT use `keywords`');
  ok('keywords' in parseTpl('script_search').params, 'script_search must use `keywords`');
  // multi_edit's file_path is top-level, never inside an edit.
  const me = parseTpl('multi_edit').params;
  ok(typeof me.file_path === 'string', 'multi_edit file_path must be a top-level param');
  ok(me.edits.every((e) => !('file_path' in e)),
    'multi_edit edits[] must not carry file_path');
});

// ── 3. insert_asset's assetId is a string, and assetName is shown ────────
// The live schema declares assetId as type:string. A numeric literal is coerced
// by the server but teaches the model to drop the quotes, and the assetName
// naming convention is documented behaviour worth showing.
t('insert_asset models assetId as a string and shows assetName', () => {
  const p = parseTpl('insert_asset').params;
  ok(typeof p.assetId === 'string', 'insert_asset assetId must be a quoted string in the template');
  ok(/^\d+$/.test(p.assetId), 'insert_asset assetId should be a numeric-looking string, e.g. "123456789"');
  ok(typeof p.assetName === 'string' && p.assetName.length > 0,
    'insert_asset should show assetName (the instance is named from it)');
});

// ── 4. generate_procedural_model shows async:true ────────────────────────
// The server's own description says "Default to calling it with the 'async'
// argument set to true". The template must model that or the model blocks.
t('generate_procedural_model template defaults to async', () => {
  const p = parseTpl('generate_procedural_model').params;
  ok(p.async === true, 'generate_procedural_model template must show "async":true');
});

// ── 5. the notes describe the real fields, not the old guesses ───────────
t('the tool notes name the real parameter fields', () => {
  const meshNote = ZS.toolNote('generate_mesh') || '';
  ok(meshNote.includes('textPrompt'), 'generate_mesh note must name textPrompt');
  ok(!/\b"prompt"\b/.test(meshNote.split('textPrompt')[0]) ||
     /NOT "prompt"|not "prompt"/.test(meshNote),
     'generate_mesh note must warn against "prompt"');
  const waitNote = ZS.toolNote('generate_procedural_model') || '';
  ok(waitNote.includes('jobId'), 'generate_procedural_model note must name jobId');
  ok(waitNote.includes('Do NOT call wait_job_finished as a reflex'),
    'the "not as a reflex" guidance must survive');
  const capNote = ZS.toolNote('screen_capture') || '';
  ok(capNote.includes('capture_id'), 'screen_capture note must name capture_id');
  const treeNote = ZS.toolNote('search_game_tree') || '';
  ok(treeNote.includes('datamodel_type'), 'search_game_tree note must name datamodel_type');
});

// ── 6. no note teaches a param the server does not take ──────────────────
// Cheap guard against the inverse error: prose that describes a field that was
// renamed on the server. Only the fields we have concrete knowledge of.
t('no note teaches a renamed-by-us parameter name', () => {
  const FORBIDDEN = [
    ['generate_procedural_model', 'generation_id', 'wait_job_finished takes jobId'],
    ['generate_mesh', '"prompt"', 'generate_mesh takes textPrompt'],
  ];
  const bad = [];
  for (const [tool, banned, why] of FORBIDDEN) {
    const note = ZS.toolNote(tool) || '';
    // Allow the string when it appears in an explicit "NOT x" correction.
    const idx = note.indexOf(banned);
    if (idx >= 0) {
      const before = note.slice(Math.max(0, idx - 40), idx);
      if (!/(not|NOT|instead of|rather than)\s*"?$/.test(before.trim()) && !/NOT/i.test(before)) {
        bad.push(`${tool}: note references "${banned}" (${why})`);
      }
    }
  }
  ok(bad.length === 0, 'stale parameter names in notes:\n    ' + bad.join('\n    '));
});

console.log(`\ntest_roblox_schema_conformance: ${passed} sections passed`);
