const pw = require('./playwright-env');
const fs = require('fs');
const NAME = 'Notion always-on injection';
pw.guard(NAME);
(async()=>{
  const manifest=JSON.parse(fs.readFileSync('extension/manifest.json','utf8'));
  const notion=manifest.content_scripts.find(x=>(x.js||[]).includes('providers/notion.js'));
  for(const pattern of ['https://notion.ai/*','https://www.notion.ai/*','https://notion.so/*','https://www.notion.so/*','https://notion.com/*','https://www.notion.com/*','https://app.notion.com/*']) {
    if(!notion.matches.includes(pattern)||!manifest.host_permissions.includes(pattern)) throw new Error('missing '+pattern);
  }
  if(!manifest.permissions.includes('scripting')||!manifest.permissions.includes('activeTab')) throw new Error('missing repair permissions');
  const browser=await pw.launch();
  if(!browser)pw.skip(NAME,'no Chromium available');
  const page=await browser.newPage();
  await page.setContent('<button id="open" aria-label="Open Notion AI">Ask AI</button><div id="shadow-host"></div>');
  await page.evaluate(()=>{
    document.getElementById('open').onclick=()=>{
      const sr=document.getElementById('shadow-host').attachShadow({mode:'open'});
      sr.innerHTML='<style>#ed{display:block;width:500px;height:50px}</style><form data-testid="ai-composer"><div id="ed" role="textbox" contenteditable="plaintext-only" aria-label="Message Notion AI"></div><button type="submit">Send</button></form>';
    };
  });
  const code=fs.readFileSync('extension/providers/notion.js','utf8')+'\nwindow.__P=ZSProvider;';
  await page.addScriptTag({content:code});
  const before=await page.evaluate(()=>window.__P.getEditor()); if(before) throw new Error('unexpected editor before open');
  const opened=await page.evaluate(()=>window.__P.openAIChat()); if(!opened) throw new Error('openAIChat did not attach');
  const found=await page.evaluate(()=>{const e=window.__P.getEditor();return {id:e&&e.id,self:window.__P.selfTest()}});
  if(found.id!=='ed'||!found.self.ready) throw new Error('shadow editor unavailable '+JSON.stringify(found));
  await browser.close();
  const main=fs.readFileSync('extension/core/main.js','utf8'), popup=fs.readFileSync('extension/popup.js','utf8');
  if(!main.includes('persistentBarWhenNoEditor')||!main.includes('zs-bar-detached')||!main.includes('open-provider')) throw new Error('missing persistent recovery UI');
  if(!popup.includes('chrome.scripting.executeScript')||!popup.includes('providers/notion.js')) throw new Error('missing popup reinjection recovery');
  console.log('PASS Notion always-on: app.notion.com + legacy domains, shadow editor, open-chat action, persistent bar and one-click reinjection');
})().catch(e=>{console.error(e);process.exit(1)});
