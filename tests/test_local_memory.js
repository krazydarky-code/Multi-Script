const fs = require('fs'), vm = require('vm');
const data = {};
const chrome = { storage:{ local:{
  get:(k,cb)=>cb(typeof k === 'string' ? {[k]:data[k]} : Object.fromEntries((k||[]).map(x=>[x,data[x]]))),
  set:(o,cb)=>{ Object.assign(data, JSON.parse(JSON.stringify(o))); if(cb)cb(); }
}}};
const ctx = { chrome, console, Date, Math, JSON, Set, Map, Promise, globalThis:null, self:null };
ctx.globalThis=ctx; ctx.self=ctx; vm.createContext(ctx);
vm.runInContext(fs.readFileSync('extension/local-memory.js','utf8'),ctx);
const M=ctx.MSLocalMemory, checks=[]; const ok=(n,c)=>{checks.push([n,!!c]); if(!c)console.error('FAIL',n)};
(async()=>{
 ok('six local MCP memory tools advertised',M.TOOLS.length===6 && M.TOOLS.every(t=>t.server==='multiscript-local'));
 let r=await M.call('create',{name:'Roblox Classic UI'}); const id=r.created.id; ok('create',r.ok&&id);
 r=await M.call('remember',{memory:id,name:'UI style',text:'Use classic grey panels',kind:'preference',pinned:true,entities:[{name:'MainMenu'}],relations:[{from:'UI style',rel:'applies to',to:'MainMenu'}]}); ok('remember graph',r.ok&&r.count>=2);
 r=await M.call('context',{memory:id,query:'classic menu'}); ok('context ranks durable notes',r.ok&&/classic grey/i.test(r.text));
 r=await M.tool('ms_memory_recall',{memory:id,query:'grey'}); ok('native local tool response',r.ok&&/UI style/.test(r.text));
 r=await M.call('settings',{memory:id,settings:{autoCapture:false,maxContextChars:700}}); ok('settings',r.settings.autoCapture===false&&r.settings.maxContextChars===700);
 const graph=await M.call('graph',{memory:id,action:'export'}); ok('graph has nodes and edge',graph.nodes.length>=2&&graph.edges.length>=1);
 const node=graph.nodes.find(n=>n.name==='UI style'); await M.call('update',{memory:id,node:node.id,pinned:false,text:'Use polished classic grey panels'});
 r=await M.call('recall',{memory:id,query:'polished'}); ok('update',r.results.some(n=>/polished/.test(n.text)));
 const ex=await M.call('export',{memory:id}); r=await M.call('import',{data:ex}); ok('export/import',r.ok&&r.nodes>=2);
 await M.call('forget',{memory:id,node:node.id}); r=await M.call('graph',{memory:id,action:'list'}); ok('forget',!r.nodes.some(n=>n.id===node.id));
 r=await M.call('list',{}); ok('persists in chrome storage',r.memories.length===2&&data[M.KEY]);
 for(const [n,c] of checks) if(c) console.log('PASS',n); const failed=checks.filter(x=>!x[1]).length; console.log(`\n${failed} failed`); process.exit(failed?1:0);
})().catch(e=>{console.error(e);process.exit(1)});
