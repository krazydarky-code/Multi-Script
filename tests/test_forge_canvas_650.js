const assert=require('assert'),fs=require('fs'),path=require('path'),pw=require('./playwright-env');
(async()=>{
 const browser=await pw.launch();assert(browser,'Chromium required for real Canvas QA');
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://forge.test/',r=>r.fulfill({body:'<!doctype html><title>Forge Canvas QA</title>',contentType:'text/html'}));await page.goto('https://forge.test/');
  await page.addScriptTag({path:path.resolve(__dirname,'../extension/core/forge.js')});
  const result=await page.evaluate(async()=>{
   const Original=OffscreenCanvas;let allocations=0;
   window.OffscreenCanvas=class extends Original{constructor(...args){super(...args);allocations++;}};
   const started=performance.now(),small=await MSForge.render({action:'ui_kit',style:'cartoon',elements:['panel_inner']});const smallAllocations=allocations;
   allocations=0;const kit=await MSForge.render({action:'ui_kit',style:'cartoon',pack:'shop'});const packAllocations=allocations;
   const uiCounts={small:Object.keys(small.files).length,pack:Object.keys(kit.files).length,smallAllocations,packAllocations};
   const vfx=await MSForge.render({action:'vfx',textures:['spark','smoke_puff']});
   const unique=[],calls=[];
   for(let i=0;i<2;i++){
    const saved=[];const output=await MSForge.run({action:'ui_kit',style:'cartoon',name:'same-theme',elements:['panel_inner'],install:false},{studioReady:false,steps:[],callBridge:async(name,args)=>{calls.push(args.action);saved.push(args.name);return JSON.stringify({name:args.name,urls:[]});}});
    unique.push(output.name);
   }
   return {uiCounts,unique,calls,vfx:vfx.manifest.textures,png:small.files.panel_inner.slice(0,16),seconds:(performance.now()-started)/1000,preview:kit.preview};
  });
  assert.strictEqual(result.uiCounts.small,1);assert(result.uiCounts.pack>5,'Complete shop pack must not silently truncate to five images');
  assert(result.uiCounts.smallAllocations<result.uiCounts.packAllocations/3,'Unselected artwork was still drawn');
  assert.notStrictEqual(result.unique[0],result.unique[1]);assert(result.calls.every(x=>x==='save'));assert(result.png.startsWith('iVBORw0KGgo'));
  assert.deepStrictEqual(result.vfx.smoke_puff.size,[1024,1024]);assert.strictEqual(result.vfx.smoke_puff.layout,'Grid4x4');assert.deepStrictEqual(errors,[]);
  fs.mkdirSync('test-results/forge-650',{recursive:true});fs.writeFileSync('test-results/forge-650/shop-preview.png',Buffer.from(result.preview,'base64'));
  delete result.preview;fs.writeFileSync('test-results/forge-650/measurements.json',JSON.stringify(result,null,2));
  console.log('PASS real Chromium Canvas PNG/flipbook generation, complete packs, lazy selected drawing, preserved repeat generations, draw-only transport; '+JSON.stringify(result.uiCounts));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
