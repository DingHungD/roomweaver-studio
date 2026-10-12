"""Synthetic layout proposals: geometry, protected baseline and revision adoption."""
import copy
import json
from unittest.mock import patch

import ezdxf
import pytest

from interior.workbench.storage import Store, Conflict
from interior.workbench.jobs import Jobs
from interior.workbench.studio.service import Studio
from interior.workbench.studio.plan_import import PlanIntake, SavePlan, Assignment
from interior.workbench.studio.layout_design import (
    LayoutDesign, LayoutRequest, AdoptLayout, LayoutBrief, site_packet, review_layout, run_layout,
    ReviseLayout,
    LayoutAnswers, validate_source_questions,
)


class Agents:
    def __init__(self):self.tasks={};self.calls=0
    def start(self,kind,model,payload,identifier):
        self.calls+=1;self.tasks[identifier]=dict(id=identifier,status='queued',kind=kind,payload=payload)
        return self.tasks[identifier]
    def get(self,identifier):return self.tasks[identifier]


@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='LAYOUT',name='Synthetic'))
    with patch.object(Jobs,'loop',return_value=None):jobs=Jobs(store)
    studio=Studio(store,jobs);agents=Agents();service=LayoutDesign(studio,agents)
    doc=ezdxf.new();doc.units=6;m=doc.modelspace()
    m.add_lwpolyline([(0,0),(6,0),(6,6),(0,6)],close=True,dxfattribs={'layer':'floor'})
    m.add_line((0,0),(6,0),dxfattribs={'layer':'wall'})
    m.add_line((0,0),(0,6),dxfattribs={'layer':'wall'})
    m.add_line((6,0),(6,6),dxfattribs={'layer':'wall'})
    m.add_line((0,6),(6,6),dxfattribs={'layer':'wall'})
    m.add_lwpolyline([(4,4),(5,4),(5,5),(4,5)],close=True,dxfattribs={'layer':'furniture'})
    path=tmp_path/'synthetic.dxf';doc.saveas(path)
    plan=service.plans.create('LAYOUT',path.name,path.read_bytes())
    request=LayoutRequest(base_revision=plan['revision'],model='fake-test',operation_id='test-request-1',brief='Two adults need a study and a clear route.',requirements=['Add one desk'],passage_width=.8)
    yield service,agents,plan,request
    jobs.close()


def proposal():
    return dict(summary='Desk facing south with a working zone.',placements=[dict(id='desk1',target_id=None,asset='desk',name='Desk',center=[3,4],size=[1.2,.6],height=.75,rotation=0,reason='Keep the western route free.',requirement_ids=['R1'])],
        routes=[dict(name='Entry to study',points=[[1,1],[1,3],[2.5,3]],width=.8,reason='Access to desk')],
        use_zones=[dict(name='Desk operation',object_id='desk1',points=[[2.4,2.9],[3.6,2.9],[3.6,3.65],[2.4,3.65]],purpose='Chair access')],
        coverage=[dict(requirement_id='R1',status='addressed',object_ids=['desk1'],reason='Added desk and access')],assumptions=['Concept dimensions'],questions=[])


def test_concept_adoption_requires_explicit_limits_and_carries_issues(setup):
    service,agents,plan,request=setup
    p=proposal();p['use_zones']=[]
    run=service.start('LAYOUT',plan['id'],request)
    agents.tasks[run['id']].update(status='passed',candidate=p)
    _,report=review_layout(run['site'],p)
    assert report['errors'] and not report['hard_errors']
    with pytest.raises(ValueError):service.adopt('LAYOUT',plan['id'],run['id'],AdoptLayout(base_revision=plan['revision'],accept_assumptions=True))
    adopted=service.adopt('LAYOUT',plan['id'],run['id'],AdoptLayout(base_revision=plan['revision'],accept_assumptions=True,accept_layout_limits=True))
    assert adopted['settings']['layout_adoption']['concept_only']
    assert adopted['settings']['layout_adoption']['remaining_issues']==report['errors']


