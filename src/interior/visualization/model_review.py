"""Disposable native-material furniture evidence, independent of any project."""
import math
import bpy
from mathutils import Vector
from decor_review import transform


def inspect(meshes):
    vertices=[o.matrix_world@v.co for o in meshes for v in o.data.vertices]
    faces=sum(len(o.data.polygons) for o in meshes)
    if not vertices or not faces or any(not math.isfinite(x) for v in vertices for x in v):
        raise ValueError('實際模型包含空網格或無效座標，保留原件')
    size=[max(v[i] for v in vertices)-min(v[i] for v in vertices) for i in range(3)]
    if min(size)<.001:raise ValueError('實際模型退化為平面或線段，保留原件')
    return dict(status='passed',vertices=len(vertices),faces=faces,dimensions=size,
                method='evaluated_mesh_finite_coordinates_and_extent')


def previews(design,group,meshes,output,modes=None,stop_file=None,focus_bounds=None):
    original=bpy.context.window.scene
    scene=bpy.data.scenes.new('Disposable furniture inspection');created=[];data=[]
    context_ids=[];omitted=[]
    try:
        bpy.context.window.scene=scene
        scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
        try:
            preferences=bpy.context.preferences.addons['cycles'].preferences
            preferences.compute_device_type='OPTIX';preferences.get_devices()
            for device in preferences.devices:device.use=device.type!='CPU'
            scene.cycles.device='GPU' if any(d.use for d in preferences.devices) else 'CPU'
        except Exception:scene.cycles.device='CPU'
        scene.render.resolution_x=512;scene.render.resolution_y=512;scene.render.resolution_percentage=100
        scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
        scene.world=bpy.data.worlds.new('Review neutral world');scene.world.use_nodes=True
        scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.6,.6,.6,1)
        scene.world.node_tree.nodes['Background'].inputs[1].default_value=.5
        def duplicate(obj,matrix):
            clone=obj.copy();clone.parent=None;clone.matrix_world=matrix@obj.matrix_world
            scene.collection.objects.link(clone);created.append(clone);return clone
        copies=[duplicate(o,transform(group)) for o in meshes]
        points=[o.matrix_world@Vector(c) for o in copies for c in o.bound_box]
        lo=Vector([min(p[i] for p in points) for i in range(3)])
        hi=Vector([max(p[i] for p in points) for i in range(3)]);center=(lo+hi)/2;size=max(hi-lo)
        if focus_bounds:
            lo,hi=map(Vector,focus_bounds);center=(lo+hi)/2;size=max(hi-lo)
        cam_data=bpy.data.cameras.new('Review camera');data.append(cam_data)
        camera=bpy.data.objects.new('Review camera',cam_data);created.append(camera);scene.collection.objects.link(camera);scene.camera=camera
        camera.data.type='ORTHO';camera.data.clip_start=.001;camera.data.clip_end=1000
        light_data=bpy.data.lights.new('Review softbox','AREA');data.append(light_data)
        light=bpy.data.objects.new('Review softbox',light_data);created.append(light);scene.collection.objects.link(light)
        light.location=center+Vector((-1,-1,2))*max(size,1)
        if group.get('fixture_installation'):light.location=center+Vector((-1,-1,-1))*max(size,1)
        light.data.energy=120*max(size,1)**2;light.data.size=max(size,1)*2
        light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
        files=[];by_id={o.get('studio_id'):o for o in original.objects}
        directions=[('object',(1,-1,.8)),('reverse',(-1,1,.8)),('context',(1,-1,2))]
        if modes and 'bottom' in modes:directions.append(('bottom',(1,-1,-1.5)))
        if group.get('fixture_installation',{}):directions[-1]=('context',(1,-1,-.35))
        if modes and any(m.startswith('axis-') for m in modes):
            directions=[('axis-positive-x',(1,0,.12)),('axis-negative-x',(-1,0,.12)),('axis-positive-y',(0,1,.12)),('axis-negative-y',(0,-1,.12))]
        for mode,direction in directions:
            if modes and mode not in modes:continue
            if stop_file and stop_file.exists():raise ValueError('已停止後續局部圖')
            if mode=='context':
                for other in design['groups']:
                    if other['id']==group['id'] or other.get('deleted'):continue
                    if group.get('fixture_installation') and other['id']!=group['fixture_installation']['ceiling_group_id']:
                        omitted.extend(other['children']);continue
                    added=False
                    for identifier in other['children']:
                        obj=by_id.get(identifier)
                        if not obj or obj.type not in ('MESH','CURVE'):continue
                        matrix=transform(other);corners=[matrix@obj.matrix_world@Vector(c) for c in obj.bound_box]
                        a=Vector([min(p[i] for p in corners) for i in range(3)]);b=Vector([max(p[i] for p in corners) for i in range(3)])
                        radius=max(.8,size*.6)
                        if any(b[i]<lo[i]-radius or a[i]>hi[i]+radius for i in (0,1)):continue
                        # A local cutaway excludes overhead and camera-facing tall occluders.
                        # Record exclusions: this view is evidence of placement, not a full room render.
                        if a.z>hi.z+.15 or (b.z>hi.z+.4 and (a.x>center.x or b.y<center.y)):
                            omitted.append(identifier);continue
                        duplicate(obj,matrix);added=True
                    if added:context_ids.append(other['id'])
            camera.data.ortho_scale=max(.2,size*(2.0 if mode!='context' else 3))
            camera.location=center+Vector(direction)*max(size*4,2)
            camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
            filename='model-'+mode+'.png';scene.render.filepath=str(output/filename)
            bpy.ops.render.render(write_still=True);files.append(filename)
        return dict(version=2,images=files,method='native_material_selected_views' if modes else 'native_material_three_view_local_cutaway',
                    context_group_ids=context_ids,omitted_occluder_ids=omitted,
                    camera_directions=[v for k,v in directions if not modes or k in modes],
                    context_limit='燈具與實際天花接合的局部證據；其他家具牆體略去，碰撞另由原生幾何檢查，不能代替整屋驗收' if group.get('fixture_installation') else '局部剖視；前方遮擋牆與上方物件略去，不能代替整屋動線驗收')
    finally:
        bpy.context.window.scene=original
        for obj in created:bpy.data.objects.remove(obj,do_unlink=True)
        for block in data:
            if isinstance(block,bpy.types.Camera):bpy.data.cameras.remove(block)
            else:bpy.data.lights.remove(block)
        world=scene.world;bpy.data.scenes.remove(scene)
        if world and not world.users:bpy.data.worlds.remove(world)
