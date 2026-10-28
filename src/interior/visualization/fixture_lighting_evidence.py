"""Read-only native geometry evidence for existing-fixture lighting."""
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0,str(Path(__file__).parent))
WORKER_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def meshes_for(group, by_id):
    return [by_id[key] for key in group['children'] if key in by_id and by_id[key].type=='MESH' and not by_id[key].hide_render]


def corners(meshes):
    return [o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]


def bounds(points):
    return [[min(p[a] for p in points) for a in range(3)], [max(p[a] for p in points) for a in range(3)]]


def materials(obj):
    return [m.name for m in obj.data.materials if m]


def inventory(design, by_id):
    groups=[]
    for group in design['groups']:
        if group.get('deleted'):continue
        meshes=meshes_for(group,by_id);points=corners(meshes)
        item=dict(id=group['id'],name=group['name'],components=[],triangles=[],sampled=False)
        groups.append(item)
        if not points:
            item['error']='缺少可辨識原生網格，請手動確認';continue
        box=bounds(points);item.update(bounds=box,dimensions=[b-a for a,b in zip(*box)])
        if any(not math.isfinite(v) for p in box for v in p):
            item['error']='模型座標無效';continue
        # Include every component's name/material; cap duplicate descriptive rows, not geometry coverage.
        descriptions=list(dict.fromkeys((o.name,tuple(materials(o))) for o in meshes))
        item['components']=[dict(name=n,materials=list(m)) for n,m in descriptions[:80]]
        item['component_count']=len(meshes)
        if len(descriptions)>80:item['components_truncated']=True
        counts=[]
        for obj in meshes:
            obj.data.calc_loop_triangles();counts.append(len(obj.data.loop_triangles))
        total=sum(counts);item['sampled']=total>2400
        if not total:
            item['error']='網格沒有可辨識表面';continue
        # Sampling is distributed across all components; no name-based exclusion.
        for obj,count in zip(meshes,counts):
            step=max(1,math.ceil(count/max(1,2400*count/max(total,1))))
            for triangle_index in range(0,count,step):
                triangle=obj.data.loop_triangles[triangle_index]
                material=obj.data.materials[triangle.material_index] if triangle.material_index<len(obj.data.materials) else None
                color=list(material.diffuse_color[:3]) if material else [.7,.7,.7]
                normal=obj.matrix_world.to_3x3().inverted_safe().transposed()@triangle.normal
                normal.normalize();shade=.5+.5*abs(normal.dot(Vector((.3,-.4,.866))))
                item['triangles'].append(dict(points=[list(obj.matrix_world@obj.data.vertices[i].co) for i in triangle.vertices],
                                              color=[c*shade for c in color]))
    from studio_lighting import propose
    native=[]
    if any(o.type=='LIGHT' for o in bpy.context.scene.objects):
        # propose also supports a fallback, so collect actual native IDs only.
        proposal,_=propose(dict(design,viewpoints=[]))
        ids={hashlib.sha256(o.name.encode()).hexdigest()[:24] for o in bpy.context.scene.objects if o.type=='LIGHT'}
        native=[l for l in proposal['lights'] if l['id'] in ids]
    return dict(groups=groups,native_lights=native)


