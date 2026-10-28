import os
import subprocess
from pathlib import Path
import pytest

def test_native_finish_preserves_original_material_and_geometry(tmp_path):
    blender=os.environ.get('INTERIOR_BLENDER')
    if not blender:pytest.skip('INTERIOR_BLENDER required')
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([blender,'--background','--factory-startup','--python-exit-code','1','--python',str(root/'tests/fixtures/scene-review/check_realism.py'),'--',str(root/'src/interior/visualization')],capture_output=True,timeout=180)
    (tmp_path/'realism-native.log').write_bytes(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout[-4000:]
    assert b'REALISM_FINISH_PRESERVATION_PASSED' in result.stdout
