"""Geometry-grounded finishing options and reproducible illustrative exteriors.

Bundled CC0 background; no original geometry changes, hidden edits or world override.
"""
import math
import hashlib
from pathlib import Path
import bpy
from mathutils import Vector


def box(obj):
    pts=[obj.matrix_world@Vector(p) for p in obj.bound_box]
    return [Vector([f(p[i] for p in pts) for i in range(3)]) for f in (min,max)]


def window_options(design,point,by_id,extent,for_framing=False):
    """Resolve external openings before ranking any furniture camera."""
    if not extent and not for_framing:return []
    scene=bpy.context.scene;deps=bpy.context.evaluated_depsgraph_get();eye=Vector(point['eye']);windows=[]
    for group in design['groups']:
        if group['deleted']:continue
        objects=[by_id[k] for k in group['children'] if k in by_id and not by_id[k].hide_render]
        children=set(group['children'])
        objects.extend(o for o in scene.objects if o.type=='MESH' and not o.hide_render and o.get('studio_refined_from') in children)
        if not objects:continue
        bounds=[box(o) for o in objects];lo=Vector([min(b[0][i] for b in bounds) for i in range(3)]);hi=Vector([max(b[1][i] for b in bounds) for i in range(3)]);center=(lo+hi)/2
        near=(center-eye).length<6
        if near and any(s in group['name'].lower() for s in ('window','glazing','窗')):
            axis=min((0,1),key=lambda i:hi[i]-lo[i]);span=1-axis
            edge=min((0,1),key=lambda j:abs(center[axis]-extent[j][axis])) if extent else 0;sign=-1 if edge==0 else 1
            outside=bool(extent) and abs(center[axis]-extent[edge][axis])<1.0
            if for_framing:
                # Interior-facing samples are independent of exterior eligibility.
                sign=1 if eye[axis]<center[axis] else -1
            # A real external opening must expose an unobstructed ray, not an interior partition.
            direction=Vector([0,0,0]);direction[axis]=sign
            origin=center+direction*((hi[axis]-lo[axis])/2+.08)
            hit=scene.ray_cast(deps,origin,direction,distance=10)[0]
            if (for_framing or (outside and not hit)) and hi[span]-lo[span]>.3:
                windows.append(dict(id=group['id'],name=group['name'],center=list(center),axis=axis,sign=sign,width=hi[span]-lo[span],height=hi.z-lo.z,label='CC0 城市 HDRI 遠景（示意，非基地實景）'))
    return windows


