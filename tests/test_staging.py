"""New-scene placement, real support bounds, idempotency and automatic fit guards."""
import copy
from unittest.mock import patch
import pytest
from interior.workbench.studio.staging import StageRequest, StageApply, StageRetry, Staging, propose, world_bounds
from interior.workbench.studio.asset_batch import AssetBatch, BatchRequest, run_batch, select_targets
from interior.workbench.studio.asset_matching import AssetMatching
from interior.workbench.studio.models import Scene
from interior.workbench.storage import read_json, Conflict
from interior.visualization.asset_fit import choose_fit
from test_asset_matching import environment, FakeAgents
from test_asset_batch import BatchAgents


def home(offset=0):
    names={'f':'客廳地板','d':'餐桌','s':'沙發','w':'窗戶'}
    scene=dict(model_id='a'*32,rooms=[dict(id='living',name='客廳')],groups=[dict(id=k,name=n,children=[k+'-mesh'],translation=[0,0,0],deleted=False) for k,n in names.items()],objects=[dict(id=k+'-mesh',name=n,room_id='living',material={}) for k,n in names.items()],viewpoints=[],links=[],lighting='existing')
    bounds={'f':([offset,0,-.1],[offset+6,5,0]),'d':([offset+2,2,0],[offset+3.4,2.8,.75]),'s':([offset+.4,3,0],[offset+2.5,3.9,.8]),'w':([offset,1,1],[offset+.1,2,2])}
    return Scene.model_validate(scene).model_dump(mode='json'),bounds


def request(kind,**kw):return StageRequest(base_revision='a'*32,operation_id='new-home-study',kind=kind,**kw)


def test_two_unrelated_plans_derive_positions_not_project_coordinates():
    a,ba=home();b,bb=home(25)
    first=propose(a,ba,request('decor'));second=propose(b,bb,request('decor'))
    assert first['items'] and len(first['items'])==len(second['items'])
    for x,y in zip(first['items'],second['items']):assert y['position'][0]-x['position'][0]==pytest.approx(25)
    assert any(i['furniture']['asset']=='vase' for i in first['items'])
    assert not first['lights']


def test_daylight_and_ceiling_fixtures_are_bound_and_duplicate_safe():
    scene,b=home();result=propose(scene,b,request('lighting'))
    assert any(l['kind']=='SUN' and l['group_id'] is None for l in result['lights'])
    for item in result['items']:
        assert item['furniture']['asset']=='ceiling_light'
        assert any(l['group_id']==item['id'] and l['position'][2]<0 for l in result['lights'])
        scene['groups'].append(dict(id=item['id']))
    scene['lighting_setup']['lights']=result['lights']
    # Already generated stable IDs must not create a second fixture.
    scene['groups']=[g if 'deleted' in g else dict(g,deleted=True) for g in scene['groups']]
    _,b=home()
    again=propose(scene,b,request('lighting'))
    assert not again['items'] and not again['lights']


def test_collision_no_support_and_room_filter_leave_reasons():
    scene,b=home();scene['groups'].append(dict(id='block',name='固定櫃',children=['block-mesh'],translation=[0,0,0],deleted=False))
    scene['objects'].append(dict(id='block-mesh',name='固定櫃',room_id='living',material={}))
    b['block']=([2,2,.75],[2.5,2.5,1.3])
    result=propose(scene,b,request('decor'))
    assert not any(i['support_id']=='d' for i in result['items'])
    assert any('重疊' in n for n in result['notes'])
    with pytest.raises(ValueError):propose(scene,b,request('decor',room_ids=['missing']))


def test_generated_host_names_cannot_turn_lights_or_decor_into_floor_materials():
    scene,_=home();scene['groups'][0]['name']='天花燈具 · floor'
    scene['groups'][1]['name']='花瓶與花 · table'
    targets=select_targets(scene,BatchRequest(base_revision='a'*32,operation_id='classification-test'))
    assert next(t for t in targets if t['group_id']=='f')['kind']=='model'
    assert next(t for t in targets if t['group_id']=='f')['category']=='light'
    assert next(t for t in targets if t['group_id']=='d')['category']=='other'


