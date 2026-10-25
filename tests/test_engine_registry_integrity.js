// SPDX-License-Identifier: GPL-3.0-or-later
// Engine registry integrity: the invariants that make the native tool surface
// self-consistent. Every one of these has been violated at some point in this
// repo's history, and each violation reaches the model as a bad call rather
// than a test failure - which is why they are pinned here instead.
//
// The registry (extension/core/engines.js) is a MIRROR of what live MCP servers
// advertise. A mirror that drifts internally is worse than no mirror: the model
// writes a perfectly-shaped call for a tool/action/param that does not exist.
//
// Invariants asserted:
//   1. every action-dispatch owner is a REAL tool in its engine
//   2. dispatch:true <=> the tool has an action vocabulary (both directions)
//   3. every template parses as JSON after placeholder substitution
//   4. a dispatch template's params.action is a real action of THAT tool
//   5. a template's `command` equals the tool name it belongs to
//   6. every tool has a template (so the required SHAPE always leads the note)
//   7. every Roblox place-scoped tool is in ROBLOX_PLACE_TOOLS, and vice versa
//   8. code-transfer templates round-trip byte-for-byte (escaping is the point)
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };

let passed = 0;
const t = (name, fn) => { fn(); passed++; console.log('  ok  ' + name); };

const ENGINE_SRC = read('extension/core/engines.js');
const CONFIG_SRC = read('extension/core/config.js');
const ZSEngine = new Function(ENGINE_SRC + ';return ZSEngine;')();
const ZS = new Function('ZSEngine', CONFIG_SRC + ';return ZS;')(ZSEngine);

// Placeholder-safe JSON parse. Templates carry <SID>/<PROJ>/<...> markers that
// are not valid JSON strings only because of the angle brackets, so we swap them
// for a token first. Everything else must be genuine JSON.
const parseTpl = (tpl) => JSON.parse(String(tpl).replace(/<[^>]*>/g, 'X'));

const ALL = [];
for (const [id, e] of Object.entries(ZSEngine.ENGINES)) {
  for (const name of Object.keys(e.tools || {})) ALL.push({ id, name, spec: e.tools[name] });
}

// ── 1. action owners must be real tools ──────────────────────────────────
t('every action-dispatch owner is a real tool in its engine', () => {
  const bad = [];
  for (const [id, e] of Object.entries(ZSEngine.ENGINES)) {
    for (const [action, owners] of Object.entries(e.actions || {})) {
      for (const o of owners) {
        if (!(e.tools || {})[o]) bad.push(`${id}: action "${action}" claims owner "${o}" which is not a tool`);
      }
    }
  }
  ok(bad.length === 0, 'dangling action owners:\n    ' + bad.join('\n    '));
});

// ── 2. dispatch flag must agree with the action vocabulary ───────────────
t('dispatch:true <=> the tool has an action vocabulary', () => {
  const bad = [];
  for (const { id, name, spec } of ALL) {
    const acts = ZSEngine.actionsOf(name) || [];
    if (spec.dispatch && acts.length === 0) bad.push(`${id}/${name}: dispatch:true but no actions`);
    if (!spec.dispatch && acts.length > 0) bad.push(`${id}/${name}: has ${acts.length} actions but dispatch is not true`);
  }
  ok(bad.length === 0, 'dispatch/vocabulary mismatch:\n    ' + bad.join('\n    '));
});

// ── 3. every template is valid JSON ├── 4. dispatch action is real ───────
t('every template parses as JSON and matches its tool command', () => {
  const bad = [];
  for (const { id, name } of ALL) {
    const tpl = ZSEngine.templateFor(name);
    ok(tpl, `${id}/${name}: no template`);
    let obj;
    try { obj = parseTpl(tpl); }
    catch (e) { bad.push(`${id}/${name}: template is not valid JSON (${e.message})`); continue; }
    if (obj.command !== name) bad.push(`${id}/${name}: template command is "${obj.command}"`);
  }
  ok(bad.length === 0, 'template problems:\n    ' + bad.join('\n    '));
});

t('a dispatch template carries a real action of that tool', () => {
  const bad = [];
  for (const { id, name, spec } of ALL) {
    if (!spec.dispatch) continue;
    let obj; try { obj = parseTpl(ZSEngine.templateFor(name)); } catch { continue; }
    const act = obj.params && obj.params.action;
    const acts = ZSEngine.actionsOf(name) || [];
    if (!act) bad.push(`${id}/${name}: dispatch template has no params.action`);
    else if (!acts.includes(act)) bad.push(`${id}/${name}: template action "${act}" not in [${acts.slice(0, 6).join(', ')}...]`);
  }
  ok(bad.length === 0, 'dispatch template problems:\n    ' + bad.join('\n    '));
});

