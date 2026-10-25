// Actual authenticated local service + actual Blender + shipped Three.js bundle.
// No intercepted page, mocked bpy, substituted glTF or fake render is used.
const assert=require('assert'),path=require('path'),cp=require('child_process'),fs=require('fs'),pw=require('./playwright-env');
(async()=>{const child=cp.spawn(process.env.MS_TEST_PYTHON||'python',['-u',path.join(__dirname,'blender_workspace_server.py')],{cwd:path.resolve(__dirname,'..'),env:{...process.env,PYTHONIOENCODING:'utf-8'},stdio:['pipe','pipe','pipe']});
let buffer='',stderr='',seq=0,readyResolve,readyReject;const pending=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
child.stderr.on('data',x=>stderr+=x);child.on('exit',code=>{if(code)readyReject(Error(stderr||'Blender test server exited '+code));for(const x of pending.values())x.reject(Error('Server exited. '+stderr));});
child.stdout.on('data',chunk=>{buffer+=chunk;let at;while((at=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,at).trim();buffer=buffer.slice(at+1);if(line.startsWith('MS_WORKSPACE_READY:'))readyResolve(JSON.parse(line.slice(19)));else if(line.startsWith('MS_WORKSPACE_REPLY:')){const r=JSON.parse(line.slice(19)),p=pending.get(r.id);if(p){pending.delete(r.id);r.ok?p.resolve(r.value):p.reject(Error(r.error));}}}});
const rpc=action=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});child.stdin.write(JSON.stringify({id,action})+'\n');});
let browser;try{
 const timeout=setTimeout(()=>readyReject(Error('Real Blender test service did not start. '+stderr)),120000);const info=await ready;clearTimeout(timeout);
 browser=await pw.launch();assert(browser);const page=await browser.newPage({viewport:{width:1440,height:950}}),errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 // Provider sessions are deterministic extension fixtures. Blender, HTTP,
 // glTF, inspector, animation, renders and exports remain actual native data.
 await page.addInitScript({content:`window.sessionCalls=[];window.rejectFollowup=false;window.chrome={runtime:{sendMessage:(m,cb)=>{sessionCalls.push(m);setTimeout(()=>cb(m.action==='list'?{ok:true,sourceTabId:7,bridge:{connected:true,engines:[{id:'godot',alive:true,enabled:true,connected:true}]},participants:[{ok:true,tabId:7,title:'Model a walnut table',host:'gemini.google.com',name:'Gemini',context:'current-context',started:true,running:true,bridge:true,engines:['blender','godot'],blenderToolsAvailable:true,blenderWorkspaceProject:${JSON.stringify(info.project)},mode:'Engine session',progress:{steps:[{title:'Inspect the scene',status:'done'},{title:'Model the tabletop and legs',status:'working'},{title:'Render and verify proportions',status:'pending'}]}}]}:m.action==='followup'?rejectFollowup?{ok:false,error:'Target chat changed. Refresh sessions.'}:{ok:true,queued:true}:{ok:true}),40)}}};`+fs.readFileSync(path.resolve('extension/workspace-link.js'),'utf8')});
 await page.goto(info.url);await page.waitForFunction(()=>document.querySelector('#status-dot').classList.contains('ready'),null,{timeout:30000});
 await page.waitForFunction(()=>window.MSBlenderPreview?.ready,null,{timeout:30000});assert.strictEqual(await page.title(),'Blender Workspace · Multi-Script');assert.strictEqual(await page.locator('#welcome').isVisible(),false);
 await page.waitForFunction(()=>document.querySelector('#pipeline-runtime').textContent.includes('connected · verified'));
 await page.waitForFunction(()=>document.querySelector('#pipeline-ai').textContent==='AI session working · Blender available');
 await page.check('[data-companion="godot"]');await page.waitForFunction(()=>document.querySelector('#pipeline-setup-note').textContent.startsWith('Saved.'));assert((await rpc('status')).companion.engines.includes('godot'));
 const slow=rpc('slow');await page.waitForFunction(()=>document.querySelector('#pipeline-runtime').textContent==='Blender is working',null,{timeout:5000});await slow;await page.waitForFunction(()=>document.querySelector('#pipeline-runtime').textContent.includes('connected · verified'));
 await page.click('#add');await page.waitForFunction(()=>window.MSBlenderPreview?.meshes===1);await page.click('.object-row[data-name="Cube"]');assert.strictEqual(await page.locator('#selection').textContent(),'Cube');assert(await page.locator('#inspector .lil-root').isVisible());
 // Actual lil-gui field edit must roundtrip into Blender and the exported scene.
 const xInput=page.locator('#inspector input[type="text"]').first();await xInput.fill('2.5');await xInput.press('Enter');await xInput.blur();await page.waitForTimeout(600);let scene=await rpc('snapshot');assert(Math.abs(scene.objects.find(o=>o.name==='Cube').location[0]-2.5)<.001,JSON.stringify(scene));
 await rpc('animate');await page.waitForFunction(()=>window.MSBlenderPreview?.clips?.some(c=>c.duration>1),null,{timeout:15000});
 await page.click('#play');await page.waitForTimeout(500);assert((await page.locator('#frame-label').textContent())!=='Frame 1','Real exported animation advances in Three.js');await page.click('#play');
 await page.locator('#timeline').fill('15');await page.locator('#timeline').dispatchEvent('input');await page.locator('#timeline').dispatchEvent('change');await page.waitForTimeout(400);scene=await rpc('snapshot');assert.strictEqual(scene.frames.current,15,'Timeline scrub sets the real Blender frame');
 assert.strictEqual(await page.getByRole('button',{name:'Render',exact:true}).count(),0,'Workspace has no Render button');
 assert.strictEqual(await page.locator('#render, #render-dialog').count(),0);
 const rendered=await rpc('render');assert.strictEqual(rendered.signature,'89504e470d0a1a0a');assert.strictEqual(rendered.width,768);assert(rendered.bytes>1000,'Native AI render path still produces a real PNG');
 const download=page.waitForEvent('download');await page.click('[data-export="glb"]');const file=await download;assert.strictEqual(file.suggestedFilename(),'export.glb');
 await page.waitForFunction(()=>document.querySelector('#assistant-status').textContent==='AI is working');
 await page.click('#assistant-toggle');assert(await page.locator('#assistant-body').isVisible());
 await page.waitForFunction(()=>document.querySelector('#assistant-session').value==='7');assert.strictEqual(await page.locator('#assistant-plan li').count(),3);
 await page.locator('#assistant-text').fill('Keep the table legs square.');await page.click('#assistant-queue');await page.waitForFunction(()=>document.querySelector('#assistant-notice').textContent.startsWith('Queued'));
 assert.strictEqual(await page.evaluate(()=>sessionCalls.filter(m=>m.action==='followup').length),1,'One acknowledged follow-up, no duplicate dispatch');
 const forwarded=await page.evaluate(()=>sessionCalls.find(m=>m.action==='followup'));assert.strictEqual(forwarded.context,'current-context');assert(forwarded.requestId.length>=8);
 await page.evaluate(()=>rejectFollowup=true);await page.locator('#assistant-text').fill('Preserve this request if the chat changed.');await page.click('#assistant-queue');await page.waitForFunction(()=>document.querySelector('#assistant-notice').textContent.includes('Target chat changed'));assert.strictEqual(await page.locator('#assistant-text').inputValue(),'Preserve this request if the chat changed.');
 await page.click('#assistant-settings');await page.waitForFunction(()=>sessionCalls.some(m=>m.action==='settings'));await page.click('#assistant-stop');await page.waitForFunction(()=>sessionCalls.some(m=>m.action==='stop'));await page.waitForFunction(()=>!document.querySelector('#assistant-chat').disabled);
 await page.click('#assistant-toggle');
 for(const engine of ['unity','godot']){
  await page.selectOption('#handoff-engine',engine);await page.fill('#handoff-folder',info[engine]);await page.fill('#handoff-name','BrowserAsset');await page.click('#handoff-send');await page.waitForFunction(()=>document.querySelector('#handoff-note').textContent.startsWith('File copied and verified'));
  assert(fs.existsSync(path.join(info[engine],engine==='unity'?'Assets/MultiScript/Blender/BrowserAsset.fbx':'assets/multiscript/blender/BrowserAsset.glb')));
 }
 await page.selectOption('#handoff-engine','roblox');await page.click('#handoff-send');await page.waitForFunction(()=>document.querySelector('#handoff-note').textContent.startsWith('GLB ready'));
 const handoffDownload=page.waitForEvent('download');await page.click('#handoff-download');const handoffFile=await handoffDownload;assert.strictEqual(handoffFile.suggestedFilename(),'BrowserAsset.glb');
 await page.click('#assistant-toggle');
 const folder=path.resolve('test-results/blender-workspace-real');fs.mkdirSync(folder,{recursive:true});await page.screenshot({path:path.join(folder,'desktop.png')});
 await page.click('#assistant-toggle');await page.setViewportSize({width:390,height:844});await page.waitForTimeout(250);await page.screenshot({path:path.join(folder,'phone.png')});
 const layout=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,canvas:document.querySelector('canvas').getBoundingClientRect().width,status:document.querySelector('#status').textContent}));assert(layout.scroll<=layout.width+1,JSON.stringify(layout));assert(layout.canvas>150);
 await page.reload();await page.waitForFunction(()=>window.MSBlenderPreview?.meshes===1);assert(await page.locator('#backend').textContent().then(t=>t.includes('Blender 4.5.15')));
 await page.click('#stop');await page.waitForSelector('#resume:not([hidden])');await page.reload();await page.waitForFunction(()=>window.MSBlenderPreview?.meshes===1);assert.strictEqual(await page.locator('#welcome').isVisible(),false,'Saved preview stays visible with Blender stopped');
 assert((await page.locator('#revision').textContent()).includes('Blender stopped'));await page.click('#resume');await page.waitForFunction(()=>document.querySelector('#pipeline-runtime').textContent.includes('connected · verified'),null,{timeout:30000});assert.strictEqual((await rpc('snapshot')).objects.filter(o=>o.type==='MESH').length,1);
 await rpc('procedural');await page.waitForFunction(()=>window.MSBlenderPreview?.texturedMeshes===1,null,{timeout:30000});await page.waitForTimeout(250);
 const textureShot=path.join(folder,'procedural-color.png');await page.locator('#viewport canvas').screenshot({path:textureShot});
 const pixels=cp.spawnSync(process.env.MS_TEST_PYTHON||'python',['-c',"from PIL import Image; import sys; im=Image.open(sys.argv[1]).convert('RGB'); n=sum(r>g*1.15 and g>b*1.1 and g>20 for r,g,b in im.getdata()); assert n>100,n; print('Actual brown viewport pixels:',n)",textureShot],{encoding:'utf8'});assert.strictEqual(pixels.status,0,pixels.stdout+pixels.stderr);assert.deepStrictEqual(errors,[]);
 // Reproduce the old texture-blocking policy against the real exported GLB.
 // The viewer must report missing textures rather than silently show white.
 const documentUrl=info.url.split('#')[0];await page.route(documentUrl,async route=>{const response=await route.fetch();const headers=response.headers();headers['content-security-policy']=headers['content-security-policy'].replace("connect-src 'self' blob:","connect-src 'self'");await route.fulfill({response,headers});});
 await page.reload();await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('A model texture could not load'),null,{timeout:15000});assert.strictEqual((await rpc('snapshot')).objects.filter(o=>o.type==='MESH').length,1);
 const expectedErrors=errors.splice(0);assert(expectedErrors.length>0&&expectedErrors.every(t=>/Content Security Policy|Fetch API|GLTFLoader.*texture/.test(t)),JSON.stringify(expectedErrors));
 await page.unroute(documentUrl);await page.reload();await page.waitForFunction(()=>window.MSBlenderPreview?.texturedMeshes===1,null,{timeout:15000});assert.deepStrictEqual(errors,[]);
 console.log('PASS real Blender browser: authenticated launch, WebGL scene, native primitive creation, lil-gui→bpy transform, animated GLB playback, real frame scrub, no Render button, retained native Cycles PNG, export download, desktop/phone layout cookie-authenticated reload and extension-linked Multi-Script session controls (provider sessions fixture).');
}finally{if(browser)await browser.close();child.stdin.end(JSON.stringify({action:'close'})+'\n');await new Promise(resolve=>{if(child.exitCode!==null)return resolve();const t=setTimeout(()=>{child.kill();resolve();},12000);child.once('exit',()=>{clearTimeout(t);resolve();});});}})().catch(e=>{console.error(e.stack);process.exit(1)});
