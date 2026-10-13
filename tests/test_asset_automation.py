"""Automatic placement covers every target without purchasing or premature cleanup."""
import copy
from unittest.mock import patch
import pytest
from interior.workbench.studio.asset_batch import AssetBatch, BatchRequest, inventory
from interior.workbench.studio.asset_matching import AssetMatching, SelectAsset
from interior.workbench.studio.blenderkit_client import normalize
from interior.workbench.storage import read_json, write_json, Conflict
from test_asset_matching import environment, raw, FREE, PAID
from test_asset_batch import BatchAgents

def setup(tmp_path):
    studio,jobs,first=environment(tmp_path);agents=BatchAgents();assets=AssetMatching(studio,agents);batch=AssetBatch(assets)
    result=batch.start('ASSETS',BatchRequest(base_revision=first['revision'],operation_id='auto-test-all',auto_apply=False,auto_repair=False,procedural_fallback=False))
    identifier=result['id'];path=batch.folder('ASSETS')/identifier
    payload=read_json(path/'input.json')
    for t in payload['targets']:
        a=normalize(raw());a['kind']=t['kind'];a['name']='Synthetic sofa' if t['kind']=='model' else 'Synthetic plaster'
        write_json(batch.assets.folder('ASSETS')/t['task_id']/'result.json',dict(status='passed',candidates=[a]))
    agents.tasks[identifier]['status']='passed'
    write_json(path/'placement.json',dict(status='matching',revision=first['revision'],items={},stop=False))
    return studio,jobs,first,batch,identifier,payload

def test_auto_fallback_and_replay_do_not_skip_targets_or_duplicate_jobs(tmp_path):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    runner=batch.automation
    try:
        target=payload['targets'][0];file=batch.assets.folder('ASSETS')/target['task_id']/'result.json'
        result=read_json(file);backup=copy.deepcopy(result['candidates'][0]);backup['asset_id']=PAID
        result['candidates'].append(backup);write_json(file,result)
        assert runner.tick('ASSETS',identifier)
        job=jobs.list('ASSETS')[0]
        # A lost post-submit journal is recovered by the deterministic operation ID.
        state=read_json(runner.path('ASSETS',identifier));state['items'][target['task_id']].pop('job_id');write_json(runner.path('ASSETS',identifier),state)
        runner.tick('ASSETS',identifier);assert len(jobs.list('ASSETS'))==1
        job.update(status='failed',error='synthetic download failure');jobs.write(job)
        runner.tick('ASSETS',identifier);assert len(jobs.list('ASSETS'))==2
        def adopt(project,jid,revision):
            scene=copy.deepcopy(studio.current(project)['scene']);scene['design_notes'].append('applied '+jid)
            return studio.save(project,scene,revision)
        with patch.object(batch.assets,'adopt',side_effect=adopt):
            job=jobs.list('ASSETS')[0];job['status']='completed';jobs.write(job)
            runner.tick('ASSETS',identifier)
            runner.tick('ASSETS',identifier)
            job=jobs.list('ASSETS')[0];job['status']='completed';jobs.write(job)
            runner.tick('ASSETS',identifier);assert not runner.tick('ASSETS',identifier)
        state=read_json(runner.path('ASSETS',identifier))
        assert state['status']=='review' and len(state['items'])==len(payload['targets'])
        assert all(r['status']=='installed' for r in state['items'].values())
        assert len(state['items'][target['task_id']]['attempts'])==1
        assert len(jobs.list('ASSETS'))==3
    finally:jobs.close()

def test_paid_only_is_not_downloaded_and_confirmation_requires_explicit_keep(tmp_path):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        for target in payload['targets']:
            write_json(batch.assets.folder('ASSETS')/target['task_id']/'result.json',dict(status='passed',candidates=[normalize(raw(PAID,False))]))
        runner=batch.automation
        while runner.tick('ASSETS',identifier):pass
        assert not jobs.list('ASSETS')
        with pytest.raises(Conflict,match='逐項'):runner.confirm('ASSETS',identifier,first['revision'],[])
        result=runner.confirm('ASSETS',identifier,first['revision'],[t['task_id'] for t in payload['targets']])
        assert result['status']=='completed'
        assert batch.get('ASSETS',identifier)['confirmed']
    finally:jobs.close()


def test_agent_failure_stops_placement_even_with_earlier_candidates(tmp_path):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        batch.agents.tasks[identifier].update(status='failed',error='模型不支援')
        assert not batch.automation.tick('ASSETS',identifier)
        result=batch.get('ASSETS',identifier)
        assert result['status']=='failed' and result['error']=='模型不支援'
        assert not jobs.list('ASSETS')
        assert studio.current('ASSETS')['revision']==first['revision']
    finally:jobs.close()


