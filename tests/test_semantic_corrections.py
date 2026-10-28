"""Independent correction drafts, exact source coordinates and preview-only batches."""
import copy
import json
from uuid import uuid4

import pytest
from PIL import Image

from test_plan_semantics import system,candidate
from interior.workbench.storage import Conflict,read_json
from interior.workbench.studio.plan_semantics import PlanSemantics,SemanticRequest,validate,run_semantics
from interior.workbench.studio.semantic_corrections import SaveCorrections,get_drafts,save_drafts,draw_batch


class Agents:
    def __init__(self):self.tasks={};self.calls=[]
    def start(self,kind,model,payload,identifier):
        self.calls.append((identifier,payload))
        raw=candidate(payload['site'])
        raw['correction_results']=[dict(id=i['id'],status='no_change',summary='Source position already matches; retain confirmed dimensions.',mark_results=[dict(mark_id=m['id'],status='no_change',expected_kind='room',object_ids=[raw['rooms'][0]['id']],summary='Source region contains this mark.') for m in i['marks']]) for i in payload['site'].get('correction_batch',{}).get('items',[])]
        self.tasks[identifier]=dict(status='passed',candidate=raw)
        if payload['site'].get('feedback_version'):
            self.tasks[identifier]['feedback_results']=[dict(r,preview_ready=True) for r in raw['correction_results']]
    def get(self,identifier):return self.tasks[identifier]


def setup(system):
    studio,plans,packet,site=system
    agents=Agents();service=PlanSemantics(studio,agents)
    run=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex))
    return service,packet,run,agents


def item(n):
    return dict(id='cor-'+str(n)*32,title='Review '+str(n),comment='Retain source dimensions',marks=[dict(id='box-'+str(n),kind='box',points=[[1,1],[2,2]],text=''),dict(id='line-'+str(n),kind='line',points=[[1,1],[2,1]],text=''),dict(id='text-'+str(n),kind='text',points=[[1,2]],text='Check here')])


def save(service,packet,run,items,revision=None):
    return save_drafts(service,'UNRELATED',packet['id'],SaveCorrections(base_revision=packet['revision'],source_task_id=run['id'],correction_revision=revision,items=items))


def request(packet,run,saved,ids):
    return SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex,base_review_id=run['id'],correction_revision=saved['revision'],correction_ids=ids)


def test_save_reopen_immutable_history_and_no_design_adoption(system):
    service,packet,run,_=setup(system);root=service.studio.root('UNRELATED');source=(root/packet['source']['path']).read_bytes()
    assert get_drafts(service,'UNRELATED',packet['id'])['items']==[]
    saved=save(service,packet,run,[item(1),item(2)])
    assert get_drafts(service,'UNRELATED',packet['id'])==saved
    changed=copy.deepcopy(saved['items']);changed[0]['comment']='New draft only'
    newer=save(service,packet,run,changed,saved['revision'])
    with pytest.raises(Conflict,match='其他視窗'):save(service,packet,run,changed,saved['revision'])
    old=service.folder('UNRELATED',packet['id'])/'corrections'/packet['revision']/'revisions'/f"{saved['revision']}.json"
    assert read_json(old)==saved and newer['revision']!=saved['revision']
    assert service.plans.current('UNRELATED',packet['id'])==packet
    assert (root/packet['source']['path']).read_bytes()==source


@pytest.mark.parametrize('change',[
    lambda i:i['marks'][0].update(points=[[1,1],[1,2]]),
    lambda i:i['marks'][1].update(points=[[1,1],[1,1]]),
    lambda i:i['marks'][2].update(text=' '),
    lambda i:i['marks'][2].update(points=[[10000,10000]]),
    lambda i:i['marks'][1].update(points=[[float('nan'),1],[2,1]]),
    lambda i:i['marks'][1].update(id=i['marks'][0]['id']),
])
def test_invalid_geometry_does_not_save(system,change):
    service,packet,run,_=setup(system);raw=item(1);change(raw)
    with pytest.raises(ValueError):save(service,packet,run,[raw])
    assert get_drafts(service,'UNRELATED',packet['id'])['revision'] is None


