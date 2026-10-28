"""CLI-only GLB readback and editable, texture-packed BLEND export."""
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector

folder=Path(sys.argv[sys.argv.index('--')+1]).resolve()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(folder/'model.glb'))
bpy.context.view_layer.update()
meshes=[o for o in bpy.data.objects if o.type=='MESH']
if not meshes:raise ValueError('轉檔模型沒有網格')
corners=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
report=dict(mesh_objects=len(meshes),materials=len(bpy.data.materials),images=len(bpy.data.images),
            bounds_z_up_m=dict(min=[min(p[k] for p in corners) for k in range(3)],max=[max(p[k] for p in corners) for k in range(3)]))
bpy.context.scene.unit_settings.system='METRIC'
bpy.context.scene.unit_settings.scale_length=1
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'model.blend'))
(folder/'blender-readback.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
