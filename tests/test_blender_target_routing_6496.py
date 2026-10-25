"""Actual Blender plus an external-client trap: every headless route must agree."""
from pathlib import Path
import asyncio,hashlib,importlib.util,json,socket,sys,tempfile
import websockets
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime'))
spec=importlib.util.spec_from_file_location('target_bridge',R/'runtime/bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
from blender_workspace import Workspace,NATIVE_NAMES

class DesktopTrap:
 id='blender';tools_stale=True
 tools_cache=[{'name':n,'inputSchema':{'type':'object','properties':{}}} for n in NATIVE_NAMES]+[{'name':'desktop_only','inputSchema':{}}]
 calls=[]
 def is_alive(self):return True
 def start(self):raise AssertionError('Headless catalog tried starting desktop MCP')
 def refresh_tools(self):raise AssertionError('Headless catalog tried refreshing desktop MCP')
 def restart(self):self.calls.append('restart');raise AssertionError('Headless reconnect restarted desktop MCP')
 def call_tool(self,name,args,timeout):self.calls.append(name);return {'text':'Could not connect to Blender. Make sure the Blender addon is running.','images':[],'isError':True}

async def resume_via_extension(w,m):
 b.probe_studio=lambda:{'app':False,'place':False};b.probe_unity=lambda:False;b.probe_godot=lambda:False;b._roblox_studio_app_running=lambda:False
 async with websockets.serve(b.handler,'127.0.0.1',0) as server:
  async with websockets.connect('ws://127.0.0.1:'+str(server.sockets[0].getsockname()[1]),origin=b.mobile_remote.extension_origin()) as ws:
   async def ask(op):
    await ws.send(json.dumps({'id':6496,'type':'blender_workspace_admin','op':op,'engines':[]}))
    while True:
     reply=json.loads(await asyncio.wait_for(ws.recv(),20))
     if reply.get('id')==6496:return reply
   result=await ask('ensure');assert result['ok'] and result['required'] and result['engines']==['blender'],result
   await asyncio.to_thread(w.job_thread.join,120);assert w.running,w.error
   status=await ask('status');assert status['verified'] and status['aiTarget'];assert next(e for e in status['engines'] if e['id']=='blender')['backend']=='headless-workspace';assert next(e for e in status['servers'] if e['id']=='blender')['alive']

with tempfile.TemporaryDirectory(prefix='ms-headless-target-') as temp:
 w=Workspace(Path(temp),0);b.BLENDER_WORKSPACE=w;m=b.MCPManager();b.mgr=m
 try:
  w.submit('create',{'name':'Cycle'});w.job_thread.join(120);assert w.running,w.error;pid=w.project
  w.command('primitive',{'shape':'cube'});native=(w.folder()/'scene.blend').read_bytes()
  # No configured desktop MCP client: native aliases and catalog still exist.
  names={t['name'] for t in m.list_tools()};assert NATIVE_NAMES<=names
  assert json.loads(m.call('get_scene_info',{},30)['text'])['objects'][0]['name']=='Cube'
  assert m.smoke_test('blender')['backend']=='headless-workspace'
  trap=DesktopTrap();m.clients={'blender':trap};m.rebuild_index()
  assert 'desktop_only' not in {t['name'] for t in m.list_tools(refresh=True)}
  assert {t['name'] for t in m.list_server_tools('blender',refresh=True)}==NATIVE_NAMES
  tested=json.loads(m.call('ms_engine_connection_test',{'server':'blender'},30)['text']);assert tested['verified'] and tested['workspaceProject']==pid
  catalog=json.loads(m.call('ms_engine_catalog',{'server':'blender','refresh':True},30)['text']);assert catalog['nativeToolCount']==4
  for name,args in [('get_scene_info',{}),('blender/get_scene_info',{}),('ms_call_engine_tool',{'server':'blender','tool':'get_scene_info'}),('ms_native_read',{'server':'blender','what':'tree'})]:assert 'Cube' in m.call(name,args,30)['text'],name
  assert (w.folder()/'scene.blend').read_bytes()==native,'Connection/catalog reads must not resave the scene'
  assert json.loads(m.call('ms_blender_scene_summary',{'target':'auto'},30)['text'])['object_counts']['MESH']==1
  assert not trap.calls
  worker=w.proc.pid;m.restart('blender');w.job_thread.join(30);assert w.proc.pid==worker and w.status()['verified'] and not trap.calls,'Reconnect verifies the selected worker, never the desktop MCP client'
  # A stopped worker retains workspace ownership and never falls through to desktop.
  w.submit('close');w.job_thread.join(30);assert w.owns_target and not w.selected and not w.status()['verified']
  row=next(e for e in b.engine_snapshot({'app':False,'place':False},False,False) if e['id']=='blender');assert row['backend']=='headless-workspace' and not row['connected'] and not row['alive']
  for f in [lambda:m.call('get_scene_info',{},30),lambda:m.call_on_server('blender','get_scene_info',{}),lambda:m.smoke_test('blender')]:
   try:f()
   except RuntimeError as e:assert 'Resume Blender' in str(e),e
   else:raise AssertionError('Stopped workspace claimed connection success')
  summary=json.loads(m.call('ms_blender_scene_summary',{'target':'auto'},30)['text']);assert not summary['ok'] and 'Resume Blender' in summary['error'];assert not trap.calls
  # Bridge-restart restoration resumes the same native project through real WS admin.
  restored=Workspace(w.root,0);b.BLENDER_WORKSPACE=restored;w.close();w=restored
  assert w.owns_target and w.project==pid;asyncio.run(resume_via_extension(w,m));assert len(w.scene['objects'])==1 and w.scene['objects'][0]['name']=='Cube' and (w.folder()/'scene.blend').is_file()
  # A live process with a dead socket must lose verified status and be recoverable.
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));bad_port=sock.getsockname()[1]
  w.worker_port=bad_port
  try:m.call('get_scene_info',{},30)
  except RuntimeError as e:assert 'no desktop add-on' in str(e)
  else:raise AssertionError('Dead socket passed a connection read')
  assert not w.status()['verified'] and w.owns_target and not trap.calls
  w.submit('ensure',{'project':pid});w.job_thread.join(120);assert w.status()['verified'] and w.project==pid and not w.error,w.error
  assert json.loads(m.call('get_scene_info',{},30)['text'])['objects'][0]['name']=='Cube'
  # Engine disable and explicit desktop selection remain authoritative.
  m.disabled={'blender'}
  for f in [lambda:m.call('get_scene_info',{},30),lambda:m.list_server_tools('blender'),lambda:m.smoke_test('blender')]:
   try:f()
   except RuntimeError as e:assert 'off' in str(e).lower()
   else:raise AssertionError('Disabled Blender was used')
  m.disabled=set();m.call_on_server('blender','get_scene_info',{},use_workspace=False);assert trap.calls==['get_scene_info']
  w.ai_target=False
  try:m.smoke_test('blender')
  except RuntimeError as e:assert 'Could not connect' in str(e)
  else:raise AssertionError('Desktop error result incorrectly marked verified')
  print('PASS real Blender: owned native catalog/aliases/facade/toolkit/connection test, no desktop fallback on stop, honest readiness, actual WS standalone resume after restart, dead-socket recovery, native-file preservation, engine disable and explicit desktop isolation.')
 finally:w.close()
