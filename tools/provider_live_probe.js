// Explicit read-only live smoke probe. Fresh unauthenticated contexts, no
// sending, picker actions, account access, CAPTCHA handling or tool execution.
// Composer detection is not an end-to-end compatibility certification.
const fs=require('fs'),path=require('path'),pw=require('../tests/playwright-env');
const sites={deepseek:'https://chat.deepseek.com/',chatgpt:'https://chatgpt.com/',claude:'https://claude.ai/',gemini:'https://gemini.google.com/app',kimi:'https://www.kimi.com/',glm:'https://chat.z.ai/',meta:'https://www.meta.ai/',qwen:'https://chat.qwen.ai/',arena:'https://arena.ai/',notion:'https://app.notion.com/chat',promptql:'https://prompt.ql.app/',superapp:'https://superapp.chat/',vani:'https://c.vani.ai/chat',venice:'https://venice.ai/chat/agent',clickup:'https://app.clickup.com/'};
(async()=>{const browser=await pw.launch();if(!browser)throw Error('Headless browser unavailable');const results=[];
try{
 const pending=Object.entries(sites);
 async function worker(){while(pending.length){const [id,url]=pending.shift(),context=await browser.newContext(),page=await context.newPage();const record={id,requestedUrl:url,checkedAt:new Date().toISOString(),authenticated:false,sentMessages:0,executedTools:0};
  try{
   await page.goto(url,{waitUntil:'domcontentloaded',timeout:25000});await page.waitForTimeout(2500);record.finalUrl=page.url();record.title=await page.title();
   // DOM-inserted script tags obey page CSP, unlike Chrome content scripts.
   // Evaluate our read-only adapter probe through the test browser instead of
   // changing CSP or misreporting a script-tag block as an extension failure.
   const shared=['vani','venice','clickup'].includes(id)?fs.readFileSync(path.join(__dirname,'../extension/providers/dom-chat.js'),'utf8'):'';
   const adapter=fs.readFileSync(path.join(__dirname,'../extension/providers',id+'.js'),'utf8');
   const probe='(()=>{'+shared+'\n'+adapter+'\n;const p=ZSProvider;return {composerDetected:!!p.getEditor(),userTurns:p.userCount(),assistantTurns:p.assistantCount(),modeWarning:p.modeWarning?.()||""};})()';
   for(let attempt=0;attempt<6;attempt++){
    record.dom=await page.evaluate(probe);
    if(record.dom.composerDetected||/login|sign.?in|just a moment|request could not be satisfied/i.test(record.title+' '+record.finalUrl))break;
    await page.waitForTimeout(1000);
   }
   record.boundary=record.dom.composerDetected?'Guest composer detected; sending and authenticated/model behavior unverified.':'No usable guest composer detected; account, route, challenge or DOM verification needed.';
  }catch(e){record.error=String(e.message).split('\n')[0].slice(0,600);record.boundary='Navigation or adapter probe failed; live compatibility unverified.';record.finalUrl=page.url();}
  results.push(record);console.log(JSON.stringify(record));await context.close();
 }}
 await Promise.all([worker(),worker(),worker(),worker()]);
 const output=path.resolve(process.argv[2]||'test-results/live-providers.json');fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,JSON.stringify({version:JSON.parse(fs.readFileSync(path.join(__dirname,'../extension/manifest.json'))).version,kind:'read-only unauthenticated headless smoke probe',results:results.sort((a,b)=>a.id.localeCompare(b.id))},null,2)+'\n');
}finally{await browser.close();}})().catch(e=>{console.error(e.stack);process.exit(1)});
