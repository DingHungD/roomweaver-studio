"""External project roots, safe directory grants and durable stage recovery."""
import io
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from interior.workbench.jobs import Jobs
from interior.workbench.server import create_app
from interior.workbench.storage import Store,write_json,read_json,Conflict
from interior.workbench.studio.models import Scene

@pytest.fixture
def client(tmp_path):
    with patch.object(Jobs,'loop',return_value=None):
        app=create_app(tmp_path/'application')
        with TestClient(app,base_url='http://127.0.0.1') as c:
            c.headers['X-Workbench-Token']=c.get('/api/session').json()['token']
            yield c

def create(c,root,name='新專案',op='a'*32):
    root.mkdir()
    with patch('interior.workbench.studio.project_library.choose_directory',return_value=str(root)):
        picked=c.post('/api/studio/project-library/folders/pick')
    assert picked.status_code==200,picked.text
    body=dict(folder_token=picked.json()['folder_token'],name=name,operation_id=op)
    r=c.post('/api/studio/project-library',json=body);assert r.status_code==200,r.text
    return r.json(),body

def png():
    b=io.BytesIO();Image.new('RGB',(200,200),'white').save(b,format='PNG');return b.getvalue()

def test_native_cancel_and_nonempty_never_write(client,tmp_path):
    with patch('interior.workbench.studio.project_library.choose_directory',return_value=None):
        assert client.post('/api/studio/project-library/folders/pick').json() is None
    root=tmp_path/'occupied';root.mkdir();(root/'keep.txt').write_text('unchanged')
    with patch('interior.workbench.studio.project_library.choose_directory',return_value=str(root)):
        assert client.post('/api/studio/project-library/folders/pick').status_code==422
    assert [p.name for p in root.iterdir()]==['keep.txt'] and client.get('/api/studio/project-library').json()==[]

def test_confirm_rechecks_folder_and_requires_picker_grant(client,tmp_path):
    root=tmp_path/'empty';root.mkdir()
    with patch('interior.workbench.studio.project_library.choose_directory',return_value=str(root)):
        token=client.post('/api/studio/project-library/folders/pick').json()['folder_token']
    assert not list(root.iterdir())
    (root/'new.txt').write_text('added after picker')
    assert client.post('/api/studio/project-library',json=dict(folder_token=token,name='New',operation_id='a'*32)).status_code==422
    assert not (root/'project.json').exists()
    assert client.post('/api/studio/project-library',json=dict(folder_token='f'*32,name='New',operation_id='b'*32)).status_code==422

def test_external_root_is_portable_and_deduplicated(client,tmp_path):
    root=tmp_path/'outside app';project,body=create(client,root,'自訂顯示名稱')
    assert client.post('/api/studio/project-library',json=body).json()==project
    assert client.app.state.store.project(project['id']).root==root.resolve()
    assert set(p.name for p in root.iterdir())=={'project.json','README.md'}
    metadata=read_json(root/'project.json');assert metadata['name']=='自訂顯示名稱' and metadata['entries']=={}
    assert str(root) not in (root/'project.json').read_text(encoding='utf-8')
    restored=Store(client.app.state.store.workspace,client.app.state.store.state_dir)
    assert restored.project(project['id']).root==root.resolve()
    with pytest.raises(ValueError):restored.project(project['id']).path('../escape')
    card=client.get('/api/studio/project-library').json()[0]
    assert card['path']==str(root.resolve()) and card['status']=='01 尚未匯入'

def test_imports_stay_in_selected_project_and_failed_input_keeps_it(client,tmp_path):
    root=tmp_path/'new-home';p,_=create(client,root);identifier=p['id']
    def upload(op,content):return client.post(f'/api/studio/intake/upload?route=image&operation_id={op}&project_id={identifier}',files={'file':('plan.png',content)})
    first=upload('b'*32,png());assert first.status_code==200,first.text
    assert upload('c'*32,png()).status_code==200
    assert upload('d'*32,b'bad').status_code==422
    assert len(client.get('/api/studio/project-library').json())==1
    assert client.app.state.store.project(identifier).metadata['name']=='新專案'
    assert not client.app.state.store.project(identifier).metadata.get('studio_archived')
    assert len(list((root/'sources/workbench').glob('*/*.png')))==2
    resume=client.get(f'/api/studio/project-library/{identifier}/resume').json()
    assert resume['step']==0 and resume['route']=='image'


