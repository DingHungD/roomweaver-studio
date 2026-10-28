import json
import pytest
from interior.workbench.studio.models import ManualDoor
from interior.workbench.studio.door_design import run_door_design

def test_manual_door_span_and_unknown_configuration():
    door=ManualDoor(id='door-'+'a'*8+'-'+'a'*4+'-'+'a'*4+'-'+'a'*4+'-'+'a'*12,name='door',points=((0,0),(1,0)))
    assert door.height==2.1
    with pytest.raises(ValueError):ManualDoor(**dict(door.model_dump(),points=((0,0),(.01,0))))

def test_agent_cannot_change_manual_choices_or_unknown_openings(tmp_path):
    class Client:
        def run(self,*a,**kw):
            assert kw['model']=='gpt-6-sol'
            return {'text':json.dumps({'controls':[{'opening_id':'one','kind':'single','side':'negative'}],'uncertainties':[]})}
    payload=dict(openings=[{'id':'one','points':[[0,0],[1,0]]}],controls=[dict(opening_id='one',kind='sliding',side=None,hinge='auto',swing='auto')])
    result=run_door_design(Client(),tmp_path,payload,'gpt-6-sol',lambda _:None,lambda _:None)
    assert result['controls'][0]['kind']=='sliding'
    payload['openings']=[]
    with pytest.raises(ValueError):run_door_design(Client(),tmp_path,payload,'gpt-6-sol',lambda _:None,lambda _:None)

def test_door_task_completes_through_runtime(tmp_path,monkeypatch):
    from interior.workbench.agent_runtime import service
    from interior.workbench.storage import write_json
    class Client:
        def __init__(self,*args):pass
        def status(self):return dict(authenticated=True,auth_type='chatgpt',version='test')
        def close(self):pass
    monkeypatch.setattr(service,'CodexRuntime',Client)
    monkeypatch.setattr(service,'select_model',lambda *args:dict(model='gpt-6-sol'))
    monkeypatch.setattr('interior.workbench.studio.door_design.run_door_design',lambda *args:dict(controls=[],uncertainties=[]))
    tasks=service.AgentTasks(tmp_path)
    task=dict(id='a'*32,kind='door_design',model='gpt-6-sol',status='queued')
    write_json(tasks.root/task['id']/'task.json',task)
    tasks._run(task,{})
    assert tasks.get(task['id'])['status']=='passed'


def test_original_fold_type_is_retained_without_changing_endpoints(tmp_path):
    class Client:
        def run(self,*args,**kwargs):
            return {'text':json.dumps({'controls':[dict(opening_id='bath',kind='single',side='positive',hinge='A')],'uncertainties':[]})}
    points=[[6.6,3.4],[6.6,2.7]]
    payload=dict(openings=[dict(id='bath',name='bath-fold',points=points,height=2.1)],controls=[])
    result=run_door_design(Client(),tmp_path,payload,'gpt-6-sol',lambda _:None,lambda _:None)
    assert result['controls'][0]['kind']=='folding'
    assert result['controls'][0]['hinge']=='A'
    assert payload['openings'][0]['points']==points
    assert payload['openings'][0]['height']==2.1


def test_deleted_doors_survive_agent_roundtrip(tmp_path):
    from interior.workbench.studio.models import DoorControl
    class Client:
        def run(self,*args,**kwargs):
            return {'text':'{"controls":[],"uncertainties":[]}'}
    deleted=DoorControl(opening_id='removed',kind='folding',deleted=True).model_dump()
    result=run_door_design(Client(),tmp_path,dict(openings=[],controls=[deleted]),'gpt-6-sol',lambda _:None,lambda _:None)
    assert result['controls']==[deleted]
    assert DoorControl.model_validate_json(DoorControl(**deleted).model_dump_json()).deleted


def test_door_materials_roundtrip_and_validation():
    from interior.workbench.studio.models import DoorControl
    d=DoorControl(opening_id='test',kind='folding',side='negative',hinge='B',materials={'leaf-0':{'color':'#336699','roughness':.82}})
    assert DoorControl.model_validate_json(d.model_dump_json())==d
    with pytest.raises(ValueError):DoorControl(opening_id='test',materials={'frame':{'color':'invalid'}})
    with pytest.raises(ValueError):DoorControl(opening_id='test',materials={'unknown':{'color':'#ffffff'}})


def test_authorised_width_uses_measured_fit_not_agent_guess(tmp_path,monkeypatch):
    from interior.workbench.studio import door_collision
    monkeypatch.setattr(door_collision,'check_poses',lambda *a:dict(items=[]))
    monkeypatch.setattr(door_collision,'width_candidates',lambda *a:{'one':{'recommended_width':.85}})
    class Client:
        def run(self,prompt,**kw):
            assert 'native_use_review' in prompt
            return {'text':json.dumps({'controls':[{'opening_id':'one','kind':'single','assembly_width':.5}],'uncertainties':[]})}
    controls=[dict(opening_id='one',kind='single',side='negative',swing='positive',allow_width_adjustment=True,materials={'frame':{'color':'#bca07b','roughness':.6}})]
    payload=dict(openings=[dict(id='one',name='door',points=[[0,0],[.9,0]])],controls=controls,collision_context=dict(blend=str(tmp_path/'runs/interior-studio/model/model.blend'),sha256='a'*64,scene={}))
    r=run_door_design(Client(),tmp_path,payload,'gpt-6-sol',lambda _:None,lambda _:None)
    assert r['controls'][0]['assembly_width']==.85
    assert r['controls'][0]['side']=='negative' and r['controls'][0]['materials']==controls[0]['materials']

def test_unapproved_agent_width_is_rejected(tmp_path):
    class Client:
        def run(self,*a,**kw):return {'text':json.dumps({'controls':[{'opening_id':'one','assembly_width':.5}],'uncertainties':[]})}
    r=run_door_design(Client(),tmp_path,dict(openings=[dict(id='one')],controls=[dict(opening_id='one',kind='single')]),'gpt-6-sol',lambda _:None,lambda _:None)
    assert r['controls'][0]['assembly_width'] is None


def test_width_search_requires_individual_authorisation(monkeypatch):
    from interior.workbench.studio import door_collision
    monkeypatch.setattr(door_collision,'check_poses',lambda *a:(_ for _ in ()).throw(AssertionError('must not resize')))
    assert door_collision.width_candidates(dict(collision_context=dict(blend='/workspace/project/runs/interior-studio/model/model.blend',sha256='a'*64),openings=[],controls=[dict(opening_id='one',kind='single',allow_width_adjustment=False)]))=={}
