// SPDX-License-Identifier: GPL-3.0-or-later
// Roblox `studio_id` contract regression.
//
// WHY THIS FILE EXISTS
// Roblox's official Studio MCP requires a `studio_id` argument on every
// place-scoped command. Nothing in this product mentioned it, so the model never
// sent it. That is invisible in a single-Studio test because the proxy SILENTLY
// auto-selects a Studio when exactly one is attached - and it is a hard failure
// the moment a second Studio (or a second StudioMCP process) is connected.
//
// Recorded straight out of this repo's own bridge log
// (runtime/logs/bridge_debug.log):
//
//   -> tool  execute_luau(code, datamodel_type, studio_id)
//   <- execute_luau (0.0s): execute_luau: invalid parameters: parameters.studio_id is required
//   [roblox] stderr: WARN ... sent a request without studio_id but multiple studios are connected
//
// The user hit exactly that ("ERROR in execute_luau: execute_luau: invalid
// parameters: parameters.studio_id is required"). The downstream symptom was the
// second screenshot: an out-of-band non-JSON reply, because the model was told to
// go read a giant truncated catalogue instead of being told which parameter it
// dropped. So this file pins BOTH halves of the fix:
//   1. the parameter is DOCUMENTED everywhere the model can see it, and
//   2. it is AUTO-FILLED when unambiguous, and REFUSED (never guessed) when not.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };

const ZSEngine = new Function(read('extension/core/engines.js') + ';return ZSEngine;')();
const ZS = new Function('ZSEngine', read('extension/core/config.js') + ';return ZS;')(ZSEngine);
const mainSrc = read('extension/core/main.js');
const configSrc = read('extension/core/config.js');

const SID = "8521cfad-f8d9-46f4-8cbe-2f0a4e9d1b77";

// ── 1. The registry documents the contract ───────────────────────────────
ok(ZSEngine.ROBLOX_STUDIO_ID === "studio_id", "ROBLOX_STUDIO_ID must be 'studio_id'");
ok(/studio_id is required/.test(ZSEngine.ROBLOX_NOTE), "ROBLOX_NOTE must quote the real server error");
ok(/multiple studios are connected|two or more Studios/i.test(ZSEngine.ROBLOX_NOTE),
  "ROBLOX_NOTE must explain the single-vs-multiple Studio asymmetry (that is why it looks intermittent)");
ok(/list_roblox_studios/.test(ZSEngine.ROBLOX_NOTE), "ROBLOX_NOTE must name the discovery command");

// ── 2. Every place-scoped tool is classified, and nothing else is ─────────
// The list is the set of tools observed in bridge_debug.log taking studio_id,
// plus the other place-scoped ones from the same server.
const MUST_NEED = [
  "execute_luau", "multi_edit", "script_read", "script_search", "script_grep",
  "inspect_instance", "search_game_tree", "get_studio_state", "get_console_output",
  "user_keyboard_input", "user_mouse_input", "start_stop_play", "wait_job_finished",
  "insert_asset", "search_asset", "screen_capture",
];
for (const t of MUST_NEED) ok(ZSEngine.needsStudioId(t), `needsStudioId must cover ${t}`);
// Namespaced/prefixed names must still classify (the bridge can prefix them).
ok(ZSEngine.needsStudioId("roblox/execute_luau"), "prefixed tool names must still classify");
// Tools that do NOT touch a place must be left alone - injecting an unknown
// property into a strict schema is its own failure mode.
for (const t of ["list_roblox_studios", "list_commands", "list_mcp_servers", "ms_studio_director",
                 "get_godot_version", "manage_scene", "execute_blender_code"]) {
  ok(!ZSEngine.needsStudioId(t), `${t} must NOT be treated as needing studio_id`);
}

// ── 3. Auto-fill: applied only when unambiguous ──────────────────────────
// (a) one Studio known -> inject it
let r = ZSEngine.withStudioId("execute_luau", { code: "return 1", datamodel_type: "Edit" }, [{ id: SID }]);
ok(r.ok && r.applied && r.params.studio_id === SID, "one known Studio must be auto-filled");
ok(r.params.code === "return 1" && r.params.datamodel_type === "Edit",
  "auto-fill must not disturb the other parameters");
