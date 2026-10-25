// Multi-Script's local workspace panel uses the extension's existing, context-
// checked provider sessions. It does not embed or impersonate a provider chat.
export function mountAssistant(){
  const dock=document.createElement('section');dock.id='ms-assistant-dock';dock.setAttribute('aria-label','Multi-Script controls');
  dock.innerHTML=`<div class="assistant-head"><b>✦ Multi-Script</b><span id="assistant-status" role="status">Connecting AI chats…</span><button id="assistant-toggle" aria-label="Expand Multi-Script controls" aria-expanded="false">⌃</button></div><div id="assistant-body" hidden><label for="assistant-session">AI chat</label><select id="assistant-session"><option value="">Choose an open provider chat</option></select><p id="assistant-detail" class="muted"></p><div class="row"><button id="assistant-chat">Open AI chat</button><button id="assistant-settings">Settings</button><button id="assistant-stop">Stop run</button></div><ol id="assistant-plan"></ol><label for="assistant-text">Follow-up for this chat</label><textarea id="assistant-text" maxlength="4000" rows="2" placeholder="Add a request to the next tool result…"></textarea><div class="row"><button id="assistant-queue" class="primary">Queue follow-up</button><button id="assistant-refresh">Refresh chats</button></div><p id="assistant-notice" class="muted" role="status">Start the Blender agent in your AI chat. Return here to view progress and queue follow-ups.</p></div>`;
  document.body.append(dock);
  const $=id=>dock.querySelector('#assistant-'+id),pending=new Map();let serial=0,participants=[],selected=null,refreshing=false,acting=false,bridge=null;
  function request(action,extra={}){return new Promise((resolve,reject)=>{
    const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error('Open this workspace from the Multi-Script bar or extension popup. Reload the extension after updating.'));},action==='list'?7000:40000);
    pending.set(id,{resolve,reject,timer});window.postMessage({type:'ms-blender-request',id,action,...extra},location.origin);
  });}
  window.addEventListener('message',event=>{
    const m=event.data;if(event.source!==window||event.origin!==location.origin||m?.type!=='ms-blender-reply')return;
    const entry=pending.get(m.id);if(!entry)return;clearTimeout(entry.timer);pending.delete(m.id);
    if(m.result?.ok)entry.resolve(m.result);else entry.reject(Error(m.result?.error||'The selected chat could not confirm this action. Inspect it before retrying.'));
  });
  function paint(){
    selected=participants.find(p=>String(p.tabId)===$('session').value)||null;
    window.dispatchEvent(new CustomEvent('ms-blender-session',{detail:{session:selected,bridge}}));
    $('status').textContent=!selected?'Choose an AI chat':!selected.ok?'Chat needs reload':selected.starting?'Starting AI session…':selected.sendUnconfirmed?'Check unconfirmed send':selected.running||selected.generating?'AI is working':selected.started?'AI chat ready':'Start in AI chat';
    $('detail').textContent=selected?selected.ok?`${selected.name||selected.host} · ${selected.mode||'No session'}${selected.queuePending?' · '+selected.queuePending+' queued':''}${selected.hasDraft?' · draft protected':''}`:selected.error:'Open a supported provider tab with Multi-Script enabled.';
    for(const key of ['chat','settings','stop'])$(key).disabled=acting||!selected?.ok;
    $('stop').disabled=acting||!selected?.ok||!(selected.running||selected.generating||selected.starting);
    $('queue').disabled=acting||!selected?.ok||!selected.started||selected.starting||selected.sendUnconfirmed;
    const plan=$('plan');plan.replaceChildren();
    for(const step of (selected?.progress?.steps||[]).slice(0,24)){const li=document.createElement('li');li.textContent=(step.status==='done'?'✓ ':step.status==='working'?'◌ ':'○ ')+step.title;li.dataset.state=step.status;plan.append(li);}
    if(!plan.children.length){const li=document.createElement('li');li.textContent=selected?.running||selected?.generating?'Waiting for the AI’s task plan.':'Task steps appear when the AI reports a plan.';plan.append(li);}
  }
  async function refresh(){
    if(refreshing||acting)return;refreshing=true;
    try{const r=await request('list'),keep=$('session').value;bridge=r.bridge;participants=r.participants||[];const options=participants.map(p=>new Option(`${p.name||p.host} · ${p.title||'Chat'}`,p.tabId));$('session').replaceChildren(new Option('Choose an open provider chat',''),...options);$('session').value=participants.some(p=>String(p.tabId)===keep)?keep:participants.some(p=>p.tabId===r.sourceTabId)?String(r.sourceTabId):participants.length===1?String(participants[0].tabId):'';paint();}
    catch(e){$('status').textContent='AI chat link unavailable';$('notice').textContent=e.message;participants=[];paint();$('status').textContent='AI chat link unavailable';}
    finally{refreshing=false;}
  }
  async function act(action){
    if(acting||!selected?.ok)return;acting=true;paint();
    const text=$('text').value;
    try{
      if(action==='followup'&&!text.trim())throw Error('Write a follow-up before queuing it.');
      const r=await request(action,{tabId:selected.tabId,context:selected.context,requestId:crypto.randomUUID(),...(action==='followup'?{text}:{} )});
      if(action==='followup'&&r.queued){$('text').value='';$('notice').textContent='Queued for the next tool-result boundary. Open the AI chat to send a new task while it is idle.';}
      else $('notice').textContent=action==='stop'?'Stop requested. Check the provider response before continuing.':'Opened the selected AI chat.';
    }catch(e){$('notice').textContent=e.message;}
    finally{acting=false;paint();}
  }
  $('toggle').onclick=()=>{const open=$('body').hidden;$('body').hidden=!open;$('toggle').setAttribute('aria-expanded',String(open));$('toggle').setAttribute('aria-label',(open?'Collapse':'Expand')+' Multi-Script controls');$('toggle').textContent=open?'⌄':'⌃';if(open)void refresh();};
  $('session').onchange=paint;$('chat').onclick=()=>void act('focus');$('settings').onclick=()=>void act('settings');$('stop').onclick=()=>void act('stop');$('queue').onclick=()=>void act('followup');$('refresh').onclick=()=>void refresh();
  paint();void refresh();setInterval(()=>{if(!document.hidden)void refresh();},5000);
}
