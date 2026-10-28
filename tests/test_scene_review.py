"""Synthetic multi-room review, constrained corrections and preview preservation."""
import copy
import json
from pathlib import Path
import pytest
from types import SimpleNamespace
import threading
from interior.workbench.studio.models import Scene
from interior.workbench.studio import scene_review as review
from interior.workbench.storage import read_json,write_json


def scene():
    return Scene.model_validate(dict(model_id='a'*32,rooms=[dict(id='room',name='Room')],objects=[dict(id='chair-part',name='chair',material={})],
        groups=[dict(id='chair',name='chair',children=['chair-part'],asset_requirements=dict(purpose='chair',dimension_source='confirmed',dimensions=[.5,.5,.8],evidence='measured'),placement_constraints=dict(area=[0,0,3,3],max_distance=.2))],
        viewpoints=[dict(id='view',name='Room',room_id='room',eye=[1,1,1.6],shots=[dict(id='front',name='Front',yaw=0)])],
        lighting_setup=dict(enabled=True,lights=[dict(id='light',name='Lamp',position=[1,1,2.5],power=100,size=1)]))).model_dump(mode='json')


def issue(**values):
    return dict(id='dark',category='lighting',target_id='light',shot_id=None,file='view-front.png',reason='桌面過暗',severity='defect',action='light',values={'power':150},**values)


def test_light_only_edits_keep_confirmed_dimensions_and_everything_else():
    original=scene();result=review.apply_issue(original,original,issue())
    assert result['groups']==original['groups']
    assert result['objects']==original['objects']
    assert result['viewpoints']==original['viewpoints']
    assert original['lighting_setup']['lights'][0]['power']==100
    assert result['lighting_setup']['lights'][0]['power']==150


@pytest.mark.parametrize('change',[{'values':{'power':501}},{'values':{'enabled':False}},{'values':{'power':float('nan')}},{'action':'delete'},{'severity':'uncertain'},{'target_id':'unknown'}])
def test_unsafe_changes_rejected(change):
    proposal=issue();proposal.update(change)
    with pytest.raises((ValueError,StopIteration)):review.apply_issue(scene(),scene(),proposal)


def test_locked_light_and_cumulative_limits():
    original=scene();original['lighting_setup']['lights'][0]['locked']=True
    with pytest.raises(ValueError):review.apply_issue(original,original,issue())
    original=scene();next_scene=review.apply_issue(original,original,issue())
    proposal=issue();proposal['values']['power']=500
    with pytest.raises(ValueError):review.apply_issue(next_scene,original,proposal)


def test_unidentified_manual_issue_is_reported_not_dropped():
    item=issue();item.update(target_id=None,action='manual',values={},category='geometry')
    verdict=review.Review.model_validate(dict(reviewed_files=['view-front.png'],summary='天花缺漏',issues=[item]))
    assert verdict.issues[0].target_id is None
    with pytest.raises(ValueError):review.apply_issue(scene(),scene(),item)


def test_table_supporting_decor_cannot_be_moved_independently():
    original=scene();original['groups'].append(dict(id='vase',decor_context={'support_group_id':'chair'}))
    item=issue();item.update(category='furniture',action='move',target_id='chair',values={'translation':[.1,0,0]})
    with pytest.raises(ValueError,match='連動'):review.apply_issue(original,original,item)


def test_move_requires_area_and_never_changes_height_or_size():
    original=scene();proposal=issue();proposal.update(category='furniture',action='move',target_id='chair',values={'translation':[.1,0,0]})
    result=review.apply_issue(original,original,proposal)
    assert result['groups'][0]['asset_requirements']==original['groups'][0]['asset_requirements']
    proposal['values']['translation'][2]=.1
    with pytest.raises(ValueError):review.apply_issue(original,original,proposal)
    proposal['values']={'translation':[.1,0,0]};original['groups'][0]['placement_constraints']=None
    with pytest.raises(ValueError):review.apply_issue(original,original,proposal)


def test_original_material_policy_and_camera_position_preserved():
    original=scene();original['groups'][0]['object_specification']={'material_policy':'original'}
    proposal=issue();proposal.update(category='material',action='roughness',target_id='chair-part',values={'render_roughness':.7})
    with pytest.raises(ValueError):review.apply_issue(original,original,proposal)
    proposal.update(category='viewpoint',action='shot',target_id='view',shot_id='front',values={'eye':[2,2,1.6]})
    with pytest.raises(ValueError):review.apply_issue(original,original,proposal)


def run_loop(tmp_path,monkeypatch,answers):
    source=tmp_path/'source.blend';source.write_bytes(b'original model')
    output=tmp_path/'run';output.mkdir()
    request=dict(source=str(source),scene=scene(),revision='b'*32,model_id='a'*32,quality='preview')
    calls=[]
    def render(payload,folder):
        calls.append(copy.deepcopy(payload['scene']))
        (folder/'view-front.png').write_bytes(b'render');(folder/'thumb-view-front.png').write_bytes(b'thumb')
        write_json(folder/'result.json',dict(images=[dict(file='view-front.png',thumbnail='thumb-view-front.png',name='Room',width=640,height=480,kind='still',quality='preview')],quality_check='passed'))
        return 0
    answers=iter(answers)
    monkeypatch.setattr(review,'review_images',lambda *args:next(answers))
    result=review.optimize(request,output,render)
    return result,read_json(output/'scene-review.json'),calls,source


