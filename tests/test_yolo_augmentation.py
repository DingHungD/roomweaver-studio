"""Synthetic scale-space, CAD clipping and augmentation invariants."""
import json
from pathlib import Path

import pytest
import numpy as np
from PIL import Image

from interior.object_recognition.tiled import pyramid_views,settings,reproject,merge
from interior.object_recognition.augmentation import build_dataset,rotate_points
from test_yolo_recognition import row


def test_half_tiles_cover_1280_context_and_native_stays_640():
    views=pyramid_views((2280,1649),settings())
    assert sum(v['family']=='native' for v in views)==20
    assert sum(v['family']=='context' for v in views)==6
    half=next(v for v in views if v['family']=='context')
    assert half['scaled_size']==[1140,825] and half['box'][2]-half['box'][0]==1280
    assert abs(half['box'][3]-half['box'][1]-1280)<=1
    assert half['scale_xy'][1]==825/1649


def test_reprojection_matches_global_nearest_grid_on_odd_dimensions():
    pytest.importorskip('cv2')
    r=row(rect=(1,1,4,4));r['window']=[0,0,4,4];r['box']=[1,1,4,4]
    projected=reproject(r,(4,4),(7,9))
    expected=Image.new('L',(4,4));expected.paste(Image.fromarray(r['mask'].astype('uint8')*255),(1,1))
    expected=np.asarray(expected.resize((7,9),Image.Resampling.NEAREST))>0
    actual=np.zeros((9,7),bool);x,y,b,c=projected['mask_box'];actual[y:c,x:b]=projected['mask']
    assert np.array_equal(actual,expected)


def test_fragment_containment_does_not_invent_union_or_promote():
    big=row(rect=(0,0,100,10));small=row('b','tile-0',rect=(0,0,20,10),clipped=True)
    result=merge([big,small],settings())
    assert len(result)==1 and result[0]['area']==1000 and result[0]['contained_fragments']==['b']
    assert result[0]['route']=='agent_review' and not result[0]['accepted']
    small['clipped']=False
    assert len(merge([big,small],settings()))==2


def test_quarter_turns_preserve_rectangle_coordinates():
    points=[[2,3],[5,3],[5,6],[2,6]]
    rotated=rotate_points(points,10,20,1)
    assert rotated==[[17,2],[17,5],[14,5],[14,2]]
    assert rotate_points(rotated,20,10,3)==points


def test_dataset_clips_labels_and_keeps_one_source_group(tmp_path):
    image=tmp_path/'image.png';Image.new('RGB',(80,70),'white').save(image)
    labels=tmp_path/'labels.txt';labels.write_text('0 0.1 0.1 0.9 0.1 0.9 0.9 0.1 0.9\n',encoding='utf-8')
    mapping=tmp_path/'mapping.json';mapping.write_text(json.dumps([dict(object_id='obj',class_id=0,contour_quality='synthetic')]),encoding='utf-8')
    classes=tmp_path/'classes.json';classes.write_text(json.dumps(dict(classes=[dict(id=0,name='wall')])),encoding='utf-8')
    out=tmp_path/'dataset';result=build_dataset(image,labels,mapping,classes,out,'synthetic-source')
    assert result['source_objects']==1 and result['derived_images']==12 and not result['independent_validation']
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    assert {r['source_group'] for r in manifest['records']}=={'synthetic-source'}
    for path in (out/'labels/train').glob('*.txt'):
        for line in path.read_text().splitlines():assert all(0<=float(v)<=1 for v in line.split()[1:])
    with pytest.raises(FileExistsError):build_dataset(image,labels,mapping,classes,out,'synthetic-source')
