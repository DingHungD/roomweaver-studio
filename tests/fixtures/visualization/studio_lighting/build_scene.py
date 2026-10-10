"""Create small synthetic lighting counterexamples; no case assets."""
import bpy,json,sys
from pathlib import Path

root=Path(sys.argv[sys.argv.index('--')+1]);root.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
objects=[]
for name,loc,size in [('floor',(0,0,-.1),(6,6,.2)),('ceiling',(0,0,3.1),(6,6,.2)),
    ('north',(0,3,1.5),(6,.2,3)),('south',(0,-3,1.5),(6,.2,3)),('east',(3,0,1.5),(.2,6,3)),('west',(-3,0,1.5),(.2,6,3)),('table',(0,.6,.5),(1,1,1))]:
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc)
    obj=bpy.context.object;obj.name=name;obj.scale=size;obj['studio_id']=name
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.5,.4,.3,1)
    obj.data.materials.append(mat)
    objects.append(dict(id=name,name=name,room_id='room',material=dict(color=None,roughness=.5)))
bpy.ops.wm.save_as_mainfile(filepath=str(root/'dark.blend'))
data=bpy.data.lights.new('Light','AREA');data.energy=700;data.shape='DISK';data.size=2
lamp=bpy.data.objects.new('Light',data);scene.collection.objects.link(lamp);lamp.location=(0,0,2.8)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'lit.blend'))
bpy.ops.export_scene.gltf(filepath=str(root/'display.glb'),export_format='GLB',export_extras=True,export_lights=False)
lamp.hide_render=True
bpy.ops.wm.save_as_mainfile(filepath=str(root/'hidden.blend'))
lamp.hide_render=False;lamp.location=(0,0,5)  # Outside sealed room: presence is insufficient.
bpy.ops.wm.save_as_mainfile(filepath=str(root/'occluded.blend'))
data.use_nodes=True
bpy.ops.wm.save_as_mainfile(filepath=str(root/'custom-light.blend'))
(root/'scene.json').write_text(json.dumps(dict(model_id='a'*32,rooms=[dict(id='room',name='Synthetic')],objects=objects,groups=[],lighting='existing',links=[],viewpoints=[dict(id='one',name='One',room_id='room',eye=[0,-1,1.5],shots=[dict(id='front',name='Front',yaw=90,pitch=0,lens=24)])])),encoding='utf-8')
