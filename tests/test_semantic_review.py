"""Source evidence, partial floor correction and answers on unrelated geometry."""
import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from shapely.geometry import Polygon

from test_plan_semantics import system,candidate
from interior.workbench.storage import Conflict
from interior.workbench.studio.plan_semantics import PlanSemantics,SemanticRequest,SaveSemanticAnswers,AdoptSemantics,site_packet,draw_site,validate
from interior.workbench.studio.semantic_evidence import floor_proof,questions_on_source,write_question_overlay


def concave_case():
    outline=[[0,0],[8,0],[8,6],[6,6],[6,4],[0,4]]
    geometry=[];walls=[]
    for i,a in enumerate(outline):
        b=outline[(i+1)%len(outline)]
        geometry.append(dict(id='source-'+str(i),points=[a,b],closed=False,kind='LINE',layer='architecture'))
        walls.append(dict(id='wall-'+str(i),name='wall-'+str(i),role='wall',room_id='living',points=[a,b],closed=False,thickness=.15,height=2.8,base=0,source_ids=[geometry[-1]['id']],evidence='Exact source edge'))
    site=dict(floors=[dict(id='old',points=[[0,0],[6,0],[6,4],[0,4]])],floor_locked=False,geometry=geometry,texts=[dict(id='room-label',point=[3,2],text='Living')],dimensions=[])
    raw=dict(summary='Corrected source footprint',rooms=[dict(id='living',name='Living',points=outline,source_ids=['room-label'],evidence='Source room label')],elements=walls,door_state='absent',window_state='absent',furniture_state='absent',inventory_evidence='No furniture shown',questions=[],floor_outline=dict(points=outline,holes=[],source_ids=[g['id'] for g in geometry],evidence='Follow each exact source edge'))
    return site,raw


def test_provisional_concave_floor_corrects_without_convex_hull_or_dimension_changes():
    site,raw=concave_case();before=copy.deepcopy(site)
    proposal,report=validate(site,raw)
    assert report['status']=='preview',report
    assert report['floor_outline']['area_m2']==36 and report['floor_outline']['previous_area_m2']==24
    assert Polygon(proposal['floor_outline']['points']).area!=Polygon(proposal['floor_outline']['points']).convex_hull.area
    assert site==before
    site['floor_locked']=True
    assert any('已確認' in e for e in validate(site,raw)[1]['errors'])


def test_arbitrary_large_frame_and_unsupported_floor_cannot_pass():
    site,raw=concave_case();raw['floor_outline']['points']=[[0,0],[12,0],[12,10],[0,10]]
    assert floor_proof(site,raw)[1]
    raw['floor_outline']['source_ids']=['invented']
    with pytest.raises(ValueError,match='來源'):floor_proof(site,raw)


def test_missed_floor_citation_is_completed_only_from_coincident_native_lines():
    site,raw=concave_case();removed=raw['floor_outline']['source_ids'].pop()
    shape,errors,report=floor_proof(site,raw)
    assert not errors and removed in report['added_source_ids'] and shape.area==36
    # Nearby but different geometry cannot prove a nonexistent perimeter.
    site['geometry'][-1]['points']=[[20,0],[20,4]]
    raw['floor_outline']['source_ids'].remove(removed)
    assert floor_proof(site,raw)[1]


def test_nonwall_thickness_does_not_invalidate_furniture_or_resize_it(system):
    _,_,_,site=system;raw=candidate(site);raw['elements'][-1]['thickness']=.03
    before=copy.deepcopy(raw['elements'][-1]['points'])
    normalized,report=validate(site,raw)
    assert report['status']=='preview' and normalized['elements'][-1]['points']==before
    raw['elements'][0]['thickness']=.03
    assert any('4 cm' in s for s in validate(site,raw)[1]['errors'])


def test_room_access_detects_sealed_room_without_treating_a_window_as_a_door():
    from interior.workbench.studio.semantic_evidence import room_access
    floor=Polygon([[0,0],[8,0],[8,6],[0,6]])
    raw=dict(rooms=[dict(id='main',name='Main',points=[[0,0],[6,0],[6,6],[0,6]],source_ids=['label-main']),dict(id='small',name='Small room',points=[[6,0],[8,0],[8,6],[6,6]],source_ids=['label-small'])],elements=[dict(id='divider',role='wall',points=[[6,0],[6,6]],closed=False,thickness=.15)])
    before=copy.deepcopy(raw);findings=room_access(raw,floor)
    assert [r['room_id'] for r in findings]==['small'] and raw==before
    raw['elements'].append(dict(id='opening',role='window',host_id='divider',points=[[6,2],[6,3]],base=0))
    assert room_access(raw,floor)
    raw['elements'][-1]['role']='door'
    assert room_access(raw,floor)==[]


