"""Repairs must preserve topology, measurement evidence and explicit review."""
import copy
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from interior.workbench.studio.image_plan import validate_recognition
from interior.workbench.studio.image_review import prepare_review, review_images, compare_passes
from interior.workbench.agent_runtime.service import AgentTasks
from interior.workbench.storage import read_json, write_json


def candidate():
    def f(id,role,points,host=None):
        return dict(id=id,name=id,role=role,points=points,closed=False,confidence='medium',evidence='visible',host_id=host)
    return dict(features=[f('wall','wall',[[20,20],[380,20]]),f('door','door',[[100,23],[160,23]],'wall')],
        scale=None,uncertainties=['height uses editable default'],dimensions=[],review=[])


def test_small_host_error_is_audited_without_moving_wall():
    p=candidate();before=copy.deepcopy(p)
    result,audit,questions=prepare_review(p,400,300,reviewed=True)
    assert p==before
    # At 400x300 the bounded tolerance is 2.4 pixels: 3 px must not be silently fixed.
    assert not audit['corrections'] and any(q['id']=='host-door' for q in questions)
    p['features'][1]['points']=[[100,22],[160,22]]
    result,audit,questions=prepare_review(p,400,300,reviewed=True)
    assert result['features'][0]==p['features'][0]
    assert result['features'][1]['points']==[[100,20],[160,20]]
    assert audit['corrections'][0]['max_pixels']==2
    assert all(q['id']!='host-door' for q in questions)


@pytest.mark.parametrize('points,host', [([[100,70],[160,70]],'wall'),([[-1,20],[160,20]],'wall'),([[100,20],[160,20]],None)])
def test_no_large_snap_host_guess_or_wall_extension(points,host):
    p=candidate();p['features'][1].update(points=points,host_id=host)
    result,audit,questions=prepare_review(p,400,300,reviewed=True)
    assert result['features']==p['features'] and not audit['corrections']
    assert any(q['id']=='host-door' for q in questions)


def test_dimension_residuals_not_global_warp_and_no_per_medium_question():
    p=candidate();p['features'][1]['points']=[[100,20],[160,20]]
    p['dimensions']=[dict(id='total',text='600 cm',metres=6,start=[20,20],end=[380,20],confidence='high',endpoint_evidence='shared wall ends'),
        dict(id='short',text='41 cm',metres=.41,start=[20,20],end=[140,20],confidence='high',endpoint_evidence='local ends')]
    result,audit,questions=prepare_review(p,400,300,reviewed=True)
    assert result['features']==p['features']
    assert result['scale']['metres']==6
    assert [q['id'] for q in questions]==['dimension-distortion']
    assert audit['dimension_residuals'][1]['difference_m']==1.59
    assert result['dimensions'][1]['metres']==.41


def test_low_confidence_and_semantic_questions_survive():
    p=candidate();p['features'][1]['confidence']='low'
    p['review']=[dict(id='ambiguous',feature_ids=['door'],kind='classification',question='Is this an opening or a window?')]
    _,_,questions=prepare_review(p,400,300,reviewed=True)
    assert any(q['id']=='agent-ambiguous' for q in questions)
    assert not any(q['id']=='low-door' for q in questions) # no duplicate confidence question


def test_crop_coordinates_and_response_references(tmp_path):
    image=tmp_path/'source.png';Image.new('RGB',(400,300)).save(image)
    paths,manifest=review_images(image,tmp_path)
    assert len(paths)==4 and manifest[-1]['box']==[160,120,400,300]
    assert Image.open(paths[-1]).size==tuple(manifest[-1]['size'])
    p=candidate();p['review']=[dict(id='bad',feature_ids=['absent'],kind='missing',question='Where?')]
    with pytest.raises(ValueError,match='不存在'):validate_recognition(json.dumps(p),400,300)


