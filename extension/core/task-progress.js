// SPDX-License-Identifier: GPL-3.0-or-later
// Response lifecycle stages are observed locally; project steps require reported evidence.
(function(g){'use strict';
 const UPDATE_FIELDS={step_id:{type:'string'},status:{type:'string',enum:['pending','working','blocked','done']},evidence:{type:'string'},blocker:{type:'string'}};
 const TOOL={name:'ms_task_progress',server:'zeroscript',description:'Optional explicit checklist; response/tool activity is tracked locally without calls. Start the actual task directly. Use one plan only when useful or requested; batch meaningful milestone changes in updates, never report each tool. Done requires verification evidence. Updates return a short receipt; read retrieves the checklist. This records reported evidence, not independent certification.',inputSchema:{type:'object',additionalProperties:false,required:['action'],properties:{run_id:{type:'string',description:'Current task ID required for plan/update. Omit for read to discover the current task.'},action:{type:'string',enum:['plan','update','read']},steps:{type:'array',maxItems:24,items:{type:'object',required:['id','title'],additionalProperties:false,properties:{id:{type:'string'},title:{type:'string'},estimate_seconds:{type:'number',minimum:1,maximum:7200}}}},...UPDATE_FIELDS,updates:{type:'array',minItems:1,maxItems:24,description:'Apply multiple milestone updates atomically in one call, instead of separate provider turns.',items:{type:'object',additionalProperties:false,required:['step_id','status'],properties:UPDATE_FIELDS}}}}};
 const clean=(s,n)=>String(s||'').trim().slice(0,n),escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function create(title,context,id){const now=Date.now();return {id,title:clean(title,300),context,planSource:'automatic',activity:[],steps:[{id:'request',title:'Capture your request',status:'done',evidence:'Request captured by Multi-Script.',completed:now},{id:'response',title:'Work on your request',status:'working',started:now},{id:'delivery',title:'Receive the final response',status:'pending'}],created:now,updated:now,calls:0,errors:0,lastTool:'',activeTool:'',outcome:'working'};}
 // Small local history: useful execution detail without extra model turns or
 // copying an ever-growing transcript into storage/the provider conversation.
 function activity(run,event,now=Date.now()){
  if(!run||!['tool','tool-error','provider-error','recovery','waiting'].includes(event?.kind))return run;
  const item={kind:event.kind,title:clean(event.title,120),detail:clean(event.detail,500).trimEnd(),argument:clean(event.argument,100),at:now};
  const last=run.activity?.at(-1);
  if(last&&last.kind===item.kind&&last.title===item.title&&last.detail===item.detail&&last.argument===item.argument&&item.kind!=='tool'&&item.kind!=='tool-error')return run;
  run.activity=[...(run.activity||[]),item].slice(-12);run.updated=now;return run;
 }
 function observe(run,event,now=Date.now()){
  if(!run)return run;
  run.updated=now;
  if(event==='start'){run.outcome='working';run.finished=0;}
  else if(['response','review','stopped','error','paused'].includes(event)){run.outcome=event;run.finished=now;run.activeTool='';}
  if(run.planSource==='automatic'){
   const response=run.steps.find(s=>s.id==='response'),delivery=run.steps.find(s=>s.id==='delivery');
   if(event==='start'&&response&&delivery){response.status='working';response.started=now;response.evidence='';delivery.status='pending';delivery.evidence='';}
   if(['response','review'].includes(event)&&response&&delivery){for(const s of [response,delivery]){s.status='done';s.completed=now;s.evidence=s===delivery?'The provider returned its final response.':'The response cycle finished. Project verification is separate.';}}
  }
  return run;
 }
 function restore(value){
  if(!value||typeof value!=='object'||typeof value.id!=='string'||!/^[a-zA-Z0-9-]{8,80}$/.test(value.id)||typeof value.context!=='string'||value.context.length>4000||!Array.isArray(value.steps)||value.steps.length>24)return null;
  try{const run=create(value.title,value.context,value.id);const planned=value.steps.length?apply(run,{run_id:run.id,action:'plan',steps:value.steps.map(s=>({id:s.id,title:s.title,estimate_seconds:s.estimate_seconds}))}):run;for(const s of value.steps){if(s.status!=='pending')Object.assign(planned,apply(planned,{run_id:run.id,action:'update',step_id:s.id,status:s.status,evidence:s.evidence,blocker:s.blocker}));const step=planned.steps.find(x=>x.id===s.id);for(const key of ['started','completed'])if(step&&Number.isFinite(s[key])&&s[key]>0&&s[key]<=Date.now())step[key]=s[key];}for(const k of ['calls','errors'])planned[k]=Math.max(0,Math.min(1e9,Number(value[k])||0));for(const k of ['created','updated','finished'])if(Number.isFinite(value[k])&&value[k]>0&&value[k]<=Date.now())planned[k]=value[k];planned.planSource=value.planSource==='automatic'||!value.steps.length?'automatic':'reported';planned.outcome=['response','review','stopped','error','paused'].includes(value.outcome)?value.outcome:'paused';planned.activeTool='';planned.lastTool=clean(value.lastTool,120);planned.awaitingConversation=value.awaitingConversation===true;for(const item of (Array.isArray(value.activity)?value.activity:[]).slice(-12)){if(item&&Number.isFinite(item.at)&&item.at>0&&item.at<=Date.now())activity(planned,item,item.at);}planned.updated=Number.isFinite(value.updated)&&value.updated>0&&value.updated<=Date.now()?value.updated:planned.updated;return planned;}catch{return null;}
 }
 function apply(run,args){
  if(!run||(args.run_id!==run.id&&!(args.action==='read'&&!args.run_id)))throw Error('This report belongs to another run. Use the current run_id.');
  if(args.action==='update'&&args.updates!==undefined){
   if(!Array.isArray(args.updates)||!args.updates.length||args.updates.length>24)throw Error('Use 1–24 milestone updates.');
   if(Object.keys(UPDATE_FIELDS).some(k=>args[k]!==undefined))throw Error('Use updates or one step update, not both.');
   const ids=new Set();let next=run;
   for(const update of args.updates){if(!update||typeof update!=='object'||Array.isArray(update)||Object.keys(update).some(k=>!Object.hasOwn(UPDATE_FIELDS,k))||typeof update.step_id!=='string'||ids.has(update.step_id))throw Error('Each milestone update needs a unique step_id and valid update fields.');ids.add(update.step_id);next=apply(next,{...update,action:'update',run_id:run.id});}
   return next;
  }
  const next=JSON.parse(JSON.stringify(run));
  if(args.action==='read')return run;
  if(args.action==='plan'){
   if(!Array.isArray(args.steps)||!args.steps.length||args.steps.length>24)throw Error('Use 1–24 concrete steps.');
   const prior=run.planSource==='automatic'?[]:run.steps;
   const ids=new Set();next.steps=args.steps.map(s=>{if(!s||typeof s.id!=='string'||!/^[a-z0-9_-]{1,48}$/i.test(s.id)||ids.has(s.id)||typeof s.title!=='string'||!s.title.trim()||s.title.length>200)throw Error('Each step needs a unique short id and a title of 1–200 characters.');if(s.estimate_seconds!==undefined&&(!Number.isFinite(s.estimate_seconds)||s.estimate_seconds<1||s.estimate_seconds>7200))throw Error('Step estimates must be 1–7200 seconds.');ids.add(s.id);const old=prior.find(x=>x.id===s.id);if(old?.status==='done'&&old.title!==s.title.trim())throw Error('Reopen a verified step before changing its scope.');return {...(old||{id:s.id,status:'pending',evidence:'',blocker:''}),title:s.title.trim(),...(s.estimate_seconds!==undefined?{estimate_seconds:s.estimate_seconds}:{})};});
   if(prior.some(s=>!ids.has(s.id)))throw Error('Keep existing steps visible; do not remove unfinished scope or verification history.');next.planSource='reported';
  }else if(args.action==='update'){
   if(run.planSource==='automatic')throw Error('Response stages are tracked automatically. Report a concrete task plan before updating project steps.');
   const step=next.steps.find(s=>s.id===args.step_id);if(!step)throw Error('Plan this step before updating it.');
   if(!['pending','working','blocked','done'].includes(args.status))throw Error('Unknown step status.');
   if(['evidence','blocker'].some(k=>args[k]!==undefined&&typeof args[k]!=='string'))throw Error('Evidence and blocker must be text.');
   const evidence=clean(args.evidence,2000),blocker=clean(args.blocker,1000);
   if(args.status==='done'&&!evidence)throw Error('Verified completion needs concrete evidence.');
   if(args.status==='blocked'&&!blocker)throw Error('Describe the blocker.');
   if(args.status==='working'&&step.status!=='working')step.started=Date.now();
   if(args.status==='done'&&step.status!=='done')step.completed=Date.now();
   if(args.status!=='done')delete step.completed;
   step.status=args.status;step.evidence=args.status==='done'?evidence:'';step.blocker=args.status==='blocked'?blocker:'';
  }else throw Error('Use plan, update or read.');
  if(JSON.stringify(next)===JSON.stringify(run))return run;
  next.updated=Date.now();return next;
 }
 function summary(run,runtime={},now=Date.now()){
  const steps=run?.steps||[],done=steps.filter(s=>s.status==='done').length,blocked=steps.filter(s=>s.status==='blocked').length;
  const failed=runtime.providerFailed||run?.outcome==='error',stopped=runtime.stopped||run?.outcome==='stopped',busy=runtime.running||runtime.generating,automatic=run?.planSource==='automatic',complete=steps.length>0&&done===steps.length;
  const state=failed?'Provider error':stopped?'Stopped':blocked?'Blocked':run?.outcome==='review'?'Review results':runtime.waitingForUser?'Waiting for response selection':busy?'Working':complete?(automatic?'Response received':'Steps reported verified'):run?'Paused · work remaining':'No active task';
  const working=steps.find(s=>s.status==='working'),next=steps.find(s=>s.status!=='done');
  const stage=failed?'Recover the provider response':stopped?'Run stopped':runtime.waitingForUser?'Choose a response on the provider page':blocked?steps.find(s=>s.status==='blocked').title:run?.activeTool?'Running '+run.activeTool:busy&&runtime.generating?(automatic?'Provider is thinking or responding':working?.title||next?.title||'Provider is responding'):complete?(automatic?'Final response received':'Plan finished'):working?.title||next?.title||'Ready for your next request';
  const durations=steps.filter(s=>s.status==='done'&&s.started&&s.completed>s.started).map(s=>s.completed-s.started);
  const remaining=steps.filter(s=>s.status!=='done');let estimate=null,timingLate=false;
  if(!automatic&&busy&&!runtime.waitingForUser&&!failed&&!stopped&&!blocked&&remaining.length){const measured=durations.length>=2?durations.reduce((a,b)=>a+b,0)/durations.length:0;const reported=remaining.every(s=>s.estimate_seconds);if(reported||measured){timingLate=remaining.some(s=>s.status==='working'&&s.started&&now-s.started>(reported?s.estimate_seconds*1000:measured)*1.6);const ms=remaining.reduce((sum,s)=>sum+Math.max(5000,(reported?s.estimate_seconds*1000:measured)-(s.status==='working'&&s.started?Math.max(0,now-s.started):0)),0);if(!timingLate)estimate={lowMs:Math.min(28800000,Math.max(5000,ms*.6)),highMs:Math.min(28800000,Math.max(15000,ms*1.6)),source:reported?'AI step estimates':'Completed step timings'};}}
  return {total:steps.length,done,remaining:steps.length-done,blocked,percent:steps.length?Math.round(done/steps.length*100):null,state,stage,automatic,elapsedMs:run?Math.max(0,(busy?now:run.finished||run.updated)-run.created):0,estimate,timingLate};
 }
 function duration(ms){const sec=Math.max(0,Math.round(ms/1000));return sec<60?sec+'s':sec<3600?Math.ceil(sec/60)+' min':(sec/3600).toFixed(1)+' hr';}
 function estimateText(s){return s.estimate?`${duration(s.estimate.lowMs)}–${duration(s.estimate.highMs)} remaining`:['Provider error','Stopped','Blocked','Review results'].includes(s.state)?'Estimate paused':s.remaining===0&&s.total?'Finished':s.timingLate?'Timing changed':s.state==='Working'?(s.automatic?'Waiting for provider':'Learning task timing…'):'Estimate paused';}
 function prompt(run){return `[MULTI-SCRIPT TASK CHECKLIST]\nRun ID: ${run.id}\nProgress and tool activity are tracked locally. Begin the user's actual task directly; no progress-tool prerequisite or per-tool status calls. Keep a concise internal plan when useful. Use ms_task_progress only for a useful explicit checklist or a user-requested progress report: create one plan, reuse it, and batch meaningful milestone changes with updates. Do not reread or resend an unchanged plan, estimate timing repeatedly, or spend turns just narrating bookkeeping. Done still requires actual verification evidence; final prose and tool chips do not verify project work. Keep unfinished scope and blockers visible. Never invent a run ID or replay an older report.`;}
 function receipt(run,args,changed){
  if(args.action==='read')return {ok:true,run,summary:summary(run)};
  const s=summary(run);return {ok:true,run_id:run.id,action:args.action,changed,done:s.done,remaining:s.remaining,blocked:s.blocked,note:changed?'Saved locally. Continue the original task; no per-tool progress calls needed.':'Already current; do not repeat this update. Continue the original task.'};
 }
 function mount({root,read,runtime,phone,onOpen}){
  const dock=document.createElement('div');dock.id='ms-run-dock';dock.hidden=true;
  const panel=document.createElement('section');panel.id='ms-run-panel';panel.hidden=true;panel.setAttribute('aria-label','Multi-Script run monitor');panel.innerHTML='<header><div><small>MULTI-SCRIPT</small><h2>Run monitor</h2></div><button type="button" data-monitor-close aria-label="Close run monitor">×</button></header><nav><button type="button" data-monitor-tab="progress">Task progress</button><button type="button" data-monitor-tab="phone">Phone control</button></nav><div id="ms-progress-view"></div><div id="ms-phone-view" hidden></div>';
  // Retain the actual controls: providers can move the bar outside this root.
  root.append(dock,panel);const phoneButton=root.querySelector('#ms-phone-chip')||document.getElementById('ms-phone-chip'),taskButton=root.querySelector('#ms-task-chip')||document.getElementById('ms-task-chip');let tab='progress',last='',lastActivity='';
  function open(which){onOpen?.();tab=which;panel.hidden=false;panel.querySelector('#ms-progress-view').hidden=which!=='progress';panel.querySelector('#ms-phone-view').hidden=which!=='phone';panel.querySelectorAll('[data-monitor-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.monitorTab===which)));if(which==='phone')phone?.(panel.querySelector('#ms-phone-view'));paint();panel.querySelector(`[data-monitor-tab="${which}"]`).focus();}
  function close(){panel.hidden=true;const target=tab==='phone'?phoneButton:taskButton;(target&&!target.hidden?target:phoneButton)?.focus();}if(taskButton)taskButton.onclick=()=>open('progress');if(phoneButton)phoneButton.onclick=()=>open('phone');panel.querySelector('[data-monitor-close]').onclick=close;panel.querySelectorAll('[data-monitor-tab]').forEach(b=>b.onclick=()=>open(b.dataset.monitorTab));panel.addEventListener('keydown',e=>{if(e.key==='Escape'){close();}});
  function paintActivity(run,view){
   const key=JSON.stringify(run?.activity||[]);if(key===lastActivity)return;lastActivity=key;
   const host=view.querySelector('[data-progress-activity]');if(!host)return;
   const events=(run?.activity||[]).slice().reverse();
   host.innerHTML='<div class="ms-progress-plan-heading"><b>Recent activity</b><span>Tracked locally</span></div>'+(events.length?'<ol class="ms-progress-steps">'+events.map(e=>`<li data-activity-kind="${escape(e.kind)}"><i aria-hidden="true">${e.kind==='tool'?'✓':e.kind.includes('error')?'!':'↻'}</i><div><b>${escape(e.title)}</b><small>${escape(new Date(e.at).toLocaleTimeString())}${e.argument?' · '+escape(e.argument):''}</small>${e.detail?`<details><summary>${e.kind.includes('error')?'View error':'View activity'}</summary><p>${escape(e.detail)}</p></details>`:''}</div></li>`).join('')+'</ol>':'<p class="ms-progress-caption">Waiting for the first tool result. Thinking and final responses are tracked above; no progress-tool call is required.</p>');
  }
  function paint(){
   const run=read(),rt=runtime(),s=summary(run,rt),button=taskButton;if(button){if(button.hidden)button.hidden=false;
   const span=button.querySelector('span'),label=s.total?(s.remaining?`${s.remaining} ${s.automatic?'stages':'tasks'} left`:s.state):'Task progress',title=s.state+' · '+s.stage+(s.total?' · '+s.remaining+' remaining':'');if(span&&span.textContent!==label)span.textContent=label;if(button.dataset.state!==s.state)button.dataset.state=s.state;if(button.title!==title)button.title=title;}
   const running=String(!!(rt.running||rt.generating));if(dock.dataset.running!==running)dock.dataset.running=running;if(panel.hidden||tab!=='progress')return;
   const view=panel.querySelector('#ms-progress-view'),timeLabel=estimateText(s),timeNote=s.timingLate?'This step exceeded its estimate. Waiting for an updated timing.':s.estimate?s.estimate.source+' · rough range':s.remaining?(s.automatic?'Elapsed time is live; provider duration varies.':'A range appears after step estimates or two timed steps.'):'Elapsed '+duration(s.elapsedMs),caption=s.done+' of '+s.total+(s.automatic?' response stages finished':' tasks reported verified')+' · '+duration(s.elapsedMs)+' elapsed';
   // Tool/timer activity changes labels, not the evidence tree. Rebuild that
   // tree only for an actual plan/evidence change, preserving expanded details.
   const key=JSON.stringify([run?.id,run?.title,run?.planSource,run?.steps]);
   if(key===last){for(const [selector,text]of [['[data-progress-time]',timeLabel],['[data-progress-time-note]',timeNote],['[data-progress-counter]',caption],['.ms-monitor-state',s.state],['.ms-progress-stage b',s.stage],['[data-progress-tool-count]',`${run?.calls||0} tool results · ${run?.errors||0} errors`]]){const el=view.querySelector(selector);if(el&&el.textContent!==text)el.textContent=text;}paintActivity(run,view);return;}last=key;
   const expanded=new Set([...view.querySelectorAll('li[data-step-id]:has(details[open])')].map(el=>el.dataset.stepId));
   panel.querySelector('#ms-progress-view').innerHTML=`<div class="ms-progress-overview"><span class="ms-monitor-state" role="status">${escape(s.state)}</span><h3>${escape(run?.title||'Your next task starts here.')}</h3><p class="ms-progress-stage"><span>Current stage</span><b>${escape(s.stage)}</b></p><div class="ms-progress-metrics"><div><strong>${s.total?s.remaining:'0'}</strong><span>${s.automatic?'response stages':'tasks'} remaining</span></div><div><b data-progress-time>${escape(estimateText(s))}</b><span data-progress-time-note>${escape(timeNote)}</span></div></div>${s.total?`<progress max="${s.total}" value="${s.done}" aria-label="${s.automatic?'Response stages':'Reported verified steps'}"></progress><p class="ms-progress-caption" data-progress-counter>${s.done} of ${s.total} ${s.automatic?'response stages finished':'tasks reported verified'} · ${duration(s.elapsedMs)} elapsed</p>`:''}</div><div data-progress-activity></div><div class="ms-progress-plan-heading"><b>${s.automatic?'Response stages':'Task plan'}</b><span>${s.blocked?s.blocked+' blocked':s.total+' steps'}</span></div><ol class="ms-progress-steps">${(run?.steps||[]).map((step,i)=>`<li data-step-status="${step.status}" data-step-id="${escape(step.id)}"><i aria-hidden="true">${step.status==='done'?'✓':step.status==='blocked'?'!':String(i+1).padStart(2,'0')}</i><div><b>${escape(step.title)}</b><small>${escape(({pending:'Up next',working:'In progress',blocked:'Needs attention',done:s.automatic?'Finished':'Reported verified'})[step.status])}</small>${step.evidence?`<details><summary>View evidence</summary><p>${escape(step.evidence)}</p></details>`:''}${step.blocker?`<p class="ms-step-blocker">${escape(step.blocker)}</p>`:''}</div></li>`).join('')}</ol><p class="ms-monitor-note">${s.automatic?'These stages track the response automatically. An optional checklist records project steps; verification still needs evidence.':'Verified steps need reported evidence. Time ranges adjust as work changes and pause when work stops.'}</p><p class="ms-progress-caption" data-progress-tool-count>${run?.calls||0} tool results · ${run?.errors||0} errors</p>`;lastActivity='';paintActivity(run,view);
   for(const el of view.querySelectorAll('li[data-step-id]'))if(expanded.has(el.dataset.stepId)){const details=el.querySelector('details');if(details)details.open=true;}
  }
  return {paint,open,panel,dock,destroy(){dock.remove();panel.remove();}};
 }
 const api={TOOL,create,apply,summary,prompt,receipt,mount,restore,observe,activity,duration,estimateText};g.MSProgress=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
