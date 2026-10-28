"""Measure and build a fixture/finish connection in a new native snapshot only."""
import math
from uuid import UUID,uuid5
import bpy
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_point_tri_2d

def matrix(group):
    p=Vector(group.get('rotation_pivot',[0,0,0]));d=Vector(group.get('translation',[0,0,0]))
    return Matrix.Translation(d+p)@Matrix.Rotation(math.radians(group.get('rotation',0)),4,'Z')@Matrix.Translation(-p)

def mount(design,group,meshes,plan,namespace):
    if plan['mode'] not in ('surface','recessed','pendant'):raise ValueError('燈具安裝方式尚未確認')
    from fixture_emission import orient
    emission=orient(meshes,plan['mode'])
    transform=matrix(group)
    corners=[transform@o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
    lo=Vector([min(v[i] for v in corners) for i in range(3)]);hi=Vector([max(v[i] for v in corners) for i in range(3)]);center=(lo+hi)/2
    by_id={o.get('studio_id'):o for o in bpy.context.scene.objects if o.type=='MESH'}
    hosts=[]
    for g in design['groups']:
        if g['id']==group['id'] or g.get('deleted'):continue
        for key in g['children']:
            obj=by_id.get(key)
            if not obj:continue
            label=(g['name']+' '+obj.name).lower()
            if any(s in label for s in ('ceiling','天花')) and not any(s in label for s in ('lamp','light','燈')):hosts.append((g,obj))
    def tree(g,obj):
        deps=bpy.context.evaluated_depsgraph_get();evaluated=obj.evaluated_get(deps);m=evaluated.to_mesh()
        try:return BVHTree.FromPolygons([matrix(g)@obj.matrix_world@v.co for v in m.vertices],[list(p.vertices) for p in m.polygons])
        finally:evaluated.to_mesh_clear()
    def contact():
        choices=[]
        for g,obj in hosts:
            t=tree(g,obj);hit=t.ray_cast(Vector((center.x,center.y,max(1.9,lo.z-.3))),Vector((0,0,1)),3)
            if hit[0] is not None and abs(hit[1].z)>.85:choices.append((hit[0].z,g,obj,t))
        return min(choices,key=lambda c:c[0]) if choices else None
    hit=contact();created=False
    if not hit:
        from realism_ceiling import ceiling_options,add_ceilings
        options=ceiling_options(design,by_id)['options'];option=next((o for o in options if any(intersect_point_tri_2d(Vector((center.x,center.y)),*(Vector(v[:2]) for v in tri)) for tri in o['triangles'])),None)
        if not option:raise ValueError('無可驗證的天花承載面；不能懸浮安裝或憑空封閉露天範圍')
        draft=dict(design,ceiling_infill=[option['id']]);add_ceilings(draft,by_id)
        obj=next(o for o in bpy.context.scene.objects if o.get('studio_ceiling_infill')==option['id'] and o.get('studio_id') is None)
        obj['studio_fixture_finish']=True
        identifier=uuid5(UUID(namespace),'fixture-ceiling:'+option['id']).hex;gid='fixture-ceiling-'+identifier
        obj['studio_id']=identifier;obj.name='Ceiling finish '+identifier
        # New finish only; underside stays at the measured wall-top datum.
        bpy.context.view_layer.objects.active=obj;obj.select_set(True)
        mod=obj.modifiers.new('Decorative finish thickness','SOLIDIFY');mod.thickness=.10;mod.offset=-1
        bpy.ops.object.modifier_apply(modifier=mod.name);obj.select_set(False)
        room=next(o['room_id'] for o in design['objects'] if o['id']==option['id'])
        design['objects'].append(dict(id=identifier,name=obj.name,room_id=room,material={}))
        g=dict(id=gid,name='天花裝修面',children=[identifier],translation=[0,0,0],deleted=False,method='individual')
        design['groups'].append(g);hosts.append((g,obj));hit=contact();created=True
    if not hit:raise ValueError('天花生成後接面射線未通過，未套用')
    z,host_group,host,t=hit
    # Four surrounding samples must all hit the same level finish. A single
    # center hit cannot prove support across a skylight, edge or existing hole.
    for x,y in ((lo.x-.02,lo.y-.02),(lo.x-.02,hi.y+.02),(hi.x+.02,lo.y-.02),(hi.x+.02,hi.y+.02)):
        support=t.ray_cast(Vector((x,y,z-.05)),Vector((0,0,1)),.1)
        if support[0] is None or abs(support[0].z-z)>.006:raise ValueError('燈具安裝範圍跨越天花邊緣或缺口，未開槽；請改小型候選或調整位置')
    if abs(z-hi.z)>1.5:raise ValueError('燈具與可確認天花相距過大，保留位置待確認')
    depth=min(plan['recess_depth'],max(0,hi.z-lo.z-.006)) if plan['mode']=='recessed' else 0
    if plan['mode']=='recessed' and depth<.01:raise ValueError('燈體過薄，嵌入後無法保留發光面；請改吸頂款式')
    modified=[]
    if depth:
        labels=' '.join([host_group['name'],host.name,*[m.name for m in host.data.materials if m]]).lower()
        if any(k in labels for k in ('slab','concrete','混凝土','結構','梁')):raise ValueError('結構樓板不可開槽；請改吸頂或吊掛安裝')
        if not host.get('studio_fixture_finish') and not any(k in labels for k in ('gypsum','plaster','石膏','裝修')):raise ValueError('未確認為可開槽的裝修天花，不能切割結構；請改吸頂或吊掛候選')
        # Verify thickness over this exact location, not a whole-object bbox.
        upper=t.ray_cast(Vector((center.x,center.y,z+.001)),Vector((0,0,1)),.4)
        if upper[0] is None or upper[0].z<z+depth+.01:raise ValueError('天花可用厚度不足以容納凹槽；請改試較淺嵌燈或吸頂款式')
        bpy.ops.mesh.primitive_cube_add(size=1,location=(center.x,center.y,z+depth/2-.002));cutter=bpy.context.object;cutter.dimensions=(hi.x-lo.x+.02,hi.y-lo.y+.02,depth+.004)
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        cutter.matrix_world=matrix(host_group).inverted()@cutter.matrix_world
        host.data=host.data.copy();bpy.context.view_layer.objects.active=host
        mod=host.modifiers.new('Bounded fixture recess','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
        bpy.ops.object.modifier_apply(modifier=mod.name);bpy.data.objects.remove(cutter,do_unlink=True);modified=[host.get('studio_id')]
    dz=z+depth-hi.z
    for obj in meshes:obj.matrix_world=Matrix.Translation((0,0,dz))@obj.matrix_world
    bpy.context.view_layer.update()
    verified=tree(host_group,host).ray_cast(Vector((center.x,center.y,z-.05)),Vector((0,0,1)),depth+.1)
    if verified[0] is None or abs(verified[0].z-(z+depth))>.006:raise ValueError('燈具頂部與安裝面重驗失敗，未套用')
    # Native model remains a complete fixture; a small top plate connects pendants.
    if plan['mode']=='pendant':
        tips=[transform@o.matrix_world@v.co for o in meshes for v in o.data.vertices if (transform@o.matrix_world@v.co).z>=z-.005]
        tip=sum(tips,Vector())/len(tips) if tips else Vector((center.x,center.y,z))
        bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=min(.07,min(hi.x-lo.x,hi.y-lo.y)*.45),depth=.012,location=(tip.x,tip.y,z-.006))
        plate=bpy.context.object;plate.name='Pendant canopy';plate.matrix_world=transform.inverted()@plate.matrix_world
        if meshes[0].data.materials:plate.data.materials.append(meshes[0].data.materials[0])
        meshes.append(plate)
    group['fixture_installation']=dict(mode=plan['mode'],ceiling_group_id=host_group['id'],ceiling_z=z,recess_depth=depth,agent_task_id=plan.get('agent_task_id'),verified=True)
    for light in design.get('lighting_setup',{}).get('lights',[]):
        if light.get('group_id')==group['id']:
            light['position'][2]+=dz
    return dict(status='passed',mode=plan['mode'],ceiling_group_id=host_group['id'],ceiling_z=z,recess_depth=depth,contact_error=abs(verified[0].z-(z+depth)),created_finish=created,modified_ids=modified,emission_orientation=emission,method='native_ceiling_rays_and_bounded_finish_connection')
