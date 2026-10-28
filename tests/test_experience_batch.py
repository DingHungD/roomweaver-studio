"""Isolated tests for selected-only, merged experience publication and Q history."""
import copy
from uuid import uuid4

import pytest

from test_plan_semantics import system
from test_semantic_corrections import setup,save,request,item
from test_cad_experience import symbol,entry
from interior.workbench.storage import Conflict
from interior.workbench.studio.experience_review import ExperienceReview
from interior.workbench.studio.experience_batch import ExperienceBatches,BatchExperienceRequest,checked_groups,run_grouping
from interior.workbench.studio.experience_library import ExperienceLibrary
from interior.workbench.studio.plan_semantics import SaveSemanticAnswers,SemanticRequest
from interior.workbench.studio.question_history import question_history


def group(ids,existing=None):
    return dict(member_ids=ids,existing_id=existing,title='同一原生輪廓規則',interpretation='用途區域',mistake='分散的圖線',reason='連續輪廓與附近註解共同支持用途',applies='輪廓及註解相符時',exceptions='不同幾何或用途不得套用',merge_reason='相同辨識條件，保留不同原圖案例')


def batch_case(system):
    semantics,packet,run,agents=setup(system)
    items=[item(1),item(2),item(3)]
    for row in items:
        for mark in row['marks']:mark['points']=[[x-1,y-1] for x,y in mark['points']]
    saved=save(semantics,packet,run,items)
    result=semantics.start('UNRELATED',packet['id'],request(packet,run,saved,[item(1)['id'],item(2)['id']]))
    service=ExperienceBatches(ExperienceReview(semantics))
    original=agents.start
    def start(kind,model,payload,identifier):
        if kind!='cad_experience_batch':return original(kind,model,payload,identifier)
        agents.tasks[identifier]=dict(status='passed',groups=[group([r['id'] for r in payload['items']])])
    agents.start=start
    body=BatchExperienceRequest(base_revision=packet['revision'],review_id=result['id'],correction_revision=saved['revision'],correction_ids=[item(1)['id'],item(2)['id']],operation_id=uuid4().hex,confirmed=True)
    return service,packet,result,saved,body


def test_selected_corrections_merge_once_and_never_adopt_the_design(system):
    service,packet,review,saved,body=batch_case(system)
    before=copy.deepcopy(service.semantics.plans.current('UNRELATED',packet['id']))
    result=service.start('UNRELATED',packet['id'],body)
    assert service.experiences.library.summary()['active']==0
    assert not result['applied']
    applied=service.apply('UNRELATED',packet['id'],result['id'])
    assert len(applied['applied']['entries'])==1
    library=service.experiences.library.catalog()['entries']
    assert len(library)==1 and len(library[0]['examples'])==2
    assert set(service.adoptions('UNRELATED',packet['id']))==set(body.correction_ids)
    assert item(3)['id'] not in service.adoptions('UNRELATED',packet['id'])
    assert service.apply('UNRELATED',packet['id'],result['id'])['applied']==applied['applied']
    assert service.experiences.library.summary()['active']==1
    assert service.semantics.plans.current('UNRELATED',packet['id'])==before
    with pytest.raises(Conflict):service.start('UNRELATED',packet['id'],body.model_copy(update={'correction_ids':[item(3)['id']]}))
    changed=copy.deepcopy(saved['items']);changed[0]['comment']='Different user feedback'
    save(service.semantics,packet,review,changed,saved['revision'])
    assert item(1)['id'] not in service.adoptions('UNRELATED',packet['id'])
    assert item(2)['id'] in service.adoptions('UNRELATED',packet['id'])


def test_incomplete_or_stale_selected_items_never_publish(system):
    service,packet,review,saved,body=batch_case(system)
    with pytest.raises(Conflict):service.start('UNRELATED',packet['id'],body.model_copy(update={'correction_ids':[item(3)['id']]}))
    started=service.start('UNRELATED',packet['id'],body)
    changed=copy.deepcopy(saved['items']);changed[0]['comment']='Changed before publication'
    save(service.semantics,packet,review,changed,saved['revision'])
    with pytest.raises(Conflict):service.apply('UNRELATED',packet['id'],started['id'])
    assert service.experiences.library.summary()['active']==0


def test_group_validation_rejects_extra_missing_and_duplicate_members():
    payload=dict(items=[dict(id='a'),dict(id='b')],existing=[])
    for rows in ([group(['a'])],[group(['a','b','c'])],[group(['a','b']),group(['a'])]):
        with pytest.raises(ValueError):checked_groups(dict(groups=rows),payload)
    assert len(checked_groups(dict(groups=[group(['a','b'])]),payload))==1