def test_subset_batch_snapshot_dedup_and_preview_never_adopts(system):
    service,packet,run,agents=setup(system);saved=save(service,packet,run,[item(1),item(2),item(3)])
    body=request(packet,run,saved,[item(1)['id'],item(3)['id']]);result=service.start('UNRELATED',packet['id'],body)
    payload=agents.calls[-1][1];batch=payload['site']['correction_batch']
    assert [i['id'] for i in batch['items']]==body.correction_ids
    assert batch['draft_revision']==saved['revision']
    assert batch['item_labels']=={item(1)['id']:'M1',item(3)['id']:'M3'}
    assert any(p.endswith('correction-batch.png') for p in payload['source_images'])
    assert result['task']['semantic_report']['status']=='preview'
    assert all(r['preview_ready'] for r in result['task']['semantic_report']['corrections'])
    assert service.start('UNRELATED',packet['id'],body)['id']==result['id'] and len(agents.calls)==2
    wrong=body.model_copy(update={'correction_ids':[item(2)['id']]})
    with pytest.raises(Conflict):service.start('UNRELATED',packet['id'],wrong)
    assert service.plans.current('UNRELATED',packet['id'])==packet
    updated=copy.deepcopy(saved['items']);updated[0]['comment']='Later draft'
    save(service,packet,result,updated,saved['revision'])
    assert service.get('UNRELATED',packet['id'],result['id'])['site']['correction_batch']==batch


def test_completion_is_per_item_and_carries_across_selected_batches(system):
    service,packet,run,_=setup(system)
    saved=save(service,packet,run,[item(1),item(2)])
    first=service.start('UNRELATED',packet['id'],request(packet,run,saved,[item(1)['id']]))
    saved=save(service,packet,first,[item(1),item(2),item(3)],saved['revision'])
    states=service.get('UNRELATED',packet['id'],first['id'])['task']['correction_states']
    assert len(states)==1 and states[0]['current'] and states[0]['preview_ready']
    second=service.start('UNRELATED',packet['id'],request(packet,first,saved,[item(2)['id']]))
    states=second['task']['correction_states']
    assert {r['id'] for r in states}=={item(1)['id'],item(2)['id']}
    assert all(r['current'] and r['preview_ready'] for r in states)
    changed=item(1);changed['comment']='New instruction'
    save(service,packet,second,[changed,item(2),item(3)],saved['revision'])
    states={r['id']:r for r in service.get('UNRELATED',packet['id'])['task']['correction_states']}
    assert not states[item(1)['id']]['current'] and states[item(2)['id']]['current']


def test_failed_retry_supersedes_previous_completion(system):
    service,packet,run,agents=setup(system);saved=save(service,packet,run,[item(1)])
    first=service.start('UNRELATED',packet['id'],request(packet,run,saved,[item(1)['id']]))
    second=service.start('UNRELATED',packet['id'],request(packet,first,saved,[item(1)['id']]))
    agents.tasks[second['id']]=dict(status='failed',error='Synthetic failure')
    states=service.get('UNRELATED',packet['id'])['task']['correction_states']
    assert len(states)==1 and states[0]['status']=='unresolved' and not states[0]['preview_ready']


def test_full_reread_does_not_claim_prior_batch_completion(system):
    service,packet,run,_=setup(system);saved=save(service,packet,run,[item(1)])
    service.start('UNRELATED',packet['id'],request(packet,run,saved,[item(1)['id']]))
    reread=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex))
    assert reread['task']['correction_states']==[]


