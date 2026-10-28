import json
import pytest
from test_realism import scene
from interior.workbench.studio import completion_fronts as module
from interior.workbench.storage import write_json,read_json

@pytest.mark.parametrize('front',['+Y',None])
def test_native_evidence_only_adds_bound_front(tmp_path,monkeypatch,front):
    original=scene();original['completion_details']=True
    def native(packet,folder):
        assert packet['completion_evidence'] and packet['prepare_only']
        (folder/'a.png').write_bytes(b'fixture')
        write_json(folder/'completion-fronts.json',dict(items=[dict(group_id='desk',signature='b'*64,images=['a.png'],name='desk')]))
        return 0
    class Client:
        def __init__(self,*args):pass
        def run(self,prompt,**kw):
            assert kw['model']=='gpt-6-sol' and len(kw['images'])==1
            return dict(text=json.dumps(dict(front=front,evidence='Visible opening in native front view')))
        def close(self):pass
    monkeypatch.setattr(module,'CodexRuntime',Client)
    result=module.resolve({'agent_model':'gpt-6-sol'},original,tmp_path,native)
    assert result['groups']==original['groups']
    assert bool(result['completion_fronts'])==bool(front)
    assert not original['completion_fronts']
    assert read_json(tmp_path/'functional-fronts/decisions.json')[0]['image_hashes']

def test_native_failure_does_not_call_model(tmp_path,monkeypatch):
    original=scene();original['completion_details']=True
    monkeypatch.setattr(module,'CodexRuntime',lambda *a:pytest.fail('should not call cloud'))
    with pytest.raises(ValueError,match='原生診斷'):
        module.resolve({},original,tmp_path,lambda *a:1)
