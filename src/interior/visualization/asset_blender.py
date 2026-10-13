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
    material_ids=request.get('target_objects')
    if asset['kind']=='material':
        if material_ids is None:material_ids=[request['target_object']] if request.get('target_object') else list(target_ids)
        if not material_ids or len(set(material_ids))!=len(material_ids) or not set(material_ids)<=target_ids:
            raise ValueError('材質目標不屬於此單物件')
    changed_ids=set(material_ids) if asset['kind']=='material' else target_ids
    untouched={identifier:signature(o) for identifier,o in by_id.items() if identifier not in changed_ids}
    reference={k:asset[k] for k in ('asset_id','version_id','name','url','license','is_free','kind') if k in asset}
    reference.update(task_id=request['task_id'],status='applied')
    prior_images=set(bpy.data.images)
    preview_overrides=[]
    if asset['kind']=='restore':
        from asset_restore import restore_group
        report=restore_group(asset,design,group,targets)
    elif asset['kind']=='preview':
        from surface_uv import ensure_uv, preview_tile
        uv_report={};tiles=[];cache={}
        for obj in targets:
            obj.data=obj.data.copy();uv_report[obj['studio_id']]=ensure_uv(obj)
            for slot,original_material in enumerate(list(obj.data.materials)):
                if not original_material:continue
                key=original_material.name
                if key not in cache:
                    material=original_material.copy()
                    folder=output/('preview-'+str(len(cache)));folder.mkdir(exist_ok=True)
                    preview,tile=preview_tile(material,folder)
                    if preview!=material:material['studio_preview_material']=preview.name
                    cache[key]=material;tiles.append(dict(material=material.name,**tile))
                obj.data.materials[slot]=cache[key]
        material_ids=list(target_ids)
        report=dict(preview_only=True,uv=uv_report,materials=tiles,native_shader_preserved=True)
    elif asset['kind'] in ('model','generated'):
        target_lo,target_hi=bounds(targets)
        if asset['kind']=='generated':
            from parametric_assets import build
            meshes=build(asset['recipe'],target_lo,target_hi)
        else:
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
        requested_angle=angle
        if request.get('auto_fit') and requested_angle:
            user_rotation=Matrix.Rotation(math.radians(requested_angle),4,'Z')
            for obj in meshes:obj.matrix_world=user_rotation@obj.matrix_world
            angle=0
        fitted_scale=None;dimension_plan=None
        from asset_dimensions import ADAPTABLE, adaptation, apply as apply_dimensions
        policy=request.get('asset_requirements') or {}
        adaptable=asset['kind']=='model' and request.get('dimension_fit')=='adapt' and policy.get('purpose') in ADAPTABLE and policy.get('dimension_source')=='confirmed'
        if request.get('auto_fit'):
            from asset_fit import choose_fit, DECOR_ASSETS
            raw_lo,raw_hi=bounds(meshes)
            if adaptable:
                dimension_plan=adaptation(list(target_hi-target_lo),list(raw_hi-raw_lo),policy,allow_rotate=not requested_angle)
                angle=dimension_plan['rotation'];fitted_scale=dimension_plan['uniform_scale']
            else:
                angle,fitted_scale,_=choose_fit(list(target_hi-target_lo),list(raw_hi-raw_lo),envelope=bool(concepts and concepts[0]['asset'] in DECOR_ASSETS),policy=policy,allow_rotate=asset['kind']!='generated' and not requested_angle)
        rotation=Matrix.Rotation(math.radians(angle),4,'Z')
        for obj in meshes:obj.matrix_world=rotation@obj.matrix_world
        lo,hi=bounds(meshes);extent=hi-lo;target_size=target_hi-target_lo
        if not request.get('auto_fit') and request.get('asset_requirements'):
            from asset_fit import choose_fit
            if adaptable:
                dimension_plan=adaptation(list(target_size),list(extent),policy,allow_rotate=False)
                fitted_scale=dimension_plan['uniform_scale']
            else:
                _,fitted_scale,_=choose_fit(list(target_size),list(extent),policy=policy,allow_rotate=False)
        factor=fitted_scale if fitted_scale is not None else min(target_size[i]/extent[i] for i in range(3))
        repair_scale=request.get('repair_scale',1)
        if not math.isfinite(repair_scale) or not .8<=repair_scale<=1:raise ValueError('模型修正比例超出允許範圍')
        if repair_scale!=1:
            if policy.get('dimension_source') not in ('unknown','estimated') or dimension_plan:raise ValueError('不可縮小已確認尺寸或改造後的尺寸')
            factor*=repair_scale
            from asset_fit import HEIGHTS
            actual_height=extent.z*factor
            limits=HEIGHTS.get(policy.get('purpose'))
            if limits and not limits[0]<=actual_height<=limits[1]:raise ValueError('修正後高度不符合用途尺寸檢查')
            if min(extent.x*factor,extent.y*factor)<.08:raise ValueError('修正後家具尺寸過小')
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
        if dimension_plan:
            fitted_lo,fitted_hi=bounds(meshes)
            apply_dimensions(meshes,fitted_lo,fitted_hi,dimension_plan)
            adjusted_lo,adjusted_hi=bounds(meshes)
            if any(abs(actual-wanted)>max(.002,.02*wanted) for actual,wanted in zip(adjusted_hi-adjusted_lo,dimension_plan['target_dimensions'])):raise ValueError('尺寸改造後量測未符合目標，保留原件')
        placement={}
        if request.get('auto_fit') or dimension_plan:
            from asset_collision import check_placement
            try:placement=check_placement(design,group,meshes)
            except ValueError as exc:
                (output/'replacement-check.json').write_text(json.dumps(dict(error=str(exc),collisions=getattr(exc,'details',[])),ensure_ascii=False),encoding='utf-8')
                if asset['kind']=='generated':
                    (output/'generation-check.json').write_text(json.dumps(dict(error=str(exc),collisions=getattr(exc,'details',[])),ensure_ascii=False),encoding='utf-8')
                raise
        # Detach children outside this assembly before unlinking its meshes.
        for obj in targets:
            for child in list(obj.children):
                if child not in targets:
                    world=child.matrix_world.copy();child.parent=None;child.matrix_world=world
            bpy.data.objects.remove(obj,do_unlink=True)
        design['objects']=[o for o in design['objects'] if o['id'] not in target_ids]+new
        group.update(children=[o['id'] for o in new],method='parametric' if asset['kind']=='generated' else 'blenderkit',asset_reference=None if asset['kind']=='generated' else reference,generated_reference=dict(task_id=request['task_id'],model_id=request['model_id'],purpose=asset['recipe']['purpose'],version=asset['recipe'].get('version',1),source=asset['recipe'].get('source','bounded_parametric_template'),agent_task_id=asset['recipe'].get('agent_task_id'),quality='concept') if asset['kind']=='generated' else None)
        if request.get('asset_requirements'):
            group['asset_requirements']={k:v for k,v in request['asset_requirements'].items() if k in ('purpose','dimension_source','dimensions','evidence')}
            group['asset_requirements']['purpose']=group['asset_requirements'].get('purpose') or ''
        from asset_fit import fit_report
        report=dict(fit_policy=fit_report(list(target_size),list(bounds(meshes)[1]-bounds(meshes)[0]),policy),placement=placement,original_dimensions=list(target_size),asset_dimensions=list(extent),uniform_scale=factor,
            resulting_dimensions=list(bounds(meshes)[1]-bounds(meshes)[0]),dimension_adjustment=dimension_plan,repair_scale=repair_scale,rotation=angle+(requested_angle if request.get('auto_fit') else 0),auto_fit=request.get('auto_fit',False),generated=asset['kind']=='generated',direction_status='needs_review',direction_note='方向待確認；外框適配不代表候選使用側已辨識')
    else:
        with bpy.data.libraries.load(asset['path'],link=False) as (src,dst):dst.materials=src.materials
        materials=[m for m in dst.materials if m]
        # A material asset should contain one intended material. Do not pick arbitrarily.
        if len(materials)!=1:raise ValueError('素材包含多個材質，無法安全判定要套用哪一個；請選其他候選')
        for identifier in material_ids:
            obj=by_id[identifier];obj.data=obj.data.copy();obj.data.materials.clear();obj.data.materials.append(materials[0])
            assignment=next(o for o in design['objects'] if o['id']==identifier)
            assignment['material'].update(color=None,url=asset['url'],asset_reference=reference,candidate_id=None)
        from surface_uv import ensure_uv, preview_tile
        uv_report={identifier:ensure_uv(by_id[identifier]) for identifier in material_ids}
        tile_report={}
        if materials[0].use_nodes:
            preview_material,tile_report=preview_tile(materials[0],output)
            if preview_material!=materials[0]:materials[0]['studio_preview_material']=preview_material.name
            preview_overrides=[(by_id[i],list(by_id[i].data.materials),preview_material) for i in material_ids]
        group.setdefault('asset_reference',None)
        report=dict(object_id=request.get('target_object'),object_ids=material_ids,material=materials[0].name,uv=uv_report,preview=tile_report)
    for image in set(bpy.data.images)-prior_images:
        if image.source in ('FILE','TILED') and not image.packed_file and not image.has_data:
            raise ValueError('素材缺少外部貼圖，未套用；請選擇含完整貼圖的素材')
        if image.has_data and not image.packed_file:
            try:image.pack()
            except RuntimeError:raise ValueError('素材貼圖無法封裝，未套用')
    for identifier,signature_before in untouched.items():
        if signature(by_id[identifier])!=signature_before:raise ValueError('替換影響其他物件，已拒絕採用')
    # Preserve baked previews in every later model export, while native Cycles
    # keeps the original material. Reuse the tile instead of rebaking other groups.
    preview_overrides=[]
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH':continue
        original=list(obj.data.materials)
        previews=[bpy.data.materials.get(m.get('studio_preview_material','')) if m else None for m in original]
        if any(previews):preview_overrides.append((obj,original,[preview or mat for preview,mat in zip(previews,original)]))
    # A self-contained current snapshot must not accumulate discarded meshes/textures.
    for collection in (bpy.data.materials,bpy.data.meshes,bpy.data.images):
        for block in collection:
            if block.use_fake_user and block.users==1:block.use_fake_user=False
    # Preview material is deliberately unassigned until export.
    for _,_,materials in preview_overrides:
        for m in materials:
            if m:m.use_fake_user=True
    bpy.data.orphans_purge(do_recursive=True)
    design['model_id']=request['model_id']
    # Lighting remains tied to the same assembly IDs. Clear obsolete proposal IDs
    # only when their native lighting source is unnecessary; preserve report below.
    setup=design.get('lighting_setup',{})
    if setup.get('source_job_id'):
        request['retained_lighting_job']=setup['source_job_id']
    bpy.context.view_layer.update()
    for obj,original,materials in preview_overrides:
        obj.data.materials.clear()
        for m in materials:obj.data.materials.append(m)
    try:
        bpy.ops.export_scene.gltf(filepath=request['preview'],export_format='GLB',export_extras=True,
            export_apply=True,export_cameras=False,export_lights=True)
    finally:
        for obj,original,_ in preview_overrides:
            obj.data.materials.clear()
            for material in original:obj.data.materials.append(material)
    # Validate the actual exported texture/coordinate contract before adoption.
    if asset['kind'] in ('material','preview'):
        import struct
        raw=Path(request['preview']).read_bytes();length=struct.unpack_from('<I',raw,12)[0]
        gltf=json.loads(raw[20:20+length])
        def coordinates(value):
            result=[]
            if isinstance(value,dict):
                for key,item in value.items():
                    if key.endswith('Texture') and isinstance(item,dict) and 'index' in item:
                        result.append(item.get('extensions',{}).get('KHR_texture_transform',{}).get('texCoord',item.get('texCoord',0)))
                    else:result.extend(coordinates(item))
            elif isinstance(value,list):
                for item in value:result.extend(coordinates(item))
            return result
        checked=0
        for node in gltf.get('nodes',[]):
            if node.get('extras',{}).get('studio_id') not in material_ids or 'mesh' not in node:continue
            for primitive in gltf['meshes'][node['mesh']]['primitives']:
                mat=gltf['materials'][primitive['material']]
                if any('TEXCOORD_'+str(i) not in primitive['attributes'] for i in coordinates(mat)):
                    raise ValueError('GLB 貼圖缺少需要的 UV；保留原件並改試候選')
                checked+=1
        if not checked:raise ValueError('GLB 無法找到材質目標，拒絕採用')
        report['export_uv_checked_primitives']=checked
    (output/'replacement-scene.json').write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'replacement-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
