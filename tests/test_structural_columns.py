"""Different native column outlines remain distinct from adjacent thin walls."""
import copy
import pytest

from test_plan_semantics import system,candidate
from interior.workbench.studio.plan_semantics import validate,prompt
from interior.workbench.studio.source_binding import resolve
from interior.workbench.studio.correction_regions import verify_regions,STRUCTURE_RULE


@pytest.mark.parametrize('category',['column','wall_junction'])
def test_source_outline_keeps_sloping_edge_and_original_coordinates(category):
    points=[[2,1],[2.55,1],[2.6,1.6],[2,1.6]]
    site=dict(native_dwg=dict(source_sha256='synthetic'),geometry=[dict(id='column-source',kind='LWPOLYLINE',points=points,closed=True,native_exact=True)])
    obj=dict(id='column',name='Synthetic column',role='wall',category=category,points=[[99,99],[100,100]],closed=False,source_ids=['column-source'],source_binding=dict(method='outline',refs=[dict(id='column-source',edge=0)]))
    before=copy.deepcopy(site);errors,_=resolve(site,dict(elements=[obj]))
    assert not errors and site==before and obj['points']==points and obj['closed']
    assert obj['thickness']==pytest.approx(.6)


def test_plain_wall_cannot_use_structural_outline_shortcut():
    site=dict(native_dwg=dict(source_sha256='x'),geometry=[dict(id='s',kind='LWPOLYLINE',points=[[0,0],[1,0],[1,1],[0,1]],closed=True,native_exact=True)])
    obj=dict(id='w',name='Synthetic wall',role='wall',category=None,source_binding=dict(method='outline',refs=[dict(id='s',edge=0)]))
    assert resolve(site,dict(elements=[obj]))[0]


def test_column_pair_cannot_trim_a_nonrectangular_source():
    source=dict(id='s',kind='LWPOLYLINE',points=[[0,0],[.5,0],[.55,.6],[0,.6]],closed=True,native_exact=True)
    site=dict(native_dwg=dict(source_sha256='x'),geometry=[source])
    obj=dict(id='col',name='column',role='wall',category='column',source_binding=dict(method='pair',refs=[dict(id='s',edge=0),dict(id='s',edge=2)]))
    errors,_=resolve(site,dict(elements=[obj]))
    assert any('outline' in e for e in errors)


def test_column_is_filterable_and_not_converted_to_furniture(system):
    _,_,_,site=system;raw=candidate(site)
    raw['elements'][0]['category']='column'
    p,r=validate(site,raw)
    wall=next(i for i in r['layers']['items'] if i['id']==p['elements'][0]['id'])
    assert wall['category']=='column' and wall['layer']=='walls' and wall['role']=='wall'
    raw['elements'][-1]['category']='column'
    assert any('不可登記為家具' in e for e in validate(site,raw)[1]['errors'])
    assert STRUCTURE_RULE in prompt(site)


def test_each_column_mark_requires_its_own_actual_structural_footprint():
    item=dict(title='修正項',comment='這屬於柱體，與牆壁厚度不一樣',marks=[dict(id='m1',kind='box',points=[[0,0],[.5,.5]]),dict(id='m2',kind='box',points=[[3,3],[3.5,3.5]])])
    column=lambda id,points:dict(id=id,role='wall',category='column',points=points,closed=True,thickness=.5)
    p=dict(elements=[column('a',[[0,0],[.5,0],[.5,.5],[0,.5]]),column('b',[[3,3],[3.5,3],[3.5,3.5],[3,3.5]])])
    result=dict(mark_results=[dict(mark_id=id,status='corrected',expected_kind='column',object_ids=[obj],summary='Column confirmed') for id,obj in [('m1','a'),('m2','b')]])
    s=dict(geometry=[])
    assert not verify_regions(s,p,item,result)[1]
    p['elements'][1].update(category=None)
    assert verify_regions(s,p,item,result)[1]
    p['elements'][1].update(category='column',points=[[3,3],[3.05,3],[3.05,3.5],[3,3.5]])
    assert any('僅覆蓋' in e for e in verify_regions(s,p,item,result)[1])
