"""Native synthetic material/leaf replacement, no catalog account needed."""
import sys,json
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src/interior/visualization'))
from opening_details import assembly
folder=Path(sys.argv[sys.argv.index('--')+1]);folder.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
mat=bpy.data.materials.new('Synthetic oak');mat.use_nodes=True;mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.2,.08,.025,1)
bpy.data.libraries.write(str(folder/'wood.blend'),{mat})
bpy.ops.mesh.primitive_cube_add(size=1);leaf=bpy.context.object;leaf.name='Panel';leaf.scale=(.8,.035,2);leaf.data.materials.append(mat)
bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
bpy.data.libraries.write(str(folder/'leaf.blend'),{leaf})
bpy.data.objects.remove(leaf,do_unlink=True)
item=dict(id='door-test',name='Test door',points=[[0,0],[.9,0]],height=2.1,base=0,role='door',control=dict(kind='single',side='positive',swing='positive',hinge='A',_asset_files={'frame':dict(path=str(folder/'wood.blend'),kind='material'),'leaf-0':dict(path=str(folder/'leaf.blend'),kind='model')}))
report=assembly(item,'a'*64)
assert report['opening']['state']=='open',report
assert report['width']==.9 and report['height']==2.1
assert all(len(p['vertices'])==8 for p in report['preview_parts'])
objects=[o for o in bpy.context.scene.objects if o.get('doorId')]
assert len(objects)>=5
assert all(o.data.materials for o in objects)
leaf=next(o for o in objects if o.get('doorPart')=='leaf-0')
assert len(leaf.data.vertices)==8
bpy.ops.object.select_all(action='DESELECT')
for o in objects:o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(folder/'doors.glb'),export_format='GLB',use_selection=True,export_extras=True)
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'result.blend'))
(folder/'report.json').write_text(json.dumps(report),encoding='utf-8')
print('DOOR_ASSET_NATIVE_PASS')
