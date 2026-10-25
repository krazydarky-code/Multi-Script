const assert=require('assert'),s=require('../extension/core/studio-workflows');
const skill=(id,extra={})=>s.validateSkill({id,name:id,engine:'general',instructions:'Inspect the actual project, adapt the implementation and verify the complete result with actual tools.',...extra});
(async()=>{
 const all=[skill('global-method'),skill('this-project',{scope:'chat:a'}),skill('other-project',{scope:'chat:b'}),skill('roblox-method',{engine:'roblox'}),skill('disabled-method',{enabled:false})];
 assert.deepStrictEqual(s.selectSkills(all,{scope:'chat:a',engines:['roblox']}).map(x=>x.id),['global-method','this-project','roblox-method']);
 assert.deepStrictEqual(s.selectSkills(all,{scope:'chat:b',engines:['workspace']}).map(x=>x.id),['global-method','other-project']);
 assert(!s.installedSkillsPrompt(all).includes('disabled-method'));
 assert(s.installedSkillsPrompt([skill('candidate-method')]).includes('candidate; validate'));
 assert(s.installedSkillsPrompt([skill('verified-method',{confirmed:true})]).includes('user verified'));
 const md=s.importSkill('---\nname: Cobalt controls\ndescription: Keyboard workflow\n---\n# Method\nInspect the existing controls. Preserve gamepad navigation, implement the intended change, then verify focus and clipping.');
 assert.strictEqual(md.name,'Cobalt controls');assert.strictEqual(md.description,'Keyboard workflow');assert(!md.instructions.includes('---'));
 assert.strictEqual(s.importSkill(JSON.stringify({skill:md})).id,md.id);assert.throws(()=>s.importSkill('[{}]'));assert.throws(()=>s.importSkill('{broken}'));assert.throws(()=>s.importSkill('x'.repeat(32001)));
 const adapted=s.adaptSkill({id:'roblox-inventory',name:'Inventory',engine:'roblox',steps:['Inspect GUI','Implement inputs'],executionWorkflow:{inspect:'project',execute:'build',verify:'playtest'}});
 assert(adapted.id.startsWith('project-roblox-inventory'));assert.notStrictEqual(s.adaptSkill({id:'ui',name:'UI'},'project-a').id,s.adaptSkill({id:'ui',name:'UI'},'project-b').id);assert(adapted.instructions.includes('Full source workflow: roblox-inventory'));assert(adapted.instructions.includes('playtest'));
 assert.notStrictEqual(adapted.id,s.adaptSkill({id:'roblox-inventory-other',name:'Other'}).id);
 const ultra=s.taskAddon('Build a game HUD','ultra',{enabled:false},{skills:[md]});assert(ultra.includes('DELIVERY CONTRACT')&&ultra.includes('candidate; validate')&&ultra.includes('Cobalt controls'));assert(!ultra.includes('CRITIC ·'));
 assert(!s.taskAddon('Build a HUD','deep',{enabled:false},{skills:[]}).includes('DELIVERY CONTRACT'));
 assert.strictEqual(s.executionBrief('Fix a crash').stages.length,4);assert(s.executionBrief('Build a HUD').stages[1].check.includes('2–3'));assert(!s.executionBrief('Fix a crash').stages[1].check.includes('2–3'));
 let context='a',delivered=[];const q=s.createCoworkQueue({context:()=>context,ready:()=>true,send:async text=>{delivered.push(text);return 1;},initial:{enabled:true}});
 const a=q.enqueue('Old scope','correction').id,b=q.enqueue('New goal','goal').id;assert(q.edit(a,'Keep the existing controls','correction').ok);assert(q.move(b,-1).ok);assert.strictEqual(q.snapshot().pending[0].id,b);
 context='b';assert(!q.edit(a,'Wrong chat').ok);assert(!q.move(b,1).ok);context='a';assert(!q.edit(a,'x'.repeat(16001)).ok);
 let release;const inflight=q.withFeedback('Actual result',text=>new Promise(r=>{delivered.push(text);release=r;}));assert(!q.edit(a,'Late edit').ok);assert(!q.move(a,-1).ok);release(3);await inflight;
 assert(delivered[0].includes('[Additional goal] New goal'));assert(delivered[0].includes('[Correction] Keep the existing controls'));assert(q.snapshot().history.every(x=>x.sentAt&&x.status==='sent'));
 q.enqueue('Another goal','goal');await q.take();assert(delivered[1].includes('preserve unfinished goals'));
 const state=s.newGame();s.stepGame(state,1000,true,()=>.5);assert(state.time<=.04);state.pipes=[{x:90,gap:80,height:140,scored:false}];state.y=150;state.vy=0;s.stepGame(state,0,false);assert(!state.over);state.pipes[0].x=50;s.stepGame(state,0,false);assert.strictEqual(state.score,2);assert.strictEqual(state.perfect,1);s.stepGame(state,0,false);assert.strictEqual(state.score,2);
 const hit=s.newGame();hit.pipes=[{x:90,gap:180,height:105}];s.stepGame(hit,0,false);assert(hit.over);const dead=JSON.stringify(hit);s.stepGame(hit,.04,true);assert.strictEqual(JSON.stringify(hit),dead);
 for(const mode of ['arcade','practice']){const st=s.newGame(mode);for(let i=0;i<3000;i++){st.y=150;st.vy=0;s.stepGame(st,.02,false,()=>.5);if(st.over)break;assert(st.pipes.length<10);}}
 console.log('PASS project/engine-scoped skills, disabled methods, verified/candidate prompts, Markdown/JSON import, library adaptation, Ultra contract, queue edit/reorder/context/receipt integrity and deterministic Flight scoring/collisions.');
})().catch(e=>{console.error(e.stack);process.exit(1)});
