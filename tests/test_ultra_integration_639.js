// SPDX-License-Identifier: GPL-3.0-or-later
const assert=require('assert'),fs=require('fs'),path=require('path');
const studio=require('../extension/core/studio-workflows');
const ui=require('../tools/studio_harness');
const root=path.resolve(__dirname,'..'),out=path.resolve(root,'../../../outputs');
const main=fs.readFileSync(path.join(root,'extension/core/main.js'),'utf8');
const noCritic={enabled:false,passes:3};
const task=studio.taskAddon('Fix a slow inventory menu and save rewards in Roblox','ultra',noCritic,{engines:['roblox']});
for(const name of ['interface','diagnosis','performance','data-and-authority'])assert(task.includes('Method: '+name),name);
assert(task.includes('Roblox context:')&&task.includes('relevant released games')&&!task.includes('CRITIC · PROMPT ADD-ON'));
assert(!task.includes('Method: motion')&&!task.includes('Method: world'),'Unrelated methods must not bloat the task');
assert(task.length<9000,'The adapted pack must stay bounded');
const maximum=studio.taskAddon('Build Roblox UI','maximum',noCritic);
assert(maximum.includes('MULTI-SCRIPT MAXIMUM · WORK METHOD'),'Maximum retains its own execution method');
assert(!maximum.includes('ULTRA · EXECUTION METHODS')&&!maximum.includes('ULTRA · SPECIALIST MANUALS'),'Demotion removes Ultra methods and manuals');
assert(!studio.taskAddon('Build UI','quick',{enabled:true}).includes('ULTRA · EXECUTION METHODS'));
const web=studio.ultraMethodsPrompt('Build a React website and fix its menu',{engines:['roblox']});
assert(!web.includes('Roblox context:'),'An unrelated connected Studio must not hijack a web task');
const code=studio.ultraMethodsPrompt('Fix this function',{engines:['workspace']});
assert(code.includes('Method: engineering')&&!code.includes('Roblox context:'));
const repeated=studio.ultraMethodsPrompt('menu '.repeat(200));
assert.strictEqual(repeated.match(/Method: interface/g).length,1);
const sourceName=JSON.parse(fs.readFileSync(path.join(root,'legal/upstream-gpl/SOURCE.json'),'utf8')).originName;
for(const forbidden of [sourceName.toLowerCase()+'_skills','bundled-ultra-','THINK=ultracode','###LUA###'])assert(!task.includes(forbidden),'Foreign transport leaked: '+forbidden);
assert(task.includes('No second handshake')&&task.includes('latest user setting is EFFORT=ultra'));
assert(main.includes('stop applying previous Ultra methods and research requirements'));
assert(fs.existsSync(path.join(root,'legal/upstream-gpl/LICENSE')));

