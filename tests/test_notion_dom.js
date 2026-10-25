const pw = require('./playwright-env'); const fs=require('fs'),path=require('path');
const NAME='Notion DOM adapter';
pw.guard(NAME);
(async()=>{
 const browser=await pw.launch();
 if(!browser)pw.skip(NAME,'no Chromium available');
 const page=await browser.newPage();
 await page.setContent(`<!doctype html><style>body{margin:0}main{height:900px}.page-editor,.agent{display:block;width:700px;height:100px}.agent{position:fixed;bottom:0;left:100px;height:300px}.composer{position:absolute;bottom:10px;width:600px;height:60px}</style>
 <main><div class="page-editor" contenteditable="true" role="textbox">ordinary page</div></main>
 <aside class="agent" data-testid="notion-agent-panel"><div data-testid="user-message" data-message-id="u1">hello</div><div data-testid="agent-message" data-message-id="a1"><p>hi there</p></div>
 <button id="model" aria-label="Model selector">Auto</button><form class="composer" data-testid="agent-composer"><div id="agent-editor" contenteditable="true" data-placeholder="Do anything with AI…"></div><button id="send" type="submit" aria-label="Send message">Send</button></form></aside>
 <script>document.getElementById('send').addEventListener('click',e=>{e.preventDefault();document.getElementById('agent-editor').textContent='';}); document.getElementById('model').addEventListener('click',()=>{if(document.getElementById('opus'))return;let b=document.createElement('button');b.id='opus';b.setAttribute('role','option');b.textContent='Claude Opus 5';b.onclick=()=>{model.textContent='Claude Opus 5';b.remove()};document.body.appendChild(b)});</script>`);
 const code=fs.readFileSync('extension/providers/notion.js','utf8')+'\nwindow.__P=ZSProvider;'; await page.addScriptTag({content:code});
 const base=await page.evaluate(()=>{const P=window.__P;P.init();return {editor:P.getEditor().id,users:P.userCount(),assistants:P.assistantCount(),reply:P.readAssistant().reply,self:P.selfTest()}});
 if(base.editor!=='agent-editor'||base.users!==1||base.assistants!==1||base.reply!=='hi there'||!base.self.ready) throw new Error(JSON.stringify(base));
 await page.evaluate(()=>window.__P.typeAndSend('tool feedback')); if(await page.$eval('#agent-editor',e=>e.textContent)!=='') throw new Error('send did not clear');
 await page.evaluate(()=>{const e=document.getElementById('agent-editor');window.__P.setInputLock(true);window.__P.setInputLock(false);if(e.getAttribute('contenteditable')!=='true'||e.style.pointerEvents!=='')throw new Error('lock damaged editor')});
 const keys=await page.evaluate(()=>{const P=window.__P,k1=P.conversationKey();document.querySelectorAll('[data-testid$="message"]').forEach(x=>x.remove());const k2=P.conversationKey(),k2b=P.conversationKey();const u=document.createElement('div');u.dataset.testid='user-message';u.dataset.role='user';u.textContent='new';document.querySelector('.agent').prepend(u);P.conversationKey();u.remove();const k3=P.conversationKey();return{k1,k2,k2b,k3}});
 if(keys.k1===keys.k2||keys.k2!==keys.k2b||keys.k2===keys.k3)throw new Error('Notion chat epoch failed '+JSON.stringify(keys));
 console.log('PASS Notion DOM selection, messages, send, lock, self-test, and new-chat identity'); await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
