"""Synthetic window-host continuity; source positions and true gaps are retained."""
import copy
import pytest
from interior.workbench.studio.source_binding import resolve,host_compatible


@pytest.mark.parametrize('angle',[0,.7])
def test_overlapping_apertures_ignore_host_names_but_respect_elevation_and_end_joints(angle):
    import math
    from interior.workbench.studio.source_binding import overlapping_openings
    def row(id,lo,hi,base=1):
        return dict(id=id,role='window',host_id=id+'-host',base=base,height=1,
            points=[[t*math.cos(angle),t*math.sin(angle)] for t in (lo,hi)])
    proposal=dict(elements=[row('a',0,3),row('b',1,3),row('c',3,4),row('transom',0,3,2)])
    found=overlapping_openings(proposal)
    assert len(found)==1 and found[0]['object_ids']==['a','b']
    assert found[0]['overlap_m']==pytest.approx(2)


@pytest.mark.parametrize('gap,compatible',[(0,True),(.02,False)])
def test_window_host_uses_same_native_continuous_runs(gap,compatible):
    def line(id,a,b):return dict(id=id,points=[a,b],closed=False,kind='LINE',native_exact=True)
    site=dict(native_dwg=dict(source_sha256='a'*64),geometry=[line('short',[0,0],[0,.05-gap]),line('long',[0,.05],[0,1.2]),line('opposite',[.16,0],[.16,1.2])])
    def item(id,role,refs,host=None):return dict(id=id,name=id,role=role,source_ids=[],host_id=host,source_binding=dict(method='pair',refs=[dict(id=r,edge=0) for r in refs]),points=[],closed=False,thickness=.16)
    candidate=dict(elements=[item('host','wall',['long','opposite']),item('window','window',['short','opposite'],'host')]);original=copy.deepcopy(site)
    errors,_=resolve(site,candidate)
    # The disconnected short line is too short to derive a window in the gap case.
    if compatible:
        assert not errors and host_compatible(candidate['elements'][1],candidate['elements'][0])
        assert {tuple(p) for p in candidate['elements'][0]['points']}=={(.08,0),(.08,1.2)}
        assert 'short' in candidate['elements'][0]['derivation']['automatic_correction']['expanded_refs']
    else:assert errors or not host_compatible(candidate['elements'][1],candidate['elements'][0])
    assert site==original
    if compatible:
        prior=copy.deepcopy(candidate)
        site['previous_review']=dict(candidate=prior)
        site['correction_batch']=dict(items=[dict(marks=[dict(points=[[8,8],[9,9]])])])
        assert not resolve(site,candidate)[0]
        assert candidate['elements'][0]['points']==prior['elements'][0]['points']


@pytest.mark.parametrize('rotation',[0,.6])
def test_edge_bounds_keeps_actual_selected_inner_edges_outside_wall_and_swing(rotation):
    import math
    geometry=[dict(id='wall',kind='LWPOLYLINE',native_exact=True,closed=True,points=[[0,-.2],[1,-.2],[1,0],[0,0]]),dict(id='screen',kind='LWPOLYLINE',native_exact=True,closed=True,points=[[1,0],[1.02,0],[1.02,2],[1,2]]),dict(id='top',kind='LINE',native_exact=True,closed=False,points=[[0,2],[1,2]]),dict(id='left',kind='LINE',native_exact=True,closed=False,points=[[0,0],[0,2]])]
    def transform(p):return [p[0]*math.cos(rotation)-p[1]*math.sin(rotation),p[0]*math.sin(rotation)+p[1]*math.cos(rotation)]
    for g in geometry:g['points']=[transform(p) for p in g['points']]
    site=dict(native_dwg=dict(source_sha256='a'*64),geometry=geometry);original=copy.deepcopy(site)
    furniture=dict(id='zone',name='Equipment zone',role='furniture',source_ids=['wall','screen'],source_binding=dict(method='edge_bounds',refs=[dict(id='wall',edge=0),dict(id='screen',edge=1),dict(id='top',edge=0),dict(id='left',edge=0)]),points=[[0,-9],[9,9]],closed=True)
    errors,_=resolve(site,dict(elements=[furniture]))
    assert not errors and all(min(math.dist(p,transform(q)) for p in furniture['points'])<1e-8 for q in ((0,0),(1,0),(1,2),(0,2))) and site==original
    furniture['role']='wall'
    assert resolve(site,dict(elements=[furniture]))[0]
