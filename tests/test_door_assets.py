import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pytest
from interior.workbench.studio.door_assets import DoorAssets,DoorMatch,DoorSelection,resolve
from interior.workbench.studio.models import DoorControl
from interior.workbench.storage import write_json,Conflict

REFERENCE=dict(asset_id='11111111-1111-4111-8111-111111111111',version_id='22222222-2222-4222-8222-222222222222',url='https://www.blenderkit.com/asset-gallery-detail/11111111-1111-4111-8111-111111111111/',name='Wood',kind='material',license='cc_zero',is_free=True,task_id='a'*32,status='applied')

def test_binding_schema_and_tamper(tmp_path):
    from interior.workbench.studio.service import digest
    key='a'*32;folder=tmp_path/'workflows/interior-studio/door-assets'/key
    folder.mkdir(parents=True);(folder/'asset.blend').write_bytes(b'synthetic')
    write_json(folder/'bundle.json',dict(reference=REFERENCE,sha256=digest(folder/'asset.blend'),opening_id='door1',part='frame'))
    scene=dict(door_controls=[dict(opening_id='door1',assets=dict(frame=dict(bundle=key,reference=REFERENCE)))])
    result=resolve(scene,tmp_path)
    assert result['door_controls'][0]['_asset_files']['frame']['kind']=='material'
    assert '_asset_files' not in scene['door_controls'][0]
    (folder/'asset.blend').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='雜湊'):resolve(scene,tmp_path)
    scene['door_controls'][0]['assets']['frame']['bundle']='../other'
    with pytest.raises(ValueError):resolve(scene,tmp_path)

def test_door_controls_keep_assets_dimensions_direction():
    c=DoorControl(opening_id='door1',kind='single',side='negative',swing='positive',assembly_width=.85,assets={'frame':dict(bundle='b'*32,reference=REFERENCE)})
    assert DoorControl.model_validate(c.model_dump()).assembly_width==.85

def test_match_context_and_structural_guard(tmp_path):
    scene=dict(model_id='m',door_controls=[dict(opening_id='door1',kind='single',deleted=False)],manual_doors=[])
    studio=SimpleNamespace(current=lambda p:dict(revision='a'*32,scene=scene),root=lambda p:tmp_path,folder=lambda p:tmp_path/'workflows/interior-studio',model=lambda *a:{})
    agents=Mock();service=DoorAssets(studio,agents)
    with patch('interior.workbench.studio.opening_details.source_openings',return_value=dict(items=[dict(id='door1',name='Bedroom door',points=[[0,0],[.9,0]],height=2.1)])):
        with pytest.raises(ValueError,match='門框保留'):service.start('p',DoorMatch(base_revision='a'*32,opening_id='door1',part='frame',kind='model'))
        r=service.start('p',DoorMatch(base_revision='a'*32,opening_id='door1',part='leaf-0',kind='model'))
        payload=agents.start.call_args.args[2]
        assert payload['context']['door_control']==scene['door_controls'][0]
        assert payload['context']['group']['asset_requirements']['dimension_source']=='confirmed'
        assert agents.start.call_args.args[1]=='gpt-6-sol'
        assert (service.path('p',r['id'])/'input.json').exists()
    service.executor.shutdown()


def test_restart_releases_running_selection(tmp_path):
    service=DoorAssets(SimpleNamespace(folder=lambda p:tmp_path),Mock())
    folder=service.path('p','a'*32)
    write_json(folder/'selection.json',dict(id='a'*32,status='running'))
    state=service.status('p','a'*32)
    assert state['status']=='failed' and '重啟' in state['error']
    service.executor.shutdown()


def test_material_queries_explicitly_ignore_model_dimensions(tmp_path):
    from interior.workbench.studio.asset_matching import run_matching
    from interior.workbench.studio import blenderkit_client as catalog
    prompts=[]
    class Client:
        def run(self,prompt,**kwargs):
            prompts.append(prompt)
            return dict(text=json.dumps({'queries':['oak wood']} if len(prompts)==1 else {'matches':[]}))
    with patch.object(catalog,'search',return_value=[]):
        run_matching(Client(),tmp_path,dict(kind='material',description='wood',context=dict(door_control={'kind':'single'})),'gpt-6-sol',lambda p:None,lambda e:None)
    assert '只搜尋材質' in prompts[0]
    assert '"kind": "material"' in prompts[0]
