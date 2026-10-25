const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'..');
const parser=new Function(fs.readFileSync(path.join(root,'extension/core/parser.js'),'utf8')+';return ZSParse;')();
const config=new Function(fs.readFileSync(path.join(root,'extension/core/config.js'),'utf8')+';return ZS;')();
for(const text of [
 '{"command":"list_commands","params":{}}',
 '{"command":"get_studio_state","params":{}}',
 '{"command":"script_read","params":{"target_file":"game.ServerScriptService.Main"}}',
 '{"command":"execute_luau","params":{"code":"return game.PlaceId","datamodel_type":"Edit"}}'
]) { const calls=parser.parseToolCalls(text); if(calls.length!==1||!calls[0].tool) throw new Error('Arena/Roblox JSON command failed '+text); }
const prompt=config.buildSystemPrompt({siteName:'Arena'});
if(!prompt.includes('exactly ONE plain-text JSON object'))throw new Error('missing JSON-only rule');
if(prompt.includes('every command goes inside a fenced code block')||prompt.includes('SPECIAL FORMAT FOR execute_luau'))throw new Error('legacy alternate format still advertised');
if(!fs.readFileSync(path.join(root,'extension/providers/arena.js'),'utf8').includes('dsml/i'))throw new Error('Arena native-markup camouflage missing');
console.log('PASS Arena Roblox JSON-only protocol: visible command chips, four live command shapes, native markup normalized');
