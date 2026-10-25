// Lost acknowledgements must not replay phone commands or mix chat targets.
const assert=require('assert'),{create}=require('../extension/mobile-control');
(async()=>{
 let ticks=0,actions=[],syncs=[],failReceipt=false;
 const packet={id:'request-12345678',tabId:4,context:'original-context',action:'followup',text:'Keep the camera',kind:'correction'};
 const remote=create({identity:async()=> 'profile-12345678',tabs:{list:async()=>({participants:[{tabId:4,ok:true,context:'changed-context'}]}),action:async cmd=>{actions.push(cmd);throw Error('Target chat changed.');}},send:async msg=>{
  syncs.push(structuredClone(msg));ticks++;
  if(ticks===1)return {ok:true,enabled:true,commands:[packet]};
  if(ticks===2&&failReceipt)throw Error('Disconnected');
  return {ok:true,enabled:ticks<5,commands:[]};
 }});
 await remote.tick();assert.strictEqual(actions.length,1);assert.strictEqual(actions[0].context,'original-context');assert.strictEqual(actions[0].requestId,packet.id);
 failReceipt=true;await remote.tick();await remote.tick();assert.strictEqual(syncs[1].payload.receipts.length,1);assert.deepStrictEqual(syncs[2].payload.receipts,syncs[1].payload.receipts,'Retry receipt only, never action');assert.strictEqual(actions.length,1);
 await remote.tick();assert.strictEqual(syncs[3].payload.receipts.length,0);await remote.tick();await remote.tick();assert.deepStrictEqual(syncs[5].payload.participants,[],'Disabled remote forgets cached snapshots');
 let release,sends=0;const busy=create({identity:async()=> 'profile',send:()=>{sends++;return new Promise(r=>release=r);},tabs:{list:async()=>({participants:[]})}});const first=busy.tick();await Promise.resolve();await busy.tick();assert.strictEqual(sends,1);release({ok:true,enabled:false});await first;
 console.log('PASS phone worker: exact target/context and request receipt, lost-ack retry retains receipt only, rejected stale chat never replays, disabled snapshots cleared and overlapping polls serialized.');
})().catch(e=>{console.error(e);process.exitCode=1;});
