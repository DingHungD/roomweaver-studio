"""Evidence-bound ceiling infill for enclosed, level interior floor patches.

Never use an overall rectangular hull: preserve source floor outlines and holes.
The wall-top datum is a proposed finish, not a newly confirmed ceiling dimension.
"""
import math
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from realism_details import box


def structural(design, by_id, kind):
    """Prefer structural roles; exact fallback avoids ceiling lamps named after floors."""
    names={'floor':('floor','地板'),'wall':('wall','walls','牆壁','牆面')}
    return [by_id[k] for g in design['groups'] if not g.get('deleted') and
            (g.get('method')=='structural_'+kind or g['name'].lower() in names[kind])
            for k in g['children'] if k in by_id and by_id[k].type=='MESH' and not by_id[k].hide_render]


def ceiling_options(design, by_id):
    scene=bpy.context.scene;deps=bpy.context.evaluated_depsgraph_get()
    floors=structural(design,by_id,'floor');walls=structural(design,by_id,'wall')
    wall_vertices=[];wall_faces=[]
    for wall in walls:
        evaluated=wall.evaluated_get(deps);mesh=evaluated.to_mesh();offset=len(wall_vertices)
        wall_vertices.extend(wall.matrix_world@v.co for v in mesh.vertices)
        wall_faces.extend(tuple(offset+i for i in face.vertices) for face in mesh.polygons);evaluated.to_mesh_clear()
    wall_tree=BVHTree.FromPolygons(wall_vertices,wall_faces) if wall_faces else None
    groups={k:g for g in design['groups'] for k in g['children']}
    room_names={r['id']:r['name'] for r in design.get('rooms',[])}
    assign={o['id']:o for o in design['objects']};options=[];skipped=[]
    lamp_ids={k for g in design['groups'] if (g.get('asset_requirements') or {}).get('purpose')=='light' or g['id'].startswith('concept-') and '天花燈具' in g['name'] for k in g['children']}
    from completion_geometry import selected_roof_trees
    roofs=selected_roof_trees(design,by_id,floors,walls)
    for floor in floors:
        key=floor.get('studio_id');lo,hi=box(floor);group=groups[key]
        labels=' '.join((floor.name,group['name'],room_names.get(assign[key].get('room_id'),''),group.get('design_prompt',''))).lower()
        def skip(reason):skipped.append(dict(id=key,name=floor.name,reason=reason))
        if any(t in labels for t in ('balcony','terrace','courtyard','atrium','outdoor','天井','露天','挑空','陽台','天窗')):
            skip('露天／挑空／陽台標記，不自動封頂');continue
        mesh=floor.evaluated_get(deps).to_mesh()
        try:
            mesh.calc_loop_triangles();verts=[floor.matrix_world@v.co for v in mesh.vertices]
            triangles=[[verts[i] for i in t.vertices] for t in mesh.loop_triangles if all(abs(verts[i].z-hi.z)<.005 for i in t.vertices)]
        finally:floor.evaluated_get(deps).to_mesh_clear()
        if not triangles:skip('沒有平整的原生地板頂面');continue
        samples=[sum(t,Vector())/3 for t in triangles]
        nearby=[box(w) for w in walls if (sum(box(w),Vector())/2-(lo+hi)/2).length<7]
        tops=[round(b[1].z,2) for b in nearby if 2.1<=b[1].z-hi.z<=4.5 and b[0].z<=hi.z+.2]
        if len(tops)<3:skip('沒有足夠同樓層牆頂高度證據');continue
        height=max(set(tops),key=tops.count)
        if sum(abs(z-height)<.03 for z in tops)/len(tops)<.8:skip('牆頂高度不一致，保留斜頂／高低頂');continue
        # A tall cabinet or lampshade is not a ceiling. Probe distributed points
        # near the wall datum, continuing past furniture and vertical wall hits.
        probes=[]
        def subdivide(t,depth=0):
            if depth<5 and max((t[(i+1)%3]-t[i]).length for i in range(3))>.6:
                a,b,c=t;ab=(a+b)/2;bc=(b+c)/2;ca=(c+a)/2
                for sub in ([a,ab,ca],[ab,b,bc],[ca,bc,c],[ab,bc,ca]):subdivide(sub,depth+1)
            else:probes.append(sum(t,Vector())/3)
        for t in triangles:subdivide(t)
        # Query roof meshes directly: wall tops and opaque lamps must not hide
        # a coplanar roof in a scene-wide nearest-hit query.
        covered=0;generated=set();foreign=0
        for p in probes:
            origin=Vector((p.x,p.y,hi.z+2.0));nearest=None
            for obj,tree in roofs:
                hit=tree.ray_cast(origin,Vector((0,0,1)),height+.15-origin.z)
                if hit[0] is not None and abs(hit[1].z)>.8 and (nearest is None or hit[3]<nearest[0]):nearest=(hit[3],obj,hit[0])
            if nearest:
                _,obj,point=nearest;covered+=1
                if obj.get('studio_ceiling_infill')==key and abs(point.z-height)<.03:generated.add(obj.name)
                else:foreign+=1
        if covered==len(probes):skip('原生射線確認完整頂面');continue
        if foreign:
            skip('既有局部頂面或天窗邊界未知；保留原頂面，不自動封口');continue
        enclosed=0;hits=[]
        p=max(triangles,key=lambda t:(t[1]-t[0]).cross(t[2]-t[0]).length);p=sum(p,Vector())/3
        for angle in range(0,360,45):
            direction=Vector((math.cos(math.radians(angle)),math.sin(math.radians(angle)),0))
            hit=wall_tree.ray_cast(Vector((p.x,p.y,height-.2)),direction,12) if wall_tree else (None,)
            hits.append(dict(angle=angle,wall_hit=hit[0] is not None))
            if hit[0] is not None:enclosed+=1
        if enclosed<7:
            skip('上緣四周不夠封閉，不能確認為室內');skipped[-1]['hits']=hits;continue
        options.append(dict(id=key,name=floor.name,height=height,floor_z=hi.z,enclosed_rays=enclosed,
            replace_generated=sorted(generated),coverage_samples=len(probes),triangles=[[list(v) for v in t] for t in triangles],source='原生地板頂面輪廓＋一致牆頂高度；推定平頂，非新增確認尺寸'))
    return dict(options=options,skipped=skipped)


