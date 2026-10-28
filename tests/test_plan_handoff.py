"""Unrelated synthetic handoffs: no customer drawing or case-specific coordinates."""
import copy
import json
from unittest.mock import Mock
import pytest
from test_plan_semantics import system
from interior.workbench.studio.plan_handoff import validate_handoff, handoff_items, compile_handoff, HandoffSpec


def sample(dx=0,dy=0):
    def p(x,y):return [x+dx,y+dy]
    source=dict(geometry=[dict(id='counter-edge',points=[p(1,1),p(4,1)],closed=False),dict(id='lamp-sign',points=[p(2,3),p(2.2,3.2)],closed=True),dict(id='rug-sign',points=[p(3,4),p(5,5)],closed=True)],texts=[dict(id='note',text='保留原有木地板',point=p(2,2))],dimensions=[dict(id='dim',start=p(1,1),end=p(4,1),metres=3)],origin=[10,20])
    c=dict(rooms=[dict(id='room',name='Study',points=[p(0,0),p(6,0),p(6,6),p(0,6)],source_ids=['note'])],elements=[dict(id='counter',name='Counter',role='furniture',room_id='room',closed=True,points=[p(1,1),p(4,1),p(4,2),p(1,2)],source_ids=['counter-edge'])],lighting=[dict(id='lamp',name='Lamp',kind='unknown',source_ids=['lamp-sign'],evidence='Original symbol')],drawing_objects=[dict(id='rug',name='Rug',layer='decoration',category='rug',source_ids=['rug-sign'],evidence='Confirmed rug')],handoff=dict(requirements=[dict(id='r',target_ids=['room'],kind='material',text='Keep wood floor',source_ids=['note'])],dimensions=[dict(dimension_id='dim',target_ids=['counter'],status='matched',reason='Same endpoints')]))
    return source,c


@pytest.mark.parametrize('offset',[(0,0),(31,-19)])
def test_source_references_and_unknown_fixture_height_are_portable(offset):
    site,candidate=sample(*offset);baseline=copy.deepcopy(candidate)
    assert validate_handoff(site,candidate)==[]
    items=handoff_items(site,candidate)
    assert len(items)==2
    lamp,rug=items
    assert lamp['editor_kind']=='lighting' and lamp['category']=='unknown'
    assert lamp['dimension_source']=='estimated' and rug['height']==.02
    assert lamp['points'][0]==[2+offset[0],3+offset[1]]
    assert baseline['elements']==candidate['elements']


def test_requirements_can_target_equipment_child_but_not_unknown_ids():
    s,c=sample();c['handoff']['parts']=[dict(id='sink',parent_id='counter',name='Sink',category='sink',points=[[2,1],[3,1],[3,1.6],[2,1.6]],source_ids=['counter-edge'],evidence='Source basin')]
    c['handoff']['requirements'][0]['target_ids']=['sink']
    assert validate_handoff(s,c)==[]
    c['handoff']['parts'][0]['points']=[[20,1],[21,1],[21,2],[20,2]]
    assert any('超出原家具' in e for e in validate_handoff(s,c))


def test_wrong_dimension_binding_and_missing_requirements_are_not_silently_accepted():
    s,c=sample();s['dimensions'][0]['start']=[25,20]
    assert any('端點' in e for e in validate_handoff(s,c))
    c['handoff']['requirements']=[];c['handoff']['text_dispositions']={'note':'Just text'}
    assert any('明確設計要求' in e for e in validate_handoff(s,c))


def test_symbol_requirements_and_opening_controls_compile_without_adopting():
    s,c=sample();c['handoff']['parts']=[dict(id='sink',parent_id='counter',name='Sink',category='sink',points=[[2,1],[3,1],[3,1.6],[2,1.6]],source_ids=['counter-edge'],evidence='Source basin')]
    assert not validate_handoff(s,c)
    parsed=dict(features=[dict(id='counter',intake_metadata=dict(semantic_id='counter',category='kitchen'))],intake_semantics=dict(handoff=c['handoff'],id_map={'counter':'counter'},source_origin=[10,20]))
    active=[dict(id='counter',name='Counter',role='furniture',room_id='room')];baseline=copy.deepcopy(parsed)
    result=compile_handoff(active,parsed,[9,19]);assert parsed==baseline
    assert active[1]['points'][0]==[3,2]
    assert active[1]['parent_assembly_id']=='counter'
    assert result['requirements'][0]['text']=='Keep wood floor'


