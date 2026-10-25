// Shipped provider/core/CSS fixtures; no authenticated-site certification.
const assert=require('assert'),path=require('path'),h=require('../tools/studio_harness'),pw=require('./playwright-env');
const {entries,html}=require('./support/provider-fixtures');
(async()=>{
 const x=await h.open({provider:'providers/vani.js',url:entries.vani.url,html:html('vani'),stateHook:true,bridge:'up',storage:{zsSetupSeen:true,msEnhanceSettings:{mode:'off'}}});assert(x);
 try{
  const p=x.page;
  await p.evaluate(()=>{
   const form=ZSProvider.composerFrame(),search=document.createElement('button');search.type='button';search.id='search-mode';search.textContent='Search';search.setAttribute('aria-pressed','true');search.onclick=()=>search.setAttribute('aria-pressed',String(search.getAttribute('aria-pressed')!=='true'));form.prepend(search);
   const a=ZSProvider.lastAssistant();a.style.display='flex';a.style.width='650px';const avatar=document.createElement('span');avatar.id='avatar';avatar.style.width='32px';avatar.textContent='✹';a.prepend(avatar);a.children[1].style.flex='1';a.children[1].style.minWidth='0';
   const reply=ZSProvider.chipAnchor(a);reply.id='answer-body';reply.innerHTML='<p id="narration">I will inspect the model and verify its materials.</p><pre>{"command":"ms_blender_workspace","params":{"action":"snapshot"}}</pre>';
   __qa.A.started=true;__qa.decorate.toolBox(a,'ms_blender_workspace','done','Verified snapshot',true);
  });
  assert(await p.evaluate(async()=> (await ZSProvider.ensureComposerReady('startup')).ready));
  assert.strictEqual(await p.getAttribute('#search-mode','aria-pressed'),'false');
  await p.evaluate(()=>document.querySelector('#search-mode').setAttribute('aria-pressed','true'));
  await p.evaluate(()=>ZSProvider.ensureComposerReady('task'));
  assert.strictEqual(await p.getAttribute('#search-mode','aria-pressed'),'true','User task Search preference is preserved');
  assert.strictEqual(await p.locator('#answer-body > .zs-chip').count(),1,'Tool chip lives inside the reply column');
  assert((await p.locator('#answer-body').boundingBox()).width>500,'Narration is not squeezed by a chip flex sibling');
  assert(await p.locator('#narration').isVisible());
  assert((await p.evaluate(()=>ZSProvider.readAssistant().reply)).includes('"action":"snapshot"'),'Masking retains the parser source');
  const result=await p.evaluate(()=>{
   const user=document.createElement('div');user.dataset.messageAuthorRole='user';user.id='feedback';user.textContent='Output of ms_task_progress:\n{"ok":true,"run":{"id":"actual-run"}}';document.querySelector('#fixture-turns').append(user);
   __qa.decorate.classify(user,null);
   return {hidden:user.classList.contains('zs-hidden'),label:user.querySelector('.zs-chip-tx')?.textContent,source:ZSProvider.itemText(user),size:getComputedStyle(user).fontSize,chipSize:getComputedStyle(user.querySelector('.zs-chip')).fontSize};
  });
  assert(result.hidden&&result.label==='ms_task_progress · result',JSON.stringify(result));assert(result.source.includes('actual-run'));assert.strictEqual(result.size,'0px');assert.strictEqual(result.chipSize,'13px');
  await p.evaluate(()=>{
   document.documentElement.style.background='oklch(0.22 0 0)';document.body.style.background='transparent';const e=ZSProvider.getEditor();e.style.background='transparent';ZSProvider.composerFrame().style.background='transparent';__qa.ui.inputCover(true);
  });
  const cover=await p.locator('#zs-input-cover').evaluate(e=>({visible:!!e.getClientRects().length,bg:getComputedStyle(e).backgroundColor}));
  assert(cover.visible&&/^rgb\((\d+),/.test(cover.bg)&&Number(cover.bg.match(/\d+/)[0])<80,JSON.stringify(cover));
  await p.evaluate(()=>{
   __qa.ui.inputCover(false);__qa.A.started=false;ZSProvider.setInputLock(false);window.outbound=[];
   document.querySelector('#fixture-send').type='submit';ZSProvider.composerFrame().onsubmit=e=>{e.preventDefault();outbound.push(ZSProvider.editorText());ZSProvider.getEditor().value='';};
   ZSProvider.getEditor().addEventListener('input',e=>{const next=e.target.cloneNode();next.value=e.target.value;e.target.replaceWith(next);},{once:true});
  });
  assert(await p.evaluate(()=>ZSProvider.typeAndSend('A complete Vani prompt ✓\nPreserve this second line.')));assert.deepStrictEqual(await p.evaluate(()=>outbound),['A complete Vani prompt ✓\nPreserve this second line.']);
  assert.deepStrictEqual(x.errors,[]);
  console.log('PASS Vani startup Search opt-out, task Search preservation, reply-column chips, progress masking with intact parser source, modern dark-theme cover.');
 }finally{await x.close();}
 const b=await pw.launch();assert(b);
 try{
  const p=await b.newPage();await p.setContent(`<main><h1>Tell Claude what to do next</h1><form data-ms-ai-composer><div contenteditable="true" data-placeholder="Type your request: I’ll search, answer, or build it for you."></div><button type="submit" aria-label="Send">Send</button></form></main><section data-ms-human-chat><textarea placeholder="Message team"></textarea></section>`);
  for(const file of ['dom-chat','clickup'])await p.addScriptTag({path:path.join(__dirname,'../extension/providers',file+'.js')});
  assert(await p.evaluate(()=>!!ZSProvider.getEditor()));
  await p.evaluate(()=>{window.sent=[];document.querySelector('form').onsubmit=e=>{e.preventDefault();sent.push(ZSProvider.editorText());ZSProvider.getEditor().textContent='';};});
  assert(await p.evaluate(()=>ZSProvider.typeAndSend('A private Brain request')));assert.deepStrictEqual(await p.evaluate(()=>sent),['A private Brain request']);
  await p.evaluate(()=>document.querySelector('h1').textContent='Team channel');assert.strictEqual(await p.evaluate(()=>ZSProvider.getEditor()),null,'An arbitrary team page must never qualify');
  await p.evaluate(()=>{document.querySelector('h1').textContent='Tell Claude what to do next';document.querySelector('main').setAttribute('data-ms-human-chat','');});assert.strictEqual(await p.evaluate(()=>ZSProvider.getEditor()),null,'Distinctive placeholder cannot override a human-channel boundary');
  console.log('PASS current ClickUp Ask Brain landing fixture and private-only transport; human channels remain excluded.');
  const q=await b.newPage();await q.route('**/*',r=>r.fulfill({contentType:'text/html',body:`<form><textarea id="prompt-textarea"></textarea><button type="submit" data-testid="composer-send-button" aria-label="Send prompt">Send</button></form>`}));await q.goto('https://chatgpt.com/uc/test');await q.addScriptTag({path:path.join(__dirname,'../extension/providers/chatgpt.js')});
  await q.evaluate(()=>{
   window.sent=[];window.remount=true;document.querySelector('form').onsubmit=e=>{e.preventDefault();sent.push(ZSProvider.editorText());ZSProvider.getEditor().value='';};
   document.querySelector('textarea').oninput=e=>{if(!remount)return;remount=false;const next=e.target.cloneNode();next.value=e.target.value;e.target.replaceWith(next);};
  });
  const payload='Startup transport\n'+('Complete instruction with Unicode ✓ and spaces.\n'.repeat(160));
  assert(await q.evaluate(t=>ZSProvider.typeAndSend(t),payload));assert.deepStrictEqual(await q.evaluate(()=>sent),[payload]);
  const error=await q.evaluate(async()=>{document.querySelector('textarea').oninput=e=>{const next=e.target.cloneNode();next.value='A different draft';e.target.replaceWith(next);};try{await ZSProvider.typeAndSend('Do not send the wrong draft');}catch(e){return {message:e.message,state:e.sendState,count:sent.length};}});
  assert(error.message.includes('composer changed')&&error.state==='not-sent'&&error.count===1,JSON.stringify(error));
  console.log('PASS ChatGPT full multiline startup fidelity, modern Send control, same-form exact-draft editor remount and different-draft rejection.');
 }finally{await b.close();}
})().catch(e=>{console.error(e.stack);process.exit(1);});
