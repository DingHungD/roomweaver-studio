"""Parametric opening assemblies inside existing cuts; no wall cutting or resizing."""
import math
from uuid import UUID,uuid5
import bpy
from mathutils import Vector,Matrix


def wood_material(name):
    """Metre-scale grain for new concept timber; keep metal and glass separate."""
    key='Opening oak '+name;mat=bpy.data.materials.get(key)
    if mat:return mat
    mat=bpy.data.materials.new(key);mat.use_nodes=True;mat.diffuse_color=(.43,.29,.16,1)
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=mat.diffuse_color;shader.inputs['Roughness'].default_value=.47
    coord=nodes.new('ShaderNodeTexCoord');scale=nodes.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(45,45,2)
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1;noise.inputs['Detail'].default_value=2
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.20,.115,.052,1);ramp.color_ramp.elements[1].color=(.55,.39,.23,1)
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.0003
    links.new(coord.outputs['Object'],scale.inputs[0]);links.new(scale.outputs['Vector'],noise.inputs['Vector']);links.new(noise.outputs['Fac'],ramp.inputs[0]);links.new(ramp.outputs[0],shader.inputs['Base Color'])
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal'])
    # glTF cannot export procedural noise. Keep an explicit oak-colour browser
    # derivative instead of allowing the exporter to turn the linked colour white.
    preview=bpy.data.materials.new(key+' preview');preview.use_nodes=True;preview.diffuse_color=mat.diffuse_color
    ps=preview.node_tree.nodes.get('Principled BSDF');ps.inputs['Base Color'].default_value=mat.diffuse_color;ps.inputs['Roughness'].default_value=.47
    mat['studio_preview_material']=preview.name
    return mat


def open_leaves(created,item,origin,direction,normal,length,frame,transform,sliding,folding):
    """Open generated leaves only after testing the swept path against existing meshes."""
    from completion_geometry import Obstacles
    leaves=[o for o in created if o.get('opening_moving')]
    guides=[o for o in created if o.get('opening_guide')]
    obstacles=Obstacles(created);original={o:o.matrix_world.copy() for o in leaves+guides}
    basis=transform or Matrix.Identity(4)
    def pose(hinge,angle,amount,track_offset=0):
        for obj in leaves:
            index=obj['opening_moving']-1
            if sliding:
                # Two tracks overlap by half the opening; never slide into the wall.
                # Try both valid packing ends, rather than retrying the same
                # first leaf four times. Keep the stationary leaf collision-tested.
                delta=direction*((1 if hinge==0 else -1)*(length-2*frame)/2*amount if index==hinge else 0)+normal*track_offset
                change=Matrix.Translation(delta)
            else:
                double=(item.get('control') or {}).get('kind')=='double'
                leaf_hinge=index if double else hinge
                x=frame if leaf_hinge==0 else length-frame
                pivot=origin+direction*x
                if not folding:
                    # A butt hinge rotates about the opening-side face, not the
                    # solid leaf centreline. Keep the jamb and opening fixed.
                    opening_side=math.copysign(1,angle)*(1 if leaf_hinge==0 else -1)
                    if double:opening_side=math.copysign(1,angle)
                    pivot+=normal*(opening_side*.0175)
                turn=angle*amount*(-1 if double and index==1 else 1)
                change=Matrix.Translation(pivot)@Matrix.Rotation(turn,4,'Z')@Matrix.Translation(-pivot)
                if folding and index==(1 if hinge==0 else 0):
                    # Put the fold hinge on the outside face, not inside the solid leaf.
                    joint=origin+direction*(length/2)-normal*math.copysign(.0175,angle*(1 if hinge==0 else -1))
                    change=change@Matrix.Translation(joint)@Matrix.Rotation(-2*turn,4,'Z')@Matrix.Translation(-joint)
            handle_shift=Matrix.Translation(direction*(-.6*(length-2*frame))) if hinge==1 and not sliding and not folding and (item.get('control') or {}).get('kind')!='double' and ' · handle-' in obj.name else Matrix.Identity(4)
            obj.matrix_world=basis@change@handle_shift@basis.inverted()@original[obj]
        for obj in guides:
            obj.matrix_world=basis@Matrix.Translation(normal*track_offset)@basis.inverted()@original[obj]
        bpy.context.view_layer.update()
    control=dict(item.get('control') or {})
    if control.get('side') and control.get('kind') in ('single','double'):
        if control['kind']=='double':control.update(hinge='A',swing=control['side'])
        elif control.get('swing')!='auto':control['hinge']='A' if control['swing']==control['side'] else 'B'
    hinges=(0,1) if control.get('hinge','auto')=='auto' else ((0,) if control['hinge']=='A' else (1,))
    angles=(math.pi/2,-math.pi/2) if control.get('swing','auto')=='auto' else ((math.pi/2,) if control['swing']=='positive' else (-math.pi/2,))
    if folding:
        if control.get('side'):
            angles=(math.radians(80)*(1 if control['side']=='positive' else -1),)
        else:angles=(math.radians(80),-math.radians(80))
    blockers=set();partial=None
    for track_offset in ((0,-.08,.08,-.1,.1) if sliding else (0,)):
      for hinge in hinges:
        for angle in ((0,) if sliding else angles):
            safe=True
            for step in range(0,13):
                pose(hinge,-angle if folding and hinge==1 else angle,step/12,track_offset)
                collisions=obstacles.collisions(leaves+guides)
                if folding:
                    panels=[o for o in leaves if ' · leaf-' in o.name]
                    if len(panels)==2 and obstacles.tree(panels[0]).overlap(obstacles.tree(panels[1])):collisions.add('折疊門板彼此干涉')
                if collisions:
                    blockers.update(collisions);safe=False;break
                if not sliding and not folding and step>=2:
                    degrees=abs(math.degrees(angle)*step/12)
                    if partial is None or degrees>partial[0]:
                        partial=(degrees,hinge,angle,step/12)
            if safe:return dict(state='open',angle=0 if sliding else math.degrees(angle),track_offset=track_offset,hinge='inferred-A' if hinge==0 else 'inferred-B',source='概念開啟姿態；閉合與12段路徑碰撞檢查，滑門可選洞口兩側軌道；非施工五金確認')
    if partial is not None:
        degrees,hinge,angle,amount=partial
        pose(hinge,angle,amount)
        return dict(state='limited',angle=math.degrees(angle)*amount,track_offset=0,hinge='inferred-A' if hinge==0 else 'inferred-B',blockers=sorted(blockers),source='依原開向限制開啟角度；保留尺寸與材質，完整開啟仍受阻，需確認使用淨寬')
    for obj,matrix in original.items():obj.matrix_world=matrix
    return dict(state='blocked',blockers=sorted(blockers),source='開門掃掠範圍受遮擋（'+ '、'.join(sorted(blockers)[:4])+'）；保留門片，未強行穿過家具或牆壁')


