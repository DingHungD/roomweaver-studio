"""Source warnings share Q answers; explicit confirmation remains version-bound."""
import copy
from uuid import uuid4
import pytest

from test_plan_semantics import system,candidate
from interior.workbench.storage import write_json,read_json,Conflict
from interior.workbench.studio.plan_import import check_plan
from interior.workbench.studio.plan_semantics import PlanSemantics,SemanticRequest,SaveSemanticAnswers,AdoptSemantics
from interior.workbench.studio.semantic_source_questions import source_questions,confirmed_ids


def setup(system):
    studio,plans,packet,site=system;packet=copy.deepcopy(packet)
    packet.update(parent=packet['revision'],revision=uuid4().hex)
    packet['parsed']['cad_preparation']['questions'].append(dict(id='cad-floor-outline',kind='floor',text='Please verify the inferred floor boundary.'))
    packet['settings']['reviewed']=[i for i in packet['settings']['reviewed'] if i!='cad-floor-outline']
    packet['check']=check_plan(packet['parsed'],packet['settings'])
    folder=plans.folder('UNRELATED',packet['id']);write_json(folder/'revisions'/f"{packet['revision']}.json",packet);write_json(folder/'current.json',dict(revision=packet['revision']))
    class Agents:
        def __init__(self):self.tasks={};self.payloads=[]
        def start(self,kind,model,payload,identifier):self.payloads.append(payload);self.tasks[identifier]=dict(status='passed',candidate=candidate(payload['site']))
        def get(self,id):return self.tasks[id]
    agents=Agents();service=PlanSemantics(studio,agents)
    return service,packet,agents


def start(service,packet):return service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='fixture',operation_id=uuid4().hex,mode='review'))


def test_floor_warning_is_located_q_but_not_implicitly_accepted(system):
    service,packet,_=setup(system);run=start(service,packet);q=run['source_questions'][0]
    assert q['source_question_id']=='cad-floor-outline' and q['box']==[0,0,8,6] and not run['source_confirmations']
    body=SaveSemanticAnswers(base_revision=packet['revision'],answers={q['id']:'The shape seems right'},annotations={q['id']:[dict(id='frame',kind='box',points=[[0,0],[8,6]])]})
    saved=service.save_answers('UNRELATED',packet['id'],run['id'],body)
    assert not saved['source_confirmations']
    with pytest.raises(ValueError,match='尚未明確確認'):service.adopt('UNRELATED',packet['id'],run['id'],AdoptSemantics(base_revision=packet['revision']))
    assert service.plans.current('UNRELATED',packet['id'])==packet
    body.answers_revision=saved['answers']['revision'];body.source_confirmations=[q['id']];body.source_targets={q['id']:q['target']}
    saved=service.save_answers('UNRELATED',packet['id'],run['id'],body)
    assert saved['source_confirmations']==[q['id']]
    assert service.get('UNRELATED',packet['id'],run['id'])['source_confirmations']==[q['id']]
    assert service.plans.current('UNRELATED',packet['id'])==packet
    adopted=service.adopt('UNRELATED',packet['id'],run['id'],AdoptSemantics(base_revision=packet['revision']))
    assert 'cad-floor-outline' in adopted['settings']['reviewed']
    assert adopted['settings']['units']==packet['settings']['units'] and adopted['parsed']['cad_preparation']['dimensions']==packet['parsed']['cad_preparation']['dimensions']


