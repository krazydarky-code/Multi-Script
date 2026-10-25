const assert=require('assert'),path=require('path'),pw=require('./playwright-env');
(async()=>{const browser=await pw.launch();assert(browser);try{
 const p=await browser.newPage();await p.setContent('<div class="cm-content"></div><div id="prompt-textarea" contenteditable="true"></div>');
 await p.evaluate(()=>{const el=document.querySelector('.cm-content');const doc=text=>({length:text.length,toString:()=>text});window.doc=doc;el.cmTile={view:{state:{doc:doc('old command')}}};});
 await p.addScriptTag({path:path.resolve(__dirname,'../extension/providers/chatgpt-cm.js')});
 assert.strictEqual(await p.locator('.cm-content').getAttribute('data-zs-cm'),'old command');
 await p.evaluate(()=>{document.querySelector('.cm-content').cmTile.view.state.doc=doc('new command');document.dispatchEvent(new Event('zs-cm-sync'));});
 assert.strictEqual(await p.locator('.cm-content').getAttribute('data-zs-cm'),'new command','Same-length native code corrections cannot be cached as the old command');
 const changes=await p.evaluate(async()=>{let mutations=0;const ob=new MutationObserver(list=>mutations+=list.length);ob.observe(document.querySelector('.cm-content'),{attributes:true});for(let i=0;i<20;i++)document.dispatchEvent(new Event('zs-cm-sync'));await Promise.resolve();ob.disconnect();return mutations;});assert.strictEqual(changes,0,'Unchanged reads do not rewrite the DOM');
 await p.evaluate(()=>{delete document.querySelector('.cm-content').cmTile;document.dispatchEvent(new Event('zs-cm-sync'));});
 assert.strictEqual(await p.locator('.cm-content').getAttribute('data-zs-cm'),null,'A detached native view cannot leave executable stale code in the snapshot');
 await p.evaluate(()=>{const ed=document.querySelector('#prompt-textarea');ed.setAttribute('data-ms-composer-text','stale snapshot');ed.dispatchEvent(new Event('ms-chatgpt-composer-read',{bubbles:true}));});
 assert.strictEqual(await p.locator('#prompt-textarea').getAttribute('data-ms-composer-text'),null,'An unsupported/remounted editor cannot retain a native snapshot');
 console.log('PASS ChatGPT MAIN-world bridge: same-length code corrections, unchanged-read DOM stability and stale composer snapshot removal.');
}finally{await browser.close();}})().catch(e=>{console.error(e.stack);process.exit(1)});
