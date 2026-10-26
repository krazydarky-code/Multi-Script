// SPDX-License-Identifier: GPL-3.0-or-later
// studio_harness.js - load the REAL Notion content-script chain + overlay.css into a
// mock app.notion.com/chat page inside Chromium, with a fake service worker, so the
// chat bar, terminal panel, "Running" list and settings menu can be driven and
// screenshotted. Used by tests/test_studio_ui.js and for visual QA.
//
//   const { open } = require('./studio_harness'); const h = await open({ bridge: 'up' });
//   await h.page.click('#zs-bridge'); await h.page.screenshot({ path: 'x.png' });
const fs = require('fs');
const path = require('path');
const pw = require('../tests/playwright-env');
const ROOT = path.resolve(__dirname, '..');
const VERSION = JSON.parse(fs.readFileSync(path.join(ROOT, 'extension', 'manifest.json'), 'utf8')).version;
const read = (p) => fs.readFileSync(path.join(ROOT, 'extension', p), 'utf8');

// Variant that mimics Notion's empty-chat state: a heading, a usage banner glued to
// the top of a TALL rounded wrapper, and the real composer card floating in the
// middle of that wrapper. Used to prove the bar docks to the card, not the wrapper.
const EMPTY_TALL_CSS = `
 .main{justify-content:flex-start;padding:0}
 .thread{display:none}
 .hero{width:704px;margin:30px 0 24px;text-align:center;font:600 28px system-ui}
 .wrap{width:704px;display:flex;flex-direction:column}
 .banner{background:#4a3b12;color:#e6d9b0;border-radius:16px 16px 0 0;padding:9px 18px;font-size:12px}
 .shell{background:#202020;border:1px solid #333;border-top:0;border-radius:16px 16px 0 0;margin-top:-8px;height:640px;display:flex;flex-direction:column;justify-content:center;align-items:center;box-sizing:border-box}
 .shell .composer{width:660px}
`;
const NOTION_HTML = (theme, layout) => `<!doctype html><html><head><meta charset="utf-8"><title>Notion AI</title>
<style>
 html,body{margin:0;height:100%;font:14px -apple-system,Segoe UI,sans-serif;background:${theme === 'light' ? '#fff' : '#191919'};color:${theme === 'light' ? '#37352f' : '#e6e6e6'}}
 .layout{display:flex;height:100%}
 .side{width:240px;background:${theme === 'light' ? '#f7f7f5' : '#202020'};padding:14px;box-sizing:border-box}
 .main{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;padding-bottom:28px}
 .thread{width:720px;flex:1;padding:40px 0;overflow:auto}
 .msg{margin:10px 0;line-height:1.5}
 .composer{width:720px;box-sizing:border-box;border-radius:16px;padding:14px 16px 10px;border:1px solid ${theme === 'light' ? '#e0e0dd' : '#3a3a3a'};background:${theme === 'light' ? '#fff' : '#252525'};box-shadow:0 2px 10px rgba(0,0,0,.15)}
 #agent-editor{min-height:44px;outline:none}
 .row{display:flex;gap:8px;align-items:center;margin-top:10px}
 .row button{border:0;border-radius:8px;padding:5px 9px;background:transparent;color:inherit}
 #send{margin-left:auto;background:#2383e2;color:#fff;width:30px;height:30px;border-radius:50%}
${/^empty/.test(layout || '') ? EMPTY_TALL_CSS : ''}${layout === 'empty-bare' ? '.composer{border:0!important;background:transparent!important;box-shadow:none!important;border-radius:0!important;padding:0!important}' : ''}
</style></head><body><div class="layout"><aside class="side"><b>Workspace</b><p>Chat</p><p>Pages</p></aside>
<div class="main">${/^empty/.test(layout || '') ? '<div class="hero">How can I help you today?</div><div class="wrap"><div class="banner">You\'ve used 80% of your trial\'s rolling Notion AI allowance. Manage usage</div><div class="shell">' : ''}<div class="thread" data-testid="notion-agent-panel">
<div class="msg" data-testid="user-message" data-message-id="u1">Build me a small obby in Roblox Studio</div>
<div class="msg" data-testid="agent-message" data-message-id="a1"><p>On it - I will inspect the place first.</p></div></div>
<form class="composer" data-testid="agent-composer"><div id="agent-editor" contenteditable="true" role="textbox" data-placeholder="Do anything with AI…"></div>
<div class="row"><button type="button" aria-label="Add context">+</button><button type="button" id="model" aria-label="Model selector">Auto</button><button type="button" id="send" data-testid="agent-send-message-button" role="button">↑</button></div></form>${/^empty/.test(layout || '') ? '</div></div>' : ''}</div></div><script>
(() => {
  // Mock Notion model picker: a portal menu that appears on pointer/click, with a
  // "More models" row that expands extra models, an Upgrade-locked model and an
  // effort section - the shapes the real detection code has to cope with.
  let menu = null, cur = 'Auto', effort = 'Medium', more = false;
  const btn = document.getElementById('model');
  const close = () => { if (menu) { menu.remove(); menu = null; } };
  const items = () => {
    const base = ['Auto', 'Claude Opus 5.5 New', 'Claude Opus 5', 'Claude Sonnet 5.5', 'GPT-5.6 Sol Upgrade'];
    return base.concat(more ? ['Kimi K3'] : []);
  };
  function render() {
    close();
    menu = document.createElement('div'); menu.setAttribute('role', 'menu'); menu.id = 'mock-model-menu';
    menu.style.cssText = 'position:fixed;left:300px;bottom:130px;width:260px;background:#2b2b2b;color:#eee;border-radius:10px;padding:6px;z-index:99999';
    for (const t of items()) {
      const r = document.createElement('div'); r.setAttribute('role', 'menuitem'); r.textContent = t; r.style.cssText = 'padding:6px 8px';
      if (/Upgrade/.test(t)) r.setAttribute('aria-disabled', 'true');
      if (t.replace(/ New| Upgrade/g, '') === cur) r.setAttribute('aria-checked', 'true');
      r.addEventListener('click', () => { if (r.getAttribute('aria-disabled') === 'true') return; cur = t.replace(/ New| Upgrade/g, ''); btn.textContent = cur; close(); });
      menu.appendChild(r);
    }
    if (!more) { const r = document.createElement('div'); r.setAttribute('role', 'menuitem'); r.textContent = 'More models'; r.style.cssText = 'padding:6px 8px'; r.addEventListener('click', (e) => { e.stopPropagation(); more = true; render(); }); menu.appendChild(r); }
    for (const e of ['Low', 'Medium', 'High', 'Max']) {
      const r = document.createElement('div'); r.setAttribute('role', 'menuitemradio'); r.textContent = e; r.style.cssText = 'padding:6px 8px';
      if (e === effort) r.setAttribute('aria-checked', 'true');
      r.addEventListener('click', () => { effort = e; window.__mockEffort = e; close(); });
      menu.appendChild(r);
    }
    document.body.appendChild(menu);
  }
  btn.addEventListener('click', () => { menu ? close() : render(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
  window.__mock = { get cur() { return cur; }, get effort() { return effort; }, get open() { return !!menu; } };
  const banner = document.createElement('a'); banner.setAttribute('role', 'button'); banner.textContent = 'Trial ends in 6 days'; banner.style.cssText = 'position:fixed;left:14px;bottom:14px;font-size:12px';
  document.body.appendChild(banner);
})();
</script></body></html>`;

