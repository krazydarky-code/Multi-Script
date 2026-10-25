"""Real worker loss and corrupt IPC must not leave a verified or orphan worker."""
from pathlib import Path
import json,socket,sys,tempfile,threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from blender_workspace import Workspace

with tempfile.TemporaryDirectory(prefix='ms-blender-faults-') as temp:
 w=Workspace(Path(temp),0)
 def resume():
  w.submit('ensure',{'project':w.project});w.job_thread.join(120)
  assert w.running and w.status()['verified'] and not w.error,w.error
 try:
  w.submit('create',{'name':'Cycle — connection QA'});w.job_thread.join(120);assert w.running,w.error
  project=w.project;w.command('exec',{'code':"import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.context.object.name='Saved Cube — păstrat'"})
  for raw in [b'[]\n',b'{"ok":true}\n',b'{"ok":true,"data":[]}\n',b'{"ok":true,"data":{}}',b'broken\n']:
   worker=w.proc;before=(w.folder()/'scene.blend').read_bytes();requests=[]
   server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1);w.worker_port=server.getsockname()[1]
   def broken_peer():
    with server:
     client,_=server.accept()
     with client:
      request=b''
      while b'\n' not in request:request+=client.recv(65536)
      requests.append(json.loads(request));client.sendall(raw)
   thread=threading.Thread(target=broken_peer);thread.start()
   try:w.command('snapshot',{},10)
   except RuntimeError as e:assert 'do not replay' in str(e)
   else:raise AssertionError('Corrupt connection was trusted')
   thread.join(5);assert len(requests)==1 and worker.poll() is not None and not w.running and not w.status()['verified'] and w.owns_target
   assert (w.folder()/'scene.blend').read_bytes()==before
   try:w.command('snapshot')
   except RuntimeError as e:assert 'Resume Blender' in str(e)
   else:raise AssertionError('A failed call silently retried/reconnected')
   resume();assert w.project==project and w.scene['objects'][0]['name']=='Saved Cube — păstrat'
  worker=w.proc
  try:w.command('exec',{'code':'import os\nos._exit(17)'},10)
  except RuntimeError as e:assert 'do not replay' in str(e)
  else:raise AssertionError('Dead process looked connected')
  assert worker.poll() is not None and not w.status()['verified'];resume()
  try:w.command('exec',{'code':"import bpy,time\nbpy.ops.mesh.primitive_uv_sphere_add()\nbpy.context.object.name='Uncommitted sphere'\ntime.sleep(30)"},5)
  except TimeoutError:pass
  else:raise AssertionError('Timed-out edit continued')
  assert not w.running and w.owns_target;resume()
  assert w.project==project and [o['name'] for o in w.scene['objects']]==['Saved Cube — păstrat']
  print('PASS actual Blender: malformed/truncated envelopes, process death, timeout mid-edit, forced worker cleanup, no automatic replay, same-project recovery and saved native geometry.')
 finally:w.close()
