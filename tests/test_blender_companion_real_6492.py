"""Actual Blender companion startup and exported game-project file handoff."""
from pathlib import Path
import hashlib,json,os,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
if os.environ.get('MS_TEST_BLENDER'):os.environ['MS_BLENDER_PATH']=os.environ['MS_TEST_BLENDER']
from blender_workspace import Workspace
import blender_portable
assert blender_portable.discover(),'Prepare the real Blender runtime before this suite.'
with tempfile.TemporaryDirectory(prefix='ms-game-blender-') as temp:
 root=Path(temp).resolve();w=Workspace(root/'workspace',0)
 try:
  assert not w.status()['verified'] and not w.pipeline.begin(['godot'])['required'] and not w.running
  w.pipeline.configure({'engines':['godot','unity','roblox']})
  try:w.pipeline.begin(['godot'])
  except RuntimeError as e:assert 'not connected'in str(e)
  else:raise AssertionError('Offline editor must not start a companion')
  w.set_engines([{'id':e,'connected':True,'enabled':True,'alive':True} for e in ('godot','unity','roblox')])
  result=w.pipeline.begin(['godot']);assert result['required'];w.job_thread.join(120);assert w.running,w.error
  pid=w.proc.pid;project=w.project;assert w.status()['verified'] and w.status()['aiTarget'];before=w.last_success['at']
  w.pipeline.begin(['unity']);w.job_thread.join(30);assert w.proc.pid==pid and w.project==project and w.last_success['at']>=before,'Reuses the same worker and project, with a real fresh response'
  w.command('primitive',{'shape':'cube'});godot=root/'godot';godot.mkdir();(godot/'project.godot').write_text('[application]\nconfig/name="Real Blender import QA"\n')
  args={'engine':'godot','project':project,'project_path':str(godot),'name':'Table'}
  g=w.pipeline.handoff(args);file=Path(g['path']);assert file.relative_to(godot).as_posix()=='assets/multiscript/blender/Table.glb';assert file.read_bytes()[:4]==b'glTF';original=file.read_bytes();assert hashlib.sha256(original).hexdigest()==g['sha256'];assert not g['engineImportVerified'];assert (w.folder()/g['assetFile']).read_bytes()==original
  w.command('primitive',{'shape':'sphere'})
  try:w.pipeline.handoff(args)
  except FileExistsError:pass
  else:raise AssertionError('A changed asset cannot overwrite by default')
  assert file.read_bytes()==original
  changed=w.pipeline.handoff(dict(args,overwrite=True));assert file.read_bytes()!=original and not changed['engineImportVerified']
  unity=root/'unity';(unity/'Assets').mkdir(parents=True);(unity/'ProjectSettings').mkdir();(unity/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.0.0f1\n')
  u=w.pipeline.handoff({'engine':'unity','project':project,'project_path':str(unity),'name':'Table'});assert Path(u['path']).relative_to(unity).as_posix()=='Assets/MultiScript/Blender/Table.fbx';assert Path(u['path']).read_bytes().startswith(b'Kaydara FBX Binary');assert u['state']=='copied-awaiting-editor-import'
  r=w.pipeline.handoff({'engine':'roblox','project':project,'name':'Table'});assert r['format']=='glb' and Path(r['path']).read_bytes()[:4]==b'glTF' and r['state']=='ready-to-import';assert not r['engineImportVerified']
  for bad in [dict(args,name='../escape'),dict(args,project='another-project'),dict(args,project_path=str(root/'not-project'))]:
   try:w.pipeline.handoff(bad)
   except (ValueError,RuntimeError,OSError):pass
   else:raise AssertionError('Invalid destination/project/name accepted')
  w.engine_enabled=lambda engine:engine!='godot'
  try:w.pipeline.handoff(args)
  except RuntimeError as e:assert 'Enable'in str(e)
  else:raise AssertionError('Disabled target engine was used')
  w.engine_enabled=lambda engine:True
  w.submit('close');w.job_thread.join(30);assert not w.status()['verified'];w.pipeline.begin(['godot']);w.job_thread.join(120);assert w.project==project and len(w.scene['objects'])==2,'Resume the actual saved project without creating a blank scene'
  restored=Workspace(w.root,0);assert restored.pipeline.settings['engines']==['roblox','unity','godot'];assert restored.pipeline.settings['destinations']['godot']==str(godot)
  print('PASS actual Blender: opt-in companion, offline-editor rejection, singleton reuse and real readiness, saved-project resume, persistent preferences, genuine GLB/FBX game-folder handoff, pinned downloads, overwrite protection, invalid-project/name/destination rejection and engine-disable enforcement. Game-editor imports are not claimed verified.')
 finally:w.close()