def test_additive_handoff_retains_completed_marks_only_if_geometry_is_preserved(system):
    service,packet,run,agents=setup(system);saved=save(service,packet,run,[item(1)])
    service.start('UNRELATED',packet['id'],request(packet,run,saved,[item(1)['id']]))
    checked=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex,handoff=True))
    states=checked['task']['correction_states']
    assert len(states)==1 and states[0]['current'] and states[0]['preview_ready']
    agents.tasks[checked['id']]['candidate']['elements'][0]['height']=3.1
    assert service.get('UNRELATED',packet['id'])['task']['correction_states']==[]


def test_old_draft_old_candidate_empty_and_missing_selection_block(system):
    service,packet,run,_=setup(system);saved=save(service,packet,run,[item(1),dict(id=item(2)['id'],title='Empty',comment='',marks=[])])
    for ids in [[item(2)['id']],['cor-'+'9'*32],[item(1)['id']]*2]:
        with pytest.raises(ValueError):service.start('UNRELATED',packet['id'],request(packet,run,saved,ids))
    stale=request(packet,run,saved,[item(1)['id']]).model_copy(update={'correction_revision':'f'*32})
    with pytest.raises(Conflict):service.start('UNRELATED',packet['id'],stale)
    result=service.start('UNRELATED',packet['id'],request(packet,run,saved,[item(1)['id']]))
    with pytest.raises(Conflict):service.start('UNRELATED',packet['id'],request(packet,run,saved,[item(1)['id']]))
    assert result['id']!=run['id']


def test_incomplete_per_item_report_retries_and_stays_blocked(system,tmp_path):
    service,packet,run,agents=setup(system);saved=save(service,packet,run,[item(1),item(2)])
    service.start('UNRELATED',packet['id'],request(packet,run,saved,[item(1)['id'],item(2)['id']]))
    site=copy.deepcopy(agents.calls[-1][1]['site']);site.pop('feedback_version',None);raw=candidate(site)
    assert '逐項' in validate(site,raw)[1]['repair_errors'][0]
    class Client:
        calls=0
        def run(self,*args,**kwargs):self.calls+=1;return dict(text=json.dumps(raw))
    client=Client();result=run_semantics(client,tmp_path,dict(site=site,image=agents.calls[-1][1]['image']),'model',lambda x:None,lambda x:None)
    assert client.calls==2 and result['semantic_report']['status']=='blocked'
    raw['correction_results']=[dict(id=item(n)['id'],status='needs_confirmation',summary='Need source evidence') for n in (1,2)]
    assert not any(r['preview_ready'] for r in validate(site,raw)[1]['corrections'])
    assert validate(site,raw)[1]['status']=='blocked'
    raw['correction_results']=[dict(id=item(n)['id'],status='corrected',summary='Updated preview') for n in (1,2)]
    raw['elements']=[e for e in raw['elements'] if e['id']!='desk']
    restored,checked=validate(site,raw)
    assert any(e['id']=='desk' for e in restored['elements'])  # outside the selected area is preserved
    site['correction_batch']['items'][0]['marks']=[dict(id='desk-area',kind='box',points=[[0,0],[8,6]],text='')]
    assert any('遺漏原有家具' in e for e in validate(site,raw)[1]['errors'])


def test_annotations_render_without_modifying_source(tmp_path):
    source=tmp_path/'source.png';Image.new('RGB',(500,400),'white').save(source);before=source.read_bytes()
    image=draw_batch(source,dict(pad=10,scale=40,bounds=[0,0,10,8]),dict(items=[item(1)]),tmp_path)
    assert source.read_bytes()==before and Image.open(image).size==(500,400)
    assert Image.open(image).getpixel((50,250))!=(255,255,255)


def test_failed_attempt_can_explicitly_retry_from_previous_preview(system):
    service,packet,run,agents=setup(system);saved=save(service,packet,run,[item(1)])
    first=service.start('UNRELATED',packet['id'],request(packet,run,saved,[item(1)['id']]))
    agents.tasks[first['id']]=dict(status='failed',error='Synthetic timeout')
    failed=service.get('UNRELATED',packet['id'],first['id'])
    assert failed['task']['status']=='failed' and failed['site']['previous_review']['candidate']
    second=service.start('UNRELATED',packet['id'],request(packet,failed,saved,[item(1)['id']]))
    assert second['task']['semantic_report']['status']=='preview'
    assert service.get('UNRELATED',packet['id'],first['id'])['task']['status']=='failed'
    assert service.plans.current('UNRELATED',packet['id'])==packet


