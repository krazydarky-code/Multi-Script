const assert=require('assert'),{create}=require('../extension/updates');
(async()=>{
 let type='development',participants=[],prefs={},calls=[],reloaded=0,nativeStatus={ok:true,configured:true,current:'1.0',staged:'1.1'},block;
 const chrome={management:{getSelf:async()=>({installType:type})},runtime:{requestUpdateCheck:async()=>({status:'no_update'}),onUpdateAvailable:{addListener:f=>block=f}},alarms:{onAlarm:{addListener(){}},create(){}}};
 const updater=create({chrome,tabs:{list:async()=>({ok:true,participants})},nativeCall:async(cmd,args)=>{calls.push(args.action);return args.action==='status'?nativeStatus:{ok:true,current:'1.1',installed:'1.1'};},storageGet:async()=>prefs,storageSet:async p=>Object.assign(prefs,p),stopBridge:async()=>{calls.push('stop');return {ok:true};},reload:()=>reloaded++});
 assert((await updater.handle({op:'status'})).staged==='1.1');
 for(const bad of [{running:true},{generating:true},{hasDraft:true},{queuePending:1},{sendUnconfirmed:true},{enhancing:true},{starting:true},{ok:false}]){
  participants=[{ok:true,...bad}];calls=[];assert(!(await updater.handle({op:'apply'})).ok);assert(!calls.includes('stop'));assert(!calls.includes('apply'));
 }
 participants=[{ok:true,started:true,stopped:false}];assert(!(await updater.handle({op:'apply'})).ok);
 participants=[{ok:true,started:true,stopped:true}];assert((await updater.handle({op:'apply'})).ok);assert(reloaded===1);assert(calls.includes('apply'));assert(prefs.msBridgeUserStopped===false);
 prefs={msUpdatesAutomatic:false};calls=[];assert((await updater.handle({op:'automatic'})).skipped);assert(!calls.length);
 await updater.handle({op:'preferences',automatic:true});assert(prefs.msUpdatesAutomatic===true);
 type='normal';calls=[];assert((await updater.handle({op:'check'})).managed);assert(!calls.length);assert(!(await updater.handle({op:'apply'})).ok);
 block({version:'2.0'});participants=[];assert((await updater.handle({op:'apply'})).ok);assert(reloaded===2);
 type='unknown';calls=[];assert((await updater.handle({op:'status'})).unknown);assert(!calls.length);
 assert(!(await updater.handle({op:'execute'})).ok);
 console.log('PASS updater install-type separation, all active/draft/queue/unconfirmed guards, explicit idle apply/reload, saved preferences, automatic-check opt-out, managed-store path and unknown-install refusal.');
})().catch(e=>{console.error(e);process.exitCode=1;});
