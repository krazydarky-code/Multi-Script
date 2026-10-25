const assert=require('assert'),h=require('../tools/studio_harness'),{html,entries}=require('./support/provider-fixtures');
(async()=>{const x=await h.open({provider:'providers/arena.js',url:entries.arena.url,html:html('arena','<p>Live answer</p>'),stateHook:true,bridge:'up'});assert(x);try{const p=x.page;
 const r=await p.evaluate(()=>{
  const list=document.querySelector('ol'),last=ZSProvider.lastAssistant();for(let i=0;i<400;i++){const e=document.createElement('div');e.className='mx-auto';e.innerHTML='<div class="prose"><pre>'+Array.from({length:20},(_,j)=>'<span>Historical '+j+'</span>').join('')+'</pre></div>';list.append(e);}
  const prose=last.querySelector('.prose');prose.innerHTML='<pre>'+Array.from({length:3000},(_,i)=>'<span>token'+i+' </span>').join('')+'</pre>';
  const expected=ZSProvider.readAssistant().reply;ZSProvider.getEditor();let wildcards=0,historyQueries=0;const query=Document.prototype.querySelectorAll,element=Element.prototype.querySelector;
  Document.prototype.querySelectorAll=function(s){if(s==='*')wildcards++;return query.call(this,s)};Element.prototype.querySelector=function(s){if(s==='.prose'&&this!==last)historyQueries++;return element.call(this,s)};
  for(let i=0;i<100;i++){if(ZSProvider.readAssistant().reply!==expected)throw Error('Inconsistent cached reply');ZSProvider.getEditor();ZSProvider.isGenerating();}
  Document.prototype.querySelectorAll=query;Element.prototype.querySelector=element;
  const native=prose.querySelector('span');native.firstChild.data='Newest live token ';const fresh=ZSProvider.readAssistant().reply;const chip=document.createElement('div');chip.className='zs-chip';chip.textContent='Never part of model text';prose.append(chip);const masked=ZSProvider.readAssistant().reply;chip.textContent='Updated chip';const stillMasked=ZSProvider.readAssistant().reply;
  const host=document.createElement('fixture-chat');document.body.append(host);const shadow=host.attachShadow({mode:'open'});shadow.innerHTML='<form><textarea aria-label="message"></textarea></form>';const old=document.querySelector('form');old.remove();const shadowFound=ZSProvider.getEditor()===shadow.querySelector('textarea');
  return{wildcards,historyQueries,fresh:fresh.slice(0,30),masked:masked.includes('Never part'),same:masked===stillMasked,shadowFound};
 });
 assert.strictEqual(r.wildcards,0,'No repeated universal document scan during streaming');assert.strictEqual(r.historyQueries,0,'Live reads do not query historical markdown');assert(r.fresh.startsWith('Newest live token'));assert(!r.masked&&r.same&&r.shadowFound);assert.deepStrictEqual(x.errors,[]);console.log('PASS Arena 400-turn/3000-span stream: 100 reads with no full-document shadow scans or historical prose lookup; native token edits, excluded chips and new shadow composers remain current.');
 }finally{await x.close();}})().catch(e=>{console.error(e.stack);process.exitCode=1;});
