# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-only main-thread worker. All bpy operations run on this thread.

The loopback socket requires a per-process secret. No add-on or open desktop
Blender window is required. A failed edit reloads the last committed .blend.
"""
import argparse,contextlib,io,json,math,os,secrets,socket,sys,time,traceback
from pathlib import Path
import bpy
from mathutils import Matrix,Vector,Euler
sys.path.insert(0,str(Path(__file__).resolve().parent))
from blender_preview_materials import preview_materials
from blender_worker_lifecycle import watch_owner,lock_project

parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--ready',required=True);parser.add_argument('--owner-pid',type=int)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
ROOT=Path(args.project).resolve();ROOT.mkdir(parents=True,exist_ok=True)
watch_owner(args.owner_pid)
PROJECT_LOCK=lock_project(ROOT)
TOKEN=os.environ.pop('MS_BLENDER_WORKER_TOKEN');REVISION=0
PREVIEW_INFO={};PREVIEW_ERROR=''
C=Matrix.Rotation(-math.pi/2,4,'X')

def local_path(name):
    if not isinstance(name,str) or not name or '\\' in name:raise ValueError('Use a relative project filename.')
    p=(ROOT/name).resolve()
    if not p.is_relative_to(ROOT) or p==ROOT:raise ValueError('Path leaves this Blender project.')
    return p

def snapshot():
    sc=bpy.context.scene;objects=[]
    for o in sc.objects:
        objects.append({'name':o.name,'type':o.type,'parent':o.parent.name if o.parent else None,
            'location':list(o.location),'rotation_deg':[math.degrees(v) for v in o.matrix_basis.to_euler('XYZ')],'rotation_mode':o.rotation_mode,'scale':list(o.scale),
            'matrix_world':[o.matrix_world[row][col] for col in range(4) for row in range(4)],
            'vertices':len(o.data.vertices) if o.type=='MESH' else 0,'polygons':len(o.data.polygons) if o.type=='MESH' else 0,
            'modifiers':[{'name':m.name,'type':m.type} for m in o.modifiers],
            'materials':[slot.material.name for slot in o.material_slots if slot.material],
            'color':list(o.active_material.diffuse_color) if o.active_material else [.55,.6,.7,1],
            'action':o.animation_data.action.name if o.animation_data and o.animation_data.action else None})
    return {'backend':'Blender '+bpy.app.version_string,'project':ROOT.name,'revision':REVISION,'objects':objects,
        'frames':{'start':sc.frame_start,'end':sc.frame_end,'current':sc.frame_current,'fps':sc.render.fps/sc.render.fps_base},
        'actions':[a.name for a in bpy.data.actions],
        'source':'scene.blend','preview':'preview.glb','previewMaterials':PREVIEW_INFO,'previewError':PREVIEW_ERROR,'previewContract':'glTF preview supports meshes, PBR, rigs, morphs and exported animation. Procedural base colors are baked for preview; use a Blender render for exact shader/effect fidelity.'}

def export_glb(path):
    global PREVIEW_INFO
    # Blender's export_apply option removes shape keys globally. Bake only
    # non-morph geometry into temporary data so bevel/subdivision previews and
    # separate skinned/morph meshes can coexist without changing the .blend.
    temporary=[]
    try:
        for o in list(bpy.context.scene.objects):
            if o.type!='MESH' or o.data.shape_keys or not any(m.type!='ARMATURE' and m.show_viewport for m in o.modifiers):continue
            original=o.data;visibility=[(m,m.show_viewport) for m in o.modifiers]
            try:
                for m,_ in visibility:
                    if m.type=='ARMATURE':m.show_viewport=False
                bpy.context.view_layer.update()
                mesh=bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()),preserve_all_data_layers=True,depsgraph=bpy.context.evaluated_depsgraph_get())
            finally:
                for m,on in visibility:m.show_viewport=on
            temporary.append((o,original,mesh,visibility));o.data=mesh
            for m,_ in visibility:
                if m.type!='ARMATURE':m.show_viewport=False
        bpy.context.view_layer.update()
        with preview_materials(ROOT) as info:
            bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',export_animations=True,export_frame_range=True,export_extras=True,export_cameras=False,export_lights=False,export_apply=False)
            PREVIEW_INFO=info
    finally:
        for o,original,mesh,visibility in temporary:
            o.data=original
            for m,on in visibility:m.show_viewport=on
            if mesh.users==0:bpy.data.meshes.remove(mesh)
        bpy.context.view_layer.update()

def publish():
    global REVISION,PREVIEW_ERROR
    if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.context.scene.objects:o['ms_object_name']=o.name
    source=ROOT/'scene.blend';preview=ROOT/'pending.glb'
    transforms=[(o,o.matrix_basis.copy()) for o in bpy.context.scene.objects]
    bones=[(b,b.matrix_basis.copy()) for o in bpy.context.scene.objects if o.type=='ARMATURE' for b in o.pose.bones]
    # The editable native project is authoritative; a preview failure must not
    # discard a successfully built model or make refresh look like data loss.
    bpy.ops.wm.save_as_mainfile(filepath=str(source),check_existing=False,compress=True)
    PREVIEW_ERROR=''
    try:
        export_glb(preview);os.replace(preview,ROOT/'preview.glb')
    except Exception as error:PREVIEW_ERROR='Saved the .blend, but preview export failed: '+str(error)[:500]
    finally:
        for o,matrix in transforms:o.matrix_basis=matrix
        for b,matrix in bones:b.matrix_basis=matrix
        bpy.context.view_layer.update()
    # Readers acquire the manager operation lock; snapshot is the final receipt.
    REVISION+=1;state=snapshot();tmp=ROOT/'snapshot.pending.json';tmp.write_text(json.dumps(state,allow_nan=False));os.replace(tmp,ROOT/'snapshot.json')
    return state

def open_saved():
    global REVISION
    if (ROOT/'scene.blend').exists():
        bpy.ops.wm.open_mainfile(filepath=str(ROOT/'scene.blend'),load_ui=False,use_scripts=False)
        try:REVISION=json.loads((ROOT/'snapshot.json').read_text())['revision']
        except (OSError,KeyError,ValueError):pass
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True);bpy.context.scene.frame_end=120
        world=bpy.data.worlds.new('Multi-Script World');world.color=(.08,.08,.08);bpy.context.scene.world=world

def find(name):
    o=bpy.context.scene.objects.get(name or '')
    if o is None:raise ValueError('Object not found: '+str(name))
    return o

def finite_list(value,length):
    if not isinstance(value,list) or len(value)!=length or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in value):raise ValueError('Expected '+str(length)+' finite numbers.')
    return value

def rotation_channel(o):return 'rotation_quaternion' if o.rotation_mode=='QUATERNION' else 'rotation_axis_angle' if o.rotation_mode=='AXIS_ANGLE' else 'rotation_euler'

def render(a):
    sc=bpy.context.scene;temporary=[];old_camera=sc.camera
    render_settings={k:getattr(sc.render,k) for k in ('engine','resolution_x','resolution_y','resolution_percentage','filepath')}
    old_format=sc.render.image_settings.file_format;old_device=sc.cycles.device;old_samples=sc.cycles.samples
    preview_lights=not any(o.type=='LIGHT' for o in sc.objects) and not (sc.world and sc.world.use_nodes)
    try:
        if sc.camera is None:
            points=[o.matrix_world@Vector(v) for o in sc.objects if o.type=='MESH' for v in o.bound_box]
            low=Vector(tuple(min(p[i] for p in points) for i in range(3))) if points else Vector((-1,-1,-1))
            high=Vector(tuple(max(p[i] for p in points) for i in range(3))) if points else Vector((1,1,1))
            center=(low+high)/2;radius=max((high-low).length,.5)
            data=bpy.data.cameras.new('MS Preview Camera');camera=bpy.data.objects.new('MS Preview Camera',data);sc.collection.objects.link(camera);temporary.append(camera)
            camera.location=center+Vector((1,-1,.8)).normalized()*radius*1.6;camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler();sc.camera=camera
        for pos,power in ([((4,-4,7),1100),((-4,1,4),700)] if preview_lights else []):
            data=bpy.data.lights.new('MS Preview Light','AREA');data.energy=power;data.shape='DISK';data.size=5
            lamp=bpy.data.objects.new('MS Preview Light',data);sc.collection.objects.link(lamp);lamp.location=pos;lamp.rotation_euler=(-lamp.location).to_track_quat('-Z','Y').to_euler();temporary.append(lamp)
        sc.render.engine='CYCLES';sc.cycles.device='CPU';sc.cycles.samples=12
        sc.render.resolution_x=sc.render.resolution_y=max(128,min(1024,int(a.get('size',512))));sc.render.resolution_percentage=100
        sc.render.image_settings.file_format='PNG';sc.render.filepath=str(ROOT/'render.png')
        bpy.ops.render.render(write_still=True)
        return {'render':'render.png','frame':sc.frame_current,'renderer':'Cycles CPU','bytes':(ROOT/'render.png').stat().st_size,'temporaryCamera':old_camera is None,'previewLighting':preview_lights}
    finally:
        sc.camera=old_camera
        for key,value in render_settings.items():setattr(sc.render,key,value)
        sc.render.image_settings.file_format=old_format;sc.cycles.device=old_device;sc.cycles.samples=old_samples
        for o in temporary:
            data=o.data;bpy.data.objects.remove(o,do_unlink=True)
            if data.users==0:
                if isinstance(data,bpy.types.Camera):bpy.data.cameras.remove(data)
                elif isinstance(data,bpy.types.Light):bpy.data.lights.remove(data)

def perform(op,a):
    if op=='snapshot':return snapshot()
    if op=='render':return render(a)
    if op=='frame':
        frame=int(a['frame']);sc=bpy.context.scene
        if not sc.frame_start<=frame<=sc.frame_end:raise ValueError('Frame is outside the project range.')
        sc.frame_set(frame);return snapshot()
    if op=='exec':
        code=a.get('code')
        if not isinstance(code,str) or not code.strip() or len(code)>200000:raise ValueError('Provide Python code (maximum 200,000 characters).')
        ns={'bpy':bpy,'math':math,'json':json,'__name__':'__multiscript__','MS_PROJECT':str(ROOT)}
        exec(compile(code,'<Multi-Script Blender>','exec'),ns,ns)
        if isinstance(ns.get('R'),dict) and ns['R'].get('ok') is False:raise RuntimeError(ns['R'].get('error','Blender toolkit operation failed.'))
        result=ns.get('result');json.dumps(result,allow_nan=False)
        if a.get('read_only'):return {'result':result,'readOnly':True}
    elif op=='primitive':
        shape=a.get('shape','cube');operations={'cube':'primitive_cube_add','sphere':'primitive_uv_sphere_add','cylinder':'primitive_cylinder_add','torus':'primitive_torus_add','plane':'primitive_plane_add','monkey':'primitive_monkey_add'}
        if shape not in operations:raise ValueError('Unsupported primitive.')
        getattr(bpy.ops.mesh,operations[shape])();o=bpy.context.object
        if a.get('name'):o.name=str(a['name'])[:100]
        result={'created':o.name}
    elif op=='transform':
        o=find(a.get('name'))
        if a.get('auto_key') and 'frame'in a:bpy.context.scene.frame_set(int(a['frame']))
        if 'world_matrix' in a:
            values=finite_list(a['world_matrix'],16);m=Matrix([values[i::4] for i in range(4)]);o.matrix_world=C.inverted()@m@C
        else:
            for prop in ['location','scale']:
                if prop in a:setattr(o,prop,finite_list(a[prop],3))
            if 'rotation_deg'in a:
                rotation=Euler([math.radians(x) for x in finite_list(a['rotation_deg'],3)],'XYZ')
                if o.rotation_mode=='QUATERNION':o.rotation_quaternion=rotation.to_quaternion()
                elif o.rotation_mode=='AXIS_ANGLE':
                    axis,angle=rotation.to_quaternion().to_axis_angle();o.rotation_axis_angle=(angle,*axis)
                else:o.rotation_euler=rotation.to_quaternion().to_euler(o.rotation_mode)
        bpy.context.view_layer.update();result={'updated':o.name}
        if a.get('auto_key'):
            for channel in ('location',rotation_channel(o),'scale'):o.keyframe_insert(data_path=channel,frame=bpy.context.scene.frame_current)
    elif op=='material':
        o=find(a.get('name'));rgba=finite_list(a.get('color'),4)
        if any(v<0 or v>1 for v in rgba):raise ValueError('Material color components must be between 0 and 1.')
        mat=o.active_material
        if mat is None:
            mat=bpy.data.materials.new(o.name+' Material');o.data.materials.append(mat)
        mat.use_nodes=True;mat.diffuse_color=rgba
        shader=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
        if shader:shader.inputs['Base Color'].default_value=rgba
        result={'material':mat.name}
    elif op=='keyframe':
        o=find(a.get('name'));frame=int(a.get('frame',bpy.context.scene.frame_current));channel=a.get('channel','location')
        if channel not in ['location','rotation_euler','scale']:raise ValueError('Use location, rotation_euler or scale.')
        if channel=='rotation_euler':channel=rotation_channel(o)
        if frame<-100000 or frame>100000:raise ValueError('Invalid keyframe.')
        o.keyframe_insert(data_path=channel,frame=frame);result={'keyframe':frame,'object':o.name,'channel':channel}
    elif op=='delete':
        o=find(a.get('name'));name=o.name;bpy.data.objects.remove(o,do_unlink=True);result={'deleted':name}
    elif op=='import':
        path=local_path(a['file'])
        if path.suffix.lower()=='.blend':bpy.ops.wm.open_mainfile(filepath=str(path),load_ui=False,use_scripts=False)
        elif path.suffix.lower() in ('.glb','.gltf'):bpy.ops.import_scene.gltf(filepath=str(path))
        else:raise ValueError('Import .blend or self-contained .glb.')
        result={'imported':path.name}
    elif op=='export':
        fmt=a.get('format','glb');path=local_path('export.'+fmt)
        if fmt=='blend':bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=False,compress=True)
        elif fmt=='glb':export_glb(path)
        elif fmt=='fbx':bpy.ops.export_scene.fbx(filepath=str(path),bake_anim=True)
        else:raise ValueError('Use blend, glb or fbx.')
        return {'file':path.name,'bytes':path.stat().st_size}
    else:raise ValueError('Unknown Blender operation: '+op)
    return {'result':result,'scene':publish()}

open_saved()
with contextlib.redirect_stdout(io.StringIO()):publish()
sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(4);sock.settimeout(1)
ready=Path(args.ready);ready.write_text(json.dumps({'port':sock.getsockname()[1],'pid':os.getpid()}))
try:
    running=True
    while running:
        try:conn,_=sock.accept()
        except socket.timeout:continue
        with conn:
            conn.settimeout(20);raw=b''
            try:
                while b'\n' not in raw and len(raw)<=1_000_000:
                    chunk=conn.recv(min(65536,1_000_001-len(raw)))
                    if not chunk:break
                    raw+=chunk
                if len(raw)>1_000_000:raise ValueError('Request too large.')
                request=json.loads(raw.split(b'\n',1)[0])
                if not secrets.compare_digest(str(request.get('token','')),TOKEN):raise PermissionError('Invalid worker token.')
                op=request.get('op');a=request.get('args') or {};log=io.StringIO()
                if op=='close':running=False;answer={'ok':True}
                else:
                    try:
                        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):result=perform(op,a)
                        answer={'ok':True,'data':result,'output':log.getvalue()[-2000000:]}
                    except Exception:
                        error=traceback.format_exc()[-10000:]
                        mutation=op not in ('snapshot','frame','render','export') and not (op=='exec' and a.get('read_only'))
                        if mutation:
                            with contextlib.redirect_stdout(io.StringIO()):open_saved()
                        answer={'ok':False,'error':error,'output':log.getvalue()[-10000:],'sceneRolledBack':mutation}
                conn.sendall(json.dumps(answer,allow_nan=False).encode()+b'\n')
            except Exception as e:
                try:conn.sendall(json.dumps({'ok':False,'error':str(e)}).encode()+b'\n')
                except OSError:pass
finally:
    sock.close();ready.unlink(missing_ok=True);PROJECT_LOCK.close()
