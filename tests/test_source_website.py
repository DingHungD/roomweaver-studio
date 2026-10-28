"""Source-bound websites bypass adoption and never accept editor design data."""
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from interior.workbench.jobs import Jobs
from interior.workbench.server import create_app
from interior.workbench.storage import write_json,read_json,Conflict
from interior.workbench.studio.models import Scene
from interior.workbench.studio.service import digest
from interior.workbench.studio.source_site import checked_model,execute_source_site


@pytest.fixture
def ready(tmp_path):
    with patch.object(Jobs,'loop',return_value=None):
        app=create_app(tmp_path/'application')
        with TestClient(app,base_url='http://127.0.0.1') as client:
            client.headers['X-Workbench-Token']=client.get('/api/session').json()['token']
            store=app.state.store;store.create_project(dict(id='SOURCE',name='Source',kind='synthetic'))
            studio=app.state.studio;root=studio.root('SOURCE')
            source=root/'sources/source.glb';source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(b'synthetic immutable source')
            write_json(studio.folder('SOURCE')/'source.json',dict(native='sources/source.glb',preview='sources/source.glb',sha256=digest(source)))
            job=studio.jobs.submit_studio('SOURCE','prepare',dict(source={}), 'prepare-source-model')
            folder=root/job['output'];folder.mkdir(parents=True)
            (folder/'model.blend').write_bytes(b'synthetic native')
            write_json(folder/'model.json',dict(source_sha256=digest(source),native_sha256=digest(folder/'model.blend'),objects=[dict(id='floor',name='Floor')]))
            job['status']='completed';studio.jobs.write(job)
            write_json(root/'workflows/project-session/intake.json',dict(route='glb',job_id=job['id'],base_revision=None))
            yield client,studio,root,job['id']


def body(model,**kwargs):return dict(model_id=model,operation_id='generate-source-site',**kwargs)


def test_complete_3d_resumes_without_adopting(ready):
    client,studio,root,model=ready
    state=client.get('/api/studio/project-library/SOURCE/resume').json()
    assert state['step']==7 and state['route']=='glb'
    assert studio.current('SOURCE')['revision'] is None
    assert client.get('/api/studio/projects/SOURCE/source-site').json()['model_id']==model
    job=studio.jobs.get(model);job['status']='running';studio.jobs.write(job)
    assert client.get('/api/studio/project-library/SOURCE/resume').json()['step']==0


def test_only_lights_and_eyes_cross_boundary_and_retries_deduplicate(ready):
    client,studio,root,model=ready
    scene=Scene(model_id=model,rooms=[dict(id='room',name='Room')],objects=[dict(id='floor',name='Floor',material={'color':'#ff0000'})],
                groups=[dict(id='g',name='Move',children=['floor'],translation=[20,30,40],deleted=True,method='individual')],
                viewpoints=[dict(id='p',room_id='room',name='View',eye=[1,2,1.5],shots=[])]).model_dump(mode='json')
    saved=studio.save('SOURCE',scene,None)
    pointer=(root/'workflows/interior-studio/current.json').read_bytes()
    response=client.post('/api/studio/projects/SOURCE/source-site',json=body(model));assert response.status_code==200,response.text
    assert client.post('/api/studio/projects/SOURCE/source-site',json=body(model)).json()['id']==response.json()['id']
    request=read_json(studio.store.state_dir/'jobs'/response.json()['id']/'request.json')['parameters']
    assert request['viewpoints']==[dict(name='View',eye=[1,2,1.5])]
    assert not {'scene','design','groups','objects','materials','revision'}&request.keys()
    assert (root/'workflows/interior-studio/current.json').read_bytes()==pointer
    assert studio.current('SOURCE')['revision']==saved['revision']
    assert client.post('/api/studio/projects/SOURCE/source-site',json=body(model,views=8)).status_code==409


