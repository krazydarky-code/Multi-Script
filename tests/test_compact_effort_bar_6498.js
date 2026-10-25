const assert=require('assert'),fs=require('fs'),path=require('path'),h=require('../tools/studio_harness'),{entries,html}=require('./support/provider-fixtures');
const out=path.resolve(__dirname,'../../../../outputs/compact-effort-6.49.8');fs.mkdirSync(out,{recursive:true});
const levels=['Adaptive','Quick','Standard','Deep','Maximum','Ultra'];
(async()=>{for(const id of Object.keys(entries)){
 const x=await h.open({provider:'providers/'+id+'.js',url:entries[id].url,html:html(id,'').replace('max-width:780px','max-width:672px'),stateHook:true,width:1100,height:900,bridge:'up',storage:{zsSetupSeen:true,msExecutionEffort:'adaptive'}});assert(x);
 try{const p=x.page;await p.evaluate(()=>{document.querySelector('#fixture-turns').replaceChildren();__qa.A.disabledEngines.add('roblox');});await p.waitForTimeout(150);
 await p.click('#zs-switch');await p.click('[data-tab="bar"]');
 for(const dock of ['auto','float','window']){
  await p.click('[data-bar-dock="'+dock+'"]');await p.click('[data-tab="agent"]');
  const heights=[];
  for(let i=0;i<6;i++){
   await p.locator('#ms-effort-slider').evaluate((e,i)=>{e.value=String(i);e.dispatchEvent(new Event('input',{bubbles:true}));},i);await p.evaluate(()=>new Promise(requestAnimationFrame));
   const s=await p.evaluate(()=>{const rect=e=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,right:r.right,bottom:r.bottom,w:r.width,h:r.height}};const b=document.querySelector('#zs-bar'),label=document.querySelector('#ms-effort-indicator'),name=b.querySelector('.ms-brand-name'),d=document.querySelector('#ms-donate-bar'),cs=getComputedStyle(label);return{bar:rect(b),identity:rect(b.querySelector('#zs-id')),acts:rect(b.querySelector('#zs-acts')),label:rect(label),nameClipped:name.scrollWidth>name.clientWidth+1,text:label.textContent,animation:cs.animationName,background:cs.backgroundImage,donate:{...rect(d),href:d.href,glow:getComputedStyle(d).boxShadow},badges:document.querySelectorAll('#zs-unstable').length,controls:[...b.querySelector('#zs-acts').children].filter(e=>e.getClientRects().length&&getComputedStyle(e).display!=='none'&&e.getBoundingClientRect().width>0).map(rect)};});
   assert.strictEqual(s.text,levels[i],id+' '+dock);assert.strictEqual(s.badges,0,id+' no permanent unstable badge');assert.strictEqual(s.donate.href,'https://ko-fi.com/multixscript');assert(s.donate.w>=24&&s.donate.glow!=='none',id+' visible glowing chatbar donation');
   assert(s.controls.every(r=>r.x>=s.bar.x-1&&r.right<=s.bar.right+1),JSON.stringify({id,dock,level:levels[i],s}));
   if(s.bar.w>=620){assert(s.bar.h<=56,id+' '+dock+' one compact row, '+s.bar.h);assert(s.identity.right<=s.acts.x+1,id+' no identity overlap');assert(!s.nameClipped,id+' full brand name beside effort');}
   assert(s.label.w>0&&s.label.x>=s.identity.x&&s.label.right<=s.identity.right+1,id+' effort stays visible');
   if(i!==5){assert.strictEqual(s.animation,'none',id+' ordinary effort has no animation');assert.strictEqual(s.background,'none',id+' ordinary effort has no Ultra gradient');}
   heights.push(s.bar.h);
  }
  assert(Math.max(...heights)-Math.min(...heights)<=2,id+' effort selection does not change bar height');
  await p.click('#zs-menu-x');if(['arena','glm','kimi','claude','chatgpt'].includes(id))await p.locator('#zs-bar').screenshot({path:path.join(out,id+'-'+dock+'.png')});
  await p.click('#zs-switch');await p.click('[data-tab="bar"]');
 }
 assert.deepStrictEqual(x.errors,[]);console.log('PASS '+id+': six effort labels, plain lower modes, same compact height, glowing Ko-fi control, no unstable badge, bounds and Auto/Floating/Window docks.');
 }finally{await x.close();}
}})().catch(e=>{console.error(e.stack);process.exit(1)});