def test_repair_is_immutable_preview_and_rejects_deletion_shrink_and_stale(setup):
    service,agents,plan,request=setup
    parent=service.start('LAYOUT',plan['id'],request)
    agents.tasks[parent['id']].update(status='passed',candidate=proposal())
    body=ReviseLayout(base_revision=plan['revision'],operation_id='repair-test-0001',candidate=proposal(),
        rationale='Review existing confirmations and preserve every required object.',
        sources=[dict(label='Synthetic confirmation',reference='fixture/confirmation',sha256='a'*64)])
    revised=service.revise('LAYOUT',plan['id'],parent['id'],body)
    assert revised['task']['status']=='preview' and revised['parent_id']==parent['id']
    assert service.revise('LAYOUT',plan['id'],parent['id'],body)['id']==revised['id']
    assert agents.calls==1
    assert service.plans.current('LAYOUT',plan['id'])['revision']==plan['revision']
    with pytest.raises(Conflict,match='尚未完成'):
        service.adopt('LAYOUT',plan['id'],revised['id'],AdoptLayout(base_revision=plan['revision'],accept_assumptions=True))
    for fault in ('shrink','delete','route'):
        bad=body.model_copy(deep=True);bad.operation_id='repair-bad-'+fault
        if fault=='shrink':bad.candidate.placements[0].size=(.5,.5)
        if fault=='delete':
            bad.candidate.placements=[];bad.candidate.use_zones=[];bad.candidate.coverage[0].object_ids=[]
        if fault=='route':bad.candidate.routes[0].name='Omitted original trip'
        with pytest.raises(ValueError,match='不能'):service.revise('LAYOUT',plan['id'],parent['id'],bad)
    saved=service.plans.save('LAYOUT',plan['id'],SavePlan(base_revision=plan['revision'],settings=plan['settings']))
    with pytest.raises(Conflict,match='舊版'):service.revise('LAYOUT',plan['id'],parent['id'],body)


def test_seated_zone_exempts_only_a_facing_adjacent_chair_not_route_or_other_furniture(setup):
    _,_,plan,request=setup;site=site_packet(plan,request);p=proposal()
    p['placements'].append(dict(id='seat',target_id=None,asset='chair',name='Seat',center=[3,3.3],size=[.5,.5],height=.85,rotation=180,reason='Face desk',requirement_ids=['R1']))
    p['use_zones']=[dict(name='Seated',object_id='desk1',points=[[2.7,3],[3.3,3],[3.3,3.6],[2.7,3.6]],purpose='Occupied chair',kind='seated',seat_id='seat'),
        dict(name='Pull out',object_id='seat',points=[[2.7,2.4],[3.3,2.4],[3.3,3],[2.7,3]],purpose='Empty access')]
    p['routes'][0]['points']=[[1,1],[1,3]]
    assert review_layout(site,p)[1]['status']=='ready'
    p['routes'][0]['points']=[[3,1],[3,3.6]]
    report=review_layout(site,p)[1]
    assert report['status']=='blocked' and report['routes'][0]['movable_obstacles']==['seat']
    p['placements'][1]['rotation']=0
    with pytest.raises(ValueError,match='未朝向'):review_layout(site,p)
    p['placements'][1]['rotation']=180;p['use_zones']=p['use_zones'][:1]
    assert any('另需' in s for s in review_layout(site,p)[1]['errors'])


def test_followup_agent_request_keeps_parent_objects_and_routes(setup):
    service,agents,plan,request=setup
    parent=service.start('LAYOUT',plan['id'],request)
    agents.tasks[parent['id']].update(status='passed',candidate=proposal())
    follow=request.model_copy(update=dict(parent_id=parent['id'],operation_id='next-preserved-task'))
    run=service.start('LAYOUT',plan['id'],follow)
    assert run['site']['repair_from']==proposal()
    bad=proposal();bad['placements'][0]['size']=[.3,.3]
    with pytest.raises(ValueError,match='縮小'):review_layout(run['site'],bad)
    bad=proposal();bad['routes'][0]['name']='Remove the original route by renaming'
    with pytest.raises(ValueError,match='生活動線'):review_layout(run['site'],bad)


