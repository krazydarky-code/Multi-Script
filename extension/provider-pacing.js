// SPDX-License-Identifier: GPL-3.0-or-later
// Shared across content tabs by the extension worker. Stores only provider ids,
// lease tokens and timestamps; never messages, credentials or account ids.
(function(g){
  'use strict';
  function create({read,write,now=Date.now}) {
    let queue=Promise.resolve();
    const update=fn=>{const job=queue.then(async()=>{const state=await read()||{};const result=fn(state);await write(state);return {...result,policyVersion:2};});queue=job.catch(()=>{});return job;};
    return (msg)=>update(state=>{
      if(!/^[a-z][a-z0-9_-]{0,39}$/.test(msg.provider||''))throw Error('Invalid provider pacing id');
      const t=now(),p=Object.prototype.hasOwnProperty.call(state,msg.provider)?state[msg.provider]:{nextAt:0,cooldownUntil:0,strikes:0};state[msg.provider]=p;
      const owner=String(msg.owner||'').slice(0,100);
      if(!owner)throw Error('A send lease requires an owner token');
      const gap=Math.max(2500,Math.min(30000,Number(msg.gapMs)||5000));
      // Remove only 6.48.6's synthetic DeepSeek delay/burst state. A real
      // provider cooldown, account pause or live send lease must survive.
      if(msg.provider==='deepseek'&&p.pacingRevision!==2){
        if(p.gapMs===20000){if(p.nextAt)p.nextAt=Math.min(p.nextAt,p.nextAt-20000+5000);p.gapMs=5000;}
        delete p.recent;p.pacingRevision=2;
      }
      if(msg.action==='acquire') {
        if(p.blocked)return{ok:true,granted:false,blocked:true,reason:p.reason||'Provider usage or access limit'};
        if(p.owner&&p.leaseUntil>t&&p.owner!==owner)return{ok:true,granted:false,waitMs:Math.min(1500,p.leaseUntil-t)};
        const wait=Math.max(0,(p.nextAt||0)-t,(p.cooldownUntil||0)-t);
        if(wait>0)return{ok:true,granted:false,waitMs:Math.min(wait,60000),cooldownUntil:p.cooldownUntil||0};
        p.owner=owner;p.leaseUntil=t+120000;p.gapMs=gap;
        return{ok:true,granted:true};
      }
      if(msg.action==='release') {
        if(p.owner!==owner)return{ok:true,stale:true};
        p.owner='';p.leaseUntil=0;p.nextAt=t+(p.gapMs||gap);
        if(msg.kind==='quota'){p.blocked=true;p.reason=String(msg.reason||'Provider access or verification notice; inspect the site before resuming.').slice(0,200);}
        if(msg.kind==='rate') {
          p.strikes=Math.min(6,(p.strikes||0)+1);
          const backoff=Math.min(900000,30000*2**(p.strikes-1));
          p.cooldownUntil=Math.max(p.cooldownUntil||0,t+backoff,t+Math.min(86400000,Math.max(0,Number(msg.retryAfterMs)||0)));
        } else if(msg.kind==='unconfirmed'||msg.kind==='busy')p.cooldownUntil=Math.max(p.cooldownUntil||0,t+15000);
        else if(msg.success)p.strikes=Math.max(0,(p.strikes||0)-1);
        return{ok:true,cooldownUntil:p.cooldownUntil||0};
      }
      if(msg.action==='notice') {
        if(msg.kind==='quota'){p.blocked=true;p.reason=String(msg.reason||'Provider usage or access limit').slice(0,200);}
        if(msg.kind==='rate'){
          p.strikes=Math.min(6,Number(p.strikes||0)+1);
          p.cooldownUntil=Math.max(p.cooldownUntil||0,t+Math.min(900000,30000*2**(p.strikes-1)),t+Math.min(86400000,Math.max(0,Number(msg.retryAfterMs)||0)));
        }
        return{ok:true,cooldownUntil:p.cooldownUntil||0,blocked:!!p.blocked};
      }
      if(msg.action==='resume') {
        // Only an explicit new user submission clears an access/quota pause.
        p.blocked=false;p.reason='';return{ok:true};
      }
      throw Error('Invalid provider pacing action');
    });
  }
  g.MSProviderPacing={create};if(typeof module!=='undefined'&&module.exports)module.exports=g.MSProviderPacing;
})(typeof self!=='undefined'?self:globalThis);
