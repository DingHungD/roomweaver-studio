"""Semantic handoff on unrelated drawings; no client coordinates or model calls."""
import copy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import ezdxf
import pytest

from interior.workbench.jobs import Jobs
from interior.workbench.storage import Store,Conflict,read_json
from interior.workbench.studio.service import Studio
from interior.workbench.studio.plan_import import PlanIntake,BuildPlan,SavePlan,check_plan
from interior.workbench.studio.plan_semantics import PlanSemantics,SemanticRequest,AdoptSemantics,site_packet,validate,run_semantics
from interior.workbench.studio.intake_contract import intake_report


def test_agent_context_omits_duplicate_host_ledger_but_keeps_source_and_confirmations():
    from interior.workbench.studio.plan_semantics import agent_site
    site=dict(geometry=[dict(id='native-edge',points=[[0,0],[1,0]])],dimensions=[dict(id='confirmed-width',value=100)],user_source_reviews=[dict(answer='Confirmed cm')],previous_review=dict(candidate=dict(elements=[dict(id='chair',source_ids=['native-edge'],source_binding=dict(method='bounds'),derivation=dict(large_host_trace='x'*50000))]),report=dict(coverage=dict(duplicate_ledger='x'*1000000),questions=[dict(id='retained-Q')],repair_errors=['Retain this actual error'])))
    original=copy.deepcopy(site);compact=agent_site(site)
    assert site==original and compact['geometry']==site['geometry'] and compact['dimensions']==site['dimensions'] and compact['user_source_reviews']==site['user_source_reviews']
    assert compact['previous_review']['report']==dict(questions=[dict(id='retained-Q')],repair_errors=['Retain this actual error'])
    assert 'derivation' not in compact['previous_review']['candidate']['elements'][0]


def drawing(path,scale=1,offset=(0,0),unit=6):
    doc=ezdxf.new();doc.units=unit;m=doc.modelspace()
    def p(x,y):return (offset[0]+x*scale,offset[1]+y*scale)
    m.add_lwpolyline([p(0,0),p(8,0),p(8,6),p(0,6)],close=True,dxfattribs={'layer':'floor'})
    m.add_line(p(0,0),p(8,0),dxfattribs={'layer':'wall'})
    m.add_text('Living room',dxfattribs={'insert':p(2,3),'height':.2*scale})
    doc.saveas(path)


def candidate(site,furniture=True):
    wall=next(g for g in site['geometry'] if g['kind']=='LINE')
    room=dict(id='living',name='Living room',points=[[0,0],[8,0],[8,6],[0,6]],source_ids=[site['texts'][0]['id']],evidence='Native room label')
    def item(id,role,points,**kw):
        return dict(id=id,name=id,role=role,points=points,room_id='living',closed=role=='furniture',source_ids=[wall['id']],evidence='Source drawing',**kw)
    elements=[item('wall','wall',[[0,0],[8,0]]),item('door','door',[[1,0],[2,0]],host_id='wall',height=2.1),item('window','window',[[4,0],[5,0]],host_id='wall',height=1.2,base=1)]
    if furniture:elements.append(item('desk','furniture',[[2,2],[3.4,2],[3.4,2.7],[2,2.7]],height=.75,asset='desk'))
    return dict(summary='Source-only interpretation',rooms=[room],elements=elements,door_state='present',window_state='present',furniture_state='present' if furniture else 'absent',inventory_evidence='Source furniture inventory',questions=[])


@pytest.fixture
def system(tmp_path,monkeypatch):
    # Most semantic tests exercise contracts, not browser rasterization. The
    # source SVG and real Chromium capture have separate integration coverage.
    from PIL import Image
    monkeypatch.setattr('interior.workbench.studio.cad_source.rasterize',lambda markup,path,width,height:Image.new('RGB',(width,height),'white').save(path))
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='UNRELATED',name='Synthetic'))
    with patch.object(Jobs,'loop',return_value=None):jobs=Jobs(store)
    studio=Studio(store,jobs);plans=PlanIntake(studio)
    path=tmp_path/'unrelated.dxf';drawing(path)
    packet=plans.create('UNRELATED',path.name,path.read_bytes())
    settings=copy.deepcopy(packet['settings']);settings['cad_unit_confirmed']=True
    settings['reviewed']=[q['id'] for q in packet['parsed']['cad_preparation']['questions']]
    packet=plans.save('UNRELATED',packet['id'],SavePlan(base_revision=packet['revision'],settings=settings))
    site=site_packet(dict(packet,_root=str(studio.root('UNRELATED'))))
    yield studio,plans,packet,site
    jobs.close()


