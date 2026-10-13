"""Measure current edited geometry without altering any native object."""
import math
import bpy
from mathutils import Matrix, Vector
from asset_placement import local_placement

def check_placement(design, group, meshes):
    by_id={o.get('studio_id'):o for o in bpy.context.scene.objects if o.type in ('MESH','CURVE')}
    def change(g):
        p=Vector(g.get('rotation_pivot',[0,0,0]));d=Vector(g.get('translation',[0,0,0]))
        return Matrix.Translation(d+p)@Matrix.Rotation(math.radians(g.get('rotation',0)),4,'Z')@Matrix.Translation(-p)
    def box(obj,transform):
        pts=[transform@obj.matrix_world@Vector(c) for c in obj.bound_box]
        return [[fn(v[i] for v in pts) for i in range(3)] for fn in (min,max)]
    bpy.context.view_layer.update();obstacles=[]
    for other in design['groups']:
        if other['id']==group['id'] or other.get('deleted'):continue
        transform=change(other)
        for identifier in other['children']:
            if identifier in by_id:obstacles.append(dict(name=other['name'],bounds=box(by_id[identifier],transform)))
        concept=next((f for f in design.get('concept_furniture',[]) if f['id']==other['id']),None)
        if concept:
            for part in concept['parts']:
                c=part['center'];s=part['size']
                pts=[transform@Vector((c[0]+x*s[0]/2,c[1]+y*s[1]/2,c[2]+z*s[2]/2)) for x in (-1,1) for y in (-1,1) for z in (-1,1)]
                obstacles.append(dict(name=other['name'],bounds=[[fn(v[i] for v in pts) for i in range(3)] for fn in (min,max)]))
    result=local_placement([box(o,change(group)) for o in meshes],obstacles,group.get('placement_constraints'))
    group['translation']=[v+d for v,d in zip(group.get('translation',[0,0,0]),result['translation'])]
    return result