def test_http_draft_save_conflict_auth_and_batch_preview(system):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from interior.workbench.server import create_app
    from interior.workbench.jobs import Jobs
    service,packet,run,agents=setup(system);store=service.studio.store
    with patch.object(Jobs,'loop',return_value=None):app=create_app(store.workspace,store.state_dir)
    app.state.plan_semantics.agents=agents
    endpoint=f"/api/studio/projects/UNRELATED/plans/{packet['id']}/semantics"
    with TestClient(app,base_url='http://127.0.0.1') as client:
        body=dict(base_revision=packet['revision'],source_task_id=run['id'],correction_revision=None,items=[item(1)])
        assert client.get(endpoint+'/corrections').json()['items']==[]
        assert client.put(endpoint+'/corrections',json=body).status_code==403
        headers={'X-Workbench-Token':client.get('/api/session').json()['token']}
        response=client.put(endpoint+'/corrections',json=body,headers=headers)
        assert response.status_code==200,response.text
        saved=response.json();assert client.get(endpoint+'/corrections').json()==saved
        assert client.put(endpoint+'/corrections',json=body,headers=headers).status_code==409
        body=request(packet,run,saved,[item(1)['id']]).model_dump(mode='json')
        result=client.post(endpoint,json=body,headers=headers)
        assert result.status_code==200,result.text
        assert result.json()['task']['semantic_report']['corrections'][0]['preview_ready']
        assert service.plans.current('UNRELATED',packet['id'])==packet


def test_confirmed_vertical_update_preserves_only_exact_authorized_changes(tmp_path):
    from types import SimpleNamespace
    from interior.workbench.studio.semantic_corrections import confirmed_vertical_updates,handoff_geometry_intact
    from interior.workbench.storage import write_json
    from interior.workbench.studio.service import digest
    root=tmp_path;folder=root/'workflows';folder.mkdir();path=folder/'confirmation.json'
    source=root/'sources'/'user.txt';source.parent.mkdir();source.write_text('Confirmed height 104 cm')
    change={'w':{'height':{'before':.9,'after':1.04}}}
    saved=dict(confirmed_by='user',source_revision='revision',original_sha256='source',vertical_updates=change,user_source=dict(path='sources/user.txt',sha256=digest(source)))
    write_json(path,saved)
    service=SimpleNamespace(studio=SimpleNamespace(root=lambda project:root))
    record=dict(source_revision='revision',site=dict(native_dwg=dict(source_sha256='source'),dimension_confirmation=dict(path='workflows/confirmation.json',sha256=digest(path))))
    assert confirmed_vertical_updates(service,'P',record)==change
    old=dict(elements=[dict(id='w',height=.9,points=[[0,0],[0,1]])]);live=copy.deepcopy(old);live['elements'][0]['height']=1.04
    assert handoff_geometry_intact(old,live,change)
    assert not handoff_geometry_intact(old,live,{})
    live['elements'][0]['points'][0][0]=.1
    assert not handoff_geometry_intact(old,live,change)
    path.write_text('{}')
    assert confirmed_vertical_updates(service,'P',record)=={}


def test_answered_questions_do_not_renumber_remaining_source_questions():
    from interior.workbench.studio.semantic_source_questions import label_questions
    site={};questions=[{'id':'beam'},{'id':'floor'}];label_questions(site,questions)
    assert [q['label'] for q in questions]==['Q1','Q2']
    remaining=[{'id':'floor'},{'id':'new'}];label_questions(site,remaining)
    assert [q['label'] for q in remaining]==['Q2','Q3']
    assert site['question_labels']['beam']=='Q1'
