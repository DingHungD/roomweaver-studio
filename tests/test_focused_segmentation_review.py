"""Scoped review must not erase uncertain objects or alter untouched masks."""
import copy

import numpy as np
import pytest

from interior.object_recognition.focused_review import apply_scoped,validate_scope


def setup():
    s=dict(source_view=dict(pad=0,scale=10,bounds=[0,0,10,10]),
           geometry=[dict(id='g',kind='LWPOLYLINE',closed=True,points=[[1,1],[3,1],[3,2],[1,2]])],texts=[dict(id='t',text='設備')])
    a=dict(id='a',class_name='furniture',class_id=0,mask_box=[10,80,30,90],box=[10,80,30,90],
           mask=np.ones((10,20),bool),area=200,contours=[],confidence=.8)
    b=dict(a,id='b',mask=a['mask'].copy())
    return s,a,b


def decision(action='replace',**extra):
    d=dict(id='a',action=action,class_name='furniture',source_ids=['g'],text_ids=['t'],reason='actual frame')
    if action=='replace':d['mask_spec']=dict(method='outline',refs=[dict(id='g')])
    return dict(d,**extra)


def apply(proposal):
    s,a,b=setup()
    return apply_scoped(s,[a],proposal,[a,b],{'furniture':0},{'a':a,'b':b},(100,100),'focused-test',{'g'})


def test_defer_keeps_original_candidate_in_final_prediction_set():
    rows,audit,pending=apply(dict(decisions=[decision('defer')]))
    assert {r['id'] for r in rows}=={'a','b'} and len(pending)==1


def test_non_targets_remain_bitwise_identical_after_native_correction():
    s,a,b=setup();before=copy.deepcopy(b)
    rows,audit,pending=apply_scoped(s,[a],dict(decisions=[decision()]),[a,b],{'furniture':0},{'a':a,'b':b},(100,100),'focused-test',{'g'})
    result=next(r for r in rows if r['id']=='b')
    assert result['mask_box']==before['mask_box'] and np.array_equal(result['mask'],before['mask'])
    assert result['class_id']==before['class_id'] and not pending


def test_keep_cannot_hide_native_boundary_change():
    with pytest.raises(ValueError,match='keep cannot'):
        apply(dict(decisions=[decision('keep',mask_spec=dict(method='outline',refs=[dict(id='g')]))]))


def test_duplicate_must_survive_and_have_actual_source_evidence():
    rows,audit,pending=apply(dict(decisions=[decision('reject',duplicate_of='b')]))
    assert [r['id'] for r in rows]==['b']
    for change in [dict(duplicate_of='a'),dict(duplicate_of='unknown'),dict(source_ids=[]),dict(text_ids=['invented'])]:
        with pytest.raises(ValueError):apply(dict(decisions=[decision('reject',**change)]))


def test_unknown_target_cannot_remove_non_target_candidate():
    with pytest.raises(ValueError,match='Exactly one'):
        apply(dict(decisions=[dict(decision('reject'),id='b')]))


def test_keep_of_already_corrected_native_object_does_not_revert_to_old_yolo():
    s,a,b=setup()
    rows,audit,pending=apply(dict(decisions=[decision()]))
    corrected=next(r for r in rows if r['id']=='a')
    assert corrected['area']!=a['area']
    kept,_,_=apply_scoped(s,[corrected],dict(decisions=[decision('keep',mask_spec=dict(method='yolo',candidate_id='a'))]),
        rows,{'furniture':0},{'a':a,'b':b},(100,100),'repair-test',{'g'})
    result=next(r for r in kept if r['id']=='a')
    assert np.array_equal(result['mask'],corrected['mask']) and result['mask_box']==corrected['mask_box']
    assert result['mask_spec']['method']=='outline' and result['provenance']=='agent_native'


def test_frozen_review_comparison_maps_canonical_to_training_class_ids(tmp_path):
    from PIL import Image
    from interior.object_recognition.agent_review import raster,source_shape,save_state
    from interior.object_recognition.review_report import freeze_review,compare_review
    from interior.object_recognition.tiled import write,sha
    pytest.importorskip('scipy')
    s,a,b=setup();source=tmp_path/'source.png';image=Image.new('RGB',(100,100),'white');image.save(source)
    s['native_dwg']=dict(source_sha256='synthetic-source')
    geometry=raster(s,source_shape(s,dict(method='outline',refs=[dict(id='g')])),image.size)
    prediction=dict(a,**geometry,route='agent_review')
    bundle=tmp_path/'bundle';bundle.mkdir();review=tmp_path/'review';review.mkdir()
    save_state(bundle,[prediction],image,'candidates');save_state(review,[prediction],image,'corrected')
    write(bundle/'config.json',dict(image=str(source),sha256=dict(image=sha(source),checkpoint='synthetic-model')))
    write(review/'layers.json',dict(layers={}));write(review/'layer-verification.json',dict(findings=[]))
    freeze_review(review)
    reference=tmp_path/'reference.json';classes=tmp_path/'classes.json';request=tmp_path/'request.json'
    write(reference,dict(source=dict(original_sha256='synthetic-source'),objects=[dict(id='object',name='furniture',
        class_id=17,training_class_id=0,class_name='furniture',exclusion_reason=None,contour_quality='exact',geometry_m=[s['geometry'][0]['points']])]))
    write(classes,dict(classes=[dict(id=0,name='furniture')]))
    write(request,dict(site=s))
    result=compare_review(review,bundle,reference,request,tmp_path/'evaluation',classes_path=classes)
    assert result['scores']['before_yolo']['true_positive']==1
    assert result['scores']['after_agent']['true_positive']==1
    assert result['training_classes_sha256']==sha(classes)