def test_floor_inference_does_not_remove_walls_or_approve_unconfirmed_routes(setup):
    from shapely.geometry import Polygon
    _,_,plan,request=setup;site=site_packet(plan,request)
    floor=next(a for a in site['items'] if a['role']=='floor')
    floor['points']=[[0,0],[2.95,0],[2.95,6],[0,6]]
    other=copy.deepcopy(floor);other.update(id='floor-b',points=[[3.05,0],[6,0],[6,6],[3.05,6]])
    site['items'].append(other);site['floor_gap_tolerance']=.22
    p=proposal();p['placements'][0]['center']=[4,2]
    p['use_zones'][0]['points']=[[3.4,1],[4.6,1],[4.6,1.65],[3.4,1.65]]
    p['routes'][0]['points']=[[1,3],[5,3]]
    original=copy.deepcopy(site)
    _,r=review_layout(site,p)
    assert site==original and r['floor_patches']
    assert r['routes'][0]['inferred_floor'] and not r['routes'][0]['blocked']
    assert r['status']=='blocked'  # inference never becomes final approval
    wall=copy.deepcopy(next(a for a in site['items'] if a['role']=='wall'))
    wall.update(id='divider',points=[[3,0],[3,6]],closed=False,thickness=.18)
    site['items'].append(wall)
    _,r=review_layout(site,p)
    assert r['routes'][0]['blocked'] and 'divider' in r['routes'][0]['wall_obstacles']
    for patch in r['floor_patches']:
        assert Polygon(patch['points'],patch['holes']).is_valid
    site['items'].remove(wall);p['placements'][0]['center']=[3,2]
    assert any('家具超出' in e for e in review_layout(site,p)[1]['errors'])
    site['excluded_floor_ids']=['floor-b']
    assert review_layout(site,p)[1]['routes'][0]['outside_floor']


def test_source_answers_preserve_geometry_validate_endpoints_and_reject_stale_writes(setup):
    service,agents,plan,request=setup
    parent=service.start('LAYOUT',plan['id'],request)
    agents.tasks[parent['id']].update(status='passed',candidate=proposal())
    note=dict(question_id='Q1',title='Door endpoints',known='90 cm confirmed',ask='Mark the endpoints',regions=[dict(label='Door',box=[10,10,200,200])],answer='')
    packet=copy.deepcopy(plan);packet['parsed']['image']=dict(width=800,height=800)
    with patch.object(service.plans,'current',return_value=packet):
        body=ReviseLayout(base_revision=plan['revision'],operation_id='annotated-repair',candidate=proposal(),rationale='Preserve the original dimensions and ask only for endpoints.',sources=[dict(label='Synthetic',reference='fixture',sha256='a'*64)],source_questions=[note])
        run=service.revise('LAYOUT',plan['id'],parent['id'],body)
        payload=LayoutAnswers(base_revision=plan['revision'],answers={'Q1':'A to B is the door opening'},source_marks=[dict(id='m1',start=[20,30],end=[80,30],description='Door jambs',question_id='Q1')])
        saved=service.save_answers('LAYOUT',plan['id'],run['id'],payload)
        assert service.answers('LAYOUT',plan['id'],run['id'])==saved
        assert saved['source']==plan['source'] and run['adoption'] is None
        assert packet['settings']==plan['settings'] and agents.calls==1
        with pytest.raises(Conflict,match='其他視窗'):service.save_answers('LAYOUT',plan['id'],run['id'],payload)
        payload.base_answer_id=saved['id']
        for endpoint in ((801,0),(float('nan'),20),(20,30)):
            bad=payload.model_copy(deep=True);bad.source_marks[0].end=endpoint
            with pytest.raises(ValueError):service.save_answers('LAYOUT',plan['id'],run['id'],bad)
        bad=payload.model_copy(deep=True);bad.answers={'Q9':'Different question'}
        with pytest.raises(ValueError,match='本版'):service.save_answers('LAYOUT',plan['id'],run['id'],bad)
        payload.answers['Q1']='Updated evidence'
        newer=service.save_answers('LAYOUT',plan['id'],run['id'],payload)
        assert (service.root('LAYOUT',plan['id'])/'runs'/run['id']/'answers'/(saved['id']+'.json')).exists()
        follow=request.model_copy(update=dict(parent_id=run['id'],operation_id='followup-with-answers'))
        # site_packet expects the synthetic CAD plan; only the source-question storage needs an image here.
    with patch.object(service.plans,'current',return_value=plan):
        continued=service.start('LAYOUT',plan['id'],follow)
        assert continued['site']['layout_source_answers']['id']==newer['id']
        assert continued['site']['layout_source_questions'][0]['question_id']=='Q1'
    assert service.plans.current('LAYOUT',plan['id'])['revision']==plan['revision']
    service.plans.save('LAYOUT',plan['id'],SavePlan(base_revision=plan['revision'],settings=plan['settings']))
    with pytest.raises(Conflict,match='平面已更新'):service.save_answers('LAYOUT',plan['id'],run['id'],payload)
    bad=copy.deepcopy(note);bad['regions'][0]['box']=[0,0,801,800]
    with pytest.raises(ValueError,match='超出'):validate_source_questions([bad],dict(width=800,height=800))


