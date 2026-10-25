"""Kill a real bridge owner while bpy is busy; its worker must release the project."""
from pathlib import Path
import json,os,subprocess,sys,tempfile,time
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime'))
from blender_workspace import Workspace

with tempfile.TemporaryDirectory(prefix='ms-blender-owner-') as temp:
 root=Path(temp);marker=root/'busy.json'
 child_code='''
import json,os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from blender_workspace import Workspace
w=Workspace(Path(sys.argv[2]),0);w.submit('create',{'name':'Owner crash recovery'});w.job_thread.join(120);assert w.running,w.error
w.command('primitive',{'shape':'cube'})
code="import bpy,json,os,time\\nfrom pathlib import Path\\nbpy.ops.mesh.primitive_uv_sphere_add()\\nbpy.context.object.name='Never committed'\\nPath("+repr(sys.argv[3])+").write_text(json.dumps({'project':"+repr(w.project)+",'worker':os.getpid()}))\\ntime.sleep(300)"
w.command('exec',{'code':code.replace('\\\\n','\\n')},600)
'''
 log=(root/'owner.log').open('wb');owner=subprocess.Popen([sys.executable,'-X','utf8','-c',child_code,str(R/'runtime'),str(root),str(marker)],stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 w=Workspace(root,0)
 try:
  deadline=time.monotonic()+120
  while not marker.exists() and time.monotonic()<deadline:
   if owner.poll() is not None:raise AssertionError((root/'owner.log').read_text(encoding='utf-8',errors='replace'))
   time.sleep(.1)
  assert marker.exists(),'Owner never reached its busy native operation'
  data=json.loads(marker.read_text(encoding='utf-8'));project=data['project']
  w.submit('open',{'project':project});w.job_thread.join(30)
  assert not w.running and 'already open in another worker' in w.error,w.error
  owner.kill();owner.wait(10)
  w.submit('open',{'project':project});w.job_thread.join(120)
  assert w.running and w.status()['verified'] and not w.error,w.error
  assert w.project==project and [o['name'] for o in w.scene['objects']]==['Cube'],'Recovery retained an uncommitted edit or lost committed geometry'
  print('PASS real Blender owner death during bpy execution: second worker refused, orphan exited independently, project lock released, saved project reopened and uncommitted mutation absent.')
 finally:
  if owner.poll() is None:owner.kill();owner.wait(10)
  w.close();log.close()