def assembly(item,source_sha256,transform=None,source_id=None):
    a,b=item['points'];original_length=math.dist(a,b);height=item['height'];base=item['base']
    width=(item.get('control') or {}).get('assembly_width')
    if width is not None and (width>original_length+.00001 or width<.5):
        raise ValueError('門組 AB 長度需至少50cm，且不得擴大來源洞口')
    padding=(original_length-width)/2 if width is not None else 0
    if padding:
        unit=[(b[i]-a[i])/original_length for i in range(2)]
        a=[a[i]+unit[i]*padding for i in range(2)];b=[b[i]-unit[i]*padding for i in range(2)]
    length=math.dist(a,b)
    if not (.25<length<8 and .3<height<4):raise ValueError('洞口尺寸超出可建立範圍')
    direction=Vector((b[0]-a[0],b[1]-a[1],0)).normalized();normal=Vector((-direction.y,direction.x,0));origin=Vector((*a,base))
    namespace=UUID(source_sha256[:32]);created=[];frame=min(.04,length/12,height/12)
    def material(name,color,roughness=.4,glass=False):
        key='Opening '+name;mat=bpy.data.materials.get(key)
        if mat:return mat
        mat=bpy.data.materials.new(key);mat.use_nodes=True;mat.diffuse_color=(*color,1)
        shader=mat.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(*color,1);shader.inputs['Roughness'].default_value=roughness
        if glass:shader.inputs['Transmission Weight'].default_value=1;shader.inputs['IOR'].default_value=1.45
        return mat
    frame_mat=material('concept-frame',(.68,.68,.68),.65) if item.get('basic_model') else wood_material('frame')
    leaf_mat=material('concept-leaf',(.72,.72,.72),.65) if item.get('basic_model') else wood_material('leaf')
    metal=material('handle',(.12,.13,.14),.23);glass=material('clear glass',(.96,.98,.99),.025,True)
    def box(label,x,y,z,w,d,h,mat):
        part='frame' if label in ('jamb-A','jamb-B','head','infill-A','infill-B') else label
        override=(item.get('control') or {}).get('materials',{}).get(part)
        if override:
            rgb=[int(override['color'][i:i+2],16)/255 for i in (1,3,5)]
            linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
            mat=material(item['id']+' '+part+' '+override['color']+' '+str(override['roughness']),linear,override['roughness'])

        vertices=[origin+direction*xx+normal*yy+Vector((0,0,zz)) for zz in (z-h/2,z+h/2) for xx,yy in ((x-w/2,y-d/2),(x+w/2,y-d/2),(x+w/2,y+d/2),(x-w/2,y+d/2))]
        if transform is not None:vertices=[transform@v for v in vertices]
        mesh=bpy.data.meshes.new(label);mesh.from_pydata(vertices,[],[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]);mesh.update()
        obj=bpy.data.objects.new(item['name']+' · '+label,mesh);bpy.context.scene.collection.objects.link(obj);obj.data.materials.append(mat)
        obj['studio_id']=uuid5(namespace,item['id']+'/opening-'+label).hex;obj['assembly_id']=item['name']+' ['+item['id']+']'
        obj['studio_role']=item['role'];obj['source_entity_id']=item['id'];obj['studio_opening_complete']=True
        if item.get('room_id'):obj['room_id']=item['room_id']
        obj['studio_opening_group']=uuid5(namespace,item['id']+'/opening-group').hex
        if source_id:obj['studio_refined_from']=source_id
        bevel=obj.modifiers.new('Manufactured edges','BEVEL');bevel.width=.0015;bevel.segments=2
        from door_asset_geometry import FILES
        spec=(item.get('control') or {}).get('_asset_files',FILES.get(item['id'],{})).get(part)
        if spec:
            from door_asset_geometry import apply
            apply(obj,spec,origin,direction,normal,x,y,z,w,d,h,transform)
        obj['doorId']=item['id'];obj['doorPart']=part
        created.append(obj);return obj
    box('jamb-A',frame/2,0,height/2,frame,.09,height,frame_mat)
    box('jamb-B',length-frame/2,0,height/2,frame,.09,height,frame_mat)
    box('head',length/2,0,height-frame/2,length-2*frame,.09,frame,frame_mat)
    if padding>0:
        box('infill-A',-padding/2,0,height/2,padding,.09,height,frame_mat)
        box('infill-B',length+padding/2,0,height/2,padding,.09,height,frame_mat)
    remaining=[]
    if item['role']=='window':
        box('sill',length/2,0,frame/2,length-2*frame,.11,frame,frame_mat)
        box('mullion',length/2,0,height/2,frame,.06,height-2*frame,frame_mat)
        for n,x in enumerate((length/4,3*length/4)):
            box('glass-'+str(n),x,0,height/2,length/2-2*frame,.006,height-2*frame,glass)
        box('handle',length/2-frame*1.6,-.045,height*.45,.015,.025,.12,metal)
        style='木框雙格玻璃窗概念；型材與開啟方式未指定'
    else:
        kind=(item.get('control') or {}).get('kind')
        sliding=kind=='sliding' if kind else any(k in item['name'].lower() for k in ('滑門','拉門','sliding'))
        folding=kind=='folding' or not kind and any(k in item['name'].lower() for k in ('fold','摺門','折門'))
        count=0 if kind=='frame' else 2 if sliding or folding or kind=='double' else 1;span=(length-2*frame)/max(count,1)
        for index in range(count):
            x=frame+(index+.5)*span;y=.045*index if sliding else 0
            box('leaf-'+str(index),x,y,(height-frame)/2,span-.006,.035,height-frame-.012,leaf_mat)['opening_moving']=index+1
            box('handle-'+str(index),x+span*.3,y-.035,min(1.0,height*.5),.09,.025,.018,metal)['opening_moving']=index+1
        style='木質門框' if kind=='frame' else '木質雙開門概念' if kind=='double' else '木質滑門概念' if sliding else '木質雙折開門概念' if folding else '木質平開門概念'
        if sliding:
            box('sliding-guide',length/2,.0225,height-frame-.018,length-2*frame,.105,.018,metal)['opening_guide']=True
        opening=open_leaves(created,item,origin,direction,normal,length,frame,transform,sliding,folding)
        if opening['state']=='blocked':remaining.append(item['name']+'：'+opening['source'])
    result=dict(id=item['id'],name=item['name'],role=item['role'],status='prepared',style=style,parts=len(created),width=length,height=height,base=base,remaining=remaining,material='procedural_oak')
    if item['role']=='door':
        if (item.get('control') or {}).get('kind')=='single':
            moving=[o for o in created if o.get('opening_moving')]
            axis=(transform.to_3x3()@direction).normalized() if transform is not None else direction
            projection=[(o.matrix_world@v.co).dot(axis) for o in moving for v in o.data.vertices]
            occupied=max(projection)-min(projection) if projection else 0
            result['passage_check']=dict(projected_clear_width=round(max(0,length-2*frame-occupied),3),method='門片與把手投影包絡估算；不是施工淨寬或法規驗收',hinge_axis='opening_side_leaf_face',dimension_changed=bool(padding),source_opening_width=original_length,assembly_width=length)
        result['opening']=opening
        result['preview_parts']=[dict(part=('frame' if o.name.rsplit(' · ',1)[-1] in ('jamb-A','jamb-B','head','infill-A','infill-B') else o.name.rsplit(' · ',1)[-1]),vertices=[list(o.matrix_world@Vector(v)) for v in [o.bound_box[i] for i in (0,4,7,3,1,5,6,2)]]) for o in created]
        if opening['state']=='limited':remaining.append(item['name']+'：'+opening['source'])
    return result


