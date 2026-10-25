// Quick Node smoke test for core/parser.js (run: node test-parser.js). Not shipped.
const fs = require("fs");
const ZSParse = new Function(fs.readFileSync(__dirname + "/core/parser.js", "utf8") + "; return ZSParse;")();

const ok = (name, cond) => { console.log((cond ? "PASS" : "FAIL") + "  " + name); if (!cond) process.exitCode = 1; };

const lua = ZSParse.parseToolCalls("###LUA###\nreturn 1+1\n###END_LUA###");
ok("lua block", lua.length === 1 && lua[0].tool === "execute_luau" && lua[0].arguments.code === "return 1+1");
ok("lua defaults to Edit datamodel", lua[0].arguments.datamodel_type === "Edit");

const luaSpaced = ZSParse.parseToolCalls("### LUA ###\nlocal s = 'x'\n### END_LUA ###");
ok("markdown-mangled lua markers", luaSpaced.length === 1 && luaSpaced[0].tool === "execute_luau");

const luaServer = ZSParse.parseToolCalls("###LUA:Server###\nreturn workspace.Name\n###END_LUA###");
ok("lua :Server datamodel", luaServer.length === 1 && luaServer[0].arguments.datamodel_type === "Server" && luaServer[0].arguments.code === "return workspace.Name");

const luaClient = ZSParse.parseToolCalls("### LUA : client ###\nreturn 1\n###END_LUA###");
ok("lua spaced :client datamodel", luaClient.length === 1 && luaClient[0].arguments.datamodel_type === "Client");

// Kimi bleeds its code-block "Copy" button caption into the block text right
// after a lowercase ###lua### marker: `###lua### Copy <code>`. The extracted
// code must NOT start with "Copy" (StudioMCP would reject `Copy task.wait(...)`
// as invalid Lua -> "Failed to parse command code").
const luaCopy = ZSParse.parseToolCalls('###lua### Copy task.wait(4)\nreturn "dom test done"\n###END_LUA###');
ok("strips Copy chrome from bare lua block", luaCopy.length === 1 && luaCopy[0].arguments.code === 'task.wait(4)\nreturn "dom test done"');
// A genuine identifier called Copy (no trailing space eaten) must survive.
const luaCopyIdent = ZSParse.parseToolCalls("###LUA###\nCopy(workspace)\n###END_LUA###");
ok("keeps legit Copy( identifier", luaCopyIdent[0].arguments.code === "Copy(workspace)");

const paramless = ZSParse.parseToolCalls('{"command":"list_commands"}');
ok("paramless command", paramless.length === 1 && paramless[0].tool === "list_commands");

const braces = ZSParse.parseToolCalls('{"command":"multi_edit","params":{"code":"if x then {y} end"}}');
ok("braces inside string value", braces.length === 1 && braces[0].arguments.code === "if x then {y} end");

const legacy = ZSParse.parseToolCalls('{"tool":"script_read","arguments":{"path":"game.Workspace"}}');
ok("legacy tool/arguments schema", legacy.length === 1 && legacy[0].tool === "script_read");

const mcp = ZSParse.parseToolCalls('###MCP_TOOL###\n{"command":"get_studio_state"}\n###END_MCP_TOOL###');
ok("mcp_tool wrapper", mcp.length === 1 && mcp[0].tool === "get_studio_state");

ok("open lua block detected", ZSParse.hasOpenToolBlock("###LUA###\nlocal x=1") === true);
ok("closed lua block not open", ZSParse.hasOpenToolBlock("###LUA###\nreturn 1\n###END_LUA###") === false);
ok("open json command detected", ZSParse.hasOpenToolBlock('{"command":"multi_edit","params":{"a":1') === true);

ok("prose has no signature", ZSParse.hasToolSignature("Here is how you could use a command in theory.") === false);
ok("command shape detected", ZSParse.hasCommandShape('{"command":"x"}') === true);
ok("injected feedback detected", ZSParse.isInjectedFeedback("Output of 'execute_luau':\n2") === true);
ok("parse-error note is feedback not command", ZSParse.isInjectedFeedback('ERROR: bad JSON, write {"command": "name"}') === true);
ok("tool name mid-stream", ZSParse.toolNameFromText('{"command":"multi_ed') === "multi_ed");

// ── salvageCutOff: auto-close a command whose trailing closers were cut ──
// The live Qwen case: a big multi_edit missing exactly ONE final "}".
const cut1 = ZSParse.salvageCutOff('{"command": "multi_edit", "params": {"datamodel_type": "Edit", "file_path": "game.ServerScriptService.AdminHandler", "edits": [{"old_string": "a", "new_string": "b"}]}');
ok("salvage: one missing root brace", cut1 && cut1.tool === "multi_edit" && cut1.arguments.edits.length === 1);
// Two missing closers (params + root) still salvages.
const cut2 = ZSParse.salvageCutOff('{"command": "get_studio_state", "params": {"verbose": true');
ok("salvage: two missing closers", cut2 && cut2.tool === "get_studio_state" && cut2.arguments.verbose === true);
// Cut MID-STRING = real content amputated -> refuse.
ok("salvage refuses mid-string cut", ZSParse.salvageCutOff('{"command": "multi_edit", "params": {"edits": [{"old_string": "elseif command ==') === null);
// Deep deficit (cut between edits: ] } } missing = 3 closers) -> refuse.
ok("salvage refuses deep deficit", ZSParse.salvageCutOff('{"command": "multi_edit", "params": {"edits": [{"old_string": "a", "new_string": "b"}') === null);
// A CLOSED command is not salvage's business.
ok("salvage ignores closed command", ZSParse.salvageCutOff('{"command": "list_commands"}') === null);
// Dangling comma after the last complete value = incomplete next value -> refuse.
ok("salvage refuses trailing comma", ZSParse.salvageCutOff('{"command": "multi_edit", "params": {"edits": [{"old_string": "a"},') === null);
// Escaped quotes inside values must not confuse the string tracking.
const cutEsc = ZSParse.salvageCutOff('{"command": "execute_luau", "params": {"code": "print(\\"hi\\")", "datamodel_type": "Edit"}');
ok("salvage handles escaped quotes", cutEsc && cutEsc.tool === "execute_luau" && cutEsc.arguments.code === 'print("hi")');

// ── Native host markup compatibility ───────────────────────────────────────
const nativeFull = [
  '<|DSML|>tool_calls>',
  '<|DSML|>invoke name="script_read">',
  '<|DSML|>parameter name="target_file" string="true">game.ServerStorage.Multi-Script.Memory</|DSML|>parameter>',
  '</|DSML|>invoke>',
  '</|DSML|>tool_calls>',
].join("\n");
const nativeCalls = ZSParse.parseToolCalls(nativeFull);
ok("native markup normalizes to one call", nativeCalls.length === 1);
ok("native markup preserves tool", nativeCalls[0].tool === "script_read");
ok("native markup preserves parameters", nativeCalls[0].arguments.target_file === "game.ServerStorage.Multi-Script.Memory");
ok("native markup is executable signature", ZSParse.hasToolSignature(nativeFull));
ok("native markup remains command-shaped for camouflage", ZSParse.hasCommandShape(nativeFull));
ok("plain JSON remains preferred", ZSParse.parseToolCalls('{"command":"get_studio_state","params":{}}')[0].tool === "get_studio_state");
