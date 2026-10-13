"""Agent generation is bounded data; failed geometry gets at most three checked versions."""
import json
import copy
import pytest
from interior.workbench.studio.parametric_assets import recipe,run_generation,SUPPORTED
from interior.visualization.generated_parts import parts

class Client:
    def __init__(self,**options):self.options=options
    def run(self,*args,**kwargs):return {'text':json.dumps(dict(reason='保留用途與必要結構',**self.options))}

def target(purpose='cabinet',source='unknown'):
    return dict(kind='model',context=dict(group=dict(name=purpose,asset_requirements=dict(purpose=purpose,
        dimension_source=source,dimensions=[1,.6,1.8],evidence='D1' if source=='confirmed' else ''))))

@pytest.mark.parametrize('purpose',sorted(SUPPORTED))
def test_all_supported_furniture_has_bounded_semantic_geometry(purpose):
    r=recipe(target(purpose));assert r and r['purpose']==purpose
    geometry=parts(purpose,{})
    assert 2<=len(geometry)<=100
    for p in geometry:
        assert min(p['size'])>0
        for axis in range(3):
            lower,upper=(-.5,.5) if axis<2 else (0,1)
            assert p['center'][axis]-p['size'][axis]/2>=lower-1e-8
            assert p['center'][axis]+p['size'][axis]/2<=upper+1e-8
    if purpose=='bunk_bed':
        names=[p['name'] for p in geometry]
        assert names.count('mattress')==2 and 'upper guard rail' in names and 'ladder rung' in names

def test_agent_cannot_change_dimensions_by_code_or_ignore_confirmed_numbers(tmp_path):
    base=recipe(target(source='confirmed'))
    with pytest.raises(ValueError):run_generation(Client(python='delete everything'),tmp_path,dict(recipe=base),'fake',lambda _:None,lambda _:None)
    with pytest.raises(ValueError,match='確認尺寸'):run_generation(Client(inset_x=.03),tmp_path,dict(recipe=base,failures=['碰撞']), 'fake',lambda _:None,lambda _:None)
    soft=recipe(target());before=copy.deepcopy(soft)
    result=run_generation(Client(inset_x=.03),tmp_path,dict(recipe=soft,failures=['碰撞：左牆']), 'fake',lambda _:None,lambda _:None)
    assert result['recipe']['dimensions']==[.94,.6,1.8] and soft==before

def test_generation_replay_and_three_attempt_cap_preserve_case(tmp_path):
    from test_asset_automation import setup
    from interior.workbench.storage import read_json,write_json
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        path=batch.automation.path('ASSETS',identifier)
        payload['settings']['procedural_fallback']=True;write_json(path.parent/'input.json',payload)
        t=next(t for t in payload['targets'] if t['kind']=='model')
        t['context']['dimensions_metres']=[2,.9,.85]
        write_json(path.parent/'input.json',payload)
        write_json(batch.assets.folder('ASSETS')/t['task_id']/'result.json',dict(status='passed',candidates=[]))
        state=read_json(path);state['items']={x['task_id']:dict(status='installed',attempts=[]) for x in payload['targets'] if x!=t};write_json(path,state)
        ids=[]
        for attempt in range(3):
            batch.automation.tick('ASSETS',identifier)
            state=read_json(path);row=state['items'][t['task_id']];agent_id=row['generation_task_id'];ids.append(agent_id)
            calls=batch.agents.calls;batch.automation.tick('ASSETS',identifier);assert batch.agents.calls==calls
            base=recipe(t)
            batch.agents.tasks[agent_id].update(status='passed',recipe=dict(base,version=2,source='agent_parametric',design=dict(reason='fixture')))
            batch.automation.tick('ASSETS',identifier)
            state=read_json(path);row=state['items'][t['task_id']];job=jobs.get(row['job_id'])
            # Lost post-submit journal must reuse the same job.
            row.pop('job_id');write_json(path,state);batch.automation.tick('ASSETS',identifier)
            assert len(jobs.list('ASSETS'))==attempt+1
            job.update(status='failed',error='碰撞檢查：牆壁');jobs.write(job)
            batch.automation.tick('ASSETS',identifier)
        batch.automation.tick('ASSETS',identifier)
        state=read_json(path)
        assert len(set(ids))==3 and state['items'][t['task_id']]['status']=='needs_attention'
        assert len(jobs.list('ASSETS'))==3 and studio.current('ASSETS')['revision']==first['revision']
    finally:jobs.close()


