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
from mathutils import Vector, Matrix, Quaternion

request = json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
output = Path(request['output'])
sys.path.insert(0,str(Path(__file__).resolve().parent))
if request.get('plan'):
    from plan_blender import build_plan
    build_report=build_plan(request)
    (output/'plan-build.json').write_text(json.dumps(build_report,ensure_ascii=False,indent=2),encoding='utf-8')
elif Path(request['source']).suffix.lower()=='.glb':
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=request['source'])
else:
    bpy.ops.wm.open_mainfile(filepath=request['source'])
if request.get('asset'):
    from asset_blender import replace_asset
    replace_asset(request)
import door_asset_geometry
door_asset_geometry.FILES=request.get('door_asset_files',{})
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

if request['mode']=='diagnose':
    from scene_diagnostics import inspect_groups,focused_previews,opening_obstructions
    from scene_framing import options
    write('diagnostics.json',dict(groups=inspect_groups(request['scene'],request.get('focus_ids')),openings=opening_obstructions(request['scene'],request.get('focus_ids',[])),framing=options(request['scene']),images=focused_previews(request['scene'],request.get('focus_ids',[]),output,Path(request['stop_file']) if request.get('stop_file') else None)))
    sys.exit(0)

if request.get('functional_repair'):
    from scene_functional_repair import apply as repair_function,export_preview
    write('functional-repair.json',repair_function(request))
    write('repaired-scene.json',request['repaired_scene'])
    export_preview(request['preview'])

if request['mode'] == 'prepare':
    namespace = UUID(request['source_sha256'][:32])
    objects=[]
    bpy.context.view_layer.update()
    for obj in bpy.data.objects:
        if obj.type in ('MESH', 'CURVE'):
            obj['studio_id']=obj.get('studio_id') or uuid5(namespace,obj.name).hex
            objects.append(dict(id=obj['studio_id'],name=obj.name,room_id=obj.get('room_id'),
                center=list(obj.matrix_world.translation),materials=[m.name if m else None for m in obj.data.materials],intake_metadata=json.loads(obj.get('intake_metadata','{}'))))
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
    # Compare transformed mesh bounds in metres after the glTF Y-up / Blender
    # Z-up conversion. ID matching alone cannot detect mismatched model pairs.
    nodes=gltf.get('nodes',[])
    parents={}
    for i,n in enumerate(nodes):
        for child in n.get('children',[]):
            if child in parents or not 0<=child<len(nodes):raise ValueError('GLB hierarchy is not a tree')
            parents[child]=i
    cache={}
    def world(index,visited=None):
        if index in cache:return cache[index]
        visited=set() if visited is None else visited
        if index in visited:raise ValueError('GLB hierarchy cycle')
        visited.add(index);node=nodes[index]
        if 'matrix' in node:
            m=node['matrix'];local=Matrix([m[i::4] for i in range(4)])
        else:
            q=node.get('rotation',[0,0,0,1]);s=node.get('scale',[1,1,1])
            local=Matrix.LocRotScale(Vector(node.get('translation',[0,0,0])),Quaternion((q[3],q[0],q[1],q[2])),Vector(s))
        cache[index]=world(parents[index],visited)@local if index in parents else local
        return cache[index]
    convert=Matrix(((1,0,0,0),(0,0,-1,0),(0,1,0,0),(0,0,0,1)))
    native_by_id={o.get('studio_id'):o for o in bpy.data.objects if o.type in ('MESH','CURVE')}
    checked=0
    for index,node in enumerate(nodes):
        if 'mesh' not in node:continue
        corners=[]
        for primitive in gltf['meshes'][node['mesh']]['primitives']:
            accessor=gltf['accessors'][primitive['attributes']['POSITION']]
            if 'min' not in accessor or 'max' not in accessor:raise ValueError('GLB positions lack bounds')
            for x in (accessor['min'][0],accessor['max'][0]):
                for y in (accessor['min'][1],accessor['max'][1]):
                    for z in (accessor['min'][2],accessor['max'][2]):corners.append(convert@world(index)@Vector((x,y,z)))
        obj=native_by_id[node['extras']['studio_id']]
        native_corners=[obj.matrix_world@Vector(c) for c in obj.bound_box]
        if any(not math.isfinite(v) for c in corners+native_corners for v in c):
            raise ValueError('模型包含非有限幾何座標：'+obj.name)
        for axis in range(3):
            lower=min(c[axis] for c in native_corners);upper=max(c[axis] for c in native_corners)
            tolerance=max(.02,(upper-lower)*.02)
            if abs(min(c[axis] for c in corners)-lower)>tolerance or abs(max(c[axis] for c in corners)-upper)>tolerance:
                raise ValueError('GLB／BLEND 尺度或位置不一致：'+obj.name)
        checked+=1
    payload=json.dumps(gltf,separators=(',',':'),ensure_ascii=False).encode()
    payload+=b' '*((-len(payload))%4)
    rest=raw[20+size:]
    (output/'model.glb').write_bytes(struct.pack('<III',magic,version,20+len(payload)+len(rest))+struct.pack('<II',len(payload),kind)+payload+rest)
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'model.blend'),compress=True)
    write('model.json',dict(id=request['model_id'],source_sha256=request['source_sha256'],
        objects=objects,selectable_ids=sorted(mapped),geometry_sha256=geometry_digest(),coordinate_system='Blender Z-up metres',
        spatial_check=dict(passed=True,checked_meshes=checked,tolerance='max(0.02 m, 2% axis extent)'),render_readiness=inspect_scene(scene)))
