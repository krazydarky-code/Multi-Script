const pw = require('./playwright-env'); const fs=require('fs');
const NAME='Notion transcript-editable guard';
pw.guard(NAME);
(async()=>{
 const browser=await pw.launch();
 if(!browser)pw.skip(NAME,'no Chromium available');
 const page=await browser.newPage({viewport:{width:1100,height:820}});
 // A /chat thread: historical messages (incl. our long system prompt) are
 // contenteditable block-editor nodes. The real composer sits at the bottom.
 await page.route('https://www.notion.so/chat/abc',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));
 await page.goto('https://www.notion.so/chat/abc');
 await page.setContent(`<!doctype html><style>body{margin:0}#scroll{height:640px;overflow:auto}
 .row{display:flex;padding:8px 40px}.row.u{justify-content:flex-end}.row.a{justify-content:flex-start}
 .msg{width:600px;min-height:120px}
 #bar{position:fixed;left:150px;bottom:12px;width:760px;height:96px}#ed{width:700px;height:40px}</style>
 <div id="scroll">
  <div class="row u" data-agent-service-scroll-anchor="u1"><div class="msg" id="usr" role="textbox" contenteditable="false" data-content-editable-root="true"><div data-block-id="b0">[MS-SYS] CONTEXT: reply to your message, ask anything, ask notion ai, do anything with AI</div></div></div>
  <div class="row a" data-agent-service-scroll-anchor="a1"><div class="msg" id="asst" role="textbox" contenteditable="true" data-content-editable-root="true"><div data-block-id="b1">Ask anything: reply to your message here</div></div></div>
  <div class="row" data-agent-service-scroll-anchor="running-placeholder:x"></div>
 </div>
 <form id="bar" data-testid="agent-composer"><div id="ed" role="textbox" contenteditable="true" data-placeholder="PLACEHOLDER"></div><div role="button" aria-label="Send message" data-testid="agent-send-message-button" style="width:30px;height:30px"></div></form>`);
 const code=fs.readFileSync('extension/providers/notion.js','utf8')+'\nwindow.__P=ZSProvider;'; await page.addScriptTag({content:code});
 for (const ph of ['Ask Notion AI','Type something']) {
  await page.evaluate((ph)=>{document.getElementById('ed').setAttribute('data-placeholder',ph);},ph);
  const r=await page.evaluate(()=>{const P=window.__P;P.init();const e=P.getEditor();const f=P.composerFrame();const fr=f&&f.getBoundingClientRect();return{id:e&&e.id,frame:f&&f.id,top:fr&&fr.top,gen:P.isGenerating()}});
  if(r.id!=='ed'||r.frame!=='bar'||!(r.top>500)) throw new Error('wrong composer for ph='+ph+' '+JSON.stringify(r));
  if(!r.gen) throw new Error('running-placeholder did not register as generating');
 }
 // Adversarial: composer with NO placeholder/role evidence. Whatever resolves,
 // it must never be a transcript node.
 const adv=await page.evaluate(()=>{const ed=document.getElementById('ed');ed.removeAttribute('data-placeholder');ed.removeAttribute('role');const P=window.__P;P.resetLayoutCache&&P.resetLayoutCache();const e=P.getEditor();return e&&e.id});
 if(adv==='usr'||adv==='asst') throw new Error('transcript node adopted as composer: '+adv);
 await page.evaluate(()=>{const ed=document.getElementById('ed');ed.setAttribute('role','textbox');ed.setAttribute('data-placeholder','Ask Notion AI');});
 await page.evaluate(()=>document.querySelector('[data-agent-service-scroll-anchor^="running-placeholder"]').remove());
 await page.waitForTimeout(2000);
 const g=await page.evaluate(()=>window.__P.isGenerating());
 if(g) throw new Error('generating stuck without placeholder/stop');
 await page.evaluate(()=>{const b=document.createElement('div');b.setAttribute('role','button');b.setAttribute('data-testid','agent-stop-button');b.style.cssText='position:fixed;left:900px;bottom:30px;width:30px;height:30px';document.body.appendChild(b);});
 if(!(await page.evaluate(()=>window.__P.isGenerating()))) throw new Error('global stop testid not detected');
 console.log('PASS Notion composer never resolves to transcript editables; running/stop signals work'); await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
