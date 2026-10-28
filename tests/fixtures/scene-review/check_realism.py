"""Blender test: preserve texture paths, shared materials, UVs and mesh dimensions."""
import sys
import bpy
sys.path.insert(0,sys.argv[-1])
from realism_finish import apply_finish,eligible
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add();a=bpy.context.object
b=a.copy();b.data=a.data;bpy.context.collection.objects.link(b)
m=bpy.data.materials.new('paint');m.use_nodes=True
p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Metallic'].default_value=0
texture=m.node_tree.nodes.new('ShaderNodeTexNoise');bump=m.node_tree.nodes.new('ShaderNodeBump')
m.node_tree.links.new(texture.outputs['Fac'],bump.inputs['Height']);m.node_tree.links.new(bump.outputs['Normal'],p.inputs['Normal']);m.node_tree.links.new(texture.outputs['Color'],p.inputs['Base Color'])
a.data.materials.append(m)
metal=m.copy();metal.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=1;a.data.materials.append(metal)
glass=m.copy();glass.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value=1
assert eligible(m) and not eligible(metal) and not eligible(glass)
before=[tuple(v.co) for v in a.data.vertices];uv=[tuple(v.uv) for v in a.data.uv_layers.active.data]
apply_finish(a,dict(albedo_gain=[.9,1,1],roughness_delta=.1,bump_factor=.5,bevel=.001))
assert a.data is not b.data and a.data.materials[0]!=m and b.data.materials[0]==m
assert a.data.materials[1]==metal and p.inputs['Base Color'].links[0].from_node==texture
assert [tuple(v.co) for v in a.data.vertices]==before and [tuple(v.uv) for v in a.data.uv_layers.active.data]==uv
local=a.data.materials[0];assert any(n.type=='TEX_NOISE' for n in local.node_tree.nodes)
assert next(n for n in local.node_tree.nodes if n.type=='BUMP').inputs['Strength'].default_value==.5
assert bump.inputs['Strength'].default_value==1
print('REALISM_FINISH_PRESERVATION_PASSED')

from realism_details import detail_options,add_exteriors
from mathutils import Vector
bpy.ops.wm.read_factory_settings(use_empty=True)
def cube(key,center,size,material):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center);o=bpy.context.object;o.name=key;o['studio_id']=key;o.dimensions=size;o.data.materials.append(material);return o
paint=bpy.data.materials.new('paint');paint.use_nodes=True
fabric=bpy.data.materials.new('Fabric cotton');fabric.use_nodes=True
floor=cube('floor',(2.5,2.5,-.1),(5,5,.2),paint)
window=cube('window',(5,2.5,1.6),(.06,1.2,1.2),paint)
cabinet=cube('cabinet',(4,4,1),(.8,.5,2),paint)
sofa=cube('sofa',(3,2,.5),(1.6,.6,1),fabric)
bpy.context.view_layer.update()
groups=[dict(id=k,name=('external window' if k=='window' else k),children=[k],deleted=False,object_specification=dict(purpose=('cabinet' if k=='cabinet' else 'sofa' if k=='sofa' else ''),front='+X' if k=='cabinet' else 'unknown')) for k in ('floor','window','cabinet','sofa')]
point=dict(id='new',eye=[1,2,1.6],shots=[dict(id='front',eye=[1,2,1.6],yaw=0,pitch=-30,lens=17)])
design=dict(groups=groups,objects=[dict(id=k) for k in ('floor','window','cabinet','sofa')],viewpoints=[point],illustrative_exteriors=['window'])
by_id={o.get('studio_id'):o for o in (floor,window,cabinet,sofa)}
options=detail_options(design,point,by_id,set(by_id))
assert options['windows'] and options['cabinets'][0]['front']=='+X' and options['textiles']==['sofa']
assert options['cameras'] and all(-10<=o['pitch']<=0 and 20<=o['lens']<=35 for o in options['cameras'])
from bpy_extras.object_utils import world_to_camera_view
import math
scene=bpy.context.scene;scene.render.resolution_x=1024;scene.render.resolution_y=768;scene.render.resolution_percentage=100
for option in options['cameras']:
    data=bpy.data.cameras.new('projection-check');cam=bpy.data.objects.new('projection-check',data);scene.collection.objects.link(cam)
    data.lens=option['lens'];data.shift_y=option['shift_y'];cam.location=option['eye']
    yaw=math.radians(option['yaw']);pitch=math.radians(option['pitch']);cam.rotation_euler=Vector((math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),math.sin(pitch))).to_track_quat('-Z','Y').to_euler();bpy.context.view_layer.update()
    projected=[world_to_camera_view(scene,cam,sofa.matrix_world@Vector(v)) for v in sofa.bound_box]
    assert all(.03<=p.x<=.97 and .03<=p.y<=.97 and p.z>0 for p in projected),projected
    bpy.data.objects.remove(cam,do_unlink=True)