// Minimal claude.ai-shaped page: a rounded <fieldset> composer holding a ProseMirror
// editor, with the send control in a footer row. Used to prove the generic dock.
const CLAUDE_HTML = (theme) => `<!doctype html><html><head><meta charset="utf-8"><title>Claude</title><style>
 html,body{margin:0;height:100%;font:14px system-ui,sans-serif;background:${theme === 'light' ? '#faf9f5' : '#262624'};color:${theme === 'light' ? '#141413' : '#eee'}}
 .main{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center}
 h1{font:500 32px Georgia,serif;margin:0 0 28px}
 fieldset{border:1px solid ${theme === 'light' ? '#ddd' : '#3d3d3a'};border-radius:22px;width:680px;box-sizing:border-box;padding:14px 16px 10px;background:${theme === 'light' ? '#fff' : '#30302e'};margin:0}
 .ProseMirror{min-height:48px;outline:none}
 .foot{display:flex;gap:8px;align-items:center;margin-top:8px}
 .foot button{border:0;background:transparent;color:inherit;border-radius:8px;padding:5px 8px}
 .send{margin-left:auto;background:#d97757!important;color:#fff!important}
</style></head><body><div class="main"><h1>How can I help you today?</h1><fieldset><div class="ProseMirror" contenteditable="true" role="textbox" aria-label="Write your prompt to Claude"><p data-placeholder="How can I help you today?"><br></p></div>
<div class="foot"><button type="button" aria-label="Add files">+</button><button type="button" data-testid="model-selector-dropdown">Opus 5.5</button><button type="button" class="send" aria-label="Send message">↑</button></div></fieldset></div></body></html>`;