def test_valid_candidate_has_exact_corridor_and_no_model_side_effect(setup):
    service,agents,plan,request=setup;site=site_packet(plan,request)
    original=copy.deepcopy(plan);p,r=review_layout(site,proposal())
    assert r['status']=='ready' and r['routes'][0]['length']==3.5
    assert plan==original and agents.calls==0


@pytest.mark.parametrize('fault',['wall','furniture','outside','route','width','use_zone','missing_zone'])
def test_geometry_failures_are_not_model_approved(setup,fault):
    _,_,plan,request=setup;p=proposal()
    if fault=='wall':p['placements'][0]['center']=[3,.2]
    if fault=='furniture':p['placements'][0]['center']=[4.5,4.5]
    if fault=='outside':p['placements'][0]['center']=[7,4]
    if fault=='route':p['routes'][0]['points']=[[3,1],[3,5]]
    if fault=='width':p['routes'][0]['width']=.6
    if fault=='use_zone':p['use_zones'][0]['points']=[[4,4],[5,4],[5,5],[4,5]]
    if fault=='missing_zone':p['use_zones']=[]
    assert review_layout(site_packet(plan,request),p)[1]['status']=='blocked'


def test_fixed_baseline_and_requirement_coverage(setup):
    _,_,plan,request=setup;site=site_packet(plan,request);p=proposal()
    p['placements'][0]['target_id']=next(a['id'] for a in site['items'] if a['role']=='wall')
    with pytest.raises(ValueError,match='未授權'):review_layout(site,p)
    p=proposal();p['coverage'][0]['requirement_id']='R99'
    with pytest.raises(ValueError,match='每項'):review_layout(site,p)


def test_collision_feedback_contains_measured_bounds_not_only_model_claims(setup):
    _,_,plan,request=setup;p=proposal();p['placements'][0]['center']=[4.5,4.5]
    _,report=review_layout(site_packet(plan,request),p)
    collision=next(d for d in report['diagnostics'] if d['object']=='desk1' and not d['other'].startswith('desk'))
    assert collision['overlap_area_m2']>0
    assert collision['object_bounds']==pytest.approx([3.9,4.2,5.1,4.8])


def test_existing_furniture_cannot_be_shrunk(setup):
    _,_,plan,request=setup;fid=next(a['id'] for a in plan['settings']['assignments'] if a['role']=='furniture')
    request.movable_ids=[fid];site=site_packet(plan,request);p=proposal();p['placements'][0]['target_id']=fid
    with pytest.raises(ValueError,match='不可縮放'):review_layout(site,p)


def test_request_dedup_adoption_and_replay_preserve_source(setup):
    service,agents,plan,request=setup
    run=service.start('LAYOUT',plan['id'],request);again=service.start('LAYOUT',plan['id'],request)
    assert run['id']==again['id'] and agents.calls==1
    agents.tasks[run['id']].update(status='passed',candidate=proposal())
    saved=service.adopt('LAYOUT',plan['id'],run['id'],AdoptLayout(base_revision=plan['revision'],accept_assumptions=True))
    assert saved['check']['status']=='ready'
    assert saved['parsed']==plan['parsed'] and saved['source']==plan['source']
    assert saved['settings']['assignments'][:-1]==[Assignment.model_validate(a).model_dump(mode='json') for a in plan['settings']['assignments']]
    assert saved['settings']['assignments'][-1]['design_asset']=='desk'
    repeated=service.adopt('LAYOUT',plan['id'],run['id'],AdoptLayout(base_revision=plan['revision'],accept_assumptions=True))
    assert repeated['revision']==saved['revision']
    assert len(saved['settings']['additions'])==1


