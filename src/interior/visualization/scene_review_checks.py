"""Actual native bounds gate for constrained edits; no source is saved in place."""
import math
from mathutils import Matrix, Vector


def bounds(group,by_id):
    pivot=Vector(group['rotation_pivot']);move=Matrix.Translation(Vector(group['translation'])+pivot)@Matrix.Rotation(math.radians(group['rotation']),4,'Z')@Matrix.Translation(-pivot)
    points=[move@by_id[key].matrix_world@Vector(c) for key in group['children'] if key in by_id for c in by_id[key].bound_box]
    if not points:raise ValueError('缺少原生網格：'+group['name'])
    return [[fn(p[i] for p in points) for i in range(3)] for fn in (min,max)]


def overlap(a,b):
    return all(min(a[1][i],b[1][i])-max(a[0][i],b[0][i])>.008 for i in range(3))


def parts(group,by_id):
    return {key:bounds(dict(group,children=[key]),by_id) for key in group['children'] if key in by_id}


def penetration(a,b):
    return max(0,min(min(a[1][i],b[1][i])-max(a[0][i],b[0][i]) for i in range(3)))


def validate_moves(design,original,by_id):
    before={g['id']:g for g in original['groups']};old={k:bounds(g,by_id) for k,g in before.items() if not g['deleted']}
    new={g['id']:bounds(g,by_id) for g in design['groups'] if not g['deleted']}
    old_parts={k:parts(g,by_id) for k,g in before.items() if not g['deleted']}
    new_parts={g['id']:parts(g,by_id) for g in design['groups'] if not g['deleted']}
    checked=[]
    for g in design['groups']:
        if g['translation']==before[g['id']]['translation']:continue
        area=g['placement_constraints']['area'];box=new[g['id']]
        if box[0][0]<area[0] or box[0][1]<area[1] or box[1][0]>area[2] or box[1][1]>area[3]:raise ValueError('修正超出允許家具區域：'+g['name'])
        for r in g['placement_constraints']['keep_out']:
            if min(box[1][0],r[2])>max(box[0][0],r[0]) and min(box[1][1],r[3])>max(box[0][1],r[1]):raise ValueError('修正進入保留動線：'+g['name'])
        for other,other_parts in new_parts.items():
            if other==g['id']:continue
            for identifier,a in new_parts[g['id']].items():
                for other_id,b in other_parts.items():
                    if penetration(a,b)>penetration(old_parts[g['id']][identifier],old_parts[other][other_id])+.008:raise ValueError('修正產生新碰撞或加重原碰撞：'+g['name'])
        checked.append(g['id'])
    return dict(checked_groups=checked,method='conservative native group bounds; not full circulation acceptance')


def override_roughness(obj,value):
    """Copy slots only; retain UV, image nodes, transmission and all other inputs."""
    copies=[]
    for slot in obj.material_slots:
        material=slot.material
        if not material or not material.use_nodes:raise ValueError('此材質不支援安全反光修正：'+obj.name)
        nodes=[n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED']
        if len(nodes)!=1:raise ValueError('複合材質需要人工核對：'+obj.name)
        node=nodes[0]
        for key in ('Transmission Weight','Metallic'):
            socket=node.inputs.get(key)
            if socket and (socket.is_linked or socket.default_value>.5):raise ValueError('玻璃／金屬不可用通用反光修正：'+obj.name)
        if node.inputs['Roughness'].is_linked:raise ValueError('粗糙度已有貼圖，保留原節點：'+obj.name)
        new=material.copy();next(n for n in new.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Roughness'].default_value=value;copies.append(new)
    if not copies:raise ValueError('物件缺少可調整的材質：'+obj.name)
    obj.data=obj.data.copy()
    for i,material in enumerate(copies):obj.data.materials[i]=material
