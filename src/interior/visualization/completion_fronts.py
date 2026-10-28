"""Source-bound multi-view evidence for functional fronts of opaque mesh assets."""
import hashlib,json
from array import array
from mathutils import Vector
from completion_geometry import bounds

KINDS=('cabinet','shoe_cabinet','wardrobe','bookcase','dishwasher','cooker','fridge','sink','vanity','shower')

def signature(objects):
    def geometry(obj):
        data=obj.data
        if not hasattr(data,'vertices'):return str(data)
        vertices=array('f',[0])* (len(data.vertices)*3);data.vertices.foreach_get('co',vertices)
        loops=array('i',[0])*len(data.loops);data.loops.foreach_get('vertex_index',loops)
        digest=hashlib.sha256(vertices.tobytes());digest.update(loops.tobytes());return digest.hexdigest()
    payload=[(o.get('studio_id'),[list(r) for r in o.matrix_world],geometry(o),[list(v) for v in bounds([o])]) for o in sorted(objects,key=lambda o:o.name)]
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

def front(design,group,objects):
    item=next((p for p in design.get('completion_fronts',[]) if p['group_id']==group['id'] and p['signature']==signature(objects)),None)
    if not item:return None
    d=Vector((0,0,0));d['XY'.index(item['front'][1])]=1 if item['front'][0]=='+' else -1
    return d,['Agent 正反面證據：'+item['evidence']]

def export(design,by_id,output):
    from completion_details import purpose,measured_front
    from model_review import previews
    items=[]
    for g in design['groups']:
        if g.get('deleted') or purpose(g) not in KINDS:continue
        objects=[by_id[k] for k in g['children'] if k in by_id and by_id[k].type=='MESH' and not by_id[k].hide_render]
        if not objects or measured_front(objects) or front(design,g,objects):continue
        folder=output/g['id'];folder.mkdir(parents=True,exist_ok=True)
        # Matrices already include the saved revision; never apply it a second time.
        evidence=previews(design,dict(g,rotation=0,translation=[0,0,0]),objects,folder,modes=('axis-positive-x','axis-negative-x','axis-positive-y','axis-negative-y'))
        items.append(dict(group_id=g['id'],name=g['name'],purpose=purpose(g),signature=signature(objects),bounds=[list(v) for v in bounds(objects)],images=[g['id']+'/'+f for f in evidence['images']],camera_directions=evidence['camera_directions']))
    return dict(items=items)