def surface_anchors(meshes):
    vertices=[];faces=[];sources=[]
    for obj in meshes:
        offset=len(vertices);vertices.extend(obj.matrix_world@v.co for v in obj.data.vertices)
        for polygon in obj.data.polygons:
            indices=tuple(offset+i for i in polygon.vertices)
            if obj.matrix_world.to_3x3().determinant()<0:indices=tuple(reversed(indices))
            faces.append(indices);sources.append((obj,polygon.material_index))
    if not faces:raise ValueError('此燈具沒有可量測發光表面')
    tree=BVHTree.FromPolygons(vertices,faces,all_triangles=False)
    box=bounds(vertices);anchors=[]
    def cast(axis,sign,center,extent,ray_tree=None,ray_sources=None,ray_box=None):
        ray_tree=ray_tree or tree;ray_sources=ray_sources or sources;ray_box=ray_box or box
        if len(anchors)>=(96 if ray_tree is tree else 256):return
        origin=Vector(center);origin[axis]=ray_box[0 if sign>0 else 1][axis]-sign*.1
        direction=Vector((0,0,0));direction[axis]=sign
        hit,normal,index,_=ray_tree.ray_cast(origin,direction,max(ray_box[1][axis]-ray_box[0][axis]+.2,.3))
        if hit is None:return
        # Select only actual outward entry surfaces. Inverted shells are left for manual review.
        if normal.dot(direction)>-.05:return
        if any((hit-Vector(a['position'])).length<.012 for a in anchors):return
        obj,material_index=ray_sources[index]
        material=obj.data.materials[material_index] if material_index<len(obj.data.materials) else None
        anchors.append(dict(id='a'+str(len(anchors)),position=list(hit),normal=list(normal.normalized()),
                            object_id=obj.get('studio_id'),component=obj.name,material=material.name if material else '',
                            max_size=max(.01,min(1,extent)),surface_scope='component' if ray_tree is not tree else 'fixture_envelope'))
    center=[(a+b)/2 for a,b in zip(*box)]
    # Outer envelope grid plus component-centre rays, retaining small bulbs in multi-part fittings.
    for axis in range(3):
        axes=[a for a in range(3) if a!=axis]
        for sign in (-1,1):
            for u in (.2,.5,.8):
                for v in (.2,.5,.8):
                    sample=list(center)
                    for a,f in zip(axes,(u,v)):sample[a]=box[0][a]+f*(box[1][a]-box[0][a])
                    cast(axis,sign,sample,min(box[1][a]-box[0][a] for a in axes))
    for obj in meshes[:80]:
        object_box=bounds(corners([obj]));sample=[(a+b)/2 for a,b in zip(*object_box)]
        for axis in range(3):
            extent=min(object_box[1][a]-object_box[0][a] for a in range(3) if a!=axis)
            for sign in (-1,1):cast(axis,sign,sample,extent)
    # A shade or pole can occlude every envelope ray toward an interior bulb.
    # Measure the actual constituent mesh as well; no aperture or bulb is invented.
    covered={a['object_id'] for a in anchors}
    small=[];overall=max(b-a for a,b in zip(*box))
    for obj in meshes:
        component_box=bounds(corners([obj]));dims=sorted(b-a for a,b in zip(*component_box))
        if .012<=dims[-1]<=max(.15,overall*.65) and 0<len(obj.data.polygons)<=150000:
            small.append((obj.get('studio_id') in covered,dims[-1]/max(.001,dims[-2]),obj.name,obj,component_box))
    for _,__,___,obj,component_box in sorted(small,key=lambda row:row[:3])[:40]:
        if len(anchors)>=256:break
        component_vertices=[obj.matrix_world@v.co for v in obj.data.vertices]
        reverse=obj.matrix_world.to_3x3().determinant()<0
        component_faces=[tuple(reversed(p.vertices)) if reverse else tuple(p.vertices) for p in obj.data.polygons]
        component_tree=BVHTree.FromPolygons(component_vertices,component_faces,all_triangles=False)
        component_sources=[(obj,p.material_index) for p in obj.data.polygons]
        for axis in range(3):
            axes=[a for a in range(3) if a!=axis]
            for sign in (-1,1):
                for u in (.2,.5,.8):
                    for v in (.2,.5,.8):
                        sample=[(a+b)/2 for a,b in zip(*component_box)]
                        for a,f in zip(axes,(u,v)):sample[a]=component_box[0][a]+f*(component_box[1][a]-component_box[0][a])
                        cast(axis,sign,sample,min(component_box[1][a]-component_box[0][a] for a in axes),component_tree,component_sources,component_box)
    return anchors


def same_mesh_lights(design,by_id,target_meshes):
    """Read-only evidence of linked, equally sized emitting components elsewhere."""
    from mathutils import Euler
    def key(obj):return (obj.data.as_pointer(),tuple(slot.material.name if slot.material else '' for slot in obj.material_slots))
    targets={};result={};cache={}
    for obj in target_meshes:targets.setdefault(key(obj),[]).append(obj)
    groups={g['id']:g for g in design['groups'] if not g.get('deleted')}
    for spec in design.get('lighting_setup',{}).get('lights',[]):
        if spec.get('origin')!='proposal' or not spec['id'].startswith('fixture-') or not spec.get('enabled') or spec['power']<=0:continue
        group=groups.get(spec.get('group_id'))
        if not group:continue
        direction=Euler(spec['rotation'],'XYZ').to_matrix()@Vector((0,0,-1))
        surface=Vector(spec['position'])-direction*.015
        for obj in meshes_for(group,by_id):
            if not obj.data.polygons:continue
            matches=targets.get(key(obj),[])
            if not matches:continue
            if obj.data.as_pointer() not in cache:
                cache[obj.data.as_pointer()]=BVHTree.FromPolygons([v.co for v in obj.data.vertices],
                    [tuple(p.vertices) for p in obj.data.polygons],all_triangles=False)
            tree=cache[obj.data.as_pointer()]
            hit,_,__,___=tree.find_nearest(obj.matrix_world.inverted_safe()@surface)
            if hit is None or (obj.matrix_world@hit-surface).length>.002:continue
            for target in matches:
                if target is obj:continue
                relative=(target.matrix_world@obj.matrix_world.inverted_safe()).to_3x3()
                gram=relative.transposed()@relative
                if max(abs(gram[i][j]-(1 if i==j else 0)) for i in range(3) for j in range(3))>1e-4:continue
                rows=result.setdefault(target.get('studio_id'),[])
                if len(rows)>=3:continue
                rows.append(dict(source_light_id=spec['id'],source_group_id=group['id'],source_component_id=obj.get('studio_id'),
                    shared_native_mesh=obj.data.name,materials=list(key(obj)[1]),same_physical_size=True,
                    source_surface_distance=(obj.matrix_world@hit-surface).length,
                    kind=spec['kind'],power=spec['power'],color=spec['color'],size=spec['size'],
                    limitation='相同原生網格／材質與等尺寸的已確認發光組成（可能為本工作尚未採用的提案）；瓦數與光色仍為推定參考，並非原廠測光'))
    return result


