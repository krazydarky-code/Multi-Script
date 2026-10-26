const assert=require('assert'),studio=require('../extension/core/studio-workflows');
assert.strictEqual(studio.resourcePlan('Create a shop','standard'),null);
assert(studio.resourcePlan('Does OMNI GUI exist?','standard').visual);
const plan=studio.resourcePlan('Create a Roblox shop UI with animated inventory',{toString:()=>''});
assert.strictEqual(plan,null);
const selected=studio.resourcePlan('Create a Roblox shop UI with animated inventory','ultra',{engines:['roblox']});
assert(selected.visual&&selected.manuals.length>0&&selected.manuals.length<=2);assert(selected.manuals.every(m=>m.sections.build&&m.sections.verify));
const context=studio.resourcePrompt(selected,{library:{available:true,references:522},memory:{available:true,vault:'PRIVATE_ROOT_MUST_NOT_BE_INJECTED',recent:[{text:'Remember the existing MenuRoot.'}],results:[]}}, {STYLES:{cartoon:{}},PACKS:['shop','full']});
assert(context.includes('522')&&context.includes('MenuRoot')&&context.includes('ms_forge'));assert(!context.includes('PRIVATE_ROOT_MUST_NOT_BE_INJECTED'));assert(context.length<14000);
console.log('PASS relevant existing manuals, explicit lower-effort discovery, bounded actual-library/Forge context and private root-path exclusion.');

const routing=new Function(require('fs').readFileSync(require('path').join(__dirname,'../extension/core/tool-routing.js'),'utf8')+';return ZSToolRouting;')();
for(const action of ['context','references','packages','preview','recipe','modules','bundle'])assert(!routing.isEngineExecution('ms_roblox_omni',{action},[{name:'ms_roblox_omni',server:'zeroscript'}]));
assert(routing.isEngineExecution('ms_roblox_omni',{action:'install'},[{name:'ms_roblox_omni',server:'zeroscript'}]));

assert.strictEqual(studio.resourcePlan('Create a UI without using memory','ultra'),null);
