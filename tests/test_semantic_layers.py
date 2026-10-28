"""Semantic display groups preserve source geometry and never configure a scene."""
import copy

import pytest

from test_plan_semantics import system,candidate
from interior.workbench.studio.semantic_layers import furniture_category,review_layers,category_layer
from interior.workbench.studio.semantic_layers import object_details
from interior.workbench.studio.plan_semantics import validate,prompt


@pytest.mark.parametrize('name,asset,category,layer',[
    ('電視矮櫃','cabinet','cabinet','furniture'),('Chair','chair','chair','furniture'),
    ('馬桶',None,'toilet','equipment'),('連續廚具','cooker','kitchen','equipment'),
    ('冰箱',None,'appliance','equipment'),('窗簾',None,'curtain','decoration'),
    ('植栽',None,'plant','decoration'),('地毯',None,'rug','decoration'),
    ('掛畫',None,'art','decoration'),('空調',None,'air_conditioner','equipment'),
    ('Unidentified symbol',None,'other','other')])
def test_category_is_not_raw_layer_or_fragment_count(name,asset,category,layer):
    item=dict(name=name,asset=asset)
    assert furniture_category(item)==category and category_layer(category)==layer
    item['category']='table'
    assert furniture_category(item)=='table'


def test_source_fragments_stay_one_object_and_unknown_lighting_not_claimed(system):
    _,_,_,site=system;raw=candidate(site)
    site=copy.deepcopy(site);site['texts'].append(dict(id='light-note',text='廊道需要有崁燈',point=[3,4]))
    before=copy.deepcopy((site,raw))
    normalized,report=validate(site,raw)
    layers=report['layers'];items=layers['items']
    assert len([i for i in items if i['layer']=='furniture'])==1
    assert len([i for i in items if i['layer']=='floors'])==1
    assert not layers['lighting_reviewed']
    note=next(i for i in items if i['layer']=='lighting')
    assert note['status']=='annotation' and note['points']==[[3,4]] and '文字位置' in note['evidence']
    assert (site,raw)==before
    assert report['counts']==dict(wall=1,door=1,window=1,furniture=1)
    assert 'drawing_objects' in prompt(site)


def test_object_defaults_are_local_readonly_and_not_claimed_confirmed(system):
    _,_,_,site=system;raw=candidate(site);raw['assumptions']=['desk height is conceptual','Unrelated bedroom note']
    original=copy.deepcopy(raw);_,report=validate(site,raw)
    desk=next(i for i in report['layers']['items'] if i['id']=='desk')
    assert desk['evidence']=='Source drawing'
    assert desk['details']['notes']==['desk height is conceptual']
    assert {p['key'] for p in desk['details']['parameters']}=={'height','base'}
    assert all(p['status']=='unconfirmed' for p in desk['details']['parameters'])
    assert raw==original
    wall=dict(name='wall',role='wall',height=2.8,base=0,thickness=.18,derivation={'method':'pair'})
    assert object_details(wall,[])['parameters'][-1]['status']=='derived'
    wall['derivation']={'method':'outline'}
    assert object_details(wall,[])['parameters'][-1]['status']=='unconfirmed'


@pytest.mark.parametrize('offset',[(0,0),(-18,22)])
def test_lamps_and_decorations_use_original_graphics_on_different_sources(system,offset):
    _,_,_,site=system;site=copy.deepcopy(site);raw=candidate(site)
    a,b=[offset[0]+1,offset[1]+1],[offset[0]+3,offset[1]+1]
    site['geometry'].extend([dict(id='track',points=[a,b],closed=False),dict(id='plant',points=[a,b,[b[0],b[1]+1]],closed=True)])
    raw['lighting']=[dict(id='lamp',name='Track light',kind='track',source_ids=['track'],evidence='Native track symbol')]
    raw['drawing_objects']=[dict(id='plant',name='Plant',layer='decoration',category='plant',source_ids=['plant'],evidence='Native planter symbol')]
    before=copy.deepcopy((site,raw));layers=review_layers(site,raw)
    lamp=next(i for i in layers['items'] if i['id']=='light:lamp')
    decor=next(i for i in layers['items'] if i['id']=='drawing:plant')
    assert lamp['points']==[a,b] and lamp['strokes'][0]['points']==[a,b]
    assert decor['layer']=='decoration' and decor['strokes'][0]['closed']
    assert (site,raw)==before and layers['lighting_reviewed']


def test_unknown_light_ids_or_only_label_cannot_become_a_fixture(system):
    _,_,_,site=system;raw=candidate(site)
    raw['lighting']=[dict(id='lamp',name='Lamp',kind='unknown',source_ids=['invented'],evidence='Unproven')]
    with pytest.raises(ValueError,match='不存在'):validate(site,raw)
    raw['lighting'][0]['source_ids']=[site['texts'][0]['id']]
    with pytest.raises(ValueError,match='只有文字'):validate(site,raw)


def test_floor_parts_are_one_display_group_and_holes_are_retained():
    site=dict(geometry=[],texts=[],floors=[dict(id='a',points=[[0,0],[2,0],[2,2],[0,2]],holes=[[[.5,.5],[1,.5],[1,1],[.5,1]]]),dict(id='b',points=[[2,0],[4,0],[4,2],[2,2]])])
    items=review_layers(site,dict(rooms=[],elements=[]))['items']
    assert len(items)==1 and items[0]['status']=='reference'
    assert len(items[0]['areas'])==2 and items[0]['areas'][0]['holes']==site['floors'][0]['holes']


def test_unsupported_or_misclassified_extra_symbols_cannot_be_claimed():
    site=dict(geometry=[dict(id='g',points=[[0,0],[1,0]],closed=False)],texts=[],floors=[])
    obj=dict(id='x',name='Plant',layer='equipment',category='plant',source_ids=['g'],evidence='Source symbol')
    proposal=dict(rooms=[],elements=[],drawing_objects=[obj])
    with pytest.raises(ValueError,match='分層不一致'):review_layers(site,proposal)
    obj['layer']='decoration';obj['source_ids']=['invented']
    with pytest.raises(ValueError,match='不存在'):review_layers(site,proposal)


def test_confirmed_vertical_detail_is_host_bound_and_exact():
    item=dict(name='Window',role='window',height=1.5,base=1.04)
    confirmed={'height':{'before':1.3,'after':1.5}}
    rows=object_details(item,[],confirmed)['parameters']
    assert rows[0]['status']=='confirmed' and rows[1]['status']=='unconfirmed'
    assert object_details(dict(item,height=1.4),[],confirmed)['parameters'][0]['status']=='unconfirmed'