ok(ZSEngine.withStudioId("execute_luau", { studio_id: SID }, [{ id: SID }]).reason === "already",
  "an explicit studio_id must never be overwritten");
ok(ZSEngine.withStudioId("execute_luau", { studio_id: "" }, [{ id: SID }]).applied === true,
  "an empty-string studio_id must be treated as absent");
// (b) a bare string list (the bridge may hand back strings) still works
ok(ZSEngine.withStudioId("script_read", { target_file: "game.Workspace.A" }, [SID]).params.studio_id === SID,
  "a string-only Studio list must auto-fill");
// (c) TWO Studios -> refuse, and hand back the candidates so the model can choose.
//     Guessing here would silently edit the WRONG place with no error at all.
r = ZSEngine.withStudioId("execute_luau", { code: "return 1" }, [{ id: "studio-a" }, { id: "studio-b" }]);
ok(!r.ok && r.reason === "ambiguous", "multiple Studios must be refused, never guessed");
ok(r.candidates.length === 2 && !r.params.studio_id, "ambiguity must not inject anything");
// (d) nothing learned yet -> refuse and say so (caller tells the model to discover)
ok(ZSEngine.withStudioId("execute_luau", {}, []).reason === "none-known",
  "no known Studio must report none-known");
ok(ZSEngine.withStudioId("execute_luau", {}, [{ id: "   " }]).reason === "none-known",
  "a blank id must not count as a known Studio");
// (e) a non-place tool is left completely untouched
r = ZSEngine.withStudioId("get_godot_version", {}, [{ id: SID }]);
ok(r.reason === "not-roblox" && !r.params.studio_id, "non-place tools must not receive studio_id");

// ── 4. Passive learning from a real answer ───────────────────────────────
// The shape observed live is {"studios":[{"id":"8521cfad-…"}]} (see the jsonSummary
// comment in main.js). The other shapes are tolerated because Studio builds differ.
const learned = ZSEngine.studiosFromBody(`Output of 'list_roblox_studios':\n{"studios":[{"id":"${SID}","name":"Baseplate"}]}`);
ok(learned.length === 1 && learned[0].id === SID, "must learn the id from the wrapped studios shape");
ok(ZSEngine.studiosFromBody(`{"studios_info":[{"id":"${SID}"}]}`).length === 1, "must handle studios_info");
ok(ZSEngine.studiosFromBody(`[{"id":"${SID}"}]`).length === 1, "must handle a bare array");
ok(ZSEngine.studiosFromBody("not json at all").length === 0, "prose must never be mined for ids");
ok(ZSEngine.studiosFromBody("").length === 0, "empty body yields nothing");
// A multi-Studio answer must yield BOTH, so the ambiguity refusal can fire.
ok(ZSEngine.studiosFromBody(`{"studios":[{"id":"studio-a"},{"id":"studio-b"}]}`).length === 2,
  "must learn every Studio, not just the first");

// ── 5. The prompt tells the model, everywhere it looks ───────────────────
const withRoblox = ZS.buildSystemPrompt({ siteName: "X", engines: ["roblox"] });
ok(/studio_id/.test(withRoblox), "the Roblox prompt must name studio_id");
ok(/list_roblox_studios/.test(withRoblox), "the Roblox prompt must tell the model how to obtain it");
ok(/only ONE Studio open the server silently auto-selects|silently auto-selects it/i.test(withRoblox),
  "the Roblox prompt must explain WHY it looks optional");
ok(/"studio_id": "<id from list_roblox_studios>"/.test(withRoblox),
  "the execute_luau example must show studio_id");
// A Roblox+Unity session still gets it (Roblox is present, so the rule applies).
ok(/studio_id/.test(ZS.buildSystemPrompt({ siteName: "X", engines: ["roblox", "unity"] })),
  "a mixed Roblox+Unity session must still get the studio_id rule");
// A Godot-only session must NOT be told about a Roblox parameter it cannot use.
const godotOnly = ZS.buildSystemPrompt({ siteName: "X", engines: ["godot"] });
ok(!/studio_id/.test(godotOnly), "a Godot-only session must not be told about studio_id");

