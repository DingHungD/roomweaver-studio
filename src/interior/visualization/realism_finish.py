"""Bounded render-only material finishing and native evidence for look development."""
import math
import bpy
from mathutils import Vector


def eligible(material):
    if not material or not material.use_nodes:return False
    nodes=material.node_tree.nodes
    shaders=[n for n in nodes if n.type=='BSDF_PRINCIPLED']
    if len(shaders)!=1 or any(n.type in ('BSDF_GLASS','BSDF_GLOSSY','BSDF_REFRACTION','MIX_SHADER','ADD_SHADER','EMISSION') or (n.type=='GROUP' and any(s.type=='SHADER' for s in n.outputs)) for n in nodes):return False
    p=shaders[0]
    for name in ('Metallic','Transmission Weight'):
        socket=p.inputs.get(name)
        if socket and (socket.is_linked or socket.default_value>.01):return False
    if p.inputs['Alpha'].is_linked or p.inputs['Alpha'].default_value<.999:return False
    emission=p.inputs['Emission Color'];strength=p.inputs['Emission Strength']
    if strength.is_linked or (strength.default_value>.01 and (emission.is_linked or max(emission.default_value[:3])>.001)):return False
    return True


def apply_finish(obj, spec):
    """Copy local data/trees; wrap linked colors/normals, never discard a texture."""
    if not obj.data.materials or not any(eligible(m) for m in obj.data.materials):
        raise ValueError('材質含玻璃、金屬、發光或複合節點，保留原材質：'+obj.name)
    obj.data=obj.data.copy()
    for slot in obj.material_slots:
        if not eligible(slot.material):continue
        mat=slot.material.copy();slot.material=mat;nodes=mat.node_tree.nodes;links=mat.node_tree.links
        p=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
        if spec.get('albedo_gain',[1,1,1])!=[1,1,1]:
            socket=p.inputs['Base Color'];mix=nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1
            mix.inputs[2].default_value=(*spec['albedo_gain'],1)
            if socket.is_linked:links.new(socket.links[0].from_socket,mix.inputs[1])
            else:mix.inputs[1].default_value=socket.default_value
            links.new(mix.outputs[0],socket)
        delta=spec.get('roughness_delta',0)
        if delta:
            socket=p.inputs['Roughness'];add=nodes.new('ShaderNodeMath');add.operation='ADD';add.use_clamp=True;add.inputs[1].default_value=delta
            if socket.is_linked:links.new(socket.links[0].from_socket,add.inputs[0])
            else:add.inputs[0].default_value=socket.default_value
            links.new(add.outputs[0],socket)
        for node in list(nodes):
            if node.type=='BUMP':
                strength=node.inputs['Strength'];factor=spec.get('bump_factor',1)
                if strength.is_linked:
                    multiply=nodes.new('ShaderNodeMath');multiply.operation='MULTIPLY';multiply.inputs[1].default_value=factor
                    links.new(strength.links[0].from_socket,multiply.inputs[0]);links.new(multiply.outputs[0],strength)
                else:strength.default_value*=factor
        if spec.get('bevel',0):
            node=nodes.new('ShaderNodeBevel');node.inputs['Radius'].default_value=spec['bevel'];node.samples=4
            if p.inputs['Normal'].is_linked:links.new(p.inputs['Normal'].links[0].from_socket,node.inputs['Normal'])
            links.new(node.outputs['Normal'],p.inputs['Normal'])
        from realism_details import surface_detail
        surface_detail(mat,p,spec)


