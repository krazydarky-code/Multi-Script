const assert=require('assert'),{createCoworkQueue}=require('../extension/core/studio-workflows');
(async()=>{
  let ctx='venice:chat-a:roblox',isReady=true,sends=[],receipts=[],fits=true;
  const create=initial=>createCoworkQueue({context:()=>ctx,ready:()=>isReady,fits:()=>fits,send:async text=>{sends.push(text);return 7;},delivered:texts=>receipts.push(...texts),initial});
  let q=create();assert(!q.enqueue('no').ok);q.setEnabled(true);assert(q.enqueue('First correction').ok);assert(q.enqueue('Second goal').ok);
  let outgoing='';const base=await q.withFeedback("Output of 'tool': actual result",async text=>{outgoing=text;return 5;});assert.strictEqual(base,5);assert(outgoing.startsWith("Output of 'tool': actual result"));assert(outgoing.includes(JSON.stringify(['First correction','Second goal'])));assert.strictEqual(q.snapshot().pending.length,0);assert.strictEqual(receipts.length,2);
  q.enqueue('Idle task');isReady=false;assert.strictEqual(await q.take(),null);isReady=true;assert.strictEqual((await q.take()).base,7);assert.deepStrictEqual(sends,['Idle task']);
  q.enqueue('Stay in this project');ctx='venice:chat-b:godot';await q.take();assert(q.snapshot().paused&&q.snapshot().pending.length===1);assert(!q.resume().ok);ctx='venice:chat-a:roblox';assert(q.resume().ok);
  fits=false;outgoing='';await q.withFeedback('large result',async text=>{outgoing=text;});assert.strictEqual(outgoing,'large result');assert.strictEqual(q.snapshot().pending.length,1);fits=true;
  await assert.rejects(q.withFeedback('result',async()=>{throw Error('unconfirmed click');}));assert(q.snapshot().paused);assert.strictEqual(q.snapshot().pending[0].status,'unconfirmed');assert(!q.resume().ok);const n=sends.length;await q.take();assert.strictEqual(sends.length,n);
  const id=q.snapshot().pending[0].id;assert(q.remove(id).ok);assert(q.resume().ok);
  q.enqueue('Reload while sending');let release;const pending=q.withFeedback('result',()=>new Promise(r=>{release=r;}));const restored=create(q.snapshot());assert.strictEqual(restored.snapshot().pending[0].status,'unconfirmed');assert(restored.snapshot().paused);assert(!q.remove(q.snapshot().pending[0].id).ok);release(1);await pending;
  q=create();q.setEnabled(true);for(let i=0;i<8;i++)assert(q.enqueue('x'.repeat(16000)).ok);assert(!q.enqueue('one more character').ok);assert(!q.enqueue('x'.repeat(16001)).ok);
  q=create();q.setEnabled(true);for(let i=0;i<20;i++)assert(q.enqueue('request '+i).ok);assert(!q.enqueue('overflow').ok);const clone=q.snapshot();clone.pending.length=0;assert.strictEqual(q.snapshot().pending.length,20);
  q.pause('Stopped by user');q.setEnabled(false);assert.strictEqual(await q.take(),null);q.setEnabled(true);assert(q.snapshot().paused,'Enabling must not undo an explicit pause');
  console.log('PASS queue ordering, tool-result preservation, confirmed receipts, idle sends, context locks, capacity deferral, uncertain-send no replay, reload recovery, bounded storage and Stop pause');
})().catch(e=>{console.error(e.stack);process.exit(1)});
