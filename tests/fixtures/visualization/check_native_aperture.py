"""Build synthetic off-axis source openings and ray-check the full wall depth."""
import copy
from pathlib import Path
import sys

import bpy
from mathutils import Vector

args=sys.argv[sys.argv.index('--')+1:]
sys.path.insert(0,str(Path(args[0])/'src/interior/visualization'))
from plan_blender import build_plan

def item(id,role,points,**kwargs):
    return dict(id=id,name=id,role=role,points=points,closed=role=='floor',base=0,
                height=.12 if role=='floor' else 2.8,thickness=.2,**kwargs)

floor=item('floor','floor',[[-1,-1],[5,-1],[5,3],[-1,3]])
wall=item('wall','wall',[[0,0],[4,0]])
door=item('door','door',[[1,.08],[2,.08]],host_id='wall');door['height']=2.1
window=item('window','window',[[3,-.08],[3.7,-.08]],host_id='wall');window.update(base=1,height=1.2)
plan=dict(items=[floor,wall,door,window],source_origin_metres=[0,0],basic_model=True)
before=copy.deepcopy(plan)
build_plan(dict(plan=plan,source_sha256='a'*64,preview=args[1]))
assert plan==before,'Source opening points were changed'
bpy.context.view_layer.update()
walls=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.name.startswith('wall-')]
def blocked(x,z):
    for obj in walls:
        inverse=obj.matrix_world.inverted()
        hit,*_=obj.ray_cast(inverse@Vector((x,-.5,z)),inverse.to_3x3()@Vector((0,1,0)),distance=1)
        if hit:return True
    return False
assert not blocked(1.5,1),'Native off-axis door left a thin wall remnant'
assert not blocked(3.35,1.5),'Native off-axis window left a thin wall remnant'
assert blocked(.5,1),'Adjacent wall was removed'
assert blocked(1.5,2.5),'Door lintel was removed'
assert blocked(3.35,.5),'Window sill wall was removed'
print('NATIVE APERTURES VERIFIED: unchanged source axes; full-depth cuts; lintel and sill retained')
