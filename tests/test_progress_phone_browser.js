// Real phone HTTP frontend -> broker -> worker coordinator -> actual content-script queue.
const assert=require('assert'),cp=require('child_process'),readline=require('readline'),path=require('path'),fs=require('fs'),h=require('../tools/studio_harness'),mobile=require('../extension/mobile-control');
const root=path.resolve(__dirname,'..'),out=process.env.MS_REMOTE_SCREENSHOTS||path.resolve(root,'../../../outputs/remote-6.49.9');fs.mkdirSync(out,{recursive:true});
function service(){const child=cp.spawn(process.env.MS_TEST_PYTHON||'python',['-u','-X','utf8','tests/mobile_remote_fixture.py'],{cwd:root,stdio:['pipe','pipe','pipe']});let id=0,errors='';const pending=new Map();child.stderr.on('data',x=>errors+=x);readline.createInterface({input:child.stdout}).on('line',line=>{const r=JSON.parse(line);pending.get(r.id)?.(r.result);pending.delete(r.id);});child.on('exit',()=>{for(const resolve of pending.values())resolve({ok:false,error:errors||'Remote fixture exited'});});return {child,rpc:(op,payload)=>new Promise(resolve=>{const key=++id;pending.set(key,resolve);child.stdin.write(JSON.stringify({id:key,op,payload})+'\n');})};}
(async()=>{
 const s=service(),x=await h.open({bridge:'up',stateHook:true,tools:[{name:'ms_list_skills',server:'zeroscript',inputSchema:{type:'object',properties:{}}}],width:1360,height:1000,storage:{msExecutionEffort:'ultra',msMenuPreferences:{theme:'cobalt',barTheme:'daybreak',barDock:'window',barFit:'fit'}}});assert(x);let timer,phone;
 try{
  const p=x.page;
  await p.exposeFunction('__msMobileAdmin',m=>s.rpc(m.op,m.payload));
  const dispatch=msg=>p.evaluate(msg=>new Promise(resolve=>{for(const f of window.__msListeners)f(msg,{},resolve);}),msg);
  await p.evaluate(()=>{const q=window.__qa;q.A.started=true;q.A.running=true;q.beginTaskProgress('Build the inventory and verify input');});
  let runId=await p.evaluate(()=>window.__qa.readTaskProgress().id);
  assert((await p.evaluate(()=>window.__qa.taskPromptAddon('Build an inventory'))).includes(runId),'Current task prompt carries current run ID');
  await p.evaluate(()=>{window.__qa.A.chatOnly=true;window.__qa.A.software=true;});
  // Start a new ledger after mode changes because its workspace context changed.
  await p.evaluate(()=>window.__qa.beginTaskProgress('Workspace task'));
  const workspaceId=await p.evaluate(()=>window.__qa.readTaskProgress().id);
  assert((await p.evaluate(id=>window.__qa.runTool({tool:'multiscript.ms_task_progress',arguments:{run_id:id,action:'plan',steps:[{id:'workspace',title:'Inspect the workspace'}]}}),workspaceId)).includes('"ok":true'),'Local reporting works in software mode even with no engine add-on');
  assert((await p.evaluate(()=>window.__qa.runTool({tool:'list_commands',arguments:{server:'multiscript'}}))).includes('ms_task_progress'),'Checklist schema is advertised as a Multi-Script tool in software mode');
  await p.evaluate(()=>{window.__qa.A.chatOnly=false;window.__qa.A.software=false;});
  await p.evaluate(()=>window.__qa.beginTaskProgress('Build the inventory and verify input'));
  runId=await p.evaluate(()=>window.__qa.readTaskProgress().id);
  assert((await p.evaluate(id=>window.__qa.runTool({tool:'ms_task_progress',arguments:{run_id:id,action:'read'}}),workspaceId)).startsWith('ERROR'),'A prior workspace cannot update the new task');
  async function tool(args){return p.evaluate(args=>window.__qa.runTool({tool:'ms_task_progress',arguments:args}),{run_id:runId,...args});}
  assert((await tool({action:'plan',steps:[{id:'inspect',title:'Inspect the current inventory'},{id:'build',title:'Integrate the revised panel'},{id:'verify',title:'Check phone layout and keyboard focus'}]})).includes('"ok":true'));
  assert((await tool({action:'update',step_id:'inspect',status:'done',evidence:'Read the real hierarchy and input handlers.'})).includes('"ok":true'));
  await tool({action:'update',step_id:'build',status:'working'});await tool({action:'update',step_id:'verify',status:'blocked',blocker:'Playtest not run yet.'});
  assert((await tool({action:'update',step_id:'verify',status:'done'})).startsWith('ERROR'));
  await p.click('#ms-task-chip');assert.strictEqual(await p.locator('.ms-progress-metrics strong').textContent(),'2');assert.strictEqual(await p.locator('[data-step-status=done]').count(),1);assert((await p.locator('#ms-progress-view').textContent()).includes('Estimate paused'));
  await p.locator('#ms-run-panel').screenshot({path:path.join(out,'Task-monitor-desktop.png')});
  await p.emulateMedia({reducedMotion:'reduce'});assert.strictEqual(await p.locator('#ms-task-chip svg').evaluate(e=>getComputedStyle(e).animationName),'none');await p.emulateMedia({reducedMotion:'no-preference'});
  await p.setViewportSize({width:390,height:844});const bounds=await p.locator('#ms-run-panel').boundingBox();assert(bounds.x>=0&&bounds.x+bounds.width<=390);await p.locator('#ms-run-panel').screenshot({path:path.join(out,'Task-monitor-mobile.png')});await p.setViewportSize({width:1360,height:1000});
  await p.click('#ms-phone-chip');await p.getByRole('button',{name:'Enable on this network'}).click();await p.waitForFunction(()=>document.querySelector('#ms-phone-url')?.value);
  const url=await p.inputValue('#ms-phone-url'),code=await p.locator('.ms-pair-code strong').textContent();assert(/^\d{8}$/.test(code));await p.locator('#ms-run-panel').screenshot({path:path.join(out,'Phone-pairing-desktop.png')});
  const pump=mobile.create({identity:async()=> 'fixture-browser',send:m=>s.rpc(m.op,m.payload),tabs:{list:async()=>({participants:[{tabId:7,title:'Inventory work',...await dispatch({type:'ms-cowork-probe'})}]}),action:msg=>dispatch({type:'ms-cowork-action',...msg})}});
  await pump.tick();await pump.tick();timer=setInterval(()=>void pump.tick(),500);
  phone=await x.browser.newPage({viewport:{width:390,height:844}});const errors=[];phone.on('pageerror',e=>errors.push(e.message));await phone.goto(url);await phone.fill('#pair-code',code);await phone.getByRole('button',{name:'Pair device',exact:true}).click();await phone.waitForSelector('#remote:not([hidden])');
  assert((await phone.locator('#progress').textContent()).includes('2 steps remaining'));assert.strictEqual(await phone.locator('#progress li[data-status=done]').count(),1);assert(!await phone.evaluate(()=>Boolean(window.chrome?.runtime?.id)),'Phone uses ordinary browser HTTP, no extension required');
  await tool({action:'plan',steps:[{id:'inspect',title:'Inspect the current inventory',estimate_seconds:30},{id:'build',title:'Integrate the revised panel',estimate_seconds:90},{id:'verify',title:'Check phone layout and keyboard focus',estimate_seconds:45}]});
  await tool({action:'update',step_id:'verify',status:'pending'});await phone.waitForFunction(()=>document.querySelector('#progress').textContent.includes('AI step estimates (rough range)'));
  await phone.screenshot({path:path.join(out,'Phone-remote-paired.png')});
  await phone.fill('#prompt','Keep the existing movement system.');await phone.getByRole('button',{name:'Queue request',exact:true}).click();await phone.waitForFunction(()=>document.querySelector('#receipts').textContent.includes('acknowledged'));
  assert.strictEqual(await p.evaluate(()=>window.__qa.ui.coworkProbe().queuePending),1);
  await phone.getByRole('button',{name:'Pause queue',exact:true}).click();await p.waitForFunction(()=>window.__qa.ui.coworkProbe().queuePaused);
  await phone.getByRole('button',{name:'Resume queue',exact:true}).click();await p.waitForFunction(()=>!window.__qa.ui.coworkProbe().queuePaused);
  await phone.getByRole('button',{name:'Stop run',exact:true}).click();await p.waitForFunction(()=>window.__qa.A.userStopped===true);assert.strictEqual(await p.evaluate(()=>window.__qa.readTaskProgress().steps.filter(s=>s.status==='done').length),1,'Stop never completes unfinished steps');
  await phone.waitForFunction(()=>document.querySelector('#session-note').textContent.startsWith('Stopped'));
  await p.getByRole('button',{name:'Refresh connection',exact:true}).click();await p.getByRole('button',{name:'Revoke',exact:true}).click();await phone.waitForSelector('#pair:not([hidden])');
  await p.getByRole('button',{name:'Turn off remote',exact:true}).click();assert(!(await s.rpc('status')).enabled);
  assert.deepStrictEqual(errors,[]);assert.deepStrictEqual(x.errors,[]);
  console.log('PASS real headless desktop/phone flow: explicit task checklist/evidence, dark/light independent themes, 390px and reduced motion; trusted-click LAN enable, one-time pairing, authenticated HTTP frontend, live progress, queued follow-up, pause/resume/Stop receipts and device revocation/disable.');
 }finally{clearInterval(timer);if(phone)await phone.close();await x.close();await s.rpc('disable');s.child.stdin.end();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