def test_stale_source_and_modified_native_are_rejected(ready):
    client,studio,root,model=ready
    (root/'runs/interior-studio'/model/'model.blend').write_bytes(b'modified')
    assert client.post('/api/studio/projects/SOURCE/source-site',json=body(model)).status_code==409
    (root/'sources/source.glb').write_bytes(b'new source')
    assert client.get('/api/studio/projects/SOURCE/source-site').status_code==409


def test_fixture_binding_and_limits(ready):
    client,studio,root,model=ready
    assert client.post('/api/studio/projects/SOURCE/source-site',json=body(model,lighting='fixtures')).status_code==409
    for kwargs in (dict(views=0),dict(views=9),dict(quality='arbitrary'),dict(lighting='edit'),dict(design={})):
        assert client.post('/api/studio/projects/SOURCE/source-site',json=body(model,**kwargs)).status_code==422
    with pytest.raises(ValueError):checked_model(root,'../outside','a'*64)


def test_artifacts_are_owned_completed_and_path_guarded(ready):
    client,studio,root,model=ready
    job=client.post('/api/studio/projects/SOURCE/source-site',json=body(model)).json()
    folder=root/job['output'];write_json(folder/'site/tour.json',dict(views=[]))
    url=f'/api/studio/projects/SOURCE/source-site/{job["id"]}/files/'
    assert client.get(url+'site/tour.json').status_code==422
    job['status']='completed';studio.jobs.write(job)
    assert client.get(url+'site/tour.json').status_code==200
    assert client.get(url+'site/missing.jpg').status_code==422
    from interior.workbench.studio.source_site import SourceSites
    with pytest.raises(ValueError):SourceSites(studio).artifact('SOURCE',job['id'],'../../../../project.json')
    assert client.get(f'/api/studio/projects/SOURCE/source-site/{model}/files/model.blend').status_code==422


def test_queue_rechecks_source_before_starting_blender(ready,tmp_path):
    client,studio,root,model=ready
    sha=digest(root/'sources/source.glb');(root/'sources/source.glb').write_bytes(b'changed after queue')
    with patch('interior.workbench.studio.source_site.subprocess.Popen') as process:
        with pytest.raises(Conflict):execute_source_site(root,root/'runs/interior-studio'/('c'*32),dict(model_id=model,source_sha256=sha),'blender')
        process.assert_not_called()


def test_standalone_completed_run_is_listed_and_downloadable(ready):
    client,studio,root,model=ready
    from interior.workbench.studio.source_site import record_completed_source_site
    identifier='d'*32;folder=root/'runs/interior-studio'/identifier
    write_json(folder/'preservation.json',dict(preserved=True))
    (folder/'website.zip').write_bytes(b'synthetic zip')
    result=dict(model_id=model,source_sha256=digest(root/'sources/source.glb'),preserved=True)
    record_completed_source_site(root,folder,result)
    current=client.get('/api/studio/projects/SOURCE/source-site').json()
    assert current['jobs'][0]['id']==identifier
    response=client.get(f'/api/studio/projects/SOURCE/source-site/{identifier}/files/website.zip')
    assert response.status_code==200 and response.content==b'synthetic zip'


def test_sync_production_freezes_inputs_without_editor_or_blender(ready):
    client,studio,root,model=ready
    write_json(root/'workflows/source-website/upstream.json',dict(producer='synthetic'))
    frozen=dict(delivery_sha256='a'*64,manifest_sha256='b'*64)
    with patch('interior.workbench.studio.production_site.production_input',return_value=frozen):
        response=client.post('/api/studio/projects/SOURCE/source-site',json=body(model,mode='sync-production'))
    assert response.status_code==200,response.text
    request=read_json(studio.store.state_dir/'jobs'/response.json()['id']/'request.json')['parameters']
    assert request['upstream']==frozen and 'scene' not in request and 'lighting_setup' not in request
    assert client.get('/api/studio/projects/SOURCE/source-site').json()['upstream_available']
    assert studio.current('SOURCE')['revision'] is None
