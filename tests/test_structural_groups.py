"""Import grouping and shared material scope, independent of any customer case."""
import copy
import json
import struct
import pytest
from interior.workbench.studio.grouping import assembly_groups, regroup_structure
from interior.workbench.studio.asset_batch import select_targets, BatchRequest
from interior.workbench.studio.asset_matching import object_context, target_reference


def fixture(tmp_path):
    specs=[('wall-north__body','wall-north','wall'),('wall-south__body','wall-south','wall'),
           ('floor-a__surface','floor-a','floor'),('floor-b__surface','floor-b','floor'),
           ('Sofa__seat','sofa-one','furniture'),('Sofa__arm','sofa-one','furniture'),
           ('Bed__frame','bed-one','furniture'),('Bed__mattress','bed-one','furniture'),
           ('Chair1__seat','chair-one','furniture'),('Chair2__seat','chair-two','furniture'),
           ('floor_lamp__shade','floor_lamp','furniture'),('wall-cabinet__door','wall-cabinet','furniture')]
    objects=[dict(id=str(i),name=n,room_id='living' if i%2==0 else 'bedroom',material={}) for i,(n,_,_) in enumerate(specs)]
    nodes=[dict(name=n,mesh=i,extras=dict(studio_id=str(i),assembly_id=a,studio_role=r)) for i,(n,a,r) in enumerate(specs)]
    raw=json.dumps(dict(nodes=nodes)).encode();raw+=b' '*((-len(raw))%4)
    path=tmp_path/'fixture.glb';path.write_bytes(struct.pack('<IIIII',0x46546c67,2,20+len(raw),len(raw),0x4e4f534a)+raw)
    groups=assembly_groups(objects,path)
    return dict(objects=objects,groups=groups,rooms=[dict(id=x,name=x) for x in ('living','bedroom')]),path


def test_structure_groups_and_independent_furniture(tmp_path):
    scene,path=fixture(tmp_path)
    assert [g['children'] for g in scene['groups']]==[['0','1'],['2','3'],['4','5'],['6','7'],['8'],['9'],['10'],['11']]
    assert assembly_groups(scene['objects'],path)==scene['groups']
    # Conservative legacy GLB names: lamps and cabinets must never become structure.
    legacy=assembly_groups(scene['objects'],tmp_path/'absent.glb')
    assert [g['children'] for g in legacy[:2]]==[['0','1'],['2','3']]
    assert all('10' not in g['children'] and '11' not in g['children'] for g in legacy if g['method'].startswith('structural_'))


def test_one_search_per_group_and_room_scope_does_not_paint_other_room(tmp_path):
    scene,_=fixture(tmp_path)
    request=BatchRequest(base_revision='a'*32,operation_id='scope-test')
    whole=select_targets(scene,request)
    assert len(whole)==8
    wall=next(t for t in whole if t['category']=='wall')
    assert wall['object_id'] is None and wall['object_ids']==['0','1']
    room=select_targets(scene,request.model_copy(update={'room_ids':['living'],'categories':['wall','floor']}))
    assert [t['object_ids'] for t in room]==[['0'],['2']]
    c=object_context(scene,wall['group_id'],object_ids=['0'])
    assert [o['id'] for o in c['parts']]==['0']
    for ids in ([],['0','0'],['4'],['unknown']):
        with pytest.raises(ValueError):object_context(scene,wall['group_id'],object_ids=ids)
    ref=dict(task_id='x',status='applied')
    scene['objects'][0]['material']['asset_reference']=ref
    assert target_reference(scene,wall) is None
    scene['objects'][1]['material']['asset_reference']=ref
    assert target_reference(scene,wall)==ref
    assert target_reference(scene,dict(wall,object_ids=['0']))==ref


def test_legacy_regroup_preserves_parts_materials_and_bound_light(tmp_path):
    scene,_=fixture(tmp_path);imported=copy.deepcopy(scene['groups'])
    wall=scene['groups'].pop(0)
    scene['groups'][:0]=[dict(wall,id='old-'+c,children=[c],method='individual') for c in wall['children']]
    scene['lighting_setup']=dict(lights=[dict(group_id='old-1')])
    scene['objects'][0]['material']=dict(color='#123456')
    before=copy.deepcopy(scene)
    merged,report=regroup_structure(scene,imported)
    assert scene==before and merged['objects']==before['objects']
    assert merged['groups'][0]['children']==['0','1']
    assert merged['lighting_setup']['lights'][0]['group_id']=='old-0'
    assert regroup_structure(merged,imported)[0]==merged
    scene['groups'][1]['translation']=[1,0,0]
    with pytest.raises(ValueError,match='位移'):regroup_structure(scene,imported)
    assert report[0]['previous']==2


def test_repeated_source_id_in_separate_furniture_instances(tmp_path):
    nodes=[dict(name='scene',children=[1,4]),dict(name='Chair',children=[2,3]),
           dict(name='seat',extras=dict(studio_id='a',source_id='chair')),
           dict(name='leg',extras=dict(studio_id='b',source_id='chair')),
           dict(name='Chair.001',children=[5,6]),
           dict(name='seat.001',extras=dict(studio_id='c',source_id='chair')),
           dict(name='leg.001',extras=dict(studio_id='d',source_id='chair'))]
    raw=json.dumps(dict(nodes=nodes)).encode();raw+=b' '*((-len(raw))%4)
    path=tmp_path/'instances.glb';path.write_bytes(struct.pack('<IIIII',0x46546c67,2,20+len(raw),len(raw),0x4e4f534a)+raw)
    objs=[dict(id=n['extras']['studio_id'],name=n['name']) for n in nodes if 'extras' in n]
    assert [g['children'] for g in assembly_groups(objs,path)]==[['a','b'],['c','d']]


