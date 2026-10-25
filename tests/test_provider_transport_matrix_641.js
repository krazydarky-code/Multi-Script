// Chromium fixtures exercise each adapter's actual input/send code, not a
// replacement transport. Model responses and UI event handlers are fixtures.
const fs=require('fs'),path=require('path'),assert=require('assert'),pw=require('./playwright-env');
const {entries,html}=require('./support/provider-fixtures');
(async()=>{const browser=await pw.launch();assert(browser);try{
 for(const [id,x] of Object.entries(entries)){
  const p=await browser.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.stack));
  await p.route('**/*',r=>r.fulfill({contentType:'text/html',body:html(id,'<p>Previous answer</p>')}));await p.goto(x.url);
  await p.evaluate(({userSource,reverse})=>{
   window.generic=(role,body)=>`<div data-message-author-role="${role}" data-message-id="sent-user">${body}</div>`;
   window.sent=[];const user=new Function('return ('+userSource+')')();const send=document.querySelector('#fixture-send,#composer-submit-button,#send-message-button');
   send.addEventListener('click',e=>{e.preventDefault();const ed=window.transport.getEditor();const text=ed.value??ed.innerText;sent.push(text);const el=document.createElement('div');el.innerHTML=user(text.replaceAll('&','&amp;').replaceAll('<','&lt;'));const turn=el.firstElementChild;if(reverse)document.querySelector('#fixture-turns').prepend(turn);else document.querySelector('#fixture-turns').append(turn);if('value'in ed)ed.value='';else ed.textContent='';ed.dispatchEvent(new InputEvent('input',{bubbles:true}));});
  },{userSource:x.user.toString(),reverse:!!x.reverse});
  if(['vani','venice','clickup'].includes(id))await p.addScriptTag({path:path.join(__dirname,'../extension/providers/dom-chat.js')});
  await p.addScriptTag({path:path.join(__dirname,'../extension/providers/'+id+'.js')});await p.evaluate(()=>{window.transport=ZSProvider;transport.init?.({diag(){}});});
  await p.evaluate(()=>transport.isBusyNow());await p.waitForTimeout(1650);
  const text='Build the game UI — editable source 🎮\nKeep "quotes", {braces}, <markup> & slashes \\ intact.\n'+('Spacing, style and actual verification.\n'.repeat(4)).trimEnd();
  await p.evaluate(async text=>{await transport.typeAndSend(text);},text);
  assert.deepStrictEqual(await p.evaluate(()=>sent),[text],id+' sends exact text once');
  assert.strictEqual((await p.evaluate(()=>transport.editorText())).trim(),'',id+' acknowledged empty composer');
  assert.strictEqual(await p.evaluate(()=>transport.userCount()),2,id+' sent user turn recognized');
  assert.deepStrictEqual(errors,[],id+' no exceptions');console.log('PASS '+id+': exact multiline Unicode send, one click, composer acknowledgement and new user role');await p.close();
 }
 console.log('PASS 15 real-adapter transport fixtures (60 assertions).');
}finally{await browser.close();}})().catch(e=>{console.error(e.stack);process.exit(1)});
