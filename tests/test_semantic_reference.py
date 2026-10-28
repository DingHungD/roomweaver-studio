"""Synthetic hash/version-bound model comparisons; no customer fixtures."""
import copy
import hashlib
import json
import pytest
from interior.workbench.studio.semantic_reference import inspect
from interior.workbench.studio.semantic_reference import resolve
from interior.workbench.studio.cad_candidates import source_hash
from interior.workbench.studio.plan_semantics import validate
from test_plan_semantics import system,candidate


def evidence(tmp_path,site,findings):
    source=tmp_path/'reference.skp';source.write_bytes(b'synthetic-reference')
    proof=dict(version=1,source_hash=source_hash(site),source_revision=site['reference_revision'],
        reference_sources=[dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest())],findings=findings)
    path=tmp_path/'comparison.json';path.write_text(json.dumps(proof),encoding='utf8')
    site['reference_evidence']=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return source,path


def test_beam_evidence_blocks_wall_but_not_other_source_bound_wall(system,tmp_path):
    _,_,_,site=system;site=copy.deepcopy(site);raw=candidate(site)
    wall=next(e for e in raw['elements'] if e['role']=='wall')
    wall['source_binding']=dict(method='pair',refs=[dict(id='beam-edge',edge=0)])
    evidence(tmp_path,site,[dict(type='prohibited_role',id='overhead-beam',source_ids=['beam-edge'],roles=['wall'],reason='上方梁不能作落地牆')])
    assert len(inspect(site,raw))==1
    wall['source_binding']['refs'][0]['id']='other-wall'
    assert not inspect(site,raw)


@pytest.mark.parametrize('change',['model','proof','drawing','revision'])
def test_reference_integrity_failure_blocks_instead_of_disappearing(system,tmp_path,change):
    _,_,_,site=system;site=copy.deepcopy(site);raw=candidate(site)
    source,path=evidence(tmp_path,site,[])
    if change=='model':source.write_bytes(b'changed')
    elif change=='proof':path.write_text('{}')
    elif change=='drawing':site['geometry'][0]['points'][0][0]+=.1
    else:site['reference_revision']='different'
    assert inspect(site,raw)[0]['check']=='source'
    _,report=validate(site,raw)
    assert report['status']=='blocked' and not report['access_checked']


def test_floor_reference_difference_survives_revalidation_without_changing_floor(system,tmp_path):
    _,_,_,site=system;site=copy.deepcopy(site);raw=candidate(site)
    evidence(tmp_path,site,[dict(type='unresolved',id='finish-vs-slab',source_ids=[],check='boundary',reason='飾面不能直接視為樓板外框')])
    before=copy.deepcopy(raw)
    proposal,report=validate(site,raw);again=validate(site,proposal)[1]
    assert proposal==validate({k:v for k,v in site.items() if k!='reference_evidence'},before)[0]
    assert report['reference_issues']==again['reference_issues'] and report['status']=='blocked'
    assert not report['diagnostics']['boundary']['evidence_sufficient']


def test_authoritative_measurements_are_explicit_and_atomic(system,tmp_path):
    _,_,_,site=system;site=copy.deepcopy(site);raw=validate(site,candidate(site))[0]
    wall=next(e for e in raw['elements'] if e['role']=='wall')
    site['reference_evidence']={'sha256':'a'*64}
    correction=dict(id=wall['id'],collection='elements',expected_binding=wall.get('source_binding'),values={'height':2.5},model_objects=['mesh-wall'],reason='measured model top')
    proof=dict(authority=dict(mode='user_designated_model',instruction='Use this model as the design reference'),corrections=[correction])
    before=copy.deepcopy(raw);records=resolve(site,raw,proof)
    assert records and next(e for e in raw['elements'] if e['id']==wall['id'])['height']==2.5
    assert all(e==before['elements'][i] for i,e in enumerate(raw['elements']) if e['id']!=wall['id'])
    raw=copy.deepcopy(before);proof['corrections'].append(dict(correction,id='missing'))
    with pytest.raises(ValueError):resolve(site,raw,proof)
    assert raw==before
    proof['corrections']=[correction];proof.pop('authority')
    with pytest.raises(ValueError,match='指定基準'):resolve(site,raw,proof)


def test_reference_cannot_overwrite_confirmed_floor_or_changed_binding(system,tmp_path):
    _,_,_,site=system;site=copy.deepcopy(site);raw=candidate(site);before=copy.deepcopy(raw)
    proof=dict(authority=dict(mode='user_designated_model',instruction='reference'),corrections=[dict(id='floor',collection='floor_outline',values={'points':[[0,0],[4,0],[4,4],[0,4]],'holes':[]},model_objects=['floor'],reason='measured')])
    site['floor_locked']=True
    with pytest.raises(ValueError,match='已確認'):resolve(site,raw,proof)
    assert raw==before
    wall=next(e for e in raw['elements'] if e['role']=='wall')
    proof['corrections']=[dict(id=wall['id'],collection='elements',expected_binding={'method':'pair','refs':[]},values={'height':2.5},model_objects=['mesh'],reason='measured')]
    with pytest.raises(ValueError,match='來源綁定'):resolve(site,raw,proof)
    assert raw==before