def detail_options(design,point,by_id,visible,include_cameras=True):
    scene=bpy.context.scene;deps=bpy.context.evaluated_depsgraph_get()
    refined={o.get('studio_refined_from') for o in scene.objects if o.get('studio_refined_from')}
    visible=set(visible)|refined
    from realism_ceiling import structural,ceiling_options
    floor=[box(o) for o in structural(design,by_id,'floor')]
    extent=[Vector([f(b[j][i] for b in floor) for i in range(3)]) for j,f in enumerate((min,max))] if floor else None
    windows=window_options(design,point,by_id,extent);framing_windows=window_options(design,point,by_id,extent,True);shelf_options=[];cabinets=[];textiles=[];cameras=[];camera_checks=[]
    if include_cameras:
        from realism_framing import window_anchors
        for shot in point['shots']:
            anchors=window_anchors(scene,deps,Vector(shot.get('eye') or point['eye']),shot,framing_windows)
            camera_checks.append(dict(shot_id=shot['id'],required_windows=[a['id'] for a in anchors]))
    eye=Vector(point['eye']);assign={o['id']:o for o in design['objects']}
    sofa_centers=[]
    if include_cameras:
        for g in design['groups']:
            purpose=(g.get('object_specification') or {}).get('purpose') or (g.get('asset_requirements') or {}).get('purpose')
            members=[by_id[k] for k in g['children'] if k in by_id and not by_id[k].hide_render]
            if g['deleted'] or purpose!='sofa' or not members or not any(k in visible for k in g['children']):continue
            bounds=[box(o) for o in members]
            sofa_centers.append(Vector([(min(b[0][i] for b in bounds)+max(b[1][i] for b in bounds))/2 for i in range(3)]))
    for group in design['groups']:
        if group['deleted']:continue
        objects=[by_id[k] for k in group['children'] if k in by_id and (not by_id[k].hide_render or k in refined)]
        if not objects:continue
        bounds=[box(o) for o in objects];lo=Vector([min(b[0][i] for b in bounds) for i in range(3)]);hi=Vector([max(b[1][i] for b in bounds) for i in range(3)]);center=(lo+hi)/2
        near=(center-eye).length<6
        spec=group.get('object_specification') or {};purpose=spec.get('purpose') or (group.get('asset_requirements') or {}).get('purpose','')
        protected=spec.get('material_policy') in ('original','specified')
        if not any(k in visible for k in group['children']):continue
        from realism_shelf import eligible_box
        if not protected and len(objects)==1 and eligible_box(objects[0]) and not group.get('method','').startswith('structural_') and purpose in ('','cabinet','storage','bookshelf'):
            local_eye=objects[0].matrix_world.inverted()@eye;local_center=sum((Vector(c) for c in objects[0].bound_box),Vector())/8;relative=local_eye-local_center;axis=max((0,1),key=lambda i:abs(relative[i]));suggested=('+' if relative[axis]>0 else '-')+'XY'[axis]
            shelf_options.append(dict(suggested_front=spec.get('front') if spec.get('front') in ('+X','-X','+Y','-Y') else suggested,object_id=objects[0].get('studio_id'),name=group['name'],purpose=purpose,fronts=['+X','-X','+Y','-Y'],source='單一矩形占位；仍須提供此物件的分層書架需求紀錄',current=next((s for s in design.get('shelf_refinements',[]) if s['object_id']==objects[0].get('studio_id')),None)))
        for obj in ([] if protected else objects):
            key=obj.get('studio_id')
            if key not in visible or key not in assign:continue
            names=' '.join(m.name for m in obj.data.materials if m).lower()
            if purpose in ('sofa','chair','bed','bunk_bed') and any(s in names for s in ('fabric','cloth','linen','cotton','upholst','textile','布')):
                textiles.append(key)
            # Detailed purchased or generated assemblies never get generic seams.
            if purpose in ('cabinet','shoe_cabinet','wardrobe','storage') and len(objects)==1 and obj.type=='MESH' and len(obj.data.vertices)<=24:
                front=spec.get('front','unknown')
                if front not in ('+X','-X','+Y','-Y'):
                    local_eye=obj.matrix_world.inverted()@eye
                    local_center=sum((Vector(c) for c in obj.bound_box),Vector())/8
                    v=local_eye-local_center;axis=max((0,1),key=lambda i:abs(v[i]));front=('+' if v[axis]>0 else '-')+'XY'[axis]
                cabinets.append(dict(object_id=key,front=front,name=group['name'],source='原生單一方塊，門縫表面細化，不聲稱實際五金或內部結構'))
        if not include_cameras or purpose not in ('sofa','table','desk','bed','bunk_bed','vanity','sink','cooker','wardrobe') or not near:continue
        # A nearby coffee table is context for the sofa, not a competing hero
        # whose camera may clip the necessary sofa. Dining/work areas stay separate.
        if purpose=='table' and any((center-c).length<2.5 for c in sofa_centers):continue
        from realism_ceiling import structural
        from realism_framing import candidates
        context=[];context_objects=[];placeholders=[o for o in scene.objects if o.get('studio_refined_from') and not o.hide_render]
        for other in design['groups']:
            if other.get('deleted') or (other.get('object_specification') or {}).get('purpose') or (other.get('asset_requirements') or {}).get('purpose'):continue
            if other.get('method','').startswith('structural_'):continue
            placeholders.extend(by_id[k] for k in other['children'] if k in by_id and by_id[k].type=='MESH' and len(by_id[k].data.vertices)<=24)
        from composition_context import related_purposes
        from realism_framing import partition_clear
        wall_objects=structural(design,by_id,'wall')
        for other in design['groups']:
            other_purpose=(other.get('object_specification') or {}).get('purpose') or (other.get('asset_requirements') or {}).get('purpose')
            if other['id']==group['id'] or other.get('deleted') or not related_purposes(purpose,other_purpose):continue
            members=[by_id[k] for k in other['children'] if k in by_id and not by_id[k].hide_render]
            boxes=[box(o) for o in members]
            if not boxes:continue
            lower=Vector([min(b[0][i] for b in boxes) for i in range(3)]);upper=Vector([max(b[1][i] for b in boxes) for i in range(3)])
            other_center=(lower+upper)/2
            if (other_center-center).length>3.5:continue
            # No project names or inferred room labels: a partition separates clusters.
            a=center.copy();b=other_center.copy();a.z=b.z=max(lo.z,lower.z)+1.1
            if not partition_clear(scene,deps,a,b,wall_objects):continue
            context.append((lower,upper));context_objects.extend(members)
        # Coverage photographs belong to one target, never to every nearby hero.
        main_point=dict(point,shots=[s for s in point['shots'] if not s['id'].startswith('coverage-')])
        main_options=candidates(main_point,group,objects,lo,hi,structural(design,by_id,'floor'),wall_objects,context,placeholders,context_objects,framing_windows)
        cameras.extend(main_options)
        # If a whole area cannot fit, offer an additional photograph rather than
        # crop its neighbours or overwrite the original window-facing view.
        nearest=min(design['viewpoints'],key=lambda p:(Vector(p['eye'])-center).length)
        existing=next((s for s in point['shots'] if s['id']=='coverage-'+group['id']),None)
        natural_options=any(o['lens']>=24 for o in main_options)
        if (existing or (not natural_options and nearest['id']==point['id'])) and purpose in ('desk','wardrobe','cooker','sink','bed','bunk_bed'):
            companions=[]
            if purpose=='desk':
                chair_ids={k for g in design['groups'] if ((g.get('object_specification') or {}).get('purpose') or (g.get('asset_requirements') or {}).get('purpose'))=='chair' for k in g['children']}
                companions=[o for o in context_objects if o.get('studio_id') in chair_ids]
            supplemental=dict(point,shots=[existing or dict(id='coverage-'+group['id'],name=group['name']+' · 完整取景',yaw=math.degrees(math.atan2(center.y-eye.y,center.x-eye.x)),pitch=0,lens=24,eye=list(eye))])
            extra=candidates(supplemental,group,objects,lo,hi,structural(design,by_id,'floor'),wall_objects,(),placeholders,companions,framing_windows if existing else ())
            for option in extra:
                option['supplemental']=True;option['shot_name']=group['name']+' · 完整取景'
                option['reason']='個別互補圖改善近景遮擋；整區需超廣角時優先分方向呈現，保留原主圖與窗景'
            cameras.extend(extra)

    ceiling=ceiling_options(design,by_id)
    for option in ceiling['options']:
        option['already_applied']=option['id'] in design.get('ceiling_infill',[])
        visible_centers=[]
        for triangle in option['triangles']:
            position=sum((Vector(v) for v in triangle),Vector())/3;position.z=option['height']-.01
            delta=position-eye;hit=scene.ray_cast(deps,eye,delta.normalized(),distance=max(.01,delta.length-.02))
            if not hit[0]:
                yaw=math.atan2(delta.y,delta.x);elevation=math.atan2(delta.z,math.hypot(delta.x,delta.y))
                visible_centers.append([round((.5-yaw/(2*math.pi))%1,3),round(.5-elevation/math.pi,3)])
        option['visible_panorama_uv']=visible_centers
    return dict(shelves=shelf_options,windows=windows,cabinets=cabinets,textiles=textiles,cameras=cameras,camera_checks=camera_checks,ceiling=ceiling)


