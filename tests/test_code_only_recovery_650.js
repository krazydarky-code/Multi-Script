const assert=require('assert'),e=require('../extension/core/execution-discipline'),h=require('../tools/studio_harness'),{entries,html}=require('./support/provider-fixtures');
const request='Can you recreate Hollow Knight combat and add it to this Roblox place?';
for(const effort of Object.keys(e.PROFILES)){
 for(const text of [request,'Please fix the combo system','I want an inventory','Add movement controls','Optimize the slow menu'])assert(e.create(text,effort,['execute_luau']).intentBuild,text);
 for(const text of ['Explain how to build a combat system','Review this code','How do I create a folder?','Give me only a code block in chat','Create a proposal without editing'])assert(!e.create(text,effort,['execute_luau']).intentBuild,text);
 assert(!e.create(request,effort,['execute_luau'],{engineFree:true}).intentBuild);
}
(async()=>{
 let applied=0;
 const tools=[{name:'execute_luau',server:'roblox',inputSchema:{type:'object',properties:{code:{type:'string'}}}}];
 const x=await h.open({provider:'providers/arena.js',url:entries.arena.url,html:html('arena'),stateHook:true,bridge:'up',tools,storage:{msPacingSettings:{mode:'off'}},toolHandler:async message=>{assert.strictEqual(message.name,'execute_luau');applied++;return {ok:true,text:'Native fixture applied the authorized complete slice.'};}});assert(x);
 try{
  await x.page.evaluate(task=>{
   window.feedbacks=[];window.phase=0;const q=__qa;q.beginTaskProgress(task);Object.assign(q.A,{started:true,lastSendOk:true,sendToken:null,lastUserText:task,toolList:[{name:'execute_luau',server:'roblox'}],toolNames:new Set(['execute_luau']),studios:[{id:'qa'}]});
   ZSProvider.lastAssistant().querySelector('.prose').textContent='Create a LocalScript called CombatController:\n```lua\nlocal combo = 1\n```';
   document.querySelector('form button').type='submit';document.querySelector('form').onsubmit=event=>{
    event.preventDefault();feedbacks.push(ZSProvider.editorText());ZSProvider.getEditor().value='';const user=document.createElement('div');user.className='mx-auto justify-end';user.innerHTML='<div class="prose">Extension feedback</div>';document.querySelector('ol').prepend(user);
    const next=document.createElement('div');next.className='mx-auto';const prose=document.createElement('div');prose.className='prose';prose.textContent=phase++===0?JSON.stringify({command:'execute_luau',params:{code:'local f=Instance.new("Folder");f.Name="QACombat";f.Parent=workspace'}}):'The applied fixture slice is ready for runtime checks.';next.append(prose);document.querySelector('ol').prepend(next);
   };q.agentLoop(0);
  },request);
  await x.page.waitForFunction(()=>!__qa.A.running&&feedbacks.length===2,null,{timeout:30000});
  const feedback=await x.page.evaluate(()=>feedbacks);assert(feedback[0].includes('Original user request:\n'+request));assert(feedback[0].includes('ordinary reply JSON'));assert.strictEqual(applied,1);assert.strictEqual(feedback.filter(x=>x.includes('[MULTI-SCRIPT VERIFICATION CHECK]')).length,1);assert.deepStrictEqual(x.errors,[]);
  console.log('PASS six effort levels: polite/add/fix/clone build intent, read-only protection and one bounded real-agent-loop code-only recovery retaining original request before actual tool dispatch.');
 }finally{await x.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
