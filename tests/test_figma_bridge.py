"""Actual bridge manager -> shipped stdio Figma server; no live editor required."""
import importlib.util,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('figma_bridge',root/'runtime/bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
client=b.MCPClient('figma','launch_figma_mcp.py',[],{'MS_FIGMA_PORT':'0'});manager=b.MCPManager();manager.clients={'figma':client}
try:
 client.start();manager.rebuild_index();tools=manager.list_tools();figma=[t for t in tools if t.get('server')=='figma'];assert len(figma)==9
 status=manager.call('figma_status',{},5);assert json.loads(status['text'])['connected'] is False
 failed=manager.call('figma_create_node',{'type':'FRAME'},5);assert failed.get('isError') is True and 'not paired' in failed['text'],'MCP isError survives the bridge instead of becoming a green success'
 assert all(name in b._NON_IDEMPOTENT_NATIVE for name in ['figma_create_node','figma_update_node','figma_delete_node','figma_import_svg','use_figma'])
 print('PASS actual manager/native Figma discovery, exact routing, real offline-file state, preserved MCP isError and write no-replay classification.')
finally:client.stop()
