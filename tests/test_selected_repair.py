"""Selected-candidate repair preserves identity, intent, revisions and bounded retries."""
import copy
import json
from unittest.mock import patch
import pytest
from test_asset_automation import setup
from interior.workbench.studio.selected_repair import SelectedRepair,AssistedSelection,validate_plan,run_repair
from interior.workbench.storage import read_json,write_json,Conflict

def prepare(tmp_path):
    studio,jobs,rev,batches,identifier,payload=setup(tmp_path)
    target=next(t for t in payload['targets'] if t['kind']=='model')
    result=batches.assets.get('ASSETS',target['task_id']);asset=result['candidates'][0]
    runner=SelectedRepair(batches.assets)
    body=AssistedSelection(base_revision=rev['revision'],asset_id=asset['asset_id'],accept_license=True,operation_id='manual-fixture')
    with patch.object(runner,'launch'):
        flow=runner.start('ASSETS',target['task_id'],body)
    return studio,jobs,batches,runner,flow,body,target

def test_repair_guards_confirmed_dimensions_and_unsupported_deformation():
    with pytest.raises(ValueError):validate_plan(dict(scale=.9,reason='shrink'),dict(dimension_source='confirmed',purpose='cabinet'))
    with pytest.raises(ValueError):validate_plan(dict(fit='adapt',reason='stretch'),dict(dimension_source='unknown',purpose='cabinet'))
    with pytest.raises(ValueError):validate_plan(dict(fit='adapt',reason='stretch'),dict(dimension_source='confirmed',purpose='sofa'))
    assert validate_plan(dict(scale=.9,reason='collision'),dict(dimension_source='unknown',purpose='sofa')).scale==.9

def test_selected_repair_replays_jobs_and_retries_only_same_candidate(tmp_path):
    studio,jobs,batches,runner,flow,body,target=prepare(tmp_path)
    try:
        p=runner.path('ASSETS',flow['id'])
        runner.tick('ASSETS',flow['id']);s=read_json(p);job=jobs.get(s['job_id'])
        assert job['source_revision']==body.base_revision
        s.pop('job_id');write_json(p,s);runner.tick('ASSETS',flow['id']);assert len(jobs.list('ASSETS'))==1
        for index,scale in enumerate((.94,.88)):
            s=read_json(p);job=jobs.get(s['job_id']);job.update(status='failed',error='碰撞檢查：牆壁');jobs.write(job)
            runner.tick('ASSETS',flow['id']);s=read_json(p);task=s['agent_task_id'];count=batches.agents.calls
            runner.tick('ASSETS',flow['id']);assert batches.agents.calls==count
            batches.agents.tasks[task].update(status='passed',repair=dict(can_repair=True,scale=scale,fit='uniform',reason='避開牆壁'))
            runner.tick('ASSETS',flow['id']);s=read_json(p)
            request=read_json(jobs.store.state_dir/'jobs'/s['job_id']/'request.json')
            assert request['parameters']['asset']['asset_id']==body.asset_id
            assert request['parameters']['repair_scale']==scale
        s=read_json(p);job=jobs.get(s['job_id']);job.update(status='failed',error='碰撞檢查：牆壁');jobs.write(job)
        assert not runner.tick('ASSETS',flow['id']);s=read_json(p)
        assert s['status']=='needs_attention' and len(s['attempts'])==3 and len(jobs.list('ASSETS'))==3
        assert studio.current('ASSETS')['revision']==body.base_revision
    finally:jobs.close()

def test_selected_repair_stop_and_stale_scene_never_adopt(tmp_path):
    studio,jobs,batches,runner,flow,body,target=prepare(tmp_path)
    try:
        runner.tick('ASSETS',flow['id']);s=read_json(runner.path('ASSETS',flow['id']));job=jobs.get(s['job_id'])
        scene=copy.deepcopy(studio.current('ASSETS')['scene']);scene['design_notes'].append('user edit')
        newer=studio.save('ASSETS',scene,body.base_revision)
        job.update(status='completed');jobs.write(job)
        with pytest.raises(Conflict):runner.tick('ASSETS',flow['id'])
        runner.stop('ASSETS',flow['id']);assert not runner.tick('ASSETS',flow['id'])
        assert studio.current('ASSETS')['revision']==newer['revision']
    finally:jobs.close()

def test_agent_can_decline_or_correct_invalid_plan(tmp_path):
    class Client:
        calls=0
        def run(self,prompt,**kwargs):
            self.calls+=1
            return dict(text=json.dumps(dict(scale=.9 if self.calls==1 else 1,can_repair=False,reason='確認尺寸禁止縮小')))
    client=Client();result=run_repair(client,tmp_path,dict(requirements=dict(dimension_source='confirmed',purpose='cabinet')),'fake',lambda _:None,lambda _:None)
    assert client.calls==2 and result['repair']['can_repair'] is False