// ── 6. toolNote carries it per command (that is what list_commands prints) ──
const note = ZS.toolNote("execute_luau");
ok(/studio_id/.test(note), "execute_luau's note must carry the studio_id requirement");
ok(/return\b/.test(note), "the pre-existing execute_luau note must survive (appended, not replaced)");
ok(/studio_id/.test(ZS.toolNote("multi_edit")), "multi_edit's note must carry it too");
ok(!/studio_id/.test(ZS.toolNote("get_godot_version")), "a Godot note must not carry it");

// ── 7. main.js wires the fill-in and the corrective error ────────────────
ok(/ZSEngine\.withStudioId/.test(mainSrc), "runTool must call withStudioId");
ok(/ZSEngine\.studiosFromBody/.test(mainSrc), "runTool must learn ids from results");
ok(/studios:\s*\[\]/.test(mainSrc), "state must track learned Studios");
ok(/list_roblox_studios/.test(mainSrc) && /call_tool/.test(mainSrc),
  "the bootstrap must probe list_roblox_studios so the id is known before the first command");
// The corrective error must name the parameter AND the one-vs-many reason -
// this is what stops the model from flailing into a non-JSON reply.
const errOne = ZS.FEEDBACK.studioId("execute_luau", "execute_luau: invalid parameters: parameters.studio_id is required", [SID], []);
ok(/studio_id is REQUIRED on every Roblox place-scoped command/.test(errOne),
  "the required-param error must be specific about studio_id");
ok(/only looks optional because with exactly ONE Studio open/.test(errOne),
  "the studio_id error must explain the asymmetry");
ok(errOne.includes(SID), "the error must name the known Studio id so the retry is immediate");
ok(/Retry the SAME command/.test(errOne), "the error must tell the model to retry the same command");
ok(errOne.includes("execute_luau: invalid parameters: parameters.studio_id is required"),
  "the error must quote the server's own complaint");
// The ambiguous case must explain WHY guessing is refused, not just refuse.
const errMany = ZS.FEEDBACK.studioId("execute_luau", "parameters.studio_id is required", ["a", "b"], ["a", "b"]);
ok(/will not guess which one you mean/.test(errMany), "the ambiguous error must say guessing is refused");
ok(/silently edit the wrong project/.test(errMany), "the ambiguous error must say why that is dangerous");
ok(errMany.includes("a") && errMany.includes("b"), "the ambiguous error must list the candidates");
// The no-id-yet case must point at discovery.
const errNone = ZS.FEEDBACK.studioId("script_read", "parameters.studio_id is required", [], []);
ok(/No Studio id has been learned yet/.test(errNone), "the none-known error must say nothing is learned");
ok(/run list_roblox_studios/.test(errNone), "the none-known error must name the discovery command");
// The generic handler must still exist for every OTHER missing parameter.
ok(/is \(required\|not available\|invalid\)/.test(mainSrc),
  "the generic required-param handler must survive");
ok(/A required or invalid parameter - check the command's parameters/.test(mainSrc),
  "the generic message must survive for non-studio_id parameters");

// ── 8. The old Roblox behaviour is intact (nothing was replaced) ─────────
// The pre-existing notes and prompt rules must be byte-for-byte present; the new
// studio_id text is APPENDED. This is the "check the way it was before" guard.
ok(/Use `return` to produce output - `print\(\)` is NOT captured/.test(configSrc),
  "the original execute_luau return/print guidance must survive");
ok(/Only the FIRST returned value is shown/.test(configSrc),
  "the original execute_luau multi-return line must survive");
ok(/GODOT MCP \(primary non-Roblox engine\): before changing a Godot project, call ms_get_skill with skill_id "godot-mcp-orchestrator"/.test(configSrc),
  "the original Godot rule must survive untouched");
ok(/UNITY MCP: before changing a Unity project, call ms_get_skill with skill_id "unity-mcp-orchestrator"/.test(configSrc),
  "the original Unity rule must survive untouched");
ok(/ALWAYS pass a timeout to WaitForChild/.test(configSrc),
  "the original WaitForChild timeout warning must survive");
ok(/WATCH FOR BAD UNICODE in old_string/.test(configSrc),
  "the original multi_edit unicode warning must survive");

console.log("PASS roblox studio_id contract: required on every place-scoped command, auto-filled when one Studio is known, refused when ambiguous, learned passively from list_roblox_studios, documented in prompt + notes + execute_luau example, and every pre-existing Roblox/Godot/Unity note intact");