@pytest.mark.parametrize('scale,offset,unit',[(1,(0,0),6),(100,(8000,-4000),5),(1000,(-30000,50000),4)])
def test_local_coordinates_and_units_generalize(tmp_path,scale,offset,unit):
    from interior.workbench.studio.plan_import import parse_dxf,suggested_settings
    path=tmp_path/'different.dxf';drawing(path,scale,offset,unit)
    parsed=parse_dxf(path);settings=suggested_settings(parsed)
    site=site_packet(dict(parsed=parsed,settings=settings,revision='v1',source={'path':path.name},_root=str(tmp_path)))
    raw=candidate(site);proposal,report=validate(site,raw)
    assert report['status']=='preview' and report['room_count']==1
    assert site['dimensions']==[] and proposal['rooms'][0]['name']=='Living room'


def test_unknown_sources_host_and_wall_evidence_blocked(system):
    _,_,_,site=system;raw=candidate(site)
    raw['elements'][1]['points'][0][1]=.5
    assert any('對齊' in x for x in validate(site,raw)[1]['errors'])
    raw=candidate(site);raw['elements'][0]['points']=[[0,4],[8,4]]
    assert any('來源線條' in x for x in validate(site,raw)[1]['errors'])
    raw=candidate(site);raw['rooms'][0]['source_ids']=['invented']
    with pytest.raises(ValueError,match='來源'):validate(site,raw)
    raw=candidate(site);raw['elements'].append(copy.deepcopy(raw['elements'][0]))
    with pytest.raises(ValueError,match='重複'):validate(site,raw)


def test_handoff_separate_from_geometry_and_conditional_layout(system):
    _,_,packet,site=system
    assert packet['check']['status']=='ready'
    assert intake_report(packet['parsed'],packet['settings'])['status']=='blocked'
    semantic=dict(rooms=candidate(site)['rooms'],door_state='absent',window_state='absent',furniture_state='absent')
    packet['parsed']['intake_semantics']=semantic
    settings=packet['settings'];settings['intake_review']=dict(purposes=True,structure=True,furniture=True)
    report=intake_report(packet['parsed'],settings)
    assert report['layout_mode']=='generate' and 'AI 空間配置' in report['errors'][0]
    settings['assignments'].append(dict(id='new-furniture',role='furniture'))
    assert intake_report(packet['parsed'],settings)['status']=='blocked'
    settings['layout_adoption']={'proposal_id':'a'*32}
    assert intake_report(packet['parsed'],settings)['status']=='ready'
    semantic['furniture_state']='present'
    assert intake_report(packet['parsed'],settings)['layout_mode']=='preserve'
    semantic['window_state']='uncertain'
    assert intake_report(packet['parsed'],settings)['status']=='blocked'