function chromeStub(opts) {
  return `(() => {
    const store = Object.assign({}, ${JSON.stringify(opts.storage || {})});
    const listeners = []; window.__msListeners=listeners;
    const o = ${JSON.stringify(opts)};
    const state = { host: o.host || 'installed', bridge: o.bridge || 'up', busy: false, calls: [] };
    window.__ms = state; window.__store = store;
    const ring = [
      {seq:1,t:'18:02:06',level:'info',msg:'===== BRIDGE START  v${VERSION}  pid=4120 ====='},
      {seq:2,t:'18:02:06',level:'info',msg:'configured 3 MCP server(s): roblox, unity, godot'},
      {seq:3,t:'18:02:07',level:'ok',msg:'[roblox] connected - 42 tools'},
      {seq:4,t:'18:02:08',level:'ok',msg:'[godot] connected - 14 tools'},
      {seq:5,t:'18:02:09',level:'warn',msg:'[unity] no editor attached yet (open a project with the MCP package)'},
      {seq:6,t:'18:02:31',level:'info',msg:'tool call execute_luau -> ok (212 ms)'},
      {seq:7,t:'18:02:31',level:'warn',msg:'schema auto-repair: renamed path to file_path; clamped count 9 to 5'},
    ];
    const service = () => ({bridgeVersion:'${VERSION}',port:17613,uptimeSeconds:754,clients:2,
      servers:[{id:'roblox',alive:true,tools:42},{id:'unity',alive:false,tools:0},{id:'godot',alive:true,tools:14}],ringSize:7,ringMax:600});
    const status = () => ({ok:true,connected:state.bridge==='up',mcpAlive:state.bridge==='up',studio:true,studioApp:true,studioProc:true,tools:56,
      servers:state.bridge==='up'?service().servers:[],engines:state.bridge==='up'?[{id:'roblox',connected:true,alive:true},{id:'godot',connected:true,alive:true}]:[]});
    const reply = (m) => {
      state.calls.push(m.type);
      switch (m.type) {
        case 'status': return status();
        case 'list_tools': return {ok:true,tools:o.tools||[]};
        case 'call_tool': return window.__msTestTool ? window.__msTestTool(m) : {ok:true,result:{text:'{}'}};
        case 'ms_mobile_admin': return window.__msMobileAdmin ? window.__msMobileAdmin(m) : {ok:false,error:'Phone control requires the current running bridge.'};
        case 'ms_update_admin': return window.__msUpdateAdmin ? window.__msUpdateAdmin(m) : (o.updateState||{ok:true,current:'${VERSION}',configured:false,automatic:true});
        case 'ms_obsidian_admin': return window.__msVaultAdmin ? window.__msVaultAdmin(m) : (o.vaultState||{ok:true,configured:false,available:false});
        case 'ms_blockbench_admin': return window.__msBlockbenchAdmin ? window.__msBlockbenchAdmin(m) : (o.blockbenchState||{ok:true,prepared:false,connected:false});
        case 'ms_cowork_tabs': return window.__msCoworkTabs ? window.__msCoworkTabs(m) : {ok:false,error:'Provider tab discovery requires the extension service worker.'};
        case 'terminal_snapshot': return state.bridge==='up' ? {ok:true,via:'ws',lines:ring.filter(r=>r.seq>(m.since||0)),newest:7,service:service()} : {ok:false,kind:'unreachable'};
        case 'host_info': return state.host==='installed' ? {ok:true,hostVersion:'1.0.0',pythonVersion:'3.12.4',platform:'win32'} : {ok:false,code:'host_missing',error:'Specified native messaging host not found.',extensionId:'abcdefghijklmnopabcdefghijklmnop'};
        case 'host_prefs': return {ok:true,autoStart:true,userStopped:false,extensionId:'abcdefghijklmnopabcdefghijklmnop'};
        case 'host_processes': return state.host==='installed' ? {ok:true,listening:state.bridge==='up',processes:[{pid:4120,role:'bridge',label:'Multi-Script bridge'},{pid:4188,role:'mcp',label:'Godot MCP'},{pid:4190,role:'mcp',label:'Roblox MCP launcher'}],apps:[{pid:900,role:'app',label:'Roblox Studio'},{pid:1200,role:'app',label:'Blender'}]} : {ok:false,code:'host_missing',extensionId:'abcdefghijklmnopabcdefghijklmnop'};
        case 'host_start': case 'host_restart': if (state.host!=='installed') return {ok:false,code:'host_missing',extensionId:'abcdefghijklmnopabcdefghijklmnop'}; state.bridge='up'; return {ok:true,started:true,listening:true,pid:4120};
        case 'host_stop': state.bridge='down'; return {ok:true,stopped:[4120],listening:false};
        case 'host_tail': return {ok:true,lines:['Traceback (most recent call last):','  File "bridge.py", line 1, in <module>','ModuleNotFoundError: No module named websockets'],listening:false};
        default: return {ok:true};
      }
    };
    window.chrome = {
      runtime: { id:'abcdefghijklmnopabcdefghijklmnop', lastError: undefined,
        getURL: (p) => p==='icon.png' ? 'data:image/png;base64,${fs.readFileSync(path.join(ROOT,'extension','icon.png')).toString('base64')}' : 'chrome-extension://abc/' + p,
        getManifest: () => ({ version: '${VERSION}', name: 'Multi-Script' }),
        sendMessage: (m, cb) => { Promise.resolve(reply(m)).then(r=>setTimeout(() => cb && cb(r), 15)); },
        onMessage: { addListener: (f) => listeners.push(f) } },
      storage: { local: {
        get: (k, cb) => { const out = {}; (Array.isArray(k) ? k : typeof k === 'string' ? [k] : Object.keys(k||{})).forEach(x => { if (x in store) out[x] = store[x]; }); cb && setTimeout(() => cb(out), 0); },
        set: (v, cb) => { Object.assign(store, v); cb && setTimeout(cb, 0); } } },
    };
    window.__deliver = (msg) => listeners.forEach(f => f(msg, {}, () => {}));
  })();`;
}