def test_confirmation_carries_only_to_identical_proposal_and_can_be_revoked(system):
    service,packet,agents=setup(system);run=start(service,packet);q=run['source_questions'][0]
    body=SaveSemanticAnswers(base_revision=packet['revision'],answers={q['id']:'Verified'},source_confirmations=[q['id']],source_targets={q['id']:q['target']})
    service.save_answers('UNRELATED',packet['id'],run['id'],body)
    second=start(service,packet)
    assert second['source_confirmations']==[q['id']]
    assert agents.payloads[-1]['site']['user_source_reviews'][0]['confirmed']
    same=source_questions(packet,second['site'],dict(floor_outline=dict(points=[[8,6],[8,0],[0,0],[0,6]],holes=[])))
    assert confirmed_ids(second,same)==[q['id']]
    new=source_questions(packet,second['site'],dict(floor_outline=dict(points=[[0,0],[7,0],[7,6],[0,6]],holes=[])))
    assert not confirmed_ids(second,new)
    third=service.save_answers('UNRELATED',packet['id'],second['id'],SaveSemanticAnswers(base_revision=packet['revision'],answers={q['id']:'Recheck'},source_confirmations=[]))
    assert not third['source_confirmations']
    with pytest.raises(Conflict):service.save_answers('UNRELATED',packet['id'],second['id'],SaveSemanticAnswers(base_revision=packet['revision'],answers={q['id']:'stale'}))


def test_source_confirmation_does_not_invent_questions_or_modify_source(system):
    service,packet,_=setup(system);run=start(service,packet)
    with pytest.raises(ValueError,match='不存在'):service.save_answers('UNRELATED',packet['id'],run['id'],SaveSemanticAnswers(base_revision=packet['revision'],source_confirmations=['invented']))
    assert not service.get('UNRELATED',packet['id'],run['id'])['source_confirmations']
    assert service.plans.current('UNRELATED',packet['id'])==packet


def test_confirmation_of_an_old_candidate_cannot_accept_new_floor(system):
    service,packet,agents=setup(system);run=start(service,packet);q=run['source_questions'][0]
    body=SaveSemanticAnswers(base_revision=packet['revision'],source_confirmations=[q['id']],source_targets={q['id']:q['target']})
    agents.tasks[run['id']]['candidate']['floor_outline']=dict(points=[[0,0],[7,0],[7,6],[0,6]],holes=[],source_ids=[run['site']['floors'][0]['id']],evidence='Different candidate, must not inherit acceptance')
    with pytest.raises(Conflict,match='候選已變更'):service.save_answers('UNRELATED',packet['id'],run['id'],body)
    assert service.plans.current('UNRELATED',packet['id'])==packet


def test_unconfirmed_source_answer_and_marks_remain_visible_across_rechecks(system):
    service,packet,agents=setup(system);first=start(service,packet);q=first['source_questions'][0]
    text='Boundary remains unconfirmed; retain measured dimensions.'
    marks=[dict(id='pending-label',kind='text',points=[[1,1]],text='Pending review')]
    saved=service.save_answers('UNRELATED',packet['id'],first['id'],SaveSemanticAnswers(base_revision=packet['revision'],answers={q['id']:text},annotations={q['id']:marks}))
    second=start(service,packet)
    assert second['answers']['revision'] is None
    assert second['answers']['answers']=={q['id']:text}
    assert second['answers']['annotations']=={q['id']:marks}
    assert second['source_confirmations']==[]
    assert not (service.folder('UNRELATED',packet['id'])/'runs'/second['id']/'answers.json').exists()
    # A reload reads the same inherited evidence, including in-flight tasks.
    agents.tasks[second['id']]={'status':'running'}
    assert service.get('UNRELATED',packet['id'],second['id'])['answers']==second['answers']
    agents.tasks[second['id']]={'status':'passed','candidate':candidate(second['site'])}
    third=start(service,packet)
    assert third['answers']['answers']=={q['id']:text}
    assert third['answers']['annotations']=={q['id']:marks}
    # Clearing and saving creates a local authoritative revision; never resurrect it.
    cleared=service.save_answers('UNRELATED',packet['id'],third['id'],SaveSemanticAnswers(base_revision=packet['revision']))
    assert cleared['answers']['answers']=={} and cleared['answers']['annotations']=={}
    fourth=start(service,packet)
    assert not fourth['answers']['answers'].get(q['id'])
    assert not fourth['answers']['annotations'].get(q['id'])
    assert service.get('UNRELATED',packet['id'],first['id'])['answers']==saved['answers']
    assert service.plans.current('UNRELATED',packet['id'])==packet
