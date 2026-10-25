// SPDX-License-Identifier: GPL-3.0-or-later
// Isolated-world relay. The service worker validates the exact granted tab.
(()=>{'use strict';
  if(location.protocol!=='http:'||location.hostname!=='127.0.0.1'||location.pathname!=='/')return;
  window.addEventListener('message',event=>{
    const m=event.data;
    if(event.source!==window||event.origin!==location.origin||m?.type!=='ms-blender-request'||!Number.isInteger(m.id))return;
    if(!['list','focus','settings','followup','stop'].includes(m.action))return;
    try{chrome.runtime.sendMessage({type:'ms_blender_workspace_control',action:m.action,tabId:m.tabId,context:m.context,requestId:m.requestId,text:m.text},result=>{
      const error=chrome.runtime.lastError;
      window.postMessage({type:'ms-blender-reply',id:m.id,result:error?{ok:false,error:'Reload Multi-Script and reopen this workspace.'}:result},location.origin);
    });}catch{window.postMessage({type:'ms-blender-reply',id:m.id,result:{ok:false,error:'Reload Multi-Script and reopen this workspace.'}},location.origin);}
  });
})();
