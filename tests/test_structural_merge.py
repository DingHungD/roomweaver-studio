"""Synthetic partial structures and independent nearby instances, without case data."""
import copy

import numpy as np
import pytest

pytest.importorskip('cv2')
from interior.object_recognition.tiled import merge, settings, mask_iou


def row(i,box,name='beam',view='full',clipped=False):
    x,y,r,b=box;mask=np.ones((b-y,r-x),bool)
    return dict(id=i,view_id=view,window=[0,0,200,200],mask_box=list(box),box=list(box),mask=mask,
                area=int(mask.sum()),contours=[],class_id={'wall':0,'beam':1,'track_light':2,'window':3}[name],
                class_name=name,clipped=clipped,confidence=.8)


def run(rows):return merge(rows,settings(dict(merge_policy='structural_v2')))


def test_contained_same_view_beam_fragment_is_not_a_new_instance():
    rows=[row('a',(0,0,100,10)),row('b',(0,0,40,10))]
    assert len(merge(rows,settings()))==2
    result=run(rows)
    assert len(result)==1 and result[0]['area']==1000
    assert result[0]['members']==['a','b'] and not result[0]['accepted']


def test_collinear_thin_masks_with_scale_width_disagreement_merge():
    rows=[row('a',(0,2,100,4),'track_light'),row('b',(0,0,100,6),'track_light','tile-0')]
    result=run(rows)
    assert len(result)==1 and result[0]['area']==200


def test_parallel_and_perpendicular_lights_remain_independent():
    rows=[row('a',(0,0,100,3),'track_light'),row('b',(0,9,100,12),'track_light','tile-0'),
          row('c',(40,0,43,100),'track_light','tile-1')]
    assert len(run(rows))==3


def test_independent_wall_and_window_are_not_joined_by_adjacency():
    rows=[row('a',(0,0,100,10),'wall'),row('b',(101,0,200,10),'wall','tile-0'),
          row('c',(0,0,100,10),'window','tile-1')]
    assert len(run(rows))==3


def test_supported_seam_extension_uses_actual_pixels_and_preserves_hole():
    a=row('a',(0,0,100,10));a['mask'][3:7,30:40]=False;a['area']=int(a['mask'].sum())
    b=row('b',(40,0,140,10),view='tile-0',clipped=True)
    c=row('c',(40,0,140,10),view='tile-1',clipped=True)
    result=run([a,b,c])[0]
    assert result['mask_box']==[0,0,140,10] and not result['mask'][5,35]
    assert result['area']==1360 and result['fusion']['added_pixels']==400
    assert any(c['hole'] for c in result['contours'])


def test_single_view_extension_cannot_invent_missing_geometry():
    rows=[row('a',(0,0,100,10)),row('b',(40,0,140,10),view='tile-0',clipped=True)]
    result=run(rows)[0]
    assert result['mask_box']==[0,0,100,10]


def test_wall_branches_can_be_restored_but_input_predictions_are_immutable():
    rows=[row('a',(0,0,100,10),'wall'),row('b',(0,0,70,10),'wall')]
    before=copy.deepcopy(rows)
    result=run(rows)
    for a,b in zip(rows,before):
        assert np.array_equal(a.pop('mask'),b.pop('mask'))
        assert a==b
    assert result[0]['area']==1000


def test_legacy_policy_still_reproduces_and_unknown_policy_rejected():
    rows=[row('a',(0,0,100,10)),row('b',(0,0,40,10))]
    assert len(merge(rows,settings()))==2
    with pytest.raises(ValueError,match='merge policy'):settings(dict(merge_policy='unknown'))


def test_a_shared_short_fragment_cannot_bridge_distinct_full_wall_instances():
    rows=[row('a',(0,0,100,10),'wall'),row('b',(50,0,150,10),'wall'),
          row('fragment',(60,0,90,10),'wall','tile-0')]
    result=run(rows)
    assert len(result)==2
    assert sorted(r['mask_box'] for r in result)==[[0,0,100,10],[50,0,150,10]]