// ── 5. template coverage ─────────────────────────────────────────────────
t('every native tool ships a required-shape template', () => {
  const missing = ALL.filter(({ name }) => !ZSEngine.templateFor(name)).map(({ id, name }) => `${id}/${name}`);
  ok(missing.length === 0, 'tools without a template:\n    ' + missing.join('\n    '));
});

// ── 6. Roblox place-scope set is exactly right ───────────────────────────
t('Roblox studio_id scoping is consistent in both directions', () => {
  // The set declares which tools REQUIRE studio_id. Anything in it must be a
  // real mirrored Roblox tool; and nothing that is place-scoped may be missing.
  const PLACE = ZSEngine.ROBLOX_PLACE_TOOLS;
  ok(PLACE && typeof PLACE.has === 'function', 'ROBLOX_PLACE_TOOLS is not a Set');
  // Every place-scoped tool must produce the studio_id suffix in its note, and
  // a non-place tool must not.
  const badScoped = [];
  const badSuffix = [];
  for (const name of PLACE) {
    if (ZS.toolNote(name) && !ZS.toolNote(name).includes('studio_id')) badSuffix.push(name);
  }
  // Round-trip: needsStudioId must agree with the Set for every mirrored name.
  for (const name of PLACE) {
    if (!ZSEngine.needsStudioId(name)) badScoped.push(`${name} (in set but needsStudioId=false)`);
  }
  ok(badScoped.length === 0, 'place-scope disagreement:\n    ' + badScoped.join('\n    '));
  ok(badSuffix.length === 0, 'place-scoped tools whose note omits studio_id:\n    ' + badSuffix.join(', '));
});

// ── 7. code-transfer templates round-trip byte-for-byte ──────────────────
// The transfer mechanism IS JSON escaping. If a template's code payload does
// not survive a parse, the model learns the wrong escaping from the example.
t('code payloads in templates round-trip byte-for-byte', () => {
  const payloads = [
    // Unity C# with quotes and newlines
    ['create_script', (o) => o.params.contents, 'class PlayerController'],
    // Blender Python
    ['execute_blender_code', (o) => o.params.code, 'import bpy'],
    // Unity structured edits
    ['script_apply_edits', (o) => o.params.edits[0].new_string, 'void Start'],
  ];
  for (const [name, pick, expectSubstr] of payloads) {
    const tpl = ZSEngine.templateFor(name);
    ok(tpl, `${name}: no template`);
    const obj = parseTpl(tpl);
    const s = pick(obj);
    ok(typeof s === 'string' && s.length > 0, `${name}: code payload did not survive parsing`);
    ok(s.includes('\n'), `${name}: code payload lost its newlines (escaping is broken)`);
    ok(s.includes(expectSubstr), `${name}: code payload is not the expected content`);
  }
  // And a quote-bearing payload must come back with REAL quotes, not \" text.
  const cs = parseTpl(ZSEngine.templateFor('create_script')).params.contents;
  ok(cs.includes('"ready"'), 'Unity create_script payload did not restore real double quotes');
});

// ── 8. templates never contain a raw unescaped newline ───────────────────
// A literal newline inside a JSON string is invalid JSON; it only "works" if a
// consumer is lenient. Catch it at the source so the examples stay honest.
t('no template contains a raw newline inside a JSON value', () => {
  const bad = [];
  for (const { id, name } of ALL) {
    const tpl = ZSEngine.templateFor(name);
    if (tpl.includes('\n') || tpl.includes('\r')) bad.push(`${id}/${name}`);
  }
  // Roblox templates are checked by the same loop (ENGINE list omits them).
  for (const name of Object.keys(ZSEngine.ROBLOX_TEMPLATES)) {
    const tpl = ZSEngine.templateFor(name);
    if (tpl.includes('\n') || tpl.includes('\r')) bad.push(`roblox/${name}`);
  }
  ok(bad.length === 0, 'templates with a raw newline (invalid JSON):\n    ' + bad.join('\n    '));
});