def test_stale_candidate_cannot_overwrite_edits(setup):
    service,agents,plan,request=setup;run=service.start('LAYOUT',plan['id'],request)
    agents.tasks[run['id']].update(status='passed',candidate=proposal())
    saved=service.plans.save('LAYOUT',plan['id'],SavePlan(base_revision=plan['revision'],settings=plan['settings']))
    with pytest.raises(Conflict,match='舊版'):service.adopt('LAYOUT',plan['id'],run['id'],AdoptLayout(base_revision=saved['revision'],accept_assumptions=True))


def test_bad_proposal_never_changes_plan(setup):
    service,agents,plan,request=setup;run=service.start('LAYOUT',plan['id'],request);p=proposal();p['placements'][0]['center']=[7,7]
    agents.tasks[run['id']].update(status='passed',candidate=p)
    with pytest.raises(ValueError,match='幾何衝突'):service.adopt('LAYOUT',plan['id'],run['id'],AdoptLayout(base_revision=plan['revision'],accept_assumptions=True))
    assert service.plans.current('LAYOUT',plan['id'])['revision']==plan['revision']


def test_existing_requirement_packet_is_version_bound_and_sent_without_mutating_plan(setup):
    service,agents,plan,request=setup
    brief=service.save_brief('LAYOUT',plan['id'],LayoutBrief(base_revision=plan['revision'],brief=request.brief,requirements=request.requirements,
        context='Owner confirmed the sink; do not ask again.',sources=[dict(label='Owner notes',reference='sources/notes.md',sha256='a'*64)]))
    assert service.brief('LAYOUT',plan['id'])['id']==brief['id']
    request.brief_id=brief['id'];run=service.start('LAYOUT',plan['id'],request)
    assert run['site']['supplied_context']['sources'][0]['sha256']=='a'*64
    assert service.plans.current('LAYOUT',plan['id'])['revision']==plan['revision']
    saved=service.plans.save('LAYOUT',plan['id'],SavePlan(base_revision=plan['revision'],settings=plan['settings']))
    request.base_revision=saved['revision'];request.operation_id='request-after-plan-edit'
    with pytest.raises(Conflict,match='需求包'):service.start('LAYOUT',plan['id'],request)


def test_agent_repairs_using_program_report(setup,tmp_path):
    _,_,plan,request=setup;bad=proposal();bad['routes'][0]['width']=.6
    class Client:
        def __init__(self):self.prompts=[]
        def run(self,prompt,**kwargs):
            self.prompts.append(prompt)
            return dict(text=json.dumps(bad if len(self.prompts)==1 else proposal()))
    client=Client();result=run_layout(client,tmp_path,dict(site=site_packet(plan,request)),'fake',lambda phase:None,lambda event:None)
    assert result['layout_report']['status']=='ready' and len(result['passes'])==2
    assert '低於使用者目標' in client.prompts[1]


def test_agent_repair_is_bounded_and_retains_failures(setup,tmp_path):
    _,_,plan,request=setup;p=proposal();p['use_zones']=[]
    class Client:
        def run(self,*args,**kwargs):return dict(text=json.dumps(p))
    result=run_layout(Client(),tmp_path,dict(site=site_packet(plan,request)),'fake',lambda phase:None,lambda event:None)
    assert len(result['passes'])==3 and result['layout_report']['status']=='blocked'


def test_invalid_final_repair_preserves_previous_preview_and_failed_task_state(setup,tmp_path):
    service,agents,plan,request=setup;p=proposal();p['use_zones']=[]
    class Client:
        calls=0
        def run(self,*args,**kwargs):
            self.calls+=1
            return dict(text=json.dumps(p) if self.calls<3 else '{"invalid":true}')
    result=run_layout(Client(),tmp_path,dict(site=site_packet(plan,request)),'fake',lambda phase:None,lambda event:None)
    assert result['candidate']==dict(p,question_targets=[]) and result['preview_pass']==2
    assert result['layout_report']['status']=='blocked'
    assert result['passes'][-1]['error'] and result['recovery_note']
    run=service.start('LAYOUT',plan['id'],request)
    agents.root=tmp_path/'tasks'
    folder=agents.root/run['id'];folder.mkdir(parents=True)
    (folder/'layout-passes.json').write_text(json.dumps(result['passes']),encoding='utf-8')
    agents.tasks[run['id']].update(status='failed',error='Invalid final repair')
    recovered=service.get('LAYOUT',plan['id'],run['id'])
    assert recovered['task']['status']=='failed' and recovered['task']['candidate']==dict(p,question_targets=[])
    with pytest.raises(Conflict,match='尚未完成'):service.adopt('LAYOUT',plan['id'],run['id'],AdoptLayout(base_revision=plan['revision'],accept_assumptions=True))
    assert service.plans.current('LAYOUT',plan['id'])['revision']==plan['revision']


