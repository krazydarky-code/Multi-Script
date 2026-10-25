// Exercise real shipped controls, trusted clicks and storage availability.
const assert=require('assert'),fs=require('fs'),h=require('../tools/studio_harness');
(async()=>{
 for(const width of [390,1280]){
  const x=await h.open({width,height:844,storage:{msUpdateAvailableVersion:'99.0.0'},updateState:{ok:false,error:'Finish active chats before updating.'}});assert(x);
  try{
   const p=x.page;if(width<600)await p.addStyleTag({content:'.side{display:none}.main{width:100%;min-width:0}.composer{width:calc(100% - 16px)}.thread{width:100%}'});await p.waitForSelector('#ms-update-notice',{state:'visible'});
   const before=await p.locator('#zs-bar').boundingBox();const badge=await p.locator('#ms-update-notice').boundingBox();assert(badge.x>=0&&badge.x+badge.width<=width);assert(Math.abs(badge.y-before.y)<20);assert(await p.locator('#ms-update-notice').evaluate(el=>getComputedStyle(el).position)==='absolute');
   await p.click('#ms-update-notice');await p.waitForSelector('#ms-update-dialog');
   await p.evaluate(()=>document.getElementById('ms-update-overlay').remove());
   await p.waitForSelector('#ms-update-dialog');
   assert(await p.locator('#ms-update-dialog').getAttribute('aria-modal')==='true');
   assert((await p.locator('[data-version]').textContent()).includes('99.0.0'));
   await p.click('#ms-update-dialog [data-update]');await p.waitForFunction(()=>document.querySelector('#ms-update-dialog [data-message]')?.textContent.includes('Finish active chats'));
   assert(await p.locator('#ms-update-dialog [data-update]').isEnabled());
   await p.click('#ms-update-dialog [data-later]');assert(await p.locator('#ms-update-dialog').count()===0);
   await p.click('#zs-switch');await p.click('#zs-switch');assert(await p.locator('#ms-update-dialog').count()===0);
   await p.click('#ms-update-notice');await p.waitForSelector('#ms-update-dialog');
   await p.keyboard.press('Escape');assert(await p.locator('#ms-update-dialog').count()===0);
   await p.waitForFunction(()=>document.getElementById('ms-update-notice')===document.activeElement);
   await p.emulateMedia({reducedMotion:'reduce'});assert(await p.locator('#ms-update-notice svg').evaluate(el=>getComputedStyle(el).animationName)==='none');
   const after=await p.locator('#zs-bar').boundingBox();assert(Math.abs(before.width-after.width)<1);
   assert.deepStrictEqual(x.errors,[]);fs.mkdirSync('test-results/update-notice-650',{recursive:true});await p.click('#ms-update-notice');await p.waitForSelector('#ms-update-dialog');await p.waitForFunction(()=>{const e=document.getElementById('ms-update-dialog'),r=e?.getBoundingClientRect();return r&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));});await p.screenshot({path:`test-results/update-notice-650/${width}.png`});
  }finally{await x.close();}
 }
 for(const prefs of [{},{msUpdateAvailableVersion:'0.0.1'}]){
  const x=await h.open({storage:prefs});assert(x);try{assert(await x.page.locator('#ms-update-notice').isHidden());assert.deepStrictEqual(x.errors,[]);}finally{await x.close();}
 }
 console.log('PASS verified availability badge, no bar reflow, narrow/desktop dialog, guarded failure, Later/reopen, focus return, reduced motion and no old-version notice.');
})().catch(e=>{console.error(e);process.exitCode=1;});
