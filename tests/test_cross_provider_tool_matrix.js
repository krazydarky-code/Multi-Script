const fs=require('fs'),path=require('path'),cp=require('child_process');
const root=path.resolve(__dirname,'..');
const parser=new Function(fs.readFileSync(path.join(root,'extension/core/parser.js'),'utf8')+';return ZSParse;')();
const tools=JSON.parse(cp.execFileSync(process.env.MS_TEST_PYTHON||'python',['-X','utf8','-c',"import sys,json;sys.path.insert(0,'runtime');import bridge;print(json.dumps([t['name'] for t in bridge.BUILTIN_TOOLS]))"],{cwd:root,encoding:'utf8',maxBuffer:4e6}));
const expected=JSON.parse(fs.readFileSync(path.join(root,'runtime/product-manifest.json'),'utf8')).catalogue.directTools;
if(tools.length!==expected||new Set(tools).size!==expected)throw new Error('Runtime catalogue uniqueness/count differs from the product manifest: '+tools.length);
const providers=['arena','chatgpt','claude','deepseek','gemini','glm','kimi','meta','notion','promptql','qwen','superapp','vani','venice','clickup'];
let cases=0;
for(const provider of providers){
 const providerCode=fs.readFileSync(path.join(root,'extension/providers',provider+'.js'),'utf8');
 for(const required of ['typeAndSend','getEditor','conversationKey','installSendHooks'])if(!providerCode.includes(required)&&!providerCode.includes('MSDomChat.create'))throw new Error(provider+' missing '+required);
 for(const tool of tools){
  const args={provider,probe:tool,nested:{items:[1,true,null,'{safe}']}};
  const obj={command:tool,params:args};
  const envelopes=[JSON.stringify(obj),'```json\n'+JSON.stringify(obj,null,2)+'\n```','###MCP_TOOL###\n'+JSON.stringify(obj)+'\n###END_MCP_TOOL###',JSON.stringify({tool,arguments:args})];
  for(const text of envelopes){const out=parser.parseToolCalls(text);if(out.length!==1||out[0].tool!==tool||out[0].arguments.provider!==provider)throw new Error(`${provider}/${tool} failed: ${text.slice(0,30)}`);cases++;}
 }
 for(const name of ['unity::create_asset','godot::create_scene','blender::create_mesh','roblox::execute_luau']){const out=parser.parseToolCalls(JSON.stringify({command:name,params:{provider}}));if(out.length!==1||out[0].tool!==name)throw new Error(provider+' namespaced '+name);cases++;}
}
console.log(`PASS cross-provider tool matrix: ${tools.length} built-ins + 4 namespaced MCP probes across ${providers.length} AI websites (${cases} command envelopes)`);
