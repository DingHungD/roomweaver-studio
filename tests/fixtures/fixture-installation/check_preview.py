import sys,json,struct
from pathlib import Path
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy
from preview_emission import compatible_emission,material_overrides
output=Path(sys.argv[-1]);output.mkdir(exist_ok=True,parents=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object
material=bpy.data.materials.new('Imported light output');material.use_nodes=True
nodes=material.node_tree.nodes;nodes.clear()
light=nodes.new('ShaderNodeOutputLight');emission=nodes.new('ShaderNodeEmission')
emission.inputs['Color'].default_value=(1,.8,.6,1);emission.inputs['Strength'].default_value=15
material.node_tree.links.new(emission.outputs[0],light.inputs['Surface']);obj.data.materials.append(material)
from surface_uv import preview_tile
same,report=preview_tile(material,output)
assert same==material and report['mode']=='native_emission_export_adapter'
shell=bpy.data.materials.new('Shell');shell.use_nodes=True;obj.data.materials.append(shell)
for p in obj.data.polygons:p.material_index=0 if p.normal.z>.9 else 1
indices=[p.material_index for p in obj.data.polygons]
preview_shell=shell.copy()
count=len(bpy.data.materials)
with material_overrides([(obj,[material,shell],[material,preview_shell])]):
    with compatible_emission([obj]) as converted:
        assert converted==[material.name]
        bpy.ops.export_scene.gltf(filepath=str(output/'fixture.glb'),export_format='GLB')
assert obj.data.materials[0]==material and len(bpy.data.materials)==count
assert obj.data.materials[1]==shell and [p.material_index for p in obj.data.polygons]==indices
assert not any(n.type=='OUTPUT_MATERIAL' for n in material.node_tree.nodes)
raw=(output/'fixture.glb').read_bytes();length=struct.unpack_from('<I',raw,12)[0];gltf=json.loads(raw[20:20+length])
assert any(sum(m.get('emissiveFactor',[0,0,0]))>0 for m in gltf['materials']),gltf['materials']
assert len(gltf['meshes'][0]['primitives'])==2,'The emitting face and shell must remain separate'
try:
    with material_overrides([(obj,[material,shell],[material,preview_shell])]):
        with compatible_emission([obj]):raise RuntimeError('export failed')
except RuntimeError:pass
assert obj.data.materials[0]==material and len(bpy.data.materials)==count
assert obj.data.materials[1]==shell and [p.material_index for p in obj.data.polygons]==indices
print('FIXTURE_PREVIEW_EMISSION_PASSED')
