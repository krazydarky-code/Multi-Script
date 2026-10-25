const assert=require('assert'),fs=require('fs'),path=require('path'),h=require('../tools/studio_harness');
const out=path.resolve(__dirname,'../../../../outputs/compact-effort-6.49.8');fs.mkdirSync(out,{recursive:true});
(async()=>{for(const theme of ['dark','light']){
 const x=await h.open({bridge:'up',theme,width:1280,height:1000,storage:{zsSetupSeen:true,msMenuPreferences:{theme:theme==='light'?'frost':'mono',barDock:'window',barFit:'full',motion:'full'}}});assert(x);
 try{const p=x.page;await p.click('#zs-switch');await p.click('[data-tab="agent"]');const range=p.locator('#ms-effort-slider');
  // Chromium does not expose the native thumb through getComputedStyle's pseudo
  // argument. Sample the rendered thumb center instead of testing the input twice.
  const read=async()=>{await p.waitForTimeout(220);const png=(await range.screenshot()).toString('base64');return range.evaluate(async(e,png)=>{const s=getComputedStyle(e),im=new Image();im.src='data:image/png;base64,'+png;await im.decode();const c=document.createElement('canvas');c.width=im.width;c.height=im.height;const ctx=c.getContext('2d');ctx.drawImage(im,0,0);return{track:s.backgroundImage,pixel:[...ctx.getImageData(Math.round(9+(im.width-18)*Number(e.value)/5),Math.floor(im.height/2),1,1).data].slice(0,3),fill:e.style.getPropertyValue('--ms-effort-fill')}} ,png)};
  for(let i=0;i<5;i++){
   await range.evaluate((e,i)=>{e.value=i;e.dispatchEvent(new Event('input',{bubbles:true}));},i);
   const s=await read();assert(s.track.includes('rgb(157, 163, 174)')&&s.track.includes('rgb(194, 198, 207)'),JSON.stringify(s));assert(s.pixel.every((v,i)=>Math.abs(v-[174,180,191][i])<=2),JSON.stringify(s));assert.strictEqual(s.fill,i*20+'%');
  }
  await p.locator('.zs-effort-sec').screenshot({path:path.join(out,'maximum-slider-'+theme+'.png')});
  await range.focus();await range.press('End');const gradients=new Set(),thumbs=new Set();
  for(const palette of ['amethyst','rainbow','aurora','sunset']){
   await p.selectOption('#ms-ultra-palette',palette);const s=await read();gradients.add(s.track);thumbs.add(JSON.stringify(s.pixel));assert(s.track.startsWith('linear-gradient'),JSON.stringify(s));
   await p.locator('.zs-effort-sec').screenshot({path:path.join(out,palette+'-slider-'+theme+'.png')});
  }
  assert.strictEqual(gradients.size,4);assert.strictEqual(thumbs.size,4,'Rendered thumb changes with each Ultra palette');await p.emulateMedia({reducedMotion:'reduce'});assert.strictEqual(await p.locator('#ms-donate-bar').evaluate(e=>getComputedStyle(e).animationName),'none');
  assert.deepStrictEqual(x.errors,[]);console.log('PASS '+theme+': five neutral effort tracks/thumbs, all four distinct Ultra palettes shared by track and thumb, native keyboard range and reduced-motion donation.');
 }finally{await x.close();}
}})().catch(e=>{console.error(e.stack);process.exit(1)});
