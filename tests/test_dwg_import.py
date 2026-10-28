"""DWG source preservation, bounded conversion and the existing plan/3D contract."""
import json
from pathlib import Path
import subprocess
import ezdxf
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from interior.workbench.jobs import Jobs
from interior.workbench.server import create_app
from interior.workbench.storage import read_json
from interior.workbench.studio import dwg_conversion as dwg

DXF=Path(__file__).parent/'fixtures/legacy-examples/dxf-courtyard/courtyard.dxf'
DWG=b'AC1032synthetic-DWG-converter-boundary'


@pytest.fixture
def client(tmp_path):
    with patch.object(Jobs,'loop',return_value=None):
        with TestClient(create_app(tmp_path),base_url='http://127.0.0.1') as c:
            c.headers['X-Workbench-Token']=c.get('/api/session').json()['token']
            c.app.state.store.create_project(dict(id='OWN',name='自己的新案'))
            yield c


@pytest.fixture
def converter(tmp_path):
    executable=tmp_path/'ODAFileConverter.exe';executable.write_bytes(b'fake executable')
    def run(args,**kwargs):
        assert args[3:]==['ACAD2018','DXF','0','0','*.dwg']
        assert (Path(args[1])/'plan.dwg').read_bytes()==DWG
        assert kwargs['timeout']==120 and kwargs['capture_output']
        (Path(args[2])/'plan.dxf').write_bytes(DXF.read_bytes())
        return SimpleNamespace(returncode=0,stdout=b'ok',stderr=b'')
    # Conversion uses synthetic bytes; native geometry has separate integration tests.
    with patch('interior.workbench.studio.native_intake.attach_native',return_value={'synthetic':True}),patch.object(dwg,'converter_executable',return_value=executable),patch.object(dwg.subprocess,'run',side_effect=run) as runner:
        yield runner


def upload(client,operation='a'*32,content=DWG):
    return client.post('/api/studio/intake/upload?route=dxf&project_id=OWN&operation_id='+operation,files={'file':('新居平面.DWG',content)})


def test_dwg_selected_project_source_provenance_reopen_and_build_dedup(client,converter):
    response=upload(client);assert response.status_code==200,response.text
    result=response.json();assert result['project']['id']=='OWN' and result['route']=='dxf'
    p=client.get('/api/studio/projects/OWN/plans/current').json()
    assert p['check']['status']=='ready'
    root=client.app.state.store.project('OWN').root
    assert (root/p['source']['original']['path']).read_bytes()==DWG
    assert (root/p['source']['path']).read_bytes()==DXF.read_bytes()
    assert p['source']['name']=='新居平面.dxf'
    manifest=read_json(root/p['source']['conversion']['record'])
    assert manifest['status']=='completed' and not manifest['audit']
    assert 'tool_sha256' in manifest and 'executable' not in manifest
    assert upload(client).json()==result and converter.call_count==1
    assert upload(client,content=DWG+b'changed').status_code==409
    assert len(client.get('/api/studio/project-library').json())==1
    assert client.get('/api/studio/project-library/OWN/resume').json()['project']['id']=='OWN'
    url=f"/api/studio/projects/OWN/plans/{p['id']}/build"
    first=client.post(url,json=dict(plan_revision=p['revision']))
    assert first.status_code==200,first.text
    assert client.post(url,json=dict(plan_revision=p['revision'])).json()['id']==first.json()['id']
    (root/p['source']['original']['path']).write_bytes(DWG+b'tampered')
    r=client.post(url,json=dict(plan_revision=p['revision']))
    assert r.status_code==422 and '原始 DWG 已變動' in r.text


