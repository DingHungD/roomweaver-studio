import os,subprocess
from pathlib import Path
import pytest

def test_four_furniture_types_keep_dimensions_materials_and_sources(tmp_path):
    blender=os.environ.get('INTERIOR_BLENDER')
    if not blender:pytest.skip('INTERIOR_BLENDER required')
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([blender,'--background','--factory-startup','--python',str(root/'tests/fixtures/furniture-review/check_native.py'),'--',str(root/'src/interior/visualization'),str(tmp_path)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300)
    (tmp_path/'blender-test.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    assert result.returncode==0,result.stdout[-6000:]+result.stderr[-2000:]
    assert 'FURNITURE_REVIEW_PASSED' in result.stdout