original={k:([tuple(v.co) for v in o.data.vertices],list(o.matrix_world)) for k,o in by_id.items()}
apply_finish(cabinet,dict(cabinet_front='+X',bevel=.001))
apply_finish(sofa,dict(textile=.6))
created=add_exteriors(design,options);assert created
assert all(not o.visible_shadow and not o.visible_diffuse for o in bpy.context.scene.objects if o.get('studio_illustrative_exterior'))
assert original=={k:([tuple(v.co) for v in o.data.vertices],list(o.matrix_world)) for k,o in by_id.items()}
print('REALISM_DETAILS_PRESERVATION_PASSED')

# An open ceiling must not reveal the background outside its window aperture.
window.hide_render=True
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=4
scene.world=bpy.data.worlds.new('neutral test');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.12,.12,.12,1)
scene.render.resolution_x=128;scene.render.resolution_y=96;scene.render.resolution_percentage=100
camera=bpy.data.cameras.new('test');cam=bpy.data.objects.new('test',camera);scene.collection.objects.link(cam);scene.camera=cam
cam.location=(1,2.5,1.6);cam.rotation_euler=Vector((1,0,0)).to_track_quat('-Z','Y').to_euler();camera.lens=24
from array import array
import tempfile
temporary=tempfile.TemporaryDirectory(prefix='roomweaver-realism-')
def pixels(name):
    scene.render.filepath=temporary.name+'/'+name+'.png';scene.render.image_settings.file_format='PNG';bpy.ops.render.render(write_still=True)
    im=bpy.data.images.load(scene.render.filepath,check_existing=False);data=array('f',[0])*len(im.pixels);im.pixels.foreach_get(data);bpy.data.images.remove(im);return data
after=pixels('with-exterior')
for obj in scene.objects:
    if obj.get('studio_illustrative_exterior'):obj.hide_render=True
before=pixels('without-exterior')
outside=[(y*128+x)*4 for y in range(80,94) for x in range(40,88)]
inside=[(y*128+x)*4 for y in range(40,56) for x in range(59,69)]
assert max(abs(after[i+c]-before[i+c]) for i in outside for c in range(3))<.015
assert max(abs(after[i+c]-before[i+c]) for i in inside for c in range(3))>.03
print('REALISM_WINDOW_APERTURE_PASSED')
# A new synthetic sofa/table arrangement must keep both full envelopes in frame.
from realism_framing import candidates
from realism_details import box
small_table=cube('coffee table',(2.3,1.5,.4),(.6,.6,.8),paint);bpy.context.view_layer.update()
frames=candidates(point,groups[-1],[sofa],*box(sofa),[floor],[],[box(small_table)])
assert frames
scene.render.resolution_x=1024;scene.render.resolution_y=768
for frame in frames:
    camera.lens=frame['lens'];camera.shift_y=frame['shift_y'];cam.location=frame['eye']
    yaw=math.radians(frame['yaw']);pitch=math.radians(frame['pitch']);cam.rotation_euler=Vector((math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),math.sin(pitch))).to_track_quat('-Z','Y').to_euler();bpy.context.view_layer.update()
    for item in (sofa,small_table):
        points=[world_to_camera_view(scene,cam,item.matrix_world@Vector(v)) for v in item.bound_box]
        assert all(.03<=p.x<=.97 and .03<=p.y<=.97 and p.z>0 for p in points)
print('REALISM_CONTEXT_FRAMING_PASSED')

# Round furniture must not require empty rectangular corners in the photograph.
from realism_framing import silhouette_hull
circle=[Vector((5+math.cos(i*math.pi/16),7+math.sin(i*math.pi/16),z)) for i in range(32) for z in (0,.5)]
hull=silhouette_hull(circle)
assert len(hull)==64 and all(any((v-p).length<1e-5 for p in circle) for v in hull)
assert all((v-Vector((6,8,.5))).length>.1 for v in hull)
print('REALISM_SILHOUETTE_HULL_PASSED')