def add_openings(design,by_id,source):
    report=dict(items=[],remaining=[],source=source or {})
    if not design.get('opening_details'):return report
    for manual in design.get('manual_doors',[]):
        control=next((d for d in design.get('door_controls',[]) if d['opening_id']==manual['id']),{})
        members=[o for o in by_id.values() if o.get('source_entity_id')==manual['id']]
        if control.get('deleted'):
            for o in members:o.hide_render=True;o.hide_set(True)
            report['items'].append(dict(id=manual['id'],status='deleted'))
            continue
        if members and not control:continue
        if not control.get('kind'):
            report['remaining'].append(manual['name']+'：尚未設定種類，保留定位，不生成門片。');continue
        import hashlib
        item=dict(manual,role='door',base=0,control=control,name=control.get('name') or manual['name'])
        previous=[(o,o.hide_render,o.hide_get()) for o in members]
        for o,_,_ in previous:o.hide_render=True;o.hide_set(True)
        try:result=assembly(item,hashlib.sha256(manual['id'].encode()).hexdigest())
        except Exception:
            for o,r,h in previous:o.hide_render=r;o.hide_set(h)
            raise
        report['items'].append(result);report['remaining'].extend(result['remaining'])
    if not source or not source.get('items'):
        report['remaining'].append((source or {}).get('reason','缺少可信門窗洞口資料，未新增。'));return report
    for item in source['items']:
        members=[o for o in by_id.values() if o.get('source_entity_id')==item['id']]
        control=next((d for d in design.get('door_controls',[]) if d['opening_id']==item['id']),None)
        if control and control.get('deleted'):
            for o in members:o.hide_render=True;o.hide_set(True)
            report['items'].append(dict(id=item['id'],status='deleted'))
            continue
        if any(o.get('studio_opening_complete') for o in members) and not control:
            report['items'].append(dict(id=item['id'],name=item['name'],status='already_complete'));continue
        owners=[g for g in design['groups'] if set(g['children']) & {o.get('studio_id') for o in members}]
        if any((g.get('object_specification') or {}).get('material_policy') in ('original','specified') for g in owners):
            report['remaining'].append(item['name']+'：門窗材質已有保留／指定設定，未以木質概念替換。');continue
        hosts=[o for o in by_id.values() if o.get('source_entity_id')==item['host_id'] and not o.hide_render]
        if not hosts or any(g['deleted'] for g in design['groups'] if set(g['children']) & {o.get('studio_id') for o in members}):
            report['remaining'].append(item['name']+'：宿主牆已刪除或來源不明，未自動補建。');continue
        # The plan builder uses world-space mesh vertices. Only reuse openings if
        # the host still contains both endpoint elevations and its centre is hollow.
        host=hosts[0];matrix=host.matrix_world.copy();a,b=item['points'];center=Vector(((a[0]+b[0])/2,(a[1]+b[1])/2,item['base']+item['height']/2))
        bounds=[Vector(v) for h in hosts for v in h.bound_box]
        lo=Vector([min(p[i] for p in bounds) for i in range(3)]);hi=Vector([max(p[i] for p in bounds) for i in range(3)])
        endpoints=[Vector((*xy,z)) for xy in (a,b) for z in (item['base'],item['base']+item['height'])]
        if any(any(p[i]<lo[i]-.05 or p[i]>hi[i]+.05 for i in range(3)) for p in endpoints) or any(h.matrix_world!=matrix for h in hosts):
            report['remaining'].append(item['name']+'：目前牆體與來源洞口範圍不符，保留原件待核對。');continue
        u=Vector((b[0]-a[0],b[1]-a[1],0)).normalized();normal=Vector((-u.y,u.x,0))
        hit=any(h.ray_cast(center-normal*.5,normal,distance=1)[0] for h in hosts)
        if hit:
            report['remaining'].append(item['name']+'：原生牆洞中心仍被牆面遮擋，未覆蓋問題或另切洞。');continue
        try:
            controlled=dict(item,control=control or {})
            if control and control.get('name'):controlled['name']=control['name']
            previous=[(obj,obj.hide_render,obj.hide_get()) for obj in members]
            for obj,_,_ in previous:obj.hide_render=True;obj.hide_set(True)
            try:result=assembly(controlled,source['source_sha256'],matrix,members[0].get('studio_id') if members else None)
            except Exception:
                for obj,render,hidden in previous:obj.hide_render=render;obj.hide_set(hidden)
                raise
            for obj in members:obj.hide_render=True;obj.hide_set(True)
            report['items'].append(result);report['remaining'].extend(result['remaining'])
        except ValueError as exc:report['remaining'].append(item['name']+'：'+str(exc))
    return report
