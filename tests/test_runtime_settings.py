"""Blender configuration survives a fresh service environment and fails before downloads."""
import os
from unittest.mock import patch
import pytest
from interior.workbench.runtime import configure_blender
from interior.workbench.storage import read_json
from interior.workbench.studio.engine import execute


def test_saved_blender_restored_after_environment_is_lost(tmp_path,monkeypatch):
    executable=tmp_path/'Blender with spaces'/'blender.exe'
    executable.parent.mkdir();executable.touch()
    monkeypatch.delenv('INTERIOR_BLENDER',raising=False)
    configure_blender(tmp_path,executable)
    assert os.environ['INTERIOR_BLENDER']==str(executable)
    monkeypatch.delenv('INTERIOR_BLENDER')
    configure_blender(tmp_path)
    assert os.environ['INTERIOR_BLENDER']==str(executable)
    before=read_json(tmp_path/'artifacts/workbench/local/runtime.json')
    with pytest.raises(ValueError,match='路徑不存在'):configure_blender(tmp_path,tmp_path/'absent.exe')
    assert read_json(tmp_path/'artifacts/workbench/local/runtime.json')==before


def test_environment_override_is_not_persisted(tmp_path,monkeypatch):
    executable=tmp_path/'blender';executable.touch()
    monkeypatch.setenv('INTERIOR_BLENDER',str(executable))
    configure_blender(tmp_path)
    assert not (tmp_path/'artifacts/workbench/local/runtime.json').exists()


def test_missing_blender_fails_before_any_download_or_output(tmp_path):
    with patch('interior.workbench.studio.engine.blender_executable',side_effect=ValueError('找不到 Blender')),patch(
            'interior.workbench.studio.blenderkit_client.download') as download:
        with pytest.raises(ValueError,match='找不到 Blender'):
            execute(tmp_path,'studio.replace',dict(output='runs/interior-studio/job'))
    download.assert_not_called()
    assert not (tmp_path/'runs').exists()