def inventory(design, point_id, by_id, include_cameras=True):
    """Ray-sampled local visibility avoids treating 'unpartitioned interior' as one room."""
    point=next(p for p in design['viewpoints'] if p['id']==point_id)
    eyes=[point['eye']]+[s.get('eye') or point['eye'] for s in point['shots']]
    scene=bpy.context.scene;graph=bpy.context.evaluated_depsgraph_get();visible=set()
    for eye in eyes:
        for j in range(12):
            pitch=math.pi*((j+.5)/12-.5)
            for i in range(48):
                yaw=i*math.tau/48;direction=Vector((math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),math.sin(pitch)))
                hit,_,_,_,obj,_=scene.ray_cast(graph,Vector(eye),direction,distance=6)
                if hit and obj and not obj.hide_render:visible.add(obj.get('studio_id'))
    assignments={o['id']:o for o in design['objects']};groups={c:g for g in design['groups'] for c in g['children']}
    regions={}
    for shot in point['shots']:
        yaw,pitch=math.radians(shot['yaw']),math.radians(shot['pitch'])
        forward=Vector((math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),math.sin(pitch)))
        rotation=forward.to_track_quat('-Z','Y');right=rotation@Vector((1,0,0));up=rotation@Vector((0,1,0))
        extent=36/(2*shot['lens']);eye=Vector(shot.get('eye') or point['eye']);samples={}
        for row in range(24):
            for col in range(32):
                u,v=(col+.5)/32,(row+.5)/24
                direction=(forward+right*((u*2-1)*extent)+up*((1-v*2)*extent*(.5625 if shot.get('aspect')=='16:9' else .75)+shot.get("shift_y",0)*extent*2)).normalized()
                hit,_,_,_,obj,_=scene.ray_cast(graph,eye,direction,distance=6)
                if hit and obj and not obj.hide_render:
                    key=obj.get('studio_id');samples.setdefault(key,[]).append([round(u,3),round(v,3)]);visible.add(key)
        for key,xy in samples.items():
            regions.setdefault(key,[]).append(dict(file=point['id']+'-'+shot['id']+'.png',sample_uv=xy,center_uv=[sum(p[i] for p in xy)/len(xy) for i in (0,1)],bounds_uv=[min(p[0] for p in xy),min(p[1] for p in xy),max(p[0] for p in xy),max(p[1] for p in xy)],hits=len(xy)))
    objects=[]
    for key in sorted(v for v in visible if v in by_id and v in assignments):
        obj=by_id[key];group=groups[key];materials=[]
        for m in obj.data.materials:
            nodes=list(m.node_tree.nodes) if m and m.use_nodes else []
            principled=next((n for n in nodes if n.type=='BSDF_PRINCIPLED'),None)
            base=principled.inputs['Base Color'] if principled else None
            # Follow only our bounded color wrappers; never pretend to measure a texture.
            for _ in range(8):
                if not base or not base.is_linked:break
                upstream=base.links[0].from_node
                if upstream.type!='MIX_RGB' or upstream.blend_type!='MULTIPLY':break
                base=upstream.inputs[1]
            emission=[]
            for node in nodes:
                if node.type not in ('EMISSION','BSDF_PRINCIPLED'):continue
                strength=node.inputs.get('Strength') or node.inputs.get('Emission Strength')
                color=node.inputs.get('Color') or node.inputs.get('Emission Color')
                if strength and not strength.is_linked and strength.default_value>.01 and color:
                    emission.append(dict(strength=strength.default_value,color=None if color.is_linked else list(color.default_value[:3])))
            materials.append(dict(base_color_linear=None if not base or base.is_linked else list(base.default_value[:3]),emission=emission,name=m.name if m else None,editable=eligible(m),textures=[n.image.name for n in nodes if n.type=='TEX_IMAGE' and n.image],bumps=sum(n.type=='BUMP' for n in nodes)))
        protected=(group.get('object_specification') or {}).get('material_policy') in ('original','specified')
        objects.append(dict(id=key,name=obj.name,group_id=group['id'],group_name=group['name'],protected=protected,editable=any(m['editable'] for m in materials) and not protected,materials=materials,screen_regions=regions.get(key,[]),finish=assignments[key]['material'].get('render_finish'),generated=group.get('generated_reference')))
    lights=[]
    for spec in design.get('lighting_setup',{}).get('lights',[]):
        obj=next((o for o in scene.objects if o.get('studio_light_id')==spec['id']),None)
        if obj and not obj.hide_render:
            local=min((obj.matrix_world.translation-Vector(e)).length for e in eyes)<=4
            if local or spec['kind']=='SUN':lights.append(dict(spec,editable=not spec['locked'],world_position=list(obj.matrix_world.translation),scope='全屋日光，其他空間也會受影響' if spec['kind']=='SUN' else '選定觀看點附近光源'))
    from realism_color import color_balance_options
    color_options=color_balance_options(objects,lights)
    from realism_details import detail_options
    from realism_framing import actual_frame_integrity
    return dict(frame_integrity=actual_frame_integrity(design,point,by_id),color_balance=color_options,point=point,objects=objects,lights=lights,details=detail_options(design,point,by_id,visible,include_cameras),scope='觀看點周圍六公尺射線可見構件；不是全屋',exposure=scene.view_settings.exposure)
