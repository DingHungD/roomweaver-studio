"""Recover assembly identity without changing immutable imported meshes or revisions."""
import json
import struct
from uuid import NAMESPACE_URL, uuid5


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
        if isinstance(source,str) and source:
            key='source:'+source;label=source;method='source_id'
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
