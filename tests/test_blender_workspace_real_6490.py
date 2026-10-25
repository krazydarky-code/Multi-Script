"""Real Blender E2E. Requires MS_TEST_BLENDER or an installed/prepared Blender.

No fixture pretends that bpy, glTF export, rendering or persistence succeeded.
"""
from pathlib import Path
import base64,importlib.util,json,os,struct,sys,tempfile,urllib.request,urllib.error
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
if os.environ.get('MS_TEST_BLENDER'):os.environ['MS_BLENDER_PATH']=os.environ['MS_TEST_BLENDER']
import blender_portable
assert blender_portable.discover(),'Prepare Blender before running this real integration suite.'
spec=importlib.util.spec_from_file_location('blender_qa_bridge',ROOT/'runtime/bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
from blender_workspace import Workspace
def gltf(path):
 raw=path.read_bytes();assert raw[:4]==b'glTF';length,kind=struct.unpack_from('<II',raw,12);assert kind==0x4e4f534a;return json.loads(raw[20:20+length])
with tempfile.TemporaryDirectory(prefix='ms-blender-real-') as temp:
 w=Workspace(Path(temp),0);b.BLENDER_WORKSPACE=w;m=b.MCPManager()
 try:
  launch=w.start_http();w.submit('create',{'name':'Verified Model Animation'});w.job_thread.join(120);assert w.running,w.error;pid=w.project
  tools={t['name']:t for t in m.list_tools()};assert 'ms_blender_create_primitive'in tools and 'ms_blender_workspace'in tools
  schema=tools['ms_blender_create_primitive']['inputSchema'];assert schema['properties']['target']['enum']==['auto','connected','workspace']
  def call(name,args):return m.call(name,args,180)
  result=json.loads(call('ms_blender_create_primitive',{'shape':'cube','name':'Hero','target':'workspace','workspace_project':pid})['text']);assert result['ok'] and result['created']['name']=='Hero'
  before_revision=w.scene['revision'];before_source=(w.folder()/'scene.blend').read_bytes()
  summary=json.loads(call('ms_blender_scene_summary',{'target':'auto'})['text']);assert summary['object_counts']['MESH']==1 and summary['file'].endswith('scene.blend')
  assert w.scene['revision']==before_revision and (w.folder()/'scene.blend').read_bytes()==before_source,'Read-only toolkit calls must not save or re-export the whole project'
  call('ms_blender_workspace',{'action':'execute','project':pid,'code':"import bpy\no=bpy.data.objects['Hero']\nmod=o.modifiers.new('Rounded','BEVEL');mod.width=.08;mod.segments=3\no.location=(1,2,3)\no.keyframe_insert(data_path='location',frame=1)\no.location=(4,2,3)\no.keyframe_insert(data_path='location',frame=30)\nbpy.context.scene.frame_end=30\nbpy.context.scene.frame_set(1)\nresult={'bpy':bpy.app.version_string,'file':bpy.data.filepath}\n"})
  saved=w.folder()/'scene.blend';assert saved.stat().st_size>1000
  preview=gltf(w.folder()/'preview.glb');assert preview.get('meshes') and preview.get('animations') and len(preview['animations'][0]['channels'])>=1
  assert next(o for o in w.scene['objects'] if o['name']=='Hero')['action']
  positions=[preview['accessors'][primitive['attributes']['POSITION']]['count'] for mesh in preview['meshes'] for primitive in mesh['primitives']];assert max(positions)>24,'Bevel modifier must reach the actual preview geometry without changing the .blend'
  call('ms_blender_workspace',{'action':'execute','code':"import bpy\nbpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8)\nmesh=bpy.context.object;mesh.name='RiggedMorph'\nmesh.shape_key_add(name='Basis');shape=mesh.shape_key_add(name='Stretch')\nfor v in shape.data:v.co.z*=1.3\nshape.value=0;shape.keyframe_insert(data_path='value',frame=1);shape.value=1;shape.keyframe_insert(data_path='value',frame=15)\nbpy.ops.object.armature_add();rig=bpy.context.object;rig.name='Rig';mesh.parent=rig\nmod=mesh.modifiers.new('Skin','ARMATURE');mod.object=rig\ngroup=mesh.vertex_groups.new(name=rig.data.bones[0].name);group.add(list(range(len(mesh.data.vertices))),1,'REPLACE')\nbone=rig.pose.bones[0];bone.rotation_mode='XYZ';bone.keyframe_insert(data_path='rotation_euler',frame=1);bone.rotation_euler.z=.5;bone.keyframe_insert(data_path='rotation_euler',frame=15)\nbpy.context.scene.frame_set(1)"})
  rigged=gltf(w.folder()/'preview.glb');paths={c['target']['path'] for clip in rigged.get('animations',[]) for c in clip['channels']};assert rigged.get('skins') and 'rotation'in paths and 'weights'in paths,'Actual glTF must contain skinning, bone rotation and morph animation'
  # Error after a real mutation must restore the committed project.
  try:call('ms_blender_workspace',{'action':'execute','code':"bpy.data.objects['Hero'].name='Uncommitted'\nraise RuntimeError('Intentional rollback check')"})
  except RuntimeError as e:assert 'Intentional rollback check'in str(e)
  else:raise AssertionError('A failed Blender operation must fail its tool result')
  assert any(o['name']=='Hero' for o in w.command('snapshot')['data']['objects'])
  # UI world-space Y up maps to Blender Z up, including a parented object.
  call('ms_blender_workspace',{'action':'execute','code':"import bpy\nbpy.ops.object.empty_add(location=(2,0,0))\np=bpy.context.object;p.name='Parent'\no=bpy.data.objects['Hero'];o.animation_data_clear();o.parent=p;o.location=(1,2,3)\nbpy.context.view_layer.update()"})
  three_matrix=[1,0,0,0,0,1,0,0,0,0,1,0,7,5,-9,1]
  w.command('transform',{'name':'Hero','world_matrix':three_matrix,'project':pid})
  hero=next(o for o in w.scene['objects'] if o['name']=='Hero');actual=hero['matrix_world'][12:15];assert all(abs(a-v)<.001 for a,v in zip(actual,[7,9,5])),actual
  call('ms_blender_workspace',{'action':'execute','code':"bpy.data.objects['Hero'].rotation_mode='QUATERNION'"})
  w.command('transform',{'name':'Hero','rotation_deg':[20,30,45],'auto_key':True,'frame':1})
  hero=next(o for o in w.scene['objects'] if o['name']=='Hero');assert hero['rotation_mode']=='QUATERNION' and all(abs(v-e)<.01 for v,e in zip(hero['rotation_deg'],[20,30,45])),'Inspector transforms must preserve native quaternion animation mode'
  # Mismatched project IDs are rejected before a real native call.
  stale=json.loads(call('ms_blender_scene_summary',{'target':'workspace','workspace_project':'different-project'})['text']);assert not stale['ok'] and 'project changed'in stale['error']
  # Explicit connected means connected, even while workspace is selected.
  external=json.loads(call('ms_blender_scene_summary',{'target':'connected'})['text']);assert not external['ok'] and ('unknown MCP server' in external['error'] or 'does not advertise'in external['error'])
  settings_code="sc=bpy.context.scene\nresult={'engine':sc.render.engine,'x':sc.render.resolution_x,'y':sc.render.resolution_y,'samples':sc.cycles.samples,'camera':sc.camera.name if sc.camera else None}"
  before_settings=w.command('exec',{'code':settings_code,'read_only':True})['data']['result']
  rendered=call('ms_blender_workspace',{'action':'render','size':256,'project':pid});assert len(rendered['images'])==1
  after_settings=w.command('exec',{'code':settings_code,'read_only':True})['data']['result'];assert before_settings==after_settings,'Preview rendering must restore the artist render settings and camera'
  png=base64.b64decode(rendered['images'][0]['data']);assert png.startswith(b'\x89PNG\r\n\x1a\n') and len(png)>1000
  for fmt in ('glb','fbx','blend'):
   result=json.loads(call('ms_blender_workspace',{'action':'export','format':fmt})['text']);assert (w.folder()/result['data']['file']).stat().st_size>100
  w._stop();w._open(pid);assert next(o for o in w.scene['objects'] if o['name']=='Hero')['parent']=='Parent'
  # Actual HTTP surface: single-use launch key, same-origin writes, cookies,
  # DNS-rebinding rejection, private assets and project path boundaries.
  origin=w.status()['url'].rstrip('/');key=launch.split('#launch=')[1]
  def request(path,body=None,headers=None):
   h={'Origin':origin,**(headers or {})};req=urllib.request.Request(origin+path,data=json.dumps(body).encode() if body is not None else None,headers=h)
   try:
    with urllib.request.urlopen(req,timeout=10) as r:return r.status,r.read(),r.headers
   except urllib.error.HTTPError as e:return e.code,e.read(),e.headers
  assert request('/api/status')[0]==403
  status,raw,headers=request('/api/session',{'key':key});assert status==200;cookie=headers['Set-Cookie'].split(';')[0];auth={'Cookie':cookie}
  assert 'HttpOnly'in headers['Set-Cookie'] and 'SameSite=Strict'in headers['Set-Cookie']
  assert request('/api/session',{'key':key})[0]==403
  assert request('/api/status',headers=auth)[0]==200
  assert request('/api/command',{'op':'primitive','args':{'project':pid}},dict(auth,Origin='https://untrusted.example'))[0]==403
  assert request('/api/status',headers=dict(auth,Host='untrusted.example'))[0]==403
  assert request('/api/asset/'+pid+'/scene.blend',headers=auth)[0]==200
  assert request('/api/asset/../state.json',headers=auth)[0]!=200
  assert request('/api/command',{'op':'primitive','args':{'project':'stale-project'}},auth)[0]==400
  assert request('/api/command',{'op':'exec','args':{'project':pid,'code':'print(1)'}},auth)[0]==400,'Browser UI does not expose arbitrary Python execution'
  m.disabled={'blender'}
  try:call('ms_blender_workspace',{'action':'execute','code':'print(1)'})
  except RuntimeError as e:assert 'off'in str(e).lower() or 'disabled'in str(e).lower()
  else:raise AssertionError('Disabled engine must stay disabled')
  print('PASS real Blender: exact existing toolkit/schema routing, headless bpy edits, keyframes and GLB animation, Cycles PNG, .blend persistence, error rollback, Y-up/Z-up parent transforms, connected/workspace separation, stale-project guards, export formats, HTTP/auth/path isolation and engine disable.')
 finally:w.close()
