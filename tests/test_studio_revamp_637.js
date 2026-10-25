const assert=require('assert'),fs=require('fs'),path=require('path');
const h=require('../tools/studio_harness'),studio=require('../extension/core/studio-workflows');
(async()=>{
  const prompt=studio.skillPrompt('Create animated lowpoly UI icons','ultra',[{name:'My skill',instructions:'Use cobalt accents and verify keyboard selection.'}]);
  assert(prompt.includes('UI / UX / GUI')&&prompt.includes('Animation and motion')&&prompt.includes('cobalt'));
  assert.throws(()=>studio.validateSkill({id:'bad',name:'x',instructions:'too short'}));
  assert(studio.criticPrompt({enabled:true,passes:2}).includes('2 review passes'));
  assert.strictEqual(studio.criticPrompt({enabled:false}),'');
  assert(studio.taskAddon('Build a fantasy game','ultra',{enabled:true}).includes('relevant released games'));
  let s=studio.newGame();studio.stepGame(s,.02,true);assert(s.vy<0);s.y=290;s.vy=200;studio.stepGame(s,.04,false);assert(s.over);
  const x=await h.open({bridge:'up',host:'installed',theme:'dark',width:1280,height:900,storage:{msMenuPreferences:{barDock:'window',barFit:'fit',barAlign:'center'}}});assert(x,'A real browser is required for this regression.');
  try {
    const p=x.page;await p.click('#zs-switch');await p.click('[data-tab="agent"]');
    const slider=p.locator('#ms-effort-slider');assert.strictEqual(await slider.getAttribute('max'),'5');
    await slider.evaluate(e=>{e.value='5';e.dispatchEvent(new Event('input',{bubbles:true}));});
    assert.strictEqual(await p.locator('#ms-effort-label').textContent(),'Ultra');
    assert.strictEqual(await p.evaluate(()=>new Promise(r=>chrome.storage.local.get('msExecutionEffort',v=>r(v.msExecutionEffort)))),'ultra');
    assert(await p.locator('.zs-effort-sec').isVisible());
    const critic=p.locator('#ms-critic-enabled');
    if(!await critic.isVisible())await p.locator('.zs-critic-sec .zs-sec-label').click();
    assert(await critic.isChecked(),'Critic review is an Agent setting');
    await critic.uncheck();assert.strictEqual(await p.evaluate(()=>new Promise(r=>chrome.storage.local.get('msCriticSettings',v=>r(v.msCriticSettings.enabled)))),false);
    await critic.check();await p.locator('#ms-critic-passes').selectOption('2');
    assert.strictEqual(await p.evaluate(()=>new Promise(r=>chrome.storage.local.get('msCriticSettings',v=>r(v.msCriticSettings.passes)))),2);
    const autonomy=p.locator('[data-autonomy="oneShot"]');if(!await autonomy.isVisible())await p.locator('.zs-menu-sec').filter({has:autonomy}).locator('.zs-sec-label').click();await autonomy.click();
    assert.strictEqual(await p.evaluate(()=>new Promise(r=>chrome.storage.local.get('zsAutonomyLevel',v=>r(v.zsAutonomyLevel)))),'oneShot');
    await p.click('#zs-menu-x');
    assert.strictEqual(await p.locator('#ms-studio,#ms-studio-menu,#ms-critic,#ms-effort-bar,#ms-autonomy-picker').count(),0,'No Studio popup, Critic action or redundant effort shortcut');
    const idea=await p.locator('#ms-new-idea').boundingBox();assert(idea.height>=26&&idea.width>=26&&idea.width<=36,'New idea is a compact accessible action');
    await p.click('#zs-switch');await p.click('[data-tab="look"]');
    for(const theme of ['aurora','lava','nebula','matrix','fnaf','scream','myers','slender','jason']) {
      await p.click(`[data-theme="${theme}"]`);await p.waitForTimeout(70);
      const bar=await p.evaluate(()=>{const r=document.querySelector('#zs-bar').getBoundingClientRect();return {count:document.querySelectorAll('#zs-bar > .ms-scene').length,theme:document.querySelector('#zs-bar > .ms-scene')?.dataset.scene,buttons:document.querySelector('#ms-new-idea').getBoundingClientRect().width,inViewport:r.top>=0&&r.bottom<=innerHeight};});
      assert.strictEqual(bar.count,1,theme+' has exactly one bar scene');assert.strictEqual(bar.theme,theme);assert(bar.buttons>=26&&bar.buttons<=36);
      assert(bar.inViewport,theme+' must preserve the fixed chatbar position inside the viewport');
    }
    await p.click('[data-motion="none"]');
    assert.strictEqual(await p.locator('#zs-bar > .ms-scene').getAttribute('data-motion'),'none');
    await p.click('[data-tab="flight"]');await p.locator('#ms-code-flight').scrollIntoViewIfNeeded();await p.locator('#ms-code-flight').click();await p.waitForTimeout(80);
    assert((await p.locator('#ms-flight-status').textContent()).includes('Thread'));
    assert.strictEqual(await p.locator('#zs-discord').getAttribute('href'),'https://discord.gg/5Q6vvNcpM6');
    assert.strictEqual(await p.locator('[href="https://ko-fi.com/multixscript"]').count(),2,'Donation remains available in the bar and settings');
    await p.click('[data-tab="software"]');assert(await p.locator('#ms-sw-enabled').isVisible());
    await p.click('[data-tab="workshop"]');assert(await p.locator('#ms-skill-create').isVisible());await p.locator('.ms-skill-import summary').click();assert(await p.locator('#ms-skill-install').isVisible());
    assert.deepStrictEqual(x.errors,[]);
    await p.click('[data-tab="agent"]');await slider.evaluate(e=>{e.value='5';e.dispatchEvent(new Event('input',{bubbles:true}));});
    await p.locator('.zs-effort-sec').scrollIntoViewIfNeeded();
    const out=path.resolve(__dirname,'../../../../outputs');fs.mkdirSync(out,{recursive:true});await p.screenshot({path:path.join(out,'Ultra-slider-and-live-chatbar.png')});
    await p.click('[data-tab="look"]');await p.click('[data-theme="matrix"]');await p.click('[data-motion="full"]');await p.click('#zs-menu-x');
    await p.screenshot({path:path.join(out,'Chatbar-6.41.0.png')});
    const barPNG=path.join(out,'Live-chatbar-Matrix.png');await p.locator('#zs-bar').screenshot({path:barPNG});
    const pixel=require('child_process').spawnSync('python',['-c','from PIL import Image;import sys;im=Image.open(sys.argv[1]).convert("RGB");print(len(im.getcolors(im.width*im.height) or []))',barPNG],{encoding:'utf8'});
    assert.strictEqual(pixel.status,0,pixel.stderr);assert(Number(pixel.stdout)>100,'Live chatbar screenshot must contain painted controls and scene, not a blank surface');
    console.log('PASS 6.37 real-browser Ultra slider persistence, nine live bar scenes, reduced motion, Critic Agent setting persistence, direct New idea action, minigame, workshop/software tabs, donations and Discord.');
  } finally {await x.close();}
})().catch(e=>{console.error(e.stack);process.exit(1)});
