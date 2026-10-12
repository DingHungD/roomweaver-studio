"""House scope, independent styles, interruption and storage reclamation contracts."""
import copy
import io
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from interior.workbench.studio.asset_batch import BatchRequest, AssetBatch, select_targets, run_batch
from interior.workbench.studio.asset_matching import AssetMatching, MatchRequest, SelectAsset
from interior.workbench.studio.asset_storage import clean_replacements, source_history
from interior.workbench.storage import write_json, read_json, Conflict
from test_asset_matching import environment, FakeAgents, FREE

def request(first,**kwargs):
    return BatchRequest(base_revision=first['revision'],operation_id='batch-test-one',auto_apply=False,**kwargs)

def test_house_room_type_and_individual_style_controls(tmp_path):
    studio,jobs,first=environment(tmp_path)
    try:
        scene=first['scene'];gid=scene['groups'][0]['id'];image='a'*64;own='b'*64
        all_targets=select_targets(scene,request(first,description='global oak',image_id=image))
        assert len(all_targets)==2 and {x['kind'] for x in all_targets}=={'material','model'}
        room=select_targets(scene,request(first,room_ids=['living']))
        assert len(room)==1 and room[0]['category']=='wall'
        assert select_targets(scene,request(first,categories=['sofa']))[0]['category']=='sofa'
        custom=select_targets(scene,request(first,description='global',image_id=image,
            overrides={gid:dict(use_global=False,description='local style',image_id=own)}))
        target=next(x for x in custom if x['group_id']==gid)
        assert target['description']=='local style' and target['image_ids']==[own]
        assert all(not x['image_ids'] for x in select_targets(scene,request(first,use_global=False,image_id=image)))
        with pytest.raises(ValueError,match='物件已變更'):select_targets(scene,request(first,overrides={'unknown':{}}))
        with pytest.raises(ValueError,match='没有|沒有'):select_targets(scene,request(first,categories=['bed']))
    finally:jobs.close()

class BatchAgents(FakeAgents):
    def get(self,identifier):
        if identifier not in self.tasks:raise FileNotFoundError(identifier)
        return super().get(identifier)
    def start(self,kind,model,payload,identifier):
        self.calls+=1;self.tasks[identifier]=dict(id=identifier,status='queued')

def test_batch_dedup_image_is_sanitized_and_interrupted_targets_are_honest(tmp_path):
    studio,jobs,first=environment(tmp_path)
    try:
        agents=BatchAgents();batch=AssetBatch(AssetMatching(studio,agents))
        out=io.BytesIO();Image.new('RGB',(30,20),'tan').save(out,format='PNG')
        image=batch.upload('ASSETS',out.getvalue())['id']
        assert Image.open(batch.image('ASSETS',image)).format=='JPEG'
        b=request(first,image_id=image)
        task=batch.start('ASSETS',b)
        assert batch.start('ASSETS',b)['id']==task['id'] and agents.calls==1
        with pytest.raises(Conflict):batch.start('ASSETS',b.model_copy(update={'description':'different'}))
        with pytest.raises(Conflict,match='已有'):batch.start('ASSETS',b.model_copy(update={'operation_id':'different-batch'}))
        agents.tasks[task['id']]['status']='interrupted'
        assert all(x['status']=='interrupted' for x in batch.current('ASSETS')['items'])
        with pytest.raises(ValueError):batch.upload('ASSETS',b'invalid image')
        with pytest.raises(ValueError):batch.image('ASSETS','../private')
    finally:jobs.close()