# Generic new home: translated floor outline, existing roof, outdoor label, and original geometry protection.
from realism_ceiling import ceiling_options,add_ceilings
bpy.ops.wm.read_factory_settings(use_empty=True)
paint=bpy.data.materials.new('new paint');paint.use_nodes=True
floor=cube('floor',(12,22,4.9),(4,4,.2),paint)
walls=[cube('wall-'+str(i),c,s,paint) for i,(c,s) in enumerate([
 ((10,22,6.4),(.2,4,2.8)),((14,22,6.4),(.2,4,2.8)),((12,20,6.4),(4,.2,2.8)),((12,24,6.4),(4,.2,2.8))])]
bpy.context.view_layer.update()
by_id={o.get('studio_id'):o for o in [floor,*walls]}
design=dict(groups=[dict(id='floor',name='floor',method='structural_floor',children=['floor']),dict(id='walls',name='walls',method='structural_wall',children=list(by_id)[1:])],objects=[dict(id=k) for k in by_id])
lamp=cube('unrelated pendant',(12.667,21.333,7.6),(1,1,.1),paint);design['groups'].append(dict(id='pendant',name='Pendant',children=['unrelated pendant'],asset_requirements=dict(purpose='light')));bpy.context.view_layer.update()
opts=ceiling_options(design,by_id);assert len(opts['options'])==1 and opts['options'][0]['height']==7.8
original={k:([tuple(v.co) for v in o.data.vertices],list(o.matrix_world)) for k,o in by_id.items()}
design['ceiling_infill']=['floor'];added=add_ceilings(design,by_id);assert added and added[0]['height']==7.8
assert original=={k:([tuple(v.co) for v in o.data.vertices],list(o.matrix_world)) for k,o in by_id.items()}
assert not ceiling_options(design,by_id)['options'] # never stack over an existing ceiling
for obj in bpy.data.objects:
 if obj.get('studio_ceiling_infill'):obj.location.z=-.4
bpy.context.view_layer.update()
assert not ceiling_options(design,by_id)['options'] # lowered ceilings also block infill
for obj in list(bpy.data.objects):
 if obj.get('studio_ceiling_infill'):bpy.data.objects.remove(obj,do_unlink=True)
bpy.context.view_layer.update()
# A concave footprint must not be replaced with its rectangular bounding box.
mesh=bpy.data.meshes.new('L footprint')
world=[(10,20,5),(14,20,5),(14,22,5),(12,22,5),(12,24,5),(10,24,5)]
mesh.from_pydata([floor.matrix_world.inverted()@Vector(p) for p in world],[],[tuple(range(6))]);mesh.update();floor.data=mesh;bpy.context.view_layer.update()
assert ceiling_options(design,by_id)['options']
add_ceilings(design,by_id)
assert not bpy.context.scene.ray_cast(bpy.context.evaluated_depsgraph_get(),Vector((13,23,7.7)),Vector((0,0,1)),distance=.2)[0]
for obj in list(bpy.data.objects):
 if obj.get('studio_ceiling_infill'):bpy.data.objects.remove(obj,do_unlink=True)
bpy.context.view_layer.update();floor.name='Courtyard floor' 
assert not ceiling_options(design,by_id)['options']
floor.name='floor';walls[0].hide_render=True;walls[0].hide_set(True);walls[1].hide_render=True;walls[1].hide_set(True);bpy.context.view_layer.update()
assert not ceiling_options(design,by_id)['options']
print('REALISM_CEILING_SAFETY_PASSED')

from realism_shelf import apply_shelves,eligible_box
bpy.ops.wm.read_factory_settings(use_empty=True)
paint=bpy.data.materials.new('shelf paint');paint.use_nodes=True
unit=cube('new equipment',(7,9,2),(1.2,.55,2.1),paint)
unit.rotation_euler.z=.6;bpy.context.view_layer.update()
before=[tuple(v.co) for v in unit.data.vertices];matrix=unit.matrix_world.copy()
design=dict(groups=[dict(id='new-unit',children=['new equipment'])],shelf_refinements=[dict(object_id='new equipment',front='-Y',evidence='New equipment is an open shelf per user record')])
assert eligible_box(unit)
report=apply_shelves(design,{'new equipment':unit})
assert report[0]['envelope_preserved'] and report[0]['parts']==8
assert unit.hide_render and matrix==unit.matrix_world and before==[tuple(v.co) for v in unit.data.vertices]
unit.data.vertices[0].co.x+=.1
assert not eligible_box(unit)
print('REALISM_SHELF_ENVELOPE_PASSED')