def test_adoption_revision_confirm_save_reopen_and_build_gate(system):
    studio,plans,packet,site=system
    class Agents:
        def start(self,kind,model,payload,identifier):
            self.result=dict(status='passed',candidate=candidate(payload['site']))
        def get(self,identifier):return self.result
    service=PlanSemantics(studio,Agents())
    req=SemanticRequest(base_revision=packet['revision'],model='test-model',operation_id=uuid4().hex)
    run=service.start('UNRELATED',packet['id'],req)
    assert service.start('UNRELATED',packet['id'],req)['id']==run['id']
    with pytest.raises(ValueError,match='交接未完成'):
        plans.build('UNRELATED',packet['id'],BuildPlan(plan_revision=packet['revision'],confirmed=True))
    adopted=service.adopt('UNRELATED',packet['id'],run['id'],AdoptSemantics(base_revision=packet['revision']))
    assert adopted['check']['status']=='ready' and adopted['check']['intake']['status']=='blocked'
    assert adopted['check']['basic_model'] and adopted['check']['rooms'][0]['id']=='living'
    assert adopted['parsed']['features'][:len(packet['parsed']['features'])]==packet['parsed']['features']
    assert not any(adopted['settings']['intake_review'].values())
    with pytest.raises(Conflict):service.adopt('UNRELATED',packet['id'],run['id'],AdoptSemantics(base_revision=packet['revision']))
    settings=copy.deepcopy(adopted['settings']);settings['intake_review']=dict(purposes=True,structure=True,furniture=True)
    saved=plans.save('UNRELATED',packet['id'],SavePlan(base_revision=adopted['revision'],settings=settings))
    reopened=plans.current('UNRELATED',packet['id'])
    assert reopened['check']['intake']['status']=='ready'
    assert reopened['settings']['intake_review']==settings['intake_review']
    job=plans.build('UNRELATED',packet['id'],BuildPlan(plan_revision=saved['revision'],confirmed=True))
    request=read_json(studio.store.state_dir/'jobs'/job['id']/'request.json')
    assert read_json(studio.root('UNRELATED')/request['parameters']['source']['plan'])['check']['basic_model']
    changed=copy.deepcopy(saved['settings']);next(a for a in changed['assignments'] if a['role']=='furniture')['height']+=.1
    edited=plans.save('UNRELATED',packet['id'],SavePlan(base_revision=saved['revision'],settings=changed))
    assert edited['settings']['intake_review']==dict(purposes=True,structure=True,furniture=False)
    assert Path(studio.root('UNRELATED')/packet['source']['path']).read_bytes().startswith(b'  0')


def test_bounded_agent_retry_retains_unresolved_reasons(system,tmp_path):
    import json
    _,_,_,site=system;raw=candidate(site);raw['questions']=['Which window symbol?']
    class Client:
        calls=0
        def run(self,*args,**kwargs):self.calls+=1;return dict(text=json.dumps(raw))
    client=Client();result=run_semantics(client,tmp_path,dict(site=site,image='unused.png'),'model',lambda x:None,lambda x:None)
    assert client.calls==2 and result['semantic_report']['status']=='blocked'
    assert 'Which window symbol?' in result['semantic_report']['errors']


def test_recognition_pending_survives_reopen_and_blocks_adopt(system):
    studio,plans,packet,site=system
    audit=dict(workflow='agent_native_v1',status='blocked',deferred=1,scan_findings=0,scan_failures=0,layers=dict(items=[],lighting_reviewed=True))
    class Agents:
        def start(self,kind,model,payload,identifier):
            self.result=dict(status='passed',candidate=candidate(payload['site']),yolo_review=audit)
        def get(self,identifier):return self.result
    service=PlanSemantics(studio,Agents())
    record=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex))
    reopened=service.get('UNRELATED',packet['id'],record['id'])
    assert reopened['task']['semantic_report']['recognition']==audit
    assert reopened['task']['semantic_report']['status']=='blocked'
    with pytest.raises(ValueError,match='待處理'):
        service.adopt('UNRELATED',packet['id'],record['id'],AdoptSemantics(base_revision=packet['revision']))


def test_source_review_precedes_main_agent_and_its_objects_enter_the_prompt(system,tmp_path,monkeypatch):
    import json
    _,_,_,site=system;calls=[]
    audit=dict(workflow='agent_native_v1',status='reviewed_preview',deferred=0,scan_findings=0,scan_failures=0,layers=dict(items=[],lighting_reviewed=True))
    def prepared(payload,output,progress):calls.append('inference');return tmp_path/'bundle'
    def reviewed(client,payload,folder,output,model,progress,event):
        calls.append('native-review');payload['site']=dict(payload['site'],yolo_reviewed=dict(objects=[dict(name='source-reviewed-object')]))
        return audit
    def legacy(*a,**kw):raise AssertionError('Native workflow must not repeat legacy review')
    monkeypatch.setattr('interior.workbench.studio.yolo_review.prepare',prepared)
    monkeypatch.setattr('interior.workbench.studio.yolo_review.review_native',reviewed)
    monkeypatch.setattr('interior.workbench.studio.yolo_review.review',legacy)
    class Client:
        def run(self,instruction,**kwargs):
            calls.append('main-agent');assert 'source-reviewed-object' in instruction
            return dict(text=json.dumps(candidate(site)))
    result=run_semantics(Client(),tmp_path,dict(site=site,image='unused.png'),'selected',lambda _:None,None)
    assert calls==['inference','native-review','main-agent']
    assert result['semantic_report']['recognition']==audit
