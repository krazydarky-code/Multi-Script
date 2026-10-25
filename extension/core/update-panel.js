// SPDX-License-Identifier: GPL-3.0-or-later
(function(g){'use strict';
function mount(root,{send}){
 if(!root?.querySelector)return {refresh:async()=>{},destroy(){}};
 let timer=null,revision=0,last=null,acting=false;
 const find=id=>root.querySelector('#'+id),status=find('ms-update-status'),check=find('ms-update-check'),apply=find('ms-update-apply'),automatic=find('ms-update-auto'),meter=find('ms-update-progress'),detail=find('ms-update-detail');
 const size=n=>n>=1048576?(n/1048576).toFixed(1)+' MB':Math.round(n/1024)+' KB';
 function paint(s){
  last=s;
  if(!s.ok){status.textContent=(s.error||'Update service unavailable.')+(s.setupNeeded?' Run Setup from the complete installed Multi-Script folder, then reopen Updates.':'');meter.hidden=true;check.disabled=acting;apply.disabled=true;return;}
  const busy=acting||s.busy;
  check.disabled=busy||s.setupPending;apply.disabled=busy||s.setupMismatch||s.setupNeeded||!(s.staged||s.recoveryRequired||s.needsReload||s.setupPending||s.pending||s.result?.status==='update_available');
  apply.textContent=s.setupPending?'Finish setup':s.needsReload?'Reload extension':s.recoveryRequired?'Recover & reload':'Apply & reload extension';
  automatic.checked=s.automatic!==false;automatic.disabled=!!(s.managed||s.unknown);
  let text=s.reloading?'Extension reloading. Refresh provider tabs.':s.unknown?'Install type is unknown; reopen your browser Extensions page to confirm this installation.':s.managed?'Browser-managed install: updates come from its store.':s.busy?(s.progress?.message||'Update operation in progress…'):s.recoveryRequired?'An interrupted update needs recovery. Stop sessions, then Recover & reload.':s.setupMismatch?'Versions differ: extension '+s.extensionVersion+', registered folder '+s.current+'. Run Setup from the folder loaded in your browser.':s.setupPending?'Version '+s.current+' files are installed; launcher setup still needs to finish. Refresh provider tabs and finish or stop active tasks, then Finish setup.':s.needsReload?'Version '+s.current+' is installed. Reload the extension, then refresh provider tabs.':s.setupNeeded?(s.setupIssue||'Install the complete Dev package and run Setup.'):!s.configured?'Publisher release hosting is not configured. See docs/UPDATES.md.':s.staged?'Version '+s.staged+' is verified and ready. Stop sessions, then Apply & reload.':'Running '+s.current+'. No newer signed release is staged.';
  if(s.lastError&&!s.busy)text+=' Last attempt: '+s.lastError;
  status.textContent=text;
  const p=s.progress||{},done=p.bytes??p.files,total=p.total??p.totalFiles;
  meter.hidden=!s.busy;
  if(s.busy&&total>0){meter.value=Math.max(0,Math.min(100,100*(done||0)/total));meter.setAttribute('aria-valuetext',Math.round(meter.value)+'%');}else meter.removeAttribute('value');
  detail.textContent=[s.root?'Registered installation: '+s.root:'',s.busy&&total>0?(p.totalFiles?(done||0)+' / '+total+' files':size(done||0)+' / '+size(total)):'',p.attempt>1?'Download attempt '+p.attempt+' of 3':'',s.checkedAt?'Last successful check: '+new Date(s.checkedAt).toLocaleString():''].filter(Boolean).join(' · ');
 }
 function schedule(s){clearTimeout(timer);if(s?.busy&&root.isConnected&&!root.closest('[hidden]'))timer=setTimeout(refresh,1200);}
 async function refresh(){const id=++revision;try{const state=await send({op:'status'});if(id===revision&&root.isConnected){paint(state);schedule(state);}}catch(e){if(id===revision)paint({ok:false,error:String(e.message||e)});}}
 async function act(op){
  if(acting)return;acting=true;const id=++revision;check.disabled=true;apply.disabled=true;status.textContent=op==='check'?'Checking signed release and download…':op==='reload'?'Reloading extension…':'Preparing update and recovery backup…';meter.hidden=false;meter.removeAttribute('value');
  // Independent status reads remain available while the long action is pending.
  timer=setTimeout(refresh,500);
  let result;try{result=await send({op});}catch(error){result={ok:false,error:String(error.message||error)};}
  acting=false;clearTimeout(timer);revision++;
  if(!root.isConnected)return;paint(result);
  if(!result.reloading){if(result.ok)await refresh();else{const error=result.error;await refresh();if(last?.ok){last.lastError=error;paint(last);}}}
 }
 check.onclick=e=>{if(e.isTrusted)void act('check');};apply.onclick=e=>{if(e.isTrusted)void act(last?.needsReload?'reload':'apply');};
 automatic.onchange=async e=>{if(!e.isTrusted)return;const result=await send({op:'preferences',automatic:automatic.checked});if(!result.ok){automatic.checked=!automatic.checked;status.textContent=result.error||'Preference could not be saved.';}};
 check.addEventListener('ms-update-status',refresh);
 return {refresh,destroy:()=>{revision++;clearTimeout(timer);}};
}
const api={mount};g.MSUpdatePanel=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