# Another orientation and non-origin location: content stays in the envelope and
# the viewer snapshot contains actual geometry, not the hidden solid placeholder.
from realism_preview import export_snapshot
import tempfile,json
unit.data.vertices[0].co.x-=.1
design['shelf_refinements'][0]['contents']=['microwave','coffee_machine','magazines']
design['groups'][0].update(name='Equipment',translation=[1,2,0],rotation=35,deleted=False)
design.update(objects=[dict(id='new equipment',name='Equipment',material={})],concept_furniture=[])
report=apply_shelves(design,{'new equipment':unit})
assert {c['kind'] for c in report[0]['contents'] if c['status']=='placed'}=={'microwave','coffee_machine','magazines'}
with tempfile.TemporaryDirectory() as directory:
    from pathlib import Path
    output=Path(directory);export_snapshot(design,output)
    packet=json.loads((output/'preview-scene.json').read_text())
    assert (output/'refined-preview.glb').stat().st_size>1000
    assert not packet['concept_furniture']
    assert all(g['translation']==[0,0,0] and g['rotation']==0 for g in packet['groups'])
    assert 'new equipment' not in {c for g in packet['groups'] for c in g['children']}
    assert len([o for o in packet['objects']])>20
print('REALISM_CONTENT_PREVIEW_PASSED')

from realism_assets import place
import hashlib
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'synthetic-machine.blend'
    machine=cube('synthetic coffee',(0,0,.15),(.2,.25,.3),paint)
    bpy.context.view_layer.update();bpy.data.libraries.write(str(path),{machine})
    asset=dict(file=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),front='-Y',source_url='https://example.invalid/fixture',license='synthetic')
    lo=Vector([min(v.co[i] for v in unit.data.vertices) for i in range(3)]);hi=Vector([max(v.co[i] for v in unit.data.vertices) for i in range(3)])
    parts=[];placed=place(asset,'coffee_machine',unit,lo,hi,[.02]*3,0,1,'+Y',2,parts)
    assert placed['scale']==1 and placed['source']=='registered_native_asset' and len(parts)==1
    inverse=unit.matrix_world.inverted();bpy.context.view_layer.update()
    assert all(all(lo[i]-1e-4<=(inverse@p.matrix_world@Vector(c))[i]<=hi[i]+1e-4 for i in range(3)) for p in parts for c in p.bound_box)
    # New catalog appliances may not be squeezed to fit an undersized shelf.
    strict_asset=dict(asset,min_scale=.999)
    before_objects=set(bpy.data.objects);rejected=[]
    try:place(strict_asset,'coffee_machine',unit,lo,lo+Vector((.1,.1,.1)),[.02]*3,0,1,'+Y',0,rejected)
    except ValueError as exc:assert '低於允許' in str(exc)
    else:raise AssertionError('Catalog appliance shrunk instead of trying another candidate')
    assert not rejected and set(bpy.data.objects)==before_objects
    paper=bpy.data.materials.new('Pages missing image');paper.use_nodes=True
    empty=paper.node_tree.nodes.new('ShaderNodeTexImage');paper.node_tree.links.new(empty.outputs['Color'],paper.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
    machine.data.materials.clear();machine.data.materials.append(paper)
    damaged=Path(directory)/'synthetic-paper.blend';bpy.data.libraries.write(str(damaged),{machine})
    page_asset=dict(asset,file=str(damaged),sha256=hashlib.sha256(damaged.read_bytes()).hexdigest())
    repaired=place(page_asset,'magazines',unit,lo,hi,[.02]*3,0,1,'+Y',0,[])
    assert repaired['material_repairs'] and empty.image is None and paper.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].is_linked
    try:place(page_asset,'coffee_machine',unit,lo,hi,[.02]*3,0,1,'+Y',0,[])
    except ValueError:pass
    else:raise AssertionError('Unknown missing material silently repaired')
    asset['sha256']='0'*64
    try:place(asset,'coffee_machine',unit,lo,hi,[.02]*3,0,1,'+Y',2,[])
    except ValueError:pass
    else:raise AssertionError('changed source accepted')
print('REALISM_NATIVE_CONTENT_PASSED')

