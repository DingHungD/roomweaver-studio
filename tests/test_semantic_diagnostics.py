"""Synthetic dependency, lineage and atomicity cases; no client data or model calls."""
import copy
import pytest
from shapely.geometry import Polygon

from test_semantic_review import concave_case
from test_plan_semantics import system,candidate
from interior.workbench.studio.plan_semantics import validate
from interior.workbench.studio.semantic_evidence import floor_proof
from interior.workbench.studio.semantic_diagnostics import (
    attach,attach_links,object_links,regressions,opening_groups,select_batch,check_atomic_openings,repair_candidates)


def test_inferred_boundary_requires_evidence_and_does_not_move_objects():
    site,raw=concave_case();site['native_dwg']={'schema':'test'}
    raw.pop('floor_outline');original=copy.deepcopy((site,raw))
    floor,errors,proof=floor_proof(site,raw)
    assert errors and not proof['evidence_sufficient'] and floor.area==24
    assert (site,raw)==original


def test_boundary_holes_are_preserved_and_confirmation_is_separate():
    site,raw=concave_case()
    site['floors']=[dict(points=[[0,0],[8,0],[8,6],[0,6]],holes=[[[2,2],[3,2],[3,3],[2,3]]])]
    site['floor_locked']=True;raw.pop('floor_outline')
    shape,errors,_=floor_proof(site,raw)
    assert shape.area==47 and len(shape.interiors)==1 and not errors


def test_confirmed_native_floor_keeps_confirmation_but_does_not_invent_geometric_proof():
    site,raw=concave_case();site['native_dwg']={'schema':'test'};site['floor_locked']=True
    raw.pop('floor_outline');original=copy.deepcopy(site)
    floor,errors,proof=floor_proof(site,raw)
    assert errors and proof['user_confirmed'] and not proof['evidence_sufficient']
    assert floor.area==24 and site==original


def test_furniture_failure_does_not_skip_access(system):
    _,_,_,site=system;raw=candidate(site);raw['elements'][-1]['closed']=False
    _,report=validate(site,raw)
    assert report['access_checked'] and report['errors']
    assert next(c for c in report['diagnostics']['checks'] if c['id']=='access')['status']=='passed'


def test_host_failure_defers_access_and_blocks_adoption(system):
    _,_,_,site=system;raw=candidate(site);raw['elements'][1]['host_id']='unknown'
    _,report=validate(site,raw)
    assert not report['access_checked'] and report['status']=='blocked'
    assert next(c for c in report['diagnostics']['checks'] if c['id']=='access')['status']=='deferred'


def test_duplicate_opening_blocks_even_when_names_and_hosts_validate(system):
    _,_,_,site=system;raw=candidate(site)
    opening=next(e for e in raw['elements'] if e['role']=='door')
    other=copy.deepcopy(opening);other['id']='duplicate';other['name']='Another aperture'
    raw['elements'].append(other)
    _,report=validate(site,raw)
    assert report['status']=='blocked' and not report['access_checked']
    issue=next(i for i in report['diagnostics']['issues'] if i['code']=='overlap')
    assert set(issue['object_ids'])=={opening['id'],'duplicate'}
    other['name']='Changed name';_,again=validate(site,raw)
    assert next(i['id'] for i in again['diagnostics']['issues'] if i['code']=='overlap')==issue['id']


def test_stable_identity_survives_renaming_but_new_failure_is_not_hidden(system):
    _,_,_,site=system;raw=candidate(site);raw['elements'][1]['host_id']='unknown'
    _,before=validate(site,raw)
    raw['elements'][1]['name']='Renamed opening';_,after=validate(site,raw)
    assert not regressions(before,after)
    raw['elements'][-1]['closed']=False;_,after=validate(site,raw)
    assert any('封閉' in m for m in regressions(before,after))


def test_newly_executable_access_failure_is_retained_not_a_regression():
    site={};raw=dict(elements=[],rooms=[])
    before=attach(site,raw,dict(errors=['宿主不符'],repair_errors=['宿主不符'],access_checked=False))
    after=attach(site,raw,dict(errors=['Room 疑似沒有可連通的入口'],repair_errors=['Room 疑似沒有可連通的入口'],access_checked=True))
    assert not regressions(before,after) and after['newly_discovered'] and after['status']=='blocked'


def test_atomic_assembly_keeps_unrelated_window_outside():
    raw=dict(elements=[dict(id='wall',role='wall'),dict(id='door',role='door',host_id='wall'),
                       dict(id='window',role='window',host_id='other'),dict(id='other',role='wall')])
    assert sorted(opening_groups(raw))==[['door','wall'],['other','window']]
    changed=copy.deepcopy(raw);changed['elements'][0]['name']='changed'
    with pytest.raises(ValueError,match='整組'):
        check_atomic_openings(raw,changed,dict(diagnostics=dict(issues=[dict(message='bad jamb',object_ids=['door'],check='openings')])))
    assert 'name' not in raw['elements'][0]


