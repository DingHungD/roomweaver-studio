"""Choose bounded, visible camera placements from real room geometry."""
import math
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from decor_review import transform
from scene_diagnostics import inspect_groups


def options(design):
    by_id={o.get('studio_id'):o for o in bpy.context.scene.objects};deps=bpy.context.evaluated_depsgraph_get()
    vertices=[];faces=[];owners=[];floor_v=[];floor_f=[]
    for g in design['groups']:
        if g['deleted']:continue
        is_floor='floor' in g['name'].lower() or '地板' in g['name'];matrix=transform(g)
        for key in g['children']:
            obj=by_id.get(key)
            if obj is None or obj.type not in ('MESH','CURVE'):continue
            ev=obj.evaluated_get(deps);mesh=ev.to_mesh();offset=len(vertices)
            pts=[matrix@obj.matrix_world@v.co for v in mesh.vertices];polys=[tuple(p.vertices) for p in mesh.polygons]
            vertices.extend(pts);faces.extend(tuple(offset+i for i in f) for f in polys);owners.extend([g['id']]*len(polys))
            if is_floor:
                offset=len(floor_v);floor_v.extend(pts);floor_f.extend(tuple(offset+i for i in f) for f in polys)
            ev.to_mesh_clear()
    tree=BVHTree.FromPolygons(vertices,faces);floor=BVHTree.FromPolygons(floor_v,floor_f) if floor_f else None
    targets={g['id'] for g in design['groups'] if ((g.get('asset_requirements') or {}).get('purpose') or (g.get('object_specification') or {}).get('purpose')) in ('bed','bunk_bed','sofa','table','desk','sink','vanity','shower')}
    measured=inspect_groups(design,targets);result=[]
    for point in design['viewpoints']:
        start=Vector(point['eye'])
        for target in measured:
            lo,hi=map(Vector,target['bounds']);center=(lo+hi)/2
            if (center-start).length>5:continue
            backwards=Vector((start.x-center.x,start.y-center.y,0))
            if backwards.length<.05:continue
            backwards.normalize();best=None
            for distance in (0,.3,.6,.9,1.2):
                eye=start+backwards*distance
                if distance:
                    if floor is None:continue
                    hit,_,_,_=floor.ray_cast(eye,Vector((0,0,-1)),2.2)
                    if hit is None or not .9<=eye.z-hit.z<=2.0:continue
                    if tree.ray_cast(start,backwards,distance+.12)[0] is not None:continue
                if any(tree.ray_cast(eye,Vector(v),.10)[0] is not None for v in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]):continue
                forward=(center-eye).normalized();right=forward.cross(Vector((0,0,1))).normalized();up=right.cross(forward).normalized()
                framed=[target]
                # Keep nearby visible functional companions (e.g. sofa/table)
                # in the same composition, not only the nominated main object.
                for other in measured:
                    if other['id']==target['id']:continue
                    a,b=map(Vector,other['bounds']);mid=(a+b)/2
                    if (mid-center).length>1.8:continue
                    ray=mid-eye;hit,_,owner,_=tree.ray_cast(eye,ray.normalized(),ray.length+.02)
                    if hit is None or (owner is not None and owners[owner]==other['id']):framed.append(other)
                pts=[Vector((x,y,z)) for item in framed for x in (item['bounds'][0][0],item['bounds'][1][0]) for y in (item['bounds'][0][1],item['bounds'][1][1]) for z in (item['bounds'][0][2],item['bounds'][1][2])]
                def fit(corners):
                    ratios=[]
                    for p in corners:
                        v=p-eye;depth=v.dot(forward)
                        if depth<.08:return 0
                        ratios.append(max(abs(v.dot(right))/depth,abs(v.dot(up))/depth*4/3))
                    return min(28,18/(max(ratios)*1.18))
                lens=fit(pts);context_framed=lens>=12
                if not context_framed:
                    lens=fit([Vector((x,y,z)) for x in (lo.x,hi.x) for y in (lo.y,hi.y) for z in (lo.z,hi.z)])
                if lens<12:continue
                samples=[center,Vector((lo.x,center.y,center.z)),Vector((hi.x,center.y,center.z)),Vector((center.x,lo.y,center.z)),Vector((center.x,hi.y,center.z))]
                visible=0
                for p in samples:
                    ray=p-eye;hit,_,idx,_=tree.ray_cast(eye,ray.normalized(),ray.length+.02)
                    if hit is None or (idx is not None and owners[idx]==target['id']):visible+=1
                if visible<3:continue
                score=min(lens,24)-distance*2+(4 if context_framed and len(framed)>1 else 0)
                option=dict(target_group_id=target['id'],eye=list(eye),yaw=math.degrees(math.atan2(forward.y,forward.x)),pitch=math.degrees(math.asin(forward.z)),lens=round(lens,2),visible_samples=visible,move_distance=distance)
                if best is None or score>best[0]:best=(score,option)
            if best:result.append(dict(viewpoint_id=point['id'],**best[1]))
    return result