def surface_detail(mat,shader,spec):
    """Add submillimetre weave or front-only panel seams; retain original maps."""
    nodes=mat.node_tree.nodes;links=mat.node_tree.links
    def mathnode(op,a,b=None):
        n=nodes.new('ShaderNodeMath');n.operation=op
        for i,v in enumerate((a,b)):
            if v is None:continue
            if isinstance(v,(float,int)):n.inputs[i].default_value=v
            else:links.new(v,n.inputs[i])
        return n.outputs[0]
    if spec.get('textile',0) and any(s in mat.name.lower() for s in ('fabric','cloth','linen','cotton','upholst','textile','布')):
        tex=nodes.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=850;tex.inputs['Detail'].default_value=2
        coords=nodes.new('ShaderNodeTexCoord');links.new(coords.outputs['Object'],tex.inputs['Vector'])
        bump=nodes.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.0003;bump.inputs['Strength'].default_value=spec['textile']*.45
        links.new(tex.outputs['Fac'],bump.inputs['Height'])
        if shader.inputs['Normal'].is_linked:links.new(shader.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
        links.new(bump.outputs['Normal'],shader.inputs['Normal'])
        if not shader.inputs['Sheen Weight'].is_linked:shader.inputs['Sheen Weight'].default_value=.15+spec['textile']*.15
    front=spec.get('cabinet_front','none')
    if front!='none':
        coords=nodes.new('ShaderNodeTexCoord');sep=nodes.new('ShaderNodeSeparateXYZ');links.new(coords.outputs['Generated'],sep.inputs[0])
        axis=front[1];cross='Y' if axis=='X' else 'X';edge=mathnode('GREATER_THAN' if front[0]=='+' else 'LESS_THAN',sep.outputs[axis],.99 if front[0]=='+' else .01)
        # Door centre seam + perimeter reveal; dimensional envelope stays exactly unchanged.
        middle=mathnode('LESS_THAN',mathnode('ABSOLUTE',mathnode('SUBTRACT',sep.outputs[cross],.5)),.004)
        horizontal=mathnode('MAXIMUM',mathnode('LESS_THAN',sep.outputs['Z'],.025),mathnode('GREATER_THAN',sep.outputs['Z'],.98))
        seam=mathnode('MULTIPLY',edge,mathnode('MAXIMUM',middle,horizontal))
        mix=nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';links.new(seam,mix.inputs[0]);mix.inputs[2].default_value=(.3,.3,.3,1)
        base=shader.inputs['Base Color']
        if base.is_linked:links.new(base.links[0].from_socket,mix.inputs[1])
        else:mix.inputs[1].default_value=base.default_value
        links.new(mix.outputs[0],base)
        bump=nodes.new('ShaderNodeBump');bump.invert=True;bump.inputs['Distance'].default_value=.002;bump.inputs['Strength'].default_value=.7;links.new(seam,bump.inputs['Height'])
        if shader.inputs['Normal'].is_linked:links.new(shader.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
        links.new(bump.outputs['Normal'],shader.inputs['Normal'])


def add_exteriors(design,options):
    """Window-masked CC0 far field; existing World and lights remain unchanged."""
    selected=design.get('illustrative_exteriors',[]);created=[]
    photo=Path(__file__).with_name('assets')/'city-sky.exr'
    if hashlib.sha256(photo.read_bytes()).hexdigest()!='a39782f9e2fbcbd36c5a0a79e7741b86b5aaeeea7958134b79d727e9c7d3fbec':raise ValueError('窗景素材雜湊不符')
    panorama=bpy.data.images.load(str(photo),check_existing=True);panorama.pack()
    def block(name,center,size,color,window):
        bpy.ops.mesh.primitive_cube_add(size=1,location=center);obj=bpy.context.object;obj.name='Illustrative exterior '+name;obj.dimensions=size
        obj['studio_illustrative_exterior']=True
        obj.visible_shadow=False;obj.visible_diffuse=False;obj.visible_glossy=False
        mat=bpy.data.materials.new(obj.name);mat.use_nodes=True;n=mat.node_tree.nodes;n.clear();em=n.new('ShaderNodeEmission');em.inputs['Color'].default_value=(*color,1);em.inputs['Strength'].default_value=.8
        links=mat.node_tree.links
        def operation(op,a,b):
            node=n.new('ShaderNodeMath');node.operation=op
            for i,v in enumerate((a,b)):
                if isinstance(v,(int,float)):node.inputs[i].default_value=v
                else:links.new(v,node.inputs[i])
            return node.outputs[0]
        geo=n.new('ShaderNodeNewGeometry');position=n.new('ShaderNodeSeparateXYZ');incoming=n.new('ShaderNodeSeparateXYZ');links.new(geo.outputs['Position'],position.inputs[0]);links.new(geo.outputs['Incoming'],incoming.inputs[0])
        env=n.new('ShaderNodeTexEnvironment');env.image=panorama;direction=n.new('ShaderNodeVectorMath');direction.operation='SCALE';direction.inputs['Scale'].default_value=-1;links.new(geo.outputs['Incoming'],direction.inputs[0]);links.new(direction.outputs[0],env.inputs['Vector']);links.new(env.outputs['Color'],em.inputs['Color']);em.inputs['Strength'].default_value=.65
        axis=window['axis'];across=1-axis
        t=operation('DIVIDE',operation('SUBTRACT',window['center'][axis],position.outputs[axis]),incoming.outputs[axis])
        u=operation('ADD',position.outputs[across],operation('MULTIPLY',incoming.outputs[across],t));z=operation('ADD',position.outputs[2],operation('MULTIPLY',incoming.outputs[2],t))
        mask=operation('GREATER_THAN',t,0)
        for value,center,width in ((u,window['center'][across],window['width']),(z,window['center'][2],window['height'])):
            mask=operation('MULTIPLY',mask,operation('GREATER_THAN',value,center-width/2))
            mask=operation('MULTIPLY',mask,operation('LESS_THAN',value,center+width/2))
        transparent=n.new('ShaderNodeBsdfTransparent');mix=n.new('ShaderNodeMixShader');links.new(mask,mix.inputs[0]);links.new(transparent.outputs[0],mix.inputs[1]);links.new(em.outputs[0],mix.inputs[2])
        out=n.new('ShaderNodeOutputMaterial');links.new(mix.outputs[0],out.inputs[0]);obj.data.materials.append(mat);created.append(obj.name)
    for window in options['windows']:
        if window['id'] not in selected:continue
        axis=window['axis'];across=1-axis;sign=window['sign'];origin=Vector(window['center'])
        sky=origin.copy();sky[axis]+=sign*22;size=[45,45,30];size[axis]=.1;block('sky',sky,size,(.56,.70,.79),window)
        # Far HDRI panorama replaces visibly schematic repeated box buildings.
        # Physical window frames retain near parallax; this far field has no finite-depth parallax.
    bpy.context.view_layer.update()
    return created
