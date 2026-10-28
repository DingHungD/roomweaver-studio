import os
import subprocess
from pathlib import Path
import pytest


def test_rotated_openings_keep_source_dimensions(tmp_path):
    blender=os.environ.get('INTERIOR_BLENDER')
    if not blender:pytest.skip('INTERIOR_BLENDER required')
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([blender,'--background','--factory-startup','--python-exit-code','1','--python',str(root/'tests/fixtures/scene-review/check_openings.py'),'--',str(root/'src/interior/visualization')],capture_output=True,timeout=180)
    (tmp_path/'openings.log').write_bytes(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout[-3000:]
    assert b'OPENING_ASSEMBLIES_PASSED' in result.stdout

    assert b'OPENING_CAMERA_RECOVERY_PASSED' in result.stdout
