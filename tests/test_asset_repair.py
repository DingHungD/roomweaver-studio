"""Failure feedback, bounded search and safe local movement on unrelated fixtures."""
import copy
from unittest.mock import patch
import pytest
from interior.visualization.asset_placement import local_placement, shifted
from interior.workbench.studio.models import PlacementConstraints
from interior.workbench.studio.asset_repair import feedback, can_research, start_research
from interior.workbench.storage import read_json, write_json
from test_asset_automation import setup

def test_local_shift_clears_collision_without_resizing_or_leaving_region():
    furniture=[[[0,0,0],[1,1,1]]]
    wall=dict(name='fixed wall',bounds=[[.95,0,0],[1.2,1,2]])
    policy=dict(area=[-.4,-.4,1.3,1.3],max_distance=.3,keep_out=[])
    report=local_placement(furniture,[wall],policy)
    assert report['status']=='moved' and report['translation'][0]==pytest.approx(-.05)
    moved=shifted(furniture[0],report['translation'])
    assert [b-a for a,b in zip(*moved)]==[1,1,1]
    assert furniture==[[[0,0,0],[1,1,1]]]

def test_collision_cannot_move_without_area_and_never_enters_keep_out():
    box=[[[0,0,0],[1,1,1]]];wall=dict(name='wall',bounds=[[.9,0,0],[1.2,1,2]])
    with pytest.raises(ValueError,match='尚未設定'):local_placement(box,[wall])
    with pytest.raises(ValueError,match='無安全位置'):local_placement(box,[wall],dict(area=[-.4,-.4,1.3,1.3],max_distance=.3,keep_out=[[-1,-1,2,2]]))
    with pytest.raises(ValueError):PlacementConstraints(max_distance=.2)
    with pytest.raises(ValueError):PlacementConstraints(area=[1,0,0,1])
    assert local_placement(box,[dict(name='floor',bounds=[[-5,-5,-.1],[5,5,0]])])['status']=='clear'

def test_failure_search_is_durable_capped_and_preserves_evidence(tmp_path):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        target=next(t for t in payload['targets'] if t['kind']=='model')
        result=batch.assets.get('ASSETS',target['task_id'])
        row=dict(status='needs_attention',attempts=[dict(asset_id=result['candidates'][0]['asset_id'],error='尺寸不合：W/D/H 100/55/40%')])
        note=feedback(target,row,result)
        assert note['failures'][0]['kind']=='size'
        snapshot=copy.deepcopy(first['scene'])
        assert can_research(target,row,result)
        task=start_research(batch.assets,'ASSETS',identifier,target,row,result,first['revision'])
        saved=read_json(batch.assets.folder('ASSETS')/task/'input.json')
        assert saved['repair']==note and saved['prior_candidates']==result['candidates']
        # Crash after task dispatch, before placement journal: identifier and inputs recover.
        reset=dict(status='needs_attention',attempts=copy.deepcopy(row['attempts']))
        assert start_research(batch.assets,'ASSETS',identifier,target,reset,result,first['revision'])==task
        assert studio.current('ASSETS')['scene']==snapshot
        row['search_round']=2;assert not can_research(target,row,result)
        row['search_round']=0;row['attempts'][-1]['error']='磁碟不足';assert not can_research(target,row,result)
        unknown=copy.deepcopy(target);unknown['context']['group']['name']='anonymous';unknown['context']['concept']=None
        row['attempts']=[];assert not can_research(unknown,row,result)
    finally:jobs.close()

def test_ui_repair_keeps_installed_rows_and_double_click_does_not_restart(tmp_path):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        path=batch.automation.path('ASSETS',identifier);state=read_json(path)
        for t in payload['targets']:state['items'][t['task_id']]=dict(status='needs_attention' if t['kind']=='model' else 'installed',attempts=[])
        state['status']='review';write_json(path,state)
        with patch('interior.workbench.studio.asset_automation.threading.Thread.start'):
            result=batch.automation.repair('ASSETS',identifier,first['revision'])
            state=read_json(path)
            assert sum(r['status']=='researching' for r in state['items'].values())==1
            assert sum(r['status']=='installed' for r in state['items'].values())==1
            research=next(r for r in state['items'].values() if r['status']=='researching')
            task=research['match_task_id']
            batch.automation.repair('ASSETS',identifier,first['revision'])
            assert read_json(path)['items']==state['items']
            assert not jobs.list('ASSETS')
    finally:jobs.close()

def test_research_results_skip_failed_asset_and_stop_interrupts_child(tmp_path):
    from test_asset_matching import FREE,PAID
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        target=next(t for t in payload['targets'] if t['kind']=='model')
        path=batch.automation.path('ASSETS',identifier);state=read_json(path)
        for t in payload['targets']:state['items'][t['task_id']]=dict(status='installed',attempts=[])
        row=state['items'][target['task_id']];row.update(status='needs_attention',attempts=[dict(asset_id=FREE,error='尺寸不合')])
        state['status']='review';write_json(path,state)
        with patch('interior.workbench.studio.asset_automation.threading.Thread.start'):
            batch.automation.repair('ASSETS',identifier,first['revision'])
        state=read_json(path);task=state['items'][target['task_id']]['match_task_id']
        result=batch.assets.get('ASSETS',target['task_id']);old=result['candidates'][0];new=dict(old,asset_id=PAID)
        batch.agents.tasks[task]=dict(id=task,status='passed',candidates=[old,new])
        assert batch.automation.tick('ASSETS',identifier)
        assert read_json(path)['items'][target['task_id']]['asset_id']==PAID
        first_job=jobs.list('ASSETS')[0]
        # Replaying after a lost journal must recover the same job.
        state=read_json(path);state['items'][target['task_id']].pop('job_id');write_json(path,state)
        batch.automation.tick('ASSETS',identifier)
        assert len(jobs.list('ASSETS'))==1 and jobs.list('ASSETS')[0]['id']==first_job['id']
        batch.agents.tasks[task]['status']='running'
        batch.agents.stop=lambda key:batch.agents.tasks[key].update(status='stopping')
        batch.automation.stop('ASSETS',identifier)
        assert batch.agents.tasks[task]['status']=='stopping'
        assert not batch.automation.tick('ASSETS',identifier)
    finally:jobs.close()
