"""Native synthetic checks: compound framing, mixed glass and independent windows."""
import sys
sys.path.insert(0,sys.argv[-1])
import bpy
from mathutils import Vector
from realism_framing import candidates, actual_frame_integrity, partition_clear, window_sightline
from realism_details import window_options
from composition_context import related_purposes
bpy.ops.wm.read_factory_settings(use_empty=True)
def cube(key,center,size):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center)
    obj=bpy.context.object;obj.name=key;obj['studio_id']=key;obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return obj
floor=cube('floor',(0,2,-.1),(8,8,.2))
a=cube('desk',(-1,3,.4),(1.2,.8,.8));b=cube('chair',(1,2,.5),(.6,.6,1))
bpy.context.view_layer.update()
point=dict(id='synthetic',eye=[0,0,1.6],shots=[dict(id='s',yaw=90,pitch=0,lens=24)])
groups=[dict(id=k,name=k,children=[k],object_specification={'purpose':k}) for k in ('desk','chair')]
options=candidates(point,groups[0],[a],Vector((-1.6,2.6,0)),Vector((-.4,3.4,.8)),[floor],[],context_objects=[b])
assert options
for option in options:
    assert 'near_edge_blocker_fraction' in option['metrics'] and 'wide_angle_penalty' in option['metrics']
    point['shots']=[dict(option,id='s')]
    checks=actual_frame_integrity({'groups':groups},point,{'desk':a,'chair':b})
    assert len(checks)==2 and all(c['all_vertices_inside'] for c in checks),checks
assert related_purposes('sink','dishwasher') and related_purposes('bunk_bed','wardrobe')
assert not related_purposes('sofa','sink') and not related_purposes('unknown','desk')
# A companion can completely hide a hero even though the combined group is visible.
cover=cube('companion cover',(-1,3,.45),(1.4,1,1))
bpy.context.view_layer.update()
point['shots']=[dict(id='s',yaw=90,pitch=0,lens=24)]
covered=candidates(point,groups[0],[a],Vector((-1.6,2.6,0)),Vector((-.4,3.4,.8)),[floor],[],context_objects=[cover])
assert not covered, 'Combined group visibility must not certify a fully hidden hero'
bpy.data.objects.remove(cover,do_unlink=True)
wall=cube('partition',(0,3,1.1),(.1,4,2.2));bpy.context.view_layer.update()
assert not partition_clear(bpy.context.scene,bpy.context.evaluated_depsgraph_get(),Vector((-1,3,1.1)),Vector((1,3,1.1)),[wall])
assert partition_clear(bpy.context.scene,bpy.context.evaluated_depsgraph_get(),Vector((-1,3,1.1)),Vector((1,3,1.1)),[])
bpy.ops.wm.read_factory_settings(use_empty=True)
pane=cube('window',(2,0,1.5),(.01,2,2))
glass=bpy.data.materials.new('glass');glass.use_nodes=True
glass.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value=1
wood=bpy.data.materials.new('unused frame slot');wood.use_nodes=True
pane.data.materials.append(glass);pane.data.materials.append(wood)
bpy.context.view_layer.update();scene=bpy.context.scene;deps=bpy.context.evaluated_depsgraph_get()
assert window_sightline(scene,deps,Vector((0,0,1.5)),Vector((4,0,1.5)))
for polygon in pane.data.polygons:polygon.material_index=1
bpy.context.view_layer.update()
assert not window_sightline(scene,bpy.context.evaluated_depsgraph_get(),Vector((0,0,1.5)),Vector((4,0,1.5)))
design={'groups':[dict(id='w',name='window',children=['window'],deleted=False)]}
extent=[Vector((-10,-10,0)),Vector((10,10,0))]
assert not window_options(design,{'eye':[0,0,1.5]},{'window':pane},extent)
assert len(window_options(design,{'eye':[0,0,1.5]},{'window':pane},extent,True))==1
print('COMPOUND_FRAMING_AND_WINDOW_TESTS_PASSED')

# Hidden source blockers must not erase the visible replacement window.
for polygon in pane.data.polygons:polygon.material_index=0
old=cube('hidden original',(1,0,1.5),(.2,2,2));old.hide_render=True
bpy.context.view_layer.update()
assert window_sightline(scene,bpy.context.evaluated_depsgraph_get(),Vector((0,0,1.5)),Vector((4,0,1.5)))
old.hide_render=False;bpy.context.view_layer.update()
assert not window_sightline(scene,bpy.context.evaluated_depsgraph_get(),Vector((0,0,1.5)),Vector((4,0,1.5)))
print('HIDDEN_SOURCE_OCCLUSION_PASSED')
