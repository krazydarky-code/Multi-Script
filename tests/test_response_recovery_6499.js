const assert=require('assert'),fs=require('fs'),h=require('../tools/studio_harness'),{entries,html}=require('./support/provider-fixtures');
const policy=new Function(fs.readFileSync(require.resolve('../extension/core/resilience'),'utf8')+';return ZSResilience')();
assert.strictEqual(policy.decide('off','native_response').action,'stop');
assert.strictEqual(policy.decide('standard','native_response',{attempt:1}).action,'stop');
assert.strictEqual(policy.decide('persistent','native_response',{attempt:3}).action,'stop');
assert.strictEqual(policy.decide('persistent','native_response').feedback,'');
(async()=>{
 // Advance the wall clock, not browser timers: reproduce a thinking pause longer
 // than the old 180-second cutoff without changing the shipped wait algorithm.
 for(const id of ['arena','glm','kimi','claude','chatgpt','gemini','clickup','vani']){
  const x=await h.open({provider:'providers/'+id+'.js',url:entries[id].url,html:html(id,'<p>Preparing the code.</p>'),bridge:'up',stateHook:true});assert(x);
  try{const p=x.page;
   await p.evaluate(()=>{const q=__qa;q.beginTaskProgress('Build the original requested feature');Object.assign(q.A,{started:true,stop:false,lastSendOk:true,sendToken:null});window.busy=true;ZSProvider.strictGeneration=true;ZSProvider.isGenerating=()=>busy;ZSProvider.waitingForUser=()=>false;const real=Date.now;window.clockJump=0;Date.now=()=>real()+clockJump;window.result=null;q.waitForResponse(0).then(r=>result=r);});
   await p.waitForTimeout(350);await p.evaluate(()=>clockJump=240000);await p.waitForTimeout(450);
   assert.strictEqual(await p.evaluate(()=>result),null,id+' must keep waiting while native generation is active');
   assert(await p.evaluate(()=>__qa.readTaskProgress().activity.some(e=>e.kind==='waiting')));
   await p.evaluate(()=>busy=false);await p.waitForFunction(()=>result);assert.strictEqual(await p.evaluate(()=>result.kind),'text');assert.deepStrictEqual(x.errors,[]);
   console.log('PASS '+id+': long thinking remains active and settles after generation ends.');
  }finally{await x.close();}
 }
 // Drive the genuine Arena adapter and agent loop through native Retry and its
 // paced/shared send lease. No prompt replay or past tool dispatch is allowed.
 const markup=html('arena','<p>Preparing the feature.</p>').replace('</body>','<script>window.sends=0;document.querySelector("form").onsubmit=e=>{e.preventDefault();sends++;};</script></body>');
 const x=await h.open({provider:'providers/arena.js',url:entries.arena.url,html:markup,bridge:'up',stateHook:true,storage:{msPacingSettings:{mode:'off'},msResilienceSettings:{level:'standard'}},mainTransform:s=>s.replace('P.installSendHooks({','window.__retry=retryNativeResponse;window.__remember=rememberExecuted;\n  P.installSendHooks({')});assert(x);
 try{const p=x.page;
  await p.evaluate(()=>{window.retries=0;window.releases=0;const orig=chrome.runtime.sendMessage;chrome.runtime.sendMessage=(m,cb)=>{if(m.type==='ms_provider_pacing'){if(m.action==='release')releases++;return cb({granted:true,policyVersion:2});}return orig(m,cb);};const item=ZSProvider.lastAssistant();window.item=item;window.addError=()=>{const error=document.createElement('div');error.id='native-error';error.innerHTML='Something went wrong while generating the response.<button id="native-retry">Retry</button><button>Clear</button>';item.append(error);document.querySelector('#native-retry').onclick=()=>{retries++;error.remove();item.querySelector('.prose').textContent='Recovered response. Your requested code is ready.';};};addError();const q=__qa;q.beginTaskProgress('Finish the original task');Object.assign(q.A,{started:true,lastSendOk:true,sendToken:null});q.agentLoop(0);});
  await p.waitForFunction(()=>!__qa.A.running&&retries===1,null,{timeout:25000});assert.strictEqual(await p.evaluate(()=>sends),0);assert.strictEqual(await p.evaluate(()=>releases),1);assert.strictEqual(await p.evaluate(()=>__qa.A.responseFailure||null),null);assert.strictEqual(await p.evaluate(()=>__qa.A.taskOutcome),'response-received');
  assert(await p.evaluate(()=>__qa.readTaskProgress().activity.some(e=>e.kind==='recovery')));
  // Removing error chrome is not acknowledgement of a recovered answer.
  const uncertain=await p.evaluate(async()=>{document.querySelector('#native-error')?.remove();addError();Object.assign(__qa.A,{running:true,userStopped:false,stop:false,sendUnconfirmed:false});document.querySelector('#native-retry').onclick=()=>{retries++;document.querySelector('#native-error').remove();};const before=retries;const ok=await __retry({item,text:'Native failed'},0);__qa.A.running=false;return {ok,clicked:retries-before,unconfirmed:__qa.A.sendUnconfirmed};});
  assert.deepStrictEqual(uncertain,{ok:false,clicked:1,unconfirmed:true});
  // A failing native attempt is bounded by Standard's single-retry budget.
  await p.evaluate(()=>{addError();document.querySelector('#native-retry').onclick=()=>{retries++;const stop=document.createElement('button');stop.id='temporary-stop';stop.setAttribute('aria-label','Stop response');document.querySelector('form').append(stop);setTimeout(()=>stop.remove(),500);};Object.assign(__qa.A,{running:false,stop:false,userStopped:false,sendUnconfirmed:false,lastSendOk:true,responseFailure:null});window.beforeBudget=retries;__qa.agentLoop(0);});
  await p.waitForFunction(()=>!__qa.A.running&&!!__qa.A.responseFailure,null,{timeout:25000});assert.strictEqual(await p.evaluate(()=>retries-beforeBudget),1);assert.strictEqual(await p.evaluate(()=>sends),0);
  // Protected cases must not spend a retry or touch composer/history.
  for(const mode of ['draft','stopped','unconfirmed','historical','disabled','captcha','rate','quota','cancel','executed']){
   const result=await p.evaluate(async mode=>{document.querySelector('#native-error')?.remove();addError();const q=__qa;Object.assign(q.A,{running:true,stop:false,userStopped:false,sendUnconfirmed:false});ZSProvider.getEditor().value=mode==='draft'?'Keep my draft':'';if(mode==='stopped')q.A.stop=true;if(mode==='unconfirmed')q.A.sendUnconfirmed=true;if(mode==='disabled')document.querySelector('#native-retry').disabled=true;if(mode==='captcha')ZSProvider.captchaPresent=()=>true;if(mode==='cancel')setTimeout(()=>q.A.stop=true,250);const target=mode==='historical'?document.createElement('div'):item;if(mode==='executed')__remember(item);const before=retries;const result=await __retry({item:target,text:mode==='rate'?'Too many requests':mode==='quota'?'Daily limit reached':'Native failed'},0);ZSProvider.captchaPresent=()=>false;q.A.running=false;return {result,clicked:retries-before,draft:ZSProvider.editorText()};},mode);
   assert(!result.result&&!result.clicked,mode);if(mode==='draft')assert.strictEqual(result.draft,'Keep my draft');
  }
  assert.deepStrictEqual(x.errors,[]);console.log('PASS native recovery: paced current-reply Retry, shared lease released, no prompt/tool replay, protected draft/stop/unconfirmed/history/disabled/executed/verification cases.');
 }finally{await x.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
