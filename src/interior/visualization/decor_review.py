"""Measure real support triangles and render disposable material-preserving evidence."""
import math
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

PURPOSES={'vase','books','tableware'}

def transform(group):
    p=Vector(group.get('rotation_pivot',[0,0,0]));d=Vector(group.get('translation',[0,0,0]))
    return Matrix.Translation(d+p)@Matrix.Rotation(math.radians(group.get('rotation',0)),4,'Z')@Matrix.Translation(-p)

def support_check(design,group,meshes):
    context=group.get('decor_context')
    if not context:return dict(status='unavailable',reason='沒有可追溯的承載物件；僅產生視覺證據')
    support=next((g for g in design['groups'] if g['id']==context['support_group_id'] and not g.get('deleted')),None)
    if not support:raise ValueError('裝飾物的承載家具已刪除，保留原件')
    by_id={o.get('studio_id'):o for o in bpy.context.scene.objects};deps=bpy.context.evaluated_depsgraph_get()
    vertices=[];faces=[]
    for identifier in support['children']:
        obj=by_id.get(identifier)
        if not obj or obj.type not in ('MESH','CURVE'):continue
        evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh()
        matrix=transform(support)@obj.matrix_world;offset=len(vertices)
        vertices.extend(matrix@v.co for v in mesh.vertices)
        faces.extend(tuple(offset+i for i in f.vertices) for f in mesh.polygons)
        evaluated.to_mesh_clear()
    if not faces:raise ValueError('承載家具沒有可檢查的實際表面')
    tree=BVHTree.FromPolygons(vertices,faces)
    decor_vertices=[];decor_faces=[]
    for obj in meshes:
        evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh();offset=len(decor_vertices);matrix=transform(group)@obj.matrix_world
        decor_vertices.extend(matrix@v.co for v in mesh.vertices)
        decor_faces.extend(tuple(offset+i for i in f.vertices) for f in mesh.polygons)
        evaluated.to_mesh_clear()
    points=[transform(group)@o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
    lo=Vector([min(p[i] for p in points) for i in range(3)]);hi=Vector([max(p[i] for p in points) for i in range(3)])
    center=(lo+hi)/2;center.z=lo.z
    samples=[(0,0),(-.25,-.25),(-.25,.25),(.25,-.25),(.25,.25)]
    # Only automatic staging may make a small placement correction, within its own support.
    offsets=sorted(((x,y) for x in (0,-.04,.04,-.08,.08) for y in (0,-.04,.04,-.08,.08)),key=lambda p:p[0]**2+p[1]**2)
    for dx,dy in offsets:
        hits=[]
        for sx,sy in samples:
            start=Vector((center.x+dx+sx*(hi.x-lo.x),center.y+dy+sy*(hi.y-lo.y),lo.z+.10))
            hit,normal,_,_=tree.ray_cast(start,Vector((0,0,-1)),.22)
            if hit is not None and normal.z>.65:hits.append(hit.z)
        if len(hits)<3 or max(hits)-min(hits)>.012:continue
        dz=max(hits)+.002-lo.z
        shift=Vector((dx,dy,dz))
        actual=BVHTree.FromPolygons([v+shift for v in decor_vertices],decor_faces)
        if tree.overlap(actual):continue
        group['translation']=[v+d for v,d in zip(group.get('translation',[0,0,0]),(dx,dy,dz))]
        return dict(status='passed',support_group_id=support['id'],surface_samples=len(hits),translation=[dx,dy,dz],support_intersections=0,method='evaluated_triangle_raycast_and_overlap')
    raise ValueError('裝飾物缺少實際檯面支撐；同一承載物件附近 8cm 內未找到可用平面，不以包圍盒當作桌面')

def previews(design,group,meshes,output):
    original=bpy.context.window.scene;scene=bpy.data.scenes.new('Disposable decor inspection');created=[]
    try:
        bpy.context.window.scene=scene
        scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
        scene.render.resolution_x=512;scene.render.resolution_y=512;scene.render.resolution_percentage=100
        scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
        scene.world=bpy.data.worlds.new('Review neutral world');scene.world.use_nodes=True
        scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.6,.6,.6,1)
        scene.world.node_tree.nodes['Background'].inputs[1].default_value=.5
        def duplicate(obj,matrix):
            clone=obj.copy();clone.matrix_world=matrix@obj.matrix_world;scene.collection.objects.link(clone);created.append(clone);return clone
        copies=[duplicate(o,transform(group)) for o in meshes]
        corners=[o.matrix_world@Vector(c) for o in copies for c in o.bound_box]
        lo=Vector([min(p[i] for p in corners) for i in range(3)]);hi=Vector([max(p[i] for p in corners) for i in range(3)])
        center=(lo+hi)/2;size=max(hi-lo)
        camera=bpy.data.objects.new('Review camera',bpy.data.cameras.new('Review camera'));scene.collection.objects.link(camera);created.append(camera);scene.camera=camera
        camera.data.type='ORTHO';camera.data.clip_start=.001;camera.data.clip_end=100
        light=bpy.data.objects.new('Review softbox',bpy.data.lights.new('Review softbox','AREA'));scene.collection.objects.link(light);created.append(light)
        light.location=center+Vector((-.6,-.5,1));light.data.energy=65;light.data.shape='DISK';light.data.size=1
        light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
        files=[]
        for mode in ('object','context'):
            if mode=='context':
                context=group.get('decor_context') or {};support=next((g for g in design['groups'] if g['id']==context.get('support_group_id')),None)
                by_id={o.get('studio_id'):o for o in original.objects}
                if support:
                    for identifier in support['children']:
                        if identifier in by_id:duplicate(by_id[identifier],transform(support))
            camera.data.ortho_scale=max(.12,size*(1.65 if mode=='object' else 3.5))
            camera.location=center+Vector((1,-1,.85))*max(size*3,1)
            camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
            filename='decor-'+mode+'.png';scene.render.filepath=str(output/filename)
            bpy.ops.render.render(write_still=True);files.append(filename)
        return dict(version=1,images=files,purpose=(group.get('asset_requirements') or {}).get('purpose'),method='native_material_local_preview')
    finally:
        bpy.context.window.scene=original
        for obj in created:bpy.data.objects.remove(obj,do_unlink=True)
        world=scene.world;bpy.data.scenes.remove(scene)
        if world and not world.users:bpy.data.worlds.remove(world)
