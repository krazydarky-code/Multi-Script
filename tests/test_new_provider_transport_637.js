const fs=require('fs'),path=require('path'),assert=require('assert');const pw=require('./playwright-env');
(async()=>{const browser=await pw.launch();assert(browser,'A browser is required.');try{
  for(const id of ['vani','venice','clickup']){
    const p=await browser.newPage();let errors=[];p.on('pageerror',e=>errors.push(e.message));
    const open=id==='clickup'?'<section data-testid="brain-chat">':'<section>';
    const editor=id==='venice'?'<textarea name="prompt-textarea"></textarea>':'<textarea placeholder="Message AI"></textarea>';
    const send=id==='venice'?'Submit chat':'Send message';
    await p.setContent(open+'<main id="messages"><div data-testid="user-message">Test</div><div data-message-author-role="assistant">Existing response</div></main><form>'+editor+'<button type="submit" aria-label="'+send+'">Send</button></form></section>');
    // Use a real URL for the provider's route guard while keeping local fixture content.
    await p.route('https://fixture.test/**',r=>r.fulfill({body:open+'<main id="messages"><div data-testid="user-message">Test</div><div data-message-author-role="assistant">Existing response</div></main><form>'+editor+'<button type="submit" aria-label="'+send+'">Send</button></form></section>',contentType:'text/html'}));
    await p.goto('https://fixture.test/chat/classic');
    await p.addScriptTag({content:fs.readFileSync(path.join(__dirname,'../extension/providers/dom-chat.js'),'utf8')});await p.addScriptTag({content:fs.readFileSync(path.join(__dirname,'../extension/providers/'+id+'.js'),'utf8')});
    await p.evaluate(()=>{window.transport=ZSProvider;document.querySelector('[data-testid="user-message"]').dataset.messageAuthorRole='user';document.querySelector('form').addEventListener('submit',e=>{e.preventDefault();const t=document.querySelector('textarea');const u=document.createElement('div');u.dataset.testid='user-message';u.dataset.messageAuthorRole='user';u.textContent=t.value;document.querySelector('#messages').append(u);t.value='';const a=document.createElement('div');a.dataset.messageAuthorRole='assistant';a.textContent='{"command":"ms_cowork","params":{"action":"list"}}';document.querySelector('#messages').append(a);});transport.installSendHooks({isBlocked:()=>true,isStarted:()=>true,onBlockedAttempt(){throw Error('Internal send hit user block');}});});
    assert(await p.evaluate(()=>transport.selfTest().ready),id+' composer ready');assert.strictEqual(await p.evaluate(()=>transport.isGenerating()),false,id+' existing response is idle');
    assert(await p.evaluate(()=>transport.typeAndSend('Fixture command request')),id+' send acknowledged');
    assert.strictEqual(await p.evaluate(()=>transport.readAssistant().reply),' {"command":"ms_cowork","params":{"action":"list"}}'.trim());
    assert.strictEqual(await p.evaluate(()=>transport.userCount()),2);assert.deepStrictEqual(errors,[]);await p.close();
  }
  const p=await browser.newPage();await p.setContent('<form><textarea placeholder="Team chat"></textarea><button aria-label="Send message">Send</button></form>');
  for(const file of ['dom-chat','clickup'])await p.addScriptTag({content:fs.readFileSync(path.join(__dirname,'../extension/providers/'+file+'.js'),'utf8')});
  assert.strictEqual(await p.evaluate(()=>ZSProvider.selfTest().ready),false,'ClickUp human team chat must never be selected');
  console.log('PASS four provider transport fixtures: exact send, own-send hook isolation, role parsing, idle detection and ClickUp private-AI scope guard.');
}finally{await browser.close();}})().catch(e=>{console.error(e.stack);process.exit(1)});
