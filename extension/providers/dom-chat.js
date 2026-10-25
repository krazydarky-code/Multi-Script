// SPDX-License-Identifier: GPL-3.0-or-later
// Shared DOM transport. Explicit roles only: never interpret arbitrary page text
// or a human team-channel message as an assistant command.
const MSDomChat = (() => {
  "use strict";
  function create(c) {
    const own="#zs-root,#rs-root,#zs-input-cover";
    const nativeHidden='[hidden],[inert],[aria-hidden="true"]';
    const availableTurn=e=>{
      if(!e?.isConnected||e.closest(nativeHidden+','+own))return false;
      for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||['hidden','collapse'].includes(s.visibility))return false;}
      return true;
    };
    const visible=e=>!!e?.isConnected && e.getClientRects().length>0 && !e.closest(nativeHidden+','+own) && !['hidden','collapse'].includes(getComputedStyle(e).visibility);
    const sleep=ms=>new Promise(r=>setTimeout(r,ms));
    const normalizeDraft=t=>String(t).replace(/\r\n?/g,'\n').replace(/\u00a0/g,' ').trimEnd();
    let diag=()=>{},locked=false,internalSend=false;
    const lockState=new WeakMap();
    const scope=()=>{
      if(!c.scope)return document;
      const roots=[...(typeof c.scope==='function'?c.scope():document.querySelectorAll(c.scope))].filter(e=>visible(e)&&!e.closest('[inert],[aria-hidden="true"]')&&(!c.ignoreRoots||!e.closest(c.ignoreRoots)));
      // ClickUp keeps empty AI panels mounted beside its active conversation.
      // Prefer a private scope with a usable composer; retain the known reply
      // scope when the native editor is temporarily absent during generation.
      const active=c.preferComposerScope?roots.filter(root=>[...root.querySelectorAll(c.editor)].some(e=>visible(e)&&!e.closest(c.turns)&&(!c.ignoreRoots||!e.closest(c.ignoreRoots)))):[];
      return active.at(-1)||roots.at(-1)||null;
    };
    const query=(sel)=>[...(scope()?.querySelectorAll(sel)||[])].filter(e=>!e.closest(own)&&(!c.ignoreRoots||!e.closest(c.ignoreRoots)));
    function getEditor(){
      const candidates=query(c.editor).filter(visible).filter(e=>{
        if(e.closest(c.turns))return false;
        // Known composers and explicitly private AI scopes can themselves be
        // hosted in a native dialog/sidebar. Reject only unrelated fallback fields.
        const known=c.scope||e.matches(c.preferredEditor||'textarea[name="prompt-textarea"]');
        return known||!e.closest('dialog,[role="dialog"],aside,nav,[role="search"]');
      });
      const preferred=c.preferredEditor&&candidates.filter(e=>e.matches(c.preferredEditor));return (preferred?.length?preferred:candidates).at(-1)||null;
    }
    const editorText=()=>{const e=getEditor();return e?(typeof ZS!=='undefined'&&ZS.readComposer?ZS.readComposer(e):e.tagName==="TEXTAREA"?e.value:e.innerText||e.textContent||""):"";};
    const composerFrame=()=>getEditor()?.closest("form,[data-testid='chat-composer'],[data-testid='composer'],[data-ms-ai-composer]")||getEditor()?.parentElement||null;
    const isUserItem=e=>!!e?.matches(c.user);
    const isAssistantItem=e=>!!e?.matches(c.assistant);
    function allItems(){
      const items=query(c.turns).filter(availableTurn).filter(e=>isUserItem(e)||isAssistantItem(e)),set=new Set(items);
      // Keep outermost native turns without comparing every pair in the history.
      // No cache: token edits, recycled nodes and native generation signals are
      // read from the current DOM on every call.
      return items.filter(e=>{for(let p=e.parentElement;p;p=p.parentElement)if(set.has(p))return false;return true;});
    }
    const assistants=()=>allItems().filter(isAssistantItem);
    const lastAssistant=()=>assistants().at(-1)||null;
    const assistantCount=()=>assistants().length,userCount=()=>allItems().filter(isUserItem).length;
    function itemText(item,exclude="") {
      if(!item)return "";
      // Native tool results and reasoning are not local command replies.
      const roots=answerRoots(item);
      return roots.map(answer=>{
      const node=answer.cloneNode(true);
      // Hidden source remains the parser's source of truth after chip masking.
      // Reading innerText would also lose CSS-hidden command blocks.
      node.querySelectorAll([".zs-chip","button","[role='toolbar']",nativeHidden,c.thinking,c.exclude,c.ignoreRoots,exclude].filter(Boolean).join(",")).forEach(x=>x.remove());
      const blocks=[...node.querySelectorAll("pre code")];for(const b of blocks)b.textContent=b.textContent;
      node.querySelectorAll('br').forEach(e=>e.replaceWith('\n'));
      node.querySelectorAll('p,pre,li,h1,h2,h3,h4').forEach(e=>e.append('\n'));
      return (node.textContent||"").trim();
      }).filter(Boolean).join("\n");
    }
    function answerRoots(item){
      if(!item)return [];
      if(!c.reply||!isAssistantItem(item))return [item];
      const roots=typeof c.reply==="function"?c.reply(item):[...item.querySelectorAll(c.reply)];
      const list=Array.isArray(roots)?roots:roots?[roots]:[];
      return list.filter(e=>!e.closest(nativeHidden+','+(c.thinking||'[data-ms-thinking]'))).filter(e=>!list.some(p=>p!==e&&p.contains(e)));
    }
    const thinkingOf=item=>item?.querySelector(c.thinking||"[data-ms-thinking]")?.textContent||"";
    const thinkingText=()=>thinkingOf(lastAssistant());
    function itemKey(e){const owner=e?.closest('[data-message-id],[data-turn-id],[data-id]');return owner?.getAttribute("data-message-id")||owner?.getAttribute("data-turn-id")||owner?.getAttribute("data-id")||e?.closest("[data-chat-turn-anchor]")?.getAttribute("data-chat-turn-anchor")?.replace(/^true$/,"")||e?.id||null;}
    const lastAssistantId=()=>itemKey(lastAssistant())||lastAssistant()||null;
    const readAssistant=()=>{const item=lastAssistant();return {present:!!item,reply:itemText(item),thinking:thinkingOf(item),item};};
    const snapshot=()=>{const item=lastAssistant();return {th:thinkingOf(item).length,rp:itemText(item).length};};
    const streamLen=()=>{const item=lastAssistant();return itemText(item).length+thinkingOf(item).length;};
    const button=(sel)=>query(sel).find(visible)||null;
    const sendButton=()=>{const f=composerFrame();if(!f)return null;return [...f.querySelectorAll(c.send)].find(visible)||null;};
    // Historical turns can retain a Stop control or a busy native tool card.
    // Only the current answer, composer and unowned site chrome are active.
    const currentSurface=(e,last,frame)=>{const turn=e.closest(c.turns);return !turn||turn===last||last?.contains(turn)||frame?.contains(e);};
    const stopButton=(last=lastAssistant(),frame=composerFrame())=>query(c.stop).find(e=>currentSurface(e,last,frame)&&visible(e))||(c.stopText?query('button').find(e=>c.stopText.test((e.getAttribute('aria-label')||e.textContent||'').trim())&&currentSurface(e,last,frame)&&visible(e)):null);
    const isGenerating=()=>{const last=lastAssistant(),frame=composerFrame();return !!stopButton(last,frame)||!!(c.generating&&query(c.generating).some(e=>currentSurface(e,last,frame)&&visible(e)))||query("[data-is-streaming='true'],[data-state='streaming'],[data-status='generating'],[aria-busy='true']").some(e=>(last?.contains(e)||e===last||frame?.contains(e))&&visible(e));};
    async function waitForSendReady({timeout=180000,cancelled=()=>false}={}) {
      const end=Date.now()+timeout;let idleAt=0,lastReply=null;
      while(Date.now()<end){if(cancelled())return false;const text=itemText(lastAssistant()),busy=isGenerating();
        if(busy||text!==lastReply){idleAt=0;lastReply=text;}else if(!idleAt)idleAt=Date.now();
        if(!busy&&idleAt&&Date.now()-idleAt>=(c.quietMs??(c.id==='vani'?2500:350)))return true;
        await sleep(150);
      }
      const error=Error(c.name+' is still answering. Nothing else was sent; wait for the native response to finish.');error.retryable=false;error.sendState='not-sent';throw error;
    }
    const chatIsEmpty=()=>!query(c.turns).some(e=>isUserItem(e)||isAssistantItem(e));
    const isFreshChat=()=>chatIsEmpty()&&!!getEditor();
    function modeWarning(){if(c.path&&!c.path.test(location.pathname))return c.openHint; if(c.scope&&!scope())return c.openHint;return "";}
    function setInputLock(on){locked=!!on;const e=getEditor();if(!e)return;if(on&&!lockState.has(e))lockState.set(e,{readOnly:e.readOnly,editable:e.getAttribute("contenteditable")});const saved=lockState.get(e);if(e.tagName==="TEXTAREA")e.readOnly=on?true:(saved?.readOnly??e.readOnly);else if(on)e.setAttribute("contenteditable","false");else if(saved){if(saved.editable===null)e.removeAttribute("contenteditable");else e.setAttribute("contenteditable",saved.editable);}e.toggleAttribute("data-zs-locked",on);if(!on)lockState.delete(e);}
    async function setText(text){const e=getEditor();if(!e)throw Error(c.name+": chat composer not found. "+c.openHint);e.focus();if(e.tagName==="TEXTAREA"){Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set.call(e,text);e.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText",data:text}));}else{e.setAttribute("contenteditable","true");const s=getSelection(),r=document.createRange();r.selectNodeContents(e);s.removeAllRanges();s.addRange(r);document.execCommand("insertText",false,text);e.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText",data:text}));if(locked)e.setAttribute("contenteditable","false");}await sleep(100);if(normalizeDraft(editorText())!==normalizeDraft(text))throw Error(c.name+": the composer did not preserve the message; nothing sent.");}
    async function attachImages(images){if(!images?.length)return true;const input=composerFrame()?.querySelector('input[type="file"]');if(!input)throw Error(c.name+": no image upload input in this composer. The tool result was not attached.");const dt=new DataTransfer();for(const [i,img]of images.entries()){const b=atob(img.data||img.base64||"");dt.items.add(new File([Uint8Array.from(b,x=>x.charCodeAt(0))],"multiscript-capture-"+i+".png",{type:img.mimeType||"image/png"}));}input.files=dt.files;input.dispatchEvent(new Event("change",{bubbles:true}));await sleep(600);return true;}
    let sending=false;
    async function typeAndSend(text,images,controls={}){
      const failure=(message,state='not-sent')=>Object.assign(Error(c.name+': '+message),{retryable:false,sendState:state});
      if(sending)throw failure('a send is already pending.');
      sending=true;let clicked=false;
      let originalEditor=getEditor();const originalContext=conversationKey(),originalFrame=composerFrame();
      const check=()=>{
        if(controls.cancelled?.())throw failure('send cancelled.',clicked?'unconfirmed':'not-sent');
        if(!clicked&&conversationKey()!==originalContext)throw failure('target changed: chat replaced. Nothing sent.');
        if(!clicked&&getEditor()!==originalEditor){
          const next=getEditor(),normalize=normalizeDraft;
          if(originalEditor&&!originalEditor.isConnected&&next&&originalFrame?.isConnected&&originalFrame.contains(next)&&normalize(editorText())===normalize(text))originalEditor=next;
          else throw failure('target changed: composer replaced. Draft preserved; nothing sent.');
        }
      };
      try{
        check();if(modeWarning())throw failure(modeWarning());
        if(isGenerating())throw failure('the provider is still generating.');
        await attachImages(images);check();await setText(text);check();
        let b=null;
        for(let i=0;i<40;i++){check();if(isGenerating())throw failure('resumed answering before Send. Draft preserved; nothing sent.');b=sendButton();if(b&&!b.disabled&&b.getAttribute('aria-disabled')!=='true')break;await sleep(100);}
        if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')throw failure('send button unavailable; draft preserved.');
        check();if(normalizeDraft(editorText())!==normalizeDraft(text))throw failure('the complete draft changed before Send. Nothing sent.');const before=userCount();internalSend=true;clicked=true;
        try{b.click();}finally{internalSend=false;}
        for(let i=0;i<50;i++){
          if((getEditor()===originalEditor&&!editorText().trim())||userCount()>before){diag('provider.sent',{provider:c.id,chars:text.length});return true;}
          check();await sleep(100);
        }
        throw failure('Send was clicked but acknowledgement is uncertain. Automatic replay stopped; check the conversation before retrying.','unconfirmed');
      }catch(error){if(error.sendState)throw error;throw failure(error.message||String(error),clicked?'unconfirmed':'not-sent');}
      finally{sending=false;}
    }
    const stopGeneration=()=>stopButton()?.click();
    async function ensureComposerReady(reason){
      let warning=modeWarning()||(!getEditor()?c.openHint:"");
      if(!warning&&c.prepareComposer)warning=await c.prepareComposer(reason,{editor:getEditor(),frame:composerFrame(),visible,sleep})||"";
      return {ready:!!getEditor()&&!warning,warning};
    }
    const enforceComposer=()=>{if(locked)setInputLock(true);return {ready:!!getEditor()&&!modeWarning()};};
    const scopeKeys=new WeakMap();let scopeSeq=0;
    const conversationKey=()=>{const root=scope();const key=c.contextAttributes?.map(k=>root?.getAttribute?.(k)).find(Boolean);if(c.contextAttributes&&root&&!key&&!scopeKeys.has(root))scopeKeys.set(root,++scopeSeq);return location.pathname+location.search+(c.contextAttributes?"|"+(key||scopeKeys.get(root)||"no-private-ai"):"");};
    function scanError(){return query("[role='alert'],[data-testid='chat-error']").filter(visible).filter(e=>!e.closest(c.turns)&&!(c.busyNotice&&c.busyNotice.test(e.textContent||''))).map(x=>x.textContent).join("\n").slice(0,2000);}
    function responseError(){const item=lastAssistant();return c.nativeError&&item?.matches(c.nativeError)?{text:itemText(item).slice(0,1000)||c.name+" marked the response as failed."}:null;}
    const isTooLongMsg=t=>/context.{0,20}(limit|exceed)|message.{0,20}too long|too many tokens/i.test(t||"");
    const isBusyMsg=t=>/rate.?limit(?:ed| exceeded| reached)|too many requests|try again later|temporarily unavailable|quota (?:exceeded|reached)/i.test(t||"");
    function installSendHooks(h){
      document.addEventListener("keydown",e=>{if(internalSend)return;if(e.key!=="Enter"||e.shiftKey||e.isComposing||!getEditor()?.contains(e.target)&&e.target!==getEditor())return;if(h.isBlocked()){e.preventDefault();e.stopImmediatePropagation();h.onBlockedAttempt?.();return;}if(h.isStarted())h.onUserMessage(assistantCount());},true);
      document.addEventListener("click",e=>{if(internalSend)return;const b=e.target.closest("button");if(!b)return;if(b===stopButton()){h.onNativeStop?.();return;}if(b!==sendButton()||b.disabled)return;if(h.isBlocked()){e.preventDefault();e.stopImmediatePropagation();h.onBlockedAttempt?.();return;}if(h.isStarted())h.onUserMessage(assistantCount());},true);
    }
    function findToolBlockSpot(item){
      if(!item)return null;
      if(typeof ZSParse!=="undefined")for(const root of answerRoots(item)){
        const blocks=[...root.querySelectorAll('pre,p')].filter(e=>!e.closest('.zs-chip')&&!e.closest(c.thinking||'[data-ms-thinking]'));
        for(const block of blocks){const text=block.textContent.trim();if(ZSParse.parseToolCalls(text).length&&/^(?:```\w*\s*)?\{/.test(text))block.classList.add('zs-tool-hide');}
      }
      return {parent:answerRoots(item)[0]||item,ref:null};
    }
    const selfTest=()=>({ready:!!getEditor()&&!!sendButton()&&!modeWarning(),provider:c.id,composer:!!getEditor(),send:!!sendButton(),userTurns:userCount(),assistantTurns:assistantCount(),warning:modeWarning(),verification:c.verification,selectors:{editor:c.editor,user:c.user,assistant:c.assistant}});
    return {id:c.id,displayName:c.name,get supportsVision(){return typeof c.vision==="function"?!!c.vision():!!c.vision;},persistentBarWhenNoEditor:!!c.persistentBarWhenNoEditor,strictGeneration:true,reusesTurnNodes:true,waitForSendReady,reliableCounts:false,chipAtItemLevel:true,chipAppend:true,
      timings:{GEN_IDLE_MS:2000,REASON_IDLE_MS:25000,WARMUP_MS:60000,REASON_NOREPLY_MS:180000,STABLE_MS:6000,RESPONSE_TIMEOUT_MS:420000},
      minSendGapMs:2500,resultCharBudget:9000,resultLineBudget:350,sendCharBudget:50000,
      promptExtra:"Multi-Script local tools use ONE plain-text JSON command per reply: {\"command\":\"exact_name\",\"params\":{}}. The extension executes it and returns the result in the next turn. Continue for as many turns as the task requires. Native provider tools run elsewhere and do not access the local workspace. Native per-response tool-call counts do not count these plain-text command exchanges. Never bypass provider quotas or claim a backend model you cannot verify.",
      init({diag:d}={}){if(d)diag=d;},thinkingSel:c.thinking||"[data-ms-thinking]",allItems,isUserItem,isAssistantItem,itemText,classifyText:itemText,assistantCount,userCount,lastAssistant,itemKey,lastAssistantId,readAssistant,snapshot,streamLen,
      getEditor,editorText,composerFrame,barAnchor:composerFrame,setInputLock,typeAndSend,attachImages,clearAttachments(){},stopGeneration,isGenerating,isHardGenerating:isGenerating,isBusyNow:isGenerating,chatIsEmpty,isFreshChat,
      enforceComposer,ensureComposerReady,modeWarning,conversationKey,scanError,responseError,isTooLongMsg,isBusyMsg,installSendHooks,findToolBlockSpot,selfTest,
      chipAnchor:item=>answerRoots(item)[0]||item,
      turnHalted:()=>false,findContinueBtn:()=>null,clickContinueBtn:()=>false,captchaPresent:()=>!!button("iframe[src*='captcha'],[data-testid='captcha']"),overlayBlocking:()=>false};
  }
  return {create};
})();
