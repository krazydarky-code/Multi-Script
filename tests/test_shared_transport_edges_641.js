const assert=require('assert'),path=require('path'),pw=require('./playwright-env');
const {entries,html}=require('./support/provider-fixtures');
(async()=>{const browser=await pw.launch();assert(browser);try{
 for(const id of ['vani','venice','clickup']){
  const p=await browser.newPage();await p.route('**/*',r=>r.fulfill({body:html(id),contentType:'text/html'}));await p.goto(entries[id].url);
  for(const file of ['core/parser.js','providers/dom-chat.js','providers/'+id+'.js'])await p.addScriptTag({path:path.join(__dirname,'../extension',file)});
  const result=await p.evaluate(()=>{
   const p=ZSProvider,before=p.readAssistant().reply,id=p.lastAssistantId(),item=p.lastAssistant();
   const command=item.querySelector('p:not([data-turn-model])')||item.querySelector('.prose');command.classList.add('zs-tool-hide');command.style.display='none';
   const chip=document.createElement('div');chip.className='zs-chip';chip.textContent='{"command":"must_not_execute_chip","params":{}}';item.append(chip);
   const hidden=p.readAssistant().reply;
   const alert=document.createElement('div');alert.setAttribute('role','alert');alert.textContent='message too long';item.append(alert);const error=p.scanError();alert.remove();
   const sourceKey=p.itemKey(item);const clone=item.cloneNode(true);item.replaceWith(clone);const stable=p.lastAssistantId()===id&&p.itemKey(clone)===sourceKey;
   p.setInputLock(true);const ed=p.getEditor(),locked=ed.readOnly;const replacement=ed.cloneNode(true);replacement.readOnly=false;ed.replaceWith(replacement);p.enforceComposer();const remountLocked=replacement.readOnly;p.setInputLock(false);const unlocked=!replacement.readOnly;
   return {before,hidden,error,stable,locked,remountLocked,unlocked,vision:p.supportsVision};
  });
  assert.strictEqual(result.hidden,result.before,id+' hidden source survives chip decoration');assert.strictEqual(result.error,'',id+' quoted alert is not site error');assert(result.stable,id+' stable turn key survives remount');assert(result.locked&&result.remountLocked&&result.unlocked,id+' composer lock survives remount and unlocks');
  if(id==='vani'){
   assert.strictEqual(result.vision,false,'Vani guest is text only');
   await p.evaluate(()=>{const other=document.createElement('textarea');other.placeholder='Search settings';document.body.append(other);});assert.strictEqual(await p.evaluate(()=>ZSProvider.getEditor().id),'public-composer','Vani prefers observed composer over unrelated text fields');
  }
  await p.evaluate(()=>{const foreign=document.createElement('button');foreign.setAttribute('aria-label','Send message');document.body.append(foreign);const frame=ZSProvider.composerFrame();frame.querySelectorAll('button').forEach(e=>e.remove());});
  assert.strictEqual(await p.evaluate(()=>ZSProvider.selfTest().send),false,id+' no global submit fallback');
  console.log('PASS '+id+': hidden source/chip isolation, quoted alerts, stable IDs, React remount lock, scoped send'+(id==='vani'?', guest vision and preferred composer':''));await p.close();
 }
 const p=await browser.newPage();await p.route('**/*',r=>r.fulfill({body:'<form><textarea placeholder="Marketing contact"></textarea><button type="submit">Send</button></form>',contentType:'text/html'}));await p.goto('https://c.vani.ai/settings');for(const f of ['dom-chat','vani'])await p.addScriptTag({path:path.join(__dirname,'../extension/providers',f+'.js')});assert.strictEqual(await p.evaluate(()=>ZSProvider.selfTest().ready),false,'Vani non-chat routes fail closed');
 console.log('PASS shared transport boundary matrix.');
}finally{await browser.close();}})().catch(e=>{console.error(e.stack);process.exit(1)});
