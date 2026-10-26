const assert=require('assert'),h=require('../tools/studio_harness');
(async()=>{
 const x=await h.open({bridge:'up',stateHook:true});assert(x);
 try{
  const p=x.page;await p.evaluate(()=>{window.vaultCalls=[];window.bbCalls=[];window.__msVaultAdmin=m=>{vaultCalls.push(m);if(m.op==='setup')return{ok:true,configured:true,available:true,vault:'C:/Multi-Script/Multi-Script Memory'};if(m.op==='import')return{ok:true,path:'Attachments/abc.zip',sourceName:'omni-gui.zip',bytes:94000000};return{ok:true,configured:false,available:false};};window.__msBlockbenchAdmin=m=>{bbCalls.push(m);return m.op==='prepare'?{ok:true,prepared:true,connected:true,renderPrepared:m.render,nativeTools:Array(21).fill({}),workspace:'C:/Models'}:{ok:true,prepared:false,connected:false};};});
  await p.click('#zs-switch');await p.click('[data-tab="engines"]');
  await p.waitForSelector('#ms-vault-connect');
  await p.locator('#ms-vault-connect').evaluate(e=>e.click());assert.strictEqual(await p.evaluate(()=>vaultCalls.filter(x=>x.op==='setup').length),0,'Untrusted synthetic clicks cannot select local filesystem roots');
  await p.click('#ms-vault-connect');await p.waitForFunction(()=>document.querySelector('#ms-vault-status').textContent.includes('Vault connected'));
  assert.strictEqual(await p.locator('#ms-vault-path').inputValue(),'C:/Multi-Script/Multi-Script Memory');
  await p.fill('#ms-vault-import-path','C:/Downloads/omni-gui.zip');await p.click('#ms-vault-import');await p.waitForFunction(()=>document.querySelector('#ms-vault-status').textContent.includes('omni-gui.zip'));
  assert.strictEqual(await p.evaluate(()=>vaultCalls.find(x=>x.op==='import').payload.path),'C:/Downloads/omni-gui.zip');
  await p.click('#ms-blockbench-prepare');await p.waitForFunction(()=>document.querySelector('#ms-blockbench-status').textContent.includes('21 native tools'));
  await p.click('#ms-blockbench-render');await p.waitForFunction(()=>document.querySelector('#ms-blockbench-status').textContent.includes('render worker prepared'));
  await p.evaluate(()=>window.__msVaultAdmin=()=>({ok:false,error:'Vault folder is read-only'}));await p.click('#ms-vault-connect');await p.waitForFunction(()=>document.querySelector('#ms-vault-status').textContent.includes('read-only'));assert(await p.locator('#ms-vault-connect').isEnabled());
  assert.deepStrictEqual(x.errors,[]);console.log('PASS real settings trusted clicks: root-vault setup/import, explicit headless/render preparation, actual status display, synthetic-click rejection and failure recovery.');
 }finally{await x.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
