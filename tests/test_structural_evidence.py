"""Independent fill and contour disagreement must not pass as correct geometry."""
import copy
from interior.workbench.studio.structural_evidence import straight_hatch_loops,outline_conflicts
from interior.workbench.studio.source_binding import resolve


def test_only_single_closed_straight_solid_hatch_is_exact():
    points=[[0,0],[.6,0],[.6,.5],[0,.5]]
    hatch=dict(entity='HATCH',is_solid_fill=1,paths=[dict(flag=1,segs=[dict(curve_type=1,first_endpoint=p,second_endpoint=points[(i+1)%4]) for i,p in enumerate(points)])])
    assert straight_hatch_loops(hatch)==[(0,points)]
    for changed in [dict(hatch,is_solid_fill=0),dict(hatch,paths=hatch['paths']*2),dict(hatch,extrusion=[0,1,0])]:assert not straight_hatch_loops(changed)
    broken=copy.deepcopy(hatch);broken['paths'][0]['segs'][1]['first_endpoint']=[.7,0]
    assert not straight_hatch_loops(broken)


def test_conflicting_native_contour_rejected_but_verified_solid_can_be_bound():
    fill=dict(id='fill',kind='HATCH',closed=True,points=[[0,0],[.6,0],[.6,.5],[0,.5]],native_exact_fill=True)
    contour=dict(id='edge',kind='LWPOLYLINE',closed=True,points=[[0,0],[.55,0],[.6,.5],[0,.5]],native_exact=True)
    site=dict(native_dwg=dict(source_sha256='fixture'),geometry=[fill,contour]);original=copy.deepcopy(site)
    assert outline_conflicts(site,contour)[0]['max_edge_difference_m']>.04
    obj=dict(id='col',name='Column',role='wall',category='column',source_ids=['edge'],source_binding=dict(method='outline',refs=[dict(id='edge',edge=0)]))
    assert any('不一致' in e for e in resolve(site,dict(elements=[obj]))[0])
    obj['source_binding']=dict(method='solid_outline',refs=[dict(id='fill',edge=0)])
    assert not resolve(site,dict(elements=[obj]))[0]
    assert obj['points']==fill['points'] and site==original
    fill['native_exact_fill']=False
    assert resolve(site,dict(elements=[obj]))[0]
    fill['native_exact_fill']=True;obj['role']='furniture'
    assert resolve(site,dict(elements=[obj]))[0]


def test_fill_provenance_and_loop_start_do_not_reset_unrelated_source_records():
    from interior.workbench.studio.cad_candidates import source_hash,same_source
    a=dict(reference_revision='same',geometry=[dict(id='f',points=[[0,0],[1,0],[1,1],[0,1]],closed=True,kind='HATCH')],texts=[],dimensions=[],origin=[0,0],factor=1,floor_locked=True)
    b=copy.deepcopy(a);b['geometry'][0]['native_exact_fill']=True
    assert source_hash(a)==source_hash(b) and same_source(a,b)
    b['geometry'][0]['points']=b['geometry'][0]['points'][1:]+b['geometry'][0]['points'][:1]
    assert same_source(a,b)
    b['geometry'][0]['points'][0][0]+=.01
    assert not same_source(a,b)
