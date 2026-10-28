"""Synthetic furniture geometry only; executable exclusively by the integration test."""
import sys,json,hashlib
from pathlib import Path
import bpy
args=sys.argv[sys.argv.index('--')+1:];sys.path.insert(0,args[0]);output=Path(args[1])
from asset_blender import replace_asset,signature
from decor_review import support_check
for n,(kind,size) in enumerate((('vase',[.18,.18,.30]),('books',[.24,.18,.08]),('tableware',[.22,.22,.1]))):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    folder=output/kind;folder.mkdir()
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,.7+n*.1));support=bpy.context.object
    support.dimensions=(1,1,.05);bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);support['studio_id']='support';support.name='Synthetic desk sink table'
    bpy.ops.mesh.primitive_cube_add(size=1,location=(.47,0,1));rail=bpy.context.object;rail.dimensions=(.04,1,.7)
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    bpy.ops.object.select_all(action='DESELECT');support.select_set(True);rail.select_set(True);bpy.context.view_layer.objects.active=support;bpy.ops.object.join()
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,size[2]/2));old=bpy.context.object
    old.dimensions=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);old['studio_id']='decor'
    before=signature(support)
    scene=dict(groups=[dict(id='support',name='support',children=['support'],translation=[2,-3,0],rotation=30,deleted=False),dict(id='decor',name='decor',children=['decor'],translation=[2,-3,.735+n*.1],rotation=30,deleted=False,decor_context=dict(purpose=kind,support_group_id='support',proposal_id='a'*32))],objects=[dict(id='support',name='support',room_id=None,material={}),dict(id='decor',name='decor',room_id=None,material={})])
    native=folder/'source.blend';bpy.ops.wm.save_as_mainfile(filepath=str(native));before_hash=hashlib.sha256(native.read_bytes()).hexdigest()
    request=dict(design=scene,asset=dict(kind='generated',recipe=dict(purpose=kind,dimensions=size,version=2,design={})),target_group='decor',output=str(folder),model_id=('123456789abcdef0'*2),task_id='b'*32,preview=str(folder/'model.glb'),auto_fit=True,asset_requirements=dict(purpose=kind,dimension_source='estimated',dimensions=size,evidence=''))
    replace_asset(request)
    report=json.loads((folder/'replacement-report.json').read_text(encoding='utf-8'))
    assert report['support']['status']=='passed' and abs(report['support']['translation'][2]+.008)<.001,report
    assert signature(support)==before and hashlib.sha256(native.read_bytes()).hexdigest()==before_hash
    updated=json.loads((folder/'replacement-scene.json').read_text(encoding='utf-8'));group=updated['groups'][1]
    meshes=[o for o in bpy.context.scene.objects if o.get('studio_id') in group['children']]
    if kind=='vase':
        bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,.90));block=bpy.context.object;block.dimensions=(.6,.6,.04)
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);block['studio_id']='block';updated['groups'][0]['children'].append('block');bpy.context.view_layer.update()
        try:support_check(updated,group,meshes)
        except ValueError:pass
        else:raise AssertionError('true triangle intersection was accepted')
        updated['groups'][0]['children'].remove('block');bpy.data.objects.remove(block,do_unlink=True)
    # No bounding-box support: move the target well outside the actual surface.
    group['translation'][0]+=2
    try:support_check(updated,group,meshes)
    except ValueError:pass
    else:raise AssertionError('unsupported decor was accepted')
print('DECOR_TEST_PASSED')