def detail(design,by_id,identifier,output):
    from model_review import previews
    group=next(g for g in design['groups'] if g['id']==identifier and not g.get('deleted'))
    meshes=meshes_for(group,by_id)
    anchors=surface_anchors(meshes)
    if not anchors:raise ValueError('無可靠外向發光表面，請手動確認')
    from decor_review import transform
    change=transform(group)
    for anchor in anchors:
        anchor['world_position']=list(change@Vector(anchor['position']))
        anchor['world_normal']=list((change.to_3x3()@Vector(anchor['normal'])).normalized())
    views=previews(design,group,meshes,output,modes=('object','reverse','bottom'))
    # A whole track can make a lamp head only a few pixels wide. Frame the small
    # assemblies more closely, retaining every original mesh and material.
    full=bounds(corners(meshes));extent=max(b-a for a,b in zip(*full));clusters=[]
    for obj in sorted(meshes,key=lambda o:o.name):
        box=bounds(corners([obj]));span=max(b-a for a,b in zip(*box))
        if not .025<=span<extent*.4:continue
        center=Vector([(a+b)/2 for a,b in zip(*box)])
        cluster=next((c for c in clusters if (center-c['center']).length<max(.08,extent*.12)),None)
        if cluster:cluster['meshes'].append(obj)
        else:clusters.append(dict(center=center,meshes=[obj]))
    closeups=[]
    for index,cluster in enumerate(clusters[:6]):
        box=bounds([change@p for p in corners(cluster['meshes'])]);center=[(a+b)/2 for a,b in zip(*box)]
        width=max(.12,max(b-a for a,b in zip(*box))*1.25)
        framed=[[v-width/2 for v in center],[v+width/2 for v in center]]
        folder=output/f'closeup-{index}';folder.mkdir(exist_ok=True)
        cropped=previews(design,group,meshes,folder,modes=('object','bottom'),focus_bounds=framed)
        filenames=[f'closeup-{index}/'+name for name in cropped['images']]
        views['images'].extend(filenames)
        closeups.append(dict(images=filenames,world_bounds=framed,component_ids=[o.get('studio_id') for o in cluster['meshes']]))
    return dict(group_id=identifier,name=group['name'],anchors=anchors,images=views['images'],directory=str(output),closeups=closeups,
                matched_existing_fixture_lights=same_mesh_lights(design,by_id,meshes),
                coordinate_system='Blender metres, base global coordinates before group translation/rotation',
                limitation='局部模型與表面方向證據，非整屋照度或陰影驗收')


def main():
    source,target=sys.argv[sys.argv.index('--')+1:]
    request=json.loads(Path(source).read_text(encoding='utf-8'))
    bpy.ops.wm.open_mainfile(filepath=request['native'])
    design=request['scene']
    from concept_geometry import add_blender_furniture
    add_blender_furniture(design.get('concept_furniture',[]))
    bpy.context.view_layer.update()
    by_id={o.get('studio_id'):o for o in bpy.context.scene.objects if o.get('studio_id')}
    if request['mode']=='inventory':result=inventory(design,by_id)
    else:result=detail(design,by_id,request['group_id'],Path(target).parent)
    result['worker_sha256']=WORKER_SHA256
    result['surface_sampling']='fixture_envelope_and_native_components'
    Path(target).write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf-8')


if __name__=='__main__':main()
