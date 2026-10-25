const assert=require('assert'),path=require('path'),fs=require('fs'),h=require('../tools/studio_harness'),studio=require('../extension/core/studio-workflows');
for(const data of [{success:false,error:'Luau failed'},{ok:false},{isError:true},{status:'failed'},{errorCount:2}])assert(studio.structuredToolFailure(JSON.stringify(data)));
for(const data of [{success:true,errorCount:0},{ok:true,error:null},{data:{success:false}},{errors:[]},['error']])assert(!studio.structuredToolFailure(JSON.stringify(data)));
const html=`<!doctype html><html><head><style>body{background:#222;color:#eee;font:14px system-ui;margin:0}ol{display:flex;flex-direction:column-reverse;padding:30px;margin:0 auto;width:760px;list-style:none}.mx-auto{width:100%;margin:12px auto}.prose{white-space:pre-wrap}#native-error{border:1px solid #633;padding:16px;color:#f44}form{position:absolute;bottom:20px;left:20%;width:760px}textarea{width:100%;height:80px}button{padding:10px}</style></head><body><ol class="flex-col-reverse"><div class="mx-auto" id="current"><div class="prose">Place is an empty baseplate, so I am building from scratch. Checking the specialist mesh first.</div><div id="native-error"><div>Something went wrong while generating the response. Please try again.</div><small>Trace ID: fixture-only</small><button id="native-retry" type="button">Retry</button><button type="button">Clear</button></div></div><div class="mx-auto justify-end"><div class="prose">Output of 'ms_roblox_run_luau':\nExecuted diagnostic probe.</div></div><div class="mx-auto" id="previous"><div class="prose">{"command":"ms_roblox_run_luau","params":{"code":"return 'probe'"}}</div></div></ol><form><textarea placeholder="Ask anything"></textarea><button aria-label="Send message" type="submit">Send</button></form><script>window.sends=0;document.querySelector('form').onsubmit=e=>{e.preventDefault();sends++;};document.querySelector('#native-retry').onclick=()=>{document.querySelector('#native-error').remove();document.querySelector('#current .prose').textContent='Recovered provider response. No further local calls requested.';};</script></body></html>`;
(async()=>{
 const x=await h.open({html,url:'https://arena.ai/c/failure-fixture',provider:'providers/arena.js',stateHook:true,bridge:'up',storage:{msPacingSettings:{mode:'off'},msResilienceSettings:{level:'off'}},toolHandler:async()=>({ok:true,text:'{"success":false,"error":"Fixture Luau execution failed"}'}),width:1280,height:900});assert(x);
 try{
  const p=x.page;
  await p.evaluate(()=>{const q=__qa;Object.assign(q.A,{started:true,lastSendOk:true,sendToken:null});q.ui.setStarted(true);q.decorate.toolBox(document.querySelector('#previous'),'ms_roblox_run_luau','done','Diagnostic returned',true);q.agentLoop(1);});
  await p.waitForFunction(()=>__qa.A.responseFailure&&!__qa.A.running);
  assert.strictEqual(await p.evaluate(()=>sends),0,'Native failure must not replay the prompt or local tool');
  assert.strictEqual(await p.evaluate(()=>__qa.A.taskOutcome),'provider-failed');
  assert((await p.locator('#zs-state').textContent()).includes('task unverified'));
  assert.strictEqual(await p.locator('#zs-action').textContent(),'Resume response');
  assert((await p.locator('#previous .zs-chip').getAttribute('title')).includes('Individual tool call'));
  await p.click('#zs-action');assert.strictEqual(await p.evaluate(()=>sends),0);assert(await p.evaluate(()=>!!__qa.A.responseFailure));
  const out=path.resolve(__dirname,'../../../../outputs');fs.mkdirSync(out,{recursive:true});await p.screenshot({path:path.join(out,'Provider-failure-paused-6.41.0.png')});
  await p.click('#native-retry');await p.click('#zs-action');await p.waitForFunction(()=>!__qa.A.running&&!__qa.A.responseFailure);
  assert.strictEqual(await p.evaluate(()=>sends),0,'Resume reads the recovered response without re-sending a message');
  assert.strictEqual(await p.evaluate(()=>__qa.A.taskOutcome),'response-received');
  const flags=await p.evaluate(()=>[__qa.feedbackIsError("Output of 'test':\n{\"success\":false,\"error\":\"Luau failed\"}"),__qa.feedbackIsError("Output of 'test':\nError count: 0"),__qa.feedbackIsError("Output of 'test':\n{\"data\":{\"success\":false}}")]);assert.deepStrictEqual(flags,[true,false,false]);
  await p.evaluate(()=>{document.querySelector('#current .prose').innerHTML='<p>Here is an example of the error UI:</p><div>Something went wrong while generating the response.<button>Retry</button><button>Clear</button></div>';});
  assert.strictEqual(await p.evaluate(()=>MSStudio.nativeResponseError(document.querySelector('#current'))),null,'Quoted markdown UI must not be treated as provider failure');
  // A model claiming completion after an actual failed local result must not
  // turn that call green or present the task as verified.
  await p.evaluate(()=>{
    document.querySelector('#current .prose').textContent=JSON.stringify({command:'execute_luau',params:{code:"error('fixture')"}});
    __qa.A.toolList=[{name:'execute_luau',server:'roblox',description:'Fixture executor',inputSchema:{type:'object',properties:{code:{type:'string'}},required:['code']}}];
    __qa.A.studios=[{id:'fixture-studio'}];__qa.A.lastSendOk=true;__qa.A.userStopped=false;
    document.querySelector('form').onsubmit=e=>{e.preventDefault();sends++;const text=document.querySelector('textarea').value;document.querySelector('textarea').value='';const user=document.createElement('div');user.className='mx-auto justify-end';const prose=document.createElement('div');prose.className='prose';prose.textContent=text;user.append(prose);document.querySelector('ol').prepend(user);const assistant=document.createElement('div');assistant.className='mx-auto';assistant.innerHTML='<div class="prose">The task is done.</div>';document.querySelector('ol').prepend(assistant);};
    __qa.agentLoop(1);
  });
  await p.waitForFunction(()=>!__qa.A.running&&__qa.A.taskOutcome==='review-results',null,{timeout:30000});
  assert.strictEqual(await p.locator('#current').getAttribute('data-zphase'),'err');
  assert((await p.locator('#zs-state').textContent()).includes('review results'));
  assert.deepStrictEqual(x.errors,[]);console.log('PASS screenshot-shaped Arena failure overrides partial prose, pauses/unverifies the task, preserves earlier call evidence, blocks replay, explicitly resumes after native Retry, and flags structured tool errors');
 }finally{await x.close();}
})().catch(e=>{console.error(e.stack);process.exit(1)});
