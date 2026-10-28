"""Independent rotated synthetic openings, source immutability and stable assemblies."""
import sys
sys.path.insert(0,sys.argv[-1])
import bpy
from mathutils import Vector
from opening_details import assembly

bpy.ops.wm.read_factory_settings(use_empty=True)
source='a'*64
for role,a,b in [('door',[8,4],[9.2,4]),('window',[12,5],[12,7.4]),('window',[20,1],[21,2])]:
    item=dict(id=role+str(a),name=role,role=role,points=[a,b],base=0 if role=='door' else 1,height=2.1 if role=='door' else 1.3)
    result=assembly(item,source);assert result['status']=='prepared'
    objects=[o for o in bpy.context.scene.objects if o.get('source_entity_id')==item['id']]
    assert len({o['studio_opening_group'] for o in objects})==1
    assert len({o['studio_id'] for o in objects})==len(objects)
    u=Vector((b[0]-a[0],b[1]-a[1],0)).normalized();origin=Vector((*a,item['base']))
    for obj in objects:
        for vertex in obj.data.vertices:
            p=obj.matrix_world@vertex.co-origin
            if not obj.get('opening_moving'):assert -.001<=p.dot(u)<=Vector((b[0]-a[0],b[1]-a[1],0)).length+.001
            assert -.001<=p.z<=item['height']+.001
    if role=='door':
        assert result['opening']['state']=='open'
        assert any(abs((o.matrix_world@v.co-origin).dot(Vector((-u.y,u.x,0))))>.5 for o in objects for v in o.data.vertices)
    assert result['material']=='procedural_oak'
    if role=='window':assert any(o.data.materials[0].node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value==1 for o in objects)
print('OPENING_ASSEMBLIES_PASSED')

# A door now exists where an old exterior shot was placed. Recovery uses the
# existing interior panorama eye and must still fit the whole independent bed.
from realism_framing import candidates,actual_frame_integrity
bpy.ops.wm.read_factory_settings(use_empty=True)
def cube(name,location,dimensions):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location)
    obj=bpy.context.object;obj.name=name;obj.dimensions=dimensions
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return obj
floor=cube('floor',(3,3,-.1),(6,6,.2))
door=cube('door',(1,0,1.5),(6,.04,3))
bed=cube('bed',(3,3,.3),(1.4,2,.6));bed['studio_id']='bed-part'
bpy.context.view_layer.update()
point=dict(id='independent-bedroom',eye=[1,1,1.6],shots=[dict(id='front',name='front',eye=[1,-.05,1.6],yaw=45,pitch=0,lens=24)])
group=dict(id='bed',name='bed',children=['bed-part'],object_specification={'purpose':'bed'})
options=candidates(point,group,[bed],Vector((2.3,2,0)),Vector((3.7,4,.6)),[floor],[door])
assert options and all(c['recovery_reason'] for c in options)
shot=options[0];point['shots']=[dict(shot,id='front')]
assert actual_frame_integrity({'groups':[group]},point,{'bed-part':bed})[0]['all_vertices_inside']
print('OPENING_CAMERA_RECOVERY_PASSED')

from realism_framing import window_sightline
bpy.ops.wm.read_factory_settings(use_empty=True)
pane=cube('intermediate glass',(2,0,1.5),(.006,2,2))
mat=bpy.data.materials.new('clear');mat.use_nodes=True
mat.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value=1
pane.data.materials.append(mat);bpy.context.view_layer.update()
scene=bpy.context.scene;deps=bpy.context.evaluated_depsgraph_get()
assert window_sightline(scene,deps,Vector((0,0,1.5)),Vector((4,0,1.5)))
mat.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value=0
bpy.context.view_layer.update()  # Reevaluate the edited shader before ray inspection.
assert not window_sightline(scene,deps,Vector((0,0,1.5)),Vector((4,0,1.5)))
print('WINDOW_THROUGH_GLASS_ANCHOR_PASSED')

# A shelf obstructs the default sliding track, but not the other mounting face.
bpy.ops.wm.read_factory_settings(use_empty=True)
cube('retained shelf',(1.25,.06,.8),(.3,.08,1.6))
item=dict(id='independent-slider',name='sliding door',role='door',points=[[0,0],[1.6,0]],base=0,height=2.1)
result=assembly(item,source)
assert result['opening']['state']=='open',result
assert result['opening']['track_offset']!=0,result
assert bpy.data.objects.get('retained shelf') is not None
print('SLIDING_ALTERNATE_TRACK_PASSED')
# Explicit user choices cannot be silently reversed to pass collisions.
bpy.ops.wm.read_factory_settings(use_empty=True)
item=dict(id='controlled-door',name='door',role='door',points=[[0,0],[1,0]],base=0,height=2.1,control={'hinge':'B','swing':'negative'})
result=assembly(item,source)
assert result['opening']['state']=='open' and result['opening']['hinge']=='inferred-B' and result['opening']['angle']==-90,result
print('EXPLICIT_DOOR_CONTROL_PASSED')

# Switching the hinge also moves the handle to the free edge, rather than leaving
# it next to the hinge. B hinge is (0.96,0) before opening.
from completion_geometry import bounds
handle=bpy.data.objects.get('door · handle-0')
center=sum(bounds([handle]),Vector())/2
assert (center-Vector((.96,0,center.z))).length>.6
print('DOOR_HANDLE_FREE_EDGE_PASSED')