def test_preview_package_cannot_be_adopted_even_if_completed(tmp_path):
    from interior.workbench.studio.service import Studio
    from interior.workbench.storage import write_json
    studio=object.__new__(Studio);studio.jobs=Mock();studio.store=Mock();studio.store.state_dir=tmp_path
    studio.jobs.get.return_value=dict(project_id='NEW',operation='studio.prepare',status='completed',id='job')
    studio.current=lambda p:dict(revision=None,scene=None)
    write_json(tmp_path/'jobs/job/request.json',dict(parameters=dict(source=dict(preview_only=True))))
    with pytest.raises(ValueError,match='未採用平面'):studio.adopt_import('NEW','job')


def test_source_lintel_is_not_stretched_into_a_doorway():
    from interior.workbench.studio.plan_import import check_plan
    features=[dict(id='floor',points=[[0,0],[5,0],[5,4],[0,4]],closed=True),dict(id='header',points=[[1,0],[2,0]],closed=False,source_geometry={'method':'portal'}),dict(id='door',points=[[1,0],[2,0]],closed=False,source_geometry={'method':'between'})]
    for f in features:f.update(layer='floor' if f['id']=='floor' else 'wall',kind='SEMANTIC')
    settings=dict(units='m',assignments=[dict(id='floor',name='Floor',role='floor',height=.1),dict(id='header',name='Lintel',role='wall',base=2.1,height=.7),dict(id='door',name='Door',role='door',height=2.1,host_id='header')])
    parsed=dict(features=features,issues=[])
    result=check_plan(parsed,settings)
    assert not result['errors'] and next(i for i in result['items'] if i['id']=='door')['host_lintel']
    assert next(i for i in result['items'] if i['id']=='header')['base']==2.1
    settings['assignments'][1]['base']=2.0
    assert any('開口超出' in e for e in check_plan(parsed,settings)['errors'])


def test_private_preview_keeps_original_revision_and_review_flags(system):
    from test_plan_semantics import candidate,validate
    from interior.workbench.studio.plan_handoff import private_packet
    from interior.workbench.studio.plan_import import check_plan
    studio,plans,packet,site=system
    raw=candidate(site);source=site['geometry'][0]['id']
    raw['handoff']=dict(openings=[dict(element_id=e['id'],kind='single' if e['role']=='door' else 'window',source_ids=e['source_ids'],evidence='Source opening') for e in raw['elements'] if e['role'] in ('door','window')],requirements=[dict(id='room-use',target_ids=['living'],kind='use',text='Living room',source_ids=[site['texts'][0]['id']])])
    c,r=validate(site,raw);assert not r['repair_errors']
    original=copy.deepcopy(packet)
    private=private_packet(packet,site,c,'a'*32)
    assert packet==original and plans.current('UNRELATED',packet['id'])['revision']==packet['revision']
    assert private['preview_only'] and not any(private['settings']['intake_review'].values())
    check=check_plan(private['parsed'],private['settings']);assert not check['errors']
    assert len(check['handoff']['requirements'])==1 and check['intake']['status']=='blocked'


def test_compiled_vertical_confirmation_is_not_reset_to_concept():
    parsed=dict(features=[dict(id='window',intake_metadata=dict(semantic_id='w',confirmed_dimensions={'height':1.5,'base':1.04}))])
    active=[dict(id='window',height=1.5,base=1.04)]
    compile_handoff(active,parsed,[0,0])
    assert active[0]['intake_metadata']['dimension_sources']['height']=='user_confirmed'
    assert active[0]['intake_metadata']['dimension_sources']['base']=='user_confirmed'
    active=[dict(id='window',height=1.3,base=1.)]
    compile_handoff(active,parsed,[0,0])
    assert active[0]['intake_metadata']['dimension_sources']['height']=='concept'


def test_beam_reference_never_becomes_a_floor_furniture_block():
    site,proposal=sample()
    proposal['drawing_objects'].append(dict(id='beam',name='Ceiling beam',layer='other',category='beam',source_ids=['counter-edge'],evidence='User confirmed beam; elevation unknown'))
    assert not any(item['id']=='beam' for item in handoff_items(site,proposal))