// ── 9. no duplicate template keys in the source ──────────────────────────
// This is the one bug JavaScript refuses to report: `{a:1, a:2}` is a syntax
// error in strict-mode JSON but legal (and silently last-wins) in an object
// literal. A duplicated key means the FIRST template is dead code the author
// still believes is shipped - exactly how `search_game_tree` and
// `set_active_instance` each shipped twice in this repo. `node --check` cannot
// see it and neither can a value-level read of the object, so we scan the SOURCE.
t('no duplicate keys in the template / note registries', () => {
  // Isolate a `const NAME = { ... };` block by brace matching from its opener,
  // then collect the top-level `key:` / `key:` occurrences inside it.
  const blockOf = (src, decl) => {
    const at = src.indexOf(decl);
    ok(at >= 0, `could not find ${decl} in engines.js`);
    const open = src.indexOf('{', at);
    let depth = 0, i = open;
    for (; i < src.length; i++) {
      const c = src[i];
      if (c === '{') depth++;
      else if (c === '}') { depth--; if (depth === 0) break; }
    }
    return src.slice(open + 1, i);
  };
  const keysOf = (body) => {
    const keys = [];
    // Walk char-by-char so (a) only depth-0 keys are collected and (b) text
    // inside string literals is skipped - notes are prose full of "foo: bar".
    let d = 0, i = 0;
    while (i < body.length) {
      const c = body[i];
      if (c === '"' || c === "'" || c === '`') {
        const q = c; i++;
        while (i < body.length) {
          if (body[i] === '\\') { i += 2; continue; }
          if (body[i] === q) { i++; break; }
          i++;
        }
        continue;
      }
      if (c === '/' && body[i + 1] === '/') { while (i < body.length && body[i] !== '\n') i++; continue; }
      if (c === '/' && body[i + 1] === '*') { i += 2; while (i < body.length && !(body[i] === '*' && body[i + 1] === '/')) i++; i += 2; continue; }
      if (c === '{' || c === '[' || c === '(') { d++; i++; continue; }
      if (c === '}' || c === ']' || c === ')') { d--; i++; continue; }
      if (d === 0 && /[A-Za-z_$]/.test(c) && (i === 0 || /[\s,{]/.test(body[i - 1]))) {
        const mm = /^([A-Za-z_$][\w$]*)\s*:/.exec(body.slice(i));
        if (mm) { keys.push(mm[1]); i += mm[0].length; continue; }
      }
      i++;
    }
    return keys;
  };
  const dupesFor = (decl) => {
    const keys = keysOf(blockOf(ENGINE_SRC, decl));
    const seen = new Set(), dup = new Set();
    for (const k of keys) { if (seen.has(k)) dup.add(k); seen.add(k); }
    return [...dup];
  };
  const report = [];
  for (const decl of ['const ROBLOX_TEMPLATES = {', 'const ENGINE_TEMPLATES = {',
                      'const ROBLOX_PLACE_TOOLS = ', 'const UNITY_ACTION_OWNERS = ']) {
    if (ENGINE_SRC.indexOf(decl) < 0) continue;
    if (decl.includes('PLACE_TOOLS') || decl.includes('ACTION_OWNERS')) continue; // not object literals
    const d = dupesFor(decl);
    if (d.length) report.push(`${decl.trim()} -> duplicate key(s): ${d.join(', ')}`);
  }
  // The note registries live in both engines.js and config.js.
  for (const [label, src] of [['engines.js', ENGINE_SRC], ['config.js', CONFIG_SRC]]) {
    for (const decl of ['const UNITY_NOTES = {', 'const BLENDER_NOTES = {', 'const GODOT_NOTES = {', 'const TOOL_NOTES = {']) {
      if (src.indexOf(decl) < 0) continue;
      const at = src.indexOf(decl);
      const open = src.indexOf('{', at);
      let depth = 0, i = open;
      for (; i < src.length; i++) {
        const c = src[i];
        if (c === '{') depth++;
        else if (c === '}') { depth--; if (depth === 0) break; }
      }
      const body = src.slice(open + 1, i);
      const keys = keysOf(body);
      const seen = new Set(), dup = new Set();
      for (const k of keys) { if (seen.has(k)) dup.add(k); seen.add(k); }
      if (dup.size) report.push(`${label} ${decl.trim()} -> duplicate key(s): ${[...dup].join(', ')}`);
    }
  }
  ok(report.length === 0, 'duplicate registry keys (last one silently wins):\n    ' + report.join('\n    '));
});

// ── 10. every tool that takes no studio_id is in the global list ─────────
// `list_roblox_studios` is the discovery call a model makes FIRST, so it is the
// worst possible place to inject a bogus studio_id. The place-scope set already
// covers the positive case; this pins the negative one so a future tool cannot
// be added to neither list (undefined behaviour: a note that neither claims nor
// denies the parameter).
t('Roblox global tools are declared and are not place-scoped', () => {
  const GLOBAL = ZSEngine.ROBLOX_GLOBAL_TOOLS;
  ok(Array.isArray(GLOBAL), 'ROBLOX_GLOBAL_TOOLS is not exported as an array');
  const overlap = GLOBAL.filter((n) => ZSEngine.ROBLOX_PLACE_TOOLS.has(n));
  ok(overlap.length === 0, 'a tool is both place-scoped and global: ' + overlap.join(', '));
  ok(GLOBAL.includes('list_roblox_studios'), 'list_roblox_studios must be declared as a global Roblox tool');
  for (const n of GLOBAL) ok(!ZSEngine.needsStudioId(n), `${n} is global yet needsStudioId() is true`);
});

console.log(`\ntest_engine_registry_integrity: ${passed} sections passed`);
