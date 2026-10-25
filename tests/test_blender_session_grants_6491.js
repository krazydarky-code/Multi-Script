const assert=require('assert'),{create}=require('../extension/blender-tabs');
(async()=>{
 let saved={},removed,updated;const calls=[];
 const chrome={runtime:{id:'extension-id'},storage:{session:{get:async()=>saved,set:async r=>Object.assign(saved,r)}},tabs:{onRemoved:{addListener:f=>removed=f},onUpdated:{addListener:f=>updated=f},sendMessage:async(id,m)=>{calls.push({id,m});return {ok:true};}}};
 const tabs={list:async()=>({ok:true,participants:[{tabId:7,context:'current-context'}]}),action:async m=>{calls.push(m);return {ok:true};}};
 const service=create({chrome,tabs}),sender={id:'extension-id',frameId:0,tab:{id:22,url:'http://127.0.0.1:17616/'},url:'http://127.0.0.1:17616/'};
 await assert.rejects(()=>service.handle({action:'list'},sender),/not a connected/);
 await service.remember({id:22,url:'http://127.0.0.1:17616/#launch=private'},7);
 assert(!JSON.stringify(saved).includes('private'),'Launch secrets never stored with tab grants');
 assert.strictEqual((await service.handle({action:'list'},sender)).sourceTabId,7);
 for(const bad of [{...sender,frameId:1},{...sender,id:'other'},{...sender,url:'http://127.0.0.1:9999/'},{...sender,url:'http://127.0.0.1:17616/other'},{...sender,tab:{id:23}}])await assert.rejects(()=>service.handle({action:'list'},bad),/not a connected/);
 await assert.rejects(()=>service.handle({action:'execute',code:'never'},sender),/Unsupported/);
 await service.handle({action:'followup',tabId:7,context:'current-context',requestId:'unique-receipt',text:'Keep model proportions'},sender);
 assert.deepStrictEqual(calls.pop(),{action:'followup',tabId:7,context:'current-context',requestId:'unique-receipt',text:'Keep model proportions',chatOnly:false});
 await service.handle({action:'settings',tabId:7},sender);assert.strictEqual(calls.pop().m.type,'zs-open-menu');assert.strictEqual(calls.pop().action,'focus');
 const restored=create({chrome,tabs});assert((await restored.handle({action:'list'},sender)).ok,'Grants survive service-worker restart');
 updated(22,{url:'https://example.com/'});await new Promise(r=>setTimeout(r,0));await assert.rejects(()=>restored.handle({action:'list'},sender),/not a connected/);
 removed(22);console.log('PASS Blender session grants: exact origin/tab/top frame, no secret storage, context/receipt forwarding, settings focus, worker restart and navigation revocation.');
})().catch(e=>{console.error(e.stack);process.exit(1)});