(async()=>{
  fs.mkdirSync(out,{recursive:true});
  for(const theme of ['dark','light']){
    const x=await ui.open({bridge:'up',host:'installed',theme,width:1280,height:1000,storage:{msMenuPreferences:{theme:theme==='light'?'frost':'mono',barTheme:theme==='light'?'auto':'matrix',barDock:'window',barAlign:'center',barFit:'fit',motion:'full'}}});
    assert(x,'A real browser is required');
    try {
      const p=x.page;await p.click('#zs-switch');await p.click('[data-tab="agent"]');
      const slider=p.locator('#ms-effort-slider');await slider.focus();await slider.press('End');
      assert.strictEqual(await slider.inputValue(),'5');
      assert.strictEqual(await p.locator('html').getAttribute('data-ms-effort'),'ultra');
      assert(await p.locator('#ms-ultra-summary').isVisible());
      assert(await p.locator('#ms-effort-indicator').isVisible());
      assert.strictEqual(await p.locator('#ms-effort-label').textContent(),'Ultra');
      assert.strictEqual(await slider.evaluate(e=>getComputedStyle(e).accentColor),'rgb(180, 138, 255)');
      assert((await slider.evaluate(e=>getComputedStyle(e).backgroundImage)).includes(theme==='light'?'rgb(98, 48, 168)':'rgb(180, 138, 255)'), 'Custom range track must use the current Ultra palette for this surface');
      assert.strictEqual(await p.locator('.ms-effort-ticks [aria-current="true"]').textContent(),'Ultra');
      assert.strictEqual(await p.evaluate(()=>new Promise(r=>chrome.storage.local.get('msExecutionEffort',v=>r(v.msExecutionEffort)))),'ultra');
      assert.strictEqual(await p.locator('#ms-effort-label').evaluate(e=>getComputedStyle(e).animationName),'ms-ultra-shine');
      const panel=p.locator('.zs-effort-sec');await panel.scrollIntoViewIfNeeded();await p.locator('#ms-effort-label').click();
      await panel.screenshot({path:path.join(out,`Ultra-Agent-${theme}-6.41.0.png`)});
      await p.click('#zs-menu-x');
      const bar=p.locator('#zs-bar');const scene=await bar.getAttribute('data-ms-bar-theme');
      assert.strictEqual(scene,theme==='light'?'frost':'matrix','Ultra must preserve the selected bar scene');
      await bar.screenshot({path:path.join(out,`Ultra-chatbar-${theme}-6.41.0.png`)});
      // Portal the actual bar just as in-flow provider adapters do. Global effort
      // state must still style it, including the mirrored motion preference.
      const before=await bar.evaluate(e=>getComputedStyle(e).borderColor);
      await bar.evaluate(e=>document.body.append(e));
      assert.strictEqual(await bar.evaluate(e=>getComputedStyle(e).borderColor),before);
      await p.emulateMedia({reducedMotion:'reduce'});
      assert.strictEqual(await p.locator('#ms-effort-indicator').evaluate(e=>getComputedStyle(e).animationName),'none');
      await p.emulateMedia({reducedMotion:'no-preference',forcedColors:'active'});
      assert.strictEqual(await p.locator('#ms-effort-indicator').evaluate(e=>getComputedStyle(e).webkitTextFillColor),await p.locator('#ms-effort-indicator').evaluate(e=>getComputedStyle(e).color));
      await p.emulateMedia({forcedColors:'none'});
      await p.click('#zs-switch');await p.click('[data-tab="agent"]');
      await slider.focus();await slider.press('ArrowLeft');
      assert.strictEqual(await slider.inputValue(),'4');
      assert.strictEqual(await p.locator('html').getAttribute('data-ms-effort'),'maximum');
      assert(await p.locator('#ms-ultra-summary').isHidden());assert(await p.locator('#ms-effort-indicator').isVisible());
      assert.strictEqual(await p.locator('#ms-effort-label').evaluate(e=>getComputedStyle(e).animationName),'none');
      await slider.press('End');await p.click('#zs-menu-x');await p.click('#zs-switch');await p.click('[data-tab="agent"]');
      assert(await p.locator('#ms-ultra-summary').isVisible(),'Menu rebuild must preserve activation');
      await p.setViewportSize({width:390,height:844});
      const stages=p.locator('.ms-ultra-stages');await stages.scrollIntoViewIfNeeded();
      assert.strictEqual(await stages.evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),1);
      const bounds=await p.locator('#zs-menu').boundingBox();assert(bounds.width<=390&&bounds.x>=0,'Narrow menu must remain inside viewport');
      assert.deepStrictEqual(x.errors,[]);
      console.log('PASS',theme,'native keyboard Ultra activation/demotion, persistence, theme/portal, reduced motion, forced colors and narrow layout');
    } finally {await x.close();}
  }
  const x=await ui.open({bridge:'up',host:'installed',storage:{msExecutionEffort:'ultra',msMenuPreferences:{motion:'none'}}});assert(x);
  try {
    const p=x.page;assert.strictEqual(await p.locator('html').getAttribute('data-ms-effort'),'ultra');
    assert.strictEqual(await p.locator('#ms-effort-indicator').evaluate(e=>getComputedStyle(e).animationName),'none');
    await p.click('#zs-switch');await p.click('[data-tab="agent"]');assert.strictEqual(await p.locator('#ms-effort-slider').inputValue(),'5');
    const reset=p.locator('#ms-reset-agent-settings');
    if(!await reset.isVisible())await p.locator('.zs-menu-sec').filter({has:reset}).locator('.zs-sec-label').click();
    await reset.click();
    assert.strictEqual(await p.locator('html').getAttribute('data-ms-effort'),'adaptive');
    assert(await p.locator('#ms-effort-indicator').isVisible());assert(await p.locator('#ms-ultra-summary').isHidden());
    assert.deepStrictEqual(x.errors,[]);console.log('PASS persisted Ultra hydration, explicit no-motion and Agent reset');
  }finally{await x.close();}
  console.log('PASS bounded Multi-Script Ultra routing, scope, Critic independence, transport and attribution');
})().catch(e=>{console.error(e.stack);process.exit(1)});
