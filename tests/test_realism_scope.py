"""New-case coverage, repeated direction IDs and cross-room regressions."""
import copy
import pytest
from interior.visualization.realism_scope import combine_inventories,manifest_for_point
from interior.workbench.studio.realism_scope import merge_reviews
from interior.workbench.studio.realism import Verdict,apply_plan
from test_realism import scene


def test_camera_only_room_selection_keeps_success_without_shared_edits():
    from interior.workbench.studio.realism_scope import select_reviewed_camera_rooms
    base=scene();other=copy.deepcopy(base['viewpoints'][0]);other['id']='other';base['viewpoints'].append(other)
    trial=copy.deepcopy(base)
    for p in trial['viewpoints']:p['shots'][0]['lens']=28
    reviews=[dict(point=p,preference='candidate' if p['id']=='other' else 'baseline') for p in trial['viewpoints']]
    result,chosen=select_reviewed_camera_rooms(base,trial,reviews)
    assert chosen==['other'] and result['viewpoints'][0]==base['viewpoints'][0]
    assert result['viewpoints'][1]==trial['viewpoints'][1] and result['groups']==base['groups']
    trial['lighting_setup']['lights'][0]['power']+=1
    assert select_reviewed_camera_rooms(base,trial,reviews)==(base,[])


def test_camera_selection_requires_complete_reviews_and_unchanged_panorama():
    from interior.workbench.studio.realism_scope import select_reviewed_camera_rooms
    base=scene();trial=copy.deepcopy(base);trial['viewpoints'][0]['shots'][0]['lens']=28
    assert select_reviewed_camera_rooms(base,trial,[])==(base,[])
    reviews=[dict(point=trial['viewpoints'][0],preference='candidate')]
    trial['viewpoints'][0]['eye'][0]+=.1
    assert select_reviewed_camera_rooms(base,trial,reviews)==(base,[])


def test_whole_house_rejection_memory_follows_room_and_effective_camera(tmp_path):
    from interior.workbench.studio import realism
    from interior.workbench.storage import write_json
    base=scene();other=copy.deepcopy(base['viewpoints'][0]);other['id']='other';base['viewpoints'].append(other)
    candidate=copy.deepcopy(base)
    candidate['viewpoints'][0]['shots'][0]['lens']=28
    candidate['viewpoints'][1]['shots'][0]['lens']=35
    old=tmp_path/'old';trial=old/'realism-attempt-2';trial.mkdir(parents=True)
    (old/'realism-baseline').mkdir()
    source=tmp_path/'source.blend';source.write_bytes(b'original')
    request=dict(source=str(source),revision='a'*32,realism_point_id='new-view')
    write_json(old/'realism-review.json',dict(status='preview_ready',revision=request['revision'],source_sha256=realism.digest(source),whole_house=True,point={'id':'other'},attempts=[dict(number=2,status='not_selected',changes=[dict(kind='camera_restore')])]))
    write_json(old/'realism-baseline/request.json',{'scene':base})
    write_json(trial/'request.json',{'scene':candidate})
    write_json(trial/'room-reviews.json',[dict(point=p,preference='baseline' if p['id']=='new-view' else 'candidate',summary='observed') for p in candidate['viewpoints']])
    failures=realism.prior_camera_failures(tmp_path/'new',request,base)
    assert len(failures)==1 and failures[0]['parameters']['lens']==28
    all_failures=realism.prior_camera_failures(tmp_path/'new',dict(request,realism_all=True),base)
    assert len(all_failures)==1  # An accepted room in a rejected whole trial is not a failure.
    candidate['lighting_setup']['lights'][0]['power']+=1
    write_json(trial/'request.json',{'scene':candidate})
    assert not realism.prior_camera_failures(tmp_path/'new',request,base)


def inventory(pid):
    return dict(point=dict(id=pid,name=pid),objects=[dict(id='wood',editable=True,screen_regions=[])],lights=[],details=dict(cameras=[dict(id='option',shot_id='front',target='desk',eye=[1,1,1.2],yaw=20,pitch=0,lens=28)],camera_checks=[dict(shot_id='front',required_windows=[])]))


def test_same_direction_id_is_independent_for_each_room():
    original=scene();other=copy.deepcopy(original['viewpoints'][0]);other['id']='other';original['viewpoints'].append(other)
    facts=combine_inventories([inventory('new-view'),inventory('other')])
    proposal=Verdict(summary='rooms',preference='baseline',reviewed_files=[],cameras=[c['id'] for c in facts['details']['cameras']])
    result,changes,rejected=apply_plan(original,original,facts,proposal)
    assert len(changes)==2 and not rejected
    assert all(p['shots'][0]['lens']==28 for p in result['viewpoints'])
    assert result['groups']==original['groups']
    assert len(facts['objects'])==1


