"""Actual procedural-color bake, native persistence and optional real Godot import."""
from pathlib import Path
import io,json,os,struct,subprocess,sys,tempfile
from PIL import Image,ImageStat
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
from blender_workspace import Workspace
import blender_portable
assert blender_portable.discover(),'Prepare real Blender before this suite.'
def glb(path):
    raw=path.read_bytes();size,kind=struct.unpack_from('<II',raw,12);assert kind==0x4e4f534a
    doc=json.loads(raw[20:20+size]);offset=20+size;length,kind=struct.unpack_from('<II',raw,offset);assert kind==0x004e4942
    return doc,raw[offset+8:offset+8+length]
with tempfile.TemporaryDirectory(prefix='ms-preview-color-') as temp:
    root=Path(temp);w=Workspace(root/'workspace',0)
    try:
        w._create('Colored model');pid=w.project
        w.command('exec',{'code':'''bpy.ops.mesh.primitive_cube_add()
o=bpy.context.object;o.name='Walnut'
mat=bpy.data.materials.new('Procedural walnut');mat.use_nodes=True;o.data.materials.append(mat)
nt=mat.node_tree;shader=nt.nodes.get('Principled BSDF');noise=nt.nodes.new('ShaderNodeTexNoise');ramp=nt.nodes.new('ShaderNodeValToRGB')
ramp.color_ramp.elements[0].color=(.06,.018,.004,1);ramp.color_ramp.elements[1].color=(.3,.1,.025,1)
nt.links.new(noise.outputs['Fac'],ramp.inputs['Fac']);nt.links.new(ramp.outputs['Color'],shader.inputs['Base Color'])
o.keyframe_insert(data_path='location',frame=1);o.location.z=1;o.keyframe_insert(data_path='location',frame=20)
bpy.context.scene.frame_end=20;bpy.context.scene.frame_set(1)
result={'originalUVs':[uv.name for uv in o.data.uv_layers]}
'''})
        assert not w.scene['previewError'] and w.scene['previewMaterials']['bakedObjects']==1,w.scene
        doc,binary=glb(w.folder()/'preview.glb');assert doc.get('animations') and doc.get('images')
        image=doc['images'][0];view=doc['bufferViews'][image['bufferView']];start=view.get('byteOffset',0)
        rgb=Image.open(io.BytesIO(binary[start:start+view['byteLength']])).convert('RGB');means=ImageStat.Stat(rgb).mean
        assert means[0]>means[1]*1.3 and means[1]>means[2]*1.2,means
        inspect="o=bpy.data.objects['Walnut'];result={'uvs':[u.name for u in o.data.uv_layers],'materials':[m.name for m in o.data.materials],'colorNode':o.active_material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].links[0].from_node.type,'objects':len(bpy.context.scene.objects)}"
        native=w.command('exec',{'code':inspect,'read_only':True})['data']['result']
        assert native['uvs']==['UVMap'] and native['materials']==['Procedural walnut'] and native['colorNode']=='VALTORGB' and native['objects']==1,native
        w.command('exec',{'code':'result=True'});assert w.scene['previewMaterials']['cachedObjects']==1
        # Induce a genuine preview exporter failure without a production test hook.
        w.command('exec',{'code':"import inspect\nworker=inspect.currentframe().f_back.f_globals\nworker['_qa_export']=worker['export_glb']\ndef fail_preview(path):raise RuntimeError('QA preview exporter failure')\nworker['export_glb']=fail_preview\nbpy.data.objects['Walnut'].location.x=4"})
        assert 'QA preview exporter failure'in w.scene['previewError'];assert (w.folder()/'scene.blend').stat().st_size>1000
        w._stop();restored=Workspace(w.root,0);status=restored.status()
        assert not status['running'] and status['savedProject'] and len(status['scene']['objects'])==1
        assert next(o for o in status['scene']['objects'] if o['name']=='Walnut')['location'][0]==4,'Saved model survives a failed preview and manager restart'
        restored._open(pid);w=restored;assert not w.scene['previewError'] and w.scene['previewMaterials']['cachedObjects']==1
        godot=os.environ.get('MS_TEST_GODOT')
        if godot:
            project=root/'godot';project.mkdir();(project/'project.godot').write_text('[application]\nconfig/name="Native import QA"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
            receipt=w.pipeline.handoff({'engine':'godot','project':pid,'project_path':str(project),'name':'Walnut'})
            (project/'verify.gd').write_text('''extends SceneTree
var meshes=0
var textured=0
var animations=0
func visit(node):
    if node is MeshInstance3D:
        meshes+=1
        for i in node.mesh.get_surface_count():
            var mat=node.mesh.surface_get_material(i)
            if mat is BaseMaterial3D and mat.albedo_texture!=null: textured+=1
    if node is AnimationPlayer:
        animations+=node.get_animation_list().size()
    for child in node.get_children(): visit(child)
func _initialize():
    var scene=load("res://assets/multiscript/blender/Walnut.glb") as PackedScene
    if scene==null: quit(2);return
    var instance=scene.instantiate()
    visit(instance)
    print("MS_GODOT_IMPORT:",JSON.stringify({"meshes":meshes,"textured":textured,"animations":animations}))
    instance.free()
    quit(0 if meshes>0 and textured>0 and animations>0 else 3)
''')
            def run(*args):
                r=subprocess.run([godot,'--headless','--path',str(project),*args],capture_output=True,text=True,timeout=90)
                assert r.returncode==0,r.stdout+'\n'+r.stderr;return r.stdout
            run('--editor','--import');output=run('--script','res://verify.gd');assert 'MS_GODOT_IMPORT:'in output;print(output.strip())
            assert receipt['engineImportVerified'] is False,'Handoff itself must not invent import proof'
        else:print('Real Godot import not requested; run with MS_TEST_GODOT for editor verification.')
        print('PASS real procedural walnut color texture, animation, original shader/UV preservation, cache reuse, native-save-before-preview failure, stopped-worker snapshot restoration and saved-model restart.')
    finally:w.close()
