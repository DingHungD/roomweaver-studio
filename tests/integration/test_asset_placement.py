"""Real Blender measurement respects scene edits and moves only revision intent."""
import json
import subprocess
from pathlib import Path
from interior.workbench.studio.engine import blender_executable

def test_edited_scene_local_placement(tmp_path):
    source=Path(__file__).resolve().parents[2]/'src/interior/visualization'
    script=tmp_path/'placement.py'
    script.write_text('''import bpy,sys,json
from pathlib import Path
sys.path.insert(0,SOURCE)
from asset_collision import check_placement
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=1,location=(.5,.5,.5))
furniture=bpy.context.object;furniture['studio_id']='chair'
bpy.ops.mesh.primitive_cube_add(size=1,location=(1.1,.5,1))
wall=bpy.context.object;wall.scale=(.3,1,2);wall['studio_id']='wall'
group=dict(id='seat',name='Seat',children=['old'],translation=[2,3,0],rotation=0,placement_constraints=dict(area=[1.6,2.6,3.3,4.3],max_distance=.3,keep_out=[]))
fixed=dict(id='wall',name='Fixed wall',children=['wall'],translation=[2,3,0])
design=dict(groups=[group,fixed])
bpy.context.view_layer.update()
before_wall=[list(r) for r in wall.matrix_world];before_furniture=[list(r) for r in furniture.matrix_world]
r=check_placement(design,group,[furniture])
assert r['status']=='moved' and abs(group['translation'][0]-1.95)<1e-6
assert before_wall==[list(r) for r in wall.matrix_world]
assert before_furniture==[list(r) for r in furniture.matrix_world]
assert group['translation'][2]==0 and fixed['translation']==[2,3,0]
assert check_placement(design,group,[furniture])['status']=='clear'
Path(OUTPUT,'verified.json').write_text(json.dumps(r))
'''.replace('SOURCE',repr(str(source))).replace('OUTPUT',repr(str(tmp_path))),encoding='utf-8')
    result=subprocess.run([blender_executable(),'--background','--disable-autoexec','--python-exit-code','1','--python',str(script)],capture_output=True,text=True,encoding='utf-8',timeout=90)
    assert result.returncode==0,result.stdout[-4000:]+result.stderr
    assert json.loads((tmp_path/'verified.json').read_text())['status']=='moved'
