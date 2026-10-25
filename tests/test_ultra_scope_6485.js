const assert=require('assert'),e=require('../extension/core/execution-discipline'),studio=require('../extension/core/studio-workflows');
const write={tool:'execute_luau',arguments:{code:'local x=Instance.new("Frame");x.Parent=game.StarterGui'}};
for(const effort of ['ultra','standard']){
 const t=e.create('Build a Roblox inventory menu without web research',effort,['ms_get_skill','ms_ultra_manual','execute_luau']);assert(!t.requireResearch,'Explicit no-research preference is preserved');
 if(effort==='ultra'){
  assert(t.requireSkill&&e.gate(t,write).blocked,'Skipping research must retain full-method requirement');
  e.record(t,{tool:'ms_get_skill',arguments:{skill_id:'roblox-data-store-safety'}},'{"id":"roblox-data-store-safety","name":"Data store safety","capabilityDomain":"data"}',false);assert(!t.skillLoaded&&e.gate(t,write).blocked,'Unrelated workflow cannot unlock a UI build');
  e.record(t,{tool:'ms_ultra_manual',arguments:{action:'read',id:'ultragui'}},'{"id":"ultragui","name":"UI production"}',false);assert(t.skillLoaded&&!e.gate(t,write).blocked,'Relevant full manual unlocks the authorized operation');assert.deepStrictEqual(t.loadedMethods,['roblox-data-store-safety','ultragui']);
 }else assert(!t.requireSkill&&!e.gate(t,write).blocked,'Standard never inherits Ultra-only obligations');
}
for(const [request,id] of [['Bake normal maps in Blender','blender-texture-baking'],['Create Blender shape keys for a face','blender-shape-keys'],['Build geometry nodes in Blender','blender-geometry-nodes'],['Export glTF from Blender','blender-gltf-export'],['Build a Figma prototype','figma-prototyping']]){
 assert(studio.taskAddon(request,'ultra',{enabled:false},{engines:['workspace']}).includes(id),id+' reaches actual task instructions');assert(!studio.taskAddon(request,'standard',{enabled:false}).includes('[ULTRA · SPECIALIST RETRIEVAL]'));
}
const disabled=e.create('Build a menu without research','ultra',['execute_luau']);assert(!e.gate(disabled,write).blocked,'No permission or unavailable tool is manufactured');
console.log('PASS scoped Ultra: no-research still loads a relevant full method, unrelated guidance cannot unlock writes, restored retrieval is bounded, demotion and unavailable-tool boundaries stay intact.');

const exported=e.create('Export glTF from Blender','ultra',['ms_get_skill','execute_blender_code']);assert(exported.requireSkill,'Specialist export tasks retain full-method retrieval');

const repeated=e.create('Build a menu without research','ultra',['ms_get_skill']);const method={tool:'ms_get_skill',arguments:{skill_id:'ui-ux-production'}};e.record(repeated,method,'same method',false);e.record(repeated,method,'same method',false);assert(e.gate(repeated,method).blocked,'Repeated full-method reads must advance to actual work');assert(!e.gate(repeated,{...method,arguments:{skill_id:'animation-production'}}).blocked,'A targeted different method remains available');
