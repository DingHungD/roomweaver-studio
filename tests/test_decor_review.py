"""Automatic decor keeps semantic identity separate from the support's name."""
import copy
from unittest.mock import patch
import pytest
from interior.workbench.studio.asset_quality import requirements,assess
from interior.workbench.studio.staging import restore_decor_identity
from interior.workbench.studio.decor_review import run_review
from interior.workbench.storage import read_json,write_json

@pytest.mark.parametrize('purpose,host,size',[('vase','table',[.18,.18,.3]),('books','desk',[.24,.18,.08]),('tableware','sink',[.22,.22,.1])])
def test_identity_survives_support_names_and_replacement(purpose,host,size):
    context=dict(group=dict(name=host+' supporting item'),concept=dict(asset=purpose),dimensions_metres=size)
    assert requirements(context)['purpose']==purpose
    context['group']['decor_context']=dict(purpose=purpose)
    context['concept']=None
    assert requirements(context)['purpose']==purpose
    assert assess(context,dict(name=host),'model')['status']=='blocked'
    assert assess(context,dict(name='Book' if purpose=='books' else purpose),'model')['status']=='eligible'
    context['group']['asset_requirements']=dict(purpose='plant',dimension_source='confirmed',dimensions=size,evidence='user')
    assert requirements(context)['purpose']=='plant' and requirements(context)['dimension_source']=='confirmed'

def test_only_proven_automatic_wrong_identity_is_migrated():
    scene=dict(groups=[dict(id='decor',deleted=False,generated_reference=dict(task_id='task'),asset_requirements=dict(purpose='sink',dimension_source='estimated',dimensions=[.2,.2,.1],evidence=''))])
    proposal=dict(id='a'*32,items=[dict(id='decor',furniture=dict(asset='tableware'),support_id='sink')])
    previous=dict(items=[dict(task_id='task')]);confirmed=copy.deepcopy(scene)
    confirmed['groups'][0]['asset_requirements'].update(dimension_source='confirmed',evidence='user')
    assert restore_decor_identity(scene,proposal,previous)=={'decor'}
    assert scene['groups'][0]['asset_requirements']['purpose']=='tableware'
    assert not restore_decor_identity(confirmed,proposal,previous)
    assert confirmed['groups'][0]['asset_requirements']['purpose']=='sink'

def test_empty_new_preview_keeps_adopted_results_accessible(tmp_path):
    from test_asset_matching import environment
    from test_asset_batch import BatchAgents
    from interior.workbench.studio.asset_matching import AssetMatching
    from interior.workbench.studio.asset_batch import AssetBatch
    from interior.workbench.studio.staging import Staging
    studio,jobs,first=environment(tmp_path)
    try:
        service=Staging(studio,AssetBatch(AssetMatching(studio,BatchAgents())))
        folder=service.folder('ASSETS');old='a'*32;new='b'*32
        write_json(folder/old/'proposal.json',dict(id=old,kind='decor',items=[dict(id=first['scene']['groups'][0]['id'])]))
        write_json(folder/old/'adoption.json',dict(selected_ids=[first['scene']['groups'][0]['id']]))
        write_json(folder/new/'proposal.json',dict(id=new,kind='decor',items=[]))
        write_json(folder/'decor-current.json',dict(id=new))
        assert service.current('ASSETS','decor')['id']==old
        assert read_json(folder/'decor-current.json')['id']==new
    finally:jobs.close()

def test_review_uses_actual_images_and_does_not_promote_task_success(tmp_path):
    images=[tmp_path/n for n in ('object.png','context.png')]
    for p in images:p.write_bytes(b'synthetic')
    class Client:
        def run(self,prompt,**kwargs):
            assert kwargs['images']==images
            return dict(text='{"status":"retry","issues":["purpose"],"reason":"這是水槽，不是餐具"}')
    result=run_review(Client(),tmp_path,dict(job_id='job',images=images),'same-model',lambda _:None,None)
    assert result['verdict']['status']=='retry' and len(result['image_hashes'])==2
    images[0].unlink()
    with pytest.raises(ValueError,match='預覽'):run_review(Client(),tmp_path,dict(images=images),None,lambda _:None,None)

@pytest.mark.parametrize('verdict,expected',[('pass','pass'),('retry','retry'),('uncertain','pause')])
def test_review_gate_is_job_bound_replayable_and_never_adopts_on_failure(tmp_path,verdict,expected):
    from test_asset_automation import setup
    studio,jobs,first,batch,identifier,payload=setup(tmp_path)
    try:
        runner=batch.automation;target=payload['targets'][0];path=runner.path('ASSETS',identifier);state=read_json(path)
        job=jobs.submit_studio('ASSETS','replace',dict(revision=first['revision']),'decor-review-test')
        folder=studio.root('ASSETS')/job['output'];folder.mkdir(parents=True,exist_ok=True)
        import hashlib
        hashes={}
        for name in ('decor-object.png','decor-context.png'):
            (folder/name).write_bytes(b'test preview');hashes[name]=hashlib.sha256(b'test preview').hexdigest()
        write_json(folder/'replacement-report.json',dict(support=dict(status='passed'),visual_review=dict(images=['decor-object.png','decor-context.png'])))
        row=dict(status='applying',job_id=job['id'],asset_id='candidate',attempts=[]);state['items'][target['task_id']]=row
        assert runner.review('ASSETS',identifier,target,row,state,path,job,payload)=='pending'
        task=row['review_task_id'];batch.agents.tasks[task].update(status='passed',job_id=job['id'],image_hashes=hashes,verdict=dict(status=verdict,issues=[] if verdict=='pass' else ['purpose'],reason='test review'))
        with patch.object(runner.assets,'adopt') as adopt:
            assert runner.review('ASSETS',identifier,target,row,state,path,job,payload)==expected
            adopt.assert_not_called()
        assert studio.current('ASSETS')['revision']==first['revision']
        if verdict=='retry':assert not row.get('job_id') and len(row['attempts'])==1
        if verdict=='pass':
            assert runner.review('ASSETS',identifier,target,row,state,path,job,payload)=='pass'
            assert row['review_task_id']==task
            (folder/'decor-object.png').write_bytes(b'changed')
            assert runner.review('ASSETS',identifier,target,row,state,path,job,payload)=='pause'
    finally:jobs.close()
