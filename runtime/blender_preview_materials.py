# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake unsupported procedural base color into temporary preview UV textures.

Only copies are edited. Original meshes, UVs, materials, renderer and selection
are restored before the native project is saved. Cache files live in the project.
"""
from contextlib import contextmanager
from pathlib import Path
from array import array
import hashlib,json
import bpy

def complex_color(mat):
    if not mat or not mat.use_nodes:return False
    shader=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
    if not shader:return False
    color=shader.inputs.get('Base Color')
    return bool(color and color.is_linked and color.links[0].from_node.type!='TEX_IMAGE')

def value(socket):
    try:
        v=socket.default_value
        if isinstance(v,(str,int,float,bool)):return v
        return list(v)
    except (AttributeError,TypeError):return None

def fingerprint(obj):
    digest=hashlib.sha256(b'MS-preview-color-v1');coords=array('f',[0.0])*(len(obj.data.vertices)*3);obj.data.vertices.foreach_get('co',coords);digest.update(coords.tobytes())
    loops=array('i',[0])*len(obj.data.loops);obj.data.loops.foreach_get('vertex_index',loops);digest.update(loops.tobytes())
    slots=array('i',[0])*len(obj.data.polygons);obj.data.polygons.foreach_get('material_index',slots);digest.update(slots.tobytes())
    for uv in obj.data.uv_layers:
        coords=array('f',[0.0])*(len(uv.data)*2);uv.data.foreach_get('uv',coords);digest.update(uv.name.encode());digest.update(coords.tobytes())
    records=[]
    for mat in obj.data.materials:
        if not mat:records.append(None);continue
        nodes=[]
        if mat.use_nodes:
            for n in mat.node_tree.nodes:
                r={'name':n.name,'type':n.type,'values':[value(i) for i in n.inputs]}
                for key in ('operation','blend_type','interpolation','noise_dimensions','wave_type','wave_profile','bands_direction','rings_direction'):
                    if hasattr(n,key):r[key]=getattr(n,key)
                if hasattr(n,'color_ramp'):r['ramp']=[(e.position,list(e.color)) for e in n.color_ramp.elements]
                if getattr(n,'image',None):r['image']=[n.image.name,n.image.filepath,list(n.image.size)]
                nodes.append(r)
            links=[(l.from_node.name,l.from_socket.identifier,l.to_node.name,l.to_socket.identifier) for l in mat.node_tree.links]
        else:links=[]
        records.append({'material':mat.name,'color':list(mat.diffuse_color),'nodes':nodes,'links':links})
    digest.update(json.dumps([records,[list(row) for row in obj.matrix_world],bpy.context.scene.frame_current],sort_keys=True,default=str).encode())
    return digest.hexdigest()

@contextmanager
def preview_materials(root):
    scene=bpy.context.scene;records=[];materials=[];images=[];stats={'bakedObjects':0,'cachedObjects':0,'warnings':[]}
    selected=list(bpy.context.selected_objects);active=bpy.context.view_layer.objects.active
    old=(scene.render.engine,scene.cycles.device,scene.cycles.samples,scene.render.bake.use_selected_to_active,scene.render.bake.margin)
    try:
        for obj in list(scene.objects):
            if obj.type!='MESH' or not len(obj.data.polygons) or not any(complex_color(m) for m in obj.data.materials):continue
            original=obj.data;mesh=None
            try:
                key=fingerprint(obj);cache=Path(root)/'preview-material-cache'/(key+'.png');cache.parent.mkdir(parents=True,exist_ok=True)
                original_uv=next((uv.name for uv in original.uv_layers if uv.active_render),None)
                mesh=original.copy();obj.data=mesh
                for o in scene.objects:o.select_set(False)
                obj.select_set(True);bpy.context.view_layer.objects.active=obj
                uv=mesh.uv_layers.get('MSPreviewUV') or mesh.uv_layers.new(name='MSPreviewUV');mesh.uv_layers.active=uv;uv.active_render=True;uv_name=uv.name
                bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(island_margin=.03);bpy.ops.object.mode_set(mode='OBJECT')
                cached=cache.is_file()
                image=bpy.data.images.load(str(cache),check_existing=False) if cached else bpy.data.images.new('MS Preview '+obj.name,width=256,height=256,alpha=False)
                images.append(image);copies=[]
                for index,mat in enumerate(list(original.materials)):
                    cp=mat.copy() if mat else bpy.data.materials.new('MS Preview Material');materials.append(cp);mesh.materials[index]=cp;cp.use_nodes=True;nt=cp.node_tree
                    # A bake UV must not change the artist's original UV-driven
                    # shader inputs. Pin implicit UV users in the material copy.
                    if original_uv:
                        source_uv=nt.nodes.new('ShaderNodeUVMap');source_uv.uv_map=original_uv
                        for node in list(nt.nodes):
                            if node.type=='TEX_IMAGE' and not node.inputs['Vector'].is_linked:nt.links.new(source_uv.outputs['UV'],node.inputs['Vector'])
                            elif node.type=='UVMAP' and node!=source_uv and not node.uv_map:node.uv_map=original_uv
                            elif node.type=='TEX_COORD':
                                for link in list(node.outputs['UV'].links):nt.links.new(source_uv.outputs['UV'],link.to_socket)
                    shader=next((n for n in nt.nodes if n.type=='BSDF_PRINCIPLED'),None)
                    out=next((n for n in nt.nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output),None)
                    if not shader or not out:raise ValueError('Preview bake needs an active Principled material output.')
                    tex=nt.nodes.new('ShaderNodeTexImage');tex.image=image;nt.nodes.active=tex
                    uvnode=nt.nodes.new('ShaderNodeUVMap');uvnode.uv_map=uv_name;nt.links.new(uvnode.outputs['UV'],tex.inputs['Vector'])
                    color=shader.inputs['Base Color'];emit=nt.nodes.new('ShaderNodeEmission')
                    if color.is_linked:nt.links.new(color.links[0].from_socket,emit.inputs['Color'])
                    else:emit.inputs['Color'].default_value=color.default_value
                    nt.links.new(emit.outputs[0],out.inputs['Surface']);copies.append((cp,shader,out,tex,emit))
                if not cached:
                    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1;scene.render.bake.use_selected_to_active=False;scene.render.bake.margin=4
                    bpy.ops.object.bake(type='EMIT');image.filepath_raw=str(cache);image.file_format='PNG';image.save()
                for cp,shader,out,tex,emit in copies:
                    nt=cp.node_tree;nt.links.new(tex.outputs['Color'],shader.inputs['Base Color']);nt.links.new(shader.outputs[0],out.inputs['Surface']);nt.nodes.remove(emit)
                records.append((obj,original,mesh));stats['cachedObjects' if cached else 'bakedObjects']+=1
            except Exception as error:
                if obj.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
                obj.data=original
                if mesh and mesh.users==0:bpy.data.meshes.remove(mesh)
                stats['warnings'].append(obj.name+': '+str(error)[:180])
        yield stats
    finally:
        for obj,original,mesh in records:
            obj.data=original
            if mesh.users==0:bpy.data.meshes.remove(mesh)
        for mat in materials:
            if mat.users==0:bpy.data.materials.remove(mat)
        for image in images:
            if image.users==0:bpy.data.images.remove(image)
        scene.render.engine,scene.cycles.device,scene.cycles.samples,scene.render.bake.use_selected_to_active,scene.render.bake.margin=old
        for o in scene.objects:o.select_set(o in selected)
        bpy.context.view_layer.objects.active=active if active and active.name in bpy.data.objects else None
