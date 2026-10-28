"""Rank native camera candidates by subject coverage, occlusion and blank wall area."""
import math
from pathlib import Path
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def render_ray(scene,deps,origin,direction,distance=10):
    """Match render visibility: hidden replaced originals cannot occlude a photo."""
    start=origin.copy();direction=direction.normalized();remaining=distance
    for _ in range(64):
        hit=scene.ray_cast(deps,start,direction,distance=remaining)
        if not hit[0] or not hit[4].hide_render:return hit
        travelled=(hit[1]-start).length+.002
        remaining-=travelled
        if remaining<=0:return (False,None,None,-1,None,None)
        start=hit[1]+direction*.002
    # Unresolved dense geometry remains conservative, never silently clear it.
    return hit


def floor_below(scene,deps,position,floors,distance=2.5):
    """Find the structural floor even when a low table is below the camera.

    This only estimates eye elevation; camera clearance and approach-path tests
    still reject collisions separately. Furniture must not masquerade as floor.
    """
    origin=position.copy();bottom=position.z-distance
    for _ in range(32):
        remaining=origin.z-bottom
        if remaining<=0:return None
        hit=render_ray(scene,deps,origin,Vector((0,0,-1)),distance=remaining)
        if not hit[0]:return None
        if hit[4] in floors:return hit[1]
        origin=hit[1]-Vector((0,0,.002))
    return None


def centered_shift(corners,forward,up,lens):
    """Centre the real subject silhouette on the sensor within allowed shift."""
    slopes=[v.dot(up)/v.dot(forward) for v in corners]
    return round(max(-.3,min(.3,(min(slopes)+max(slopes))*lens/72)),4)


def sensor_fit(horizontal,lower,upper,lens,half_height,shift,margin=.92):
    """Exact interval equivalent of checking every projected hull vertex."""
    offset=shift*36/lens;limit=half_height/lens*margin
    return horizontal<18/lens*margin and lower-offset>-limit and upper-offset<limit


def silhouette_hull(points):
    """Exact convex support vertices, avoiding empty AABB corners in camera fitting."""
    import bmesh
    mesh=bmesh.new()
    try:
        for point in points:mesh.verts.new(point)
        mesh.verts.ensure_lookup_table()
        result=bmesh.ops.convex_hull(mesh,input=list(mesh.verts),use_existing_faces=False)
        verts={v for element in result['geom'] for v in ([element] if isinstance(element,bmesh.types.BMVert) else element.verts)}
        return [v.co.copy() for v in verts]
    finally:mesh.free()


def frame_axes(shot):
    yaw=math.radians(shot['yaw']);pitch=math.radians(shot.get('pitch',0))
    forward=Vector((math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),math.sin(pitch)))
    rotation=forward.to_track_quat('-Z','Y')
    return forward,rotation@Vector((1,0,0)),rotation@Vector((0,1,0))


def in_frame(position,eye,shot,margin=.96):
    forward,right,up=frame_axes(shot);v=position-eye;depth=v.dot(forward)
    if depth<.15:return False
    lens=shot['lens'];height=10.125 if shot.get('aspect')=='16:9' else 13.5
    return abs(v.dot(right)/depth)<18/lens*margin and abs(v.dot(up)/depth-shot.get('shift_y',0)*36/lens)<height/lens*margin


def partition_clear(scene,deps,origin,target,walls):
    """Ignore furniture on the joining segment, but never cross structural walls."""
    start=origin.copy();direction=(target-origin).normalized()
    for _ in range(64):
        distance=(target-start).dot(direction)-.02
        if distance<=0:return True
        hit=render_ray(scene,deps,start,direction,distance=distance)
        if not hit[0]:return True
        if hit[4] in walls:return False
        start=hit[1]+direction*.005
    return False


