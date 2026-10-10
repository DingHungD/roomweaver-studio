import hashlib
import json
from pathlib import Path
import pytest
from interior.workbench.storage import Conflict, read_json
from interior.workbench.studio.example import register_example


def source(tmp_path):
    folder=tmp_path/'example';folder.mkdir()
    values={'native':'room.blend','preview':'room.glb'}
    for name in values.values():(folder/name).write_bytes(b'fixture')
    (folder/'manifest.json').write_text(json.dumps(dict(**values,name='Test',
        suggested_viewpoints=[],sha256={name:hashlib.sha256(b'fixture').hexdigest() for name in values.values()})))
    return folder


def test_example_preserves_original_and_refuses_existing_project(tmp_path):
    folder=source(tmp_path);workspace=tmp_path/'workspace'
    register_example(workspace,folder)
    copied=workspace/'projects/daylight/sources/example/room.blend'
    assert copied.read_bytes()==b'fixture'
    copied.write_bytes(b'user modification')
    with pytest.raises(Conflict):register_example(workspace,folder)
    assert copied.read_bytes()==b'user modification'
    assert (folder/'room.blend').read_bytes()==b'fixture'


def test_bad_hash_and_traversal_rejected_before_project_creation(tmp_path):
    folder=source(tmp_path);workspace=tmp_path/'workspace'
    (folder/'room.blend').write_bytes(b'changed')
    with pytest.raises(ValueError,match='checksum'):register_example(workspace,folder)
    assert not (workspace/'projects').exists()
    manifest=read_json(folder/'manifest.json');manifest['native']='../outside.blend'
    (folder/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='inside'):register_example(workspace,folder)
