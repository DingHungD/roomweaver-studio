"""Real Blender replacement checks across four synthetic furniture types."""
import sys,json,hashlib
from pathlib import Path
import bpy
args=sys.argv[sys.argv.index('--')+1:];sys.path.insert(0,args[0]);output=Path(args[1])
from asset_blender import replace_asset,signature
for kind,size in [('chair',[.5,.5,.85]),('bed',[2,1.5,.55]),('desk',[1.2,.6,.75]),('cabinet',[.8,.5,1.2])]:
    bpy.ops.wm.read_factory_settings(use_empty=True);folder=output/kind;folder.mkdir(parents=True)
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,-.06));floor=bpy.context.object;floor.dimensions=(8,8,.1)
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);floor['studio_id']='floor';before=signature(floor)
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,size[2]/2));old=bpy.context.object;old.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);old['studio_id']='target'
    design=dict(groups=[dict(id='floor',name='floor',children=['floor'],deleted=False,method='structural_floor'),dict(id='target',name=kind,children=['target'],deleted=False,translation=[.5,-.4,0],rotation=20)],objects=[dict(id='floor',name='floor',room_id=None,material={}),dict(id='target',name=kind,room_id=None,material={})])
    native=folder/'source.blend';bpy.ops.wm.save_as_mainfile(filepath=str(native));digest=hashlib.sha256(native.read_bytes()).hexdigest()
    request=dict(design=design,asset=dict(kind='generated',recipe=dict(purpose=kind,dimensions=size,version=2,design={})),target_group='target',output=str(folder),model_id='123456789abcdef0'*2,task_id='b'*32,preview=str(folder/'model.glb'),auto_fit=True,asset_requirements=dict(purpose=kind,dimension_source='confirmed',dimensions=size,evidence='synthetic confirmed plan'))
    replace_asset(request)
    report=json.loads((folder/'replacement-report.json').read_text(encoding='utf-8'))
    assert report['model_check']['status']=='passed' and report['model_check']['faces']>6
    assert all(abs(a-b)<.002 for a,b in zip(size,report['resulting_dimensions'])),report
    assert report['visual_review']['context_group_ids']==['floor']
    assert len(report['visual_review']['images'])==3
    for name in report['visual_review']['images']:assert (folder/name).stat().st_size>2000
    assert signature(floor)==before and hashlib.sha256(native.read_bytes()).hexdigest()==digest
print('FURNITURE_REVIEW_PASSED')
