// Actual shipped manual/skill routing with deterministic provider surfaces.
const assert=require('assert'),fs=require('fs'),path=require('path'),cp=require('child_process'),h=require('../tools/studio_harness');
const manuals=require('../extension/core/ultra-manuals'),craft=require('../extension/core/ultra-craft'),book=require('../extension/core/ultra-handbook'),production=require('../extension/core/roblox-production');
const before=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/ultra-before-6493.json'),'utf8'));
assert.deepStrictEqual(Object.keys(craft.styles),Object.keys(before.coreStyles));for(const [key,text]of Object.entries(before.coreStyles))assert(craft.styles[key].startsWith(text));
assert.strictEqual(manuals.manuals.length,12);assert.deepStrictEqual(manuals.TOOL.inputSchema.properties.action.enum,['list','read'],'No parallel tools or method types');
assert(manuals.select('Create a blocky deer pet model').some(x=>x.id==='ultramodelling'));
assert(manuals.select('Improve the studded village trees and interior').some(x=>x.id==='ultraworld'));
assert(manuals.select('Improve daily rewards and item cards').some(x=>x.id==='ultragui'));
assert.strictEqual(Object.keys(production.pack.themes).length,9);
for(const m of manuals.manuals)for(const engine of Object.keys(craft.engines)){
 const value=manuals.read({action:'read',id:m.id,engine});assert.deepStrictEqual(value.handbook.phaseChecklists,book.pack.manuals[m.id].phases);
 assert(JSON.stringify(value).length<50000,m.id+' full manual still fits the supported text transport budget');
}
const rpc=data=>{const r=cp.spawnSync(process.env.MS_TEST_PYTHON||'python',['-X','utf8',path.join(__dirname,'runtime_fixture_rpc.py')],{input:JSON.stringify(data),encoding:'utf8',cwd:path.resolve(__dirname,'..')});assert.strictEqual(r.status,0,r.stderr);return JSON.parse(r.stdout);};
(async()=>{const calls=[],tools=rpc({action:'catalog'});const x=await h.open({stateHook:true,bridge:'up',tools,storage:{zsSetupSeen:true,msExecutionEffort:'ultra'},toolHandler:async message=>{calls.push(message);return {ok:true,...rpc({name:message.name,arguments:message.arguments})};}});assert(x);try{
 const p=x.page;const initial=await p.evaluate(()=>__qa.startupPrompt());assert(!initial.includes('multi-script-ultra-handbook-6493')&&!initial.includes('stable item IDs')&&!initial.includes('referenceStudies'),'Expansion stays out of startup');
 const result=await p.evaluate(()=>__qa.runTool({tool:'ms_ultra_manual',arguments:{action:'read',id:'ultragui',engine:'roblox',section:'build'}}));assert(!result.startsWith('ERROR'),result);const expanded=JSON.parse(result.slice(result.indexOf('\n')+1));assert(expanded.handbook.phaseChecklists.build.some(x=>x.includes('rarity')));assert(expanded.engineSpecialist.build.includes('UIStroke'));assert(expanded.engineSpecialist.fullReference.skill_id==='roblox-studio-gui-composition');assert(!expanded.handbook.phaseChecklists.design,'Phase retrieval remains scoped');
 const answer=await p.evaluate(()=>__qa.runTool({tool:'ms_get_skill',arguments:{skill_id:'roblox-studio-gui-composition',objective:'Improve the existing cartoon shop and inventory'}}));assert(!answer.startsWith('ERROR'),answer);const skill=JSON.parse(answer.slice(answer.indexOf('\n')+1));assert(skill.executionWorkflow.execute.includes('stable item IDs'));assert(skill.manualApplication.phaseChecklists.build.some(x=>x.includes('rarity')));assert(calls.some(x=>x.name==='ms_get_skill'));
 assert((await p.evaluate(()=>__qa.taskPromptAddon('Build a village with creatures, UI, animation and VFX'))).length<9000);
 await p.click('#zs-switch');await p.click('[data-tab="agent"]');await p.locator('#ms-effort-slider').focus();await p.keyboard.press('Home');assert((await p.evaluate(()=>__qa.runTool({tool:'ms_ultra_manual',arguments:{action:'read',id:'ultragui'}}))).startsWith('ERROR'));assert.deepStrictEqual(x.errors,[]);
 console.log('PASS existing five core/nine production styles and twelve manuals retained, actual expanded phase/skill transport, existing tool actions, bounded full/default/startup payloads, improved craft matching and immediate Ultra demotion.');
 }finally{await x.close();}})().catch(e=>{console.error(e.stack);process.exit(1);});