def test_fits_rotate_instead_of_shrinking_and_reject_incomplete_parts():
    angle,scale,size=choose_fit([1.12,2.06,1.8],[2.0,1.1,1.8])
    assert angle==90 and size[2]==pytest.approx(1.8)
    with pytest.raises(ValueError,match='適配'):choose_fit([.6,.6,.85],[.3,.6,.06])
    with pytest.raises(ValueError,match='適配'):choose_fit([1.4,.8,.75],[2.21,1,.769])
    # A thin shade fits a NEW ceiling envelope; existing furniture retains height protection.
    _,_,shade=choose_fit([.45,.45,.12],[.3,.3,.066],envelope=True)
    assert shade[2]==pytest.approx(.099)
    with pytest.raises(ValueError,match='適配'):choose_fit([.45,.45,.12],[.3,.3,.04])


def test_capacity_retry_and_fallback_keep_required_function(tmp_path):
    target=dict(task_id='x',name='Cooker cabinet',result_path=str(tmp_path/'result.json'),description='Must include base cabinet',kind='model')
    calls=[]
    def match(client,directory,settings,*args):
        calls.append(settings)
        if len(calls)==1:raise ValueError('serverOverloaded at capacity')
        if len(calls)==2:return dict(candidates=[])
        return dict(candidates=[dict(asset_id='a',is_free=True)])
    with patch('interior.workbench.studio.asset_batch.run_matching',side_effect=match):run_batch(None,tmp_path,dict(targets=[target]),'same-model',lambda _:None,None)
    assert len(calls)==3 and 'Must include base cabinet' in calls[-1]['description']
    assert read_json(tmp_path/'result.json')['status']=='passed'


def test_apply_uses_normal_batch_and_same_click_cannot_duplicate(tmp_path):
    studio,jobs,first=environment(tmp_path)
    try:
        batches=AssetBatch(AssetMatching(studio,BatchAgents()));service=Staging(studio,batches)
        # Test setup uses synthetic actual scene names; no case data.
        sc=copy.deepcopy(first['scene']);sc['groups'][0]['name']='餐桌';sc['groups'][0]['method']='individual'
        saved=studio.save('ASSETS',sc,first['revision']);gid=sc['groups'][0]['id']
        body=request('decor').model_copy(update={'base_revision':saved['revision']})
        with patch('interior.workbench.studio.staging.world_bounds',return_value={gid:([0,0,0],[1.4,.8,.75])}):p=service.preview('ASSETS',body)
        assert p['items']
        apply=StageApply(base_revision=saved['revision'],selected_ids=[p['items'][0]['id']])
        with patch.object(batches.automation,'start'):
            result=service.apply('ASSETS',p['id'],apply)
            again=service.apply('ASSETS',p['id'],apply)
        assert again['batch']['id']==result['batch']['id']
        assert len(studio.current('ASSETS')['scene']['concept_furniture'])==1
        assert result['batch']['items'][0]['kind']=='model'
        with pytest.raises(Conflict):service.apply('ASSETS',p['id'],apply.model_copy(update={'selected_ids':[]}))
    finally:jobs.close()


def test_retry_only_failed_groups_and_preserves_requirements(tmp_path):
    from interior.workbench.storage import write_json
    studio,jobs,first=environment(tmp_path)
    try:
        batches=AssetBatch(AssetMatching(studio,BatchAgents()));service=Staging(studio,batches)
        groups=first['scene']['groups'];failed=groups[0]['id']
        identifier='a'*32
        write_json(service.folder('ASSETS')/identifier/'proposal.json',dict(id=identifier))
        write_json(service.folder('ASSETS')/identifier/'adoption.json',dict(batch_id='b'*32))
        previous=dict(status='review',items=[dict(group_id=g['id'],placement=dict(status='needs_attention' if g['id']==failed else 'installed')) for g in groups],settings=BatchRequest(base_revision=first['revision'],operation_id='previous-test',description='required function').model_dump())
        with patch.object(batches,'get',return_value=previous),patch.object(batches,'start',return_value=dict(id='c'*32)) as start:
            service.retry('ASSETS',identifier,StageRetry(base_revision=first['revision'],operation_id='retry-test'))
        body=start.call_args.args[1]
        assert body.description=='required function'
        assert {gid for gid,opt in body.overrides.items() if opt.enabled}=={failed}
        adopted=read_json(service.folder('ASSETS')/identifier/'adoption.json')
        assert adopted['previous_batches']==['b'*32]
    finally:jobs.close()
