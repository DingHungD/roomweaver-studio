"""Try native installation candidates in a disposable scene, retaining originals."""
import hashlib,math
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
from completion_geometry import bounds,Obstacles
from completion_details import wall_gap,selected_tree
from realism_ceiling import structural

def load(entry):
    path=Path(entry['file'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('安裝素材雜湊不符')
    with bpy.data.libraries.load(str(path),link=False) as (source,target):target.objects=list(source.objects)
    loaded=[o for o in target.objects if o];meshes=[]
    try:
        for o in loaded:
            if not o.users_collection:bpy.context.scene.collection.objects.link(o)
        bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
        for o in loaded:
            if o.type!='MESH' or o.hide_render:continue
            mesh=bpy.data.meshes.new_from_object(o.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps);mesh.transform(o.matrix_world)
            obj=bpy.data.objects.new('Installation '+o.name,mesh);bpy.context.scene.collection.objects.link(obj);meshes.append(obj)
        if not meshes:raise ValueError('素材沒有實際網格')
        from studio_render_checks import connected_nodes
        for obj in meshes:
            for mat in obj.data.materials:
                if mat and any(n.type in ('TEX_IMAGE','TEX_ENVIRONMENT') and (not n.image or n.image.source=='FILE' and not n.image.packed_file and not Path(bpy.path.abspath(n.image.filepath,library=n.image.library)).is_file()) for n in connected_nodes(mat)):raise ValueError('素材缺少貼圖：'+mat.name)
        return meshes
    except Exception:
        for obj in meshes:bpy.data.objects.remove(obj,do_unlink=True)
        raise
    finally:
        for obj in loaded:bpy.data.objects.remove(obj,do_unlink=True)

def apply(design,by_id,assets,completion):
    reports=[]
    walls=selected_tree(structural(design,by_id,'wall'));floors=selected_tree(structural(design,by_id,'floor'))
    for spec in design.get('installation_replacements',[]):
        group=next(g for g in design['groups'] if g['id']==spec['group_id']);original=[by_id[k] for k in group['children'] if k in by_id and not by_id[k].hide_render]
        if group.get('deleted') or not original:continue
        row=dict(group_id=group['id'],name=group['name'],status='unresolved',attempts=[])
        lo,hi=bounds(original);size=hi-lo;axes={}
        for axis in (0,1):
            for sign in (1,-1):
                d=Vector((0,0,0));d[axis]=sign;gap=wall_gap(original,walls,d)
                if gap and gap['distance']<=.25:axes[axis]=(sign,(hi[axis] if sign>0 else lo[axis])+sign*gap['distance']);break
        if len(axes)!=2:row['reason']='缺少兩個可信相鄰牆面，不能推定淋浴間安裝位置';reports.append(row);continue
        requirements=group.get('asset_requirements') or {};confirmed=requirements.get('dimension_source')=='confirmed';target=requirements.get('dimensions')
        for entry in (assets or {}).get(group['id'],[]):
            parts=[];attempt=dict(name=entry['name'],url=entry['url'],failures=[]);row['attempts'].append(attempt)
            try:
                parts=load(entry);obstacles=Obstacles(original+parts)
                for turn in range(4):
                    for obj in parts:obj.matrix_world=Matrix.Rotation(turn*math.pi/2,4,'Z')
                    bpy.context.view_layer.update();a,b=bounds(parts);actual=b-a
                    if confirmed and target and any(abs(actual[i]-target[i])>.005 for i in range(3)):
                        attempt['failures'].append('原件尺寸不符合已確認尺寸，不縮放覆寫');continue
                    # Unknown heights are not fixed targets. Keep the occupied floor envelope.
                    if any(actual[i]>size[i]+.005 for i in (0,1)):
                        attempt['failures'].append('占地超過原有安裝範圍');continue
                    offset=Vector((0,0,lo.z-a.z))
                    for axis,(sign,plane) in axes.items():offset[axis]=plane-sign*.003-(b[axis] if sign>0 else a[axis])
                    for obj in parts:obj.matrix_world=Matrix.Translation(offset)@obj.matrix_world
                    bpy.context.view_layer.update();a,b=bounds(parts)
                    collision=obstacles.collisions(parts)
                    if collision:attempt['failures'].append('安裝碰撞：'+ '、'.join(sorted(collision)[:5]));continue
                    supported=all(floors.ray(Vector((a.x+(b.x-a.x)*u,a.y+(b.y-a.y)*v,a.z+.1)),Vector((0,0,-1)),.3) for u,v in ((.1,.1),(.1,.9),(.9,.1),(.9,.9),(.5,.5)))
                    if not supported:attempt['failures'].append('底部缺少地板支承');continue
                    # Require actual vertical mounting edges near BOTH measured walls.
                    mounting=[]
                    for axis,(sign,plane) in axes.items():
                        vertices=[obj.matrix_world@v.co for obj in parts for v in obj.data.vertices]
                        near=[v for v in vertices if abs(v[axis]-plane)<.025]
                        span=max((v.z for v in near),default=0)-min((v.z for v in near),default=0)
                        mounting.append(span>=actual.z*.7)
                    if not all(mounting):attempt['failures'].append('缺少連續可貼牆安裝邊，外凸配件不能視為貼牆面');continue
                    for obj in original:obj.hide_render=True;obj.hide_set(True)
                    for obj in parts:obj['studio_refined_from']=original[0]['studio_id'];obj['studio_installation_candidate']=entry['asset_id']
                    attempt.update(status='selected',selected_rotation=turn*90,prior_orientation_failures=list(attempt['failures']));attempt['failures']=[]
                    row.update(status='prepared',checks=dict(two_wall_mounting_spans=True,floor_support=True,collision_free=True,confirmed_dimensions_preserved=True),center=list((a+b)/2),selected=entry,rotation=turn*90,dimensions=list(actual),wall_gap=.003,scale=1,quality='geometry_checked_visual_pending')
                    break
                if row['status']=='prepared':break
            except (ValueError,OSError) as exc:attempt['failures'].append(str(exc))
            for obj in parts:bpy.data.objects.remove(obj,do_unlink=True)
        if row['status']!='prepared':row['reason']='免費候選皆未通過安裝檢查，保留原件；詳見逐項失敗原因'
        else:
            old=next((r for r in completion.get('items',[]) if r.get('id')==group['id']),None)
            if old:
                old_reason=old.get('reason','');completion['remaining']=[s for s in completion['remaining'] if s!=old['name']+'：'+old_reason]
                old['previous_installation_changes']=old['changes'];old['changes']=[]
                old.update(status='corrected',reason='已改試免費模型並通過安裝幾何檢查，待 Agent 看圖確認');old['changes'].append(dict(action='installation_replacement',source_url=row['selected']['url']))
        reports.append(row)
    return dict(items=reports)
