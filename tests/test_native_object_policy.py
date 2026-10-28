"""Synthetic native-shape safeguards, unrelated to client drawings."""
import copy
import numpy as np
import pytest
from interior.object_recognition.native_policy import normalized_site,GUIDANCE
from interior.object_recognition.agent_review import source_shape,raster,apply_response


def test_exact_return_closure_is_derived_without_changing_source_or_bridging_gaps():
    source=dict(geometry=[dict(id='return',closed=False,points=[[1,1],[3,1],[2,2],[1,1]]),
                          dict(id='gap',closed=False,points=[[5,1],[7,1],[6,2],[5.00001,1]])])
    original=copy.deepcopy(source);site,audit=normalized_site(source)
    assert source==original and site['geometry'][0]['closed'] and not site['geometry'][1]['closed']
    assert [r['id'] for r in audit]==['return'] and not audit[0]['coordinates_changed']
    assert source_shape(source,dict(method='outline',refs=[dict(id='return')])).area==1
    with pytest.raises(ValueError,match='closed'):source_shape(source,dict(method='outline',refs=[dict(id='gap')]))


def test_native_hull_fills_the_whole_curved_footprint_without_rectangle_corners():
    site=dict(geometry=[dict(id='back',closed=False,points=[[0,1],[.3,1.4],[.7,1.4],[1,1]]),
                        dict(id='seat',closed=False,points=[[0,1],[0,0],[1,0],[1,1]])])
    spec=dict(method='hull',refs=[dict(id='back'),dict(id='seat')]);shape=source_shape(site,spec)
    assert 1<shape.area<1.4 and shape.bounds==(0,0,1,1.4)
    assert all(list(p) in [p for g in site['geometry'] for p in g['points']] for p in list(shape.exterior.coords)[:-1])
    with pytest.raises(ValueError,match='Unknown'):source_shape(site,dict(method='hull',refs=[dict(id='invented')]))


def test_human_class_and_decisions_cannot_be_silently_overridden():
    site=dict(source_view=dict(pad=0,scale=10,bounds=[0,0,10,10]),texts=[],geometry=[dict(id='native',closed=True,points=[[1,1],[3,1],[3,2],[1,2]])])
    spec=dict(method='outline',refs=[dict(id='native')]);row=dict(id='model-object',class_id=0,class_name='furniture',human_confirmation=dict(decision='model'),human_semantics=dict(possible_reserved_space=True),**raster(site,source_shape(site,spec),(100,100)))
    d=dict(id=row['id'],action='replace',class_name='wall',source_ids=['native'],reason='synthetic',mask_spec=spec)
    def apply(decision):return apply_response(site,[row],dict(decisions=[decision]),[row],dict(furniture=0,wall=1),{row['id']:row},(100,100),'test')
    with pytest.raises(ValueError,match='class is locked'):apply(d)
    with pytest.raises(ValueError,match='human-confirmed'):apply(dict(d,action='reject'))
    result,_,_=apply(dict(d,class_name='furniture'))
    assert result[0]['human_confirmation']==row['human_confirmation'] and result[0]['human_semantics']==row['human_semantics']
    with pytest.raises(ValueError,match='only for curved furniture'):apply(dict(d,class_name='wall',mask_spec=dict(spec,method='hull')))


def test_guidance_is_generic_and_has_no_case_specific_identifiers():
    assert 'project08' not in GUIDANCE.lower() and 'e-722' not in GUIDANCE and 'Y041' not in GUIDANCE


def test_yolo_handoff_does_not_weaken_the_existing_nonzero_dimension_contract():
    from interior.workbench.studio.plan_semantics import SemanticElement
    from interior.workbench.studio.yolo_review import SEMANTIC_HANDOFF_RULES
    furniture=dict(id='chair',name='Chair',role='furniture',room_id='room',points=[[0,0],[1,0],[1,1]],closed=True,source_ids=['native'],evidence='Synthetic source')
    with pytest.raises(ValueError):SemanticElement.model_validate(dict(furniture,thickness=0))
    result=SemanticElement.model_validate(furniture)
    assert result.thickness==.15 and '省略thickness' in SEMANTIC_HANDOFF_RULES
    assert 'drawing_objects' in SEMANTIC_HANDOFF_RULES and 'source_binding' in SEMANTIC_HANDOFF_RULES