def test_existing_experience_gets_examples_instead_of_duplicate_entry(tmp_path):
    library=ExperienceLibrary(tmp_path/'library');_,_,descriptor,image=symbol(tmp_path)
    existing=library._publish_confirmed(entry(descriptor),image)
    _,_,second,image2=symbol(tmp_path,'parallel',offset=(20,40))
    combined=group(['b'],existing['id']);combined.update(existing_revision=existing['revision'],examples=[dict(id='second',descriptor=second,source_image=str(image2),provenance=dict(synthetic=True))])
    published=library.publish_groups([combined],dict(batch_id='synthetic'))
    assert published[0]['id']==existing['id'] and library.summary()['active']==1
    assert len(library.catalog()['entries'][0]['examples'])==2
    assert library.search(second)['hits'][0]['id']==existing['id']
    with pytest.raises(Conflict):library.publish_groups([combined],dict(batch_id='stale'))
    assert library.summary()['active']==1


def test_question_history_keeps_completed_answer_and_current_empty_answer(system):
    service,packet,run,agents=setup(system)
    question=dict(id='native-meaning',title='原生線用途',ask='線條代表什麼？',reason='未註明',source_ids=[run['site']['geometry'][0]['id']],box=None)
    agents.tasks[run['id']]['candidate']['questions']=[question]
    run=service.get('UNRELATED',packet['id'],run['id'])
    service.save_answers('UNRELATED',packet['id'],run['id'],SaveSemanticAnswers(base_revision=packet['revision'],answers_revision=None,answers={question['id']:'天花板樑'}))
    newer=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='synthetic',operation_id=uuid4().hex,mode='review'))
    history=question_history(service,'UNRELATED',packet['id'],newer['id'])
    row=next(q for q in history['questions'] if q['id']==question['id'])
    assert row['answer']=='天花板樑' and row['status']=='resolved'
    assert row['versions'][0]['review_id']==run['id']
    assert service.plans.current('UNRELATED',packet['id'])==packet


def test_vertical_confirmation_can_be_recovered_from_same_source_lineage(tmp_path):
    from types import SimpleNamespace
    from interior.workbench.storage import write_json
    from interior.workbench.studio.service import digest
    from interior.workbench.studio.semantic_corrections import confirmed_vertical_updates
    root=tmp_path;source=root/'sources/user.txt';source.parent.mkdir();source.write_text('104 cm')
    proof=root/'workflows/confirmation.json';write_json(proof,dict(confirmed_by='user',source_revision='same',original_sha256='dwg',user_source=dict(path='sources/user.txt',sha256=digest(source)),vertical_updates={'w':{'height':{'before':.9,'after':1.04}}}))
    site=dict(native_dwg=dict(source_sha256='dwg'),geometry=[],texts=[],dimensions=[])
    parent=dict(id='a'*32,source_revision='same',site=dict(site,dimension_confirmation=dict(path='workflows/confirmation.json',sha256=digest(proof))))
    folder=root/'workflows/plan/semantics';write_json(folder/'runs'/parent['id']/'request.json',parent)
    current=dict(id='b'*32,source_revision='same',site=dict(site,previous_review=dict(task_id=parent['id'])))
    service=SimpleNamespace(studio=SimpleNamespace(root=lambda p:root),folder=lambda p,plan:folder)
    assert confirmed_vertical_updates(service,'P',current,'plan')['w']['height']['after']==1.04
    assert current['site']['dimension_confirmation']['updates']['w']['height']['after']==1.04
    different=dict(current,source_revision='other',site=dict(site,previous_review=dict(task_id=parent['id'])))
    assert confirmed_vertical_updates(service,'P',different,'plan')=={}


def test_new_object_bound_correction_preserves_existing_snapshots(system):
    service,packet,review,saved,body=batch_case(system)
    before=copy.deepcopy(saved['items'])
    new=dict(id='cor-'+'4'*32,title='Object feedback',comment='',marks=[dict(id='source-box',kind='box',points=[[0,0],[1,1]],text='')],target_id='room:living',target_kind='object')
    saved=save(service.semantics,packet,review,[*before,new],saved['revision'])
    assert saved['items'][:-1]==before and saved['items'][-1]['target_id']=='room:living'
    states=service.semantics.get('UNRELATED',packet['id'])['task']['correction_states']
    assert len(states)==2 and all(row['current'] and row['preview_ready'] for row in states)


def test_handoff_review_can_prepare_inherited_completed_correction(system):
    service,packet,review,saved,body=batch_case(system)
    next_review=service.semantics.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='synthetic',operation_id=uuid4().hex,handoff=True))
    assert 'correction_batch' not in next_review['site']
    from interior.workbench.studio.experience_review import CreateExperience
    draft=service.experiences.create('UNRELATED',packet['id'],CreateExperience(base_revision=packet['revision'],review_id=next_review['id'],kind='correction',target_id=body.correction_ids[0]))
    assert draft['correction_revision']==saved['revision'] and not draft['confirmed']
