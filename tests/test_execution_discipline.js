const assert=require('assert'),e=require('../extension/core/execution-discipline');
assert.strictEqual(e.kind({tool:'bbmodel_edit',arguments:{operations:[{op:'add_cube'}]}}),'write');assert.strictEqual(e.kind({tool:'bbmodel_validate',arguments:{}}),'read');assert.strictEqual(e.kind({tool:'bbmodel_render',arguments:{}}),'capture');assert.strictEqual(e.kind({tool:'ms_obsidian',arguments:{action:'remember'}}),'other','Memory bookkeeping is not a project implementation');
const read={tool:'inspect_instance',arguments:{studio_id:'studio-a',path:'game.Workspace'}},write={tool:'execute_luau',arguments:{code:'local p=Instance.new("Part"); p.Parent=workspace'}};
let trace=e.create('Inspect the current place','standard',[]);
e.record(trace,read,'one baseplate',false);e.record(trace,read,'one baseplate',false);assert(e.gate(trace,read).blocked);assert(e.gate(trace,read).feedback.includes('does not prove the place is empty'));
e.record(trace,write,'created',false);assert(!e.gate(trace,read).blocked,'Successful writes invalidate prior read observations');
e.record(trace,read,'two parts',false);e.record(trace,read,'three parts',false);assert(!e.gate(trace,read).blocked,'Changing observations may be polled');
const bad={tool:'script_read',arguments:{path:'game.ServerScriptService.Main'}};e.record(trace,bad,'ERROR target_file required',true);e.record(trace,bad,'ERROR target_file required',true);assert(e.gate(trace,bad).blocked);assert(!e.gate(trace,{...bad,arguments:{target_file:'game.ServerScriptService.Main',studio_id:'studio-a'}}).blocked);
trace=e.create('Build an animated creature game','ultra',['ms_fetch_reference','ms_screen_record','screen_capture']);assert(e.gate(trace,write).blocked,'Major Ultra writes require actual reference access when available');
e.record(trace,{tool:'ms_fetch_reference',arguments:{url:'https://create.roblox.com/docs/animation/editor'}},'Fetched actual docs',false);assert(!e.gate(trace,write).blocked);e.record(trace,write,'created',false);assert(e.finalCheck(trace).includes('recording'));e.record(trace,{tool:'ms_screen_record',arguments:{seconds:2,fps:4}},'actual clip',false);assert.strictEqual(e.finalCheck(trace),'');
e.record(trace,write,'changed again',false);assert(e.finalCheck(trace),'Captures expire after a new write');
trace=e.create('Make a game UI','ultra',['ms_fetch_reference']);e.record(trace,{tool:'ms_fetch_reference',arguments:{}},'ERROR offline',true);assert(!e.gate(trace,write).blocked,'Unavailable research must not force invented evidence or a permanent loop');
const small=e.create('Build a matching UI icon for my game.','ultra',['ms_create_icon_pack','ms_fetch_reference']);assert(!small.requireResearch&&!small.intentBuild,'A single local icon does not require a game-build research pipeline');e.record(small,{tool:'ms_create_icon_pack',arguments:{}},'actual svg',false);assert.strictEqual(e.finalCheck(small),'');
assert.strictEqual(Object.keys(e.PROFILES).length,6);for(const level of Object.keys(e.PROFILES)){const policy=e.policy('Fix the inventory',level,{tools:['script_read']});assert(policy.includes('target_file'));assert(policy.includes('UNKNOWN, not empty'));assert(policy.includes(level.toUpperCase()));}
trace=e.create('Build an animated creature game','ultra',['ms_get_skill','ms_ultra_manual']);
for(const call of [{tool:'ms_ultra_manual',arguments:{action:'list'}},{tool:'ms_ultra_manual',arguments:{action:'read',id:'ultraanimation',section:'verify'}},{tool:'ms_skill_reference',arguments:{skill_id:'blender-reference-blockout',action:'index'}}]){e.record(trace,call,'actual directory or excerpt',false);assert(!trace.skillLoaded);assert(e.gate(trace,write).blocked);}
e.record(trace,{tool:'ms_ultra_manual',arguments:{action:'read',id:'ultraanimation'}},'actual complete manual',false);assert(trace.skillLoaded&&!e.gate(trace,write).blocked);
console.log('PASS six effort methods, observed research/evidence gates, bounded repeated-read/failure stalls, changed-state invalidation and truthful unavailable-tool fallbacks.');

const asset=e.create('Build an animated model','ultra',['bbmodel_edit','bbmodel_render','ms_screen_record']);const edit={tool:'bbmodel_edit',arguments:{file:'hero.bbmodel'}};
e.record(asset,edit,'Native file revision saved',false);assert(asset.projectWrite);
const frame=time=>({tool:'bbmodel_render',arguments:{file:'hero.bbmodel',clip:'walk',time}});
e.record(asset,frame(0),'Actual rendered PNG at frame zero',false);e.record(asset,frame(0),'Same pose again',false);assert(e.finalCheck(asset),'Repeated static pose is not temporal evidence');
e.record(asset,frame(0.4),'Actual rendered PNG at a later pose',false);assert.strictEqual(e.finalCheck(asset),'');e.record(asset,edit,'Changed animation',false);assert(e.finalCheck(asset),'A later edit invalidates old rendered poses');

for(const level of Object.keys(e.PROFILES)){
 const native=e.create('Build a native inventory UI in Roblox Studio',level,['ms_create_canvas_ui','execute_luau']);
 e.record(native,{tool:'ms_create_canvas_ui',arguments:{name:'inventory'}},'Local SVG mockup saved',false);
 assert(e.finalCheck(native),level+' cannot claim native implementation from a local mockup');
 const mock=e.create('Create an SVG mockup of an inventory',level,['ms_create_canvas_ui']);e.record(mock,{tool:'ms_create_canvas_ui',arguments:{}},'actual SVG',false);assert.strictEqual(e.finalCheck(mock),'');
}