def test_one_failed_target_does_not_drop_others_and_images_are_forwarded(tmp_path):
    targets=[dict(task_id=str(i),name='chair',result_path=str(tmp_path/str(i)/'result.json'),images=['reference.jpg']) for i in range(2)]
    for t in targets:Path(t['result_path']).parent.mkdir()
    calls=[]
    def match(client,directory,target,*args):
        calls.append(target)
        if target['task_id']=='0':raise ValueError('synthetic candidate failure')
        return dict(candidates=[{'asset_id':FREE}])
    with patch('interior.workbench.studio.asset_batch.run_matching',side_effect=match):
        result=run_batch(None,tmp_path,dict(targets=targets),'test',lambda x:None,lambda x:None)
    assert len(result['completed'])==2 and calls[0]['images']==['reference.jpg']
    assert read_json(Path(targets[0]['result_path']))['status']=='failed'
    assert read_json(Path(targets[1]['result_path']))['status']=='passed'

def test_storage_reclaims_only_superseded_replacements_blocks_old_replay_and_keeps_sources(tmp_path):
    studio,jobs,first=environment(tmp_path)
    try:
        root=studio.root('ASSETS');original=first['scene']['model_id']
        (root/'runs/interior-studio'/original/'model.blend').write_bytes(b'original')
        def replacement(before):
            job=jobs.submit_studio('ASSETS','replace',dict(revision=before['revision']),f"new-{before['revision']}")
            folder=root/job['output'];folder.mkdir(parents=True)
            scene=copy.deepcopy(before['scene']);scene['model_id']=job['id']
            write_json(folder/'model.json',dict(objects=scene['objects'],ancestor_model_ids=[before['scene']['model_id'],original]))
            for file in ('asset.blend','source.glb','model.blend','model.glb'): (folder/file).write_bytes(b'dummy')
            job['status']='completed';jobs.write(job)
            return studio.save('ASSETS',scene,before['revision']),folder
        second,old=replacement(first);third,current=replacement(second)
        pending=jobs.submit_studio('ASSETS','render',dict(revision=second['revision']),'pending-render')
        assert clean_replacements(studio,'ASSETS',third['revision'])['status']=='deferred'
        assert (old/'model.blend').exists()
        pending['status']='completed';jobs.write(pending)
        report=clean_replacements(studio,'ASSETS',third['revision'])
        assert report['bytes_freed']==30 and not (old/'model.blend').exists()
        assert (old/'model-retired.json').exists() and (old/'model.json').exists()
        assert (current/'model.blend').exists() and not (current/'asset.blend').exists()
        assert (root/'runs/interior-studio'/original/'model.blend').read_bytes()==b'original'
        assert clean_replacements(studio,'ASSETS',third['revision'])['bytes_freed']==0
        with pytest.raises(Conflict,match='釋放'):studio.save('ASSETS',second['scene'],third['revision'])
        with pytest.raises(ValueError,match='釋放'):jobs.submit_studio('ASSETS','render',dict(revision=second['revision']),'old-model-replay')
    finally:jobs.close()

def test_batch_candidate_survives_replacement_of_different_group_in_same_lineage(tmp_path):
    studio,jobs,first=environment(tmp_path)
    try:
        service=AssetMatching(studio,FakeAgents());gid=first['scene']['groups'][0]['id']
        task=service.start('ASSETS',MatchRequest(base_revision=first['revision'],group_id=gid,operation_id='matching-target'))
        scene=copy.deepcopy(first['scene']);scene['model_id']='e'*32
        write_json(studio.root('ASSETS')/'runs/interior-studio'/scene['model_id']/'model.json',dict(objects=scene['objects'],ancestor_model_ids=[first['scene']['model_id']]))
        saved=studio.save('ASSETS',scene,first['revision'])
        selected=SelectAsset(base_revision=saved['revision'],asset_id=FREE,operation_id='ref-target')
        referenced=service.reference('ASSETS',task['id'],selected)
        assert source_history(studio,'ASSETS',gid)[0]['asset_id']==FREE
        moved=copy.deepcopy(referenced['scene']);moved['groups'][0]['rotation']=90
        changed=studio.save('ASSETS',moved,referenced['revision']);selected.base_revision=changed['revision']
        with pytest.raises(Conflict):service.reference('ASSETS',task['id'],selected)
    finally:jobs.close()
