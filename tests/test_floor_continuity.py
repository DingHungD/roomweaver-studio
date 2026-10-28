"""Different plans preserve voids, boundaries and confirmed floor polygons."""
import copy
import pytest
from interior.workbench.studio.floor_continuity import inspect

def fixture():
    def wall(i,points):return dict(id=i,name=i,role='wall',points=points,closed=False,thickness=.18,base=0,height=2.8)
    def floor(i,points):return dict(id=i,name=i,role='floor',points=points,closed=True,height=.1,base=0)
    return [wall('outer',[(0,0),(5,0),(5,4),(0,4),(0,0)]),wall('divider',[(2.5,0),(2.5,4)]),
        floor('left',[(0,0),(2.4,0),(2.4,4),(0,4)]),floor('right',[(2.6,0),(5,0),(5,4),(2.6,4)]),
        dict(id='door',role='door',points=[(2.5,1),(2.5,2.2)],base=0,host_id='divider')]

def test_floor_seam_is_bounded_by_actual_door_and_does_not_change_input():
    items=fixture();before=copy.deepcopy(items);value=inspect(items)
    assert items==before
    # Door threshold plus the 1 cm strips left between each slab and the wall.
    assert value['repair_area']==pytest.approx(.2*1.2+.02*(4-.18-1.2),abs=.00001)
    assert all(p['donor_id'] in ('left','right') for p in value['patches'])
    assert inspect(items)==value

def test_unknown_boundary_wide_void_and_different_slab_depth_are_not_patched():
    items=fixture();items[0]['points']=items[0]['points'][:-1]
    assert not inspect(items)['patches']
    items=fixture();items[3]['height']=.25
    assert not inspect(items)['patches']
    items=fixture();items[3]['points']=[(3,0),(5,0),(5,4),(3,4)]
    assert not inspect(items)['patches']

def test_window_or_raised_door_does_not_cut_a_floor_passage():
    items=fixture();items[-1]['role']='window'
    assert inspect(items)['repair_area']==0
    items[-1]['role']='door';items[-1]['base']=.3
    assert inspect(items)['repair_area']==0