async function open(opts = {}) {
  const browser = await pw.launch();
  if (!browser) return null;
  const ctx = await browser.newContext({ viewport: { width: opts.width || 1280, height: opts.height || 800 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  if(opts.toolHandler)await page.exposeFunction("__msTestTool",opts.toolHandler);
  const errors = [];
  page.on('pageerror', (e) => errors.push(process.env.STACK ? String(e.stack) : String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.route('**/*', (r) => r.fulfill({ contentType: 'text/html', body: opts.html || (opts.site === 'claude' ? CLAUDE_HTML(opts.theme) : NOTION_HTML(opts.theme, opts.layout)) }));
  await page.addInitScript(chromeStub(opts));
  await page.goto(opts.url || (opts.site === 'claude' ? 'https://claude.ai/new' : 'https://app.notion.com/chat'));
  // Use the shipped provider chain, including dependency additions and CSS order.
  // A second hand-maintained load list can silently omit the very runtime under test.
  const provider=opts.provider || (opts.site==='claude'?'providers/claude.js':'providers/notion.js');
  const manifest=JSON.parse(read('manifest.json'));
  const block=manifest.content_scripts.find(entry=>(entry.js||[]).includes(provider)&&(entry.js||[]).includes('core/main.js'));
  if(!block)throw Error('No shipped content-script chain for '+provider);
  for(const file of block.css||[])await page.addStyleTag({content:read(file)});
  for (const f of block.js) {
    let source=read(f);if(f==='core/main.js'&&opts.mainTransform)source=opts.mainTransform(source);if(opts.stateHook&&f==='core/main.js')source=source.replace('P.installSendHooks({','window.__qa={A,ui,agentLoop,waitForResponse,feedbackIsError,decorate,taskPromptAddon,skillScopeKey,activeCustomSkills,beginTaskProgress,readTaskProgress,runTool,systemPrompt,startupPrompt,enhanceFacts};\n  P.installSendHooks({');
    await page.addScriptTag({ content: source });
  }
  await page.waitForSelector('#zs-bar', { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(500);
  return { browser, page, errors, close: () => browser.close() };
}
module.exports = { open };
