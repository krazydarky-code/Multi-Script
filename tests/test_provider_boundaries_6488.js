// Browser fixtures exercise the shipped adapters. These are DOM/transport
// regressions, not certification of authenticated providers or their models.
const assert=require('assert'),path=require('path'),pw=require('./playwright-env');
const {entries,html}=require('./support/provider-fixtures');
const root=path.resolve(__dirname,'../extension');
async function open(browser,id){
  const p=await browser.newPage();
  await p.route('**/*',r=>r.fulfill({contentType:'text/html',body:html(id,'<p>Current final answer.</p>')}));
  await p.goto(entries[id].url);
  if(['vani','venice','clickup'].includes(id))await p.addScriptTag({path:path.join(root,'providers/dom-chat.js')});
  await p.addScriptTag({path:path.join(root,'providers',id+'.js')});
  await p.evaluate(()=>{
    window.clicks=0;window.stopClicks=0;window.ack=true;window.cancel=false;
    window.actualEditor=ZSProvider.getEditor();window.actualSend=ZSProvider.composerFrame().querySelector('button');
    actualSend.onclick=e=>{e.preventDefault();clicks++;if(ack){if('value'in actualEditor)actualEditor.value='';else actualEditor.textContent='';}};
    window.send=async(text,images,controls={})=>{try{await ZSProvider.typeAndSend(text,images,controls);return{ok:true};}catch(e){return{ok:false,error:e.message,state:e.sendState,retryable:e.retryable};}};
  });
  return p;
}
(async()=>{const b=await pw.launch();assert(b);try{
  for(const id of ['gemini','chatgpt','venice','vani','clickup']){
    const p=await open(b,id);
    if(id==='clickup')await p.evaluate(()=>{const privatePanel=document.querySelector('[data-testid="brain-chat"]'),aside=document.createElement('aside');aside.setAttribute('role','dialog');privatePanel.before(aside);aside.append(privatePanel);if(ZSProvider.getEditor()!==actualEditor)throw Error('Explicit private AI scope must work inside a native modal/sidebar');});
    const hidden=await p.evaluate(()=>{
      const assistant=ZSProvider.lastAssistant(),before=ZSProvider.readAssistant().reply;
      const ghost=assistant.cloneNode(true);ghost.setAttribute('aria-hidden','true');ghost.textContent='{"command":"never_run_alternate","params":{}}';assistant.after(ghost);
      const editor=actualEditor.cloneNode(true),portal=document.createElement('div');portal.inert=true;portal.append(editor);document.body.prepend(portal);
      const stop=document.createElement('button');stop.setAttribute('aria-label','Stop generating');stop.textContent='Stop it';portal.append(stop);
      const picked=ZSProvider.getEditor()===actualEditor,last=ZSProvider.lastAssistant()===assistant;
      const after=ZSProvider.readAssistant().reply,users=ZSProvider.userCount(),assistants=ZSProvider.assistantCount();
      ghost.remove();portal.remove();return{before,after,picked,last,users,assistants};
    });
    assert(hidden.picked&&hidden.last,id+' rejects inert composer and hidden alternate turn');
    assert.strictEqual(hidden.after,hidden.before);assert.strictEqual(hidden.assistants,1);assert.strictEqual(hidden.users,1);
    const identity=await p.evaluate(()=>{const key=ZSProvider.conversationKey(),thread=document.querySelector('#fixture-turns');thread.setAttribute('aria-hidden','true');const out={stable:ZSProvider.conversationKey()===key,fresh:ZSProvider.isFreshChat(),empty:ZSProvider.chatIsEmpty(),reply:ZSProvider.readAssistant().reply};thread.removeAttribute('aria-hidden');return out;});
    assert(identity.stable&&!identity.fresh&&!identity.empty&&identity.reply==='',id+' a modal-hidden transcript is not a new conversation or an executable reply');
    assert(await p.evaluate(()=>{const a=ZSProvider.lastAssistant(),text=ZSProvider.readAssistant().reply;a.style.display='contents';const retained=ZSProvider.lastAssistant()===a&&ZSProvider.readAssistant().reply===text;a.style.removeProperty('display');return retained;}),id+' visible display:contents turn wrappers retain their final reply');
    if(id==='chatgpt'){
      await p.evaluate(()=>{const unrelated=document.createElement('button');unrelated.type='button';unrelated.setAttribute('aria-label','Send feedback');unrelated.onclick=()=>{throw Error('Feedback is not the composer Send');};ZSProvider.composerFrame().prepend(unrelated);});
      const parsed=await p.evaluate(()=>{
        const a=ZSProvider.lastAssistant();
        const thinking=document.createElement('div');thinking.dataset.testid='reasoning-panel';thinking.innerHTML='<div class="markdown">{"command":"never_run_reasoning","params":{}}</div>';a.prepend(thinking);
        const hidden=document.createElement('div');hidden.hidden=true;hidden.innerHTML='<div class="markdown">{"command":"never_run_hidden","params":{}}</div>';a.append(hidden);
        return{read:ZSProvider.readAssistant().reply,classified:ZSProvider.classifyText(a,'.zs-chip')};
      });
      assert(!/never_run/.test(parsed.read+parsed.classified),'Neither ChatGPT parser path can execute reasoning or a hidden answer');
    }
    if(['vani','venice'].includes(id)){
      const old=await p.evaluate(()=>{
        const a=ZSProvider.lastAssistant(),clone=a.cloneNode(true);a.before(clone);
        const stop=document.createElement('button');stop.textContent='Stop it';stop.setAttribute('aria-label','Stop generating');clone.append(stop);
        const spinner=document.createElement('div');spinner.setAttribute('aria-busy','true');spinner.textContent='Old native tool';clone.append(spinner);
        const busy=ZSProvider.isGenerating();clone.remove();return busy;
      });assert.strictEqual(old,false,id+' historical Stop and busy tool card cannot keep current run busy');
    }
    if(id==='vani'){
      assert(await p.evaluate(()=>{const e=document.createElement('div');e.dataset.status='thinking';ZSProvider.lastAssistant().append(e);const busy=ZSProvider.isGenerating();e.remove();return busy;}),'Vani quiet thinking flag remains active without a Stop button');
    }
    // Source hidden by Multi-Script remains available; native hidden content does not.
    assert(await p.evaluate(()=>{const a=ZSProvider.lastAssistant();const source=[...a.querySelectorAll('.prose')].at(-1)||a.querySelector('message-content,.markdown,[data-turn-model] + div,p');source.classList.add('zs-tool-hide');source.style.display='none';return ZSProvider.readAssistant().reply.includes('Current final answer.');}),id+' chip camouflage preserves source');
    await p.evaluate(()=>ZSProvider.isGenerating());await p.waitForTimeout(1650);
    const nav=await p.evaluate(async()=>{
      const route=location.pathname;actualEditor.addEventListener('input',()=>history.pushState({},'',route+'/other-chat'),{once:true});
      const result=await send('Do not deliver across navigation');history.replaceState({},'',route);return{...result,clicks};
    });
    assert(!nav.ok&&nav.state==='not-sent'&&nav.retryable===false&&nav.clicks===0,id+' same composer reused by a different chat is never sent');
    const cancelled=await p.evaluate(()=>send('Cancelled before typing',undefined,{cancelled:()=>true}));assert(!cancelled.ok&&cancelled.state==='not-sent',id+' respects cancellation');
    assert((await p.evaluate(()=>send('Exact prompt — 🎮\nOne user send.'))).ok,id+' actual acknowledged text send');
    assert.strictEqual(await p.evaluate(()=>clicks),1,id+' one send click');
    if(['chatgpt','venice','vani','clickup'].includes(id)){
      await p.evaluate(()=>{ack=false;cancel=false;window.pending=send('Unconfirmed message',undefined,{cancelled:()=>cancel});});
      await p.waitForFunction(()=>clicks===2);
      const duplicate=await p.evaluate(()=>send('Must not overwrite pending send'));
      assert(!duplicate.ok&&duplicate.state==='not-sent'&&duplicate.retryable===false,id+' refuses concurrent send');
      await p.waitForTimeout(700);assert.strictEqual(await p.evaluate(()=>clicks),2,id+' no click polling');
      await p.evaluate(()=>cancel=true);const pending=await p.evaluate(()=>pending);
      assert(!pending.ok&&pending.state==='unconfirmed'&&pending.retryable===false,id+' uncertain delivery never permits automatic replay');
    }
    console.log('PASS '+id+': native hidden/inert isolation, source retention, navigation and cancellation boundaries, exact sending'+(id==='gemini'?'':', acknowledged single click and concurrent-send exclusion'));
    await p.close();
  }
  // ChatGPT's real attachment event path waits for readiness; it never clicks
  // repeatedly or silently substitutes text for an unaccepted attachment.
  const p=await open(b,'chatgpt');
  await p.evaluate(()=>{
    const input=document.createElement('input');input.type='file';input.dataset.testid='upload-photos-input';ZSProvider.composerFrame().append(input);
    input.onchange=()=>{const preview=document.createElement('div');preview.className='attachment-preview';ZSProvider.composerFrame().append(preview);actualSend.disabled=true;window.uploadStart=Date.now();setTimeout(()=>{actualSend.disabled=false;window.uploadDone=Date.now();},1200);};
    actualSend.onclick=e=>{e.preventDefault();clicks++;window.clickedAt=Date.now();actualEditor.textContent='';};
  });
  await p.evaluate(()=>ZSProvider.isGenerating());await p.waitForTimeout(1650);
  const upload=await p.evaluate(()=>send('Verify the capture',[{mimeType:'image/png',data:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII='}]));
  assert(upload.ok);assert(await p.evaluate(()=>clicks===1&&clickedAt>=uploadDone),'ChatGPT attachment readiness precedes exactly one acknowledged click');
  await p.close();console.log('PASS ChatGPT attachment readiness and single acknowledged delivery.');
}finally{await b.close();}})().catch(e=>{console.error(e.stack);process.exit(1)});
