import copy
from pathlib import Path
import pytest
from interior.workbench.studio import shelf_assets
from interior.workbench.storage import write_json
from interior.workbench.studio.models import ShelfRefinement

def candidate(**kw):
    return dict(name='Microwave',is_free=True,license='royalty_free',dimensions=[.45,.3,.27],**kw)

def test_exact_fit_filter_rejects_room_paid_and_oversize():
    available=[.50,.41,.47]
    assert shelf_assets.eligible(candidate(),'microwave',available)
    for key,value in [('name','Microwave kitchen set'),('is_free',False),('dimensions',[.55,.49,.3])]:
        c=candidate();c[key]=value;assert not shelf_assets.eligible(c,'microwave',available)
    assert not shelf_assets.eligible(candidate(),'magazines',available)

def test_search_download_and_bundle_are_independent_of_case(tmp_path,monkeypatch):
    root=tmp_path/'new-house';folder=root/'runs/interior-studio'/('a'*32);folder.mkdir(parents=True)
    c=candidate(asset_id='new-micro',url='https://www.blenderkit.com/asset-gallery-detail/new-micro/',description='')
    calls=[]
    monkeypatch.setattr(shelf_assets.catalog,'search',lambda q,k,f:[c])
    def download(item,path,identifier):
        calls.append(item['asset_id']);path.write_bytes(b'native fixture');return {'sha256':shelf_assets.digest(path)}
    monkeypatch.setattr(shelf_assets.catalog,'download',download)
    scene={'shelf_refinements':[{'object_id':'different-shelf','contents':['microwave']}]};original=copy.deepcopy(scene)
    reports=[dict(object_id='different-shelf',clearance=[.5,.41,.47],contents=[dict(kind='microwave',source=None)])]
    result,index,changed=shelf_assets.match_missing(scene,reports,folder,'sourcehash',{},tmp_path/'stop')
    assert changed and calls==['new-micro'] and scene==original
    choices=shelf_assets.resolve(result,root,'sourcehash')
    selected=choices['different-shelf']['microwave'][0]
    assert selected['min_scale']==.999 and Path(selected['file']).is_file()
    assert index['searches'][0]['candidates'][0]['eligible']
    with pytest.raises(ValueError):shelf_assets.resolve(result,root,'changed-source')
    Path(selected['file']).write_bytes(b'changed')
    with pytest.raises(ValueError):shelf_assets.resolve(result,root,'sourcehash')

def test_bundle_cannot_escape_job_directory(tmp_path):
    with pytest.raises(ValueError):ShelfRefinement(object_id='x',front='+Y',evidence='confirmed shelf',asset_bundle='../file')
    root=tmp_path/'case';folder=root/'runs/interior-studio'/('a'*32);folder.mkdir(parents=True)
    write_json(folder/'shelf-assets.json',dict(source_sha256='s',objects={'x':{'microwave':[dict(file='../../outside',sha256='x')]}}))
    with pytest.raises(ValueError):shelf_assets.resolve({'shelf_refinements':[dict(object_id='x',asset_bundle='a'*32)]},root,'s')

def test_no_result_retains_original_and_reason(tmp_path,monkeypatch):
    monkeypatch.setattr(shelf_assets.catalog,'search',lambda *args:[])
    scene={'shelf_refinements':[dict(object_id='other')]}
    result,index,changed=shelf_assets.match_missing(scene,[dict(object_id='other',clearance=[.3,.2,.1],contents=[dict(kind='microwave')])],tmp_path,'s',{},tmp_path/'stop')
    assert not changed and result==scene and index['searches'][0]['candidates']==[]

def test_editor_preparation_is_revision_bound_deduplicated_and_not_adopted(tmp_path):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from interior.workbench.storage import Store,read_json
    from interior.workbench.server import create_app
    from interior.workbench.jobs import Jobs
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='NEW',name='Synthetic'))
    with patch.object(Jobs,'loop',return_value=None):
        app=create_app(tmp_path)
        with TestClient(app,base_url='http://127.0.0.1') as c:
            studio=app.state.studio;model='a'*32
            write_json(studio.root('NEW')/'runs/interior-studio'/model/'model.json',dict(objects=[dict(id='unit',name='Unit')]))
            scene=dict(model_id=model,rooms=[dict(id='room',name='Room')],objects=[dict(id='unit',name='Unit',material={})],viewpoints=[dict(id='view',name='View',room_id='room',eye=[0,0,1.5],shots=[])])
            revision=studio.save('NEW',scene,None)
            headers={'x-workbench-token':c.get('/api/session').json()['token']}
            body=dict(base_revision=revision['revision'],operation_id='prep-new-house',point_id='view',brief='owner record')
            first=c.post('/api/studio/projects/NEW/realism-prepare',json=body,headers=headers)
            assert first.status_code==200,first.text
            assert c.post('/api/studio/projects/NEW/realism-prepare',json=body,headers=headers).json()['id']==first.json()['id']
            assert c.get('/api/studio/projects/NEW/realism-prepare').json()['id']==first.json()['id']
            assert studio.current('NEW')['revision']==revision['revision']
            assert c.post('/api/studio/projects/NEW/realism-prepare',json=dict(body,base_revision='b'*32),headers=headers).status_code==409
            assert c.post('/api/studio/projects/NEW/realism-prepare',json=dict(body,point_id='unknown'),headers=headers).status_code==422

def test_camera_frame_defaults_and_explicit_landscape():
    from interior.workbench.studio.models import Shot
    assert Shot(id='x',name='x',yaw=0).aspect=='4:3'
    assert Shot(id='x',name='x',yaw=0,aspect='16:9').aspect=='16:9'
    with pytest.raises(ValueError):Shot(id='x',name='x',yaw=0,aspect='arbitrary')
