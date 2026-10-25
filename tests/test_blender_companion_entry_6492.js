const assert=require('assert'),h=require('../tools/studio_harness'),{html,entries}=require('./support/provider-fixtures');
(async()=>{const x=await h.open({provider:'providers/gemini.js',url:entries.gemini.url,html:html('gemini'),bridge:'up',stateHook:true,mainTransform:s=>s.replace('P.installSendHooks({','window.__companion={prepareBlenderCompanion,startSession};\n  P.installSendHooks({'),storage:{zsSetupSeen:true,msEnhanceSettings:{mode:'off'}}});assert(x);
try{const p=x.page;
 await p.evaluate(()=>{
  window.companionCalls=[];window.failCompanion=false;const send=chrome.runtime.sendMessage;
  chrome.runtime.sendMessage=(m,cb)=>{
   if(m.type!=='ms_blender_companion')return send(m,cb);
   companionCalls.push(m);const r=failCompanion?{ok:false,error:'Blender preparation failed'}:m.op==='ensure'?{ok:true,required:true,engines:m.engines,job:{state:'running'}}:m.op==='companion'?{ok:true,companion:m.payload}:{ok:true,running:true,verified:true,aiTarget:true,job:{state:'done'},companion:{engines:['godot']},engines:[{id:'godot',alive:true,connected:true,enabled:true},{id:'blender',alive:true,connected:true,enabled:true,backend:'headless-workspace',workspaceProject:'asset-project'}]};cb?.(r);return Promise.resolve(r);
  };
 });
 for(const engine of ['roblox','unity','godot']){
  await p.evaluate(engine=>{companionCalls=[];Object.assign(__qa.A,{stop:false,chatOnly:false,bridge:{connected:true,bridgeCapabilities:{blender_companion:true},engines:[{id:engine,connected:true,alive:true,enabled:true}]}});},engine);
  assert(await p.evaluate(()=>__companion.prepareBlenderCompanion(()=>true)));const calls=await p.evaluate(()=>companionCalls);assert.strictEqual(calls.length,2);assert.deepStrictEqual(calls[0].engines,[engine]);assert.strictEqual(calls[1].op,'status');assert((await p.evaluate(()=>__qa.systemPrompt())).includes('asset-project'));
 }
 await p.evaluate(()=>{companionCalls=[];failCompanion=true;});const error=await p.evaluate(async()=>{try{await __companion.prepareBlenderCompanion(()=>true);return '';}catch(e){return e.message;}});assert(error.includes('failed'));
 await p.evaluate(()=>{companionCalls=[];failCompanion=false;Object.assign(__qa.A,{started:false,starting:false,chatOnly:false,stop:false});ZSProvider.typeAndSend=async()=>{const e=Error('Fixture stops before provider delivery');e.retryable=false;e.sendState='not-sent';throw e;};});
 await p.evaluate(()=>void __companion.startSession({chatOnly:true}));await p.waitForFunction(()=>!__qa.A.starting);assert.strictEqual(await p.evaluate(()=>companionCalls.length),0,'Chat Studio cannot prepare or start the Blender companion');
 await p.click('#zs-switch');await p.click('[data-tab="engines"]');await p.waitForFunction(()=>document.querySelector('.ms-blender-companion[value="godot"]').checked);await p.check('.ms-blender-companion[value="unity"]');await p.waitForFunction(()=>document.querySelector('#ms-blender-companion-note').textContent.startsWith('Saved.'));assert((await p.evaluate(()=>companionCalls)).some(m=>m.op==='companion'&&m.payload.engines.includes('unity')));
 assert.deepStrictEqual(x.errors,[]);console.log('PASS companion startup for Roblox/Unity/Godot, verified current-project tool instructions, honest preparation failure, engine-free Chat Studio isolation and saved opt-in controls.');
}finally{await x.close();}})().catch(e=>{console.error(e.stack);process.exit(1)});