def add_ceilings(design,by_id):
    selected=design.get('ceiling_infill',[])
    if not selected:return []
    check=ceiling_options(design,by_id)
    available={o['id']:o for o in check['options']}
    complete={o['id'] for o in check['skipped'] if '完整頂面' in o['reason']}
    if any(k not in available and k not in complete for k in selected):raise ValueError('天花補面來源已變動或缺乏封閉與高度證據，請重新精修')
    # Replaying an already complete generated ceiling is a no-op. Other missing
    # evidence is reported by the caller rather than silently overwriting a roof.
    selected=[k for k in selected if k in available]
    if not selected:return []
    material=bpy.data.materials.new('Studio ceiling matte plaster');material.use_nodes=True
    shader=material.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(.72,.70,.66,1);shader.inputs['Roughness'].default_value=.82
    created=[];created_objects={}
    for key in selected:
        option=available[key];verts=[];faces=[]
        for name in option.get('replace_generated',[]):
            old=bpy.data.objects.get(name)
            if old:old.hide_render=True;old.hide_set(True)
        for tri in option['triangles']:
            start=len(verts);verts.extend((v[0],v[1],option['height']) for v in tri);faces.append((start+2,start+1,start))
        mesh=bpy.data.meshes.new('Ceiling infill '+key);mesh.from_pydata(verts,[],faces);mesh.update()
        obj=bpy.data.objects.new('Ceiling infill '+key,mesh);bpy.context.collection.objects.link(obj)
        obj['studio_ceiling_infill']=key;obj['height_source']=option['source'];obj.data.materials.append(material)
        created_objects[key]=obj
        created.append(dict(id=key,height=option['height'],triangles=len(faces),source=option['source']))
    bpy.context.view_layer.update()
    # Upward verification after generation; lamps and furniture are not used as the ceiling datum.
    deps=bpy.context.evaluated_depsgraph_get()
    for key in selected:
        option=available[key]
        obj=created_objects[key]
        tree=BVHTree.FromPolygons([obj.matrix_world@v.co for v in obj.data.vertices],[list(p.vertices) for p in obj.data.polygons])
        for tri in option['triangles']:
            p=sum((Vector(v) for v in tri),Vector())/3;p.z=option['height']-.02
            hit=tree.ray_cast(p,Vector((0,0,1)),.04)
            if hit[0] is None:raise ValueError('天花補面射線重驗失敗')
    return created
