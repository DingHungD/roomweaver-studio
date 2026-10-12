"""Blender-only synthetic living/dining room; no customer data or downloaded assets."""
import bpy,sys,json,hashlib
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
out=Path(sys.argv[sys.argv.index('--')+1]).resolve();out.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def box(name,source,size,location,color):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location)
    obj=bpy.context.object;obj.name=name;obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj['studio_id']=uuid5(NAMESPACE_URL,name).hex;obj['source_id']=source
    mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
    mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*color,1)
    obj.data.materials.append(mat)
box('Living floor','floor',[5,4,.1],[2.5,2,-.05],[.55,.42,.3])
box('North wall','wall',[5,.12,2.7],[2.5,4,1.35],[.8,.79,.75])
box('Dining table top','table',[1.4,.8,.06],[2.5,2,.72],[.55,.38,.22])
for i,x in enumerate((1.9,3.1)):
    for j,y in enumerate((1.7,2.3)):box(f'Dining table leg {i}{j}','table',[.06,.06,.69],[x,y,.345],[.4,.3,.2])
box('Sofa seat','sofa',[1.8,.8,.35],[1.4,3.2,.3],[.2,.3,.4])
box('Sofa back','sofa',[1.8,.15,.65],[1.4,3.55,.55],[.2,.3,.4])
bpy.context.scene.world.color=(.15,.15,.15)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'model.blend'))
bpy.ops.export_scene.gltf(filepath=str(out/'model.glb'),export_format='GLB',export_extras=True,export_apply=True)
manifest=dict(name='New home｜照明與裝飾通用流程實測',native='model.blend',preview='model.glb',suggested_viewpoints=[dict(name='Living',eye=[4,.8,1.6],yaw=130,pitch=0,lens=28)],sha256={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ('model.blend','model.glb')})
(out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
