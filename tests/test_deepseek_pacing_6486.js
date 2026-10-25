const assert=require('assert'),{create}=require('../extension/provider-pacing');
(async()=>{let state={deepseek:{gapMs:20000,nextAt:21000,recent:[1,2,3,4,5,6]}},time=1000;const service=()=>create({read:async()=>structuredClone(state),write:async s=>{state=structuredClone(s);},now:()=>time});let call=service();
 const ask=owner=>call({action:'acquire',provider:'deepseek',owner,gapMs:5000});
 const initial=await ask('initial');assert(!initial.granted&&initial.waitMs===5000,'Migrate persisted 20s spacing to the normal 5s shared gap');assert(!state.deepseek.recent,'Remove the synthetic six-per-five-minute history');
 time+=5000;
 for(let i=0;i<8;i++){assert((await ask('tab-'+i)).granted);assert(!(await ask('other-tab')).granted,'Preserve single-flight leases');await call({action:'release',provider:'deepseek',owner:'tab-'+i,success:true});time+=4999;assert(!(await ask('early')).granted);time++;}
 assert((await ask('ninth')).granted,'No hidden six-message burst cap on ordinary turns');
 await call({action:'release',provider:'deepseek',owner:'ninth',kind:'rate',retryAfterMs:360000});call=service();await call({action:'resume',provider:'deepseek',owner:'user'});time+=300000;assert(!(await ask('respect-reset')).granted,'Worker restart and manual Start preserve real Retry-After cooldowns');
 time+=60000;assert((await ask('resumed')).granted);await call({action:'release',provider:'deepseek',owner:'resumed',kind:'quota',reason:'Your account is suspended'});assert((await ask('other-tab')).blocked);
 state.deepseek.pacingRevision=1;state.deepseek.recent=[time];assert((await ask('migration-cannot-unblock')).blocked,'Migration preserves an existing account pause');
 state.deepseek={gapMs:20000,owner:'live-owner',leaseUntil:time+120000,nextAt:0};assert(!(await ask('must-wait-for-live-owner')).granted,'Migration keeps the live owner');await call({action:'release',provider:'deepseek',owner:'live-owner',success:true});assert.strictEqual(state.deepseek.nextAt,time+5000,'A migrated in-flight release cannot recreate the 20-second gap');
 assert((await call({action:'acquire',provider:'chatgpt',owner:'independent'})).granted);
 console.log('PASS DeepSeek normal pacing, old-state migration, no synthetic burst cap, cross-tab leases, real reset/cooldown persistence and account-stop preservation.');
})().catch(e=>{console.error(e.stack);process.exit(1)});
