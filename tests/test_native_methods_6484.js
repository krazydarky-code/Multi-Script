// Complete shipped chains; reduced provider DOM, never signed-in certification.
const assert=require('assert'),fs=require('fs'),path=require('path'),h=require('../tools/studio_harness');
const {entries,html}=require('./support/provider-fixtures');
const levels=['adaptive','quick','standard','deep','maximum','ultra'];
(async()=>{
 for(const [id,x] of Object.entries(entries).filter(([id])=>!process.env.MS_TEST_PROVIDER||process.env.MS_TEST_PROVIDER===id)){
  const fixture=await h.open({html:html(id,'<p>Ready.</p>'),url:x.url,provider:'providers/'+id+'.js',stateHook:true,storage:{msEnhanceSettings:{mode:'off'},msCriticSettings:{enabled:false},msPacingSettings:{mode:'off'},msMethodReceipts:{legacy:{effort:'ultra',at:Date.now()}}}});assert(fixture);
  try{const p=fixture.page;
   await p.evaluate(({levels,userSource,assistantSource,reverse})=>{
    __qa.A.started=true;window.methodReceiptRequests=[];const send=chrome.runtime.sendMessage;
    chrome.runtime.sendMessage=(msg,cb)=>{if(msg.type==='ms_method_receipt'){methodReceiptRequests.push(msg);return;}return send(msg,cb);};
    window.generic=(role,body)=>`<div data-message-author-role="${role}" data-message-id="${role}-fixture">${body}</div>`;const user=new Function('return ('+userSource+')')(),assistant=new Function('return ('+assistantSource+')')(),host=document.querySelector('#fixture-turns');window.nativeMethods=[];window.nativeMarkup=node=>{const copy=node.cloneNode(true);copy.removeAttribute('data-zs-role-align');return copy.outerHTML;};
    for(const effort of levels){
     const prompt='Design a Roblox inventory GUI with motion. '+effort;
     const payload=prompt+'\n\n'+MSStudio.taskAddon(prompt,effort,{enabled:false},{engines:['workspace'],tools:[]});
     const wrap=document.createElement('div');wrap.innerHTML=user('');const node=wrap.firstElementChild;
     // Keep native action controls, literal markup and the original attachment.
     const content=node.querySelector('.prose,.fbb737a4')||node;const text=document.createElement('div');text.style.whiteSpace='pre-wrap';text.textContent=payload+'\nLiteral <img src=x onerror=alert(1)> stays text.';content.prepend(text);
     const image=document.createElement('img');image.src='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60"></svg>';image.alt='Original user attachment';content.append(image);
     const action=document.createElement('button');action.textContent='Copy original';action.onclick=()=>window.lastNativeCopy=payload;content.append(action);
     const reply=document.createElement('div');reply.innerHTML=assistant('<p>Fixture response.</p>');
     if(reverse){host.prepend(node);host.prepend(reply.firstElementChild);}else{host.append(node);host.append(reply.firstElementChild);}
     nativeMethods.push({node,payload,before:nativeMarkup(node),action,image});
    }
   },{levels,userSource:x.user.toString(),assistantSource:x.assistant.toString(),reverse:!!x.reverse});
   await p.waitForTimeout(650);
   for(const width of [1280,390]){
    await p.setViewportSize({width,height:900});await p.evaluate(()=>{__qa.decorate.sweep();document.querySelector('#fixture-turns').scrollTop=2000;});await p.waitForTimeout(100);
    const results=await p.evaluate(()=>nativeMethods.map(({node,payload,before,image})=>({unchanged:nativeMarkup(node)===before,diff:nativeMarkup(node)===before?null:{before,after:nativeMarkup(node)},visible:getComputedStyle(node).visibility,masked:!!node.closest('.zs-hidden,.ms-method-source'),image:node.contains(image),payload:node.textContent.includes(payload),roles:ZSProvider.allItems().some(item=>ZSProvider.isUserItem(item)&&(item===node||item.contains(node)||node.contains(item)))})));
    for(const result of results){if(!result.unchanged){const d=result.diff;let at=0;while(d.before[at]===d.after[at]&&at<d.before.length)at++;console.log(id+' diff',at,d.before.slice(Math.max(0,at-60),at+180),d.after.slice(Math.max(0,at-60),at+180));}assert(result.unchanged,id+' native message children/styles unchanged at '+width);assert.strictEqual(result.visible,'visible',id);assert(!result.masked&&result.image&&result.payload&&result.roles,id+' attachment, source and native roles retained');}
   }
   assert(await p.evaluate(()=>{const entry=nativeMethods.at(-1);entry.action.click();return lastNativeCopy===entry.payload;}),id+' original native controls still work');
   await p.evaluate(()=>{for(const entry of nativeMethods){const next=entry.node.cloneNode(true);entry.node.replaceWith(next);entry.node=next;entry.before=nativeMarkup(next);}__qa.decorate.sweep();});await p.waitForTimeout(200);
   assert(await p.evaluate(()=>nativeMethods.every(({node,before})=>nativeMarkup(node)===before)),id+' provider remount stays native');
   assert.strictEqual(await p.locator('.ms-method-display,.ms-method-chip,.ms-method-source').count(),0,id+' no method masks');
   assert.strictEqual(await p.evaluate(()=>methodReceiptRequests.length),0,id+' no cosmetic IPC');assert.deepStrictEqual(fixture.errors,[]);
   if(['chatgpt','gemini','claude'].includes(id)){const dir=path.join(__dirname,'../test-results/native-methods-6484');fs.mkdirSync(dir,{recursive:true});await p.screenshot({path:path.join(dir,id+'.png')});}
   console.log('PASS '+id+': six native effort methods, unchanged layout/attachments, desktop/phone and provider remount; old receipts inert.');
  }finally{await fixture.close();}
 }
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
