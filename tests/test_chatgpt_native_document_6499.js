// Actual ProseMirror transactions, DOM decorations and native Chromium editing.
// This verifies the shipped adapter, not a live signed-in provider account.
const assert=require('assert'),fs=require('fs'),path=require('path'),pw=require('./playwright-env');
const bundle=process.env.MS_NATIVE_EDITOR_BUNDLE;
if(!bundle||!fs.existsSync(bundle))pw.skip('ChatGPT native document','Set MS_NATIVE_EDITOR_BUNDLE to the bundled tests/support/native-prosemirror.mjs fixture');
const root=path.resolve(__dirname,'..'),adapter=path.join(root,'extension/providers/chatgpt.js'),bridge=path.join(root,'extension/providers/chatgpt-cm.js');
const payload='Original user task ✓ 🎮\n\n  Keep indentation, `code`, tabs\tand blank lines.\nLiteral <img src=x onerror="window.__injected=true"> & <script>code</script>.\n\n\n'+Array.from({length:220},(_,i)=>i%7===0?'':'Line '+i+' '+('retained task details '.repeat(8))).join('\n')+'\nEND_TASK';
(async()=>{const browser=await pw.launch();assert(browser);try{
 for(const [exposeView,shadow] of [[true,false],[false,false],[true,true],[false,true]]){
  const p=await browser.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.setContent('<meta charset="utf-8"><style>.ProseMirror{white-space:pre-wrap;min-height:50px}</style><form><div id="mount"></div><button type="submit" data-testid="composer-send-button" aria-label="Send message">Send</button></form>');
  await p.addScriptTag({path:bundle});await p.evaluate(({exposeView,shadow})=>{window.nativeForm=document.querySelector('form');if(shadow){const host=document.createElement('div');document.body.append(host);const root=host.attachShadow({mode:'open'});root.innerHTML='<style>.ProseMirror{white-space:pre-wrap;min-height:50px}</style>';root.append(nativeForm);}createNativeComposer({exposeView,mount:nativeForm.querySelector('#mount')});},{exposeView,shadow});
  await p.addScriptTag({path:path.join(root,'extension/core/config.js')});await p.addScriptTag({path:adapter});
  await p.evaluate(()=>{
   window.sent=[];window.execCalls=0;const old=document.execCommand.bind(document);document.execCommand=(...args)=>{execCalls++;return old(...args);};
   nativeForm.onsubmit=e=>{e.preventDefault();sent.push({native:nativeText(),read:ZSProvider.editorText()});pm.dispatch(pm.state.tr.delete(0,pm.state.doc.content.size));};
  });
  const reproduction=await p.evaluate(async()=>{try{await ZSProvider.typeAndSend('Original task\n\nEND_TASK');}catch(e){return{message:e.message,clicks:sent.length,native:nativeText(),read:ZSProvider.editorText()};}});
  assert(reproduction.message.includes('did not retain')&&reproduction.clicks===0&&reproduction.read.includes('Native editor hint'),JSON.stringify(reproduction));
  console.log('REPRODUCED pre-bridge draft rejection with native inline decorations and line-by-line browser editing: '+JSON.stringify(reproduction));
  await p.addScriptTag({path:bridge});
  await p.evaluate(()=>{nativeTransactions=0;execCalls=0;ZSProvider.setInputLock(true);});
  assert(await p.evaluate(text=>ZSProvider.typeAndSend(text),payload));
  const result=await p.evaluate(()=>({sent,execCalls,nativeTransactions,text:ZSProvider.editorText(),locked:ZSProvider.getEditor().getAttribute('contenteditable'),request:ZSProvider.getEditor().hasAttribute('data-ms-composer-request')}));
  assert.deepStrictEqual(result.sent,[{native:payload,read:payload}]);assert.strictEqual(result.text,'');assert.strictEqual(result.locked,'false');assert.strictEqual(result.request,false);
  assert.strictEqual(await p.evaluate(()=>window.__injected),undefined,'Code/markup stays literal message text');
  if(exposeView){assert.strictEqual(result.execCalls,0);assert.strictEqual(result.nativeTransactions,2,'One native write plus the fixture clearing after Send');}
  else assert.strictEqual(result.execCalls,1,'Plain ProseMirror receives one native paragraph edit');
  assert(await p.evaluate(()=>ZSProvider.typeAndSend('Second task\n\n  Keep this too.')));assert.strictEqual(await p.evaluate(()=>sent.length),2);
  if(exposeView){
   await p.evaluate(()=>{rejectNative=true;});
   let failure=await p.evaluate(async()=>{try{await ZSProvider.typeAndSend('Do not submit a rejected transaction');}catch(e){return {state:e.sendState,text:ZSProvider.editorText(),clicks:sent.length};}});
   assert.deepStrictEqual(failure,{state:'not-sent',text:'',clicks:2});
   await p.evaluate(()=>{rejectNative=false;throwAfterNative=true;});
   failure=await p.evaluate(async()=>{const before=execCalls;try{await ZSProvider.typeAndSend('Preserve accepted draft after a plugin exception');}catch(e){return{state:e.sendState,text:nativeText(),clicks:sent.length,fallbackCalls:execCalls-before,request:ZSProvider.getEditor().hasAttribute('data-ms-composer-request')};}});
   assert.deepStrictEqual(failure,{state:'not-sent',text:'Preserve accepted draft after a plugin exception',clicks:2,fallbackCalls:0,request:false});
  }
  assert.deepStrictEqual(errors,[]);await p.close();console.log('PASS native document '+(exposeView?'single transaction':'browser fallback')+(shadow?' in shadow root':'')+': long task, decoration exclusion, Unicode, blank lines, lock restoration, subsequent send and no partial/replayed send.');
 }
 // The rollout can keep the old composer ID on a wrapper, not the textarea.
 const p=await browser.newPage();await p.setContent('<div id="mobile-composer-prompt"><textarea aria-label="Chat with ChatGPT"></textarea><button aria-label="Send message">Send</button></div>');await p.addScriptTag({path:adapter});
 assert.strictEqual(await p.evaluate(()=>ZSProvider.getEditor().tagName),'TEXTAREA');
 await p.evaluate(()=>{window.sent=[];document.querySelector('button').onclick=()=>{sent.push(ZSProvider.editorText());document.querySelector('textarea').value='';};});
 assert(await p.evaluate(()=>ZSProvider.typeAndSend('Wrapped current textarea\n\nOriginal task')));assert.deepStrictEqual(await p.evaluate(()=>sent),['Wrapped current textarea\n\nOriginal task']);
 await p.evaluate(()=>document.querySelector('textarea').readOnly=true);
 const blocked=await p.evaluate(async()=>{try{await ZSProvider.typeAndSend('Must not overwrite');}catch(e){return{state:e.sendState,text:ZSProvider.editorText(),clicks:sent.length};}});assert.deepStrictEqual(blocked,{state:'not-sent',text:'',clicks:1});
 await p.evaluate(()=>{const ed=ZSProvider.getEditor();ed.readOnly=false;ed.value='Keep the disabled draft';ed.disabled=true;ZSProvider.setInputLock(true);});
 const disabled=await p.evaluate(async()=>{try{await ZSProvider.typeAndSend('Must not bypass native disabled input');return{unexpected:true,text:ZSProvider.editorText(),clicks:sent.length};}catch(e){return{state:e.sendState,text:ZSProvider.editorText(),clicks:sent.length};}});assert.deepStrictEqual(disabled,{state:'not-sent',text:'Keep the disabled draft',clicks:1});await p.close();
 console.log('PASS non-editable composer wrapper selects the native textarea; native read-only gate preserves the draft.');
}finally{await browser.close();}})().catch(e=>{console.error(e.stack);process.exit(1)});
