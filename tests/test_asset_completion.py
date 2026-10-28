"""An adopted manual alternative resolves an old failure, not a bare reference."""
from copy import deepcopy
from types import SimpleNamespace
from interior.workbench.storage import write_json
from interior.workbench.studio.asset_completion import adopted_completion, failure_details


def fixture(tmp_path):
    ref=dict(task_id='t'*32,asset_id='asset',status='applied')
    group=dict(id='lamp',children=['new'],asset_reference=ref)
    scene=dict(groups=[group],objects=[dict(id='new',material={})])
    target=dict(group_id='lamp',kind='model',context=dict(group=dict(id='lamp',children=['old']),parts=[]))
    folder=tmp_path/'assets';job='j'*32
    write_json(folder/ref['task_id']/'replacement.json',dict(job_id=job))
    write_json(tmp_path/'job/request.json',dict(target_group='lamp',task_id=ref['task_id'],asset={'asset_id':'asset'}))
    write_json(tmp_path/'job/replacement-scene.json',scene)
    write_json(tmp_path/'job/replacement-report.json',dict(model_check={'status':'passed'}))
    studio=SimpleNamespace(root=lambda p:tmp_path,jobs=SimpleNamespace(get=lambda k:dict(status='completed',project_id='P',operation='studio.replace',output='job')))
    return studio,folder,scene,target,[job]


def test_manual_success_resolves_waiting_but_not_preview_or_reference(tmp_path):
    studio,folder,scene,target,lineage=fixture(tmp_path)
    result=adopted_completion(studio,folder,'P',scene,target,lineage)
    assert result['status']=='installed' and not result['installation_verified']
    assert adopted_completion(studio,folder,'P',scene,target,[]) is None
    scene['groups'][0]['asset_reference']['status']='reference'
    assert adopted_completion(studio,folder,'P',scene,target,lineage) is None


def test_other_target_reverted_geometry_and_unverified_model_never_clear(tmp_path):
    studio,folder,scene,target,lineage=fixture(tmp_path)
    changed=deepcopy(scene);changed['groups'][0]['children']=['old']
    assert adopted_completion(studio,folder,'P',changed,target,lineage) is None
    request=tmp_path/'job/request.json'
    write_json(request,dict(target_group='other',task_id='t'*32,asset={'asset_id':'asset'}))
    assert adopted_completion(studio,folder,'P',scene,target,lineage) is None
    write_json(request,dict(target_group='lamp',task_id='t'*32,asset={'asset_id':'asset'}))
    write_json(tmp_path/'job/replacement-report.json',dict(model_check={'status':'blocked'}))
    assert adopted_completion(studio,folder,'P',scene,target,lineage) is None


def test_preexisting_source_is_not_a_new_success(tmp_path):
    studio,folder,scene,target,lineage=fixture(tmp_path)
    target['context']['group']=deepcopy(scene['groups'][0])
    assert adopted_completion(studio,folder,'P',scene,target,lineage) is None


def test_a_later_failed_alternative_does_not_make_an_adopted_model_unfinished(tmp_path):
    studio,folder,scene,target,lineage=fixture(tmp_path)
    write_json(folder/('t'*32)/'replacement.json',dict(job_id='failed-trial'))
    assert adopted_completion(studio,folder,'P',scene,target,lineage)['status']=='installed'


def test_all_material_members_must_be_applied_by_the_adopted_job(tmp_path):
    studio,folder,scene,target,lineage=fixture(tmp_path)
    ref=scene['groups'][0].pop('asset_reference')
    scene['groups'][0]['children']=['a','b']
    scene['objects']=[dict(id=i,material={'asset_reference':deepcopy(ref)}) for i in ('a','b')]
    target.update(kind='material',object_ids=['a','b'])
    target['context']['parts']=[dict(id=i,material={}) for i in ('a','b')]
    write_json(tmp_path/'job/request.json',dict(target_group='lamp',target_objects=['a','b'],task_id=ref['task_id'],asset={'asset_id':'asset'}))
    write_json(tmp_path/'job/replacement-scene.json',scene)
    assert adopted_completion(studio,folder,'P',scene,target,lineage)['status']=='installed'
    scene['objects'][1]['material']={}
    assert adopted_completion(studio,folder,'P',scene,target,lineage) is None


def test_failure_details_keep_actual_trial_and_rejected_candidate_reasons():
    details=failure_details(dict(error='已達上限',attempts=[dict(asset_id='light',error='發光面朝上')],rejected=[dict(name='wrong',reasons=['用途不符'])]))
    assert [d['reason'] for d in details]==['發光面朝上','用途不符']
    assert failure_details(dict(error='工具逾時'))[0]['reason']=='工具逾時'
