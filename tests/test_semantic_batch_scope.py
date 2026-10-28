"""Synthetic incremental batches preserve unrelated source decisions and cards."""
import copy
from uuid import uuid4

from test_plan_semantics import system
from test_cad_candidates import fixture,fridge_patch
from test_semantic_corrections import save,request,item
from test_cad_experience import service_case
from interior.workbench.studio.cad_candidates import assess,inventory,fingerprint,source_hash,apply_report,component_group
from interior.workbench.studio.semantic_batch import inherited_decisions,constrain
from interior.workbench.studio.plan_semantics import validate,AdoptSemantics
from interior.workbench.studio.experience_review import prepare_batch_experiences,ExperienceFields
from interior.workbench.storage import read_json,write_json


def batch(site,base,report):
    site=copy.deepcopy(site)
    site['previous_review']=dict(candidate=base,report=report,source_hash=source_hash(site))
    site['correction_batch']=dict(items=[dict(id='cor-'+'1'*32,title='Fridge',comment='Check only this appliance',marks=[dict(kind='box',points=[[4.9,1.9],[5.7,2.7]])])],selected_ids=['cor-'+'1'*32])
    return site


def test_native_furniture_can_contract_to_its_own_components_without_expanding_scope():
    baseline=dict(id='fixture',role='furniture',points=[[0,0],[2,0],[2,2],[0,2]],closed=True,height=2,base=0,source_ids=['component'])
    unrelated=dict(baseline,id='other',points=[[4,0],[5,0],[5,1],[4,1]])
    site=dict(geometry=[],previous_review=dict(candidate=dict(elements=[baseline,unrelated],door_state='none',window_state='none',furniture_state='present')),correction_batch=dict(items=[dict(marks=[dict(points=[[0,0],[1,2]])])]))
    proposed=dict(baseline,points=[[0,0],[1,0],[1,2],[0,2]],height=.1,source_binding=dict(method='bounds',refs=[dict(id='component',edge=0)]),derivation=dict(method='bounds'))
    result,_=constrain(site,dict(elements=[proposed,dict(unrelated,name='Unrequested')]),resolved=True)
    assert result['elements'][0]['points']==proposed['points'] and result['elements'][0]['height']==2
    assert result['elements'][1]==unrelated
    proposed['points']=[[0,0],[3,0],[3,2],[0,2]]
    assert constrain(site,dict(elements=[proposed,unrelated]),resolved=True)[0]['elements'][0]==baseline


def test_whole_proposal_cannot_rewrite_unselected_objects_or_add_unrelated_questions(system):
    site,base,report,_=fixture(system);site=batch(site,base,report)
    raw=copy.deepcopy(base);desk=next(i for i in raw['elements'] if i['id']=='desk');desk.update(name='Wrong cabinet',category='cabinet',height=9)
    raw['elements']+=fridge_patch()['elements']
    outside=copy.deepcopy(fridge_patch()['elements'][0]);outside.update(id='outside-fridge',points=[[.1,4],[.5,4],[.5,4.5],[.1,4.5]])
    raw['elements'].append(outside)
    raw['questions']=[dict(id='outside-q',title='Not selected',ask='Unrelated question',reason='Not part of this batch',source_ids=['text-fridge'],box=[0,4,1,5])]
    updated,checked=validate(site,raw)
    assert next(i for i in updated['elements'] if i['id']=='desk')==next(i for i in base['elements'] if i['id']=='desk')
    assert any(i['id']=='fridge' for i in updated['elements'])
    assert not any(i['id']=='outside-fridge' for i in updated['elements']) and not updated['questions']
    assert 'outside-fridge' in checked['batch_scope']['excluded']
    assert base!=updated


def test_resolved_source_binding_cannot_move_a_host_outside_the_marked_area(system):
    site,base,report,_=fixture(system);site=batch(site,base,report)
    raw=copy.deepcopy(base);wall=raw['elements'][0];baseline=copy.deepcopy(wall)
    wall['points']=[[p[0],p[1]+1] for p in wall['points']]
    updated,audit=constrain(site,raw,resolved=True)
    assert updated['elements'][0]==baseline and wall['id'] in audit['preserved']


def test_individual_completed_source_decisions_survive_an_unrelated_candidate_change(system):
    site,base,report,row=fixture(system)
    decision=dict(action='ignore',object_ids=[],source_ids=row['source_ids'],reason='Confirmed reference-only note',source_target=fingerprint(next(r for r in inventory(site) if r['id']==row['id'])))
    report['coverage']=assess(site,base,report,{row['id']:decision})
    site=batch(site,base,report)
    changed=copy.deepcopy(base);changed['summary']='Only another part of the plan changed'
    retained=inherited_decisions(site,changed)
    assert retained[row['id']]==decision
    coverage=apply_report(site,changed,validate(site,changed)[1])['coverage']
    assert coverage['counts']['pending']==0 and coverage['counts']['ignored']==1
    site['texts'][-1]['text']='A different native annotation'
    assert not inherited_decisions(site,changed)


