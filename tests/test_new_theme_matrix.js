// SPDX-License-Identifier: GPL-3.0-or-later
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const harness = require('../tools/studio_harness');
const themes = require('../extension/core/theme-catalog').themes.filter(t => ['cobalt','porcelain','ember','tidal','starlight','daybreak'].includes(t.id));
const failures = [], counts = { combinations:0, contrast:0, paintedContrast:0, motion:0, screenshots:0 };
const shots = process.env.MS_THEME_SCREENSHOTS;
if (shots) fs.mkdirSync(shots, {recursive:true});

// Resolve translucent control backgrounds through their actual ancestor stack.
// Scene light panels are also checked for an opaque reading surface below.
async function inspect(page, context, portal=false) {
  const result = await page.evaluate(portal => {
    const barNode=document.querySelector('#zs-bar'),parent=barNode.parentNode,next=barNode.nextSibling;
    if(portal) document.querySelector('form,fieldset').prepend(barNode);
    const rgb = s => {const a=(s.match(/[\d.]+/g)||[]).map(Number);return s.startsWith('color(srgb ')?a.map((v,i)=>i<3?v*255:v):a;};
    const blend = (a,b) => a.slice(0,3).map((v,i) => v*(a[3]??1)+b[i]*(1-(a[3]??1)));
    const background = e => {const stack=[];for(let p=e;p;p=p.parentElement)stack.push(rgb(getComputedStyle(p).backgroundColor));return stack.reverse().reduce((b,a)=>blend(a,b),[255,255,255]);};
    const lum = a => a.map(v=>(v/=255)<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
    const selectors=['#zs-brand','#zs-state','#ms-new-idea','#ms-effort-indicator','#zs-chat-only','#zs-switch','#zs-bridge-run',
      '#zs-menu .zs-menu-logo','#zs-menu .zs-menu-health','#zs-menu .zs-menu-tabs button','#zs-menu .zs-menu-note','#zs-menu .zs-pref-label','#zs-menu .zs-slider-label','#zs-menu .zs-pref-opt','#zs-menu .zs-setting-title','#zs-menu .zs-theme-opt b','#ms-bar-theme'];
    const checks=[];
    for(const selector of selectors) for(const e of document.querySelectorAll(selector)) {
      const r=e.getBoundingClientRect(),s=getComputedStyle(e);
      if(!r.width||!r.height||s.visibility==='hidden'||s.display==='none'||parseFloat(s.fontSize)===0||e.disabled)continue;
      const b=background(e),f=blend(rgb(s.color),b),a=lum(b),c=lum(f),ratio=(Math.max(a,c)+.05)/(Math.min(a,c)+.05);
      checks.push({selector,text:(e.textContent||'icon').trim().slice(0,42),ratio:+ratio.toFixed(2),fg:s.color,bg:b});
    }
    const menu=document.querySelector('#zs-menu'),bar=document.querySelector('#zs-bar');
    const result={checks,menuScene:menu.querySelectorAll(':scope > .ms-scene').length,barScene:bar.querySelectorAll(':scope > .ms-scene').length,barLight:bar.dataset.msBarLight,ultraGradient:getComputedStyle(bar.querySelector('#ms-effort-indicator')).backgroundImage,
      ported:!bar.closest('#zs-root'),rect:{x:bar.getBoundingClientRect().x,right:bar.getBoundingClientRect().right},viewport:innerWidth};
    if(portal) parent.insertBefore(barNode,next);
    return result;
  },portal);
  counts.combinations++;
  for(const check of result.checks) {counts.contrast++;if(check.ratio<4.5)failures.push(`${context}: ${JSON.stringify(check)}`);}
  return result;
}

async function paintedContrast(page,context) {
  // Read actual compositor pixels, including scene layers and ::after scrims.
  // Temporarily hide foregrounds without changing layout or background tokens.
  // Returning a simulated portal to #zs-root replays the entry fade. Sample
  // the settled surface, not a partly transparent frame over the host page.
  await page.waitForFunction(()=>Number(getComputedStyle(document.querySelector('#zs-bar')).opacity)>.999);
  const samples=await page.evaluate(()=>{const b=document.querySelector('#zs-bar'),r=b.getBoundingClientRect();return [...b.querySelectorAll('#zs-brand,#zs-state,#ms-new-idea,#ms-effort-indicator,#zs-chat-only,#zs-switch,#zs-bridge-run')].map(e=>{const q=e.getBoundingClientRect(),style=getComputedStyle(e);let left=q.left,right=q.right,top=q.top,bottom=q.bottom;for(let p=e.parentElement;p;p=p.parentElement){const s=getComputedStyle(p),r=p.getBoundingClientRect();if(/hidden|clip|auto|scroll/.test(s.overflowX)){left=Math.max(left,r.left);right=Math.min(right,r.right);}if(/hidden|clip|auto|scroll/.test(s.overflowY)){top=Math.max(top,r.top);bottom=Math.min(bottom,r.bottom);}}return {id:e.id,color:style.color,foregrounds:style.backgroundClip==='text'?(style.backgroundImage.match(/rgba?\([^)]+\)/g)||[style.color]):[style.color],x:Math.floor((left+right)/2-r.x),y:Math.floor((top+bottom)/2-r.y),visible:right-left>1&&bottom-top>1};}).filter(s=>s.visible);});
  const style=await page.addStyleTag({content:'#zs-bar > :not(.ms-scene),#zs-bar > :not(.ms-scene) * {color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important;transition:none!important} #zs-bar > :not(.ms-scene) svg{visibility:hidden!important} #zs-bar #ms-effort-indicator{background-image:none!important}'});
  let buffer;
  try{buffer=await page.locator('#zs-bar').screenshot({animations:'allow'});}finally{await style.evaluate(e=>e.remove());await page.waitForTimeout(230);}
  const results=await page.evaluate(async({base64,samples})=>{
    const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0)),bitmap=await createImageBitmap(new Blob([bytes],{type:'image/png'})),canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;const ctx=canvas.getContext('2d');ctx.drawImage(bitmap,0,0);bitmap.close();
    const lum=a=>a.map(v=>(v/=255)<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
    return samples.map(s=>{const bg=[...ctx.getImageData(s.x,s.y,1,1).data].slice(0,3),a=lum(bg),ratios=s.foregrounds.map(color=>{const b=lum((color.match(/[\d.]+/g)||[]).slice(0,3).map(Number));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);});return {...s,bg,ratio:+Math.min(...ratios).toFixed(2)};});
  },{base64:buffer.toString('base64'),samples});
  for(const s of results){counts.paintedContrast++;if(s.ratio<4.5)failures.push(`${context}/paint: ${JSON.stringify({...s,selector:'#'+s.id})}`);}
}

