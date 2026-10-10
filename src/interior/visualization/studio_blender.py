"""Blender entrypoint for stable native/GLB identity and revision-bound renders.

Run only through the Studio worker. No source model is ever saved in place.
"""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from uuid import UUID, uuid5
import bpy
from mathutils import Vector

request = json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
output = Path(request['output'])
if Path(request['source']).suffix.lower()=='.glb':
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=request['source'])
else:
    bpy.ops.wm.open_mainfile(filepath=request['source'])
scene = bpy.context.scene
sys.path.insert(0,str(Path(__file__).resolve().parent))
from studio_render_checks import inspect_scene, inspect_image

def write(name, value):
    (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def geometry_digest():
    value=[]
    for obj in sorted(bpy.data.objects,key=lambda o:o.name):
        if obj.type == 'CURVE':
            value.append((obj.get('studio_id',obj.name), [list(r) for r in obj.matrix_world],
                [[list(p.co) for p in spline.bezier_points]+[list(p.co) for p in spline.points] for spline in obj.data.splines]))
        if obj.type == 'MESH':
            value.append((obj.get('studio_id',obj.name),list(sum((list(r) for r in obj.matrix_world),[])),
                len(obj.data.vertices),len(obj.data.polygons),
                hashlib.sha256(b''.join(struct.pack('<fff',*v.co) for v in obj.data.vertices)).hexdigest()))
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

if request['mode'] == 'prepare':
    namespace = UUID(request['source_sha256'][:32])
    objects=[]
    for obj in bpy.data.objects:
        if obj.type in ('MESH', 'CURVE'):
            obj['studio_id']=obj.get('studio_id') or uuid5(namespace,obj.name).hex
            objects.append(dict(id=obj['studio_id'],name=obj.name,
                center=list(obj.matrix_world.translation),materials=[m.name if m else None for m in obj.data.materials]))
    # Preserve the optimized display geometry, adding explicit native IDs to its nodes.
    # Unknown display meshes fail import rather than silently selecting a wrong object.
    raw=Path(request['preview']).read_bytes()
    magic,version,length=struct.unpack_from('<III',raw)
    if magic!=0x46546C67 or version!=2 or length!=len(raw):
        raise ValueError('Preview is not a valid GLB 2')
    size,kind=struct.unpack_from('<II',raw,12)
    gltf=json.loads(raw[20:20+size])
    by_name={o['name']:o['id'] for o in objects}
    known_ids={o['id'] for o in objects}
    mapped=set()
    unknown=[]
    for node in gltf.get('nodes',[]):
        if 'mesh' in node:
            name=node.get('name','')
            existing=node.get('extras',{}).get('studio_id')
            identifier=existing if existing in known_ids else by_name.get(name)
            if identifier is None:
                unknown.append(name)
                continue
            node.setdefault('extras',{})['studio_id']=identifier
            mapped.add(identifier)
    if unknown:
        raise ValueError('GLB objects lack native mapping: '+repr(unknown[:20]))
    payload=json.dumps(gltf,separators=(',',':'),ensure_ascii=False).encode()
    payload+=b' '*((-len(payload))%4)
    rest=raw[20+size:]
    (output/'model.glb').write_bytes(struct.pack('<III',magic,version,20+len(payload)+len(rest))+struct.pack('<II',len(payload),kind)+payload+rest)
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'model.blend'),compress=True)
    write('model.json',dict(id=request['model_id'],source_sha256=request['source_sha256'],
        objects=objects,selectable_ids=sorted(mapped),geometry_sha256=geometry_digest(),coordinate_system='Blender Z-up metres',render_readiness=inspect_scene(scene)))
elif request['mode']=='lighting':
    from studio_lighting import propose
    setup,notes=propose(request['scene'],request.get('lighting_source'))
    setup['source_job_id']=request['job_id']
    write('result.json',dict(lighting_setup=setup,notes=notes,revision=request['revision'],model_id=request['model_id'],lighting_source=request.get('lighting_source')))
