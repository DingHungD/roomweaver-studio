"""Generic specification preview, immutable dimensions and bounded Agent suggestions."""
import copy
from unittest.mock import patch
import pytest
from interior.workbench.studio.object_specs import preview, save, SpecificationInput, suggest_front, edited_bounds, run_understanding
from interior.workbench.studio.asset_quality import requirements
from interior.workbench.studio.models import ObjectSpecification
from interior.workbench.storage import Conflict
from test_asset_matching import environment

def test_front_is_a_suggestion_and_corner_stays_unknown():
    box=[[1,1,0],[2,2,1]]
    assert suggest_front(box,[[[.8,1,0],[.99,2,3]]],'cabinet')['front']=='+X'
    assert suggest_front(box,[[[.8,1,0],[.99,2,3]],[[1,.8,0],[2,.99,3]]],'cabinet')['front']=='unknown'
    assert suggest_front(box,[],'table')['front']=='multiple'
    assert suggest_front(box,[],None)['front']=='unknown'
    assert suggest_front(box,[[[.8,1,0],[.99,2,3]]],'cabinet',[[[2.1,1,0],[3,2,1]]])['front']=='unknown'
    lo,hi=edited_bounds([[0,0,0],[1,2,1]],dict(rotation=90,translation=[3,0,0]))
    assert lo==pytest.approx([1,0,0]) and hi==pytest.approx([3,1,1])

def test_preview_and_save_do_not_rewrite_dimensions_geometry_or_materials(tmp_path):
    studio,jobs,first=environment(tmp_path)
    try:
        scene=copy.deepcopy(first['scene']);g=scene['groups'][0]
        g['asset_requirements']=dict(purpose='chair',dimension_source='confirmed',dimensions=[.5,.6,.9],evidence='synthetic dimension D1')
        current=studio.save('ASSETS',scene,first['revision']);before=copy.deepcopy(current)
        report=preview(studio,'ASSETS',current['revision']);row=next(r for r in report['items'] if r['group_id']==g['id'])
        assert row['dimensions']==[.5,.6,.9] and row['dimension_source']=='confirmed'
        assert studio.current('ASSETS')==before
        body=SpecificationInput(base_revision=current['revision'],specifications={g['id']:ObjectSpecification(purpose='chair',front='+Y',front_source='user')})
        saved=save(studio,'ASSETS',body)
        stripped=copy.deepcopy(saved['scene'])
        for group in stripped['groups']:group['object_specification']=None
        assert stripped==current['scene']
        with pytest.raises(Conflict):save(studio,'ASSETS',body)
        with pytest.raises(ValueError,match='已確認用途'):
            save(studio,'ASSETS',SpecificationInput(base_revision=saved['revision'],specifications={g['id']:ObjectSpecification(purpose='sofa')}))
    finally:jobs.close()

def test_agent_cannot_replace_known_purpose_or_modify_dimensions():
    source=dict(base_revision='a'*32,items=[dict(group_id='chair',structural=False,specification=dict(purpose='chair'),dimensions=[.5,.6,.9],issues=[]),dict(group_id='unknown',structural=False,specification=dict(purpose=''),dimensions=[1,2,3],issues=['用途待確認'])])
    class Client:
        def run(self,*a,**k):return {'text':'{"items":[{"group_id":"chair","purpose":"sofa","confidence":"high"},{"group_id":"unknown","purpose":"cabinet","confidence":"low"}]}'}
    result=run_understanding(Client(),None,dict(preview=source),'test',lambda _:None,lambda _:None)['preview']
    assert result['items'][0]['specification']['purpose']=='chair'
    assert result['items'][1]['specification']['purpose']==''
    assert result['items'][0]['dimensions']==[.5,.6,.9] and 'agent_complete' not in source

def test_required_purpose_has_priority_over_suggestion():
    req=requirements({'group':{'name':'unknown','asset_requirements':{'purpose':'bed','dimension_source':'confirmed','dimensions':[1,2,1],'evidence':'D2'},'object_specification':{'purpose':'sofa'}}})
    assert req['purpose']=='bed' and req['dimensions']==[1,2,1]
    with pytest.raises(ValueError):ObjectSpecification(material_policy='specified')

def test_saved_specification_reaches_batch_search_without_changing_confirmed_sizes(tmp_path):
    from interior.workbench.studio.asset_batch import AssetBatch, BatchRequest, select_targets
    from interior.workbench.studio.asset_matching import AssetMatching
    from test_asset_batch import BatchAgents
    from interior.workbench.storage import read_json
    studio,jobs,first=environment(tmp_path)
    try:
        group=first['scene']['groups'][0]
        current=save(studio,'ASSETS',SpecificationInput(base_revision=first['revision'],specifications={group['id']:ObjectSpecification(purpose='chair',front='+X',front_source='user')}))
        batches=AssetBatch(AssetMatching(studio,BatchAgents()))
        body=BatchRequest(base_revision=current['revision'],operation_id='specification-test',auto_apply=False)
        task=batches.start('ASSETS',body)
        payload=read_json(batches.folder('ASSETS')/task['id']/'input.json')
        context=next(t['context'] for t in payload['targets'] if t['group_id']==group['id'])
        assert context['group']['object_specification']['front']=='+X'
        assert context['design_specification']['dimensions']==context['dimensions_metres']
        original=copy.deepcopy(current['scene']);original['groups'][0]['object_specification']['material_policy']='original'
        selected=select_targets(original,BatchRequest(base_revision=current['revision'],operation_id='original-material',description='bright red'))
        assert 'bright red' not in selected[0]['description'] and '沿用原物件材質' in selected[0]['description']
    finally:jobs.close()
