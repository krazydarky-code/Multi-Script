// SPDX-License-Identifier: GPL-3.0-or-later
// Signed package staging through the registered native host; settings stay local.
(function(g){'use strict';
function create({chrome,nativeCall,tabs,storageGet,storageSet,stopBridge,reload}){
 let operation=null,storePending=null;
 const current=()=>chrome.runtime.getManifest?.().version||'';
 const newer=(a,b)=>{const x=String(a).split('.').map(Number),y=String(b).split('.').map(Number);for(let i=0;i<4;i++){if((x[i]||0)!==(y[i]||0))return (x[i]||0)>(y[i]||0);}return false;};
 const fail=message=>{throw Error(message);};
 async function installType(){try{return (await chrome.management.getSelf()).installType;}catch{return 'unknown';}}
 async function idle(){const r=await tabs.list();if(!r.ok||!Array.isArray(r.participants)||r.participants.some(t=>!t.ok||t.running||t.starting||t.generating||t.hasDraft||t.queuePending||t.sendUnconfirmed||t.enhancing))fail('Finish or stop active chats, resolve drafts and queued prompts, and reload disconnected provider tabs before updating.');return r;}
 async function nativeState(prefs,own=false){
  const state=await nativeCall('update',{action:'status'},12000);
  if(!state.ok)return {...state,automatic:prefs.msUpdatesAutomatic!==false,setupNeeded:['host_missing','host_forbidden','host_exited'].includes(state.code)};
  // An earlier worker may have stopped the bridge and then lost its reply.
  if(prefs.msUpdateBridgePause&&!operation&&!state.busy&&!state.recoveryRequired&&!state.setupPending){
   await storageSet({msBridgeUserStopped:prefs.msUpdateBridgePause.wasUserStopped,msUpdateBridgePause:null});
  }
  const mismatch=!!(current()&&state.current&&current()!==state.current);
  const completedUpdate=mismatch&&newer(state.current,current())&&state.lastUpdate?.version===state.current;
  const needsReload=completedUpdate&&!state.recoveryRequired&&!state.busy&&!state.setupPending;
  return {...state,automatic:prefs.msUpdatesAutomatic!==false,extensionVersion:current(),operation,busy:!!(state.busy||(!own&&operation)),needsReload,setupMismatch:mismatch&&!completedUpdate&&!state.busy&&!state.recoveryRequired,setupNeeded:state.setupReady===false,checkedAt:prefs.msUpdateLastCheck||null,lastError:prefs.msUpdateLastError||state.lastCheckError||null};
 }
 async function handle(msg){
  if(!['status','check','apply','reload','preferences','automatic','finish_setup'].includes(msg.op))return {ok:false,error:'Unsupported update action.'};
  const prefs=await storageGet(['msUpdatesAutomatic','msUpdateLastCheck','msUpdateLastAttempt','msUpdateLastError','msUpdateFailureCount','msUpdateRetryAt','msBridgeUserStopped','msUpdateBridgePause','msStoreUpdatePending','msUpdateSetupTries']);
  if(msg.op==='preferences'){await storageSet({msUpdatesAutomatic:msg.automatic!==false});return {ok:true,automatic:msg.automatic!==false};}
  const type=await installType();
  if(type!=='development'){
   storePending=storePending||prefs.msStoreUpdatePending||null;
   if(msg.op==='apply'||msg.op==='reload'){
    if(type==='unknown')return {ok:false,error:'Install type is unknown. Reload the Extensions page and run Setup from your installed folder.'};
    if(!storePending)return {ok:false,error:'No browser-managed update is pending.'};
    await idle();await storageSet({msStoreUpdatePending:null});reload();return {ok:true,reloading:true};
   }
   if(msg.op==='check')try{const result=await chrome.runtime.requestUpdateCheck();if(result.status==='update_available'){storePending=result.version;await storageSet({msStoreUpdatePending:result.version});}return {ok:true,managed:true,result,pending:storePending,automatic:true};}catch(error){return {ok:false,managed:true,error:String(error.message||error)};}
   return {ok:true,managed:type!=='unknown',unknown:type==='unknown',pending:storePending,automatic:true};
  }
  if(msg.op==='status')return nativeState(prefs);
  if(operation){if(msg.op==='finish_setup'&&msg.automatic)chrome.alarms?.create('ms-finish-setup',{delayInMinutes:1});return {ok:false,busy:true,error:'An update operation is already running. Its progress is available below.'};}
  if(msg.op==='automatic'&&(prefs.msUpdatesAutomatic===false||Date.now()-(prefs.msUpdateLastCheck||0)<86400000||Date.now()-(prefs.msUpdateLastAttempt||0)<900000||Date.now()<(prefs.msUpdateRetryAt||0)))return {ok:true,skipped:true};
  operation=msg.op;
  let paused=false,settled=false,pendingSetup=false,setupAttempts=0,checking=false;
  try{
   const state=await nativeState(prefs,true);
   if(!state.ok)return state;
   if(['automatic','check'].includes(msg.op)&&state.nextCheckAt>Date.now()){
    if(msg.op==='automatic')return {...state,skipped:true};
    fail(state.lastCheckError||'Update hosting requested a cooldown. Wait before checking again.');
   }
   pendingSetup=!!state.setupPending;
   if(msg.op==='finish_setup'&&(!state.setupPending||state.setupNeeded)){if(!state.setupPending&&!state.busy&&!state.recoveryRequired&&prefs.msUpdateBridgePause){await storageSet({msBridgeUserStopped:prefs.msUpdateBridgePause.wasUserStopped,msUpdateBridgePause:null});chrome.alarms?.clear?.('ms-finish-setup');}return {...state,skipped:true};}
   if(state.busy)fail('Another updater is running. Wait for its progress to finish.');
   if(msg.op==='reload'){
    if(!state.needsReload)fail('No completed update is waiting for a reload.');
    await idle();reload();return {ok:true,reloading:true};
   }
   if(state.setupMismatch)fail('The extension and registered installation versions differ. Run Setup from the complete folder loaded in your browser, then retry. Registered folder: '+state.root);
   if(state.setupNeeded)fail(state.setupIssue||'Install the complete Dev package and run Setup from that folder.');
   if(!state.configured)return {...state,automatic:prefs.msUpdatesAutomatic!==false};
   operation=msg.op;
   if(msg.op==='apply'||msg.op==='finish_setup'){
    if(state.needsReload){await idle();reload();return {ok:true,reloading:true};}
    if(!state.staged&&!state.recoveryRequired&&!state.setupPending)fail('Check and download a signed release first.');
    if(msg.automatic){setupAttempts=prefs.msUpdateSetupTries?.version===state.current?prefs.msUpdateSetupTries.count||0:0;if(setupAttempts>=3)return {...state,skipped:true};}
    const sessions=await idle();
    if(!state.setupPending&&sessions.participants.some(t=>t.started&&!t.stopped))fail('Stop Multi-Script sessions in all provider tabs before applying an update.');
    // Busy chats defer setup without consuming an installation attempt.
    if(msg.automatic)await storageSet({msUpdateSetupTries:{version:state.current,count:++setupAttempts}});
    const pause=prefs.msUpdateBridgePause||{wasUserStopped:prefs.msBridgeUserStopped===true,at:Date.now()};
    await storageSet({msUpdateBridgePause:pause,msBridgeUserStopped:true});paused=true;
    const stopped=await stopBridge();if(!stopped.ok)fail(stopped.error||'Could not stop the bridge.');
    await idle();
    let result=await nativeCall('update',{action:state.recoveryRequired?'recover':state.setupPending?'setup':'apply'},300000);
    if(!result.ok)fail(result.error||'Update failed. Check recovery status below.');
    if(result.setupPending){pendingSetup=true;result=await nativeCall('update',{action:'setup'},300000);if(!result.ok||result.setupPending)fail(result.error||'Files installed, but setup is incomplete. Retry Finish setup.');}
    await storageSet({msUpdateReceipt:{version:result.installed||result.current,at:Date.now(),recovered:!!result.recovered},msBridgeUserStopped:pause.wasUserStopped,msUpdateBridgePause:null,msUpdateLastError:null,msUpdateSetupTries:null});settled=true;chrome.alarms?.clear?.('ms-finish-setup');
    if(msg.op==='finish_setup'&&current()===result.current)return {...result,setupComplete:true};
    reload();return {...result,reloading:true};
   }
   if(state.recoveryRequired||state.setupPending)return state;
   await storageSet({msUpdateLastAttempt:Date.now()});
   checking=true;
   const result=await nativeCall('update',{action:'check'},240000);
   if(!result.ok)fail(result.error||'Could not download the signed update.');
   await storageSet({msUpdateLastCheck:Date.now(),msUpdateLastError:null,msUpdateFailureCount:0,msUpdateRetryAt:null});
   return {...result,busy:false,automatic:prefs.msUpdatesAutomatic!==false};
  }catch(error){
   const message=String(error?.message||error);await storageSet({msUpdateLastError:message});
   if(checking){const failures=Math.min(10,Math.max(0,Number(prefs.msUpdateFailureCount)||0)+1);await storageSet({msUpdateFailureCount:failures,msUpdateRetryAt:Date.now()+Math.min(86400000,900000*2**(failures-1))});}
   if(pendingSetup&&msg.automatic&&setupAttempts<3)chrome.alarms?.create('ms-finish-setup',{delayInMinutes:1});
   return {ok:false,error:message};
  }finally{
   operation=null;
   if(paused&&!settled){
    // Do not restart a bridge over a still-running or interrupted native apply.
    const state=await nativeCall('update',{action:'status'},12000).catch(()=>({ok:false}));
    if(state.ok&&!state.busy&&!state.recoveryRequired&&!state.setupPending){
     const saved=await storageGet(['msUpdateBridgePause']);
     if(saved.msUpdateBridgePause)await storageSet({msBridgeUserStopped:saved.msUpdateBridgePause.wasUserStopped,msUpdateBridgePause:null});
    }
   }
  }
 }
 chrome.runtime.onUpdateAvailable?.addListener(info=>{storePending=info.version;void storageSet({msStoreUpdatePending:info.version}).catch(()=>{});});
 chrome.alarms?.onAlarm.addListener(a=>{if(a.name==='ms-release-check')void safeHandle({op:'automatic'});if(a.name==='ms-finish-setup')void safeHandle({op:'finish_setup',automatic:true});});
 // Preserve the existing alarm across service-worker restarts.
 if(chrome.alarms?.get)Promise.resolve(chrome.alarms.get('ms-release-check')).then(alarm=>{if(!alarm)chrome.alarms.create('ms-release-check',{delayInMinutes:5,periodInMinutes:15});}).catch(()=>{});
 else chrome.alarms?.create('ms-release-check',{delayInMinutes:5,periodInMinutes:15});
 async function safeHandle(msg){try{return await handle(msg);}catch(error){return {ok:false,error:String(error?.message||error)};}}
 return {handle:safeHandle};
}
const api={create};g.MSUpdates=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
