"""Blender ray checks: empty aperture versus solid adjoining/upper wall."""
import bpy
from mathutils import Vector

walls=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.name.startswith('wall-')]
def blocked(origin,direction,distance):
    for obj in walls:
        inverse=obj.matrix_world.inverted()
        hit,*_=obj.ray_cast(inverse@Vector(origin),inverse.to_3x3()@Vector(direction),distance=distance)
        if hit:return True
    return False
assert not blocked((1.5,-.4,1),(0,1,0),.8),'entrance door was not cut'
assert blocked((.5,-.4,1),(0,1,0),.8),'adjoining wall disappeared'
assert blocked((1.5,-.4,2.5),(0,1,0),.8),'door lintel disappeared'
assert not blocked((3.6,1.5,1),(1,0,0),.8),'interior door was not cut'
assert not blocked((6.6,3.5,1.6),(1,0,0),.8),'window was not cut'
assert blocked((6.6,3.5,.5),(1,0,0),.8),'window sill wall disappeared'
print('APERTURES VERIFIED: 2 doors, window, adjoining walls and lintels')
