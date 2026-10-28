"""Different synthetic geometry: installation repair and confirmed bounds rejection."""
import sys,json,copy
from pathlib import Path
import bpy
from mathutils import Matrix
sys.path.insert(0,sys.argv[-1])
from scene_functional_repair import apply
from scene_diagnostics import inspect_groups,opening_obstructions
from scene_framing import options

def cube(identifier,center,size):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center);o=bpy.context.object;o.name=identifier;o['studio_id']=identifier;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    m=bpy.data.materials.new(identifier);m.use_nodes=True;o.data.materials.append(m);return o

def setup(confirmed=False,obstacle=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cube('floor',(0,0,-.05),(8,8,.1));cube('basin',(0,0,.35),(.8,.55,.1));cube('ornament',(0,0,.45),(.1,.1,.1))
    if obstacle:cube('blocker',(0,0,.8),(.8,.55,.2))
    ids=['floor','basin','ornament']+(['blocker'] if obstacle else [])
    groups=[dict(id=i,name=i,children=[i],deleted=False,translation=[0,0,0],rotation=0,rotation_pivot=[0,0,0],asset_requirements=None,decor_context=None) for i in ids]
    groups[1]['asset_requirements']=dict(purpose='vanity',dimension_source='confirmed' if confirmed else 'unknown',dimensions=[.8,.55,.1],evidence='synthetic' if confirmed else '')
    groups[2]['decor_context']=dict(support_group_id='basin')
    bpy.context.view_layer.update()
    return dict(groups=groups,objects=[dict(id=i,name=i,room_id=None,material={}) for i in ids],concept_furniture=[],lighting_setup={'lights':[]},design_notes=[],viewpoints=[dict(id='point',eye=[0,-.8,1.6],shots=[])])

scene=setup();before=inspect_groups(scene);original=bpy.data.objects['basin'].dimensions.copy()
packet=dict(scene=scene,model_id='a'*32,functional_repair=dict(target_id='basin',action='install',values={'surface_z':.4,'target_height':.85},reason='test'))
result=apply(packet)
assert abs(result['shift_z']-.45)<.001
assert (bpy.data.objects['basin'].dimensions-original).length<.001
assert abs(bpy.data.objects['ornament'].location.z-.90)<.001
assert len(result['created_ids'])==3
assert packet['repaired_scene']['groups'][1]['asset_requirements']==scene['groups'][1]['asset_requirements']
assert options(packet['repaired_scene'])  # Framing uses floor and visibility, not a case ID.
for confirmed,obstacle in [(True,False),(False,True)]:
    packet['scene']=setup(confirmed,obstacle)
    try:apply(packet)
    except ValueError:pass
    else:raise AssertionError('unsafe repair accepted')

# A floor-reaching pipe must not shorten supports under the bowl.
scene=setup();scene['groups'][1]['asset_requirements']['purpose']='sink'
cube('pipe',(0,0,.15),(.05,.05,.3));scene['groups'][1]['children'].append('pipe')
scene['objects'].append(dict(id='pipe',name='pipe',room_id=None,material={}))
bpy.context.view_layer.update()
packet=dict(scene=scene,model_id='b'*32,functional_repair=dict(target_id='basin',action='install',values={'surface_z':.4,'target_height':.85},reason='support test'))
result=apply(packet)
sides=[c for c in result['after']['components'] if 'installation side' in c['name']]
assert len(sides)==2 and all(abs(c['bounds'][1][2]-.825)<.001 for c in sides)
scene=packet['repaired_scene']
packet=dict(scene=scene,model_id='c'*32,functional_repair=dict(target_id='basin',action='component',values={'faucet':{'base':[-.3,-.2,.85],'spout':[-.15,-.2,.98],'material_id':'basin'}},reason='missing faucet'))
result=apply(packet)
assert len(result['created_ids'])==1 and result['shift_z']==0
assert all(k in packet['repaired_scene']['groups'][1]['children'] for k in scene['groups'][1]['children'])
scene=setup()
for identifier,name,size in [('opening','window test',(.06,1,1)),('wall','wall test',(.12,1.5,2))]:
    cube(identifier,(2,2,1),size)
    scene['groups'].append(dict(id=identifier,name=name,children=[identifier],deleted=False,translation=[0,0,0],rotation=0,rotation_pivot=[0,0,0]))
bpy.context.view_layer.update()
probes=opening_obstructions(scene,['opening'])
assert len(probes)==1 and len(probes[0]['samples'])==18
assert all(s['hit_group_id']=='wall' for s in probes[0]['samples'])
scene=setup()
for obj in bpy.context.scene.objects:obj.location.z+=2
scene['groups'][1]['translation']=[1,0,0];scene['groups'][1]['rotation']=90
bpy.context.view_layer.update()
packet=dict(scene=scene,model_id='d'*32,functional_repair=dict(target_id='basin',action='install',values={'surface_z':2.4,'target_height':.85},reason='nonzero floor and rotated group'))
result=apply(packet)
assert abs(result['shift_z']-.45)<.001 and abs(result['after']['floor_z']-2)<.001
assert packet['repaired_scene']['groups'][1]['translation']==[1,0,0]
assert packet['repaired_scene']['groups'][1]['rotation']==90
print('FUNCTIONAL_REPAIR_CHECKS_PASSED')
