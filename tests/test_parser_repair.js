// SPDX-License-Identifier: GPL-3.0-or-later
// The "JSON schema error" class on the chat side: a model (or the chat UI that
// renders it) hands us almost-JSON. The parser must recover the call, and must
// never rewrite code that sits inside a VALID call.
const fs = require('fs'), path = require('path');
const Z = new Function(fs.readFileSync(path.join(__dirname, '../extension/core/parser.js'), 'utf8') + ';return ZSParse;')();
let n = 0; const eq = (name, got, want) => { if (JSON.stringify(got) !== JSON.stringify(want)) { console.error('FAIL ' + name + '\n  got  ' + JSON.stringify(got) + '\n  want ' + JSON.stringify(want)); process.exit(1); } n++; console.log('PASS ' + name); };
const call = (text) => (Z.parseToolCalls(text)[0] || null);
const A = { tool: 'x', arguments: { a: 1 } };
eq('trailing commas', call('{"command":"x","params":{"a":1,},}'), A);
eq('// comments', call('{"command":"x", // why\n"params":{"a":1}}'), A);
eq('single-quoted JSON', call("{'command':'x','params':{'a':1}}"), A);
eq('curly (smart) quotes', call('{“command”:“x”,“params”:{“a”:1}}'), A);
eq('python True/None', call('{"command":"x","params":{"a":true,"b":None}}').arguments, { a: true, b: null });
eq('raw newline inside a string', call('{"command":"x","params":{"code":"l1\nl2"}}').arguments, { code: 'l1\nl2' });
eq('params as a stringified object', call('{"command":"x","params":"{\\"a\\":1}"}'), A);
eq('fenced ```json block', call('```json\n{"command":"x","params":{"a":1}}\n```'), A);
eq('prose around the call', call('Sure! Here you go:\n{"command":"x","params":{"a":1}}\nDone.'), A);
// Valid call whose Lua string legitimately contains curly quotes: must stay byte-identical.
const code = 'print("it’s “fine”")';
eq('curly quotes inside a valid call are preserved', call(JSON.stringify({ command: 'execute_luau', params: { code } })).arguments.code, code);
eq('no call in plain prose', Z.parseToolCalls('The “command” palette is nice.'), []);
eq('hasToolSignature sees curly-quoted calls', Z.hasToolSignature('{“tool”:“x”,“arguments”:{}}'), true);
console.log(`PASS parser repair (${n} checks)`);
