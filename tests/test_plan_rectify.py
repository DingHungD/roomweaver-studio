"""Orthogonal geometry, exact bound lengths and preserved source evidence."""
import copy
import math
import pytest
from interior.workbench.studio.plan_rectify import rectify
from interior.workbench.studio.plan_import import check_plan,PlanSettings


def sample():
    features=[dict(id='wall',layer='wall',points=[[40,42],[350,48],[358,270]],closed=False),
        dict(id='floor',layer='floor',points=[[40,42],[350,48],[358,270],[40,270]],closed=True),
        dict(id='door',layer='door',points=[[102,43.2],[164,44.4]],closed=False)]
    parsed=dict(image=dict(width=500,height=400),features=features,questions=[],issues=[],
        dimensions=[dict(id='width',metres=3.2,source_refs=['confirmed']),dict(id='conflict',metres=3.4,source_refs=['confirmed'])])
    parsed['recognition_audit']=dict(evidence_review=dict(records=[dict(id='confirmed',dimensions=[dict(dimension_id='width',metres=3.2),dict(dimension_id='conflict',metres=3.4)])]))
    settings=PlanSettings(units='m',calibration=dict(start=[0,0],end=[100,0],metres=1,confirmed=True),
        assignments=[dict(id=f['id'],name=f['id'],role=f['layer'],host_id='wall' if f['id']=='door' else None) for f in features]).model_dump(mode='json')
    binding=dict(dimension_id='width',start=dict(feature_id='wall',vertex=0),end=dict(feature_id='wall',vertex=1),axis='x')
    return parsed,settings,binding


def test_right_angles_exact_measurement_and_opening_transport():
    p,s,b=sample();before=copy.deepcopy((p,s))
    out=rectify(p,s,[b],'revision')
    assert (p,s)==before
    w=out['assignments'][0]['points'];d=out['assignments'][2]['points']
    assert w[0][1]==w[1][1] and w[1][0]==w[2][0]
    assert math.dist(w[0],w[1])*.01==pytest.approx(3.2,abs=1e-8)
    assert all(v[1]==w[0][1] for v in d)
    assert (d[1][0]-d[0][0])/(w[1][0]-w[0][0])==pytest.approx(.2)
    assert out['reconstruction']['bindings']==[b]
    assert check_plan(p,out)['status']=='ready'
    out['assignments'][0]['points'][0][0]-=10
    assert any('已綁定尺寸' in e for e in check_plan(p,out)['errors'])


def test_conflicting_dimensions_rejected_without_averaging():
    p,s,b=sample();other=copy.deepcopy(b);other['dimension_id']='conflict'
    with pytest.raises(ValueError,match='衝突'):rectify(p,s,[b,other],'revision')


@pytest.mark.parametrize('change',['unconfirmed','unknown_vertex','wrong_axis','oblique_wall'])
def test_no_guessed_measurements_or_directions(change):
    p,s,b=sample()
    if change=='unconfirmed':p['dimensions'][0]['source_refs']=[]
    if change=='unknown_vertex':b['end']['vertex']=99
    if change=='wrong_axis':b['axis']='y' # horizontal edge joins the same y group
    if change=='oblique_wall':p['features'][0]['points'][1]=[100,100]
    with pytest.raises(ValueError):rectify(p,s,[b],'revision')


def test_annotations_are_source_coordinates_not_measurement_constraints():
    p,s,_=sample();p['questions']=[dict(id='q',text='Which face?')]
    note=dict(question_id='q',title='Endpoint',known='Value accepted',ask='Which face?',regions=[dict(label='text',box=[10,10,30,30])],answer='inner face')
    s['question_notes']=[note]
    out=rectify(p,s,[],'revision')
    assert out['question_notes']==[note] and not out['reviewed']
    s['question_notes'][0]['regions'][0]['box'][2]=999
    with pytest.raises(ValueError,match='超出'):check_plan(p,s)


def test_opening_exact_width_preserves_host_and_replays():
    p,s,b=sample()
    # First orthogonalize, then apply a width across a redundant wall vertex.
    s=rectify(p,s,[],'first')
    wall=s['assignments'][0]['points'];wall.insert(1,[(wall[0][0]+wall[1][0])/2,wall[0][1]])
    p['dimensions'][0]['metres']=.9
    p['recognition_audit']['evidence_review']['records'][0]['dimensions'][0]['metres']=.9
    b.update(mode='opening_width',start=dict(feature_id='door',vertex=0),end=dict(feature_id='door',vertex=1))
    before=copy.deepcopy(s)
    out=rectify(p,s,[b],'second')
    assert out['assignments'][0]['points']==wall
    assert s==before
    assert check_plan(p,out)['status']=='ready'
    assert check_plan(p,out)['dimension_report'][0]['status']=='applied'
    again=rectify(p,out,[b],'third')
    assert again['assignments']==out['assignments']
    out['assignments'][2]['points'][0][0]-=5
    report=check_plan(p,out)['dimension_report'][0]
    assert report['status']=='conflict' and report['difference_m']==pytest.approx(.05)


def test_opening_does_not_extend_host_or_shrink_confirmed_width():
    p,s,b=sample();b.update(mode='opening_width',start=dict(feature_id='door',vertex=0),end=dict(feature_id='door',vertex=1))
    with pytest.raises(ValueError,match='超過宿主牆'):rectify(p,s,[b],'revision')


def test_source_marks_preserved_and_do_not_approve_questions():
    p,s,_=sample();p['questions']=[dict(id='q',text='Which face?')]
    mark=dict(id='ab',start=[10,20],end=[100,20],description='Inside face to frame',question_id='q')
    s['source_marks']=[mark]
    out=rectify(p,s,[],'revision')
    assert out['source_marks']==[mark] and out['reviewed']==[]
    assert any('疑點' in e for e in check_plan(p,out)['errors'])
    s['source_marks'][0]['end']=[600,20]
    with pytest.raises(ValueError,match='超出'):check_plan(p,s)


def test_preserve_unhosted_addition_and_unaffected_user_confirmations():
    p,s,b=sample();p['questions']=[dict(id='q',text='equipment',feature_ids=['door'])];s['reviewed']=['q']
    s=rectify(p,s,[],'first');s['reviewed']=['q']
    s['assignments'][2]['host_id']=None
    for point in s['assignments'][2]['points']:point[1]+=40
    out=rectify(p,s,[b],'second')
    assert out['assignments'][2]['points']==s['assignments'][2]['points']
    assert out['reviewed']==['q']
    assert any('需對齊' in e for e in check_plan(p,out)['errors'])


def test_confirmed_unbound_dimensions_are_pending_not_applied():
    p,s,_=sample();report=check_plan(p,s)['dimension_report']
    assert all(r['status']=='pending' and r['measured_m'] is None for r in report)
