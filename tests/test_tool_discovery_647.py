import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import tool_discovery,schema_repair
w=types.ModuleType('websockets');w.ConnectionClosed=Exception;sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('discovery_bridge',ROOT/'runtime/bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
native={'name':'execute_luau','server':'roblox','inputSchema':{'type':'object','properties':{'code':{'type':'string','maxLength':32},'studio_id':{'type':'string'}},'required':['code','studio_id']}}
catalog=[*b.BUILTIN_TOOLS,native,{'name':'ms_roblox_run_luau','server':'zeroscript','inputSchema':{'type':'object','properties':{'code':{'type':'string'}}}}]
manager=types.SimpleNamespace(disabled=set(),list_tools=lambda:catalog)
for args in [{'tool':'execute_luau'},{'tool_name':'execute_luau'},{'name':'execute_luau'},{'tool':'ms_roblox_run_lua'}]:
 result=json.loads(b.MCPManager._dispatch(manager,'ms_direct_tool_details',args,10)['text']);assert result['available'],args
 assert result['tool']['name'] in ('execute_luau','ms_roblox_run_luau')
assert not json.loads(b.MCPManager._dispatch(manager,'ms_direct_tool_details',{'tool':'unknown'},10)['text'])['available']
source='return "'+'x'*100+'"'
fixed,notes=schema_repair.repair_arguments(native['inputSchema'],{'code':source,'studio_id':'actual-studio'},'execute_luau');assert fixed['code']==source
try:b._resilient_arguments(native['inputSchema'],fixed,'execute_luau');raise AssertionError('Oversized source accepted')
except RuntimeError as error:assert 'at most 32' in str(error)
two=[native,{**native,'name':'other/execute_luau','server':'other'}]
assert tool_discovery.details('execute_luau','other',two,[])['tool']['server']=='other'
print('PASS live native/toolkit discovery, safe name aliases, server scope, honest unknown availability and no silent source clipping in strict or repaired calls.')
