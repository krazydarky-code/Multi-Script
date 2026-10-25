const assert=require('assert'),fs=require('fs'),path=require('path'),h=require('../tools/studio_harness');
const out=path.resolve(__dirname,'../../../../outputs/effort-6.49.7');fs.mkdirSync(out,{recursive:true});
(async()=>{for(const theme of ['dark','light']){
 const x=await h.open({bridge:'up',theme,width:1280,height:1000,storage:{zsSetupSeen:true,msMenuPreferences:{theme:theme==='light'?'frost':'mono',barDock:'window',barFit:'full',motion:'full'}}});assert(x);
 try{const p=x.page;await p.click('#zs-switch');
  const donation=p.locator('#ms-donate');assert.strictEqual(await donation.getAttribute('href'),'https://ko-fi.com/multixscript');assert((await donation.getAttribute('rel')).includes('noopener'));assert(await donation.isVisible());
  await donation.screenshot({path:path.join(out,'donation-'+theme+'.png')});await p.click('[data-tab="agent"]');
  const range=p.locator('#ms-effort-slider');
  for(const [i,label] of ['Adaptive','Quick','Standard','Deep','Maximum','Ultra'].entries()){
   await range.evaluate((e,i)=>{e.value=i;e.dispatchEvent(new Event('input',{bubbles:true}));},i);
   assert.strictEqual(await p.locator('#ms-effort-indicator').textContent(),label);assert(await p.locator('#ms-effort-indicator').isVisible());assert.strictEqual(await range.getAttribute('aria-valuetext'),label);
   assert.strictEqual(await range.evaluate(e=>e.style.getPropertyValue('--ms-effort-fill')),i*20+'%');
  }
  await p.selectOption('#ms-ultra-palette','rainbow');await p.selectOption('#ms-ultra-animation','flow');
  assert.strictEqual(await p.locator('html').getAttribute('data-ms-ultra-palette'),'rainbow');const gradient=await p.locator('#ms-effort-indicator').evaluate(e=>getComputedStyle(e).backgroundImage);assert(theme==='light'?gradient.includes('182, 32, 76')&&gradient.includes('8, 126, 73'):gradient.includes('255, 119, 149')&&gradient.includes('112, 226, 175'),gradient);
  assert.strictEqual(await p.locator('#ms-effort-indicator').evaluate(e=>getComputedStyle(e).animationName),'ms-ultra-shine');
  const bounds=await p.locator('#ms-effort-indicator').evaluate(e=>({e:e.getBoundingClientRect().toJSON(),p:e.parentElement.getBoundingClientRect().toJSON()}));assert(bounds.e.left>=bounds.p.left&&bounds.e.right<=bounds.p.right+1,'Effort label must not be clipped out of its brand column');await p.locator('.zs-effort-sec').screenshot({path:path.join(out,'rainbow-'+theme+'.png')});await p.locator('#zs-bar').screenshot({path:path.join(out,'bar-'+theme+'.png')});
  await p.selectOption('#ms-ultra-animation','breathe');assert.strictEqual(await p.locator('#ms-effort-indicator').evaluate(e=>getComputedStyle(e).animationName),'ms-ultra-breathe');
  await p.selectOption('#ms-ultra-animation','still');assert.strictEqual(await p.locator('#ms-effort-indicator').evaluate(e=>getComputedStyle(e).animationName),'none');
  const saved=await p.evaluate(()=>new Promise(r=>chrome.storage.local.get('msMenuPreferences',x=>r(x.msMenuPreferences))));assert.strictEqual(saved.ultraPalette,'rainbow');assert.strictEqual(saved.ultraAnimation,'still');
  await p.selectOption('#ms-ultra-animation','flow');await p.emulateMedia({reducedMotion:'reduce'});assert.strictEqual(await p.locator('#ms-effort-indicator').evaluate(e=>getComputedStyle(e).animationName),'none');
  await p.emulateMedia({reducedMotion:'no-preference',forcedColors:'active'});assert.strictEqual(await p.locator('#ms-effort-indicator').evaluate(e=>getComputedStyle(e).webkitTextFillColor),await p.locator('#ms-effort-indicator').evaluate(e=>getComputedStyle(e).color));
  await p.emulateMedia({forcedColors:'none'});await range.focus();await range.press('Home');assert.strictEqual(await p.locator('#ms-effort-indicator').textContent(),'Adaptive');await range.press('ArrowRight');assert.strictEqual(await p.locator('#ms-effort-indicator').textContent(),'Quick');await range.press('End');assert.strictEqual(await range.inputValue(),'5');
  assert.deepStrictEqual(x.errors,[]);console.log('PASS '+theme+': six live chatbar effort labels, keyboard range/fill, Ko-fi destination, palettes/animation persistence, reduced motion and forced colors.');
 }finally{await x.close();}
}})().catch(e=>{console.error(e.stack);process.exit(1)});