def test_beam_dimensions_require_reference_evidence(system):
    _,_,_,site=system;raw=candidate(site)
    raw['drawing_objects']=[dict(id='beam',model_dimensions={'base':2.1,'height':.3,'datum':'model_finish_floor'})]
    assert inspect(site,raw)[0]['check']=='source'


def test_verified_model_dimensions_and_host_height_survive_revalidation(system,tmp_path):
    _,_,_,site=system;site=copy.deepcopy(site);raw=candidate(site)
    raw['drawing_objects']=[dict(id='beam',name='Beam',layer='other',category='beam',source_ids=[site['geometry'][0]['id']],evidence='Model section')]
    _,path=evidence(tmp_path,site,[])
    proof=json.loads(path.read_text(encoding='utf8'))
    wall=next(e for e in raw['elements'] if e['role']=='wall')
    proof.update(authority=dict(mode='user_designated_model',instruction='Use model'),corrections=[
        dict(id='beam',collection='drawing_objects',expected_binding=None,values=dict(model_dimensions=dict(base=2.1,height=.3,datum='model_finish_floor')),model_objects=['beam-mesh'],reason='three measured sections'),
        dict(id=wall['id'],collection='elements',expected_binding=wall.get('source_binding'),values={'height':2.6},model_objects=['wall-mesh'],reason='model cap')])
    path.write_text(json.dumps(proof),encoding='utf8');site['reference_evidence']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    first,report=validate(site,raw);second,again=validate(site,first)
    assert first==second and len(report['reference_geometry'])==2 and not report['reference_issues']
    assert first['drawing_objects'][0]['model_dimensions']==dict(base=2.1,height=.3,datum='model_finish_floor')
    assert first['elements'][0]['height']==2.6 and not again['reference_issues']


def test_user_confirmed_underside_preserves_missing_depth_and_answer_hash(system,tmp_path):
    from interior.workbench.studio.semantic_diagnostics import beam_requirements
    _,_,_,site=system;site=copy.deepcopy(site);raw=candidate(site)
    raw['drawing_objects']=[dict(id='beam',name='Beam',layer='other',category='beam',source_ids=[site['geometry'][0]['id']],evidence='User identified a hidden beam')]
    _,path=evidence(tmp_path,site,[])
    answer=tmp_path/'answer.txt';answer.write_text('Underside is 2.1 m above finished floor',encoding='utf8')
    source=dict(path=str(answer),sha256=hashlib.sha256(answer.read_bytes()).hexdigest())
    proof=json.loads(path.read_text(encoding='utf8'));proof['reference_sources'].append(source)
    proof.update(authority=dict(mode='user_designated_model',instruction='Use model and my answers'),corrections=[dict(
        id='beam',collection='drawing_objects',expected_binding=None,
        values=dict(model_dimensions=dict(base=2.1,height=None,datum='model_finish_floor')),
        user_confirmation={**source,'statement':'Underside is 2.1 m above finished floor'},reason='Confirmed underside; depth was not supplied')])
    path.write_text(json.dumps(proof),encoding='utf8');site['reference_evidence']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    first,report=validate(site,raw);second,again=validate(site,first)
    assert first==second and first['drawing_objects'][0]['model_dimensions']['height'] is None
    assert report['status']=='blocked' and report['reference_issues']==again['reference_issues']
    assert report['reference_issues'][0]['code']=='reference:beam-depth'
    assert beam_requirements(first['drawing_objects'])==['梁深尚須確認']
    assert report['reference_geometry'][0]['user_confirmation']['sha256']==source['sha256']
    answer.write_text('Changed answer',encoding='utf8')
    assert inspect(site,first)[0]['code']=='reference:integrity'


def test_unbound_user_answer_is_rejected_atomically(system):
    _,_,_,site=system;site=copy.deepcopy(site);raw=validate(site,candidate(site))[0]
    row=raw['elements'][0];before=copy.deepcopy(raw)
    proof=dict(authority=dict(mode='user_designated_model',instruction='Use model'),reference_sources=[],corrections=[dict(
        id=row['id'],collection='elements',expected_binding=row.get('source_binding'),values={'height':2.5},
        user_confirmation=dict(path='not-bound.txt',sha256='a'*64,statement='2.5m'),reason='User answer')])
    with pytest.raises(ValueError,match='來源證據'):resolve(site,raw,proof)
    assert raw==before


def test_split_beam_one_complete_target_does_not_hide_other_missing_depth():
    from interior.workbench.studio.semantic_diagnostics import beam_requirements
    assert beam_requirements([{'model_dimensions':{'base':2.1,'height':.3}},{'model_dimensions':{'base':2.1,'height':None}}])==['梁深尚須確認']
    assert beam_requirements([{'model_dimensions':{'base':2.1,'height':.3}},{}])==['梁標高與梁深尚須確認']
