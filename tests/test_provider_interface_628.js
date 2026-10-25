// SPDX-License-Identifier: GPL-3.0-or-later
// 6.28: provider compatibility audit. Loads every adapter with a fully stubbed
// DOM and asserts the complete shared ZSProvider floor - the members every
// adapter exports today and core relies on. Catches a future edit dropping a
// method on ONE provider (a per-site runtime break), leftover TODOs, and files
// that no longer parse. Helper scripts (chatgpt-cm, qwen-net, superapp-net) run in the MAIN
// world by design and only need to parse.
const fs = require('fs'), path = require('path'), vm = require('vm');
const root = path.resolve(__dirname, '..');
const ok = (c, m) => { if (!c) throw new Error(m); };

const FLOOR = ['allItems', 'assistantCount', 'chatIsEmpty', 'classifyText', 'clickContinueBtn', 'composerFrame',
  'conversationKey', 'displayName', 'editorText', 'enforceComposer', 'ensureComposerReady', 'findContinueBtn',
  'findToolBlockSpot', 'getEditor', 'id', 'init', 'installSendHooks', 'isAssistantItem', 'isBusyMsg', 'isBusyNow',
  'isFreshChat', 'isGenerating', 'isHardGenerating', 'isTooLongMsg', 'isUserItem', 'itemText', 'lastAssistant',
  'readAssistant', 'scanError', 'setInputLock', 'snapshot', 'stopGeneration', 'streamLen', 'supportsVision',
  'timings', 'turnHalted', 'typeAndSend', 'userCount'];
const HELPERS = new Set(['providers/chatgpt-cm.js', 'providers/qwen-net.js', 'providers/superapp-net.js', 'providers/dom-chat.js']);

const manifest = JSON.parse(fs.readFileSync(path.join(root, 'extension/manifest.json'), 'utf8'));
const listed = new Set();
for (const cs of manifest.content_scripts) for (const j of cs.js) if (j.startsWith('providers/')) listed.add(j);

const stub = () => new Proxy(function () {}, { get: (t, k) => (k === Symbol.toPrimitive ? () => '' : stub()), apply: () => stub(), construct: () => stub() });
let adapters = 0;
for (const file of [...listed].sort()) {
  const src = fs.readFileSync(path.join(root, 'extension', file), 'utf8');
  ok(!/\bTODO\b|\bFIXME\b/.test(src), file + ': leftover TODO/FIXME');
  new Function(src); // parse check for every file, helpers included
  if (HELPERS.has(file)) { console.log('  ok  ' + file + ' (main-world helper, parse-checked)'); continue; }
  const sandbox = { console, document: stub(), window: stub(), chrome: stub(), MutationObserver: stub(),
    requestAnimationFrame: () => 0, setInterval: () => 0, setTimeout: () => 0, clearTimeout: () => {}, clearInterval: () => {},
    navigator: stub(), location: stub(), Node: stub(), CustomEvent: stub(), Event: stub(), getComputedStyle: stub(),
    localStorage: stub(), sessionStorage: stub(), fetch: stub(), URL, Intl, atob: () => '' };
  vm.createContext(sandbox);
  if(src.includes('MSDomChat.create'))vm.runInContext(fs.readFileSync(path.join(root,'extension/providers/dom-chat.js'),'utf8'),sandbox);
  vm.runInContext(src + '\n;globalThis.__P = (typeof ZSProvider !== "undefined") ? ZSProvider : null;', sandbox);
  const P = sandbox.__P;
  ok(P && typeof P === 'object', file + ': does not export ZSProvider');
  const missing = FLOOR.filter((m) => !(m in P));
  ok(!missing.length, file + ': dropped interface members: ' + missing.join(', '));
  adapters++;
  console.log('  ok  ' + file + ' (' + P.id + ', ' + Object.keys(P).length + ' members)');
}
ok(adapters >= 10, 'expected at least 10 adapters, found ' + adapters);
console.log('PASS provider compatibility audit: ' + adapters + ' adapters, full ' + FLOOR.length + '-member interface floor');
