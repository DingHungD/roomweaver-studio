import sys,json,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import bpy
from mathutils import Vector,Matrix
from opening_details import add_openings
from concept_geometry import add_blender_furniture
source_path,target_path=sys.argv[sys.argv.index('--')+1:]
packet=json.loads(Path(source_path).read_text(encoding='utf-8'))
bpy.ops.wm.open_mainfile(filepath=packet['blend'])
design=packet['scene'];add_blender_furniture(design.get('concept_furniture',[]))
by_id={o.get('studio_id'):o for o in bpy.data.objects if o.type in ('MESH','CURVE')}
for g in design['groups']:
 pivot=Vector(g.get('rotation_pivot',[0,0,0]));delta=Vector(g['translation']);change=Matrix.Translation(delta+pivot)@Matrix.Rotation(math.radians(g.get('rotation',0)),4,'Z')@Matrix.Translation(-pivot)
 for key in g['children']:
  o=by_id[key];o.matrix_world=change@o.matrix_world
  if g['deleted']:o.hide_render=True;o.hide_set(True)
bpy.context.view_layer.update()
source=packet['source']
report=add_openings(design,by_id,source)
if any(c.get('_asset_files') for c in design.get('door_controls',[])):
 bpy.ops.object.select_all(action='DESELECT')
 for obj in bpy.context.scene.objects:
  if obj.get('doorId') and not obj.hide_render:obj.select_set(True)
 from surface_uv import preview_tile
 cache={};restore=[]
 for obj in bpy.context.selected_objects:
  if obj.type!='MESH':continue
  original=list(obj.data.materials);restore.append((obj,original))
  for index,mat in enumerate(original):
   if not mat:continue
   if mat.name not in cache:
    tile_dir=Path(target_path).parent/('material-'+str(len(cache)));tile_dir.mkdir(exist_ok=True)
    cache[mat.name]=preview_tile(mat,tile_dir)[0]
   obj.data.materials[index]=cache[mat.name]
 bpy.ops.export_scene.gltf(filepath=str(Path(target_path).with_name('doors.glb')),export_format='GLB',use_selection=True,export_extras=True,export_apply=True,export_cameras=False,export_lights=False)
Path(target_path).write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