(async()=>{
  for(const site of ['notion','claude']) {
    const x=await harness.open({site,bridge:'up',storage:{msExecutionEffort:'ultra',msMenuPreferences:{theme:'cobalt',barFit:'fit',width:'studio'}}});
    assert(x,'Chromium is required for theme verification');
    try {
      const p=x.page;await p.click('#zs-switch');
      // Text must adopt a new dark palette immediately, even before a delayed
      // animation frame can finish the previous light-theme transition.
      await p.click('[data-tab="bar"]');await p.selectOption('#ms-bar-theme','daybreak');await p.waitForTimeout(230);await p.selectOption('#ms-bar-theme','cobalt');
      assert.strictEqual(await p.locator('#zs-chat-only').evaluate(e=>getComputedStyle(e).color),'rgb(234, 243, 255)');
      for(const dock of ['auto','window']) {
        await p.click('[data-tab="bar"]');await p.click(`[data-bar-dock="${dock}"]`);
        for(const menu of themes) {
          await p.click('[data-tab="look"]');await p.click(`[data-theme="${menu.id}"]`);
          await p.waitForTimeout(230);await inspect(p,`${site}/${dock}/${menu.id}/picker`);
          await p.click('[data-tab="bar"]');
          for(const bar of themes) {
            await p.selectOption('#ms-bar-theme',bar.id);await p.waitForTimeout(230);
            const context=`${site}/${dock}/${menu.id}/${bar.id}`,r=await inspect(p,context);
            assert.strictEqual(r.barLight,bar.light?'1':'0',context);
            assert(r.ultraGradient.includes(bar.light?'rgb(98, 48, 168)':'rgb(180, 138, 255)'),context+' Ultra gradient must follow the bar, independently of the menu');
            assert.strictEqual(r.menuScene,menu.animated?1:0,context+' menu scene count');
            assert.strictEqual(r.barScene,bar.animated?1:0,context+' bar scene count');
            if(dock==='window')assert.strictEqual(r.ported,false,context+' window dock');
            const port=await inspect(p,context+'/portal',true);assert(port.ported,context+' portal styles');
            assert(r.rect.x>=-1&&r.rect.right<=r.viewport+1,context+' bar outside viewport');
            if(dock==='window'&&['cobalt','porcelain'].includes(menu.id))await paintedContrast(p,context);
          }
        }
        console.log('Verified '+site+'/'+dock+' theme combinations; contrast failures: '+failures.length);
      }
      for(const theme of themes) {
        await p.click('[data-tab="look"]');await p.click(`[data-theme="${theme.id}"]`);
        await p.click('[data-tab="bar"]');await p.selectOption('#ms-bar-theme','auto');
        await p.setViewportSize({width:390,height:844});await p.waitForTimeout(250);
        await inspect(p,`${site}/390/${theme.id}/follow`);
        await paintedContrast(p,`${site}/390/${theme.id}`);
        assert.strictEqual(await p.evaluate(()=>window.__store.msMenuPreferences.theme),theme.id);
        assert.strictEqual(await p.getAttribute('#zs-bar','data-ms-bar-theme'),theme.id);
        if(shots&&site==='notion') {await p.screenshot({path:path.join(shots,theme.id+'-mobile.png')});counts.screenshots++;}
        if(theme.animated) {
          for(const motion of ['full','reduced','none']) {
            await p.click('[data-tab="look"]');await p.click(`button[data-motion="${motion}"]`);
            await p.waitForTimeout(100);
            const state=await p.evaluate(()=>[...document.querySelectorAll('.ms-scene')].map(s=>({motion:s.dataset.motion,active:[...s.querySelectorAll('*')].filter(e=>getComputedStyle(e).animationName!=='none').length})));
            assert.strictEqual(state.length,2,'both menu and bar scenes survive motion changes');
            for(const s of state){assert.strictEqual(s.motion,motion);assert(motion==='full'?s.active>0:s.active===0,JSON.stringify({theme:theme.id,motion,state}));counts.motion++;}
          }
          await p.click('button[data-motion="full"]');await p.emulateMedia({reducedMotion:'reduce'});await p.waitForTimeout(100);
          assert.strictEqual(await p.evaluate(()=>[...document.querySelectorAll('.ms-scene *')].filter(e=>getComputedStyle(e).animationName!=='none').length),0,'OS reduced motion');counts.motion++;
          await p.emulateMedia({reducedMotion:'no-preference'});
        }
        await p.setViewportSize({width:1440,height:960});
      }
      // The last selection must survive a fresh extension initialization.
      const saved=await p.evaluate(()=>window.__store);
      const fresh=await harness.open({site,bridge:'up',storage:saved});
      try{assert.strictEqual(await fresh.page.getAttribute('#zs-bar','data-ms-bar-theme'),'daybreak');assert.deepStrictEqual(fresh.errors,[]);}finally{await fresh.close();}
      assert.deepStrictEqual(x.errors,[]);
    } finally {await x.close();}
  }
  if(process.env.MS_THEME_REPORT)fs.writeFileSync(process.env.MS_THEME_REPORT,JSON.stringify({counts,failures},null,2));
  if(failures.length) {
    const samples=new Map();for(const f of failures){const k=f.split(': {')[0].split('/')[2]+' '+JSON.parse(f.slice(f.indexOf('{'))).selector;if(!samples.has(k))samples.set(k,f);}
    console.error([...samples.values()].slice(0,65).join('\n'));
  }
  assert.strictEqual(failures.length,0,`${failures.length} low-contrast text/control cases`);
  console.log('PASS new theme matrix '+JSON.stringify(counts)+'; independent menus/bars, composer portals, mobile, persistence, scene cleanup and motion preferences.');
})().catch(e=>{console.error(e.stack);process.exit(1);});
