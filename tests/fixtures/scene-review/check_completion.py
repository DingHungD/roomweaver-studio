"""Independent room: exact dimensions, functional fronts, ceiling and wall fit."""
import sys
sys.path.insert(0,sys.argv[-1])
import bpy
from mathutils import Vector
from completion_details import prepare,placement,measured_front
from realism_ceiling import ceiling_options
from completion_geometry import bounds

bpy.ops.wm.read_factory_settings(use_empty=True)
design=dict(completion_details=True,groups=[],objects=[],rooms=[],lighting_setup={'lights':[]},ceiling_infill=[])
by={}
def cube(key,position,size,group=None,kind=None):
    bpy.ops.mesh.primitive_cube_add(size=1,location=position);o=bpy.context.object;o.name=key;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o['studio_id']=key;by[key]=o
    if group is None:
        group=dict(id=key,name=key,children=[],deleted=False,method='structural_'+kind if kind else 'individual');design['groups'].append(group)
    group['children'].append(key);design['objects'].append(dict(id=key,room_id=None));return o
floor=cube('floor',(3,2.5,-.1),(6,5,.2),kind='floor')
cube('south',(3,-.1,1.5),(6.4,.2,3),kind='wall');cube('north',(3,5.1,1.5),(6.4,.2,3),kind='wall')
cube('west',(-.1,2.5,1.5),(.2,5,3),kind='wall');cube('east',(6.1,2.5,1.5),(.2,5,3),kind='wall')
cabinet=dict(id='cabinet',name='Independent cabinet',children=[],deleted=False,asset_requirements={'purpose':'cabinet','dimension_source':'confirmed','dimensions':[1,.6,.9],'evidence':'synthetic fixed size'})
design['groups'].append(cabinet)
body=cube('cabinet-body',(1,.4,.45),(1,.6,.9),cabinet)
handle=cube('handle',(1,.095,.6),(.2,.01,.02),cabinet)
shower=dict(id='shower',name='Independent shower',children=[],deleted=False,asset_requirements={'purpose':'shower','dimension_source':'confirmed','dimensions':[.8,.8,2.1],'evidence':'synthetic fixed size'})
design['groups'].append(shower);tray=cube('shower-body',(5.55,4.54,1.05),(.8,.8,2.1),shower)
# A high cabinet is not a roof; one triangle centroid used to be enough to skip it.
cube('tall cabinet',(3,2.5,1.4),(.5,.5,2.8))
lamp_group=dict(id='lamp',name='ceiling fixture',children=[],deleted=False,asset_requirements={'purpose':'light'})
design['groups'].append(lamp_group);lamp=cube('lamp-shell',(3,1.5,2.82),(.4,.4,.08),lamp_group)
light_data=bpy.data.lights.new('test-emitter','AREA');light=bpy.data.objects.new('test-emitter',light_data);bpy.context.scene.collection.objects.link(light);light.location=(3,1.5,2.74);light['studio_light_id']='light-concept-1234567890abcdef1234567890abcdef'
design['lighting_setup']['lights']=[dict(id='light-concept-1234567890abcdef1234567890abcdef',name='test light',kind='AREA',enabled=True,group_id='lamp',locked=False,color=[1,1,1])]
bpy.context.view_layer.update()
assert measured_front([body,handle])[0].y==-1
before={k:tuple(bounds([o])[1]-bounds([o])[0]) for k,o in by.items()}
options=ceiling_options(design,by);assert [o['id'] for o in options['options']]==['floor']
report=prepare(design,by)
assert len(report['ceiling_patches'])==1
assert {r['action'] for row in report['items'] if row['id']=='light-concept-1234567890abcdef1234567890abcdef' for r in row['changes']}=={'mount','diffuser'}
rows={r['id']:r for r in report['items']}
assert rows['cabinet']['status']=='corrected',rows
assert rows['shower']['status']=='corrected',rows
assert measured_front([body,handle])[0].y==1
assert abs(bounds([tray])[1].x-5.997)<.005 and abs(bounds([tray])[1].y-4.997)<.005
assert all(max(abs(a-b) for a,b in zip(before[k],bounds([o])[1]-bounds([o])[0]))<.005 for k,o in by.items())
assert not ceiling_options(design,by)['options']
# Replay should not add ceilings or double-rotate a correct cabinet.
again=prepare(design,by);assert not again['ceiling_patches'];assert not any(r['changes'] for r in again['items'])
# Original wall/floor vertices and confirmed geometry size are preserved.
print('COMPLETION_DETAILS_PASSED')

# Agent evidence cannot survive a moved/replaced model; a valid native front may
# rotate an opaque product while preserving the confirmed dimensions.
from completion_fronts import signature,front
evidence=dict(group_id=cabinet['id'],signature=signature([body,handle]),front='+Y',evidence='Synthetic actual front/back view evidence')
design['completion_fronts']=[evidence]
assert front(design,cabinet,[body,handle])[0].y==1
body.data.vertices[0].co.x+=.01
assert front(design,cabinet,[body,handle]) is None
body.data.vertices[0].co.x-=.01
body.location.x+=.02;bpy.context.view_layer.update()
assert front(design,cabinet,[body,handle]) is None
body.location.x-=.02;bpy.context.view_layer.update()

# Independently authored sink: retain bowl, support, dimensions and open basin.
from completion_sink import finish_sinks
sink=dict(id='sink',name='independent sink',children=[],deleted=False,asset_requirements={'purpose':'sink'})
design['groups'].append(sink)
cube('Repair installation side A',(3-.28,.35,.425),(.04,.6,.85),sink)
cube('Repair installation side B',(3+.28,.35,.425),(.04,.6,.85),sink)
cube('Basin bowl',(3,.28,.78),(.5,.42,.18),sink)
result=finish_sinks(design,by)
assert result[0]['status']=='corrected',result
assert any(r['action']=='sink_finish' for r in result[0]['changes'])
assert not finish_sinks(design,by)[0]['changes']
tap=cube('faucet',(3,.49,.94),(.025,.025,.18),sink)
assert measured_front([by['Basin bowl'],tap])[0].y==-1
print('FUNCTIONAL_FRONTS_AND_SINK_PASSED')
