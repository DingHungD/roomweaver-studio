import os,subprocess
from pathlib import Path
import pytest

def test_installation_candidates_keep_confirmed_dimensions(tmp_path):
    blender=os.environ.get('INTERIOR_BLENDER')
    if not blender:pytest.skip('INTERIOR_BLENDER required')
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([blender,'--background','--factory-startup','--python-exit-code','1','--python',str(root/'tests/fixtures/scene-review/check_installation.py'),'--',str(root/'src/interior/visualization')],capture_output=True,timeout=180)
    (tmp_path/'installation.log').write_bytes(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout[-4000:]+result.stderr[-2000:]
    assert b'INSTALLATION_RETRY_AND_CONFIRMED_DIMENSIONS_PASSED' in result.stdout
