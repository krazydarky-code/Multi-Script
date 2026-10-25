// Real shipped chains in Chromium, reduced provider DOM, real parser/chip UI.
// No provider model, authentication, quota or native editor is simulated as live.
const fs=require('fs'),path=require('path'),assert=require('assert'),pw=require('./playwright-env');
const {entries,html}=require('./support/provider-fixtures');
const root=path.resolve(__dirname,'..'),read=f=>fs.readFileSync(path.join(root,'extension',f),'utf8');
const manifest=JSON.parse(read('manifest.json'));
(async()=>{const browser=await pw.launch();assert(browser);let count=0;try{
 for(const [id,x] of Object.entries(entries)){
  const p=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];p.on('pageerror',e=>errors.push(e.stack));
  await p.route('**/*',r=>r.fulfill({contentType:'text/html',body:html(id)}));
  await p.addInitScript(({version})=>{const store={zsSetupSeen:true,msEnhanceSettings:{mode:'off'},msMenuPreferences:{barDock:'window'}};
   window.chrome={runtime:{id:'fixture',getManifest:()=>({version}),getURL:f=>'https://fixture.test/'+f,onMessage:{addListener(){}},sendMessage:(m,cb)=>{const data=m.type==='status'?{ok:true,connected:true,mcpAlive:true,tools:0,servers:[],engines:[]}:m.type==='list_tools'?{ok:true,tools:[]}:{ok:true};setTimeout(()=>cb?.(data),0);}},storage:{local:{get:(keys,cb)=>setTimeout(()=>cb?.(Object.fromEntries((Array.isArray(keys)?keys:[keys]).filter(k=>k in store).map(k=>[k,store[k]]))),0),set:(v,cb)=>{Object.assign(store,v);cb?.();}},onChanged:{addListener(){}}}};
  },{version:manifest.version});
  await p.goto(x.url);await p.addStyleTag({content:read('overlay.css')});await p.addStyleTag({content:read('core/scenes.css')});
  const chain=manifest.content_scripts.find(c=>c.js.includes('providers/'+id+'.js')).js;
  for(const file of chain){let source=read(file);if(file==='core/main.js')source=source.replace('P.installSendHooks({','window.__qa={A,ui,decorate,systemPrompt,taskPromptAddon,waitForResponse};\n  P.installSendHooks({');await p.addScriptTag({content:source});}
  await p.waitForSelector('#zs-bar');await p.waitForTimeout(120);
  const probe=await p.evaluate(()=>({id:ZSProvider.id,editor:!!ZSProvider.getEditor(),users:ZSProvider.userCount(),assistants:ZSProvider.assistantCount(),reply:ZSProvider.readAssistant().reply,calls:ZSParse.parseToolCalls(ZSProvider.readAssistant().reply)}));
  assert.strictEqual(probe.id,id);assert(probe.editor,id+' composer');assert.strictEqual(probe.users,1,id+' user roles');assert.strictEqual(probe.assistants,1,id+' assistant roles');assert.strictEqual(probe.calls[0]?.tool,'ms_get_skill',id+' parse: '+probe.reply);count+=5;
  const chip=await p.evaluate(()=>{const item=ZSProvider.lastAssistant(),before=ZSProvider.readAssistant().reply;__qa.decorate.chip(item,{label:'ms_get_skill',body:'Actual result would be shown here',phase:'done',category:'tool'});return {before,after:ZSProvider.readAssistant().reply,count:item.querySelectorAll('.zs-chip').length};});
  assert.strictEqual(chip.count,1,id+' one chip');
  assert.strictEqual(chip.after,chip.before,id+' chip decoration preserves parser source');
  assert(!chip.after.includes('Actual result would be shown here'),id+' chip body never executed');count+=3;
  if(id==='venice'){
   const failure=await p.evaluate(async()=>{const item=ZSProvider.lastAssistant();item.setAttribute('data-is-error','true');const result=await __qa.waitForResponse(0);item.removeAttribute('data-is-error');return result.kind;});
   assert.strictEqual(failure,'provider_error','Native Venice error flags override an otherwise parseable command');count++;
  }
  await p.click('#zs-switch');await p.click('[data-tab="agent"]');
  assert(await p.locator('#ms-effort-range').count()||await p.locator('input[type="range"][max="5"]').count(),id+' six-step effort control');
  assert(await p.locator('#ms-critic-enabled').count(),id+' Critic in Agent settings');count+=2;
  for(const [index,effort] of ['adaptive','quick','standard','deep','maximum','ultra'].entries()){
   const result=await p.evaluate(({index})=>{const slider=document.querySelector('#ms-effort-slider');slider.value=String(index);slider.dispatchEvent(new Event('input',{bubbles:true}));return {effort:document.documentElement.dataset.msEffort,label:document.querySelector('#ms-effort-label').textContent,prompt:__qa.systemPrompt(),addon:__qa.taskPromptAddon('Build a polished game UI with actual test evidence.')};},{index});
   assert.strictEqual(result.effort,effort,id+' effort '+effort);assert(result.prompt.includes('EFFORT='+effort),id+' startup receives '+effort);assert.strictEqual(result.addon.includes('ULTRA · EXECUTION METHODS'),effort==='ultra',id+' Ultra routing only at final stop');count+=3;
  }
  if(!await p.locator('#ms-critic-enabled').isVisible())await p.locator('.zs-menu-sec').filter({has:p.locator('#ms-critic-enabled')}).locator('.zs-sec-label').click();
  await p.locator('#ms-critic-enabled').uncheck();assert(!(await p.evaluate(()=>__qa.taskPromptAddon('Build a game UI.'))).includes('CRITIC · PROMPT ADD-ON'),id+' Critic off');count++;
  await p.locator('#ms-critic-enabled').check();await p.locator('#ms-critic-passes').selectOption('2');assert((await p.evaluate(()=>__qa.taskPromptAddon('Build a game UI.'))).includes('2 review passes'),id+' chosen Critic passes');count++;
  await p.click('[data-tab="workshop"]');assert(await p.locator('#ms-library-search').count(),id+' skills library');count++;
  assert.deepStrictEqual(errors,[],id+' no content-script exceptions');count++;
  console.log('PASS '+id+': real chain, roles, command parse, chip source, Agent/Ultra/Critic and skills UI');await p.close();
 }
 console.log(`PASS all ${Object.keys(entries).length} provider browser fixtures; ${count} assertions.`);
}finally{await browser.close();}})().catch(e=>{console.error(e.stack);process.exit(1)});