def test_batch_limit_never_splits_assembly():
    raw=dict(elements=[dict(id='wall',role='wall'),dict(id='window',role='window',host_id='wall')])
    pending=[dict(id=str(i),atomic_ids=['wall'],repair_priority=1) for i in range(25)]
    chosen,skipped=select_batch(pending,raw)
    assert not chosen and len(skipped)==25
    chosen,_=select_batch(pending[:2]+[dict(id='other',repair_priority=2)],raw)
    assert len(chosen)==2


def test_jamb_joins_only_with_source_evidence_and_actual_adjacency():
    opening=dict(id='window',role='window',host_id='host',points=[[0,0],[2,0]],source_ids=['frame'])
    jamb=dict(id='jamb',role='wall',points=[[0,0],[0,.2]],thickness=.1,source_ids=['frame'])
    remote=dict(jamb,id='remote',points=[[8,0],[8,.2]])
    neighbour=dict(jamb,id='neighbour',source_ids=['unrelated'])
    groups=opening_groups(dict(elements=[opening,jamb,remote,neighbour,dict(id='host',role='wall')]))
    assert groups==[['host','jamb','window']]


def test_collinear_opening_repair_bounds_are_finite():
    import json
    raw=dict(elements=[dict(id='w',name='wall',role='wall',points=[[0,0],[0,5]],source_ids=['s']),
                       dict(id='d',name='door',role='door',host_id='w',points=[[0,1],[0,2]],source_ids=['s'])])
    report=attach({},raw,dict(errors=['door 洞口未對齊原生宿主牆帶'],repair_errors=['door 洞口未對齊原生宿主牆帶']))
    groups=repair_candidates({},raw,report)
    assert groups and Polygon.from_bounds(*groups[0]['box']).area>0
    json.dumps(groups,allow_nan=False)


def test_boundary_is_one_repair_root_with_real_sources():
    site,raw=concave_case();raw.pop('floor_outline')
    report=dict(errors=['Living 超出已提供的地板／外牆範圍'],repair_errors=['Living 超出已提供的地板／外牆範圍'],
                access_checked=False,floor_outline=dict(status='blocked',evidence_sufficient=False))
    attach(site,raw,report);repairs=repair_candidates(site,raw,report)
    boundary=[r for r in repairs if r['repair_priority']==0]
    assert len(boundary)==1 and boundary[0]['source_ids']


def test_lineage_requires_shape_and_class_not_just_shared_source():
    site=dict(geometry=[])
    obj=dict(id='recognition:a',category='sofa',points=[[0,0],[2,0],[2,1],[0,1]],closed=True,source_ids=['s'],status='interpreted')
    target=dict(obj,id='sofa',role='furniture')
    audit=dict(layers=dict(items=[obj]))
    raw=dict(elements=[target]);links=object_links(site,raw,audit)
    assert links['pending']==0 and links['items'][0]['targets'][0]['id']=='sofa'
    target['points']=[[10,10],[12,10],[12,11],[10,11]]
    assert object_links(site,raw,audit)['pending']==2  # Both disconnected representations remain visible.
    target['points']=obj['points'];target['category']='chair'
    assert object_links(site,raw,audit)['pending']==1
    assert audit['layers']['items'][0]==obj


def test_beam_maps_to_drawing_and_keeps_model_requirements():
    geometry=dict(id='s',points=[[0,0],[2,0],[2,1],[0,1]],closed=True,kind='LWPOLYLINE')
    site=dict(geometry=[geometry])
    obj=dict(id='recognition:beam',category='beam',points=geometry['points'],closed=True,source_ids=['s'],status='interpreted')
    raw=dict(drawing_objects=[dict(id='beam',category='beam',source_ids=['s'])])
    links=object_links(site,raw,dict(layers=dict(items=[obj])))
    assert not links['pending'] and links['items'][0]['modeling_requirements']
    raw=dict(elements=[dict(id='wall',role='wall',points=[[0,.5],[2,.5]],thickness=1,source_ids=['s'])])
    assert object_links(site,raw,dict(layers=dict(items=[obj])))['pending']==1


def test_split_lineage_requires_combined_coverage():
    site=dict(geometry=[])
    obj=dict(id='recognition:a',category='sofa',points=[[0,0],[2,0],[2,1],[0,1]],closed=True,source_ids=['s'],status='interpreted')
    parts=[dict(id=str(i),role='furniture',category='sofa',points=[[i,0],[i+1,0],[i+1,1],[i,1]],closed=True,source_ids=['s']) for i in range(2)]
    links=object_links(site,dict(elements=parts),dict(layers=dict(items=[obj])))
    assert links['items'][0]['relation']=='split' and not links['pending']
    assert object_links(site,dict(elements=parts[:1]),dict(layers=dict(items=[obj])))['pending']==1