def test_private_concept_preview_is_never_resumed_as_an_import(client,tmp_path):
    root=tmp_path/'preview-home';p,_=create(client,root);identifier=p['id']
    uploaded=client.post(f'/api/studio/intake/upload?route=image&operation_id={"b"*32}&project_id={identifier}',files={'file':('plan.png',png())})
    assert uploaded.status_code==200
    studio=client.app.state.studio
    studio.jobs.submit_studio(identifier,'prepare',dict(source=dict(plan='private-preview.json',preview_only=True)), 'private-preview-job')
    resume=client.get(f'/api/studio/project-library/{identifier}/resume')
    assert resume.status_code==200 and resume.json()['job'] is None
    assert resume.json()['step']==0 and resume.json()['route']=='image'

def test_view_is_revision_bound_and_missing_directory_is_not_recreated(client,tmp_path):
    root=tmp_path/'saved';p,_=create(client,root);identifier=p['id'];studio=client.app.state.studio
    model='b'*32
    write_json(root/'runs/interior-studio'/model/'model.json',dict(objects=[dict(id='floor',name='Floor')]))
    scene=Scene(model_id=model,rooms=[],objects=[dict(id='floor',name='Floor',material={})],groups=[dict(id='g',name='Floor',children=['floor'],translation=[0,0,0],deleted=False,method='individual')],viewpoints=[],links=[]).model_dump(mode='json')
    saved=studio.save(identifier,scene,None)
    import json
    run=dict(run_id='c'*32,project_id=identifier,operation_id='read-only-card',revision=saved['revision'],quality='preview',status='awaiting_confirmation')
    with studio.jobs.connect() as db:db.execute('INSERT INTO studio_workflows VALUES (?,?,?,?)',(run['run_id'],identifier,run['operation_id'],json.dumps(run)))
    with patch.object(client.app.state.studio_coordinator,'get',side_effect=AssertionError('Card listing must not advance graphs')):
        assert client.get('/api/studio/project-library').json()[0]['status']=='03 整合輸出'
    assert not studio.jobs.list(identifier)
    assert client.put(f'/api/studio/project-library/{identifier}/view',json=dict(revision=saved['revision'],step=6)).status_code==200
    assert client.get(f'/api/studio/project-library/{identifier}/resume').json()['step']==6
    next_revision=studio.save(identifier,scene,saved['revision'])
    assert client.get(f'/api/studio/project-library/{identifier}/resume').json()['step']==1
    assert client.put(f'/api/studio/project-library/{identifier}/view',json=dict(revision=saved['revision'],step=6)).status_code==409
    # Rename only this synthetic directory to simulate a disconnected drive.
    moved=tmp_path/'moved';root.rename(moved)
    cards=client.get('/api/studio/project-library').json();assert not cards[0]['available']
    assert not root.exists() and client.get(f'/api/studio/project-library/{identifier}/resume').status_code==404

def test_new_plan_takes_precedence_over_previous_model(client,tmp_path):
    root=tmp_path/'changed';p,_=create(client,root);identifier=p['id']
    model='b'*32;write_json(root/'runs/interior-studio'/model/'model.json',dict(objects=[]))
    saved=client.app.state.studio.save(identifier,dict(model_id=model,rooms=[],objects=[],groups=[],viewpoints=[],links=[]),None)
    r=client.post(f'/api/studio/intake/upload?route=image&operation_id={"c"*32}&project_id={identifier}',files={'file':('new.png',png())})
    assert r.status_code==200,r.text
    assert r.json()['base_revision']==saved['revision']
    resume=client.get(f'/api/studio/project-library/{identifier}/resume').json()
    assert resume['step']==0 and resume['route']=='image' and resume['base_revision']==saved['revision']
    assert client.app.state.studio.current(identifier)['revision']==saved['revision']

def test_backup_keeps_external_registry_and_session_evidence(client,tmp_path):
    from interior.workbench.studio.backup import create_backup
    root=tmp_path/'backup-external';p,_=create(client,root)
    write_json(root/'workflows/project-session/view.json',dict(revision='a'*32,step=2))
    backup=create_backup(client.app.state.studio,client.app.state.studio_coordinator)
    folder=Path(backup['path']);manifest=read_json(folder/'manifest.json')
    item=next(item for item in manifest['projects'] if item['id']==p['id'])
    assert 'project-session' in item['parts']
    assert read_json(folder/'application/project-library-registry.json')['projects'][0]['root']==str(root.resolve())
    assert (folder/'projects'/p['id']/'project-session/view.json').is_file()
    assert (root/'workflows/project-session/view.json').is_file()
