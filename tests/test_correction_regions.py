"""Synthetic adjacent cabinet/walls and every-mark completion checks."""
import copy
import pytest

from interior.workbench.studio.correction_regions import verify_regions, WALL_CABINET_RULE
from interior.workbench.studio.semantic_corrections import correction_report
from interior.workbench.studio.plan_semantics import prompt


def fixture():
    item=dict(id='cor-'+'1'*32,title='書房牆',comment='此處為牆壁',marks=[
        dict(id='top',kind='box',points=[[0,3],[4,3.15]],text=''),
        dict(id='bottom',kind='box',points=[[0,0],[4,.15]],text='')])
    wall=lambda id,y:dict(id=id,role='wall',points=[[0,y],[4,y]],closed=False)
    proposal=dict(elements=[wall('north',3.07),wall('south',.07),dict(id='cabinet',role='furniture',points=[[0,2],[4,2],[4,3],[0,3]],closed=True,source_ids=['wall-source'])])
    row=dict(id=item['id'],status='corrected',summary='Both spans corrected',mark_results=[dict(mark_id=m['id'],status='corrected',expected_kind='wall',object_ids=[id],summary='Actual wall') for m,id in zip(item['marks'],['north','south'])])
    return dict(geometry=[],correction_batch=dict(items=[item],selected_ids=[item['id']],verification_version='mark-regions-v1')),proposal,item,row


def test_all_marks_have_resolved_geometry_and_no_change_must_also_prove():
    s,p,i,r=fixture()
    for status in ['corrected','no_change']:
        r['status']=status
        checks,issues=verify_regions(s,p,i,r)
        assert not issues and len(checks)==2 and all(c['passed'] for c in checks)
        assert correction_report(s,dict(p,correction_results=[r]),[])[0][0]['preview_ready']


@pytest.mark.parametrize('mode',['missing','duplicate','foreign','wrong-role','wrong-location','corner-only','second-disappeared','unresolved'])
def test_incomplete_mark_never_completes(mode):
    s,p,i,r=fixture()
    if mode=='missing':r['mark_results'].pop()
    if mode=='duplicate':r['mark_results'].append(copy.deepcopy(r['mark_results'][0]))
    if mode=='foreign':r['mark_results'][1]['mark_id']='other-item-mark'
    if mode=='wrong-role':r['mark_results'][0].update(object_ids=['cabinet'],expected_kind='furniture')
    if mode=='wrong-location':r['mark_results'][0]['object_ids']=['south']
    if mode=='corner-only':p['elements'][0]['points']=[[0,3.07],[.2,3.07]]
    if mode=='second-disappeared':p['elements']=[e for e in p['elements'] if e['id']!='south']
    if mode=='unresolved':r['mark_results'][1]['status']='unresolved'
    checks,issues=verify_regions(s,p,i,r)
    assert issues
    rows,errors=correction_report(s,dict(p,correction_results=[r]),[])
    assert errors and rows[0]['status']=='unresolved' and not rows[0]['preview_ready']


def test_historical_wall_self_claim_is_audited_without_rewriting_history():
    s,p,i,r=fixture();r.pop('mark_results');s['correction_batch'].pop('verification_version')
    original=copy.deepcopy(r)
    assert not verify_regions(s,p,i,r,strict=False)[1]
    p['elements'].pop(1)
    rows,errors=correction_report(s,dict(p,correction_results=[r]),[])
    assert errors and not rows[0]['preview_ready'] and r==original
    assert not rows[0]['mark_checks'][1]['passed']


def test_adjacent_rule_and_per_mark_contract_are_in_shared_prompt():
    s,_,_,_=fixture()
    assert WALL_CABINET_RULE in prompt(s)
    assert 'mark_results' in prompt(s) and 'object_ids' in prompt(s)


def test_mixed_request_does_not_treat_every_mark_as_wall():
    from interior.workbench.studio.correction_regions import explicit_wall
    assert not explicit_wall(dict(title='淋浴間',comment='右邊為玻璃門，下方為牆'))
    assert not explicit_wall(dict(title='浴廁門口',comment='此處不為牆壁，為門口'))
    assert explicit_wall(dict(title='書房牆',comment='此處為牆壁'))


def test_actual_wall_thickness_can_overlap_a_mark_drawn_on_its_face():
    s,p,i,r=fixture();p['elements'][0].update(points=[[0,3.25],[4,3.25]],thickness=.3)
    assert not verify_regions(s,p,i,r)[1]