def window_sightline(scene,deps,origin,target):
    """Transparent intermediate panes must not erase an existing window anchor."""
    start=origin.copy();direction=(target-origin).normalized()
    for _ in range(12):
        distance=(target-start).dot(direction)-.02
        if distance<=0:return True
        hit=render_ray(scene,deps,start,direction,distance=distance)
        if not hit[0]:return True
        evaluated=hit[4].evaluated_get(deps)
        polygons=evaluated.data.polygons;slots=evaluated.data.materials
        index=polygons[hit[3]].material_index if 0<=hit[3]<len(polygons) else -1
        materials=[slots[index]] if 0<=index<len(slots) and slots[index] else []
        def clear(mat):
            if not mat.use_nodes:return False
            bsdf=mat.node_tree.nodes.get('Principled BSDF')
            if not bsdf:return False
            transmission=bsdf.inputs.get('Transmission Weight')
            return transmission is not None and not transmission.is_linked and transmission.default_value>.9
        if not materials or not all(clear(m) for m in materials):return False
        start=hit[1]+direction*.01
    return False


def window_anchors(scene,deps,eye,shot,windows):
    """Protect only openings actually visible in the reference photograph.

    Samples are on the interior side of the window, so transparent glass and
    frame objects do not falsely count as room obstructions. Hidden windows in
    other rooms never become a requirement for this composition.
    """
    anchors=[]
    for window in windows:
        samples=[]
        for across in (-.45,-.35,-.25,-.15,0,.15,.25,.35,.45):
            for vertical in (-.4,-.2,0,.2,.4):
                p=Vector(window['center']);p[1-window['axis']]+=across*window['width'];p.z+=vertical*window['height']
                p[window['axis']]-=window['sign']*.09
                delta=p-eye
                if not in_frame(p,eye,shot):continue
                if window_sightline(scene,deps,eye,p):samples.append(p)
        if len(samples)>=2:anchors.append(dict(id=window['id'],points=samples))
    return anchors


