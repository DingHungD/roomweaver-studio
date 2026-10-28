"""Generic repair contracts, independent of project IDs and live Agent accounts."""
import copy
from pathlib import Path
import pytest
from interior.workbench.studio.models import Scene
from interior.workbench.studio.scene_repair import frame


def scene():
    return Scene.model_validate(dict(model_id='a'*32,rooms=[dict(id='room',name='Room')],objects=[dict(id='chair-part',name='chair')],groups=[dict(id='chair',name='chair',children=['chair-part'])],viewpoints=[dict(id='view',name='Room',room_id='room',eye=[1,1,1.6],shots=[dict(id='front',name='Front',yaw=0)])])).model_dump(mode='json')


def test_framing_preserves_tour_point_and_other_shots():
    original=scene();before=copy.deepcopy(original)
    proposal=dict(category='viewpoint',target_id='view',shot_id='front',values={'target_group_id':'chair'})
    facts=dict(framing=[dict(viewpoint_id='view',target_group_id='chair',eye=[0,-1,1.6],yaw=90,pitch=-20,lens=24)])
    result,_=frame(original,proposal,facts)
    assert original==before
    assert result['viewpoints'][0]['eye']==original['viewpoints'][0]['eye']
    assert result['viewpoints'][0]['shots'][0]['eye']==[0,-1,1.6]
    assert result['groups']==original['groups']
    proposal['values']['target_group_id']='missing'
    with pytest.raises(StopIteration):frame(original,proposal,facts)


def test_nonfinite_shot_position_rejected():
    data=scene();data['viewpoints'][0]['shots'][0]['eye']=[float('nan'),0,1]
    with pytest.raises(ValueError):Scene.model_validate(data)


def test_repair_preview_requires_completed_owning_job(tmp_path):
    from types import SimpleNamespace
    from interior.workbench.studio.service import Studio
    from interior.workbench.storage import write_json
    model='a'*32;owner='b'*32
    folder=tmp_path/'runs/interior-studio'/model
    write_json(folder/'model.json',dict(scene_review_owner=owner))
    (folder/'model.glb').write_bytes(b'fixture')
    job=dict(project_id='TEST',operation='studio.render',status='completed',output='runs/interior-studio/'+owner)
    write_json(tmp_path/job['output']/'scene-review-effective.json',dict(scene={'model_id':model}))
    def get(key):
        if key!=owner:raise FileNotFoundError()
        return job
    studio=SimpleNamespace(jobs=SimpleNamespace(get=get),root=lambda _:tmp_path)
    assert Studio.artifact(studio,'TEST',model,'model.glb')==folder/'model.glb'
    job['status']='running'
    with pytest.raises(FileNotFoundError):Studio.artifact(studio,'TEST',model,'model.glb')
    job['status']='completed';job['project_id']='OTHER'
    with pytest.raises(FileNotFoundError):Studio.artifact(studio,'TEST',model,'model.glb')
    with pytest.raises(FileNotFoundError):Studio.artifact(studio,'TEST',model,'../model.blend')
