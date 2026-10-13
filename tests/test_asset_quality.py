"""Purpose gates must generalize without reading real project records."""
import pytest
from interior.workbench.studio.asset_quality import assess, requirements
from interior.workbench.studio.models import AssetRequirements
from interior.visualization.asset_fit import choose_fit

@pytest.mark.parametrize('target,candidate',[
    ('hob-kitchen','Freestanding Dishwasher'),('dishwasher-kitchen','Integrated washing machine'),
    ('wardrobe-child','Children\'s Bookshelf'),('cabinet-balcony','Outdoor Side Table'),
    ('洗碗機','Washing machine'),('上下舖','Double bed'),('書桌','Coffee Table'),
])
def test_reject_wrong_function_in_any_project(target,candidate):
    q=assess(dict(group=dict(name=target)),dict(name=candidate),'model')
    assert q['status']=='blocked' and q['reasons']

def test_replacement_names_cannot_redefine_target_purpose():
    context=dict(group=dict(name='wardrobe',asset_reference={'name':'Bookshelf'}),parts=[dict(name='Bookshelf')])
    assert requirements(context)['purpose']=='wardrobe'
    assert assess(context,dict(name='Bedroom Closet'),'model')['status']=='eligible'
    assert assess(context,dict(name='Bedroom Closet',warnings=['用途待確認']),'model')['status']=='blocked'

def test_unknown_requires_review_not_guess():
    assert assess(dict(group=dict(name='assembly 819')),dict(name='Chair'),'model')['status']=='blocked'
    assert requirements(dict(group=dict(name='bed')))['dimension_source']=='unknown'
    assert requirements(dict(group=dict(name='bed'),concept=dict(asset='bed')))['dimension_source']=='estimated'

def test_dimension_source_validates_evidence_and_preserves_confirmed_size():
    with pytest.raises(ValueError):AssetRequirements(dimension_source='confirmed',dimensions=[1,1,1])
    policy=AssetRequirements(purpose='bed',dimension_source='confirmed',dimensions=[2,1,1],evidence='client confirmed A-B').model_dump()
    with pytest.raises(ValueError,match='已確認'):choose_fit([2,1,1],[2,1,.5],policy=policy)
    assert policy['dimensions']==(2.,1.,1.)
    _,_,result=choose_fit([2,1,1],[2,1,.5],policy=dict(dimension_source='estimated'))
    assert result==[2,1,.5]
    with pytest.raises(ValueError):choose_fit([2,1,1],[2,1,.5],policy=dict(dimension_source='unknown'))

def test_scope_envelope_is_never_exceeded():
    policy=dict(dimension_source='envelope',dimensions=[1,.8,2],evidence='usable alcove')
    _,_,result=choose_fit([2,2,2],[2,2,3],policy=policy)
    assert all(a<=b for a,b in zip(result,policy['dimensions']))

def test_specific_names_and_explicit_rotation():
    from interior.workbench.studio.asset_quality import classify
    assert classify('TV Stand')=='cabinet'
    assert classify('Television cabinet')=='cabinet'
    assert classify('Desk chair')=='chair'
    assert classify('Vanity with sink')=='vanity'
    angle,_,_=choose_fit([2,1,1],[2,1,1],allow_rotate=False)
    assert angle==0

def test_service_rejects_wrong_candidate_before_job_submission(tmp_path):
    from test_asset_matching import environment,FakeAgents,FREE
    from interior.workbench.studio.asset_matching import AssetMatching,MatchRequest,SelectAsset
    studio,jobs,first=environment(tmp_path)
    try:
        agents=FakeAgents();assets=AssetMatching(studio,agents)
        group=next(g for g in first['scene']['groups'] if 'sofa' in g['children'])
        task=assets.start('ASSETS',MatchRequest(base_revision=first['revision'],group_id=group['id'],operation_id='wrong-purpose'))
        agents.tasks[task['id']]['candidates'][0]['name']='Office chair'
        with pytest.raises(ValueError,match='用途不符'):
            assets.replace('ASSETS',task['id'],SelectAsset(base_revision=first['revision'],asset_id=FREE,operation_id='wrong-purpose-replace',accept_license=True,auto_fit=True))
        assert not jobs.list('ASSETS')
    finally:jobs.close()

def test_automation_skips_incompatible_first_candidate_without_download(tmp_path):
    from test_asset_automation import setup
    from test_asset_matching import PAID
    from interior.workbench.storage import read_json,write_json
    import copy
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        target=next(t for t in payload['targets'] if t['kind']=='model')
        file=batch.assets.folder('ASSETS')/target['task_id']/'result.json';result=read_json(file)
        wrong=copy.deepcopy(result['candidates'][0]);wrong.update(asset_id=PAID,name='Washing machine')
        result['candidates'].insert(0,wrong);write_json(file,result)
        path=batch.automation.path('ASSETS',identifier);state=read_json(path)
        state['items']={t['task_id']:dict(status='installed',attempts=[]) for t in payload['targets'] if t['task_id']!=target['task_id']}
        write_json(path,state);batch.automation.tick('ASSETS',identifier)
        state=read_json(path);row=state['items'][target['task_id']]
        assert row['asset_id']!=PAID and len(row['rejected'])==1 and len(jobs.list('ASSETS'))==1
    finally:jobs.close()