def test_merged_lineage_checks_both_sides_and_rejects_duplicates():
    objects=[dict(id='recognition:'+str(i),category='sofa',points=[[i,0],[i+1,0],[i+1,1],[i,1]],closed=True,source_ids=['s'],status='interpreted') for i in range(2)]
    target=dict(id='merged',role='furniture',category='sofa',points=[[0,0],[2,0],[2,1],[0,1]],closed=True,source_ids=['s'])
    links=object_links(dict(geometry=[]),dict(elements=[target]),dict(layers=dict(items=objects)))
    assert not links['pending'] and all(r['relation']=='merged' for r in links['items'])
    duplicate=dict(target,id='duplicate')
    links=object_links(dict(geometry=[]),dict(elements=[target,duplicate]),dict(layers=dict(items=objects)))
    assert links['pending'] and any('重複' in r['reason'] for r in links['items'])


def test_short_line_cannot_cover_a_long_recognition_object():
    obj=dict(id='recognition:w',category='window',points=[[0,0],[4,0]],closed=False,source_ids=['s'],status='interpreted')
    target=dict(id='window',role='window',points=[[0,0],[1,0]],closed=False,source_ids=['s'])
    assert object_links(dict(geometry=[]),dict(elements=[target]),dict(layers=dict(items=[obj])))['pending']


def test_changed_purpose_stays_pending_on_both_representations():
    obj=dict(id='recognition:w',category='sofa',points=[[0,0],[1,0],[1,1],[0,1]],closed=True,source_ids=['s'],status='interpreted')
    target=dict(obj,id='chair',role='furniture',category='chair')
    links=object_links(dict(geometry=[]),dict(elements=[target]),dict(layers=dict(items=[obj])))
    assert links['pending'] and any(t['id']=='chair' for r in links['items'] for t in r['targets'])


def test_timeout_budget_is_shared_and_failed_inputs_are_not_requeued(system,tmp_path):
    from PIL import Image
    from interior.workbench.studio.cad_candidates import VERSION
    from interior.workbench.studio.semantic_local_review import run_local_reviews
    _,_,_,original=system;site=copy.deepcopy(original)
    site['coverage_version']=VERSION
    site['texts'] += [dict(id='note-'+str(i),text='冰箱待核 '+str(i),point=[5,3]) for i in range(100)]
    site['source_view']=dict(width=800,height=600,bounds=[0,0,8,6],scale=100,pad=0)
    image=tmp_path/'source.png';Image.new('RGB',(800,600),'white').save(image)
    raw,report=validate(site,candidate(site));before=copy.deepcopy((site,raw))
    class Client:
        calls=0
        def run(self,*args,**kwargs):
            self.calls+=1
            raise TimeoutError('synthetic timeout')
    client=Client()
    updated,checked,coverage,rounds=run_local_reviews(client,tmp_path,dict(site=site,image=str(image)),'test',raw,report,lambda _:None,lambda _:None,validate,max_rounds=99)
    assert client.calls==8 and len(rounds)==4 and all(len(r['candidate_ids'])==24 for r in rounds)
    identifiers=[i for r in rounds for i in r['candidate_ids']]
    assert len(set(identifiers))==96 and coverage['counts']['pending']==100
    assert not checked['questions'] and checked['status']=='blocked' and (site,updated)==before


def test_continuation_uses_existing_endpoint_with_revision_bound_baseline(system):
    from uuid import uuid4
    from interior.workbench.studio.plan_semantics import PlanSemantics,SemanticRequest
    from interior.workbench.storage import Conflict
    studio,plans,packet,_=system
    class Agents:
        def __init__(self):self.values={}
        def start(self,kind,model,payload,identifier):
            self.payload=payload
            self.values[identifier]=dict(status='passed',candidate=candidate(payload['site']))
        def get(self,identifier):return self.values[identifier]
    agents=Agents();service=PlanSemantics(studio,agents)
    first=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex,mode='review'))
    second=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],base_review_id=first['id'],use_object_recognition=False,model='test',operation_id=uuid4().hex,mode='review'))
    assert second['id']!=first['id'] and agents.payload['use_object_recognition'] is False
    assert plans.current('UNRELATED',packet['id'])['revision']==packet['revision']
    with pytest.raises(Conflict,match='基底'):
        service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],base_review_id=first['id'],use_object_recognition=False,model='test',operation_id=uuid4().hex,mode='review'))
