"""No ground truth: a proposed relabel or non-duplicate deletion cannot erase a model object."""
import numpy as np
from interior.object_recognition.conservative_review import guard


def row(id='a',cls=0,name='wall',box=(0,0,100,10)):
    x,y,r,b=box;mask=np.ones((b-y,r-x),bool)
    return dict(id=id,class_id=cls,class_name=name,mask_box=list(box),mask=mask,area=int(mask.sum()),accepted=True)


def test_class_change_and_unique_deletion_retain_original_as_pending():
    a=row();b=row('b',box=(200,0,300,10))
    rows,pending,_=guard([a,b],[dict(a,class_id=1,class_name='beam')],[dict(id='b',action='reject')])
    assert {r['id'] for r in rows}=={'a','b'} and len(pending)==2
    assert all(not r['accepted'] for r in rows) and rows[0]['class_id']==0


def test_short_fragment_cannot_delete_a_distinct_wall_via_tiny_corner_overlap():
    a=row();b=row('b',box=(90,0,190,10))
    rows,pending,_=guard([a,b],[a],[dict(id='b',action='reject',duplicate_of='a')])
    assert len(rows)==2 and pending[0]['id']=='b'


def test_confirmed_contained_fragment_is_removed_but_large_outline_change_is_held():
    a=row();fragment=row('fragment',box=(0,0,20,10));changed=row('a',box=(0,0,100,100))
    rows,pending,_=guard([a,fragment],[changed],[dict(id='fragment',action='reject',duplicate_of='a')])
    assert len(rows)==1 and rows[0]['mask_box']==a['mask_box'] and len(pending)==1


def test_thin_glass_projection_can_shrink_to_actual_contained_source():
    a=row(name='shower_screen');source=row(name='shower_screen',box=(0,0,100,3))
    rows,pending,_=guard([a],[source],[])
    assert not pending and rows[0]['area']==300
