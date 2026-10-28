"""Small anonymous fitting for real Blender and optional live Agent checks."""
import json
from pathlib import Path
import sys
import bpy

output=Path(sys.argv[sys.argv.index('--')+1]).resolve();output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
def material(name,color):
    mat=bpy.data.materials.new(name);mat.use_nodes=True;mat.diffuse_color=(*color,1)
    mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(*color,1)
    return mat
metal=material('dark metal housing',(.05,.05,.06));white=material('frosted diffuser',(.9,.9,.88))
wood=material('table wood',(.4,.2,.1))
objects=[]
def obj(identifier,mat):
    o=bpy.context.object;o.name=identifier;o['studio_id']=identifier;o.data.materials.append(mat)
    objects.append(dict(id=identifier,name=identifier,room_id='room',material={}))
    return o
# A cup with an open bottom: the actual entry hit is the diffuser, not an enclosing solid cylinder.
bpy.ops.mesh.primitive_torus_add(major_radius=.19,minor_radius=.035,major_segments=48,minor_segments=12,location=(1,2,2.7))
obj('part-01',metal)
bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=.16,depth=.018,location=(1,2,2.7))
obj('part-02',white)
for name,loc,size in [('part-03',(0,0,.75),(1.2,.7,.08)),('part-04',(-.5,0,.35),(.08,.08,.7)),('part-05',(.5,0,.35),(.08,.08,.7))]:
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=obj(name,wood);o.scale=size
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(output/'source.blend'))
scene=dict(model_id='a'*32,rooms=[dict(id='room',name='Synthetic room')],objects=objects,
    groups=[dict(id='anonymous-01',name='Component 23',children=['part-01','part-02'],translation=[3,-2,.2],rotation=90,rotation_pivot=[1,2,0],deleted=False),
            dict(id='table',name='Component 24',children=['part-03','part-04','part-05'],translation=[0,0,0],deleted=False)],
    viewpoints=[],links=[],lighting='existing',lighting_setup=dict(enabled=True,mode='existing',exposure=.2,auto_adjust=False,agent_review=False,
        lights=[dict(id='manual-locked',name='Locked manual',kind='POINT',position=[9,9,2],rotation=[0,0,0],power=10,color=[1,1,1],size=.1,angle=90,enabled=False,locked=True,group_id=None,origin='manual')]))
(output/'scene.json').write_text(json.dumps(scene),encoding='utf-8')
