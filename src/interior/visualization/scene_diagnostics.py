"""Native component evidence used before deciding whether furniture needs repair."""
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from decor_review import transform


def box(obj, matrix):
    pts=[matrix@obj.matrix_world@Vector(c) for c in obj.bound_box]
    return [[fn(p[i] for p in pts) for i in range(3)] for fn in (min,max)]


def inspect_groups(design, ids=None):
    by_id={o.get('studio_id'):o for o in bpy.context.scene.objects}
    deps=bpy.context.evaluated_depsgraph_get();result=[]
    floor_vertices=[];floor_faces=[]
    for g in design['groups']:
        if g['deleted'] or not ('floor' in g['name'].lower() or '地板' in g['name']):continue
        for k in g['children']:
            o=by_id.get(k)
            if o is None or o.type!='MESH':continue
            ev=o.evaluated_get(deps);mesh=ev.to_mesh();offset=len(floor_vertices)
            floor_vertices.extend(transform(g)@o.matrix_world@v.co for v in mesh.vertices)
            floor_faces.extend(tuple(offset+i for i in f.vertices) for f in mesh.polygons);ev.to_mesh_clear()
    floor=BVHTree.FromPolygons(floor_vertices,floor_faces) if floor_faces else None
    for group in design['groups']:
        if group['deleted'] or (ids is not None and group['id'] not in ids):continue
        matrix=transform(group);components=[];vertices=[];faces=[]
        for identifier in group['children']:
            obj=by_id.get(identifier)
            if obj is None or obj.type not in ('MESH','CURVE'):continue
            materials=[]
            for slot in obj.material_slots:
                mat=slot.material
                if not mat:continue
                nodes=[n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'] if mat.use_nodes else []
                materials.append(dict(name=mat.name,transmission=[float(n.inputs['Transmission Weight'].default_value) for n in nodes],alpha=[float(n.inputs['Alpha'].default_value) for n in nodes]))
            components.append(dict(id=identifier,name=obj.name,bounds=box(obj,matrix),materials=materials))
            evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh();offset=len(vertices)
            vertices.extend(matrix@obj.matrix_world@v.co for v in mesh.vertices)
            faces.extend(tuple(offset+i for i in f.vertices) for f in mesh.polygons);evaluated.to_mesh_clear()
        if not vertices:continue
        lo=[min(v[i] for v in vertices) for i in range(3)];hi=[max(v[i] for v in vertices) for i in range(3)]
        tree=BVHTree.FromPolygons(vertices,faces);surface=[]
        for u in (.25,.5,.75):
            for v in (.25,.5,.75):
                hit,normal,_,_=tree.ray_cast(Vector((lo[0]+u*(hi[0]-lo[0]),lo[1]+v*(hi[1]-lo[1]),hi[2]+.05)),Vector((0,0,-1)),hi[2]-lo[2]+.1)
                if hit is not None:surface.append(dict(position=list(hit),normal=list(normal)))
        hit=floor.ray_cast(Vector(((lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]+.1)),Vector((0,0,-1)),3)[0] if floor else None
        result.append(dict(id=group['id'],name=group['name'],bounds=[lo,hi],floor_z=hit.z if hit is not None else None,dimensions=[hi[i]-lo[i] for i in range(3)],components=components,top_surface_samples=surface))
    return result


def focused_previews(design, ids, output,stop_file=None):
    """Native two-sided evidence; never edits or saves the source scene."""
    from model_review import previews
    by_id={o.get('studio_id'):o for o in bpy.context.scene.objects}
    images=[]
    for group in design['groups']:
        if group['id'] not in ids or group['deleted']:continue
        folder=output/group['id'];folder.mkdir()
        meshes=[by_id[k] for k in group['children'] if k in by_id and by_id[k].type=='MESH']
        if not meshes:continue
        evidence=previews(design,group,meshes,folder,modes=('object','reverse'),stop_file=stop_file)
        images.extend(dict(file=f'{group["id"]}/{name}',group_id=group['id']) for name in evidence['images'][:2])
    return images


def opening_obstructions(design,ids):
    """Report measured objects in front of window interiors; never cut a wall."""
    windows=[g['id'] for g in design['groups'] if g['id'] in ids and ('window' in g['name'].lower() or '窗' in g['name'])]
    if not windows:return []
    measured=inspect_groups(design,windows);by_id={o.get('studio_id'):o for o in bpy.context.scene.objects};deps=bpy.context.evaluated_depsgraph_get()
    vertices=[];faces=[];owners=[]
    for g in design['groups']:
        if g['deleted'] or g['id'] in windows:continue
        for k in g['children']:
            o=by_id.get(k)
            if o is None or o.type not in ('MESH','CURVE'):continue
            ev=o.evaluated_get(deps);mesh=ev.to_mesh();offset=len(vertices)
            vertices.extend(transform(g)@o.matrix_world@v.co for v in mesh.vertices)
            faces.extend(tuple(offset+i for i in f.vertices) for f in mesh.polygons);owners.extend([(g['id'],k,g['name'])]*len(mesh.polygons));ev.to_mesh_clear()
    if not faces:return []
    tree=BVHTree.FromPolygons(vertices,faces);result=[]
    for w in measured:
        lo,hi=w['bounds'];axis=min((0,1),key=lambda i:hi[i]-lo[i]);other=1-axis;samples=[]
        for u in (.25,.5,.75):
            for v in (.25,.5,.75):
                center=Vector([(lo[i]+hi[i])/2 for i in range(3)]);center[other]=lo[other]+u*(hi[other]-lo[other]);center.z=lo[2]+v*(hi[2]-lo[2])
                for sign in (-1,1):
                    ray=Vector((0,0,0));ray[axis]=sign;origin=center-ray*.5
                    hit,_,index,distance=tree.ray_cast(origin,ray,1)
                    samples.append(dict(origin=list(origin),direction=list(ray),hit_group_id=owners[index][0] if hit is not None else None,hit_object_id=owners[index][1] if hit is not None else None,hit_name=owners[index][2] if hit is not None else None,position=list(hit) if hit is not None else None,distance=distance))
        result.append(dict(group_id=w['id'],normal_axis=axis,samples=samples,limitation='以薄軸作概念窗法線、兩側各0.5m量測；斜窗或實際洞口須比對確認資料，不能自動切牆'))
    return result