def test_actual_rerender_follows_correction_and_source_kept(tmp_path,monkeypatch):
    result,report,calls,source=run_loop(tmp_path,monkeypatch,[dict(summary='dark',issues=[issue()]),dict(summary='okay',issues=[])])
    assert result['scene_review_status']=='passed' and len(calls)==2
    assert calls[1]['lighting_setup']['lights'][0]['power']==150
    assert source.read_bytes()==b'original model'
    assert report['attempts'][0]['changes'] and report['attempts'][1]['images']
    assert result['images'][0]['file'].startswith('scene-attempt-2/')


def test_manual_issue_cannot_disappear_in_later_agent_pass(tmp_path,monkeypatch):
    pending=issue();pending.update(id='bed-size',category='furniture',target_id='chair',action='manual',values={},reason='尺寸需要確認')
    result,report,calls,_=run_loop(tmp_path,monkeypatch,[dict(summary='fix',issues=[issue(),pending]),dict(summary='okay',issues=[])])
    assert result['scene_review_status']=='needs_attention'
    assert report['pending'][0]['reason']=='尺寸需要確認'
    assert len(calls)==2


def test_three_round_bound_preserves_unresolved_preview(tmp_path,monkeypatch):
    answers=[]
    for power in (150,200,250):
        proposal=issue();proposal['values']['power']=power;answers.append(dict(summary='dark',issues=[proposal]))
    result,report,calls,_=run_loop(tmp_path,monkeypatch,answers)
    assert len(calls)==3 and result['scene_review_status']=='needs_attention'
    assert calls[-1]['lighting_setup']['lights'][0]['power']==200
    assert report['pending']


def test_adoption_rejects_stale_scene_and_source_and_preserves_other_fields(tmp_path):
    original=scene();effective=review.apply_issue(original,original,issue());revision='b'*32;job_id='c'*32
    native=tmp_path/'runs/interior-studio'/original['model_id']/'model.blend';native.parent.mkdir(parents=True);native.write_bytes(b'original')
    folder=tmp_path/'runs/interior-studio'/job_id
    report=dict(changed=True,effective_scene_hash=review.fingerprint(effective),original_scene_hash=review.fingerprint(original),source_sha256=review.digest(native))
    write_json(folder/'scene-review.json',report)
    write_json(folder/'scene-review-effective.json',dict(source_revision=revision,scene=effective))
    job=dict(project_id='TEST',operation='studio.render',status='completed',source_revision=revision,output=f'runs/interior-studio/{job_id}')
    current=dict(revision=revision,scene=original);saved=[]
    studio=SimpleNamespace(store=SimpleNamespace(lock=threading.RLock()),jobs=SimpleNamespace(get=lambda _:job),root=lambda _:tmp_path,current=lambda _:current,save=lambda *args:saved.append(args) or dict(revision='d'*32,scene=args[1]))
    result=review.adopt(studio,'TEST',job_id,revision)
    assert result['scene']['groups']==original['groups'] and len(saved)==1
    current['revision']='e'*32
    with pytest.raises(review.Conflict):review.adopt(studio,'TEST',job_id,revision)
    current['revision']=revision;native.write_bytes(b'changed')
    with pytest.raises(review.Conflict):review.adopt(studio,'TEST',job_id,revision)
    assert len(saved)==1


def test_agent_must_cover_every_picture_and_hashes_are_bound(tmp_path,monkeypatch):
    (tmp_path/'a.png').write_bytes(b'actual image');(tmp_path/'b.png').write_bytes(b'another image')
    class Client:
        def __init__(self,*args):pass
        def status(self):return dict(authenticated=True,auth_type='chatgpt')
        def run(self,*args,**kwargs):return dict(text=json.dumps(dict(reviewed_files=['a.png'],summary='okay',issues=[])))
        def close(self):pass
    monkeypatch.setattr(review,'CodexRuntime',Client)
    with pytest.raises(ValueError,match='逐張'):review.review_images(tmp_path,scene(),dict(images=[dict(file='a.png'),dict(file='b.png')]),tmp_path/'stop')
    assert (tmp_path/'agent-response-1.json').exists()


def test_retry_carries_only_same_revision_source_and_requires_explicit_clearance(tmp_path):
    output=tmp_path/'new';output.mkdir()
    item=issue();item.update(category='furniture',target_id='chair',action='manual',values={},reason='缺工作面')
    def report(name,revision='rev',source='sha',pending=None,resolved=None,completed=True):
        folder=tmp_path/name
        write_json(folder/'scene-review.json',dict(revision=revision,source_sha256=source,pending=pending or [],attempts=[dict(resolved=resolved or [])]))
        if completed:write_json(folder/'result.json',{})
    report('old',pending=[item])
    report('omitted')
    report('different-revision',revision='other',pending=[dict(item,target_id='other')])
    report('different-source',source='other',pending=[dict(item,target_id='other')])
    report('running',pending=[dict(item,target_id='unfinished')],completed=False)
    items,_=review.previous_issues(output,'rev','sha')
    assert len(items)==1 and items[0]['target_id']=='chair' and items[0]['values']=={}
    report('cleared',resolved=[dict(item,action='cleared')])
    assert review.previous_issues(output,'rev','sha')[0]==[]


def test_retry_merges_omitted_findings_but_not_missing_views_or_duplicate_targets():
    item=issue();item['file']='scene-attempt-3/view-front.png'
    missing=dict(item,target_id='missing',file='removed-view.png')
    merged=review.merge_unresolved([], [item,missing],dict(images=[dict(file='view-front.png')]))
    assert len(merged)==1 and merged[0]['action']=='manual' and merged[0]['file']=='view-front.png'
    assert item['action']=='light'
    assert review.merge_unresolved([issue()],[item],dict(images=[dict(file='view-front.png')]))==[issue()]
