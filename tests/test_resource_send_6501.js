const assert=require('assert'),h=require('../tools/studio_harness'),{entries,html}=require('./support/provider-fixtures');
(async()=>{
 let calls=0;
 const tools=[{name:'ms_roblox_omni',server:'zeroscript',inputSchema:{type:'object'}},{name:'ms_obsidian',server:'zeroscript',inputSchema:{type:'object'}}];
 const x=await h.open({provider:'providers/arena.js',url:entries.arena.url,html:html('arena'),stateHook:true,bridge:'up',tools,storage:{msExecutionEffort:'ultra'},mainTransform:s=>s.replace('P.installSendHooks({','window.__resources={preloadTaskResources,runEnhancedSend,captureSubmission:()=>{submitAndGetBase=async text=>{window.__resourceSent=text;A.lastSendOk=false;return 0;};}};\n P.installSendHooks({'),toolHandler:async m=>{calls++;if(m.arguments.query.includes('slow'))await new Promise(r=>setTimeout(r,400));assert.strictEqual(m.arguments.action,'context');return {ok:true,text:JSON.stringify({library:{available:true,references:522,packages:[{id:'native-ui-kit'}]},recipe:{excerpt:'Use meaningful populated states.'},references:[{id:'ed500_001',pdfPage:2}]})};}});assert(x);
 try{
  const result=await x.page.evaluate(async tools=>{Object.assign(__qa.A,{started:true,toolList:tools,toolNames:new Set(tools.map(t=>t.name))});const request='Create a Roblox inventory UI using OMNI references';const before=ZSProvider.editorText();const first=await __resources.preloadTaskResources(request),second=await __resources.preloadTaskResources(request);return {first,second,before,after:ZSProvider.editorText()};},tools);
  assert(result.first.includes('522')&&result.first.includes('native-ui-kit'));assert.strictEqual(result.first,result.second);assert.strictEqual(calls,1);assert.strictEqual(result.before,result.after);assert.deepStrictEqual(x.errors,[]);
  const cancelled=await x.page.evaluate(async()=>{
    const input=ZSProvider.getEditor();input.value='Create slow OMNI shop';let sends=0;document.querySelector('form').onsubmit=e=>{e.preventDefault();sends++;};
    const promise=__resources.runEnhancedSend(input.value,{text:input.value,enhanced:false});
    setTimeout(()=>{input.value='A newer draft must survive';},120);await promise;
    return {sends,text:input.value};
  });assert.strictEqual(cancelled.sends,0);assert.strictEqual(cancelled.text,'A newer draft must survive');
  const composed=await x.page.evaluate(async()=>{
    const request='Create a Roblox inventory UI using OMNI references';ZSProvider.getEditor().value=request;
    __resources.captureSubmission();await __resources.runEnhancedSend(request,{text:request,enhanced:false});return {request,text:window.__resourceSent};
  });assert(composed.text.startsWith(composed.request));assert(composed.text.includes('LOADED RESOURCES')&&composed.text.includes('522'));
  console.log('PASS real provider chain: one read-only prefetch, cached repeated reads, actual inventory in context unchanged native draft and no send after a draft edit during preload.');
 }finally{await x.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