@pytest.mark.parametrize('malformed_first', [False, True])
def test_two_pass_task_and_no_automatic_build(tmp_path,malformed_first):
    calls=[]
    class Runtime:
        def __init__(self,directory):self.directory=directory
        def status(self):return dict(authenticated=True,auth_type='chatgpt',version='test',models=[dict(id='visual',inputModalities=['image'])])
        def run(self,prompt,**kwargs):
            calls.append(kwargs)
            if malformed_first and len(calls)==1:return dict(text='{"features": "invalid"}',model='visual')
            return dict(text=json.dumps(candidate()),model='visual')
        def close(self):pass
    source=tmp_path/'source.png';Image.new('RGB',(400,300)).save(source)
    agents=AgentTasks(tmp_path);task=dict(id='a'*32,status='queued',kind='plan_image',model='visual')
    write_json(agents.root/task['id']/'task.json',task)
    with patch('interior.workbench.agent_runtime.service.CodexRuntime',Runtime):
        agents._run(task,dict(image=str(source),width=400,height=300,result_path=str(tmp_path/'result.json')))
    result=read_json(tmp_path/'result.json')
    assert result['status']=='passed' and result['review_complete']
    assert len(result['passes'])==2 and len(calls[1]['images'])==4
    assert bool(result['passes'][0]['validation_error'])==malformed_first
    assert not list(tmp_path.rglob('*.blend'))


def test_stop_after_inventory_does_not_launch_review(tmp_path):
    agents=AgentTasks(tmp_path);calls=[]
    task=dict(id='b'*32,status='queued',kind='plan_image',model='visual')
    path=agents.root/task['id']/'task.json';write_json(path,task)
    class Runtime:
        def __init__(self,directory):pass
        def status(self):return dict(authenticated=True,auth_type='chatgpt',version='test',models=[dict(id='visual',inputModalities=['image'])])
        def run(self,*args,**kwargs):
            calls.append(1);write_json(path,dict(task,status='stopping'))
            return dict(text=json.dumps(candidate()))
        def close(self):pass
    with patch('interior.workbench.agent_runtime.service.CodexRuntime',Runtime):
        agents._run(task,dict(image=str(tmp_path/'source.png'),width=400,height=300))
    assert agents.get(task['id'])['status']=='stopped' and len(calls)==1


def test_invalid_final_review_never_becomes_a_candidate(tmp_path):
    calls=[]
    class Runtime:
        def __init__(self,directory):pass
        def status(self):return dict(authenticated=True,auth_type='chatgpt',version='test',models=[dict(id='visual',inputModalities=['image'])])
        def run(self,*args,**kwargs):
            calls.append(1)
            return dict(text=json.dumps(candidate()) if len(calls)==1 else '{invalid')
        def close(self):pass
    source=tmp_path/'source.png';Image.new('RGB',(400,300)).save(source)
    agents=AgentTasks(tmp_path);task=dict(id='c'*32,status='queued',kind='plan_image',model='visual')
    write_json(agents.root/task['id']/'task.json',task)
    with patch('interior.workbench.agent_runtime.service.CodexRuntime',Runtime):
        agents._run(task,dict(image=str(source),width=400,height=300))
    result=agents.get(task['id'])
    assert result['status']=='failed' and 'candidate' not in result
    assert len(calls)==2 and result['response']['text']=='{invalid'


def test_dimension_references_are_valid_but_outside_endpoints_are_not():
    p=candidate()
    p['dimensions']=[dict(id='dim1',text='90?',metres=None,start=None,end=None,endpoint_evidence='unclear',confidence='low')]
    p['review']=[dict(id='q1',feature_ids=['dim1'],kind='dimension',question='Which endpoints?')]
    assert validate_recognition(json.dumps(p),400,300)['review'][0]['feature_ids']==['dim1']
    p['dimensions'][0]['start']=[450,10]
    with pytest.raises(ValueError,match='範圍'):validate_recognition(json.dumps(p),400,300)


def test_review_diff_ignores_float_noise_and_records_actual_changes():
    old=candidate();new=copy.deepcopy(old)
    new['features'][1]['points'][0][1]+=.0000004
    assert compare_passes([dict(candidate=old),dict(candidate=new)])==[]
    new['features'][1]['points'][0][1]+=1
    assert compare_passes([dict(candidate=old),dict(candidate=new)])[0]['feature_id']=='door'
    assert compare_passes([dict(candidate='invalid raw'),dict(candidate=new)])==[]
    p=candidate();p['features'][1]['points']=[[100,20.0000004],[160,20.0000004]]
    _,audit,_=prepare_review(p,400,300,reviewed=True)
    assert audit['corrections']==[]
