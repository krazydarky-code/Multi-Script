"""Real bridge WebSocket and HTTP launch boundary, without starting Blender."""
import asyncio,importlib.util,json,tempfile
from pathlib import Path
import websockets
root=Path(__file__).resolve().parents[1];spec=importlib.util.spec_from_file_location('blender_wire',root/'runtime/bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
b.mgr=b.MCPManager();b.probe_studio=lambda:{'app':False,'place':False};b.probe_unity=lambda:False;b.probe_godot=lambda:False;b._roblox_studio_app_running=lambda:False
async def verify(workspace):
 async with websockets.serve(b.handler,'127.0.0.1',0,max_size=16*1024*1024) as server:
  url='ws://127.0.0.1:'+str(server.sockets[0].getsockname()[1])
  async def request(origin,op='open',tool=False):
   async with websockets.connect(url,origin=origin) as ws:
    await ws.send(json.dumps({'id':88,'type':'call_tool','name':'ms_blender_workspace','arguments':{'action':'status'}} if tool else {'id':88,'type':'blender_workspace_admin','op':op}))
    for _ in range(10):
     reply=json.loads(await asyncio.wait_for(ws.recv(),8))
     if reply.get('id')==88:return reply
    raise AssertionError('No Blender launch reply')
  for origin in (None,'https://c.vani.ai','https://gemini.google.com','chrome-extension://'+'a'*32):
   reply=await request(origin);assert not reply['ok'] and 'extension'in reply['error'].lower()
  assert workspace.server is None
  good=b.mobile_remote.extension_origin();reply=await request(good);assert reply['ok'] and reply['url'].startswith('http://127.0.0.1:') and '#launch='in reply['url']
  assert not workspace.running,'Opening the local window must not claim a Blender engine is ready'
  for origin in ('https://c.vani.ai','https://untrusted.example','null'):
   reply=await request(origin,tool=True);assert not reply['ok'] and 'origin'in reply['error']
  assert (await request(good,tool=True))['ok']
  assert (await request(None,tool=True))['ok'],'Non-browser local protocol clients remain supported'
  reply=await request(good,'arbitrary');assert not reply['ok']
  b.mgr.disabled={'blender'};reply=await request(good);assert not reply['ok'] and 'Enable Blender'in reply['error']
 print('PASS real bridge: pinned extension-only Blender window launch, no provider-origin control, no unsolicited engine readiness, unknown-operation and engine-disable rejection.')
with tempfile.TemporaryDirectory(prefix='ms-blender-wire-') as temp:
 workspace=b.blender_workspace.Workspace(Path(temp),0);b.BLENDER_WORKSPACE=workspace
 try:asyncio.run(verify(workspace))
 finally:workspace.close()