# A coffee table below eye level must not remove an otherwise clear viewpoint.
from realism_framing import floor_below
bpy.ops.wm.read_factory_settings(use_empty=True)
paint=bpy.data.materials.new('fixture paint');paint.use_nodes=True
floor=cube('structural floor',(12,9,-.1),(4,4,.2),paint)
table=cube('low table',(12,9,.5),(.8,.8,.1),paint)
bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
ground=floor_below(bpy.context.scene,deps,Vector((12,9,1.6)),[floor])
assert ground is not None and abs(ground.z)<1e-5
assert floor_below(bpy.context.scene,deps,Vector((30,30,1.6)),[floor]) is None
assert not bpy.context.scene.ray_cast(deps,Vector((12,9,1.6)),Vector((1,0,0)),distance=.15)[0]
print('REALISM_FLOOR_BELOW_FURNITURE_PASSED')
from realism_framing import centered_shift
forward=Vector((1,0,0));up=Vector((0,0,1))
corners=[Vector((2,-.5,-1)),Vector((2,.5,.1))]
shift=centered_shift(corners,forward,up,28)
assert -.3<=shift<=.3
low=min(v.dot(up)/v.dot(forward)-shift*36/28 for v in corners)
high=max(v.dot(up)/v.dot(forward)-shift*36/28 for v in corners)
assert abs(low+high)<.0002
assert centered_shift([Vector((1,0,-10))],forward,up,35)==-.3
print('REALISM_SUBJECT_CENTERED_SENSOR_PASSED')

# Unrelated room/location: preserve only windows actually visible in this shot.
from realism_framing import window_anchors,in_frame
bpy.ops.wm.read_factory_settings(use_empty=True)
paint=bpy.data.materials.new('neutral');paint.use_nodes=True
shot=dict(yaw=0,pitch=0,lens=28,shift_y=0,aspect='4:3')
eye=Vector((12,9,1.5));window=dict(id='east-window',center=[15,9,1.5],axis=0,sign=1,width=1,height=1)
bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
anchors=window_anchors(bpy.context.scene,deps,eye,shot,[window])
assert len(anchors)==1 and len(anchors[0]['points'])==9
assert not window_anchors(bpy.context.scene,deps,eye,dict(shot,yaw=90),[window])
assert not in_frame(Vector((15,9,2.6)),eye,dict(shot,aspect='16:9'))
assert in_frame(Vector((15,9,2.6)),eye,shot)
cube('partition',(13.5,9,1.5),(.1,2,2),paint);bpy.context.view_layer.update()
assert not window_anchors(bpy.context.scene,bpy.context.evaluated_depsgraph_get(),eye,shot,[window])
print('REALISM_VISIBLE_WINDOW_PRESERVATION_PASSED')

# Scalar extrema must retain the exact full-vertex frustum test.
from realism_framing import sensor_fit
import random
random.seed(610)
for _ in range(100):
    scale=random.uniform(.05,1.1);offset=random.uniform(-.2,.2)
    points=[(random.uniform(-scale,scale),random.uniform(-scale,scale)+offset) for _ in range(25)]
    horizontal=max(abs(x) for x,y in points);lower=min(y for x,y in points);upper=max(y for x,y in points)
    for lens in (20,24,28,32,35):
        for half_height in (10.125,13.5):
            for shift in (-.3,-.12,0,.06):
                exact=all(abs(x)<18/lens*.92 and abs(y-shift*36/lens)<half_height/lens*.92 for x,y in points)
                assert sensor_fit(horizontal,lower,upper,lens,half_height,shift)==exact
print('REALISM_FRUSTUM_INTERVAL_EQUIVALENCE_PASSED')


from realism_framing import actual_frame_integrity
bpy.ops.wm.read_factory_settings(use_empty=True)
paint=bpy.data.materials.new('neutral');paint.use_nodes=True
obj=cube('independent table',(15,9,1.0),(1.0,.8,.7),paint)
bpy.context.view_layer.update()
design={'groups':[{'id':'table-group','name':'test table','children':['part'],'object_specification':{'purpose':'table'}}]}
point={'id':'test-point','eye':[12,9,1.5],'shots':[dict(shot,id='front')]}
record=actual_frame_integrity(design,point,{'part':obj})[0]
assert record['all_vertices_inside'] and all(0<v<1 for v in record['bounds_uv'])
design['groups'][0]['object_specification']['purpose']='coffee_table'
assert actual_frame_integrity(design,point,{'part':obj})[0]['all_vertices_inside']
obj.location.y=10.8;bpy.context.view_layer.update()
clipped=actual_frame_integrity(design,point,{'part':obj})[0]
assert not clipped['all_vertices_inside'] and (clipped['bounds_uv'][0]<0 or clipped['bounds_uv'][2]>1)
print('REALISM_ACTUAL_FURNITURE_FRAME_EVIDENCE_PASSED')
