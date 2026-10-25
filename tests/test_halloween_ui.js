// Full extension UI fixture: no login, network or engine connection is used.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const env=require('./playwright-env');env.guard('Halloween UI');
const root=path.resolve(__dirname,'../extension');
(async()=>{
 const browser=await env.launch();if(!browser)env.skip('Halloween UI','browser unavailable');
 try {
  const page=await browser.newPage({viewport:{width:1200,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url());
   if(u.pathname.startsWith('/__ms/')){
    const file=path.resolve(root,u.pathname.slice(6));
    if(!file.startsWith(root+path.sep)||!fs.existsSync(file))return route.fulfill({status:404,body:''});
    return route.fulfill({body:fs.readFileSync(file),contentType:file.endsWith('.json')?'application/json':'text/plain'});
   }
   return route.fulfill({contentType:'text/html',body:'<html><body style="background:#202123;color:white"><h1>SuperApp fixture</h1><div id="composer" data-testid="rich-message-input" style="position:absolute;bottom:35px;left:180px;width:820px"><button aria-label="Send">Send</button></div></body></html>'});
  });
  await page.addInitScript(()=>{
   const data={zsSetupSeen:true,msMenuPreferences:{theme:'scream',barTheme:'auto'}};
   window.chrome={runtime:{id:'qa-extension',getManifest:()=>({version:'6.32.0'}),getURL:p=>'https://superapp.chat/__ms/'+p,lastError:null,onMessage:{addListener(){}},sendMessage:(m,cb)=>{const r={connected:false,tools:[],servers:[]};if(cb)setTimeout(()=>cb(r),0);return Promise.resolve(r);}},storage:{local:{get:(k,cb)=>{if(cb)setTimeout(()=>cb(data),0);return Promise.resolve(data);},set:(v,cb)=>{Object.assign(data,v);cb?.();return Promise.resolve();}},onChanged:{addListener(){}}},i18n:{getMessage:k=>k}};
  });
  await page.goto('https://superapp.chat/');
  await page.addStyleTag({path:path.join(root,'overlay.css')});
  await page.addStyleTag({path:path.join(root,'core/scenes.css')});
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'manifest.json'),'utf8'));
  const block=manifest.content_scripts.find(c=>c.js.includes('providers/superapp.js'));
  await page.addScriptTag({content:block.js.map(f=>fs.readFileSync(path.join(root,f),'utf8')).join('\n;\n')});
  await page.locator('#zs-chat-only').waitFor({state:'attached'});
  assert.equal(await page.locator('#zs-chat-only').evaluate(b=>b.style.display),'');
  assert.equal(await page.locator('#zs-chat-only').isDisabled(),true);
  // The site mounts its composer later, while the extension's status is unchanged.
  await page.evaluate(()=>{const ta=document.createElement('textarea');ta.placeholder='Send a message...';ta.style.cssText='height:70px;width:700px';document.querySelector('#composer').prepend(ta);});
  await page.waitForFunction(()=>!document.querySelector('#zs-chat-only').disabled,{timeout:10000});
  assert.equal(await page.locator('#zs-chat-only').isVisible(),true);
  // Existing conversations also keep the engine-free entry point.
  await page.evaluate(()=>{const list=document.createElement('div');list.setAttribute('role','log');list.style.cssText='position:absolute;left:180px;top:110px;height:420px;width:820px;overflow-y:auto';list.innerHTML='<div data-testid="message-row-user"><div>Remy 10:01 AM</div><div>An existing question</div></div><div data-testid="message-row-assistant"><div>SuperApp 10:02 AM</div><div class="markdown-body">An existing answer</div></div>';document.body.prepend(list);});
  await page.waitForFunction(()=>!ZSProvider.chatIsEmpty());
  assert.equal(await page.locator('#zs-chat-only').isEnabled(),true);
  await page.locator('#zs-switch').click();
  await page.locator('.zs-menu-tabs button[data-tab="look"]').click();
  await page.waitForFunction(()=>document.querySelector('#zs-root').dataset.msTheme==='scream');
  for(const id of ['scream','myers','slender','jason']){
   await page.locator('.zs-theme-opt[data-theme="'+id+'"]').click();
   const result=await page.evaluate(id=>{
    const theme=MSThemes.get(id),root=document.querySelector('#zs-root');
    return {art:theme.art,bg:getComputedStyle(root.querySelector('#zs-menu')).backgroundColor,selected:root.dataset.msTheme,bar:document.querySelector('#zs-bar').dataset.msBarTheme};
   },id);
   assert.ok(result.art.startsWith('data:image/svg+xml'));
   assert.ok(result.bg);
   assert.equal(result.selected,id);assert.equal(result.bar,id);
  }
  await page.locator('.zs-theme-opt[data-theme="scream"]').click();
  await page.screenshot({path:path.resolve(__dirname,'../../../extension-halloween.png')});
  assert.deepEqual(errors,[]);
  console.log('PASS Halloween UI: late composer, existing conversation, four character themes, no page errors');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
