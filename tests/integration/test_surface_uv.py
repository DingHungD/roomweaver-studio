"""Synthetic procedural surfaces: physical UV continuity and evaluated colour."""
import json
import subprocess
from pathlib import Path
from interior.workbench.studio.engine import blender_executable

def test_procedural_surface_tile_and_black_rejection(tmp_path):
    source=Path(__file__).resolve().parents[2]/'src/interior/visualization'
    script=tmp_path/'check.py'
    script.write_text('''import bpy,sys,json
from pathlib import Path
sys.path.insert(0,SOURCE)
from surface_uv import ensure_uv,preview_tile
bpy.ops.wm.read_factory_settings(use_empty=True)
material=bpy.data.materials.new('Synthetic warm oak');material.use_nodes=True
nodes=material.node_tree.nodes
shader=nodes.get('Principled BSDF')
noise=nodes.new('ShaderNodeTexChecker')
noise.inputs['Color1'].default_value=(.2,.1,.04,1)
noise.inputs['Color2'].default_value=(.5,.3,.15,1)
material.node_tree.links.new(noise.outputs['Color'],shader.inputs['Base Color'])
floors=[]
for x in (0,1):
 bpy.ops.mesh.primitive_plane_add(size=1,location=(x,0,0))
 obj=bpy.context.object;obj.data.materials.append(material)
 for uv in list(obj.data.uv_layers):obj.data.uv_layers.remove(uv)
 before=[tuple(v.co) for v in obj.data.vertices]
 assert ensure_uv(obj)=='generated_metres'
 assert before==[tuple(v.co) for v in obj.data.vertices]
 assert ensure_uv(obj)=='preserved'
 floors.append(obj)
assert max(u.uv.x for u in floors[0].data.uv_layers.active.data)==min(u.uv.x for u in floors[1].data.uv_layers.active.data)
original=len(material.node_tree.nodes)
preview,report=preview_tile(material,Path(OUTPUT))
assert report['mean_linear']>.01 and preview!=material and len(material.node_tree.nodes)==original
assert all(o.data.materials[0]==material for o in floors)
assert report['roughness_baked'] and Path(OUTPUT,'surface-roughness.png').is_file()
assert report['normal_baked'] and report['metallic_baked']
assert report['channel_means']['Metallic']<.001
assert Path(OUTPUT,'surface-normal.png').is_file()
assert preview.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].is_linked
material.node_tree.links.remove(shader.inputs['Base Color'].links[0]);shader.inputs['Base Color'].default_value=(0,0,0,1)
try:preview_tile(material,Path(OUTPUT))
except ValueError as e:assert '全黑' in str(e)
else:raise AssertionError('black material was accepted')
Path(OUTPUT,'verified.json').write_text(json.dumps(report))
'''.replace('SOURCE',repr(str(source))).replace('OUTPUT',repr(str(tmp_path))),encoding='utf-8')
    result=subprocess.run([blender_executable(),'--background','--disable-autoexec','--python-exit-code','1','--python',str(script)],capture_output=True,text=True,encoding='utf-8',timeout=120)
    assert result.returncode==0,result.stdout[-5000:]+result.stderr
    assert json.loads((tmp_path/'verified.json').read_text())['native_shader_preserved']
