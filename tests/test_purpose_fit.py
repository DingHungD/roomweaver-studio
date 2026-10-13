"""Unknown boxes, confirmed products and fit-policy replay have different contracts."""
import copy
from unittest.mock import patch
import pytest
from interior.visualization.asset_fit import choose_fit, fit_report


@pytest.mark.parametrize('purpose,target,asset',[
    ('sofa',[2,.9,1],[2,.9,.78]),
    ('television',[1.5,.25,1.55],[1.3,.04,.75]),
    ('sink',[.8,.55,.9],[.75,.5,.25]),
    ('bed',[2.1,1.6,1.5],[2.0,1.5,.8]),
    ('bookcase',[.6,.35,.95],[.58,.3,1.2]),
])
def test_unknown_height_is_not_a_fixed_target(purpose,target,asset):
    policy=dict(purpose=purpose,dimension_source='unknown',dimensions=target)
    before=copy.deepcopy(policy);_,scale,result=choose_fit(target,asset,policy=policy,allow_rotate=False)
    assert scale==1 and result==asset and policy==before
    assert fit_report(target,result,policy)['height_reference_only']


def test_confirmed_size_wins_over_stale_preview_and_never_relaxes():
    p=dict(purpose='cabinet',dimension_source='confirmed',dimensions=[1,.5,1],evidence='D1')
    assert choose_fit([.8,.4,.8],[1,.5,1],policy=p)[2]==[1,.5,1]
    with pytest.raises(ValueError,match='已確認'):choose_fit([1,.5,1],[1,.5,.78],policy=p)


def test_envelope_can_be_underfilled_but_not_exceeded():
    p=dict(purpose='television',dimension_source='envelope',dimensions=[1.5,.3,1.5],evidence='wall area')
    _,_,r=choose_fit([2,2,2],[1.4,.04,.8],policy=p)
    assert all(x<=y+1e-9 for x,y in zip(r,p['dimensions']))


def test_functional_height_rejects_miniature_desk_but_accepts_low_table():
    for source in ('unknown','estimated'):
        with pytest.raises(ValueError,match='用途尺寸'):choose_fit([1,.6,1],[1,.6,.3],policy=dict(purpose='desk',dimension_source=source))
        assert choose_fit([1,.6,1],[1,.6,.3],policy=dict(purpose='table',dimension_source=source))[2][2]==.3


def test_retry_upgrade_is_once_and_preserves_success_keep_and_non_size_failures(tmp_path):
    from test_asset_automation import setup
    from interior.workbench.storage import read_json,write_json
    from interior.workbench.studio.asset_automation import size_retry_targets
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        path=batch.automation.path('ASSETS',identifier)
        target=next(t for t in payload['targets'] if t['kind']=='model')
        state=read_json(path);state.update(status='review',quality_version=1)
        state['items']={t['task_id']:dict(status='installed',attempts=[]) for t in payload['targets']}
        state['items'][target['task_id']]=dict(status='needs_attention',attempts=[dict(asset_id='old',error='尺寸改造超過 50%')],search_round=2,generated=True)
        write_json(path,state)
        assert len(size_retry_targets(payload,state))==1
        with patch('threading.Thread.start'):
            batch.automation.start('ASSETS',identifier,first['revision'])
            batch.automation.start('ASSETS',identifier,first['revision'])
        after=read_json(path);row=after['items'][target['task_id']]
        assert row['generation']==1 and row['attempts']==[] and len(row['previous_passes'])==1
        assert not size_retry_targets(payload,after)
        for t in payload['targets']:
            if t['task_id']!=target['task_id']:assert after['items'][t['task_id']]==state['items'][t['task_id']]
        state['items'][target['task_id']]['attempts']=[dict(error='碰撞：牆壁')]
        assert not size_retry_targets(payload,state)
    finally:jobs.close()
