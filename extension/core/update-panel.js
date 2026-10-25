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
// Storage changes carry availability; no timer, history observer or native-host
// polling is needed in provider tabs. Applying still uses the guarded service.
function notice({root,menu,storage,version,send,openSettings,onLayout=()=>{}}){
 const doc=root.ownerDocument;let available=null,dismissed=null,overlay=null,previousFocus=null,disposed=false,locked=[],forcedOpen=false;
 const newer=(a,b)=>{const x=String(a).split('.').map(Number),y=String(b).split('.').map(Number);for(let i=0;i<4;i++)if((x[i]||0)!==(y[i]||0))return (x[i]||0)>(y[i]||0);return false;};
 const button=doc.createElement('button');button.id='ms-update-notice';button.type='button';button.hidden=true;button.setAttribute('aria-label','Update Multi-Script');button.title='A new Multi-Script update is ready';
 button.innerHTML='<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/></svg>';
 const style=doc.createElement('style');style.textContent=`
 #zs-bar.zs-bar-inline{position:relative}
 #zs-bar #ms-update-notice[hidden],#zs-root #ms-update-overlay[hidden]{display:none!important}
 #zs-bar #ms-update-notice{position:absolute;inset-inline-end:6px;top:-15px;width:28px;height:28px;border:1px solid #60dfa2;border-radius:9px;background:#123c2d;color:#9fffc5;box-shadow:0 0 12px #39d98766;cursor:pointer;display:grid;place-items:center}
 #zs-bar #ms-update-notice svg{animation:ms-update-bob 2.4s ease-in-out infinite}
 #zs-bar #ms-update-notice:focus-visible{outline:2px solid #b2ffce;outline-offset:3px}
 #zs-root #ms-update-overlay{position:absolute;inset:0;z-index:20;background:#090c1499;backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px);display:grid;place-items:center;padding:20px;border-radius:inherit}
 #zs-root #ms-update-dialog{box-sizing:border-box;width:min(100%,390px);padding:24px;border:1px solid #64dba099;border-radius:16px;background:#131b21;color:#f2faf6;box-shadow:0 18px 60px #0007;font:13px/1.5 system-ui}
 #zs-root #ms-update-dialog h2{margin:0 0 10px;font-size:20px;color:inherit}
 #zs-root #ms-update-dialog p{margin:0 0 14px;color:inherit}
 #zs-root #ms-update-dialog .ms-update-choice{display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap}
 #zs-root #ms-update-dialog button{font:inherit;padding:8px 15px;border:1px solid #7d998c;border-radius:8px;background:#24352f;color:inherit;cursor:pointer}
 #zs-root #ms-update-dialog button[data-update]{background:#15683e;border-color:#67e7a2}
 #zs-root #ms-update-dialog button:disabled{opacity:.6;cursor:wait}
 #zs-root #ms-update-dialog button:focus-visible{outline:2px solid #9fffc5;outline-offset:3px}
 @keyframes ms-update-bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}
 @media(prefers-reduced-motion:reduce){#zs-bar #ms-update-notice svg{animation:none}}
 @media(forced-colors:active){#zs-bar #ms-update-notice,#zs-root #ms-update-dialog{border:1px solid ButtonText;background:Canvas;color:CanvasText;box-shadow:none}}
 `;
 root.appendChild(style);(root.querySelector('#zs-bar')||root).appendChild(button);
 function close({remember=false,preserve=false}={}){
  if(!preserve)forcedOpen=false;
  if(remember&&available){dismissed=available;void storage.set({msUpdateNoticeDismissed:available});}
  overlay?.remove();overlay=null;for(const [el,was] of locked)el.inert=was;locked=[];
  if(previousFocus?.isConnected)previousFocus.focus();previousFocus=null;
 }
 function open(explicit=false){
  if(explicit)forcedOpen=true;
  if(disposed||!available||menu.hidden||overlay?.isConnected||(!forcedOpen&&dismissed===available))return;
  // A rebuilt menu detaches its old overlay. Release its inert state first.
  const restore=previousFocus?.isConnected?previousFocus:doc.activeElement;
  close({preserve:true});previousFocus=restore;
  overlay=doc.createElement('div');overlay.id='ms-update-overlay';
  overlay.innerHTML='<section id="ms-update-dialog" role="dialog" aria-modal="true" aria-labelledby="ms-update-title"><h2 id="ms-update-title">An update is ready</h2><p data-version></p><p>Update now? Finish or stop active sessions and resolve drafts first. Your settings and projects are preserved.</p><p role="status" aria-live="polite" data-message></p><div class="ms-update-choice"><button type="button" data-later>Later</button><button type="button" data-update>Update &amp; reload</button></div></section>';
  overlay.querySelector('[data-version]').textContent='Multi-Script '+available+' has been verified and downloaded.';
  locked=Array.from(menu.children).map(el=>[el,el.inert]);for(const [el] of locked)el.inert=true;
  menu.appendChild(overlay);
  const later=overlay.querySelector('[data-later]'),update=overlay.querySelector('[data-update]'),message=overlay.querySelector('[data-message]');
  later.onclick=e=>{if(e.isTrusted)close({remember:true});};
  update.onclick=async e=>{
   if(!e.isTrusted||update.disabled)return;
   update.disabled=true;message.textContent='Checking sessions and preparing the update…';
   try{const result=await send({op:'apply'});if(!overlay?.isConnected)return;message.textContent=result.ok?'Update applied. Refresh provider tabs after the extension reloads.':result.error||'Update could not be applied.';}
   catch(error){if(message.isConnected)message.textContent=String(error.message||error);}
   finally{if(update.isConnected)update.disabled=false;}
  };
  overlay.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close({remember:true});}else if(e.key==='Tab'){const first=update.disabled?later:(e.shiftKey?later:update);if(doc.activeElement===first){e.preventDefault();(e.shiftKey?(update.disabled?later:update):later).focus();}}};
  later.focus();
 }
 function paint(){const show=!!available;button.hidden=!show;button.setAttribute('aria-label',show?'Update Multi-Script to '+available:'Update Multi-Script');onLayout();if(!show)close();else if(!menu.hidden)open();}
 const changed=(changes,area)=>{if(area!=='local'||disposed)return;if(changes.msUpdateNoticeDismissed)dismissed=changes.msUpdateNoticeDismissed.newValue;if(changes.msUpdateAvailableVersion){const value=changes.msUpdateAvailableVersion.newValue;available=value&&newer(value,version)?value:null;paint();}};
 storage.get(['msUpdateAvailableVersion','msUpdateNoticeDismissed'],prefs=>{if(disposed)return;dismissed=prefs?.msUpdateNoticeDismissed;const value=prefs?.msUpdateAvailableVersion;available=value&&newer(value,version)?value:null;paint();});
 g.chrome?.storage?.onChanged?.addListener(changed);
 // Settings rebuild on bridge/theme changes. Observe this small panel only so
 // a refresh cannot silently discard the dialog or leave rebuilt controls live.
 const observer=new MutationObserver(()=>{if(disposed)return;if(menu.hidden){if(overlay)close();}else if(available&&!overlay?.isConnected)open();});
 observer.observe(menu,{childList:true,attributes:true,attributeFilter:['hidden']});
 button.onclick=e=>{if(!e.isTrusted)return;e.stopPropagation();openSettings();open(true);};
 return {opened:()=>open(),closed:()=>close(),destroy(){disposed=true;observer.disconnect();close();g.chrome?.storage?.onChanged?.removeListener(changed);button.remove();style.remove();}};
}
const api={mount,notice};g.MSUpdatePanel=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
