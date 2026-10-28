"""Native Blender material previews and triangle support on unrelated synthetic scenes."""
import os,subprocess
from pathlib import Path
import pytest

def test_three_decor_types_on_translated_rotated_supports(tmp_path):
    script=Path(__file__).parents[1]/'fixtures/decor-review/check_native.py'
    root=Path(__file__).parents[2]
    result=subprocess.run([os.environ['INTERIOR_BLENDER'],'--background','--factory-startup','--python',str(script),'--',str(root/'src/interior/visualization'),str(tmp_path)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=240)
    (tmp_path/'blender-test.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    assert result.returncode==0 and 'DECOR_TEST_PASSED' in result.stdout,result.stdout[-5000:]+result.stderr[-2000:]
    for kind in ('vase','books','tableware'):
        assert (tmp_path/kind/'decor-object.png').stat().st_size>1000
        assert (tmp_path/kind/'decor-context.png').stat().st_size>1000
