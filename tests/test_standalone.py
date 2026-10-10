from pathlib import Path
import tempfile
from unittest.mock import patch
from fastapi.testclient import TestClient
from interior.workbench.server import create_app
from interior.workbench.storage import Store
from interior.workbench.__main__ import main
from interior.workbench.studio.models import LightingSetup


def test_first_run_and_local_boundary():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        assert main(['init','--workspace',str(root)])==0
        assert main(['init','--workspace',str(root)])==0
        with patch('interior.workbench.agent_runtime.codex.CodexRuntime.__init__',side_effect=AssertionError('Unexpected model connection')):
            with TestClient(create_app(root),base_url='http://127.0.0.1') as client:
                assert client.get('/api/health').json()['status']=='ok'
                assert client.get('/api/studio/projects').json()[0]['id']=='DEMO'
                assert client.get('/api/studio/projects/DEMO/scene').json()['scene'] is None
                assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==403
                assert client.get('/api/health',headers={'Origin':'https://evil.example'}).status_code==403
                assert client.post('/api/studio/backup').status_code==403
        assert not LightingSetup().agent_review


def test_upload_is_owned_and_repeated_names_do_not_overwrite():
    with tempfile.TemporaryDirectory() as temp:
        store=Store(temp,Path(temp)/'state');store.create_project(dict(id='TEST',name='test'))
        one=store.upload('TEST','../../sample.glb',b'first')
        two=store.upload('TEST','sample.glb',b'second')
        assert one['path']!=two['path']
        assert store.project('TEST').path(one['path']).read_bytes()==b'first'
