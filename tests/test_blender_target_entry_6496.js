const assert=require('assert'),h=require('../tools/studio_harness'),{html,entries}=require('./support/provider-fixtures');
(async()=>{const x=await h.open({provider:'providers/gemini.js',url:entries.gemini.url,html:html('gemini'),bridge:'up',stateHook:true,mainTransform:s=>s.replace('P.installSendHooks({','window.__targetQA={prepareBlenderCompanion};\n  P.installSendHooks({'),storage:{zsSetupSeen:true,msEnhanceSettings:{mode:'off'}}});assert(x);try{const p=x.page;
 await p.evaluate(()=>{
  window.calls=[];const send=chrome.runtime.sendMessage;
  chrome.runtime.sendMessage=(m,cb)=>{if(m.type!=='ms_blender_companion')return send(m,cb);calls.push(m);const r=m.op==='ensure'?{ok:true,required:true,engines:['blender'],job:{state:'running'}}:{ok:true,running:true,verified:true,aiTarget:true,job:{state:'done'},engines:[{id:'blender',enabled:true,alive:true,connected:true,backend:'headless-workspace',workspaceProject:'cycle-project'}],servers:[{id:'blender',alive:true,workspace:true,tools:4}]};cb?.(r);return Promise.resolve(r);};
  Object.assign(__qa.A,{stop:false,chatOnly:false,bridge:{connected:true,bridgeCapabilities:{blender_companion:true},engines:[{id:'blender',enabled:true,alive:false,connected:false,backend:'headless-workspace',workspaceProject:'cycle-project'}],servers:[{id:'blender',alive:false}]}});
 });
 const offline=await p.evaluate(()=>__qa.systemPrompt());assert(offline.includes('cycle-project')&&offline.includes('stopped or not responding')&&offline.includes('Do not switch to desktop Blender'));
 assert(await p.evaluate(()=>__targetQA.prepareBlenderCompanion(()=>true)));const calls=await p.evaluate(()=>window.calls);assert.deepStrictEqual(calls[0].engines,[],'Standalone headless startup does not require a connected game engine');assert.strictEqual(calls[1].op,'status');
 const ready=await p.evaluate(()=>({prompt:__qa.systemPrompt(),bridge:__qa.A.bridge}));assert(ready.prompt.includes('Real headless Blender is connected to project "cycle-project"'));assert(ready.bridge.servers.find(s=>s.id==='blender').alive,'Fresh server health replaces the old desktop/offline row before tool filtering');
 await p.evaluate(()=>__qa.A.chatOnly=true);assert(!(await p.evaluate(()=>__qa.systemPrompt())).includes('[BLENDER WORKSPACE]'));assert.deepStrictEqual(x.errors,[]);
 console.log('PASS standalone saved-workspace preparation, honest offline/project guidance, fresh server health before catalog filtering and Chat Studio isolation.');
 }finally{await x.close();}})().catch(e=>{console.error(e.stack);process.exit(1)});
