// SPDX-License-Identifier: GPL-3.0-or-later
// Only acknowledged, context-bound provider actions cross the phone boundary.
(function(g){'use strict';
 function create({send,tabs,identity}){let busy=false,participants=[],receipts=[];
  async function tick(){if(busy)return;busy=true;try{const response=await send({type:'mobile_admin',op:'sync',owner:await identity(),payload:{participants,receipts}},12000);if(!response?.ok)return;receipts=[];if(!response.enabled){participants=[];return;}for(const command of response.commands||[]){try{const r=await tabs.action({action:command.action,tabId:command.tabId,context:command.context,requestId:command.id,text:command.text,kind:command.kind});receipts.push({id:command.id,ok:r?.ok===true,error:r?.error,note:r?.queued?'Queued in the selected chat; execution is pending.':r?.stopped?'Stop requested; an already-running tool may still settle.':undefined});}catch(e){receipts.push({id:command.id,ok:false,error:String(e.message||e)});}}participants=(await tabs.list()).participants||[];}catch{}finally{busy=false;}}
  return {tick};
 }
 g.MSMobileControl={create};if(typeof module!=='undefined'&&module.exports)module.exports=g.MSMobileControl;
})(globalThis);
