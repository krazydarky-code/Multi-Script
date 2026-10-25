const assert=require('assert'),h=require('../tools/studio_harness'),{entries,html}=require('./support/provider-fixtures');
const tools=[
 {name:'execute_luau',server:'roblox',description:'Run actual native Luau',inputSchema:{type:'object',properties:{code:{type:'string'},studio_id:{type:'string'}},required:['code','studio_id']}},
 {name:'ms_roblox_run_luau',server:'zeroscript',inputSchema:{type:'object',properties:{code:{type:'string'}},required:['code']}},
 {name:'msrb_project_summary',server:'roblox-companion',inputSchema:{type:'object',properties:{}}},
 {name:'msrb_replace_script',server:'roblox-companion',inputSchema:{type:'object',properties:{path:{type:'string'},source:{type:'string',maxLength:4194304}},required:['path','source']}},
 {name:'ms_ws_status',server:'zeroscript',inputSchema:{type:'object',properties:{}}},
 {name:'ms_get_skill',server:'zeroscript',inputSchema:{type:'object',properties:{skill_id:{type:'string'}},required:['skill_id']}}
];
(async()=>{for(const id of ['notion','vani']){let calls=0;const x=await h.open({url:entries[id].url,html:html(id),provider:'providers/'+id+'.js',bridge:'up',stateHook:true,tools,storage:{msSoftwareBuilder:{enabled:true,addons:{skills:true,engines:false,mcp:false}}},toolHandler:async()=>{calls++;return{ok:true,text:'actual workspace receipt'};}});assert(x);try{const p=x.page;
 await p.evaluate(()=>Object.assign(__qa.A,{started:true,chatOnly:false,software:false,bridge:{connected:true,studio:true,mcpAlive:true,engines:[{id:'roblox',connected:true,alive:true}],servers:[{id:'roblox',alive:true,tools:1}]}}));
 const detail=await p.evaluate(()=>__qa.runTool({tool:'ms_direct_tool_details',arguments:{tool_name:'execute_luau'}}));assert(detail.includes('studio_id')&&detail.includes('advertised for this session'));
 assert((await p.evaluate(()=>__qa.runTool({tool:'ms_direct_tool_details',arguments:{name:'ms_roblox_run_lua'}}))).includes('ms_roblox_run_luau'));
 assert((await p.evaluate(()=>__qa.runTool({tool:'ms_direct_tool_details',arguments:{}}))).includes('params.tool'));
 assert.strictEqual(calls,0,'Schema inspection must not execute project actions');
 await p.evaluate(()=>{__qa.A.bridge.servers[0].alive=false;__qa.A.bridge.mcpAlive=false;});
 assert((await p.evaluate(()=>__qa.runTool({tool:'list_mcp_servers',arguments:{}}))).includes('roblox-companion: connected Studio plugin'));
 assert((await p.evaluate(()=>__qa.runTool({tool:'ms_direct_tool_details',arguments:{tool:'execute_luau'}}))).includes('unavailable in this session'),'Native schemas must not borrow companion health');
 const companion=await p.evaluate(()=>__qa.runTool({tool:'list_commands',arguments:{}}));assert(companion.includes('msrb_replace_script'),'Connected companion remains discoverable with native MCP offline');assert(!companion.includes('\nexecute_luau('));
 await p.evaluate(()=>{__qa.A.bridge.engines[0].connected=false;__qa.A.bridge.engines[0].alive=false;});
 const offline=await p.evaluate(()=>__qa.runTool({tool:'list_commands',arguments:{server:'all'}}));assert(!offline.includes('msrb_replace_script'),'Disconnected engines must not advertise companion tools');
 await p.evaluate(()=>Object.assign(__qa.A,{chatOnly:true,software:false}));
 const hidden=await p.evaluate(()=>__qa.runTool({tool:'ms_direct_tool_details',arguments:{tool:'msrb_replace_script'}}));assert(hidden.includes('unavailable in this session')&&!hidden.includes('4194304'));
 assert((await p.evaluate(()=>__qa.runTool({tool:'msrb_project_summary',arguments:{}}))).startsWith('ERROR'));assert.strictEqual(calls,0);
 await p.evaluate(()=>Object.assign(__qa.A,{software:true,chatOnly:true}));
 assert((await p.evaluate(()=>__qa.runTool({tool:'ms_ws_status',arguments:{}}))).includes('actual workspace receipt'));assert.strictEqual(calls,1,'Build software operates without Studio');
 assert((await p.evaluate(()=>__qa.runTool({tool:'msrb_project_summary',arguments:{}}))).startsWith('ERROR'));assert.strictEqual(calls,1);
 await p.click('#zs-switch');await p.click('[data-tab="home"]');assert(await p.locator('#zs-menu').getByText('Choose your workspace',{exact:true}).isVisible());
 assert.deepStrictEqual(x.errors,[]);console.log('PASS '+id+': exact schemas/aliases, missing-parameter recovery, companion-only discovery, disconnected/chat isolation, workspace execution without Studio, workspace help.');
 }finally{await x.close();}}})().catch(e=>{console.error(e.stack);process.exit(1)});