def candidates(point,group,objects,lo,hi,floors,walls,context_bounds=(),placeholders=(),context_objects=(),windows=(),recovery=False):
    scene=bpy.context.scene;deps=bpy.context.evaluated_depsgraph_get();center=(lo+hi)/2
    hero_objects=list(objects)
    objects=list(dict.fromkeys(list(objects)+list(context_objects)))
    vertices=[];faces=[];hero_vertices=[];hero_faces=[]
    for obj in objects:
        evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh();offset=len(vertices)
        vertices.extend(obj.matrix_world@v.co for v in mesh.vertices)
        faces.extend(tuple(offset+i for i in f.vertices) for f in mesh.polygons);evaluated.to_mesh_clear()
        if obj in hero_objects:
            hero_offset=len(hero_vertices)
            hero_vertices.extend(vertices[offset:])
            hero_faces.extend(tuple(hero_offset+i-offset for i in f) for f in faces if all(i>=offset for i in f))
    if not faces:return []
    fitting=list(vertices)
    if not context_objects:
        for lower,upper in context_bounds:
            fitting.extend(Vector((a,b,c)) for a in (lower.x,upper.x) for b in (lower.y,upper.y) for c in (lower.z,upper.z))
    fitting=silhouette_hull(fitting)
    center=Vector([(min(v[i] for v in fitting)+max(v[i] for v in fitting))/2 for i in range(3)])
    target=BVHTree.FromPolygons(vertices,faces);hero_target=BVHTree.FromPolygons(hero_vertices,hero_faces);result=[]
    for shot in point['shots']:
        start=Vector(shot.get('eye') or point['eye']);ranked=[];shortlist={}
        # A newly completed door can obstruct an old shot outside its room.
        # Recover from the existing panorama eye, never tunnel through a wall.
        blocked_start=any(render_ray(scene,deps,start,Vector(d),distance=.16)[0] for d in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)))
        travel_origin=Vector(point['eye']) if blocked_start or recovery else start
        anchors=window_anchors(scene,deps,start,shot,windows)
        required_window_points=[p for a in anchors for p in a['points']]
        shot_fitting=fitting+required_window_points
        positions={(x,y) for x in (-1.5,-1,-.5,0,.5,1,1.5) for y in (-1.5,-1,-.5,0,.5,1,1.5)}
        # Fine offsets around the retained photograph avoid jumping over a useful
        # composition between coarse half-metre samples. No project coordinates.
        positions.update((start.x-point['eye'][0]+x,start.y-point['eye'][1]+y) for x in (-.25,0,.25) for y in (-.25,0,.25))
        for x,y in sorted(positions):
            stop_file=scene.get('studio_search_stop_file')
            if stop_file and Path(stop_file).exists():raise ValueError('已停止取景搜尋')
            for height in ((1.05,1.15,1.3,1.5,1.65) if anchors else (1.15,1.35,1.55,1.65)):
                pos=Vector(point['eye'])+Vector((x,y,0))
                ground=floor_below(scene,deps,pos,floors)
                if ground is None:continue
                pos.z=ground.z+height;delta=pos-travel_origin;distance=delta.length
                if distance>2:continue
                if distance and render_ray(scene,deps,travel_origin,delta.normalized(),distance=distance+.12)[0]:continue
                if any(render_ray(scene,deps,pos,Vector(d),distance=.15)[0] for d in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0))):continue
                # A view through a partition is not a preserved window view.
                if any(not window_sightline(scene,deps,pos,p) for p in required_window_points):continue
                ray=center-pos;yaw=math.atan2(ray.y,ray.x)
                # Keep fine angles and the prior shot when broadening search;
                # otherwise a new search can lose an already well-framed view.
                view_yaws={yaw+math.radians(offset) for offset in ((-24,-12,-8,-4,0,4,8,12,24) if anchors else (-24,-12,-8,0,8,12,24))}
                view_yaws.add(math.radians(shot['yaw']))
                for view_yaw in sorted(view_yaws):
                    for pitch in ((0,-8,-16,-24) if recovery else (0,-4,-8)):
                        p=math.radians(pitch);forward=Vector((math.cos(view_yaw)*math.cos(p),math.sin(view_yaw)*math.cos(p),math.sin(p)))
                        rotation=forward.to_track_quat('-Z','Y');right=rotation@Vector((1,0,0));up=rotation@Vector((0,1,0))
                        corners=[v-pos for v in shot_fitting]
                        depths=[v.dot(forward) for v in corners]
                        if min(depths)<.15:continue
                        horizontal=max(abs(v.dot(right)/d) for v,d in zip(corners,depths))
                        slopes=[v.dot(up)/d for v,d in zip(corners,depths)]
                        lower,upper=min(slopes),max(slopes)
                        furniture_lower=min(slopes[:len(fitting)])
                        # Shift the sensor down instead of using a steep downward camera angle.
                        for aspect in ("4:3","16:9"):
                            half_height=13.5 if aspect=="4:3" else 10.125
                            # A shorter sensor needs extra downward shift to
                            # retain table legs while trimming empty upper wall.
                            shifts={.06,0,-.06,-.12}
                            shifts.update(round(max(-.3,min(.3,(lower+upper)*lens/72)),4) for lens in (20,24,28,32,35))
                            # Align the bottom of real furniture to a safe sensor margin,
                            # instead of centring the taller window+furniture union.
                            for trial_lens in ((24,28,32,35) if anchors else ()):
                                edge_shift=(furniture_lower*trial_lens+half_height*.88)/36
                                if -.3<=edge_shift<=.3:shifts.add(round(edge_shift,4))
                            for shift in sorted(shifts):
                                fits=[]
                                for lens in ((14,16,18,20,24,28,32,35) if recovery else (20,24,28,32,35)):
                                    if sensor_fit(horizontal,lower,upper,lens,half_height,shift):fits.append(lens)
                                if not fits:continue
                                lens=max(fits)
                                # Bound expensive native visibility rays per subject. Keep
                                # diverse positions/frames after exact frustum validation.
                                proxy=horizontal*lens/18*(max(slopes[:len(fitting)])-furniture_lower)*lens/(2*half_height)-distance*.03
                                key=(round(pos.x,3),round(pos.y,3),round(pos.z,3),aspect)
                                bucket=shortlist.setdefault(key,[])
                                bucket.append((proxy,(pos,distance,forward,right,up,view_yaw,pitch,lens,shift,aspect,half_height)))
                                bucket.sort(key=lambda pair:pair[0],reverse=True)
                                del bucket[2:]
        for _,sample in sorted((item for bucket in shortlist.values() for item in bucket),key=lambda pair:pair[0],reverse=True)[:512]:
            pos,distance,forward,right,up,view_yaw,pitch,lens,shift,aspect,half_height=sample
            subject=potential=occluded=foreground=wall=upperwall=floor_area=placeholder_area=foreground_floor=hero_potential=hero_occluded=edge_blocker=0
            hero_distance=max(.75,((lo+hi)/2-pos).length)
            for row in range(10):
                for col in range(14):
                    raydir=(forward+right*((2*(col+.5)/14-1)*18/lens)+up*((1-2*(row+.5)/10)*half_height/lens+shift*36/lens)).normalized()
                    intended=target.ray_cast(pos,raydir,10);hit=render_ray(scene,deps,pos,raydir,distance=10)
                    hero_hit=hero_target.ray_cast(pos,raydir,10)
                    if hero_hit[0] is not None:
                        hero_potential+=1
                        hero_occluded+=int(hit[0] and hit[4] not in hero_objects and (hit[1]-pos).length<hero_hit[3]-.02)
                    is_subject=hit[0] and hit[4] in objects
                    if intended[0] is not None:
                        potential+=1;occluded+=int(not is_subject and hit[0] and (hit[1]-pos).length<intended[3]-.02)
                    subject+=int(is_subject)
                    if hit[0]:
                        near=(hit[1]-pos).length<max(.75,hero_distance*.65)
                        foreground+=int(near and not is_subject and hit[4] not in floors and hit[4] not in walls)
                        edge_blocker+=int(near and col in (0,1,2,11,12,13) and not is_subject and hit[4] not in floors)
                        wall+=int(hit[4] in walls);upperwall+=int(row<5 and hit[4] in walls)
                        floor_area+=int(hit[4] in floors);placeholder_area+=int(hit[4] in placeholders)
                        foreground_floor+=int(row>=7 and hit[4] in floors)
            if potential<10 or subject<10 or foreground>14 or occluded/potential>.4 or hero_potential<3 or hero_occluded/hero_potential>.6:continue
            score=subject*.75-occluded*1.7-hero_occluded*2.5-edge_blocker*1.2-upperwall*.7-wall*.25-floor_area*.35-max(0,floor_area-35)*1.8-foreground_floor*.5-placeholder_area*1.5-max(0,placeholder_area-14)*2-foreground*.7-distance*.4+min(lens,28)*.08-max(0,24-lens)*1.5
            ranked.append((score,dict(shot_id=shot['id'],target=group['name'],context_object_ids=[o.get('studio_id') for o in context_objects],eye=list(pos),yaw=math.degrees(view_yaw),pitch=pitch,lens=lens,shift_y=shift,aspect=aspect,
                recovery_reason='從既有全景眼位檢查安全路徑；狹小空間允許較廣鏡頭，仍保留完整主體及窗景' if recovery else ('原效果圖鏡頭淨空不足，從既有全景眼位內恢復取景' if blocked_start else ''),preserved_windows=[a['id'] for a in anchors],window_sample_count=len(required_window_points),
                metrics=dict(hero_occlusion_fraction=round(hero_occluded/max(1,hero_potential),3),near_edge_blocker_fraction=round(edge_blocker/60,3),wide_angle_penalty=max(0,24-lens)*1.5,subject_fraction=round(subject/140,3),occlusion_fraction=round(occluded/potential,3),wall_fraction=round(wall/140,3),upper_wall_fraction=round(upperwall/70,3),floor_fraction=round(floor_area/140,3),foreground_floor_fraction=round(foreground_floor/42,3),placeholder_fraction=round(placeholder_area/140,3)))))
        chosen=[]
        balanced=sorted(ranked,key=lambda item:item[0],reverse=True)
        # Preserve useful trade-offs for visual review. A 15cm eye-height change
        # can expose a sofa seat without changing the furniture or window.
        less_occluded=sorted(ranked,key=lambda pair:(pair[1]['metrics']['hero_occlusion_fraction'],-pair[0]))
        less_wall=sorted(ranked,key=lambda pair:(pair[1]['metrics']['upper_wall_fraction'],-pair[0]))
        shortlist_review=[]
        for index in range(max(len(balanced),len(less_occluded),len(less_wall))):
            for ranking in (balanced,less_occluded,less_wall):
                if index<len(ranking):shortlist_review.append(ranking[index])
        for score,item in shortlist_review:
            if any((Vector(item['eye'])-Vector(c['eye'])).length<.45 and abs(item['eye'][2]-c['eye'][2])<.12 and abs(item['shift_y']-c['shift_y'])<.1 and item['aspect']==c['aspect'] for c in chosen):continue
            item['id']=f'{shot["id"]}:{group["id"]}:composition-{len(chosen)+1}';chosen.append(item)
            if len(chosen)==6:break
        result.extend(chosen)
    if not result and not recovery:
        return candidates(point,group,hero_objects,lo,hi,floors,walls,context_bounds,placeholders,context_objects,windows,True)
    return result


