"""Bounded installation and missing-component repairs; no arbitrary Agent code."""
import copy
import math
from uuid import NAMESPACE_URL, uuid5
import bpy
from mathutils import Matrix,Vector
from decor_review import transform
from scene_diagnostics import inspect_groups,box
from scene_review_checks import penetration


def export_preview(path):
    """Keep previously baked editor textures while retaining native Cycles nodes."""
    backups=[]
    try:
        for obj in bpy.context.scene.objects:
            if obj.type!='MESH':continue
            original=list(obj.data.materials)
            previews=[bpy.data.materials.get(m.get('studio_preview_material','')) if m else None for m in original]
            if any(previews):
                backups.append((obj,original))
                for i,(preview,material) in enumerate(zip(previews,original)):obj.data.materials[i]=preview or material
        bpy.ops.export_scene.gltf(filepath=path,export_format='GLB',export_extras=True,export_apply=True,export_cameras=False,export_lights=True)
    finally:
        for obj,original in backups:
            for i,material in enumerate(original):obj.data.materials[i]=material


def apply(request):
    design=copy.deepcopy(request['scene']);proposal=request['functional_repair']
    group=next(g for g in design['groups'] if g['id']==proposal['target_id'] and not g['deleted'])
    if any(f['id']==group['id'] for f in design.get('concept_furniture',[])):raise ValueError('請先完成概念模型轉檔再修補構件')
    req=group.get('asset_requirements') or {};purpose=req.get('purpose') or (group.get('object_specification') or {}).get('purpose')
    if purpose not in ('table','desk','bunk_bed','sink','vanity'):raise ValueError('此用途尚無安全構件修補器')
    by_id={o.get('studio_id'):o for o in bpy.context.scene.objects if o.type in ('MESH','CURVE')}
    facts=inspect_groups(design,[group['id']])[0];lo,hi=facts['bounds'];matrix=transform(group)
    old={g['id']:{k:box(by_id[k],transform(g)) for k in g['children'] if k in by_id} for g in design['groups'] if not g['deleted']}
    created=[];moved=[];values=proposal['values'];dz=0;base=lo[2]
    def register(obj,material_id):
        if material_id not in group['children']:raise ValueError('修補材質必須來自原家具')
        obj.matrix_world=matrix.inverted()@obj.matrix_world
        obj['studio_id']=uuid5(NAMESPACE_URL,request['model_id']+':'+str(len(created))).hex
        for slot in by_id[material_id].material_slots:
            if slot.material:obj.data.materials.append(slot.material)
        if not obj.data.materials:raise ValueError('原家具沒有可沿用材質')
        created.append(obj);by_id[obj['studio_id']]=obj;group['children'].append(obj['studio_id'])
        design['objects'].append(dict(id=obj['studio_id'],name=obj.name,room_id=next(o['room_id'] for o in design['objects'] if o['id']==material_id),material={}))

    def panel(name,center,size,material_id):
        if any(not math.isfinite(v) for v in center+size) or any(v<.005 or v>4 for v in size):raise ValueError('修補構件尺寸無效')
        low=[center[i]-size[i]/2 for i in range(3)];high=[center[i]+size[i]/2 for i in range(3)]
        if any(low[i]<lo[i]-.002 or high[i]>hi[i]+.002 for i in (0,1)):raise ValueError('修補不得改變家具平面占地')
        if low[2]<base-.005 or high[2]>max(hi[2],base+1.05)+.005:raise ValueError('修補構件超出高度範圍')
        if material_id not in group['children']:raise ValueError('修補材質必須來自原家具')
        bpy.ops.mesh.primitive_cube_add(size=1,location=center);obj=bpy.context.object;obj.name='Repair '+name;obj.dimensions=size
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        register(obj,material_id)
        bevel=obj.modifiers.new('Repair edge','BEVEL');bevel.width=min(.003,min(size)/8);bevel.segments=2
    if proposal['action']=='install':
        if purpose not in ('sink','vanity'):raise ValueError('安裝高度修正只適用洗手櫃／水槽')
        if req.get('dimension_source') in ('confirmed','envelope'):raise ValueError('已確認外框不能自動增加底座，需確認安裝基準')
        surface=values['surface_z'];height=values['target_height']
        if not any(abs(s['position'][2]-surface)<.015 and s['normal'][2]>.8 for s in facts['top_surface_samples']):raise ValueError('工作面高度缺少實際表面證據')
        if not (.75<=height<=.95 if purpose=='vanity' else .8<=height<=1.0):raise ValueError('超出此用途的概念安裝高度範圍')
        if facts['floor_z'] is None:raise ValueError('缺少可確認的地板安裝基準')
        base=facts['floor_z'];dz=base+height-surface
        if not .03<=dz<=.6:raise ValueError('安裝高度修正超出 3～60 cm 範圍')
        ids=list(group['children'])
        dependents=[g for g in design['groups'] if (g.get('decor_context') or {}).get('support_group_id')==group['id']]
        if any(l.get('group_id')==group['id'] for l in design['lighting_setup']['lights']):raise ValueError('綁定燈具的家具不自動升高')
        snapshots={k:o.matrix_world.copy() for k,o in by_id.items()}
        for target in [group,*dependents]:
            inverse=transform(target).inverted();shift=inverse.to_3x3()@Vector((0,0,dz))
            for identifier in target['children']:
                if identifier not in by_id:raise ValueError('承載物包含未轉檔概念構件')
                obj=by_id[identifier];world=snapshots[identifier].copy();world.translation+=shift;obj.matrix_world=world;moved.append(identifier)
        w,d=hi[0]-lo[0],hi[1]-lo[1];th=min(.035,w*.08,d*.08);cx=(lo[0]+hi[0])/2;cy=(lo[1]+hi[1])/2
        material_id=ids[0]
        # Two side panels and a bottom plinth support the lifted unit; the basin stays open.
        # Basin pipes may reach the floor in the source asset. They are not the
        # underside of the supported bowl; supports must meet the rim instead.
        support_height=(height-.025) if purpose=='sink' else lo[2]+dz-base
        if support_height<.03:raise ValueError('安裝後無需底座或高度無效')
        for side in (-1,1):panel('installation side', [cx+side*(w/2-th/2),cy,base+support_height/2],[th,d,support_height],material_id)
        panel('installation plinth',[cx,cy,base+th/2],[w,d,th],material_id)
    elif proposal['action']=='component':
        if set(values)-{'panels','faucet'} or len(values.get('panels',[]))>6 or not (values.get('panels') or values.get('faucet')):raise ValueError('只允許必要構件與受控龍頭提案')
        for p in values.get('panels',[]):
            if set(p)!={'name','center','size','material_id'}:raise ValueError('修補構件欄位不符')
            panel(p['name'],p['center'],p['size'],p['material_id'])
        if values.get('faucet'):
            if purpose not in ('sink','vanity'):raise ValueError('龍頭提案只適用水槽與洗手台')
            f=values['faucet']
            if set(f)!={'base','spout','material_id'}:raise ValueError('龍頭提案欄位不符')
            a,b=Vector(f['base']),Vector(f['spout'])
            if len(a)!=3 or len(b)!=3 or any(not math.isfinite(v) for v in (*a,*b)):raise ValueError('龍頭位置無效')
            if not .06<=b.z-a.z<=.3 or not .06<=Vector((b.x-a.x,b.y-a.y)).length<=.35:raise ValueError('龍頭超出受控尺寸')
            if any(p[i]<lo[i]+.012 or p[i]>hi[i]-.012 for p in (a,b) for i in (0,1)):raise ValueError('龍頭不得超出原平面占地')
            if not any(abs(s['position'][2]-a.z)<.025 and s['normal'][2]>.8 for s in facts['top_surface_samples']):raise ValueError('龍頭底座缺少工作面高度依據')
            if req.get('dimension_source') in ('confirmed','envelope') and b.z+.055>hi[2]:raise ValueError('龍頭將改變已確認外框')
            curve=bpy.data.curves.new('Repair faucet','CURVE');curve.dimensions='3D';curve.bevel_depth=.01;curve.bevel_resolution=3
            spline=curve.splines.new('BEZIER');spline.bezier_points.add(3)
            for p,co in zip(spline.bezier_points,(a,Vector((a.x,a.y,b.z)),Vector((b.x,b.y,b.z+.03)),b)):
                p.co=co;p.handle_left_type='AUTO';p.handle_right_type='AUTO'
            obj=bpy.data.objects.new('Repair faucet concept',curve);bpy.context.collection.objects.link(obj)
            bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj;bpy.ops.object.convert(target='MESH')
            register(bpy.context.object,f['material_id'])
    else:raise ValueError('未知功能修正')
    bpy.context.view_layer.update();after=inspect_groups(design,[group['id']])[0]
    if any(after['bounds'][0][i]<facts['bounds'][0][i]-.003 or after['bounds'][1][i]>facts['bounds'][1][i]+.003 for i in (0,1)):raise ValueError('修補超出原家具平面占地')
    if req.get('dimension_source') in ('confirmed','envelope'):
        if any(abs(after['bounds'][side][i]-facts['bounds'][side][i])>.003 for side in (0,1) for i in range(3)):raise ValueError('修補改變已確認尺寸／外框')
    affected={group['id'],*[g['id'] for g in design['groups'] if (g.get('decor_context') or {}).get('support_group_id')==group['id']]}
    for target in design['groups']:
        if target['id'] not in affected:continue
        for identifier in target['children']:
            if identifier not in moved and identifier not in {o['studio_id'] for o in created}:continue
            a=box(by_id[identifier],transform(target))
            for other,objects in old.items():
                if other in affected:continue
                for k,b in objects.items():
                    previous=penetration(old[target['id']][identifier],b) if identifier in old[target['id']] else 0
                    if penetration(a,b)>previous+.008:raise ValueError('修補新增或加重其他家具／牆體碰撞')
    design['model_id']=request['model_id']
    design['design_notes'].append('自動修補預覽（非使用者確認尺寸）：'+proposal['reason'])
    request['repaired_scene']=design
    return dict(group_id=group['id'],purpose=purpose,action=proposal['action'],shift_z=dz,created_ids=[o['studio_id'] for o in created],moved_ids=moved,before=facts,after=after,source_preserved=True)