def test_lighting_and_decor_still_see_separate_structural_supports(tmp_path):
    from interior.workbench.studio.staging import geometry_scene, propose, StageRequest
    scene,_=fixture(tmp_path);before=copy.deepcopy(scene)
    geometry=geometry_scene(scene)
    assert scene==before
    structures=[g for g in geometry['groups'] if g['method'].startswith('structural_')]
    assert len(structures)==4 and all(len(g['children'])==1 for g in structures)
    # Floors are separate supports; walls around the room are not one solid box.
    bounds={g['id']:([0,0,-.1],[3,3,0]) if g['children']==['2'] else
            ([4,0,-.1],[7,3,0]) if g['children']==['3'] else
            ([-.1,-.1,0],[7.1,0,2.7]) if g['children']==['0'] else
            ([-.1,3,0],[7.1,3.1,2.7]) for g in structures}
    result=propose(geometry,bounds,StageRequest(base_revision='a'*32,operation_id='lights-test',kind='lighting'))
    assert len(result['items'])==2
    assert {i['room_id'] for i in result['items']}=={'living','bedroom'}


def test_group_candidate_reference_replacement_and_partial_provenance(tmp_path):
    from test_asset_matching import environment, raw, FREE
    from test_asset_batch import BatchAgents
    from interior.workbench.studio.asset_batch import AssetBatch
    from interior.workbench.studio.asset_matching import AssetMatching, SelectAsset
    from interior.workbench.studio.blenderkit_client import normalize
    from interior.workbench.storage import read_json, write_json, Conflict
    studio,jobs,first=environment(tmp_path)
    try:
        scene=copy.deepcopy(first['scene']);scene['groups']=[]
        scene['objects'].append(dict(id='wall2',name='Wall north',room_id='living',material={}))
        write_json(studio.root('ASSETS')/'runs/interior-studio'/scene['model_id']/'model.json',dict(objects=scene['objects']))
        saved=studio.save('ASSETS',scene,first['revision'])
        agents=BatchAgents();assets=AssetMatching(studio,agents);batch=AssetBatch(assets)
        request=BatchRequest(base_revision=saved['revision'],operation_id='group-material',auto_apply=False,categories=['wall'])
        result=batch.start('ASSETS',request)
        assert len(result['items'])==1 and result['items'][0]['object_ids']==['wall','wall2']
        target=read_json(batch.folder('ASSETS')/result['id']/'input.json')['targets'][0]
        assert len(target['context']['parts'])==2
        candidate=normalize(raw());candidate['kind']='material'
        write_json(assets.folder('ASSETS')/target['task_id']/'result.json',dict(status='passed',candidates=[candidate]))
        selection=SelectAsset(base_revision=saved['revision'],operation_id='replace-group',asset_id=FREE,accept_license=True)
        linked=assets.reference('ASSETS',target['task_id'],selection)
        assert all(o['material']['asset_reference'] for o in linked['scene']['objects'] if o['id'].startswith('wall'))
        assert not next(o for o in linked['scene']['objects'] if o['id']=='sofa')['material']['asset_reference']
        selection.base_revision=linked['revision']
        job=assets.replace('ASSETS',target['task_id'],selection)
        assert assets.replace('ASSETS',target['task_id'],selection)['id']==job['id']
        payload=read_json(studio.store.state_dir/'jobs'/job['id']/'request.json')['parameters']
        assert payload['object_ids']==['wall','wall2'] and payload['object_id'] is None
        # One applied member is not proof that an entire scope was replaced.
        changed=copy.deepcopy(linked['scene'])
        changed['objects'][0]['material']['asset_reference']['status']='applied'
        changed['objects'][0]['material']['color']='#abcdef'
        revised=studio.save('ASSETS',changed,linked['revision']);selection.base_revision=revised['revision']
        with pytest.raises(Conflict):assets.candidate('ASSETS',target['task_id'],selection)
    finally:jobs.close()


def test_regroup_is_revision_bound_and_keeps_history(tmp_path):
    from test_asset_matching import environment
    from interior.workbench.storage import write_json, Conflict
    studio,jobs,first=environment(tmp_path)
    try:
        scene=copy.deepcopy(first['scene'])
        scene['objects'].append(dict(id='wall2',name='Wall north',room_id='living',material={}))
        scene['groups'].append(dict(scene['groups'][0],id='old-wall2',children=['wall2'],method='individual',name='Wall north'))
        write_json(studio.root('ASSETS')/'runs/interior-studio'/scene['model_id']/'model.json',dict(objects=scene['objects']))
        old=studio.save('ASSETS',scene,first['revision'])
        new=studio.regroup('ASSETS',old['revision'])
        assert len(new['scene']['groups'])==2 and len(studio.revision('ASSETS',old['revision'])['scene']['groups'])==3
        assert studio.regroup('ASSETS',new['revision'])['revision']==new['revision']
        with pytest.raises(Conflict):studio.regroup('ASSETS',old['revision'])
    finally:jobs.close()
