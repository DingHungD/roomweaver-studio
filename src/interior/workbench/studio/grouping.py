"""Recover assembly identity without changing immutable imported meshes or revisions."""
import json
import struct
import re
from uuid import NAMESPACE_URL, uuid5


def structural_role(name, extras=None):
    """Prefer explicit semantics; never infer structure from a host/furniture name."""
    explicit=(extras or {}).get('studio_role')
    if explicit:return explicit if explicit in ('wall','floor') else None
    # Match a leading architectural noun, not "floor lamp", "wall cabinet",
    # "shower wall shelf" or material names attached to a piece of furniture.
    stem=name.lower().split('__',1)[0]
    if re.search(r'lamp|light|shelf|cabinet|decor|rug|mat\b|燈|櫃|架|毯',stem):return None
    for role,pattern in (('wall',r'^(?:walls?(?=$|[\s_.\-\d])|牆壁|牆面|牆體|牆)'),
                         ('floor',r'^(?:floors?(?=$|[\s_.\-\d])|地板|地坪|樓板)')):
        if re.search(pattern,stem):return role
    return None


def assembly_groups(objects, path):
    nodes=[]
    if path.is_file():
        with path.open('rb') as stream:
            header=stream.read(20)
            if len(header)==20 and header[:4]==b'glTF':
                size=struct.unpack_from('<I',header,12)[0]
                nodes=json.loads(stream.read(size)).get('nodes',[])
    by_id={n.get('extras',{}).get('studio_id'):n for n in nodes}
    by_name={n.get('name'):n for n in nodes}
    parents={child:index for index,n in enumerate(nodes) for child in n.get('children',[])}
    indices={id(n):i for i,n in enumerate(nodes)}
    buckets={}
    for obj in objects:
        node=by_id.get(obj['id']) or by_name.get(obj['name'],{})
        extra=node.get('extras',{})
        source=extra.get('assembly_id') or extra.get('source_id')
        name=obj['name']
        role=structural_role(node.get('name',name),extra)
        if not role and not extra.get('studio_role') and isinstance(source,str):role=structural_role(source)
        if role:
            key='structure:'+role;label={'wall':'牆壁','floor':'地板'}[role];method='structural_'+role
        elif extra.get('skp_assembly_id'):
            key='skp:'+extra['skp_assembly_id'];label=extra.get('skp_assembly_name') or name;method='skp_source_instance'
        elif isinstance(source,str) and source:
            key='source:'+source;label=source;method='source_id'
            parent_index=parents.get(indices.get(id(node)))
            if parent_index in parents and 'mesh' not in nodes[parent_index]:
                # Instanced furniture can share a source ID; its local container
                # still identifies a separate physical chair/bed.
                key+=':instance:'+str(parent_index)
        elif '__' in name:
            label=name.split('__',1)[0];key='name:'+label;method='name_prefix'
        else:
            index=parents.get(indices.get(id(node)))
            parent=nodes[index] if index is not None else {}
            label=parent.get('name','')
            # Only a local assembly parent, never the scene/container root.
            if index in parents and label and len(parent.get('children',[]))<=100:
                key='parent:'+str(index);method='hierarchy'
            else:
                key='object:'+obj['id'];label=name;method='individual'
        bucket=buckets.setdefault(key,dict(id=uuid5(NAMESPACE_URL,key+'|'+str(path.parent.name)).hex,
            name=label,children=[],translation=[0,0,0],deleted=False,method=method))
        bucket['children'].append(obj['id'])
    return list(buckets.values())


def regroup_structure(scene, imported_groups):
    """Revision-only migration. Refuse unequal transforms rather than move geometry."""
    import copy
    result=copy.deepcopy(scene);changes=[]
    roles={child:g['method'] for g in imported_groups if g['method'].startswith('structural_') for child in g['children']}
    for method,label in (('structural_wall','牆壁'),('structural_floor','地板')):
        candidates=[g for g in result['groups'] if not g['deleted'] and
                    (g.get('method')==method or all(roles.get(c)==method for c in g['children']))]
        if not candidates:continue
        first=candidates[0]
        def transform(g):return (g['translation'],g.get('rotation',0),g.get('rotation_pivot',[0,0,0]))
        if any(transform(g)!=transform(first) for g in candidates):
            raise ValueError(label+'已有不同位移或旋轉，尚未合組；請先在編輯中恢復相同變換，以免改變位置')
        if len(candidates)>1 and any(g.get('asset_reference') for g in candidates):
            raise ValueError(label+'含模型替換來源，尚未合組；請保留既有版本並重新匯入整理後模型')
        old_ids={g['id'] for g in candidates}
        first.update(name=label,method=method,children=[c for g in candidates for c in g['children']])
        result['groups']=[g for g in result['groups'] if g['id']==first['id'] or g['id'] not in old_ids]
        for light in result.get('lighting_setup',{}).get('lights',[]):
            if light.get('group_id') in old_ids:light['group_id']=first['id']
        changes.append(dict(kind=method,previous=len(candidates),children=len(first['children'])))
    return result,changes
