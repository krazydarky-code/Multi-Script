const assert=require('assert'),fs=require('fs'),path=require('path'),h=require('../tools/studio_harness'),{entries,html}=require('./support/provider-fixtures');
const out=path.resolve(__dirname,'../../../../outputs/compact-effort-6.49.8');fs.mkdirSync(out,{recursive:true});
(async()=>{for(const id of ['arena','glm','kimi','claude','chatgpt']){
 const x=await h.open({provider:'providers/'+id+'.js',url:entries[id].url,html:html(id,''),width:1100,height:900,bridge:'up',storage:{zsSetupSeen:true,msExecutionEffort:'standard'}});assert(x);
 try{const p=x.page;await p.evaluate(()=>document.querySelector('#fixture-turns').replaceChildren());await p.click('#zs-switch');await p.click('[data-tab="bar"]');
  for(const dock of ['auto','float']){
   await p.click('[data-bar-dock="'+dock+'"]');
   for(const width of [654,672,710,960]){
    await p.locator('body>section').evaluate((e,w)=>e.style.maxWidth=w+'px',width);await p.waitForTimeout(350);
    const s=await p.evaluate(()=>{const b=document.querySelector('#zs-bar'),r=b.getBoundingClientRect(),id=b.querySelector('#zs-id').getBoundingClientRect(),a=b.querySelector('#zs-acts').getBoundingClientRect(),name=b.querySelector('.ms-brand-name');return{width:r.width,height:r.height,left:r.left,right:r.right,idRight:id.right,actsLeft:a.left,nameClipped:name.scrollWidth>name.clientWidth+1,controls:[...b.querySelector('#zs-acts').children].filter(e=>e.getClientRects().length&&getComputedStyle(e).display!=='none').map(e=>{const r=e.getBoundingClientRect();return{l:r.left,r:r.right}})}});
    assert(s.width>=width-50&&s.width<=width+2,JSON.stringify({id,dock,width,s}));assert(s.height<=56,JSON.stringify({id,dock,width,s}));assert(s.idRight<=s.actsLeft+1&&!s.nameClipped,JSON.stringify({id,dock,width,s}));assert(s.controls.every(c=>c.l>=s.left-1&&c.r<=s.right+1),JSON.stringify({id,dock,width,s}));
    if(width===672){const primary=await p.locator('#zs-action').evaluate(e=>{const s=getComputedStyle(e);return{display:s.display,overflow:s.textOverflow,title:e.title,text:e.textContent}});assert.strictEqual(primary.display,'block',id+' native portal rules must preserve text ellipsis');assert.strictEqual(primary.overflow,'ellipsis');assert.strictEqual(primary.title,primary.text);await p.click('#zs-menu-x');await p.locator('#zs-bar').screenshot({path:path.join(out,id+'-standard-'+dock+'.png')});await p.click('#zs-switch');await p.click('[data-tab="bar"]');}
   }
  }
  assert.deepStrictEqual(x.errors,[]);console.log('PASS '+id+': Auto/Floating keep one row, complete brand, adjacent effort and bounded controls through four live composer resizes.');
 }finally{await x.close();}
}})().catch(e=>{console.error(e.stack);process.exit(1)});