def actual_frame_integrity(design, point, by_id):
    """Project evaluated furniture vertices, distinguishing clipping from occlusion."""
    deps=bpy.context.evaluated_depsgraph_get();result=[]
    for group in design['groups']:
        purpose=(group.get('object_specification') or {}).get('purpose') or (group.get('asset_requirements') or {}).get('purpose')
        if group.get('deleted') or purpose not in ('sofa','table','coffee_table','desk','chair','bed','bunk_bed','cabinet','bookshelf','wardrobe','vanity','sink','cooker'):continue
        vertices=[]
        for key in group['children']:
            obj=by_id.get(key)
            if obj is None or obj.type!='MESH' or obj.hide_render:continue
            evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh()
            try:vertices.extend(evaluated.matrix_world@v.co for v in mesh.vertices)
            finally:evaluated.to_mesh_clear()
        if not vertices:continue
        lo=Vector([min(v[i] for v in vertices) for i in range(3)]);hi=Vector([max(v[i] for v in vertices) for i in range(3)])
        for shot in point['shots']:
            eye=Vector(shot.get('eye') or point['eye'])
            if ((lo+hi)/2-eye).length>6:continue
            forward,right,up=frame_axes(shot);half_height=10.125 if shot.get('aspect')=='16:9' else 13.5
            projected=[];behind=False
            for vertex in vertices:
                delta=vertex-eye;depth=delta.dot(forward)
                if depth<=.15:behind=True;continue
                projected.append((.5+delta.dot(right)/depth*shot['lens']/36,
                    .5-(delta.dot(up)/depth*shot['lens']-shot.get('shift_y',0)*36)/(2*half_height)))
            if not projected:continue
            bounds=[min(p[0] for p in projected),min(p[1] for p in projected),max(p[0] for p in projected),max(p[1] for p in projected)]
            if bounds[0]>1 or bounds[1]>1 or bounds[2]<0 or bounds[3]<0:continue
            result.append(dict(file=point['id']+'-'+shot['id']+'.png',group_id=group['id'],name=group['name'],purpose=purpose,
                bounds_uv=[round(v,5) for v in bounds],all_vertices_inside=not behind and min(bounds[:2])>=0 and max(bounds[2:])<=1,
                vertex_count=len(vertices),note='原生評估網格投影；完整在畫框內不代表沒有被其他物件遮擋，也不是美感分數'))
    return result