def test_handoff_adapter_preserves_source_and_semantics_but_canonicalizes_display_fields():
    from interior.workbench.studio.yolo_review import normalize_semantic_handoff
    from interior.workbench.studio.plan_semantics import SemanticElement
    original=dict(elements=[dict(id='chair',name='Chair',role='furniture',room_id='room',points=[[1,1],[2,1],[2,2]],source_ids=['source'],evidence='native',thickness=0),dict(id='wall',role='wall',thickness=0)],drawing_objects=[dict(id='screen',category='other',layer='equipment',source_ids=['screen-source'])])
    before=copy.deepcopy(original);result,audit=normalize_semantic_handoff(original)
    assert original==before and result['elements'][0]['points']==original['elements'][0]['points']
    assert result['elements'][0]['role']=='furniture' and 'thickness' not in result['elements'][0]
    assert SemanticElement.model_validate(result['elements'][0]).thickness==.15
    assert result['elements'][1]['thickness']==0 and result['drawing_objects'][0]['category']=='other'
    assert result['drawing_objects'][0]['layer']=='other' and len(audit)==2
    with pytest.raises(ValueError):SemanticElement.model_validate(dict(result['elements'][0],role='wall',thickness=0))


def test_resume_key_ignores_only_enumeration_order_and_untrusted_failed_guesses():
    from interior.workbench.studio.yolo_review import recognition_source_key
    a=dict(geometry=[dict(id='b',points=[[0,0],[1,1]]),dict(id='a',points=[[2,2],[3,3]])],source_view=dict(scale=10),confirmed_unit='cm')
    b=copy.deepcopy(a);b['geometry'].reverse();b['previous_failed_review']=dict(candidate='not authoritative')
    assert recognition_source_key(a)==recognition_source_key(b)
    b['geometry'][0]['points'][0][0]+=1
    assert recognition_source_key(a)!=recognition_source_key(b)


def test_resume_rejects_cross_plan_and_tampered_frozen_results(tmp_path):
    from interior.workbench.studio.yolo_review import resume_bundle
    from interior.object_recognition.tiled import write,sha
    import json
    source=tmp_path/'source.png';source.write_bytes(b'original-image')
    previous=tmp_path/'old';output=tmp_path/'new';output.mkdir();bundle=previous/'yolo-inference';review=previous/'yolo-native-review';bundle.mkdir(parents=True);review.mkdir()
    site=dict(geometry=[]);write(previous/'request.json',dict(site=site))
    for name in ['candidates.json','candidates-masks.npz','taxonomy.json']:(bundle/name).write_text('{}')
    write(bundle/'config.json',dict(sha256=dict(image=sha(source),checkpoint='model'),options={}))
    write(bundle/'status.json',dict(status='completed'));write(review/'pipeline-summary.json',{})
    (review/'objects.json').write_text('[]');write(review/'frozen-result.json',dict(files={'objects.json':sha(review/'objects.json')}))
    write(review/'binding.json',{k:sha(bundle/name) for k,name in [('candidates','candidates.json'),('masks','candidates-masks.npz'),('taxonomy','taxonomy.json')]})
    payload=dict(_recognition_resume_from=str(previous),image=str(source),site=site)
    assert resume_bundle(payload,output,'model',{})==bundle.resolve()
    assert json.loads((output/'recognition-resume.json').read_text())['source_run']=='old'
    with pytest.raises(ValueError,match='同一平面'):resume_bundle(payload,tmp_path/'different-plan/new','model',{})
    (review/'objects.json').write_text('[1]')
    with pytest.raises(ValueError,match='雜湊'):resume_bundle(payload,output,'model',{})
