// Real Chromium + the full SuperApp extension chain. No live login/network.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const env = require('./playwright-env'); env.guard('enhanced prompt browser send');
const root = path.resolve(__dirname, '../extension');
const sourceText = 'make the door open when the player touches it';
const scenarios = [
 { name:'fresh enhanced send', stopped:false, action:'send' },
 { name:'enhanced send after Stop', stopped:true, action:'send' },
 { name:'original send after Stop', stopped:true, action:'original' },
 { name:'edited enhanced send after Stop', stopped:true, action:'send', edited:true },
 { name:'automatic enhancement after Stop', stopped:true, preview:false },
 { name:'Cancel preserves draft', stopped:true, action:'cancel', noSend:true },
 { name:'Stop during review cancels send', action:'send', stopDuring:true, noSend:true },
 { name:'navigation during review cancels send', action:'send', navigate:true, noSend:true },
];
(async () => {
 const browser = await env.launch(); if (!browser) env.skip('enhanced prompt browser send','browser unavailable');
 try {
  for (const scenario of scenarios) {
   const page = await browser.newPage({viewport:{width:1200,height:900}});
   const errors=[]; page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/*', async route=>{
    const u=new URL(route.request().url());
    if(u.pathname.startsWith('/__ms/')) return route.fulfill({body:fs.readFileSync(path.join(root,u.pathname.slice(6))),contentType:'text/plain'});
    await route.fulfill({contentType:'text/html',body:`<html><body><div role="log" style="position:absolute;top:30px;left:180px;width:800px;height:400px;overflow-y:auto"><div data-testid="message-row-user">A previous question</div><div data-testid="message-row-assistant"><div class="markdown-body">A previous answer</div></div></div><div data-testid="rich-message-input" style="position:absolute;bottom:30px;left:180px;width:800px"><textarea placeholder="Send a message" style="width:700px;height:80px"></textarea><button aria-label="Send">Send</button></div><script>window.sent=[];document.querySelector('button').addEventListener('click',()=>{const t=document.querySelector('textarea');if(!t.value.trim())return;window.sent.push(t.value);const r=document.createElement('div');r.dataset.testid='message-row-user';r.textContent=t.value;document.querySelector('[role=log]').append(r);t.value='';t.dispatchEvent(new Event('input',{bubbles:true}));});</script></body></html>`});
   });
   await page.addInitScript(scenario=>{
    const data={zsSetupSeen:true,msEnhanceSettings:{mode:'balanced',preview:scenario.preview!==false},msPacingSettings:{mode:'off'},msCriticSettings:{enabled:false,passes:3}};
    window.chrome={runtime:{id:'qa-extension',getManifest:()=>({version:'6.36.1'}),getURL:p=>'https://superapp.chat/__ms/'+p,onMessage:{addListener(){}},sendMessage:(m,cb)=>{const r={connected:false,tools:[],servers:[]};if(cb)setTimeout(()=>cb(r),0);return Promise.resolve(r);}},storage:{local:{get:(k,cb)=>{if(cb)setTimeout(()=>cb(data),0);return Promise.resolve(data);},set:(v,cb)=>{Object.assign(data,v);cb?.();return Promise.resolve();}},onChanged:{addListener(){}}},i18n:{getMessage:k=>k}};
   },scenario);
   await page.goto('https://superapp.chat/');
   await page.addStyleTag({path:path.join(root,'overlay.css')});
   const manifest=JSON.parse(fs.readFileSync(path.join(root,'manifest.json')));
   const chain=manifest.content_scripts.find(c=>c.js.includes('providers/superapp.js')).js;
   const source=chain.map(f=>{
    const t=fs.readFileSync(path.join(root,f),'utf8');
    // Expose state only in this in-memory test copy, never in shipped JS.
    return f==='core/main.js'?t.replace('P.installSendHooks({','window.__msQA={state:A,stopLoop};\n  P.installSendHooks({'):t;
   }).join('\n;\n');
   await page.addScriptTag({content:source});
   await page.waitForTimeout(300);
   await page.evaluate(stopped=>{Object.assign(__msQA.state,{started:true,chatOnly:true,stop:!!stopped,userStopped:!!stopped,running:false,starting:false});},scenario.stopped);
   const composer=page.locator('[data-testid="rich-message-input"] textarea');
   await composer.fill(sourceText);
   await composer.press('Enter');
   if(scenario.preview!==false){
    const review=page.locator('.zs-enhance-review'); await review.waitFor();
    assert.equal(await page.evaluate(()=>sent.length),0,'review must hold the native send');
    if(scenario.edited) await review.locator('textarea').fill('My edited improved prompt');
    if(scenario.stopDuring) await page.evaluate(()=>__msQA.stopLoop());
    if(scenario.navigate) await page.evaluate(()=>history.pushState({},'', '/chat/another'));
    await review.locator('[data-action='+scenario.action+']').click();
   }
   if(scenario.noSend) await page.waitForTimeout(600);
   else await page.waitForFunction(()=>window.sent.length>0,null,{timeout:10000});
   // Observe beyond the event turn to detect an accidental second send.
   await page.waitForTimeout(400);
   const sent=await page.evaluate(()=>window.sent);
   assert.equal(sent.length,scenario.noSend?0:1,scenario.name);
   if(scenario.noSend) assert.equal(await composer.inputValue(),sourceText);
   else if(scenario.action==='original'){assert(sent[0].startsWith(sourceText+'\n\n'));assert(!sent[0].includes('ENHANCED BRIEF'));}
   else if(scenario.edited){assert(sent[0].startsWith(sourceText+'\n\n'));assert(sent[0].includes('My edited improved prompt'));}
   else assert.match(sent[0],/ENHANCED BRIEF/);
   await page.waitForFunction(()=>!__msQA.state.enhanceBusy,null,{timeout:5000});
   assert.deepEqual(errors,[],scenario.name);
   console.log('PASS '+scenario.name);
   await page.close();
  }
  console.log('PASS 8 full-chain Chromium enhanced-prompt send scenarios');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