def test_invalid_raw_coordinates_are_supplied_to_the_bounded_retry(system,tmp_path):
    from interior.workbench.studio.plan_semantics import run_semantics
    _,_,_,site=system;raw=candidate(site)
    bad=copy.deepcopy(raw);bad['floor_outline']=dict(points=[[0,0],[8,6],[8,0],[0,6]],holes=[],source_ids=[site['geometry'][1]['id']],evidence='Malformed ring for regression')
    class Client:
        calls=0
        def run(self,instruction,**kwargs):
            self.calls+=1
            if self.calls==2:assert 'raw_candidate' in instruction and 'Self-intersection' in instruction
            return dict(text=json.dumps(bad if self.calls==1 else raw))
    client=Client();result=run_semantics(client,tmp_path,dict(site=site,image='unused.png'),'test',lambda s:None,lambda e:None)
    assert result['semantic_report']['status']=='preview' and client.calls==2
    assert (tmp_path/'raw-pass-1.json').exists()


def test_located_human_question_waits_instead_of_pressuring_agent_to_invent(system,tmp_path):
    from interior.workbench.studio.plan_semantics import run_semantics
    _,_,_,site=system;raw=candidate(site);wall=next(g for g in site['geometry'] if g['kind']=='LINE')
    raw['questions']=[dict(id='kind',title='Window kind',ask='Fixed or sliding window?',reason='No elevation',source_ids=[wall['id']],box=[4,-.1,5,.2])]
    class Client:
        calls=0
        def run(self,*args,**kwargs):self.calls+=1;return dict(text=json.dumps(raw))
    client=Client();result=run_semantics(client,tmp_path,dict(site=site,image='unused.png'),'test',lambda x:None,lambda x:None)
    assert client.calls==1 and result['semantic_report']['requires_confirmation']
    assert result['semantic_report']['status']=='blocked'


def test_question_registration_uses_native_segments_not_just_endpoints(tmp_path):
    site,raw=concave_case();raw['questions']=[dict(id='opening',title='Opening type',ask='Is this a window or a door?',reason='No swing symbol',source_ids=['source-0'],box=[3,-.1,4,.2])]
    q=questions_on_source(site,raw)
    assert q[0]['label']=='Q1' and q[0]['box']==[3,-.1,4,.2]
    image=tmp_path/'source.png';Image.new('RGB',(1000,800),'white').save(image);before=image.read_bytes()
    write_question_overlay(image,dict(width=1000,height=800,bounds=[-1,-1,9,7],scale=90,pad=40),q,tmp_path)
    assert 'Q1' in (tmp_path/'questions.svg').read_text() and image.read_bytes()==before
    assert json.loads((tmp_path/'questions.json').read_text())['questions'][0]['source_ids']==['source-0']
    raw['questions'][0]['box']=[20,20,21,21]
    with pytest.raises(ValueError,match='不相交'):questions_on_source(site,raw)


def test_full_source_curve_and_external_note_are_not_clipped_by_inferred_floor(system,tmp_path):
    studio,_,packet,_=system
    packet=copy.deepcopy(packet)
    import ezdxf
    path=studio.root('UNRELATED')/packet['source']['path']
    doc=ezdxf.readfile(path);curve=doc.modelspace().add_arc((9.5,2),.6,0,180,dxfattribs={'layer':'architecture'});doc.saveas(path)
    site=site_packet(dict(packet,_root=str(studio.root('UNRELATED'))))
    assert len(next(g for g in site['geometry'] if g['id']=='e-'+curve.dxf.handle)['points'])>15
    view=draw_site(packet,site,tmp_path/'full.png')
    assert view['bounds'][2]>9.7


def test_answers_survive_reopen_and_are_reused_without_reasking(system):
    studio,plans,packet,_=system
    class Agents:
        def start(self,kind,model,payload,identifier):
            self.payload=payload;self.result=dict(status='passed',candidate=candidate(payload['site']))
            self.result['candidate']['questions']=[dict(id='window-kind',title='Window kind',ask='Sliding or fixed?',reason='Elevation not provided',source_ids=[payload['site']['geometry'][1]['id']],box=None)]
        def get(self,identifier):return self.result
    agents=Agents();service=PlanSemantics(studio,agents)
    def start():return service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex,mode='review'))
    run=start()
    saved=service.save_answers('UNRELATED',packet['id'],run['id'],SaveSemanticAnswers(base_revision=packet['revision'],answers={'window-kind':'Confirmed fixed window'}))
    assert service.get('UNRELATED',packet['id'],run['id'])['answers']==saved['answers']
    with pytest.raises(Conflict):service.save_answers('UNRELATED',packet['id'],run['id'],SaveSemanticAnswers(base_revision=packet['revision'],answers={}))
    with pytest.raises(ValueError,match='不存在'):service.save_answers('UNRELATED',packet['id'],run['id'],SaveSemanticAnswers(base_revision=packet['revision'],answers_revision=saved['answers']['revision'],answers={'unknown':'answer'}))
    fresh=start()
    assert fresh['site']['confirmed_answers'][0]['answer']=='Confirmed fixed window'
    assert fresh['site']['previous_review']['task_id']==run['id']
    assert agents.payload['source_images'], 'The same button must supply source crops on follow-up'
    assert plans.current('UNRELATED',packet['id'])['revision']==packet['revision']
