from unittest.mock import patch
import os
import pytest
from interior.workbench.storage import write_json,read_json

def test_windows_transient_share_denial_retries_same_atomic_write(tmp_path):
    target=tmp_path/'state.json';write_json(target,{'version':1})
    denied=PermissionError('temporarily shared');denied.winerror=32
    real=os.replace;calls=[]
    def replace(a,b):
        calls.append((a,b))
        assert read_json(target)=={'version':1}
        if len(calls)<3:raise denied
        real(a,b)
    with patch('interior.workbench.storage.os.replace',side_effect=replace),patch('interior.workbench.storage.time.sleep'):
        write_json(target,{'version':2})
    assert read_json(target)=={'version':2} and len({a for a,b in calls})==1
    assert not list(tmp_path.glob('*.tmp'))

def test_permanent_write_failure_leaves_old_state_and_surfaces_error(tmp_path):
    target=tmp_path/'state.json';write_json(target,{'version':1})
    with patch('interior.workbench.storage.os.replace',side_effect=PermissionError('permanent')),pytest.raises(PermissionError):
        write_json(target,{'version':2})
    assert read_json(target)=={'version':1}
