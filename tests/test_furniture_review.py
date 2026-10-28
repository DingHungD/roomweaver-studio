"""New-project furniture adoption requires job-bound evidence and bounded repairs."""
import hashlib
from unittest.mock import patch
import pytest
from interior.workbench.storage import read_json,write_json
from interior.workbench.studio.decor_review import run_review
from interior.workbench.studio.model_repair import request_repair,advance
from test_asset_automation import setup


def evidence(studio,job):
    folder=studio.root('ASSETS')/job['output'];names=['model-object.png','model-reverse.png','model-context.png']
    folder.mkdir(parents=True,exist_ok=True)
    for name in names:(folder/name).write_bytes(b'synthetic evidence')
    write_json(folder/'replacement-report.json',dict(model_check=dict(status='passed'),visual_review=dict(version=2,images=names)))
    return {name:hashlib.sha256(b'synthetic evidence').hexdigest() for name in names}


@pytest.mark.parametrize('status',['pass','retry','uncertain'])
def test_every_furniture_requires_review_before_adoption(tmp_path,status):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        runner=batch.automation;target=next(t for t in payload['targets'] if t['kind']=='model')
        payload['targets']=[target];path=runner.path('ASSETS',identifier);write_json(path.parent/'input.json',payload)
        runner.tick('ASSETS',identifier);job=jobs.list('ASSETS')[0];job['status']='completed';jobs.write(job)
        with patch.object(runner.assets,'adopt') as adopt:
            # Missing evidence cannot silently adopt even though Blender completed.
            assert not runner.tick('ASSETS',identifier);adopt.assert_not_called()
            state=read_json(path);assert state['status']=='paused'
            state.update(status='applying');write_json(path,state);hashes=evidence(studio,job)
            assert runner.tick('ASSETS',identifier);adopt.assert_not_called()
            state=read_json(path);row=state['items'][target['task_id']];task=row['review_task_id']
            batch.agents.tasks[task].update(status='passed',job_id=job['id'],image_hashes=hashes,verdict=dict(status=status,issues=[] if status=='pass' else ['purpose'],reason='synthetic chair inspection'))
            adopt.return_value=first;runner.tick('ASSETS',identifier)
            assert adopt.call_count==(1 if status=='pass' else 0)
            assert studio.current('ASSETS')['revision']==first['revision']
    finally:jobs.close()


def test_proportion_retry_reuses_candidate_once_and_protects_dimensions(tmp_path):
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        target=next(t for t in payload['targets'] if t['kind']=='model');runner=batch.automation;path=runner.path('ASSETS',identifier)
        item=read_json(batch.assets.folder('ASSETS')/target['task_id']/'result.json')['candidates'][0]
        job=jobs.submit_studio('ASSETS','replace',dict(revision=first['revision']),'failed-original')
        row=dict(status='waiting',asset_id=item['asset_id'],attempts=[dict(job_id=job['id'],asset_id=item['asset_id'],error='比例過大',check=dict(issues=['proportion']))])
        request_repair(row,'比例過大');state=read_json(path);state['items'][target['task_id']]=row
        assert advance(runner,'ASSETS',identifier,target,row,state,path,payload,target['task_id'])
        task=row['adjust_task_id'];batch.agents.tasks[task].update(status='passed',repair=dict(can_repair=True,scale=.9,fit='uniform',reason='依估計範圍縮小10%'))
        with patch.object(runner.assets,'candidate',return_value=(first,target,item)):
            assert advance(runner,'ASSETS',identifier,target,row,state,path,payload,target['task_id'])
        assert row['job_id']!=job['id'] and row['adjustment']['scale']==.9
        assert not row.get('pending_adjust');request_repair(row,'仍過大');assert not row.get('pending_adjust')
        from interior.workbench.studio.selected_repair import validate_plan
        with pytest.raises(ValueError,match='已確認'):
            validate_plan(dict(scale=.9,reason='不可縮小'),dict(dimension_source='confirmed',purpose='chair'))
    finally:jobs.close()


def test_three_views_are_sent_with_structural_and_direction_requirements(tmp_path):
    paths=[tmp_path/n for n in ('model-object.png','model-reverse.png','model-context.png')]
    for path in paths:path.write_bytes(b'fixture')
    class Client:
        def run(self,prompt,**kwargs):
            assert kwargs['images']==paths and '椅子座面' in prompt and 'unknown' in prompt
            return dict(text='{"status":"retry","issues":["structure"],"reason":"缺少座面","observed_purpose":"chair","feature_results":{"seat":"fail","support":"pass"}}')
    result=run_review(Client(),tmp_path,dict(images=paths,job_id='job',requirements=dict(purpose='chair')),None,lambda _:None,None)
    assert result['verdict']['issues']==['structure'] and len(result['image_hashes'])==3


def test_dresser_means_makeup_table_and_cannot_pass_as_storage(tmp_path):
    from interior.workbench.studio.asset_quality import assess,classify
    context=dict(group=dict(name='dresser',asset_requirements=dict(purpose='dresser')))
    assert assess(context,dict(name='Small Dresser'),'model')['status']=='blocked'
    assert assess(context,dict(name='Makeup vanity table'),'model')['status']=='eligible'
    assert classify('Chest of drawers')=='cabinet' and classify('Bathroom vanity')=='vanity'
    assert classify('Make up table')=='dresser'
    images=[tmp_path/n for n in ('object.png','reverse.png','context.png')]
    for p in images:p.write_bytes(b'fixture')
    class Client:
        def run(self,prompt,**kwargs):
            assert '膝腿空間' in prompt
            return dict(text='{"status":"pass","issues":[],"reason":"衣櫃外觀完整","observed_purpose":"wardrobe","feature_results":{"worktop":"pass","knee_space":"fail","mirror":"fail"}}')
    review=run_review(Client(),tmp_path,dict(images=images,job_id='job',requirements=dict(purpose='dresser')),None,lambda _:None,None)
    assert review['verdict']['status']=='retry' and review['verdict']['issues']==['purpose','structure']


@pytest.mark.parametrize('label',['makeup_vanity_table','dressing_table','Make up table'])
def test_observed_purpose_synonyms_are_not_false_defects(tmp_path,label):
    import json
    images=[tmp_path/n for n in ('object.png','reverse.png','context.png')]
    for p in images:p.write_bytes(b'fixture')
    class Client:
        def run(self,prompt,**kwargs):
            return dict(text=json.dumps(dict(status='pass',issues=[],reason='鏡子、桌面、腿部空間可見',observed_purpose=label,feature_results=dict(worktop='pass',knee_space='pass',mirror='pass'))))
    review=run_review(Client(),tmp_path,dict(images=images,job_id='job',requirements=dict(purpose='dresser')),None,lambda _:None,None)
    assert review['verdict']['status']=='pass' and review['verdict']['observed_purpose']=='dresser'
