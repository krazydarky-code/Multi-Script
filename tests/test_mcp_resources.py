import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=types.ModuleType('websockets'); w.ConnectionClosed=Exception; sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('ms_bridge',ROOT/'runtime'/'bridge.py'); b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
c=b.MCPClient('unity',sys.executable,[str(ROOT/'tests'/'fake_mcp_server.py')]); c.start()
try:
 assert any(x['name']=='ping' for x in c.tools_cache)
 b.mgr.clients['unity']=c
 cat=json.loads(b._builtin_call('ms_engine_catalog',{'server':'unity'},b.mgr)['text'])
 # The direct catalog grows as built-ins are added. Assert against the runtime
 # source of truth instead of the stale 6.25-era 230+6+7+27 literal.
 assert cat['nativeToolCount']>=1 and cat['multiScriptDirectToolCount']==len(b.BUILTIN_TOOLS)
 routed=b._builtin_call('ms_call_engine_tool',{'server':'unity','tool':'ping','arguments':{}},b.mgr); assert routed['text']=='pong'
 smoke=json.loads(b._builtin_call('ms_engine_connection_test',{'server':'unity','tool':'ping'},b.mgr)['text']); assert smoke['verified'] and smoke['testedTool']=='ping'
 assert c.call_tool('ping',{},3)['text']=='pong'
 assert c.list_resources()['resources'][0]['uri']=='mcpforunity://instances'
 assert b.probe_unity() is True
 snap=b.engine_snapshot({'app':False,'place':False},True)
 assert any(x['id']=='unity' and x['connected'] is True for x in snap)
 out=c.read_resource('mcpforunity://instances'); assert 'Demo@abc' in out['text']
 print('PASS MCP tools and resources transport')
finally: c.stop()
