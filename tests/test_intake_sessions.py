"""File-first intake uses isolated projects, real parsers and no model calls."""
import hashlib
import io
from unittest.mock import patch
import ezdxf
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from interior.workbench.jobs import Jobs
from interior.workbench.server import create_app
from interior.workbench.storage import Store,Conflict,read_json,write_json

def png():
    stream=io.BytesIO();Image.new('RGB',(200,200),'white').save(stream,format='PNG');return stream.getvalue()

def dxf():
    drawing=ezdxf.new();drawing.units=6;drawing.modelspace().add_line((0,0),(3,0),dxfattribs={'layer':'wall'})
    stream=io.StringIO();drawing.write(stream);return stream.getvalue().encode()

@pytest.fixture
def client(tmp_path):
    with patch.object(Jobs,'loop',return_value=None):
        app=create_app(tmp_path)
        with TestClient(app,base_url='http://127.0.0.1') as client:
            client.headers['X-Workbench-Token']=client.get('/api/session').json()['token']
            yield client

def upload(client,route,name,content,operation='a'*32):
    return client.post(f'/api/studio/intake/upload?route={route}&operation_id={operation}',files={'file':(name,content)})

def test_empty_workspace_and_real_png_intake(client):
    assert client.get('/api/studio/intake').json()['current'] is None
    r=upload(client,'image','new-sketch.png',png());assert r.status_code==200,r.text
    data=r.json();assert data['route']=='image' and not data['job'] and data['project']['has_intake']
    assert client.get('/api/studio/intake').json()['current']['id']==data['project']['id']
    record=client.get(f'/api/studio/projects/{data["project"]["id"]}/image-plans/current').json()
    assert record['source']['name']=='new-sketch.png' and record['task_id'] is None

def test_repeated_request_deduplicates_and_changed_input_conflicts(client):
    first=upload(client,'image','one.png',png()).json()
    assert upload(client,'image','one.png',png()).json()==first
    assert len(client.get('/api/studio/projects').json())==1
    assert upload(client,'image','two.png',png()).status_code==409
    second=upload(client,'image','one.png',png(),'b'*32).json()
    assert first['project']['id']!=second['project']['id']

def test_dxf_and_glb_create_their_own_route_without_adopting(client):
    plan=upload(client,'dxf','floor.dxf',dxf()).json()
    r=client.get(f'/api/studio/projects/{plan["project"]["id"]}/plans/current')
    assert r.json()['source']['name']=='floor.dxf'
    model=upload(client,'glb','model.glb',b'glTFsynthetic-pending-validation','b'*32).json()
    assert model['job']['project_id']==model['project']['id'] and model['job']['status']=='queued'
    current=client.get('/api/studio/intake').json()
    assert current['job']['id']==model['job']['id'] and current['current']['revision'] is None
    assert client.get(f'/api/studio/projects/{plan["project"]["id"]}/scene').json()['scene'] is None

def test_invalid_file_does_not_replace_active_session(client):
    first=upload(client,'image','one.png',png()).json()
    assert upload(client,'image','bad.png',b'bad','b'*32).status_code==422
    assert upload(client,'dxf','wrong.png',png(),'c'*32).status_code==422
    assert client.get('/api/studio/intake').json()['current']['id']==first['project']['id']
    assert len(client.get('/api/studio/projects').json())==1
    assert len(client.app.state.store.projects(include_archived=True))==2

def test_archive_hides_registry_but_preserves_direct_references(client):
    data=upload(client,'image','one.png',png()).json();identifier=data['project']['id']
    store=client.app.state.store;path=store.project(identifier).root/'project.json'
    old=read_json(path);write_json(path,dict(old,studio_archived=True))
    assert store.projects()==[] and store.project(identifier).root==path.parent
    assert client.get('/api/studio/intake').json()['current'] is None
    assert path.exists()
    with pytest.raises(Conflict):store.create_project(dict(id=identifier,name='must not overwrite'))

def test_examples_use_clean_sources_and_independent_copies(client,tmp_path):
    from interior.workbench.studio.intake import IntakeSessions
    from interior.workbench.studio.image_plan import ImageIntake
    from interior.workbench.studio.plan_import import PlanIntake
    root=tmp_path/'examples'
    for name,content in [('from-image/project04-plan.png',png()),('from-dxf/project04-plan.dxf',dxf()),('from-3d/project04-apartment.glb',b'glTFfixture'),('from-3d/project04-apartment.blend',b'fixture native')]:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
    pair=root/'from-3d'
    manifest=dict(name='Project04 synthetic test',native='project04-apartment.blend',preview='project04-apartment.glb',suggested_viewpoints=[],sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in pair.iterdir()})
    write_json(pair/'manifest.json',manifest)
    studio=client.app.state.studio
    sessions=IntakeSessions(studio,ImageIntake(studio,client.app.state.studio_agents),PlanIntake(studio),root)
    records=[sessions.open(route,'',b'',key*32,True) for route,key in [('image','a'),('dxf','b'),('glb','c')]]
    assert len({r['project']['id'] for r in records})==3
    assert all(r['project']['name'] for r in records)
    assert records[-1]['job']['status']=='queued'
    configured=studio.configured_source(records[-1]['project']['id'])
    assert configured['native'].endswith('.blend') and configured['preview'].endswith('.glb')
    assert read_json(pair/'manifest.json')==manifest
    assert all(hashlib.sha256((pair/name).read_bytes()).hexdigest()==digest for name,digest in manifest['sha256'].items())
