import sys
from pathlib import Path
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy
from mathutils import Vector
from fixture_mount import mount

def box(name,location,size,key):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location);obj=bpy.context.object;obj.name=name;obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);obj['studio_id']=key;return obj

for mode in ('surface','recessed','pendant'):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    host=box('Plaster ceiling',(0,0,2.85),(4,4,.3),'roof');host['studio_fixture_finish']=True
    lamp=box('Light',(0,0,.1),(.4,.4,.2),'lamp')
    group=dict(id='light',name='天花燈具',children=['lamp'],translation=[0,0,2.4],rotation=0)
    scene=dict(groups=[group,dict(id='ceiling',name='天花裝修',children=['roof'],translation=[0,0,0])],objects=[],lighting_setup={'lights':[]})
    old=[tuple(v.co) for v in host.data.vertices]
    report=mount(scene,group,[lamp],dict(mode=mode,recess_depth=.04),'a'*32)
    assert report['status']=='passed' and report['contact_error']<.006
    top=max((lamp.matrix_world@Vector(c)).z for c in lamp.bound_box)+2.4
    assert abs(top-(2.7+(.04 if mode=='recessed' else 0)))<.001,(mode,top)
    if mode=='recessed':assert len(host.data.vertices)>8
    else:assert old==[tuple(v.co) for v in host.data.vertices]
    if mode=='pendant':assert any(o.name=='Pendant canopy' for o in bpy.context.scene.objects)

# A lamp name or a structural slab cannot substitute for an allowed finish.
bpy.ops.wm.read_factory_settings(use_empty=True)
host=box('Concrete structural slab',(0,0,2.85),(4,4,.3),'roof');lamp=box('Light',(0,0,2.6),(.4,.4,.2),'lamp')
group=dict(id='light',name='天花燈具',children=['lamp'],translation=[0,0,0])
scene=dict(groups=[group,dict(id='ceiling',name='結構樓板',children=['roof'],translation=[0,0,0])],objects=[])
try:mount(scene,group,[lamp],dict(mode='recessed',recess_depth=.04),'b'*32)
except ValueError:pass
else:raise AssertionError('structural slab must not be cut')
print('FIXTURE_INSTALLATION_PASSED')

# Area/intensity evidence corrects only clearly upward, flat emitting fixtures.
from fixture_emission import orient,measure
bpy.ops.wm.read_factory_settings(use_empty=True)
lamp=box('Flat disc',(0,0,0),(.4,.4,.08),'light')
emission=bpy.data.materials.new('Emitter');emission.use_nodes=True
node=emission.node_tree.nodes.get('Principled BSDF');node.inputs['Emission Strength'].default_value=15
lamp.data.materials.append(emission)
shell=bpy.data.materials.new('Shell');lamp.data.materials.append(shell)
for p in lamp.data.polygons:p.material_index=0 if p.normal.z>.9 else 1
before=measure([lamp]);assert before.get('weighted_normal_z',0)>.99,before
old=tuple(lamp.dimensions)
report=orient([lamp],'surface')
assert report['corrected'] and measure([lamp])['weighted_normal_z']<-.99
assert all(abs(a-b)<1e-5 for a,b in zip(old,lamp.dimensions))
assert not orient([lamp],'surface')['corrected'] # no oscillation on replay
lamp.matrix_world=__import__('mathutils').Matrix.Identity(4);assert not orient([lamp],'pendant')['corrected']
plain=box('No emissive material',(2,0,0),(.4,.4,.1),'plain');assert not orient([plain],'surface')['corrected']
print('FIXTURE_EMISSION_PASSED')
