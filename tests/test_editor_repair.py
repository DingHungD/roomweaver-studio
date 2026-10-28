import copy
import pytest
from interior.workbench.studio.editor_repair import protected
from interior.workbench.studio.fixture_installation import ceiling_fixture,FixturePlan
from interior.workbench.studio.viewpoint_repair import apply_plan

def baseline():
    return dict(manual_doors=[],rooms=[],door_controls=[dict(opening_id='door',side='positive',swing='negative',kind='single',assembly_width=.85,materials={'frame':{'color':'#aaa'}})],groups=[dict(id='desk',deleted=False,asset_requirements={'purpose':'desk','dimension_source':'confirmed','dimensions':[1.2,.6,.75]})],viewpoints=[dict(id='living',eye=[1,2,1.6],shots=[dict(id='front',name='正面',aspect='4:3',yaw=0,pitch=0,lens=24)])])

@pytest.mark.parametrize('key,value',[('side','negative'),('swing','positive'),('assembly_width',.9),('materials',{})])
def test_repair_cannot_change_confirmed_door(key,value):
    old=baseline();new=copy.deepcopy(old);new['door_controls'][0][key]=value
    with pytest.raises(ValueError):protected(old,new)

def test_required_furniture_and_confirmed_dimensions_cannot_be_removed_or_reclassified():
    old=baseline();new=copy.deepcopy(old);new['groups'][0]['deleted']=True
    with pytest.raises(ValueError):protected(old,new)
    new=copy.deepcopy(old);new['groups'][0]['asset_requirements']['dimension_source']='estimated'
    with pytest.raises(ValueError):protected(old,new)
    assert protected(old,copy.deepcopy(old)) is None

def test_fixture_identity_and_plan_cannot_claim_arbitrary_excavation():
    assert ceiling_fixture(dict(group=dict(name='天花燈具 · 地板'),concept=None))
    assert not ceiling_fixture(dict(group=dict(name='落地燈'),concept=dict(asset='floor_lamp')))
    with pytest.raises(ValueError):FixturePlan(mode='recessed',recess_depth=.5,reason='unsafe')
    assert FixturePlan(mode='surface',recess_depth=0,reason='吸頂沒有凹槽').recess_depth==0
    with pytest.raises(ValueError):FixturePlan(mode='recessed',recess_depth=0,reason='沒有槽深')

def test_verified_fixture_intent_does_not_force_a_pendant_into_placeholder_height():
    from interior.visualization.asset_fit import choose_fit
    _,scale,size=choose_fit([.45,.45,.12],[.25,.25,1.2],envelope=True,policy=dict(purpose='light',dimension_source='estimated',installation_mode='pendant'))
    assert scale==1 and size==[.25,.25,1.2]
    with pytest.raises(ValueError):choose_fit([.45,.45,.12],[.25,.25,1.2],policy=dict(purpose='light',dimension_source='confirmed',dimensions=[.45,.45,.12],evidence='confirmed',installation_mode='pendant'))

def test_camera_repair_only_changes_one_shot_and_limits_travel():
    old=baseline();shot=copy.deepcopy(old['viewpoints'][0]['shots'][0]);shot.update(lens=35,eye=[1.2,2,1.6])
    new=apply_plan(old,'living','front',dict(can_repair=True,shot=shot,reason='減少近景'))
    assert new['door_controls']==old['door_controls'] and new['groups']==old['groups']
    assert old['viewpoints'][0]['shots'][0]['lens']==24
    shot['eye']=[9,2,1.6]
    with pytest.raises(ValueError):apply_plan(old,'living','front',dict(can_repair=True,shot=shot,reason='too far'))

def test_repair_operation_is_deduplicated_and_stale_revision_cannot_start(tmp_path):
    import threading
    from types import SimpleNamespace
    from unittest.mock import patch
    from interior.workbench.studio.editor_repair import EditorRepairs,EditorRepairRequest
    from interior.workbench.storage import Conflict
    folder=tmp_path/'case';folder.mkdir()
    studio=SimpleNamespace(folder=lambda p:folder,current=lambda p:dict(revision='a'*32,scene=baseline()),store=SimpleNamespace(lock=threading.RLock()),jobs=SimpleNamespace(close_callbacks=[]))
    batches=SimpleNamespace(folder=lambda p:tmp_path/'batches')
    service=EditorRepairs(studio,None,batches)
    body=EditorRepairRequest(base_revision='a'*32,operation_id='operation-one',category='door',target_id='door',reason='碰牆')
    with patch('interior.workbench.studio.editor_repair.threading.Thread') as thread:
        first=service.start('P',body);again=service.start('P',body)
        assert first['id']==again['id'] and thread.return_value.start.call_count==1
    stale=body.model_copy(update={'operation_id':'operation-two','base_revision':'b'*32})
    service.running.clear()
    with pytest.raises(Conflict):service.start('P',stale)

def test_occluded_installation_view_retries_once_without_dismissing_the_problem(tmp_path):
    from types import SimpleNamespace
    from interior.workbench.studio.asset_automation import AutoPlacement
    from interior.workbench.storage import write_json
    job=dict(id='a'*32,output='trial')
    report=dict(model_check={'status':'passed'},installation={'status':'passed'},visual_review={'images':['model-object.png','model-reverse.png','model-context.png']})
    write_json(tmp_path/'trial/replacement-report.json',report)
    agent=dict(status='passed',job_id=job['id'],verdict={'status':'uncertain','issues':['visibility'],'reason':'天花接點被遮擋'})
    runner=SimpleNamespace(studio=SimpleNamespace(root=lambda p:tmp_path),batches=SimpleNamespace(agents=SimpleNamespace(get=lambda key:agent)))
    row={'job_id':job['id']};state={};path=tmp_path/'state.json'
    target={'name':'天花燈具','context':{'group':{}}}
    assert AutoPlacement.review(runner,'P','b'*32,target,row,state,path,job,{})=='pending'
    assert row['installation_view_retries']==1 and 'job_id' not in row and row['generation']==1
    assert AutoPlacement.review(runner,'P','b'*32,target,row,state,path,job,{})=='pause'
    assert state['status']=='paused' and '未確認' in row['error']


def test_old_repair_records_expose_trial_reasons_without_rewriting_history(tmp_path):
    import threading
    from types import SimpleNamespace
    from interior.workbench.storage import write_json
    from interior.workbench.studio.editor_repair import EditorRepairs
    studio=SimpleNamespace(folder=lambda p:tmp_path/'case',jobs=SimpleNamespace(close_callbacks=[]))
    batches=SimpleNamespace(folder=lambda p:tmp_path/'batches')
    repairs=EditorRepairs(studio,None,batches)
    key='a'*32;batch='b'*32
    path=repairs.path('P',key)
    write_json(path,dict(status='needs_attention',batch_id=batch,error='已達兩輪上限',request=dict(target_id='lamp')))
    write_json(tmp_path/'batches'/batch/'input.json',dict(targets=[dict(group_id='lamp',task_id='source')]))
    write_json(tmp_path/'batches'/batch/'placement.json',dict(items={'source':dict(attempts=[dict(error='主要發光面朝上')])}))
    before=path.read_bytes()
    result=repairs.get('P',key)
    assert result['failure_details'][0]['reason']=='主要發光面朝上'
    assert path.read_bytes()==before
