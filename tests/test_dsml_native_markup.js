// DeepSeek's own tool-call markup (DSML) must run, or at least be answered - never a dead "command ... not run" turn.
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const [ZS, ZSParse] = new Function(read('extension/core/parser.js') + '\n' + read('extension/core/config.js') + ';return [ZS, ZSParse];')({ storage: { local: { get() {}, set() {} }, onChanged: { addListener() {} } } });
const MAIN = read('extension/core/main.js');
let failed = 0;
const t = (name, fn) => { try { fn(); console.log('  ok  ' + name); } catch (e) { failed++; console.log('  FAIL ' + name + ': ' + e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m || 'assertion failed'); };
const shapes = {
  'ASCII bars + ">" (older form)': '<|DSML|>tool_calls>\n<|DSML|>invoke name="script_read">\n<|DSML|>parameter name="target_file" string="true">game.SSS.A</|DSML|>parameter>\n</|DSML|>invoke>\n</|DSML|>tool_calls>',
  'full-width bars, no ">"': '<｜DSML｜function_calls>\n<｜DSML｜invoke name="script_read">\n<｜DSML｜parameter name="target_file" string="true">game.SSS.A</｜DSML｜parameter>\n</｜DSML｜invoke>\n</｜DSML｜function_calls>',
  'ASCII bars, no ">"': '<|DSML|function_calls>\n<|DSML|invoke name="script_read">\n<|DSML|parameter name="target_file" string="true">game.SSS.A</|DSML|parameter>\n</|DSML|invoke>\n</|DSML|function_calls>',
  'spaced as rendered': '< | DSML | function_calls>\n< | DSML | invoke name="script_read">\n< | DSML | parameter name="target_file" string="true">game.SSS.A</ | DSML | parameter>\n</ | DSML | invoke>\n</ | DSML | function_calls>',
  'stopped before the closing tags': '<｜DSML｜function_calls>\n<｜DSML｜invoke name="script_read">\n<｜DSML｜parameter name="target_file" string="true">game.SSS.A</｜DSML｜parameter>',
};
for (const [k, v] of Object.entries(shapes)) {
  t('parses: ' + k, () => {
    const c = ZSParse.parseToolCalls(v);
    ok(c.length === 1 && c[0].tool === 'script_read' && c[0].arguments.target_file === 'game.SSS.A', JSON.stringify(c));
    ok(ZSParse.toolNameFromText(v) === 'script_read', 'chip would say ' + ZSParse.toolNameFromText(v));
  });
}
t('typed values: numbers, booleans, JSON, multi-line code and several invokes', () => {
  const v = '<｜DSML｜function_calls>\n<｜DSML｜invoke name="a"><｜DSML｜parameter name="n">5</｜DSML｜parameter><｜DSML｜parameter name="b">true</｜DSML｜parameter><｜DSML｜parameter name="o">{"x":1}</｜DSML｜parameter></｜DSML｜invoke>\n' +
    '<｜DSML｜invoke name="ms_roblox_run_luau"><｜DSML｜parameter name="code" string="true">local a = 1\nif a &lt; 2 then print("&amp;") end</｜DSML｜parameter></｜DSML｜invoke></｜DSML｜function_calls>';
  const c = ZSParse.parseToolCalls(v);
  ok(c.length === 2 && c[0].arguments.n === 5 && c[0].arguments.b === true && c[0].arguments.o.x === 1, JSON.stringify(c));
  ok(/a < 2/.test(c[1].arguments.code) && /"&"/.test(c[1].arguments.code), JSON.stringify(c[1]));
});
t('a value cut off mid-parameter is NOT executed', () => {
  const v = '<｜DSML｜invoke name="ms_roblox_run_luau"><｜DSML｜parameter name="code" string="true">print("half';
  ok(ZSParse.parseToolCalls(v).length === 0);
  ok(ZSParse.toolNameFromText(v) === 'ms_roblox_run_luau');
});
t('a bare marker is detected but unreadable -> handled by the dsml parse_error', () => {
  const v = '<|DSML|>tool_calls>';
  ok(ZSParse.hasToolSignature(v) && ZSParse.parseToolCalls(v).length === 0);
  ok(/ZSParse\.DSML_RE\.test\(r\)\) return \{ kind: "parse_error", reason: "dsml"/.test(MAIN), 'main.js branch missing');
  const f = ZS.FEEDBACK.parseError('dsml', 'ms_roblox_run_luau', '<｜DSML｜invoke name="ms_roblox_run_luau"><｜DSML｜parameter name="code">x');
  ok(/did not run/.test(f) && /ms_roblox_run_luau/.test(f) && /JSON/.test(f), f);
  ok(/did not run/.test(ZS.FEEDBACK.parseError('dsml', 'command', '<|DSML|>tool_calls>')));
});
t('a reply that is only a command but unreadable is answered, whatever the tool name', () => {
  ok(/\^\\s\*\(\?:```\[a-z\]\*\\s\*\)\?\\\{/.test(MAIN.replace(/\n/g, '')) || /command\|tool\)\\s\*\["\\u201d\]\/i\.test\(r\)/.test(MAIN), 'solo-command guard missing');
});
t('ordinary prose that merely mentions DSML-free JSON is unaffected', () => {
  ok(ZSParse.parseToolCalls('Here is how you call it: {"command":"list_commands"}').length === 1);
  ok(ZSParse.parseToolCalls('no tools here').length === 0 && !ZSParse.hasToolSignature('just talking'));
});
console.log(failed ? `\n${failed} FAILED` : '\nall passed');
process.exit(failed ? 1 : 0);