elif request['mode']=='lighting':
    from studio_lighting import propose
    setup,notes=propose(request['scene'],request.get('lighting_source'))
    setup['source_job_id']=request['job_id']
    write('result.json',dict(lighting_setup=setup,notes=notes,revision=request['revision'],model_id=request['model_id'],lighting_source=request.get('lighting_source')))
else:
    design=request['scene']
    before=geometry_digest()
    from concept_geometry import add_blender_furniture
    add_blender_furniture(design.get('concept_furniture',[]))
    by_id={o.get('studio_id'):o for o in bpy.data.objects if o.type in ('MESH','CURVE')}
    if request.get('original_scene'):
        from scene_review_checks import validate_moves
        write('scene-geometry-check.json',validate_moves(design,request['original_scene'],by_id))
    # Apply revision edits in world space; never edit the immutable prepared model.
    edited=[]
    matrices={key:o.matrix_world.copy() for key,o in by_id.items()}
    for group in design.get('groups',[]):
        delta=Vector(group.get('translation',[0,0,0]))
        pivot=Vector(group.get('rotation_pivot',[0,0,0]))
        angle=math.radians(group.get('rotation',0))
        change=Matrix.Translation(delta+pivot)@Matrix.Rotation(angle,4,'Z')@Matrix.Translation(-pivot)
        for identifier in group['children']:
            obj=by_id[identifier]
            obj.matrix_world=change@matrices[identifier]
            if group.get('deleted'):
                obj.hide_render=True;obj.hide_set(True)
        if delta.length or angle or group.get('deleted'):edited.append(group['id'])
    bpy.context.view_layer.update()
    after_edits=geometry_digest()
    applied=[]
    for assignment in design['objects']:
        spec=assignment['material']
        if spec.get('render_roughness') is not None and not spec.get('color'):
            from scene_review_checks import override_roughness
            override_roughness(by_id[assignment['id']],spec['render_roughness'])
        if not spec.get('color'):
            continue
        obj=by_id[assignment['id']]
        material=bpy.data.materials.new('Studio '+assignment['id'])
        material.use_nodes=True
        shader=material.node_tree.nodes.get('Principled BSDF')
        srgb=[int(spec['color'][n:n+2],16)/255 for n in (1,3,5)]
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in srgb]
        shader.inputs['Base Color'].default_value=(*linear,1)
        shader.inputs['Roughness'].default_value=spec.get('render_roughness') if spec.get('render_roughness') is not None else spec.get('roughness',.5)
        # Detach shared mesh data before changing slots; only selected object changes.
        obj.data=obj.data.copy()
        obj.data.materials.clear()
        obj.data.materials.append(material)
        applied.append(assignment['id'])
    if geometry_digest()!=after_edits:
        raise ValueError('Material assignment changed geometry')
    from realism_finish import apply_finish, inventory
    for assignment in design['objects']:
        finish=assignment['material'].get('render_finish')
        if finish:apply_finish(by_id[assignment['id']],finish)
    from studio_lighting import apply
    apply(design,request.get('lighting_source'))
    finish_geometry_preserved=geometry_digest()==after_edits
    if not finish_geometry_preserved:raise ValueError('材質精修不應改變原生幾何')
    from realism_shelf import apply_shelves
    write('shelf-refinements.json',apply_shelves(design,by_id,request.get('realism_assets')))
    from opening_details import add_openings
    write('opening-details.json',add_openings(design,by_id,request.get('opening_source')))
    if request.get('completion_evidence'):
        from completion_fronts import export as export_front_evidence
        write('completion-fronts.json',export_front_evidence(design,by_id,output))
        sys.exit(0)
    from completion_details import prepare as complete_model
    completion_report=complete_model(design,by_id)
    from installation_replacement import apply as apply_installations
    write('installation-results.json',apply_installations(design,by_id,request.get('installation_assets'),completion_report))
    write('completion-details.json',completion_report)
    if request.get('realism_inventory'):
        bpy.context.scene['studio_search_stop_file']=request.get('stop_file','')
        include_cameras=not request.get('prepare_only') and request.get('realism_camera_search',True)
        if request.get('realism_all'):
            from realism_scope import combine_inventories
            facts=combine_inventories([inventory(design,p['id'],by_id,include_cameras) for p in design['viewpoints'] if p['shots'] or request.get('prepare_only')])
        else:facts=inventory(design,request['realism_inventory'],by_id,include_cameras)
        facts['completion_results']=completion_report
        write('realism-inventory.json',facts)
        if request.get('inventory_only'):sys.exit(0)
    from realism_ceiling import add_ceilings
    ceiling_report=add_ceilings(design,by_id)
    write("ceiling-infill.json",dict(patches=ceiling_report,original_geometry_preserved=finish_geometry_preserved))
    if request.get('prepare_only'):
        from realism_preview import export_snapshot
        write('preview-package.json',export_snapshot(design,output))
        write('result.json',dict(images=[],quality_check='geometry_only',revision=request['revision'],model_id=design['model_id']))
        sys.exit(0)
    exterior_objects=[]
    if design.get('illustrative_exteriors'):
        from realism_details import detail_options,add_exteriors
        windows={}
        for point in design['viewpoints']:
            for window in detail_options(design,point,by_id,set())['windows']:windows[window['id']]=window
        exterior_objects=add_exteriors(design,dict(windows=list(windows.values())))
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
    scene.cycles.adaptive_threshold=.02 if request.get('realism_trial') else (.04 if request['quality']=='preview' else .02)
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
    measurements=[]
    if request.get('scene_trial'):
        for group in design['groups']:
            if group['deleted']:continue
            installed=[o for o in scene.objects if o.get('studio_installation_candidate') and o.get('studio_refined_from') in group['children'] and not o.hide_render]
            measured=installed or [by_id[k] for k in group['children'] if k in by_id]
            pts=[o.matrix_world@Vector(c) for o in measured for c in o.bound_box]
            if pts:
                box=[[fn(p[i] for p in pts) for i in range(3)] for fn in (min,max)]
                measurements.append(dict(id=group['id'],name=group['name'],bounds=box,dimensions=[box[1][i]-box[0][i] for i in range(3)]))
    rendered_cameras=[]
    points=[p for p in design['viewpoints'] if request.get('realism_all') or not request.get('realism_point_id') or p['id']==request['realism_point_id']]
    total=sum(1+len(p['shots']) for p in points)
    checks=[]
    for probing in ((False,) if request.get('scene_trial') else (True,) if request.get('probe_only') else (True,False)):
        scene.cycles.samples=8 if probing else (64 if request.get('realism_trial') else 16 if request['quality']=='preview' else 96)
        for point in points:
            specs=[dict(id='panorama',name='360°',kind='panorama',yaw=0,pitch=0,lens=24)]+[dict(s,kind='still') for s in point['shots']]
            for shot in specs:
                if request.get('stop_file') and Path(request['stop_file']).exists():
                    raise ValueError('已完成目前圖片，停止後續照明與出圖')
                name=('probe-' if probing else '')+point['id']+'-'+shot['id']+'.png'
                camera=bpy.data.cameras.new('Studio camera')
                obj=bpy.data.objects.new('Studio camera',camera)
                scene.collection.objects.link(obj)
                obj.location=shot.get('eye') or point['eye']
                scene.camera=obj
                if shot['kind']=='panorama':
                    camera.type='PANO'
                    camera.panorama_type='EQUIRECTANGULAR'
                    obj.rotation_euler=(math.pi/2,0,-math.pi/2)
                    width=2048 if request.get('realism_trial') else 1024 if request['quality']=='preview' else 4096
                    height=width//2
                else:
                    camera.type='PERSP'
                    camera.lens=shot['lens']
                    camera.shift_y=shot.get('shift_y',0)
                    yaw,pitch=math.radians(shot['yaw']),math.radians(shot['pitch'])
                    direction=Vector((math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),math.sin(pitch)))
                    obj.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
                    width,height=(1024,768) if request.get('realism_trial') else (640,480) if request['quality']=='preview' else (1600,1200)
                    if shot.get('aspect')=='16:9':height=round(width*9/16)
                if probing:
                    width,height=(192,96) if shot['kind']=='panorama' else (128,96)
                    if shot['kind']!='panorama' and shot.get('aspect')=='16:9':height=72
                scene.render.resolution_x=width
                scene.render.resolution_y=height
                if not probing:
                    rendered_cameras.append(dict(file=name,location=list(obj.location),rotation=list(obj.rotation_euler),kind=shot['kind'],lens=camera.lens,shift_y=camera.shift_y,sensor_width=camera.sensor_width,aspect=shot.get('aspect','4:3'),width=width,height=height))
                scene.render.filepath=str(output/name)
                write('progress.json',dict(completed=len(checks) if probing else len(images),total=total,current=('試渲染檢查 · ' if probing else '正式出圖 · ')+point['name']+' '+shot['name']))
                bpy.ops.render.render(write_still=True)
                image=bpy.data.images.load(str(output/name),check_existing=False)
                assessment=inspect_image(image)
                if probing or assessment['status']=='blocked':
                    checks.append(dict(assessment,phase='probe' if probing else 'output',file=name,viewpoint_id=point['id'],shot_id=shot['id']))
                    write('quality-checks.json',dict(revision=request['revision'],status='blocked' if assessment['status']=='blocked' else 'checking',checks=checks))
                if assessment['status']=='blocked' and not request.get('scene_trial'):
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
    check_status='blocked' if any(c['status']=='blocked' for c in checks) else 'passed'
    write('quality-checks.json',dict(revision=request['revision'],status=check_status,checks=checks,visual_review='pending',quality_check=check_status))
    if request.get('probe_only'):
        write('result.json',dict(revision=request['revision'],quality_check='passed',probe_only=True))
        sys.exit(0)
    if not request.get('scene_trial'):
        bpy.ops.wm.save_as_mainfile(filepath=str(output/'rendered-model.blend'),compress=True)
    if request.get('realism_trial'):
        from realism_preview import export_snapshot
        write('preview-package.json',export_snapshot(design,output))
    write('progress.json',dict(completed=total,total=total,current='完成'))
    write('result.json',dict(images=images,revision=request['revision'],model_id=request['model_id'],
        applied_object_ids=applied,geometry_preserved=geometry_digest()==before,device=scene.cycles.device,
        edited_group_ids=edited,added_concept_ids=[f['id'] for f in design.get('concept_furniture',[])],material_geometry_preserved=finish_geometry_preserved,
        visual_review='pending',quality_check=check_status,measurements=measurements,illustrative_exterior_objects=exterior_objects,rendered_cameras=rendered_cameras))