else:
    design=request['scene']
    before=geometry_digest()
    by_id={o.get('studio_id'):o for o in bpy.data.objects if o.type in ('MESH','CURVE')}
    # Apply revision edits in world space; never edit the immutable prepared model.
    edited=[]
    matrices={key:o.matrix_world.copy() for key,o in by_id.items()}
    for group in design.get('groups',[]):
        delta=Vector(group.get('translation',[0,0,0]))
        for identifier in group['children']:
            obj=by_id[identifier]
            matrix=matrices[identifier].copy();matrix.translation+=delta
            if delta.length:
                obj.matrix_world=matrix
            if group.get('deleted'):
                obj.hide_render=True;obj.hide_set(True)
        if delta.length or group.get('deleted'):edited.append(group['id'])
    bpy.context.view_layer.update()
    after_edits=geometry_digest()
    applied=[]
    for assignment in design['objects']:
        spec=assignment['material']
        if not spec.get('color'):
            continue
        obj=by_id[assignment['id']]
        material=bpy.data.materials.new('Studio '+assignment['id'])
        material.use_nodes=True
        shader=material.node_tree.nodes.get('Principled BSDF')
        srgb=[int(spec['color'][n:n+2],16)/255 for n in (1,3,5)]
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in srgb]
        shader.inputs['Base Color'].default_value=(*linear,1)
        shader.inputs['Roughness'].default_value=spec.get('roughness',.5)
        # Detach shared mesh data before changing slots; only selected object changes.
        obj.data=obj.data.copy()
        obj.data.materials.clear()
        obj.data.materials.append(material)
        applied.append(assignment['id'])
    if geometry_digest()!=after_edits:
        raise ValueError('Material assignment changed geometry')
    from studio_lighting import apply
    apply(design,request.get('lighting_source'))
    if design.get('lighting_setup',{}).get('enabled'):
        write('lighting-applied.json',dict(revision=request['revision'],lights=[dict(id=o.get('studio_light_id'),position=list(o.matrix_world.translation),power=o.data.energy) for o in scene.objects if o.type=='LIGHT' and not o.hide_render]))
    readiness=inspect_scene(scene)
    write('render-readiness.json',dict(readiness,revision=request['revision']))
    if readiness['status']=='blocked':
        raise ValueError('渲染前檢查未通過：'+'；'.join(readiness['issues']))
    scene.render.engine='CYCLES'
    scene.cycles.samples=16 if request['quality']=='preview' else 96
    scene.cycles.use_denoising=True
    scene.cycles.use_adaptive_sampling=True
    scene.cycles.adaptive_threshold=.04 if request['quality']=='preview' else .02
    scene.cycles.seed=17
    try:
        preferences=bpy.context.preferences.addons['cycles'].preferences
        preferences.compute_device_type='OPTIX'
        preferences.get_devices()
        gpu=False
        for device in preferences.devices:
            device.use=device.type!='CPU'
            gpu=gpu or device.use
        scene.cycles.device='GPU' if gpu else 'CPU'
    except Exception:
        scene.cycles.device='CPU'
    # Existing model lighting and material node trees remain intact.
    scene.use_nodes=False
    scene.render.image_settings.file_format='PNG'
    scene.render.resolution_percentage=100
    scene.render.use_compositing=False
    scene.render.film_transparent=False
    images=[]
    total=sum(1+len(p['shots']) for p in design['viewpoints'])
    checks=[]
    for probing in ((True,) if request.get('probe_only') else (True,False)):
        scene.cycles.samples=8 if probing else (16 if request['quality']=='preview' else 96)
        for point in design['viewpoints']:
            specs=[dict(id='panorama',name='360°',kind='panorama',yaw=0,pitch=0,lens=24)]+[dict(s,kind='still') for s in point['shots']]
            for shot in specs:
                if request.get('stop_file') and Path(request['stop_file']).exists():
                    raise ValueError('已完成目前圖片，停止後續照明與出圖')
                name=('probe-' if probing else '')+point['id']+'-'+shot['id']+'.png'
                camera=bpy.data.cameras.new('Studio camera')
                obj=bpy.data.objects.new('Studio camera',camera)
                scene.collection.objects.link(obj)
                obj.location=point['eye']
                scene.camera=obj
                if shot['kind']=='panorama':
                    camera.type='PANO'
                    camera.panorama_type='EQUIRECTANGULAR'
                    obj.rotation_euler=(math.pi/2,0,-math.pi/2)
                    width=1024 if request['quality']=='preview' else 4096
                    height=width//2
                else:
                    camera.type='PERSP'
                    camera.lens=shot['lens']
                    yaw,pitch=math.radians(shot['yaw']),math.radians(shot['pitch'])
                    direction=Vector((math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),math.sin(pitch)))
                    obj.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
                    width,height=(640,480) if request['quality']=='preview' else (1600,1200)
                if probing:
                    width,height=(192,96) if shot['kind']=='panorama' else (128,96)
                scene.render.resolution_x=width
                scene.render.resolution_y=height
                scene.render.filepath=str(output/name)
                write('progress.json',dict(completed=len(checks) if probing else len(images),total=total,current=('試渲染檢查 · ' if probing else '正式出圖 · ')+point['name']+' '+shot['name']))
                bpy.ops.render.render(write_still=True)
                image=bpy.data.images.load(str(output/name),check_existing=False)
                assessment=inspect_image(image)
                if probing or assessment['status']=='blocked':
                    checks.append(dict(assessment,phase='probe' if probing else 'output',file=name,viewpoint_id=point['id'],shot_id=shot['id']))
                    write('quality-checks.json',dict(revision=request['revision'],status='blocked' if assessment['status']=='blocked' else 'checking',checks=checks))
                if assessment['status']=='blocked':
                    bpy.data.images.remove(image)
                    raise ValueError('亮度檢查未通過：'+point['name']+' '+shot['name']+'。'+assessment['reason']+' 已停止後續出圖，原件未修改。')
                if probing:
                    bpy.data.images.remove(image)
                    bpy.data.objects.remove(obj,do_unlink=True)
                    continue
                image.scale(320,160 if shot['kind']=='panorama' else 240)
                image.filepath_raw=str(output/('thumb-'+name))
                image.save()
                bpy.data.images.remove(image)
                images.append(dict(name=point['name']+' · '+shot['name'],file=name,thumbnail='thumb-'+name,
                    viewpoint_id=point['id'],shot_id=shot['id'],kind=shot['kind'],width=width,height=height,
                    quality=request['quality'],sha256=hashlib.sha256((output/name).read_bytes()).hexdigest()))
                bpy.data.objects.remove(obj,do_unlink=True)
    write('quality-checks.json',dict(revision=request['revision'],status='passed',checks=checks,visual_review='pending',quality_check='passed'))
    if request.get('probe_only'):
        write('result.json',dict(revision=request['revision'],quality_check='passed',probe_only=True))
        sys.exit(0)
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'rendered-model.blend'),compress=True)
    write('progress.json',dict(completed=total,total=total,current='完成'))
    write('result.json',dict(images=images,revision=request['revision'],model_id=request['model_id'],
        applied_object_ids=applied,geometry_preserved=geometry_digest()==before,device=scene.cycles.device,
        edited_group_ids=edited,material_geometry_preserved=geometry_digest()==after_edits,
        visual_review='pending',quality_check='passed'))
