// Real Chromium editing plus the shipped adapters/core. Site hydration and AI
// replies are fixtures; this does not certify signed-in provider accounts.
const assert=require('assert'),path=require('path'),pw=require('./playwright-env'),h=require('../tools/studio_harness');
const root=path.resolve(__dirname,'..');
(async()=>{const b=await pw.launch();assert(b);try{
 const p=await b.newPage();await p.route('**/*',r=>r.fulfill({contentType:'text/html',body:'<form><div id="prompt-textarea" contenteditable="true" class="ProseMirror" style="white-space:pre-wrap;min-height:50px"></div><button type="submit" data-testid="composer-send-button" aria-label="Send prompt">Send</button></form>'}));await p.goto('https://chatgpt.com/');await p.addScriptTag({path:path.join(root,'extension/providers/chatgpt.js')});
 await p.evaluate(()=>{
  window.sent=[];window.clicks=0;window.hydrate=true;window.alter=false;
  const ed=ZSProvider.getEditor(),button=document.querySelector('button');
  ed.addEventListener('input',()=>{
   if(!hydrate||!ed.textContent.endsWith('END_PAYLOAD'))return;
   hydrate=false;button.disabled=true;
   // Native browser editing inserts BRs; the provider can hydrate the same
   // document as paragraphs, including empty paragraph nodes without a BR.
   const draft=ed.innerText;
   setTimeout(()=>{ed.replaceChildren(...draft.replace(/\n$/,'').split('\n').map(line=>{const n=document.createElement('p');n.textContent=line;return n;}));if(alter)ed.lastChild.textContent='Changed draft';button.disabled=false;},20);
  });
  document.querySelector('form').onsubmit=e=>{e.preventDefault();clicks++;sent.push(ZSProvider.editorText());ed.replaceChildren();};
 });
 const text='Startup instructions ✓\n\n  Preserve indentation.\n\n\n{"command":"list_commands","params":{}}\nEND_PAYLOAD';
 assert(await p.evaluate(t=>ZSProvider.typeAndSend(t),text));assert.deepStrictEqual(await p.evaluate(()=>sent),[text]);assert.strictEqual(await p.evaluate(()=>clicks),1);
 assert(await p.evaluate(t=>ZSProvider.typeAndSend(t),text.replace(/\n/g,'\r\n')));assert.strictEqual(await p.evaluate(()=>sent[1]),text,'CRLF messages arrive as the complete equivalent inline draft');
 await p.evaluate(()=>{hydrate=true;alter=true;});const failure=await p.evaluate(async t=>{try{await ZSProvider.typeAndSend(t);}catch(e){return {error:e.message,state:e.sendState,clicks};}},text);assert(failure.error.includes('did not retain')&&failure.state==='not-sent'&&failure.clicks===2,JSON.stringify(failure));
 await p.evaluate(()=>{hydrate=false;const ed=ZSProvider.getEditor();ed.addEventListener('input',()=>{if(!ed.textContent.endsWith('END_PAYLOAD'))return;const original=ed.innerHTML;ed.append('hydrating');setTimeout(()=>{ed.innerHTML=original;const b=document.querySelector('button');b.dataset.testid='stop-button';b.setAttribute('aria-label','Stop generating');},30);});});
 const resumed=await p.evaluate(async t=>{try{await ZSProvider.typeAndSend(t);}catch(e){return {error:e.message,state:e.sendState,clicks};}},text);assert(resumed.error.includes('responding')&&resumed.state==='not-sent'&&resumed.clicks===2,JSON.stringify(resumed));
 await p.close();console.log('PASS ChatGPT hydrated rich paragraphs, consecutive blank lines, indentation, Unicode, CRLF, exact single Send and changed-draft rejection.');
}finally{await b.close();}
 const markup=`<meta charset="utf-8"><style>body{background:#222;color:white}main{margin:40px auto;width:700px}form{padding:20px}textarea{width:90%;height:90px}</style><main><h1>Tell Claude what to do next</h1><form data-ms-ai-composer><textarea placeholder="Type your request: I’ll search, answer, or build it for you."></textarea><button type="submit" aria-label="Send">Send</button></form></main><section data-ms-human-chat><textarea id="team" placeholder="Message team"></textarea></section>`;
 const x=await h.open({provider:'providers/clickup.js',url:'https://app.clickup.com/901/brain',html:markup,stateHook:true,bridge:'up',storage:{zsSetupSeen:true,msEnhanceSettings:{mode:'off'}}});assert(x);try{const p=x.page;
  assert(await p.evaluate(()=>!!ZSProvider.getEditor()));const key=await p.evaluate(()=>ZSProvider.conversationKey());
  await p.evaluate(()=>{document.querySelector('main h1').remove();document.querySelector('main textarea').removeAttribute('placeholder');});
  for(let i=0;i<4;i++){await p.waitForTimeout(300);assert(await p.locator('#zs-bar').isVisible());assert(await p.evaluate(()=>!!ZSProvider.getEditor()));assert.strictEqual(await p.evaluate(()=>ZSProvider.conversationKey()),key);}
  await p.evaluate(()=>{window.sends=[];document.querySelector('form').onsubmit=e=>{e.preventDefault();sends.push(ZSProvider.editorText());ZSProvider.getEditor().value='';};});
  assert(await p.evaluate(()=>ZSProvider.typeAndSend('Continue in the identified private AI composer')));assert.strictEqual(await p.inputValue('#team'),'');assert.strictEqual(await p.evaluate(()=>sends.length),1);
  await p.evaluate(()=>{window.saved=document.querySelector('main form');saved.remove();});await p.waitForTimeout(350);assert(await p.locator('#zs-bar').isVisible(),'Controls remain available during a real SPA composer gap');assert.strictEqual(await p.evaluate(()=>ZSProvider.getEditor()),null,'No fallback to team input');
  await p.evaluate(()=>{document.querySelector('main').innerHTML='<h3>Ask Brain</h3>';saved.querySelector('textarea').placeholder='Type your request: I’ll search, answer, or build it for you.';document.querySelector('main').append(saved);});await p.waitForTimeout(350);assert(await p.evaluate(()=>!!ZSProvider.getEditor()));
  await p.evaluate(()=>{history.pushState({},'', '/901/team');document.querySelector('main h3').remove();document.querySelector('main textarea').removeAttribute('placeholder');});assert.strictEqual(await p.evaluate(()=>ZSProvider.getEditor()),null,'Landing identity is not retained across routes');
  await p.evaluate(()=>{document.querySelector('main').setAttribute('data-ms-human-chat','');document.querySelector('main').insertAdjacentHTML('afterbegin','<h1>Tell Claude what to do next</h1>');document.querySelector('main textarea').placeholder='Type your request: I’ll search, answer, or build it for you.';});assert.strictEqual(await p.evaluate(()=>ZSProvider.getEditor()),null);assert.deepStrictEqual(x.errors,[]);
  console.log('PASS ClickUp stable AI landing identity through heading/placeholder hydration, persistent controls during composer gaps, H3 remount, route invalidation and human-channel exclusion.');
  await p.evaluate(()=>{history.pushState({},'', '/901/brain');document.querySelector('main').removeAttribute('data-ms-human-chat');document.querySelector('main').innerHTML='<h2>Tell Claude what to do next</h2><form data-ms-ai-composer><div class="ProseMirror" contenteditable="true"><p data-placeholder="Type your request: I’ll search, answer, or build it for you."><br></p></div><button type="submit" aria-label="Send">Send</button></form>';});
  assert.strictEqual(await p.evaluate(()=>ZSProvider.getEditor()?.className),'ProseMirror','Tiptap child-paragraph placeholders identify their real editor');
  await p.evaluate(()=>{ZSProvider.setInputLock(true);document.querySelector('main h2').remove();document.querySelector('main p').removeAttribute('data-placeholder');});assert(await p.evaluate(()=>!!ZSProvider.getEditor()),'Lock and placeholder removal preserve the identified contenteditable');
  await p.evaluate(()=>{ZSProvider.setInputLock(false);document.querySelector('main').setAttribute('data-ms-human-chat','');});assert.strictEqual(await p.evaluate(()=>ZSProvider.getEditor()),null,'A previously identified editor is revoked when it becomes a human surface');
  await p.evaluate(()=>{document.querySelector('main').removeAttribute('data-ms-human-chat');document.querySelector('main').dataset.testid='brain-chat';const empty=document.createElement('section');empty.dataset.testid='ai-chat';empty.textContent='Loading AI panel';document.body.append(empty);});assert.strictEqual(await p.evaluate(()=>ZSProvider.getEditor()?.className),'ProseMirror','A visible empty AI panel must not displace the live private composer');
 }finally{await x.close();}
})().catch(e=>{console.error(e.stack);process.exit(1);});
