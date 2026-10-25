"""Real local service for Playwright tests; never binds a user's normal bridge."""
from pathlib import Path
import sys,json,os,tempfile
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'runtime'))
if os.environ.get('MS_TEST_BLENDER'):os.environ['MS_BLENDER_PATH']=os.environ['MS_TEST_BLENDER']
from blender_workspace import Workspace
with tempfile.TemporaryDirectory(prefix='ms-blender-browser-') as temp:
 w=Workspace(Path(temp),0)
 try:
  url=w.start_http();w.submit('create',{'name':'Browser Integration'});w.job_thread.join(120)
  if not w.running:raise RuntimeError(w.error)
  godot=Path(temp)/'GodotGame';godot.mkdir();(godot/'project.godot').write_text('[application]\nconfig/name="Workspace QA"\n')
  unity=Path(temp)/'UnityGame';(unity/'Assets').mkdir(parents=True);(unity/'ProjectSettings').mkdir();(unity/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.0.0f1\n')
  print('MS_WORKSPACE_READY:'+json.dumps({'url':url,'project':w.project,'godot':str(godot),'unity':str(unity)}),flush=True)
  for line in sys.stdin:
   msg=json.loads(line)
   try:
    if msg['action']=='close':break
    if msg['action']=='animate':
     value=w.command('exec',{'code':"import bpy\no=bpy.data.objects.get('Cube') or next(o for o in bpy.context.scene.objects if o.type=='MESH')\no.location=(0,0,0);o.keyframe_insert(data_path='location',frame=1)\no.location=(3,0,0);o.keyframe_insert(data_path='location',frame=30)\nbpy.context.scene.frame_end=30;bpy.context.scene.frame_set(1)"})
    elif msg['action']=='render':
     w.command('render',{'size':768});raw=(w.folder()/'render.png').read_bytes();value={'signature':raw[:8].hex(),'width':int.from_bytes(raw[16:20],'big'),'bytes':len(raw)}
    elif msg['action']=='snapshot':value=w.command('snapshot')['data']
    elif msg['action']=='status':value=w.status()
    elif msg['action']=='slow':value=w.command('exec',{'code':'import time\ntime.sleep(3)\nprint("Actual Blender operation finished")'})
    elif msg['action']=='procedural':value=w.command('exec',{'code':"o=bpy.data.objects['Cube'];mat=bpy.data.materials.new('Walnut QA');mat.use_nodes=True;o.data.materials.clear();o.data.materials.append(mat)\nnt=mat.node_tree;ramp=nt.nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.08,.025,.005,1);ramp.color_ramp.elements[1].color=(.3,.1,.025,1);noise=nt.nodes.new('ShaderNodeTexNoise');nt.links.new(noise.outputs['Fac'],ramp.inputs['Fac']);nt.links.new(ramp.outputs['Color'],nt.nodes.get('Principled BSDF').inputs['Base Color'])"})
    else:raise ValueError('Unknown test action')
    print('MS_WORKSPACE_REPLY:'+json.dumps({'id':msg['id'],'ok':True,'value':value}),flush=True)
   except Exception as e:print('MS_WORKSPACE_REPLY:'+json.dumps({'id':msg['id'],'ok':False,'error':str(e)}),flush=True)
 finally:w.close()
