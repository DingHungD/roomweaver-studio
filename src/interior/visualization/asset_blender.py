"""Replace one assembly or material in a new native snapshot, never the source."""
import copy
import hashlib
import json
import math
from pathlib import Path
from uuid import UUID, uuid5
import bpy
from mathutils import Vector, Matrix

def bounds(objects):
    bpy.context.view_layer.update()
    corners=[o.matrix_world@Vector(c) for o in objects for c in o.bound_box]
    if not corners:raise ValueError('素材沒有可用幾何')
    lo=Vector([min(p[i] for p in corners) for i in range(3)])
    hi=Vector([max(p[i] for p in corners) for i in range(3)])
    if any(not math.isfinite(v) for v in (*lo,*hi)) or min(hi-lo)<=.00001:raise ValueError('素材尺寸無效')
    return lo,hi

def signature(obj):
    # Native data, transform and material slots of non-targets must survive unchanged.
    return (tuple(v for row in obj.matrix_world for v in row), obj.data.as_pointer(),
        tuple(m.as_pointer() if m else 0 for m in obj.data.materials))

def replace_asset(request):
    design=copy.deepcopy(request['design']);asset=request['asset'];gid=request['target_group']
    group=next(g for g in design['groups'] if g['id']==gid and not g['deleted'])
    target_ids=set(group['children']);output=Path(request['output'])
    concepts=[f for f in design.get('concept_furniture',[]) if f['id']==gid]
    if concepts:
        from concept_geometry import add_blender_furniture
        add_blender_furniture(concepts)
        design['concept_furniture']=[f for f in design['concept_furniture'] if f['id']!=gid]
        group['method']='source_id'
    by_id={o.get('studio_id'):o for o in bpy.context.scene.objects if o.type in ('MESH','CURVE')}
    targets=[by_id[x] for x in group['children']]
    untouched={identifier:signature(o) for identifier,o in by_id.items() if identifier not in target_ids}
    reference={k:asset[k] for k in ('asset_id','version_id','name','url','license','is_free','kind')}
    reference.update(task_id=request['task_id'],status='applied')
    prior_images=set(bpy.data.images)
    if asset['kind']=='model':
        target_lo,target_hi=bounds(targets)
        with bpy.data.libraries.load(asset['path'],link=False) as (src,dst):dst.objects=src.objects
        loaded=[o for o in dst.objects if o]
        for obj in loaded:
            if obj.name not in bpy.context.scene.collection.objects:bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        meshes=[];deps=bpy.context.evaluated_depsgraph_get()
        # Freeze only asset geometry; exclude asset cameras, lights and scripts.
        for obj in loaded:
            if obj.type not in ('MESH','CURVE'):continue
            evaluated=obj.evaluated_get(deps)
            mesh=bpy.data.meshes.new_from_object(evaluated,preserve_all_data_layers=True,depsgraph=deps)
            if not mesh.vertices:continue
            node=bpy.data.objects.new('Asset '+obj.name,mesh);bpy.context.scene.collection.objects.link(node)
            node.matrix_world=obj.matrix_world.copy();meshes.append(node)
        for obj in loaded:bpy.data.objects.remove(obj,do_unlink=True)
        if not meshes or len(meshes)>500:raise ValueError('素材不是可替換的單物件或組成超過 500 件')
        angle=request.get('asset_rotation',0)
        if request.get('auto_fit'):
            from asset_fit import choose_fit, DECOR_ASSETS
            raw_lo,raw_hi=bounds(meshes)
            angle,_,_=choose_fit(list(target_hi-target_lo),list(raw_hi-raw_lo),envelope=bool(concepts and concepts[0]['asset'] in DECOR_ASSETS))
        rotation=Matrix.Rotation(math.radians(angle),4,'Z')
        for obj in meshes:obj.matrix_world=rotation@obj.matrix_world
        lo,hi=bounds(meshes);extent=hi-lo;target_size=target_hi-target_lo
        factor=min(target_size[i]/extent[i] for i in range(3))
        center=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z))
        anchor=Vector(((target_lo.x+target_hi.x)/2,(target_lo.y+target_hi.y)/2,target_lo.z))
        if concepts and concepts[0]['asset']=='ceiling_light':
            # Mount the top to the ceiling; a thinner shade must not float below it.
            anchor.z=target_hi.z-extent.z*factor
            for light in design.get('lighting_setup',{}).get('lights',[]):
                if light.get('group_id')==gid:light['position'][2]=anchor.z-.03
        transform=Matrix.Translation(anchor)@Matrix.Scale(factor,4)@Matrix.Translation(-center)
        room=next(o for o in design['objects'] if o['id'] in target_ids)['room_id']
        new=[]
        for i,obj in enumerate(meshes):
            obj.matrix_world=transform@obj.matrix_world
            identifier=uuid5(UUID(request['model_id']),f'asset-{i}').hex
            obj['studio_id']=identifier;obj['source_id']=gid
            new.append(dict(id=identifier,name=obj.name,room_id=room,material={}))
        # Detach children outside this assembly before unlinking its meshes.
        for obj in targets:
            for child in list(obj.children):
                if child not in targets:
                    world=child.matrix_world.copy();child.parent=None;child.matrix_world=world
            bpy.data.objects.remove(obj,do_unlink=True)
        design['objects']=[o for o in design['objects'] if o['id'] not in target_ids]+new
        group.update(children=[o['id'] for o in new],method='blenderkit',asset_reference=reference)
        report=dict(original_dimensions=list(target_size),asset_dimensions=list(extent),uniform_scale=factor,
            resulting_dimensions=list(extent*factor),rotation=angle,auto_fit=request.get('auto_fit',False))
    else:
        identifier=request['target_object']
        if identifier not in target_ids:raise ValueError('材質目標不屬於此單物件')
        with bpy.data.libraries.load(asset['path'],link=False) as (src,dst):dst.materials=src.materials
        materials=[m for m in dst.materials if m]
        # A material asset should contain one intended material. Do not pick arbitrarily.
        if len(materials)!=1:raise ValueError('素材包含多個材質，無法安全判定要套用哪一個；請選其他候選')
        obj=by_id[identifier];obj.data=obj.data.copy();obj.data.materials.clear();obj.data.materials.append(materials[0])
        assignment=next(o for o in design['objects'] if o['id']==identifier)
        assignment['material'].update(color=None,url=asset['url'],asset_reference=reference,candidate_id=None)
        group.setdefault('asset_reference',None)
        report=dict(object_id=identifier,material=materials[0].name)
    for image in set(bpy.data.images)-prior_images:
        if image.source in ('FILE','TILED') and not image.packed_file and not image.has_data:
            raise ValueError('素材缺少外部貼圖，未套用；請選擇含完整貼圖的素材')
        if image.has_data and not image.packed_file:
            try:image.pack()
            except RuntimeError:raise ValueError('素材貼圖無法封裝，未套用')
    for identifier,signature_before in untouched.items():
        if signature(by_id[identifier])!=signature_before:raise ValueError('替換影響其他物件，已拒絕採用')
    # A self-contained current snapshot must not accumulate discarded meshes/textures.
    for collection in (bpy.data.materials,bpy.data.meshes,bpy.data.images):
        for block in collection:
            if block.use_fake_user and block.users==1:block.use_fake_user=False
    bpy.data.orphans_purge(do_recursive=True)
    design['model_id']=request['model_id']
    # Lighting remains tied to the same assembly IDs. Clear obsolete proposal IDs
    # only when their native lighting source is unnecessary; preserve report below.
    setup=design.get('lighting_setup',{})
    if setup.get('source_job_id'):
        request['retained_lighting_job']=setup['source_job_id']
    bpy.context.view_layer.update()
    bpy.ops.export_scene.gltf(filepath=request['preview'],export_format='GLB',export_extras=True,
        export_apply=True,export_cameras=False,export_lights=True)
    (output/'replacement-scene.json').write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'replacement-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
