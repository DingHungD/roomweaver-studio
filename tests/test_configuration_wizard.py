"""Wizard contracts: validation is server-side, searches bounded, fallback honest."""
import copy
import threading
from pathlib import Path
from unittest.mock import patch
import pytest
from interior.workbench.studio.asset_batch import BatchRequest,AssetBatch,select_targets,run_batch,DEFAULT_STYLE
from interior.workbench.studio.asset_matching import AssetMatching
from interior.workbench.studio.parametric_assets import recipe
from interior.workbench.storage import read_json,write_json
from test_asset_matching import environment
from test_asset_batch import BatchAgents

def test_unknown_purpose_blocks_before_cloud_but_explicit_keep_can_proceed(tmp_path):
    studio,jobs,initial=environment(tmp_path)
    try:
        scene=copy.deepcopy(initial['scene']);g=next(g for g in scene['groups'] if 'sofa' in g['children']);g['name']='unidentified enclosure'
        rev=studio.save('ASSETS',scene,initial['revision']);agents=BatchAgents();batch=AssetBatch(AssetMatching(studio,agents))
        body=BatchRequest(base_revision=rev['revision'],operation_id='wizard-required-purpose',auto_apply=False)
        with pytest.raises(ValueError,match='本次保留原件'):batch.start('ASSETS',body)
        assert agents.calls==0
        body.overrides={g['id']:__import__('interior.workbench.studio.asset_batch',fromlist=['ObjectStyle']).ObjectStyle(keep_original=True)}
        result=batch.start('ASSETS',body);payload=read_json(batch.folder('ASSETS')/result['id']/'input.json')
        assert next(t for t in payload['targets'] if t['group_id']==g['id'])['keep_original']
        assert all(t['description']==DEFAULT_STYLE for t in payload['targets'])
    finally:jobs.close()

def test_bounded_two_searches_and_kept_object_never_calls_model(tmp_path):
    gate=threading.Barrier(2);lock=threading.Lock();active=0;peak=0;calls=[]
    class Client:
        def close(self):pass
    targets=[dict(task_id=str(i),name='chair',keep_original=i==4,result_path=str(tmp_path/str(i)/'result.json')) for i in range(5)]
    def match(client,directory,target,*args):
        nonlocal active,peak
        with lock:active+=1;peak=max(peak,active);calls.append(target['task_id'])
        gate.wait(timeout=5)
        with lock:active-=1
        return dict(candidates=[dict(asset_id=target['task_id'],is_free=True,quality={'status':'eligible'})])
    with patch('interior.workbench.studio.asset_batch.run_matching',side_effect=match):
        result=run_batch(Client(),tmp_path,dict(targets=targets),'test',lambda _:None,lambda _:None,Client)
    assert peak==2 and set(calls)=={'0','1','2','3'} and len(result['completed'])==5

def test_fallback_only_has_supported_purpose_and_keeps_dimension_classification():
    context={'group':{'name':'cabinet','asset_requirements':{'purpose':'cabinet','dimension_source':'confirmed','dimensions':[1,.5,1.2],'evidence':'D1'}}}
    target=dict(kind='model',context=context,description='warm oak')
    r=recipe(target);assert r['dimensions']==[1,.5,1.2] and r['dimension_source']=='confirmed' and r['quality']=='concept'
    context['group']['asset_requirements']['purpose']='sofa';assert recipe(target)['purpose']=='sofa'
    context['group']['asset_requirements']['purpose']='cabinet';target['keep_original']=True;assert recipe(target) is None


def test_dimension_adaptation_keeps_confirmed_targets_and_edge_thickness():
    from interior.visualization.asset_dimensions import adaptation,edge_preserving
    policy=dict(purpose='cabinet',dimension_source='confirmed',dimensions=[1,.5,1.2],evidence='D1')
    result=adaptation([.9,.5,1.2],[.8,.5,1.2],policy)
    assert result['target_dimensions']==[1,.5,1.2] and result['rotation']==0
    assert edge_preserving(.02,0,.8,1)==pytest.approx(.02)
    assert edge_preserving(.78,0,.8,1)==pytest.approx(.98)
    assert edge_preserving(.4,0,.8,1)==pytest.approx(.5)
    with pytest.raises(ValueError,match='50%'):adaptation([1,.5,1.2],[.2,.5,1.2],policy)
    with pytest.raises(ValueError,match='用途'):adaptation([1,.5,1.2],[.8,.5,1.2],dict(policy,purpose='chair'))
