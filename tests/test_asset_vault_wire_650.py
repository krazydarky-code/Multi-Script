"""Real WebSocket origin gates and serialized attachment of a real asset server."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import asyncio,json,os,sys,tempfile,types
import websockets
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import bridge as b,obsidian_vault as vault
b.mgr=b.MCPManager();b.probe_studio=lambda:{'app':False,'place':False};b.probe_unity=lambda:False;b.probe_godot=lambda:False;b._roblox_studio_app_running=lambda:False

async def wire():
 async with websockets.serve(b.handler,'127.0.0.1',0,max_size=16*1024*1024) as server:
  url='ws://127.0.0.1:'+str(server.sockets[0].getsockname()[1])
  async def request(origin,kind,op,payload=None):
   async with websockets.connect(url,origin=origin) as ws:
    await ws.send(json.dumps({'id':91,'type':kind,'op':op,'payload':payload or {}}))
    for _ in range(15):
     row=json.loads(await asyncio.wait_for(ws.recv(),15))
     if row.get('id')==91:return row
    raise AssertionError('No admin result')
  for kind in ('obsidian_admin','blockbench_workspace_admin'):
   for origin in (None,'https://chatgpt.com','https://arena.ai','chrome-extension://'+'a'*32):
    row=await request(origin,kind,'status');assert not row['ok'] and 'extension' in row['error'].lower()
  origin=b.mobile_remote.extension_origin();row=await request(origin,'obsidian_admin','setup');assert row['ok'] and row['available']
  result=json.loads(b._builtin_call('ms_obsidian',{'action':'remember','project':'wire','title':'Native bridge memory','text':'actualvaultwirecanary'},b.mgr)['text'])
  assert result['created'];recall=json.loads(b._builtin_call('ms_obsidian',{'action':'search','project':'wire','query':'actualvaultwirecanary','library':False},b.mgr)['text']);assert len(recall['results'])==1
  assert not (await request(origin,'obsidian_admin','arbitrary'))['ok']
  row=await request(origin,'blockbench_workspace_admin','status');assert row['ok'] and row['prepared'] and not row['connected']
 print('PASS real bridge WebSocket: pinned-origin admin only, root-vault setup, native builtin remember/search and accurate prepared-versus-connected asset status.')

with tempfile.TemporaryDirectory(prefix='ms-asset-wire-') as temp:
 os.environ['MS_OBSIDIAN_VAULT']=str(Path(temp)/'vault');asyncio.run(wire())
 os.environ['MS_BLOCKBENCH_PROJECT_ROOT']=str(Path(temp)/'models')
 existing=types.SimpleNamespace(tools_cache=[{'name':'unrelated_tool'}]);b.mgr.clients['existing']=existing
 factory=b.MCPClient
 with patch.object(b,'_read_config',return_value={'mcpServers':{}}),patch.object(b,'config_add_server',return_value=(True,'saved')),patch.object(b,'MCPClient',wraps=factory) as construct:
  with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(lambda _:json.loads(b._builtin_call('ms_blockbench_workspace',{'action':'prepare'},b.mgr)['text']),range(4)))
  assert all(row['connected'] and len(row['nativeTools'])==21 for row in rows);assert construct.call_count==1;assert b.mgr.clients['existing'] is existing
  assert 'unrelated_tool' in b.mgr.index
  b.mgr.disabled.add('blockbench')
  try:b._builtin_call('ms_blockbench_workspace',{'action':'prepare'},b.mgr);raise AssertionError('Disabled assets attached')
  except RuntimeError:pass
  finally:b.mgr.clients['blockbench'].stop()
 assert {'bbmodel_edit','bbmodel_create','bbmodel_add_texture'}<=b._NON_IDEMPOTENT_NATIVE
 print('PASS concurrent prepare attaches one live 21-tool server, preserves unrelated connections, honors disable and forbids ambiguous write replay.')
 with patch.object(b,'CONFIG_PATH',str(Path(temp)/'config.json')):
  b._write_config({'mcpServers':{'roblox':{'command':'keep-primary'},'existing':{'command':'keep-custom'}}})
  with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(lambda i:b.config_add_server('addon'+str(i),'qa-server',[]),range(32)))
  assert all(ok for ok,_ in results);assert len(b._read_config()['mcpServers'])==34
  with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(lambda i:b.config_remove_server('addon'+str(i)),range(16)))
  assert all(ok for ok,_ in results);assert len(b._read_config()['mcpServers'])==18
  assert b._read_config()['mcpServers']['existing']['command']=='keep-custom'
  b.mgr.disabled.discard('blockbench')
  def user_changes_config(**_):
   assert b.config_add_server('blockbench','user-custom-server',[])[0]
   return b.studio_hub._blockbench.status()
  with patch.object(b.studio_hub._blockbench,'prepare',side_effect=user_changes_config):
   try:b._builtin_call('ms_blockbench_workspace',{'action':'prepare'},b.mgr);raise AssertionError('Custom server was replaced during preparation')
   except RuntimeError as error:assert 'changed during preparation' in str(error)
  assert b._read_config()['mcpServers']['blockbench']['command']=='user-custom-server'
 print('PASS concurrent add/remove preserves every unrelated MCP setting; a custom Blockbench server selected during preparation is retained.')
