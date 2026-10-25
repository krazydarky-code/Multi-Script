// SPDX-License-Identifier: GPL-3.0-or-later
// Provider-tab coordination uses explicit targets and acknowledged messages.
// It never types into an arbitrary tab or treats dispatch as task completion.
(function(g){'use strict';
 function create({chrome,urls=()=>[],timeout=2500}){
  const allowed=url=>{try{const u=new URL(url);return u.protocol==='https:'&&urls().some(pattern=>{const p=new URL(pattern.replace(/\*.*$/,''));return p.hostname===u.hostname;});}catch{return false;}};
  const bounded=async(p,ms)=>{let timer;try{return await Promise.race([p,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Tab did not acknowledge. Inspect it before retrying.')),ms);})]);}finally{clearTimeout(timer);}};
  async function target(id){if(!Number.isInteger(id)||id<0)throw Error('Choose a provider tab.');const tab=await chrome.tabs.get(id);if(!allowed(tab.url))throw Error('Only a supported HTTPS provider tab can participate.');return tab;}
  async function list(){
   const tabs=(await chrome.tabs.query({url:urls()})).filter(t=>allowed(t.url)).slice(0,40);
   const participants=await Promise.all(tabs.map(async tab=>{const base={tabId:tab.id,title:String(tab.title||'Provider chat').slice(0,160),host:new URL(tab.url).hostname,active:!!tab.active};try{const state=await bounded(chrome.tabs.sendMessage(tab.id,{type:'ms-cowork-probe'}),timeout);return {...base,...(state?.ok?state:{ok:false,error:state?.error||'Reload this tab to connect Multi-Script.'})};}catch(e){return {...base,ok:false,error:e.message||'Reload this tab to connect Multi-Script.'};}}));
   return {ok:true,participants,note:'Only supported provider tabs were inspected. Start and assign tasks explicitly; each tab keeps its own model and account.'};
  }
  async function action(msg){
   const tab=await target(msg.tabId);
   if(msg.action==='focus'){await chrome.tabs.update(msg.tabId,{active:true});if(chrome.windows?.update&&Number.isInteger(tab.windowId))await chrome.windows.update(tab.windowId,{focused:true});return {ok:true};}
   if(msg.action==='read')return bounded(chrome.tabs.sendMessage(msg.tabId,{type:'ms-cowork-probe',includeBrief:true}),timeout);
   if(!['start','assign','pause','resume','stop','followup'].includes(msg.action))throw Error('Unsupported session action.');
   if(typeof msg.context!=='string'||!msg.context||msg.context.length>3000)throw Error('Refresh the session list before acting.');
   if(typeof msg.requestId!=='string'||!/^[a-zA-Z0-9-]{8,80}$/.test(msg.requestId))throw Error('A unique dispatch receipt is required.');
   return bounded(chrome.tabs.sendMessage(msg.tabId,{type:'ms-cowork-action',action:msg.action,context:msg.context,requestId:msg.requestId,taskId:msg.taskId,chatOnly:msg.chatOnly===true,background:msg.background===true,text:msg.text,kind:msg.kind}),35000);
  }
  return {list,action,allowed};
 }
 const api={create};g.MSCoworkTabs=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
