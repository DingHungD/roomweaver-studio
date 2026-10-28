import os,subprocess
from pathlib import Path
import pytest

def test_fixture_mount_native_contact_recess_pendant_and_structure_rejection(tmp_path):
    blender=os.environ.get('INTERIOR_BLENDER')
    if not blender:pytest.skip('INTERIOR_BLENDER required')
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([blender,'-b','--factory-startup','--python-exit-code','1','--python',str(root/'tests/fixtures/fixture-installation/check_mount.py'),'--',str(root/'src/interior/visualization')],capture_output=True,timeout=120)
    (tmp_path/'fixture.log').write_bytes(result.stdout+result.stderr)
    assert result.returncode==0,(result.stdout+result.stderr)[-4000:]
    assert b'FIXTURE_INSTALLATION_PASSED' in result.stdout


def test_imported_light_output_exports_emission_without_changing_native_material(tmp_path):
    blender=os.environ.get('INTERIOR_BLENDER')
    if not blender:pytest.skip('INTERIOR_BLENDER required')
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([blender,'-b','--factory-startup','--python-exit-code','1','--python',str(root/'tests/fixtures/fixture-installation/check_preview.py'),'--',str(root/'src/interior/visualization'),str(tmp_path)],capture_output=True,timeout=120)
    (tmp_path/'preview-emission.log').write_bytes(result.stdout+result.stderr)
    assert result.returncode==0,(result.stdout+result.stderr)[-6000:]
    assert b'FIXTURE_PREVIEW_EMISSION_PASSED' in result.stdout