def test_image_layout_http_adoption_preserves_pixel_origin_and_reopens(tmp_path):
    import io
    from PIL import Image
    from fastapi.testclient import TestClient
    from interior.workbench.server import create_app
    from interior.workbench.storage import write_json
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='IMAGE',name='Synthetic image layout'))
    data=io.BytesIO();Image.new('RGB',(800,800),'white').save(data,format='PNG')
    image_proposal=dict(features=[
        dict(id='floor',name='Floor',role='floor',points=[[100,100],[700,100],[700,700],[100,700]],closed=True,confidence='high',evidence='synthetic',host_id=None),
        dict(id='wall',name='Wall',role='wall',points=[[100,100],[700,100]],closed=False,confidence='high',evidence='synthetic',host_id=None)],
        scale=dict(start=[100,100],end=[700,100],metres=6,evidence='synthetic dimension'),uncertainties=['height'])
    def fake_start(self,kind,model,payload,identifier):
        candidate=image_proposal if kind=='plan_image' else proposal()
        result=dict(id=identifier,status='passed',kind=kind,model=model,candidate=candidate)
        write_json(self.root/identifier/'task.json',result);return result
    with patch.object(Jobs,'loop',return_value=None),patch('interior.workbench.agent_runtime.service.AgentTasks.start',fake_start):
        with TestClient(create_app(tmp_path),base_url='http://127.0.0.1') as c:
            h={'x-workbench-token':c.get('/api/session').json()['token']};url='/api/studio/projects/IMAGE'
            record=c.post(url+'/image-plans/upload',files={'file':('synthetic.png',data.getvalue())},headers=h).json()
            route=url+'/image-plans/'+record['id']
            c.post(route+'/recognize',json={'model':'test-image'},headers=h).raise_for_status()
            plan=c.post(route+'/draft',headers=h).json();settings=copy.deepcopy(plan['settings'])
            settings['calibration']['confirmed']=True;settings['reviewed']=[q['id'] for q in plan['parsed']['questions']]
            question=plan['parsed']['questions'][0]
            settings['question_notes']=[dict(question_id=question['id'],title='Unknown fixture',known='',ask='What is it?',regions=[dict(label='Fixture',box=[100,100,200,200])],answer='This is a refrigerator.')]
            plan_route=url+'/plans/'+plan['id']
            plan=c.put(plan_route,json=dict(base_revision=plan['revision'],settings=settings),headers=h).json()
            payload=dict(base_revision=plan['revision'],model='fake',operation_id='image-layout-1',brief='A single adult needs a working desk.',requirements=['Add a desk'])
            run=c.post(plan_route+'/layout',json=payload,headers=h).json()
            assert run['site']['confirmed_answers']==[dict(title='Unknown fixture',answer='This is a refrigerator.',accepted_for_concept=True)]
            assert c.post(plan_route+'/layout/'+run['id']+'/adopt',json=dict(base_revision=plan['revision'],accept_assumptions=False),headers=h).status_code==422
            response=c.post(plan_route+'/layout/'+run['id']+'/adopt',json=dict(base_revision=plan['revision'],accept_assumptions=True),headers=h)
            assert response.status_code==200,response.text
            saved=response.json();item=saved['check']['items'][-1]
            assert item['points'][0]==pytest.approx([2.4,3.7])
            assert item['points'][2]==pytest.approx([3.6,4.3])
            assert saved['settings']['additions'][0]['points'][0]==pytest.approx([340,330])
            assert saved['parsed']==plan['parsed'] and saved['source']==plan['source']
        with TestClient(create_app(tmp_path),base_url='http://127.0.0.1') as c:
            assert c.get(plan_route+'/layout/current').json()['adoption']['revision']==saved['revision']
            assert c.get(url+'/image-plans/current').json()['plan']['revision']==saved['revision']