@pytest.mark.parametrize('legacy_pending_job',[False,True])
def test_missing_blender_pauses_and_retries_same_candidate_without_new_search(tmp_path,legacy_pending_job):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        runner=batch.automation
        assert runner.tick('ASSETS',identifier)
        job=jobs.list('ASSETS')[0]
        job.update(status='failed',error='ValueError: 找不到 Blender，請設定 INTERIOR_BLENDER');jobs.write(job)
        assert not runner.tick('ASSETS',identifier)
        state=read_json(runner.path('ASSETS',identifier))
        assert state['status']=='paused' and len(jobs.list('ASSETS'))==1
        # Also exercise recovery of the old version's exhausted-candidates records.
        row=state['items'][payload['targets'][0]['task_id']]
        row['status']='needs_attention';state['status']='review'
        if legacy_pending_job:
            row.update(status='applying',job_id=job['id'],attempts=[])
        write_json(runner.path('ASSETS',identifier),state)
        searches=batch.agents.calls
        with patch('interior.workbench.studio.asset_automation.threading.Thread.start'):
            runner.start('ASSETS',identifier,first['revision'])
        assert runner.tick('ASSETS',identifier)
        assert batch.agents.calls==searches
        state=read_json(runner.path('ASSETS',identifier));row=state['items'][payload['targets'][0]['task_id']]
        assert len(jobs.list('ASSETS'))==2 and row['job_id']!=job['id']
        assert row['asset_id']==row['attempts'][0]['asset_id']
        assert row['attempts'][0]['job_id']==job['id']
    finally:jobs.close()

def test_changed_scene_pauses_and_does_not_override_user_edit(tmp_path):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        scene=copy.deepcopy(first['scene']);scene['groups'][0]['translation']=[2,0,0]
        latest=studio.save('ASSETS',scene,first['revision'])
        assert not batch.automation.tick('ASSETS',identifier)
        assert read_json(batch.automation.path('ASSETS',identifier))['status']=='paused'
        assert studio.current('ASSETS')['revision']==latest['revision'] and not jobs.list('ASSETS')
    finally:jobs.close()

def test_alternative_stays_valid_after_same_list_replacement(tmp_path):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        target=next(t for t in payload['targets'] if t['kind']=='model')
        scene=copy.deepcopy(first['scene']);g=next(g for g in scene['groups'] if g['id']==target['group_id'])
        a=normalize(raw());g['asset_reference']={k:a[k] for k in ('asset_id','version_id','url','name','kind','license','is_free')}
        g['asset_reference'].update(task_id=target['task_id'],status='applied')
        g['translation']=[3,0,0]
        saved=studio.save('ASSETS',scene,first['revision'])
        body=SelectAsset(base_revision=saved['revision'],asset_id=FREE,operation_id='choose-alternate',accept_license=True)
        assert batch.assets.replace('ASSETS',target['task_id'],body)['status']=='queued'
    finally:jobs.close()

def test_inventory_uses_children_and_never_replaces_window_geometry(tmp_path):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        scene=copy.deepcopy(first['scene']);g=scene['groups'][0];g['name']='unnamed assembly';g['method']='individual'
        for o in scene['objects']:
            if o['id'] in g['children']:o['name']='chair seat'
        assert inventory(scene)[0]['category']=='chair'
        g['name']='window';assert inventory(scene)[0]['category']=='surface'
    finally:jobs.close()

def test_confirm_cleans_failed_owned_downloads_but_not_unrelated_results(tmp_path):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        runner=batch.automation;path=runner.path('ASSETS',identifier)
        state=read_json(path);state['status']='review'
        for index,target in enumerate(payload['targets']):
            job=jobs.submit_studio('ASSETS','replace',dict(revision=first['revision']),'failed-attempt-'+str(index))
            folder=studio.root('ASSETS')/job['output'];folder.mkdir(parents=True)
            (folder/'asset.blend').write_bytes(b'failed unused asset')
            job.update(status='failed');jobs.write(job)
            if index==0:state['items'][target['task_id']]=dict(status='needs_attention',attempts=[dict(job_id=job['id'],asset_id=FREE)])
        write_json(path,state)
        owned=studio.root('ASSETS')/jobs.list('ASSETS')[-1]['output']/'asset.blend'
        with pytest.raises(Conflict):runner.confirm('ASSETS',identifier,first['revision'],[])
        assert owned.exists()
        result=runner.confirm('ASSETS',identifier,first['revision'],[t['task_id'] for t in payload['targets']])
        assert result['bytes_freed']==len(b'failed unused asset') and not owned.exists()
        assert (folder/'asset.blend').exists()  # unrelated unadopted job remains
        assert all((batch.assets.folder('ASSETS')/t['task_id']/'result.json').exists() for t in payload['targets'])
    finally:jobs.close()
