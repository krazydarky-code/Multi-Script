const assert=require('assert'),h=require('../tools/studio_harness');
const {html,entries}=require('./support/provider-fixtures');
(async()=>{
 const x=await h.open({provider:'providers/gemini.js',url:entries.gemini.url,html:html('gemini'),bridge:'up',stateHook:true,storage:{zsSetupSeen:true,msEnhanceSettings:{mode:'off'}}});assert(x);
 try{const p=x.page;
  await p.evaluate(()=>{
   Object.assign(ZSProvider.timings,{STABLE_MS:120,GEN_IDLE_MS:80,RESPONSE_TIMEOUT_MS:6000});
   Object.assign(__qa.A,{started:true,stop:false});
   const a=document.createElement('model-response');a.innerHTML='<message-content>{"command":"list_commands","params":{}}</message-content>';document.body.append(a);
   document.querySelector('input-area-v2 mat-icon').setAttribute('fonticon','stop');
   window.result=null;window.responseWait=__qa.waitForResponse(0).then(r=>result=r);
  });
  await p.waitForTimeout(1700);assert.strictEqual(await p.evaluate(()=>result),null,'A complete command frozen longer than STABLE_MS cannot finish while Gemini still shows Stop');
  await p.evaluate(()=>document.querySelector('input-area-v2 mat-icon').setAttribute('fonticon','arrow_upward'));
  await p.waitForFunction(()=>result);assert.strictEqual(await p.evaluate(()=>result.kind),'tool');
  await p.evaluate(()=>{
   window.ready=null;window.canceled=false;window.waitMessages=[];
   document.querySelector('input-area-v2 mat-icon').setAttribute('fonticon','stop');
   ZSProvider.getEditor().textContent='Keep this personal draft';
   ZSProvider.waitForSendReady({timeout:5000,cancelled:()=>canceled,onWait:m=>waitMessages.push(m)}).then(r=>ready=r);
  });
  await p.waitForTimeout(400);assert.strictEqual(await p.evaluate(()=>ready),null);assert.strictEqual(await p.evaluate(()=>ZSProvider.editorText()),'Keep this personal draft');
  await p.evaluate(()=>canceled=true);await p.waitForFunction(()=>ready===false);assert.strictEqual(await p.evaluate(()=>waitMessages.length),1);
  await p.evaluate(()=>{Object.assign(__qa.A,{starting:true,startBeganAt:Date.now()-23000,startStage:3,startPhase:'Tools checked · Gemini is finishing setup'});__qa.ui.setStarting();});
  await p.click('#zs-state');assert(await p.locator('#ms-startup-info').isVisible());assert((await p.locator('#ms-startup-detail').textContent()).includes('23s elapsed'));
  assert.strictEqual(await p.locator('#ms-startup-info [data-state="done"]').count(),2);
  await p.evaluate(()=>{__qa.A.starting=false;__qa.ui.setStarting();});assert(await p.locator('#ms-startup-info').isHidden());
  assert.deepStrictEqual(x.errors,[]);console.log('PASS Gemini slow reply: no premature command execution/follow-up, cancellable draft-safe wait, truthful startup stages and elapsed time.');
 }finally{await x.close();}
})().catch(e=>{console.error(e.stack);process.exit(1)});