def test_invalid_recipe_feedback_is_sent_back_to_agent(tmp_path):
    class RepairClient:
        def __init__(self):self.prompts=[]
        def run(self,prompt,**kwargs):
            self.prompts.append(prompt)
            return {'text':json.dumps(dict(reason='保留尺寸修正參數',inset_x=.03 if len(self.prompts)==1 else 0))}
    client=RepairClient();base=recipe(target(source='confirmed'))
    result=run_generation(client,tmp_path,dict(recipe=base,failures=['碰撞']), 'fake',lambda _:None,lambda _:None)
    assert len(client.prompts)==2 and '生成修正不可變更已確認尺寸' in client.prompts[1]
    assert result['recipe']['dimensions']==base['dimensions']


def test_narration_before_json_is_accepted_but_extra_code_is_not(tmp_path):
    class Narrative:
        def run(self,*args,**kwargs):return {'text':'先依用途設計。\n```json\n'+json.dumps(dict(reason='只有必要櫃體'))+'\n```'}
    result=run_generation(Narrative(),tmp_path,dict(recipe=recipe(target())), 'fake',lambda _:None,lambda _:None)
    assert result['recipe']['design']['reason']=='只有必要櫃體'


def test_missing_generation_retry_is_revision_bound_and_archives_failure(tmp_path):
    from test_asset_automation import setup
    from interior.workbench.storage import read_json,write_json,Conflict
    from unittest.mock import patch
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        runner=batch.automation;path=runner.path('ASSETS',identifier)
        t=next(t for t in payload['targets'] if t['kind']=='model');t['context']['dimensions_metres']=[2,.9,.85]
        write_json(path.parent/'input.json',payload)
        state=read_json(path);state.update(status='review',items={x['task_id']:dict(status='installed',attempts=[]) for x in payload['targets']})
        failure=dict(status='needs_attention',attempts=[],generation_version=2,error='Agent 概念建模未完成：格式錯誤')
        state['items'][t['task_id']]=failure;write_json(path,state)
        with patch.object(runner,'start'):
            runner.generate_missing('ASSETS',identifier,first['revision'])
        saved=read_json(path);row=saved['items'][t['task_id']]
        assert row['force_generate'] and row['previous_passes']==[failure]
        assert all(saved['items'][x['task_id']]['status']=='installed' for x in payload['targets'] if x!=t)
        write_json(path,state)
        scene=copy.deepcopy(first['scene']);scene['design_notes'].append('user changed intent')
        revision=studio.save('ASSETS',scene,first['revision'])
        with pytest.raises(Conflict,match='最新物件規格'):runner.generate_missing('ASSETS',identifier,revision['revision'])
        assert not jobs.list('ASSETS') and read_json(path)==state
    finally:jobs.close()


def test_unused_appliance_fields_can_be_zero_but_necessary_parts_cannot(tmp_path):
    client=Client(shelves=0,seats=0,doors=0,drawers=0)
    assert run_generation(client,tmp_path,dict(recipe=recipe(target('dishwasher'))),'fake',lambda _:None,lambda _:None)['recipe']['purpose']=='dishwasher'
    for purpose in ('bookcase','sofa','wardrobe'):
        with pytest.raises(ValueError):run_generation(client,tmp_path,dict(recipe=recipe(target(purpose))),'fake',lambda _:None,lambda _:None)
