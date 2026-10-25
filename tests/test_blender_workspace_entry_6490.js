const assert=require('assert'),h=require('../tools/studio_harness');
const {html,entries}=require('./support/provider-fixtures');
(async()=>{for(const id of ['gemini','chatgpt']){
 const x=await h.open({provider:'providers/'+id+'.js',url:entries[id].url,html:html(id),bridge:'up',stateHook:true,storage:{zsSetupSeen:true,msEnhanceSettings:{mode:'off'}}});assert(x);
 try{const p=x.page;await p.evaluate(()=>{const send=chrome.runtime.sendMessage;window.workspaceOpen=0;chrome.runtime.sendMessage=(msg,cb)=>{if(msg.type==='ms_blender_workspace_open'){workspaceOpen++;cb?.({ok:true,tabId:101});return Promise.resolve({ok:true});}return send(msg,cb);};Object.assign(__qa.A,{started:true,chatOnly:false,bridge:{connected:true,engines:[{id:'blender',connected:true,alive:true,backend:'headless-workspace',workspaceProject:'verified-project'}],servers:[{id:'blender',alive:true,workspace:true}]}});});
  let prompt=await p.evaluate(()=>__qa.systemPrompt());assert(prompt.includes('[BLENDER WORKSPACE]')&&prompt.includes('verified-project')&&prompt.includes('target=workspace'));
  await p.evaluate(()=>__qa.A.chatOnly=true);prompt=await p.evaluate(()=>__qa.systemPrompt());assert(!prompt.includes('[BLENDER WORKSPACE]'),'Chat Studio must not receive active engine instructions');
  await p.click('#ms-blender-open');assert.strictEqual(await p.evaluate(()=>workspaceOpen),1);assert.strictEqual(await p.locator('#ms-blender-open').getAttribute('type'),'button');
  await p.click('#zs-switch');await p.click('.zs-menu-tabs button[data-tab="engines"]');await p.click('#ms-blender-workspace-open');assert.strictEqual(await p.evaluate(()=>workspaceOpen),2);assert((await p.locator('#ms-blender-workspace-status').textContent()).includes('Opened in its own tab'));assert.deepStrictEqual(x.errors,[]);
  console.log('PASS '+id+': discoverable workspace entry sends one open command; headless project instructions stay engine-scoped.');
 }finally{await x.close();}
}})().catch(e=>{console.error(e.stack);process.exit(1)});
