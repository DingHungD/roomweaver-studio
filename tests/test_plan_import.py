"""Plan intake invariants, geometry blockers, and durable confirmation boundaries."""
import copy
from pathlib import Path
from unittest.mock import patch
import ezdxf
import pytest
from fastapi.testclient import TestClient
from interior.workbench.server import create_app
from interior.workbench.storage import Store
from interior.workbench.jobs import Jobs
from interior.workbench.studio.plan_import import parse_dxf, suggested_settings, check_plan
from interior.workbench.studio.backup import restore_backup

EXAMPLE=Path(__file__).parents[1]/'examples/dxf-courtyard/courtyard.dxf'


def test_example_contract_and_scale():
    data=parse_dxf(EXAMPLE);settings=suggested_settings(data)
    check=check_plan(data,settings)
    assert check['status']=='ready'
    assert check['counts']==dict(floor=1,wall=5,door=2,window=2,furniture=4)
    assert all(o['host_id'] for o in check['items'] if o['role'] in ('door','window'))
    bad=copy.deepcopy(settings);bad['units']='m'
    assert check_plan(data,bad)['status']=='blocked'
    bad=copy.deepcopy(settings)
    next(a for a in bad['assignments'] if a['role']=='door')['offset']=[0,1]
    assert any('唯一牆體' in x for x in check_plan(data,bad)['errors'])
    bad=copy.deepcopy(settings)
    next(a for a in bad['assignments'] if a['role']=='window')['height']=4
    assert any('高度' in x for x in check_plan(data,bad)['errors'])


def test_unsupported_geometry_and_annotations_are_explicit(tmp_path):
    doc=ezdxf.readfile(EXAMPLE);m=doc.modelspace()
    m.add_circle((1,2),3);m.add_text('dimensions are not geometry')
    path=tmp_path/'unsupported.dxf';doc.saveas(path)
    parsed=parse_dxf(path)
    assert parsed['issues'][0]['kind']=='CIRCLE'
    assert parsed['annotations']=={'TEXT':1}
    assert check_plan(parsed,suggested_settings(parsed))['status']=='blocked'


def test_nonzero_elevation_and_nonconvex_are_blocked(tmp_path):
    doc=ezdxf.new();doc.units=4
    doc.modelspace().add_line((0,0,1),(10,0,1))
    doc.modelspace().add_lwpolyline([(0,0),(5000,0),(2500,1000),(5000,5000),(0,5000)],close=True,dxfattribs={'layer':'floor'})
    p=tmp_path/'bad.dxf';doc.saveas(p);parsed=parse_dxf(p)
    check=check_plan(parsed,suggested_settings(parsed))
    assert parsed['issues'] and any('凸多邊形' in s for s in check['errors'])


def test_rotated_centimetre_fixture(tmp_path):
    doc=ezdxf.readfile(EXAMPLE)
    from ezdxf.math import Matrix44
    for entity in doc.modelspace():entity.transform(Matrix44.chain(Matrix44.scale(.1),Matrix44.z_rotate(.4),Matrix44.translate(1200,-500,0)))
    doc.units=5;p=tmp_path/'rotated.dxf';doc.saveas(p)
    data=parse_dxf(p)
    assert data['detected_units']=='cm'
    assert check_plan(data,suggested_settings(data))['status']=='ready'


def test_http_reopen_stale_confirm_dedup_and_source_preservation(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='DXF',name='test'))
    with patch.object(Jobs,'loop',return_value=None):
        with TestClient(create_app(tmp_path),base_url='http://127.0.0.1') as c:
            headers={'x-workbench-token':c.get('/api/session').json()['token']}
            url='/api/studio/projects/DXF'
            p=c.post(url+'/plans/upload',files={'file':('example.dxf',EXAMPLE.read_bytes())},headers=headers)
            assert p.status_code==200,p.text
            p=p.json();assert c.get(url+'/scene').json()['scene'] is None
            saved=c.put(url+'/plans/'+p['id'],json=dict(base_revision=p['revision'],settings=p['settings']),headers=headers).json()
            assert saved['revision']!=p['revision']
            assert c.post(url+'/plans/'+p['id']+'/build',json=dict(plan_revision=p['revision']),headers=headers).status_code==409
            payload=dict(plan_revision=saved['revision'])
            a=c.post(url+'/plans/'+p['id']+'/build',json=payload,headers=headers)
            b=c.post(url+'/plans/'+p['id']+'/build',json=payload,headers=headers)
            assert a.status_code==200,a.text
            assert a.json()['id']==b.json()['id']
            source=tmp_path/'projects/dxf'/p['source']['path']
            assert source.read_bytes()==EXAMPLE.read_bytes()
    with patch.object(Jobs,'loop',return_value=None):
        with TestClient(create_app(tmp_path),base_url='http://127.0.0.1') as c:
            assert c.get(url+'/plans/current').json()['revision']==saved['revision']
            assert len(c.app.state.jobs.list())==1
            source.write_bytes(b'changed')
            headers={'x-workbench-token':c.get('/api/session').json()['token']}
            bad=c.post(url+'/plans/'+p['id']+'/build',json=payload,headers=headers)
            assert bad.status_code==422 and '已變動' in bad.text


def test_backup_restores_plan_pointer_without_rebuilding(tmp_path):
    store=Store(tmp_path,tmp_path/'artifacts/workbench/local');store.create_project(dict(id='DXF',name='test'))
    with patch.object(Jobs,'loop',return_value=None):
        with TestClient(create_app(tmp_path),base_url='http://127.0.0.1') as c:
            h={'x-workbench-token':c.get('/api/session').json()['token']};url='/api/studio/projects/DXF'
            p=c.post(url+'/plans/upload',files={'file':('example.dxf',EXAMPLE.read_bytes())},headers=h).json()
            backup=c.post('/api/studio/backup',headers=h).json()
            changed=copy.deepcopy(p['settings']);changed['assignments'][0]['name']='Changed floor'
            later=c.put(url+'/plans/'+p['id'],json=dict(base_revision=p['revision'],settings=changed),headers=h).json()
            assert later['revision']!=p['revision']
        restore_backup(store,backup['path'])
        with TestClient(create_app(tmp_path),base_url='http://127.0.0.1') as c:
            assert c.get(url+'/plans/current').json()['revision']==p['revision']
            assert c.app.state.jobs.list()==[]