def test_shared_edit_conflicts_are_not_last_writer_wins():
    def proposal(gain,preference):return Verdict(summary='observed',preference=preference,reviewed_files=[],materials=[dict(object_id='wood',finish={'bump_factor':gain},reason='observed grain')])
    merged=merge_reviews([(dict(name='A'),proposal(.4,'candidate')),(dict(name='B'),proposal(.8,'baseline'))],Verdict,True)
    assert merged.preference=='baseline' and not merged.materials and merged.remaining
    merged=merge_reviews([(dict(name='A'),proposal(.4,'candidate')),(dict(name='B'),proposal(.4,'equivalent'))],Verdict,True)
    assert merged.preference=='candidate' and len(merged.materials)==1


def test_missing_room_images_cannot_pass_review():
    with pytest.raises(ValueError):manifest_for_point({'images':[{'file':'room-A-front.png'}]},'room-B')
    with pytest.raises(ValueError):combine_inventories([])


def test_room_review_receives_current_installation_evidence(tmp_path):
    from interior.workbench.studio.realism_scope import review_rooms
    facts=combine_inventories([inventory('new-view'),inventory('other')])
    facts['installation_results']={'items':[{'status':'prepared','checks':{'wall_gap':.003}}]}
    seen=[]
    def review(folder,base,bm,cf,cm,room,original,stop,model):
        seen.append(room['installation_results'])
        return Verdict(summary='checked',preference='baseline',reviewed_files=[])
    manifest={'images':[{'file':'new-view-front.png'},{'file':'other-front.png'}]}
    review_rooms(review,Verdict,tmp_path,tmp_path,manifest,None,None,facts,{},tmp_path/'stop','gpt-6-sol')
    assert len(seen)==2 and all(v==facts['installation_results'] for v in seen)


def test_no_plan_lineage_does_not_invent_openings(tmp_path):
    from interior.workbench.studio.opening_details import source_openings
    result=source_openings(tmp_path,dict(id='independent-glb',ancestor_model_ids=[]))
    assert result['items']==[] and result['reason']


def test_rejected_whole_trial_keeps_improvement_only_for_retrial(tmp_path,monkeypatch):
    from interior.workbench.studio import realism
    from interior.workbench.storage import write_json,read_json
    from test_realism import facts
    source=tmp_path/'source.blend';source.write_bytes(b'unchanged')
    output=tmp_path/'run';output.mkdir();calls=[]
    request=dict(source=str(source),scene=scene(),revision='b'*32,realism_point_id='new-view',realism_all=True)
    def render(payload,folder):
        if payload.get('completion_evidence'):
            write_json(folder/'completion-fronts.json',dict(items=[]));return 0
        calls.append(copy.deepcopy(payload['scene']))
        write_json(folder/'result.json',dict(quality_check='passed',images=[]))
        write_json(folder/'realism-inventory.json',facts());return 0
    answers=iter([
        Verdict(summary='propose',preference='baseline',reviewed_files=[],materials=[dict(object_id='wood',finish={'bump_factor':.5},reason='improve one room')],lights=[dict(light_id='lamp',power=120,color=[1,1,1],size=1,reason='trial')]),
        Verdict(summary='another room regressed',preference='baseline',reviewed_files=[],lights=[dict(light_id='lamp',power=90,color=[1,1,1],size=1,reason='correct the shared light')]),
        Verdict(summary='all rooms preserved',preference='candidate',reviewed_files=[]),
    ])
    monkeypatch.setattr(realism,'inspect',lambda *args:next(answers))
    realism.optimize(request,output,render)
    report=read_json(output/'realism-review.json')
    assert report['attempts'][0]['status']=='not_selected'
    assert report['selected_folder']=='realism-attempt-2'
    assert calls[2]['objects'][0]['material']['render_finish']['bump_factor']==.5
    assert calls[2]['lighting_setup']['lights'][0]['power']==90
    assert all(c['groups']==scene()['groups'] for c in calls)



def test_room_without_better_camera_restores_baseline_only_for_that_room():
    from interior.workbench.studio.realism_scope import restore_unpreferred_cameras
    base=scene();other=copy.deepcopy(base['viewpoints'][0]);other['id']='other';base['viewpoints'].append(other)
    candidate=copy.deepcopy(base)
    for p in candidate['viewpoints']:p['shots'][0]['lens']=20
    candidate['objects'][0]['material']['description']='kept refinement'
    reviews=[dict(point=dict(id='new-view'),preference='baseline'),dict(point=dict(id='other'),preference='candidate')]
    changes=restore_unpreferred_cameras(candidate,base,reviews,[])
    assert len(changes)==1 and changes[0]['point_id']=='new-view'
    assert candidate['viewpoints'][0]['shots']==base['viewpoints'][0]['shots']
    assert candidate['viewpoints'][1]['shots'][0]['lens']==20
    assert candidate['objects'][0]['material']['description']=='kept refinement'
    candidate['viewpoints'][0]['shots'][0]['lens']=28
    assert not restore_unpreferred_cameras(candidate,base,reviews,[dict(kind='camera',point_id='new-view')])
    assert candidate['viewpoints'][0]['shots'][0]['lens']==28
