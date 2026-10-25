// SPDX-License-Identifier: GPL-3.0-or-later
// Grants are exact local tabs opened by Multi-Script, never arbitrary localhost pages.
(function(g){'use strict';
  function create({chrome,tabs,readBridge=()=>null}){
    const grants=new Map(),storage=chrome.storage.session;
    const ready=storage?storage.get('msBlenderTabs').then(r=>{for(const [id,value]of r.msBlenderTabs||[])grants.set(id,value);}):Promise.resolve();
    async function save(){if(storage)await storage.set({msBlenderTabs:[...grants]});}
    async function remember(tab,source){await ready;const u=new URL(tab.url);if(u.protocol!=='http:'||u.hostname!=='127.0.0.1'||u.pathname!=='/')throw Error('Invalid workspace tab.');grants.set(tab.id,{origin:u.origin,source:Number.isInteger(source)?source:null});await save();}
    chrome.tabs.onRemoved?.addListener(id=>{void ready.then(async()=>{if(grants.delete(id))await save();});});
    chrome.tabs.onUpdated?.addListener((id,change)=>{if(change.url)void ready.then(async()=>{const grant=grants.get(id);if(grant){let valid=false;try{const u=new URL(change.url);valid=u.origin===grant.origin&&u.pathname==='/';}catch{}if(!valid){grants.delete(id);await save();}}});});
    async function handle(msg,sender){
      await ready;const grant=grants.get(sender.tab?.id);let u;
      try{u=new URL(sender.url||sender.tab?.url);}catch{throw Error('Open Blender Workspace from Multi-Script.');}
      if(sender.id!==chrome.runtime.id||sender.frameId!==0||!grant||u.origin!==grant.origin||u.pathname!=='/')throw Error('This tab is not a connected Blender Workspace.');
      if(msg.action==='list'){const result=await tabs.list();return {...result,sourceTabId:grant.source,bridge:readBridge()};}
      if(!['focus','settings','followup','stop'].includes(msg.action))throw Error('Unsupported workspace session action.');
      if(msg.action==='focus'||msg.action==='settings'){
        const result=await tabs.action({action:'focus',tabId:msg.tabId});
        if(msg.action==='settings')await chrome.tabs.sendMessage(msg.tabId,{type:'zs-open-menu'});
        return result;
      }
      // Native provider-side context/draft/generation checks and dispatch receipts
      // remain authoritative. Never turn an unconfirmed action into an automatic replay.
      return tabs.action({action:msg.action,tabId:msg.tabId,context:msg.context,requestId:msg.requestId,text:msg.text,chatOnly:false});
    }
    return {remember,handle};
  }
  const api={create};g.MSBlenderTabs=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
