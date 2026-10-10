"""Generate an original synthetic GLB; run with Blender 4.5, never uses customer assets."""
from pathlib import Path
import json
import hashlib
import bpy

folder=Path(__file__).resolve().parent
bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name,color,roughness=.55):
    mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
    node=mat.node_tree.nodes.get('Principled BSDF')
    node.inputs['Base Color'].default_value=(*color,1);node.inputs['Roughness'].default_value=roughness
    return mat


wall=material('Warm white',(.72,.69,.62))
wood=material('Oak color',(.45,.26,.11))
fabric=material('Sage fabric',(.22,.35,.29))
dark=material('Graphite',(.08,.09,.1))
floor=material('Light floor',(.58,.48,.35))


def box(name,location,size,mat):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location)
    obj=bpy.context.object;obj.name=name;obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.data.materials.append(mat)
    obj['assembly_id']=name.split('__')[0]
    bevel=obj.modifiers.new('Soft edges','BEVEL');bevel.width=.025;bevel.segments=2
    return obj


box('floor',(3,2,-.1),(6.2,4.2,.2),floor)
box('wall-north',(3,4,1.4),(6.2,.16,2.8),wall)
box('wall-west',(0,2,1.4),(.16,4,2.8),wall)
box('wall-east',(6,2,1.4),(.16,4,2.8),wall)
# Entrance opening: deliberately model a real gap, not a black panel.
box('wall-south-left',(1,0,1.4),(2,.16,2.8),wall)
box('wall-south-right',(4.5,0,1.4),(3,.16,2.8),wall)
box('entrance-lintel',(2.5,0,2.55),(1,.16,.5),wall)
ceiling=box('ceiling',(3,2,2.9),(6.2,4.2,.2),wall)
box('sofa__seat',(1,2.8,.43),(1.5,.8,.38),fabric)
box('sofa__back',(1,3.18,.83),(1.5,.2,.8),fabric)
box('coffee-table__top',(1.25,1.6,.5),(1.15,.65,.09),wood)
for x in [.8,1.7]:
    for y in [1.38,1.82]:box(f'coffee-table__leg-{x}-{y}',(x,y,.25),(.06,.06,.5),dark)
box('dining-table__top',(4.15,2,.78),(1.4,.9,.12),wood)
for x in [3.6,4.7]:
    for y in [1.7,2.3]:box(f'dining-table__leg-{x}-{y}',(x,y,.37),(.07,.07,.74),dark)
for number,y in [(1,1.15),(2,2.85)]:
    box(f'chair-{number}__seat',(4.15,y,.48),(.5,.5,.1),fabric)
    back_y=y+(-.22 if number==1 else .22)
    box(f'chair-{number}__back',(4.15,back_y,.78),(.5,.07,.6),wood)
    for x in [3.95,4.35]:
        for leg_y in [y-.2,y+.2]:box(f'chair-{number}__leg-{x}-{leg_y}',(x,leg_y,.23),(.05,.05,.46),wood)
box('kitchen-counter',(5.5,3.1,.5),(.8,1.4,1),wall)
for number,x in [(1,1.4),(2,4.4)]:
    box(f'ceiling-fixture-{number}',(x,2.2,2.65),(.45,.45,.09),wall)
    data=bpy.data.lights.new(f'Room light {number}','POINT');data.energy=220;data.color=(1,.88,.72);data.shadow_soft_size=.3
    obj=bpy.data.objects.new(data.name,data);bpy.context.collection.objects.link(obj);obj.location=(x,2.2,2.35)
bpy.context.view_layer.update()
bpy.ops.export_scene.gltf(filepath=str(folder/'demo-apartment.glb'),export_format='GLB',export_extras=True,export_lights=True)

# A real top-down view of the same generated geometry; illustration only, not an input converter.
ceiling.hide_render=True
camera_data=bpy.data.cameras.new('Plan');camera=bpy.data.objects.new('Plan',camera_data);bpy.context.collection.objects.link(camera)
camera.location=(3,2,12);camera.rotation_euler=(0,0,0);camera_data.type='ORTHO';camera_data.ortho_scale=7
scene=bpy.context.scene;scene.camera=camera;scene.render.engine='BLENDER_WORKBENCH'
scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL';scene.display.shading.show_shadows=True
scene.render.resolution_x=960;scene.render.resolution_y=720;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(folder/'layout.png');bpy.ops.render.render(write_still=True)
manifest={
    'name':'Demo apartment','kind':'synthetic','license':'MIT','units':'metres',
    'source':'build_example.py; original primitive geometry, no external models or textures',
    'floor_size':[6,4],'height':2.8,
    'suggested_viewpoints':[
        {'name':'Living','eye':[2.5,1.1,1.6],'yaw':135,'pitch':0,'lens':24},
        {'name':'Dining','eye':[3.1,2.2,1.6],'yaw':0,'pitch':0,'lens':24}
    ],
    'sha256':{name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ['demo-apartment.glb','layout.png']}
}
(folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
