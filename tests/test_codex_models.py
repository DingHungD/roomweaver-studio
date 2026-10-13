"""Catalog selection and batch failures must not masquerade as empty search results."""
import json
from unittest.mock import patch
import pytest
from interior.workbench.agent_runtime.codex import CodexRuntime, ModelAccessError, select_model, turn_error
from interior.workbench.agent_runtime.service import AgentTasks
from interior.workbench.studio.asset_batch import run_batch
from interior.workbench.storage import read_json, write_json


CATALOG = dict(authenticated=True, auth_type='chatgpt', version='test', models=[
    dict(id='catalog-id', model='inference-model', isDefault=True, inputModalities=['text','image'])])


def test_default_and_catalog_alias_use_inference_model():
    assert select_model(CATALOG)['model']=='inference-model'
    assert select_model(CATALOG,'catalog-id')==select_model(CATALOG,'inference-model')
    with pytest.raises(ModelAccessError,match='重新檢查'):
        select_model(CATALOG,'unsupported-model')
    with pytest.raises(ModelAccessError):select_model(dict(models=[]))


def test_status_reads_all_model_pages_without_auth_details():
    runtime=object.__new__(CodexRuntime);runtime.version='test'
    with patch.object(runtime,'request',side_effect=[{'account':{'type':'chatgpt','email':'private'}},
            {'data':[],'nextCursor':'next'},{'data':CATALOG['models'],'nextCursor':None}]) as rpc:
        result=runtime.status()
    assert result['default_model']=='inference-model'
    assert 'private' not in json.dumps(result)
    assert rpc.call_args_list[-1].args==('model/list',{'cursor':'next'})


def test_nested_rejection_is_actionable_and_not_a_search_failure():
    error={'message':json.dumps({'error':{'message':"The 'bad' model is not supported when using Codex with a ChatGPT account."}})}
    exc=turn_error(error,'bad')
    assert isinstance(exc,ModelAccessError)
    assert '不代表找不到素材' in str(exc) and 'Agent 與能力測試' in str(exc)
    assert str(turn_error({'message':'ordinary failure'},'ok'))=='Codex 任務未完成：ordinary failure'


@pytest.mark.parametrize('rejected',[True,False])
def test_batch_preflight_resolves_default_once_and_blocks_search_on_rejection(tmp_path,rejected):
    calls=[]
    class Runtime:
        def __init__(self,directory):pass
        def status(self):return CATALOG
        def run(self,prompt,**kwargs):
            calls.append(kwargs['model'])
            if rejected:raise ModelAccessError('帳號拒絕此模型')
            return dict(text='STUDIO_READY',model=kwargs['model'])
        def close(self):pass
    agents=AgentTasks(tmp_path)
    task=dict(id='a'*32,kind='asset_batch',model=None,status='queued')
    write_json(agents.root/task['id']/'task.json',task)
    targets=[dict(task_id=str(i),result_path=str(tmp_path/f'{i}.json')) for i in range(3)]
    for t in targets:write_json(t['result_path'],dict(id=t['task_id'],status='queued'))
    with patch('interior.workbench.agent_runtime.service.CodexRuntime',Runtime),patch(
            'interior.workbench.studio.asset_batch.run_batch',return_value={}) as batch:
        agents._run(task,dict(targets=targets))
    result=agents.get(task['id'])
    assert calls==['inference-model'] and result['model']=='inference-model'
    assert result['status']==('failed' if rejected else 'passed')
    assert batch.call_count==(0 if rejected else 1)
    if rejected:
        assert all(read_json(t['result_path'])['status']=='failed' for t in targets)


def test_access_rejection_during_batch_does_not_retry_or_search_other_objects(tmp_path):
    targets=[dict(task_id=str(i),name=f'Object {i}',result_path=str(tmp_path/f'{i}.json')) for i in range(3)]
    with patch('interior.workbench.studio.asset_batch.run_matching',side_effect=ModelAccessError('model not supported')) as match:
        with pytest.raises(ModelAccessError):run_batch(None,tmp_path,dict(targets=targets),'model',lambda p:None,None)
    assert match.call_count==1 and not (tmp_path/'1.json').exists()
