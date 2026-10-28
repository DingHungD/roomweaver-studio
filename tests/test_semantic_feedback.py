"""Synthetic feedback security and continuity, independent of any client plan."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from interior.workbench.studio.semantic_feedback import (
    VERSION, addition_limits, apply_patch, attach_feedback, mark_area,
    question_snapshot, recover_recognition, run_feedback, shape, scope_for,
)
from interior.workbench.studio.plan_semantics import SemanticRequest, run_semantics
from interior.workbench.storage import Conflict, write_json


def validate(site, candidate):
    return copy.deepcopy(candidate), dict(status='preview', errors=[], repair_errors=[], questions=[], counts={}, layers=dict(items=[]))


def fixture():
    def rectangle(identifier, x):
        return dict(id=identifier, kind='LWPOLYLINE', points=[[x, 0], [x+1, 0], [x+1, 1], [x, 1]], closed=True)
    geometry = [rectangle('native-a', 0), rectangle('native-b', 3), rectangle('native-new', 1.5)]
    def furniture(identifier, source, x):
        return dict(id=identifier, name=identifier, role='furniture', category='table', points=rectangle('', x)['points'],
                    closed=True, source_ids=[source], evidence='synthetic source', height=.75, base=0)
    a, b = furniture('desk-a', 'native-a', 0), furniture('desk-b', 'native-b', 3)
    base = dict(rooms=[], elements=[a, b], lighting=[], drawing_objects=[], questions=[],
                door_state='absent', window_state='absent', furniture_state='present')
    objects = [dict(r, id='recognition:'+r['id'], role='mask', layer='furniture', status='interpreted') for r in (a, b)]
    audit = dict(workflow='agent_native_v1', status='blocked', objects=2, layers=dict(items=objects, lighting_reviewed=True),
                 pending=1, deferred=1, pending_items=[dict(id='unrelated-pending', reason='retain')], findings=1, scan_findings=1)
    site = dict(geometry=geometry, texts=[], dimensions=[], source_view=dict(bounds=[0, 0, 5, 4], scale=100, pad=0),
                feedback_version=VERSION, previous_review=dict(candidate=copy.deepcopy(base), report=dict(recognition=copy.deepcopy(audit))))
    item = dict(id='cor-'+'a'*32, title='Desk', comment='修正桌子的名稱', target_kind='object',
                target_domain='objects', target_id='recognition:desk-a', mode='object', marks=[])
    return site, base, audit, item


def patch(*operations, status='corrected', marks=None):
    return dict(status=status, summary='Checked local feedback', operations=list(operations), mark_results=marks or [])


def operation(collection, identifier, values=None, action='update', **extra):
    return dict(collection=collection, id=identifier, action=action, values=values or {}, **extra)


def test_object_patch_preserves_unselected_objects_and_other_representation():
    site, base, audit, item = fixture()
    original = copy.deepcopy((base, audit))
    raw = patch(operation('objects', item['target_id'], dict(name='Corrected desk')),
                operation('elements', 'desk-a', dict(name='Corrected desk')))
    updated, revised, outcome = apply_patch(site, item, base, audit, raw, validate)
    assert updated['elements'][1] == base['elements'][1]
    assert revised['layers']['items'][1] == audit['layers']['items'][1]
    assert revised['layers']['items'][0]['points'] == audit['layers']['items'][0]['points']
    assert updated['elements'][0]['name'] == 'Corrected desk'
    assert revised['pending_items'] == audit['pending_items'] and revised['scan_findings'] == 1
    assert original == (base, audit) and outcome['preview_ready']


@pytest.mark.parametrize('raw', [
    patch(operation('elements', 'desk-b', dict(name='Unrelated'))),
    patch(operation('objects', 'recognition:desk-b', dict(category='chair'))),
    patch(operation('elements', 'desk-a', dict(id='new-id'))),
    patch(operation('elements', 'desk-a', dict(height=2))),
    dict(elements=[], summary='Whole plan', status='corrected'),
])
def test_unselected_id_full_plan_and_dimension_edits_are_rejected_atomically(raw):
    site, base, audit, item = fixture();before=copy.deepcopy((base,audit))
    with pytest.raises(ValueError):apply_patch(site,item,base,audit,raw,validate)
    assert before==(base,audit)


def test_in_scope_addition_requires_explicit_kind_count_and_quote():
    site, base, audit, item = fixture()
    item.update(mode='region', target_id=None, comment='修正桌子', marks=[dict(id='m',kind='box',points=[[-.1,-.1],[2.6,1.1]],text='')])
    values=dict(name='Extra table',category='table',source_ids=['native-new'],evidence='real native source',mask_spec=dict(method='outline',refs=[dict(id='native-new')]))
    raw=patch(operation('objects','recognition:extra',values,action='add',feedback_quote='修正桌子'))
    with pytest.raises(ValueError,match='明確反饋'):apply_patch(site,item,base,audit,raw,validate)
    item['comment']='這裡漏了一張桌子'
    raw['operations'][0]['feedback_quote']=item['comment']
    raw['mark_results']=[dict(mark_id='m',status='corrected',expected_kind='furniture',object_ids=['recognition:extra'],summary='source table in marked area')]
    _,revised,result=apply_patch(site,item,base,audit,raw,validate)
    assert len(revised['layers']['items'])==3
    assert result['status']=='needs_confirmation'  # no invented semantic projection
    raw['operations'].append(operation('objects','recognition:extra-2',values,action='add',feedback_quote=item['comment']))
    with pytest.raises(ValueError,match='數量'):apply_patch(site,item,base,audit,raw,validate)


@pytest.mark.parametrize('text,expected', [
    ('這裡漏了一扇門', {'door':1}), ('新增兩張桌子', {'table':2}),
    ('不要新增一扇門', {}), ('這裡漏了一些門', {}), ('這是門', {}),
])
def test_addition_intent_is_not_inferred_from_a_classification(text,expected):
    assert addition_limits(text)==expected


def test_region_changes_cannot_escape_or_reclassify_outside_the_box():
    site,base,audit,item=fixture()
    item.update(mode='region',comment='桌子改成椅子',marks=[dict(id='m',kind='box',points=[[0,0],[.5,1]],text='')])
    raw=patch(operation('objects','recognition:desk-a',dict(category='chair')))
    with pytest.raises(ValueError,match='跨界'):apply_patch(site,item,base,audit,raw,validate)
    raw=patch(operation('elements','desk-a',dict(points=[[0,0],[1.1,0],[1.1,1],[0,1]])))
    with pytest.raises(ValueError,match='超出'):apply_patch(site,item,base,audit,raw,validate)


def test_open_polyline_is_not_closed_for_scope_calculation():
    site,_,_,_=fixture()
    row=dict(id='open',kind='LWPOLYLINE',closed=False,points=[[0,0],[3,0],[3,2]])
    assert shape(site,row).geom_type=='LineString' and shape(site,row).area==0
    from interior.workbench.studio.semantic_batch import footprint
    assert footprint(site,row).geom_type=='LineString'


def test_text_alone_does_not_authorize_a_region():
    site,base,audit,item=fixture()
    item.update(mode='region',marks=[dict(id='t',kind='text',points=[[0,0]],text='Change here')],target_id=None)
    with pytest.raises(ValueError,match='純文字'):scope_for(site,item,base,audit)


def test_legacy_resized_object_mark_does_not_authorize_the_whole_group():
    site,base,audit,item=fixture()
    item.pop('mode');item['marks']=[dict(id='m',kind='box',points=[[0,0],[.5,1]],text='')]
    scope=scope_for(site,item,base,audit)
    assert scope['mode']=='region' and scope['area'].bounds==(0.,0.,.5,1.)


def test_invalid_unrelated_floor_does_not_block_a_valid_object_feedback():
    site,base,audit,item=fixture()
    site['floors']=[dict(id='invalid-floor',points=[[0,0],[5,5],[0,5],[5,0]])]
    _,_,result=apply_patch(site,item,base,audit,patch(status='no_change'),validate)
    assert result['status']=='no_change'
    item.update(mode='region',target_id=None,comment='地板範圍正確',marks=[dict(id='m',kind='box',points=[[0,0],[5,5]],text='')])
    with pytest.raises(ValueError,match='輪廓無效'):scope_for(site,item,base,audit)


def test_q_snapshot_is_selected_and_revision_bound():
    previous=dict(id='b'*32,answers=dict(revision='a'*32,answers={'q1':'這是梁','q2':'保留'},annotations={}),
                  task=dict(semantic_report=dict(questions=[dict(id='q1',title='Check beam',box=[0,0,1,1],source_ids=['a']),dict(id='q2',title='Unrelated',box=[3,0,4,1])])),source_questions=[])
    request=SemanticRequest(base_revision='v',model='test',operation_id='a'*32,mode='feedback',question_ids=['q1'],answers_revision='a'*32)
    result=question_snapshot(previous,request)
    assert [i['id'] for i in result['items']]==['q1'] and result['items'][0]['marks']
    with pytest.raises(Conflict):question_snapshot(previous,request.model_copy(update={'answers_revision':'c'*32}))
    with pytest.raises(ValueError):question_snapshot(previous,request.model_copy(update={'question_ids':[]}))


def test_feedback_dispatch_never_runs_yolo_or_whole_plan(monkeypatch,tmp_path):
    site,base,audit,item=fixture()
    site.update(correction_batch=dict(items=[item],selected_ids=[item['id']]))
    monkeypatch.setattr('interior.workbench.studio.yolo_review.prepare',lambda *a:pytest.fail('whole-image inference'))
    monkeypatch.setattr('interior.workbench.studio.plan_semantics.validate',validate)
    client=Mock();client.run.return_value=dict(text=json.dumps(patch(status='no_change')))
    result=run_semantics(client,tmp_path,dict(site=site,image='not-opened.png'),'test',lambda _:None,lambda _:None)
    assert client.run.call_count==1 and result['feedback_version']==VERSION
    assert result['yolo_review']['layers']==audit['layers'] and result['candidate']['elements']==base['elements']
    assert result['semantic_report']['recognition']['layers']==audit['layers']


def test_failed_patch_is_bounded_and_keeps_baseline_and_blocker_on_reread(tmp_path):
    site,base,audit,item=fixture();site['correction_batch']=dict(items=[item],selected_ids=[item['id']])
    client=Mock();client.run.return_value=dict(text=json.dumps(dict(elements=[])))
    result=run_feedback(client,tmp_path,dict(site=site,image='unused.png'),'test',lambda _:None,lambda _:None,validate)
    assert client.run.call_count==2 and result['candidate']['elements']==base['elements']
    assert result['feedback_results'][0]['status']=='unresolved'
    report=validate(site,base)[1];attach_feedback(site,result,report)
    assert report['status']=='blocked' and not report['corrections'][0]['preview_ready']


def test_ancestor_recognition_recovery_requires_frozen_hashes_and_unchanged_geometry(tmp_path):
    site,base,audit,_=fixture()
    from interior.workbench.studio.cad_candidates import source_hash
    source=dict(origin=[0,0],factor=1,geometry=site['geometry'],texts=[],dimensions=[],floors=[],source_is_image=False)
    identifier='a'*32;folder=tmp_path/'runs'/identifier;folder.mkdir(parents=True)
    review=folder/'yolo-native-review';review.mkdir()
    write_json(review/'object-layers.json',audit['layers'])
    import hashlib
    write_json(review/'frozen-result.json',dict(files={'object-layers.json':hashlib.sha256((review/'object-layers.json').read_bytes()).hexdigest()}))
    write_json(folder/'request.json',dict(source_revision='v',site=source))
    write_json(folder/'result.json',dict(candidate=base,yolo_review=audit))
    record=dict(source_revision='v',site=dict(source,previous_review=dict(task_id=identifier,candidate=base,report={})))
    service=Mock();service.folder.return_value=tmp_path
    inherited=recover_recognition(service,'synthetic','plan',record,dict(candidate=base))
    assert inherited['layers']==audit['layers'] and inherited['inherited_from']==identifier
    changed=copy.deepcopy(base);changed['elements'][0]['points'][0][0]=.5
    assert recover_recognition(service,'synthetic','plan',record,dict(candidate=changed)) is None
    write_json(review/'object-layers.json',dict(items=[]))
    with pytest.raises(Conflict,match='凍結'):recover_recognition(service,'synthetic','plan',record,dict(candidate=base))


def test_required_reclassification_cannot_be_claimed_as_no_change():
    site,base,audit,item=fixture();item['comment']='這是椅子'
    with pytest.raises(ValueError,match='用途'):apply_patch(site,item,base,audit,patch(status='no_change'),validate)


def test_split_preserves_outside_shape_and_class_without_duplicate_objects():
    site,base,audit,item=fixture()
    item.update(mode='region',comment='桌子框內改成椅子',marks=[dict(id='m',kind='box',points=[[0,0],[.5,1]],text='')])
    values=dict(name='Chair segment',category='chair',source_ids=['native-a'],evidence='user scoped segment',
                mask_spec=dict(method='outline',refs=[dict(id='native-a')]),clip_to_scope='inside')
    raw=patch(operation('objects','recognition:desk-a',dict(clip_to_scope='outside')),
              operation('objects','recognition:chair-part',values,action='add',parent_ids=['recognition:desk-a']),
              marks=[dict(mark_id='m',status='corrected',expected_kind='furniture',object_ids=['recognition:chair-part'],summary='inside segment')])
    _,revised,outcome=apply_patch(site,item,base,audit,raw,validate)
    old=shape(site,audit['layers']['items'][0]);rows={r['id']:r for r in revised['layers']['items']}
    kept=shape(site,rows['recognition:desk-a']);chair=shape(site,rows['recognition:chair-part'])
    assert kept.union(chair).equals(old) and kept.intersection(chair).area==0
    assert rows['recognition:desk-a']['category']=='table'
    assert outcome['status']=='needs_confirmation'  # semantic segments still need matching


def test_native_resolution_cannot_expand_a_patch_outside_its_region():
    site,base,audit,item=fixture()
    item.update(mode='region',comment='桌子名稱',marks=[dict(id='m',kind='box',points=[[0,0],[1,1]],text='')])
    def expanded(s,c):
        updated,report=validate(s,c)
        if updated['elements'][0]['name']=='Expand after source binding':
            updated['elements'][0]['points'][1][0]=1.5
        return updated,report
    with pytest.raises(ValueError,match='超出'):
        apply_patch(site,item,base,audit,patch(operation('elements','desk-a',dict(name='Expand after source binding'))),expanded)


def test_overlapping_feedback_is_not_resolved_by_submission_order(tmp_path):
    site,base,audit,item=fixture();other=dict(item,id='cor-'+'b'*32,comment='Conflicting instruction')
    site['correction_batch']=dict(items=[item,other],selected_ids=[item['id'],other['id']])
    client=Mock()
    result=run_feedback(client,tmp_path,dict(site=site,image='unused.png'),'test',lambda _:None,lambda _:None,validate)
    assert client.run.call_count==0 and all(r['status']=='unresolved' for r in result['feedback_results'])
    assert result['candidate']['elements']==base['elements']


def test_saved_patch_integrity_blocks_altered_geometry_on_reread(tmp_path):
    site,base,audit,item=fixture();site['correction_batch']=dict(items=[item],selected_ids=[item['id']])
    client=Mock();client.run.return_value=dict(text=json.dumps(patch(status='no_change')))
    result=run_feedback(client,tmp_path,dict(site=site,image='unused.png'),'test',lambda _:None,lambda _:None,validate)
    report=validate(site,base)[1];attach_feedback(site,result,report)
    result['candidate']['elements'][1]['points'][0][0]=20
    with pytest.raises(Conflict,match='驗證紀錄'):attach_feedback(site,result,report)


def test_real_service_uses_local_runner_and_preserves_revision_and_recognition(system,tmp_path,monkeypatch):
    from uuid import uuid4
    from test_plan_semantics import candidate
    from test_semantic_corrections import save,request
    from interior.workbench.studio.plan_semantics import PlanSemantics,SaveSemanticAnswers
    studio,plans,packet,_=system
    class Agents:
        def __init__(self):self.tasks={};self.calls=[]
        def start(self,k,model,payload,identifier):
            self.calls.append(payload)
            if payload['site'].get('feedback_version'):
                client=Mock()
                client.run.return_value=dict(text=json.dumps(patch(operation('elements','desk',dict(name='Renamed desk')),
                                                                    operation('objects','recognition:desk',dict(name='Renamed desk')))))
                self.tasks[identifier]=dict(status='passed',**run_semantics(client,tmp_path/identifier,payload,model,lambda _:None,lambda _:None))
            else:
                c=candidate(payload['site']);desk=next(r for r in c['elements'] if r['id']=='desk')
                audit=dict(workflow='agent_native_v1',status='reviewed_preview',objects=1,layers=dict(items=[dict(desk,id='recognition:desk',role='mask',layer='furniture',category='table')],lighting_reviewed=True))
                self.tasks[identifier]=dict(status='passed',candidate=c,yolo_review=audit)
        def get(self,identifier):return self.tasks[identifier]
    agents=Agents();service=PlanSemantics(studio,agents)
    first=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex))
    item=dict(id='cor-'+'c'*32,title='Desk',comment='修正桌子的名稱',marks=[],mode='object',target_kind='object',target_domain='plan',target_id='desk')
    saved=save(service,packet,first,[item]);body=request(packet,first,saved,[item['id']])
    monkeypatch.setattr('interior.workbench.studio.yolo_review.prepare',lambda *a:pytest.fail('YOLO on feedback'))
    second=service.start('UNRELATED',packet['id'],body)
    assert second['task']['feedback_version']==VERSION
    assert second['task']['semantic_report']['recognition']['layers']['items'][0]['name']=='Renamed desk'
    assert next(r for r in second['task']['candidate']['elements'] if r['id']=='desk')['name']=='Renamed desk'
    assert second['task']['correction_states'][0]['preview_ready']
    assert plans.current('UNRELATED',packet['id'])==packet
    assert service.start('UNRELATED',packet['id'],body)['id']==second['id'] and len(agents.calls)==2
    assert service.get('UNRELATED',packet['id'])['task']['semantic_report']['recognition']['objects']==1


def test_q_service_only_applies_selected_answer_and_keeps_unselected_draft(system,tmp_path):
    from uuid import uuid4
    from test_plan_semantics import candidate
    from interior.workbench.studio.plan_semantics import PlanSemantics,SaveSemanticAnswers
    studio,plans,packet,_=system
    class Agents:
        def __init__(self):self.tasks={};self.calls=[]
        def start(self,k,model,payload,identifier):
            self.calls.append(payload)
            if payload['site'].get('feedback_version'):
                item=payload['site']['feedback_batch']['items'][0]
                client=Mock();client.run.return_value=dict(text=json.dumps(patch(status='no_change',marks=[dict(mark_id=m['id'],status='no_change',expected_kind='furniture',object_ids=['desk'],summary='Verified source desk') for m in item['marks']])))
                self.tasks[identifier]=dict(status='passed',**run_semantics(client,tmp_path/identifier,payload,model,lambda _:None,lambda _:None))
            else:
                c=candidate(payload['site'])
                c['questions']=[dict(id=i,title=i,ask='What is the source object?',reason='Synthetic Q',source_ids=c['elements'][-1]['source_ids'],box=[0,0,8,.1]) for i in ('q1','q2')]
                self.tasks[identifier]=dict(status='passed',candidate=c)
        def get(self,i):return self.tasks[i]
    agents=Agents();service=PlanSemantics(studio,agents)
    first=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex))
    saved=service.save_answers('UNRELATED',packet['id'],first['id'],SaveSemanticAnswers(base_revision=packet['revision'],answers={'q1':'這是桌子','q2':'這是椅子'},annotations={'q1':[dict(id='q1-area',kind='box',points=[[1.9,1.9],[3.5,2.8]])]}))
    with pytest.raises(Conflict,match='局部反饋'):
        service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex))
    body=SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex,mode='feedback',base_review_id=first['id'],question_ids=['q1'],answers_revision=saved['answers']['revision'])
    second=service.start('UNRELATED',packet['id'],body)
    assert [r['id'] for r in second['site']['feedback_batch']['items']]==['q1']
    assert [r['question']['id'] for r in second['site']['confirmed_answers']]==['q1']
    assert any(q['id']=='q2' for q in second['task']['semantic_report']['questions'])
    assert second['answers']['answers']['q2']=='這是椅子'
    assert second['task']['feedback_results'][0]['status']=='no_change'
    assert not agents.calls[-1]['use_object_recognition']


def test_only_verified_target_pending_is_cleared():
    site,base,audit,item=fixture()
    audit['pending_items'].append(dict(id='desk-a',reason='Target source needs review'));audit.update(pending=2,deferred=2)
    _,revised,_=apply_patch(site,item,base,audit,patch(status='no_change'),validate)
    assert revised['pending_items']==[dict(id='unrelated-pending',reason='retain')]
    assert revised['pending']==1 and revised['findings']==1


def test_server_owned_native_clip_is_reapplied_after_source_derivation():
    from interior.workbench.studio.semantic_feedback import apply_semantic_clips
    site,_,_,_=fixture()
    site['feedback_clips']={'elements:wall':dict(mode='outside',component=0,regions=[[[1,-1],[2,-1],[2,1],[1,1]]],source_ids=['native-a'],feedback_id='synthetic')}
    candidate=dict(elements=[dict(id='wall',role='wall',closed=False,points=[[0,0],[4,0]],source_ids=['native-a'],derivation=dict(method='pair'))])
    apply_semantic_clips(site,candidate)
    assert candidate['elements'][0]['points']==[[0,0],[1,0]]
    candidate['elements'][0]['points']=[[0,0],[4,0]]
    apply_semantic_clips(site,candidate)
    assert candidate['elements'][0]['points']==[[0,0],[1,0]]


def test_later_feedback_invalidates_only_the_touched_completed_object():
    from interior.workbench.studio.semantic_feedback import outcome_still_current
    site,base,audit,item=fixture()
    updated,revised,outcome=apply_patch(site,item,base,audit,patch(operation('elements','desk-a',dict(name='Fixed desk')),
                                      operation('objects','recognition:desk-a',dict(name='Fixed desk'))),validate)
    updated['elements'][1]['name']='Other feedback'
    assert outcome_still_current(outcome,updated,revised,site)
    updated['elements'][0]['name']='Revised same object'
    assert not outcome_still_current(outcome,updated,revised,site)


def test_q_feedback_keeps_unrelated_completed_m_states(system):
    from test_semantic_corrections import setup,save,request,item
    from interior.workbench.studio.plan_semantics import SaveSemanticAnswers
    from uuid import uuid4
    service,packet,first,agents=setup(system)
    saved=save(service,packet,first,[item(1)])
    corrected=service.start('UNRELATED',packet['id'],request(packet,first,saved,[item(1)['id']]))
    agents.tasks[corrected['id']]['candidate']['questions']=[dict(id='another-q',title='Another Q',ask='Source meaning?',reason='Synthetic',source_ids=[corrected['site']['geometry'][0]['id']],box=None)]
    current=service.get('UNRELATED',packet['id'])
    answered=service.save_answers('UNRELATED',packet['id'],current['id'],SaveSemanticAnswers(base_revision=packet['revision'],answers={'another-q':'保留'},annotations={'another-q':[dict(id='answer-area',kind='box',points=[[4,4],[5,5]])]}))
    q=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex,mode='feedback',base_review_id=current['id'],question_ids=['another-q'],answers_revision=answered['answers']['revision']))
    assert q['task']['correction_states'][0]['id']==item(1)['id']
    assert q['task']['correction_states'][0]['preview_ready']


def test_worklist_q_scope_does_not_include_saved_history():
    from interior.workbench.agent_runtime.activity import describe
    result=describe('plan_semantics',dict(site=dict(feedback_batch=dict(items=[dict(id='q1',title='Only this Q')]),confirmed_answers=[dict(question=dict(id='q2',title='Old history'))])))
    assert result['items']==['Only this Q']


from test_plan_semantics import system