def test_secondary_upload_and_converter_does_not_hold_store_lock(client,converter):
    import threading
    acquired=[]
    original=converter.side_effect
    def unlocked(*args,**kwargs):
        def worker():
            lock=client.app.state.store.lock
            ok=lock.acquire(timeout=.5);acquired.append(ok)
            if ok:lock.release()
        t=threading.Thread(target=worker);t.start();t.join(2)
        return original(*args,**kwargs)
    converter.side_effect=unlocked
    r=client.post('/api/studio/projects/OWN/plans/upload',files={'file':('floor.dwg',DWG)})
    assert r.status_code==200,r.text
    assert acquired==[True]


@pytest.mark.parametrize('failure',['missing','timeout','empty','exit','oversize'])
def test_failure_preserves_original_and_previous_plan(client,converter,failure):
    old=client.post('/api/studio/projects/OWN/plans/upload',files={'file':('before.dxf',DXF.read_bytes())}).json()
    if failure=='missing':
        resolution=patch.object(dwg,'converter_executable',side_effect=ValueError('找不到 ODA File Converter'))
    else:
        from contextlib import nullcontext
        resolution=nullcontext()
        def run(args,**kwargs):
            if failure=='timeout':raise subprocess.TimeoutExpired(args,120)
            if failure=='oversize':(Path(args[2])/'plan.dxf').write_bytes(b'0'*10_000_001)
            return SimpleNamespace(returncode=1 if failure=='exit' else 0,stdout=b'',stderr=b'failed')
        converter.side_effect=run
    with resolution:r=upload(client)
    assert r.status_code==422 and '原始 DWG' in r.text
    assert client.get('/api/studio/projects/OWN/plans/current').json()==old
    root=client.app.state.store.project('OWN').root
    assert next(root.glob('sources/workbench/*/*.DWG')).read_bytes()==DWG
    assert read_json(next(root.glob('runs/plan-conversion/*/conversion.json')))['status']=='failed'
    assert client.get('/api/studio/project-library').json()[0]['available']
    assert len(client.app.state.jobs.list())==0


def test_invalid_dwg_header_never_executes_converter(client,converter):
    r=upload(client,content=DXF.read_bytes())
    assert r.status_code==422 and '檔頭無效' in r.text
    converter.assert_not_called()


def test_dwg_hatch_reaches_confirmation_with_traceable_boundary(client,converter):
    original=converter.side_effect
    def run(args,**kwargs):
        result=original(args,**kwargs)
        path=Path(args[2])/'plan.dxf'
        doc=ezdxf.readfile(path)
        hatch=doc.modelspace().add_hatch()
        hatch.paths.add_polyline_path([(0,0),(1,0),(1,1),(0,1)],is_closed=True)
        doc.saveas(path)
        return result
    converter.side_effect=run
    response=upload(client);assert response.status_code==200,response.text
    plan=client.get('/api/studio/projects/OWN/plans/current').json()
    assert not any(i['kind']=='HATCH' for i in plan['parsed']['issues'])
    assert plan['parsed']['cad_preparation']['counts']['hatches']==1
    assert any(f['kind']=='HATCH' and f['suggested_role']=='ignore' for f in plan['parsed']['features'])
    root=client.app.state.store.project('OWN').root
    assert (root/plan['source']['original']['path']).read_bytes()==DWG
    url=f"/api/studio/projects/OWN/plans/{plan['id']}/build"
    response=client.post(url,json=dict(plan_revision=plan['revision']))
    assert response.status_code==200,response.text


def test_converter_settings_precedence_and_no_silent_fallback(tmp_path,monkeypatch):
    explicit=tmp_path/'chosen.exe';explicit.touch()
    monkeypatch.setenv('ODA_FILE_CONVERTER',str(explicit))
    assert dwg.converter_executable(tmp_path)==explicit.resolve()
    explicit.unlink()
    with pytest.raises(ValueError,match='路徑不存在'):dwg.converter_executable(tmp_path)
    monkeypatch.delenv('ODA_FILE_CONVERTER')
    runtime=tmp_path/'runtime.json';runtime.write_text(json.dumps(dict(oda=str(explicit))))
    with pytest.raises(ValueError,match='路徑不存在'):dwg.converter_executable(tmp_path)