def test_area_annotation_does_not_reset_a_reviewed_physical_source(system):
    site,base,report,row=fixture(system)
    decision=dict(action='ignore',object_ids=[],source_ids=row['source_ids'],reason='Demand text; no positioned equipment',source_target=fingerprint(next(r for r in inventory(site) if r['id']==row['id'])))
    report['coverage']=assess(site,base,report,{row['id']:decision});site=batch(site,base,report)
    changed=copy.deepcopy(base)
    room=copy.deepcopy(changed['rooms'][0]);room.update(id='circulation',name='Circulation',source_ids=row['source_ids'])
    changed['rooms'].append(room)
    assert inherited_decisions(site,changed)[row['id']]==decision


def test_a_changed_referenced_object_reopens_only_its_dependent_source(system):
    site,base,report,row=fixture(system);base['elements']+=fridge_patch()['elements']
    ignored=dict(action='ignore',object_ids=[],source_ids=row['source_ids'],reason='Old review',source_target=fingerprint(next(r for r in inventory(site) if r['id']==row['id'])))
    report['coverage']=assess(site,base,report,{row['id']:ignored})
    site=batch(site,base,report)
    changed=copy.deepcopy(base);changed['elements'][-1]['category']='cabinet'
    assert row['id'] not in inherited_decisions(site,changed)
    assert assess(site,changed,report,inherited_decisions(site,changed))['counts']['pending']==1


def test_previously_answered_identical_question_is_not_asked_again(system):
    site,base,report,_=fixture(system);site=batch(site,base,report)
    q=dict(id='answered',title='Appliance purpose',ask='Is this the fridge?',reason='Source note',source_ids=['text-fridge'],box=[5,2,5.6,2.6])
    site['confirmed_answers']=[dict(question=q,answer='Yes, already confirmed')]
    raw=copy.deepcopy(base);raw['questions']=[q]
    assert not constrain(site,raw)[0]['questions']
    # Even an older candidate still listing the answered Q must not reintroduce
    # it when the new selection is elsewhere.
    site['previous_review']['candidate']['questions']=[q]
    site['correction_batch']['items'][0]['marks']=[dict(kind='box',points=[[1,1],[2,2]])]
    assert not constrain(site,raw)[0]['questions']


def test_cross_segment_frame_is_accounted_for_without_inventing_a_new_opening():
    row=dict(kind='frame',source_ids=['frame'],options=[dict(points=[[0,0],[4,0]])])
    elements=[dict(id='one',role='window',points=[[0,0],[2,0]],source_ids=['frame']),dict(id='two',role='window',points=[[2,0],[4,0]],source_ids=['frame'])]
    assert set(component_group(row,dict(elements=elements),['one','two']))=={'one','two'}
    elements[1]['points']=[[3.5,0],[4,0]]
    assert not component_group(row,dict(elements=elements),['one','two'])


def test_reconcile_legacy_batch_preserves_history_card_edits_and_never_calls_agent(service_case,monkeypatch):
    experience,packet,run,agents=service_case;service=experience.semantics
    saved=save(service,packet,run,[item(1),item(2),item(3)])
    reviewed=service.start('UNRELATED',packet['id'],request(packet,run,saved,[i['id'] for i in saved['items']]))
    # Model an actual pre-local-feedback run; new runs cannot use legacy replay.
    path=service.folder('UNRELATED',packet['id'])/'runs'/reviewed['id']/'request.json'
    legacy=read_json(path);legacy['site'].pop('feedback_version',None);write_json(path,legacy)
    reviewed=service.get('UNRELATED',packet['id'],reviewed['id'])
    payload=agents.calls[-1][1]
    prepare_batch_experiences(payload,reviewed['task']['candidate'],reviewed['task']['semantic_report'])
    drafts=experience.list('UNRELATED',packet['id'])['drafts'];chosen=drafts[0]
    fields={k:chosen[k] for k in ('title','interpretation','mistake','reason','applies','exceptions')};fields['reason']='User edited, do not erase'
    experience.save('UNRELATED',packet['id'],chosen['id'],ExperienceFields(draft_revision=chosen['revision'],**fields))
    old_get=agents.get
    def get(identifier):
        if identifier not in agents.tasks:raise FileNotFoundError(identifier)
        return old_get(identifier)
    monkeypatch.setattr(agents,'get',get)
    # A new, unselected draft must not invalidate the immutable selected items.
    save(service,packet,reviewed,[*saved['items'],item(4)],saved['revision'])
    before=copy.deepcopy(service.plans.current('UNRELATED',packet['id']));old_task=copy.deepcopy(agents.tasks[reviewed['id']]);calls=len(agents.calls)
    result=service.reconcile_batch('UNRELATED',packet['id'],reviewed['id'],AdoptSemantics(base_revision=packet['revision']))
    assert len(agents.calls)==calls and result['task']['model_called'] is False
    assert result['id']!=reviewed['id'] and service.get('UNRELATED',packet['id'])['id']==result['id']
    assert service.plans.current('UNRELATED',packet['id'])==before and agents.tasks[reviewed['id']]==old_task
    newer=experience.list('UNRELATED',packet['id'])['drafts']
    assert {d['id'] for d in newer}=={d['id'] for d in drafts}
    assert all(d['review_id']==result['id'] and not d['confirmed'] for d in newer)
    assert next(d for d in newer if d['id']==chosen['id'])['reason']=='User edited, do not erase'
    assert experience.library.summary()['active']==0
