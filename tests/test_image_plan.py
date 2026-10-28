"""Synthetic image intake, untrusted recognition, and human confirmation gates."""
import copy
import io
import json
from unittest.mock import patch
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from interior.workbench.server import create_app
from interior.workbench.storage import Store,read_json,write_json
from interior.workbench.jobs import Jobs
from interior.workbench.studio.image_plan import validate_recognition
from interior.workbench.studio.plan_import import check_plan


def proposal():
    def feature(id,role,points,closed=False):
        return dict(id=id,name=id,role=role,points=points,closed=closed,confidence='medium',evidence='visible outline',host_id=None)
    return dict(features=[feature('floor','floor',[[20,20],[380,20],[380,280],[20,280]],True),
        feature('wall','wall',[[20,20],[380,20]]),feature('window','window',[[100,20],[200,20]]),
        feature('desk','furniture',[[230,170],[320,170],[320,220],[230,220]],True)],
        scale=dict(start=[20,20],end=[380,20],metres=6,evidence='dimension six metres'),uncertainties=['height unknown'])


def png():
    data=io.BytesIO();Image.new('RGB',(400,300),'white').save(data,format='PNG');return data.getvalue()


@pytest.mark.parametrize('change', ['duplicate','out_of_bounds','nan','unknown_host','instruction','oversized'])
def test_untrusted_response(change):
    p=proposal()
    if change=='duplicate':p['features'][1]['id']='floor'
    if change=='out_of_bounds':p['features'][1]['points'][0][0]=500
    if change=='nan':p['features'][1]['points'][0][0]=float('nan')
    if change=='unknown_host':p['features'][2]['host_id']='missing'
    if change=='instruction':p['execute']='shell command'
    if change=='oversized':p['features']*=60
    with pytest.raises(ValueError):validate_recognition(json.dumps(p),400,300)


def test_image_http_confirmation_resume_and_dedup(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='IMAGE',name='synthetic'))
    starts=[]
    def fake_start(self,kind,model,payload,identifier):
        starts.append(identifier)
        result=dict(id=identifier,status='passed',kind=kind,model=model,candidate=proposal())
        if kind=='plan_semantics':
            source=payload['site']['geometry'];wall=next(g for g in source if g['source_role']=='wall')
            result['candidate']=dict(summary='Synthetic source inventory',rooms=[dict(id='study',name='Study',points=payload['site']['floors'][0]['points'],source_ids=[wall['id']],evidence='Source plan')],
                elements=[dict(id=g['id'],name=g['name'],role=g['source_role'],room_id='study',points=g['points'],closed=g['closed'],height=1.2 if g['source_role']=='window' else .75 if g['source_role']=='furniture' else 2.8,base=1 if g['source_role']=='window' else 0,host_id=wall['id'] if g['source_role']=='window' else None,source_ids=[g['id']],evidence='Source feature') for g in source if g['source_role'] in ('wall','window','furniture')],
                door_state='absent',window_state='present',furniture_state='present',inventory_evidence='Source desk preserved',questions=[])
            assert payload['source_images'], 'Image interpretation must include the original normalized image'
        write_json(self.root/identifier/'task.json',result)
        return result
    with patch.object(Jobs,'loop',return_value=None),patch('interior.workbench.agent_runtime.service.AgentTasks.start',fake_start):
        with TestClient(create_app(tmp_path),base_url='http://127.0.0.1') as c:
            h={'x-workbench-token':c.get('/api/session').json()['token']};url='/api/studio/projects/IMAGE'
            assert c.post(url+'/image-plans/upload',files={'file':('bad.png',b'not image')},headers=h).status_code==422
            record=c.post(url+'/image-plans/upload',files={'file':('plan.png',png())},headers=h).json()
            assert starts==[] and record['task_id'] is None
            route=url+'/image-plans/'+record['id']
            assert c.post(route+'/draft',headers=h).status_code==409
            a=c.post(route+'/recognize',json={'model':'test-image'},headers=h).json()
            b=c.post(route+'/recognize',json={'model':'test-image'},headers=h).json()
            assert a['task_id']==b['task_id'] and len(starts)==1
            draft=c.post(route+'/draft',headers=h).json()
            assert c.post(route+'/draft',headers=h).json()['revision']==draft['revision']
            assert draft['check']['status']=='blocked'
            assert c.get(url+'/scene').json()['scene'] is None
            build=url+'/plans/'+draft['id']+'/build'
            assert c.post(build,json={'plan_revision':draft['revision'],'confirmed':True},headers=h).status_code==422
            settings=copy.deepcopy(draft['settings']);settings['calibration']['confirmed']=True
            settings['reviewed']=[q['id'] for q in draft['parsed']['questions']]
            settings['question_notes']=[dict(question_id=draft['parsed']['questions'][0]['id'],title='Synthetic question',known='known value',ask='which face?',regions=[dict(label='region',box=[10,10,40,40])],answer='saved synthetic answer')]
            # Missing elements can be added without altering the Agent/source geometry.
            manual=copy.deepcopy(settings)
            identifier='manual-'+'a'*32
            manual['additions']=[dict(id=identifier,layer='wall',kind='MANUAL',points=[[20,20],[20,280]],closed=False)]
            manual['assignments'].append(dict(id=identifier,name='added wall',role='wall'))
            assert check_plan(draft['parsed'],manual)['counts']['wall']==2
            manual['additions'].append(manual['additions'][0])
            with pytest.raises(ValueError,match='ID'):check_plan(draft['parsed'],manual)
            # Pixels are Y-down; build space is Y-up and normalized to floor origin.
            check=check_plan(draft['parsed'],settings);assert check['status']=='ready'
            assert check['items'][1]['points'][0][1]>4
            bad=copy.deepcopy(settings);bad['assignments'][1]['points']=[[0,0],[999,0]]
            assert c.put(url+'/plans/'+draft['id'],json={'base_revision':draft['revision'],'settings':bad},headers=h).status_code==422
            saved=c.put(url+'/plans/'+draft['id'],json={'base_revision':draft['revision'],'settings':settings},headers=h).json()
            assert c.post(build,json={'plan_revision':draft['revision'],'confirmed':True},headers=h).status_code==409
            assert c.post(build,json={'plan_revision':saved['revision']},headers=h).status_code==422
            # Geometry and scale alone no longer constitute a confirmed intake.
            assert c.post(build,json={'plan_revision':saved['revision'],'confirmed':True},headers=h).status_code==422
            from uuid import uuid4
            semantic_url=url+'/plans/'+draft['id']+'/semantics'
            semantic=c.post(semantic_url,json=dict(base_revision=saved['revision'],model='test-image',operation_id=uuid4().hex),headers=h)
            assert semantic.status_code==200,semantic.text
            adopted=c.post(semantic_url+'/'+semantic.json()['id']+'/adopt',json=dict(base_revision=saved['revision']),headers=h)
            assert adopted.status_code==200,adopted.text
            saved=adopted.json();settings=saved['settings'];settings['intake_review']=dict(purposes=True,structure=True,furniture=True)
            saved=c.put(url+'/plans/'+draft['id'],json=dict(base_revision=saved['revision'],settings=settings),headers=h).json()
            payload={'plan_revision':saved['revision'],'confirmed':True}
            a=c.post(build,json=payload,headers=h);b=c.post(build,json=payload,headers=h)
            assert a.status_code==200,a.text
            assert a.json()['id']==b.json()['id']
            assert c.get(url+'/image-plans/current').json()['plan']['revision']==saved['revision']
            assert (tmp_path/'projects/image'/draft['source']['path']).read_bytes()==png()
            (tmp_path/'projects/image'/draft['source']['path']).write_bytes(b'tamper')
            assert c.post(build,json=payload,headers=h).status_code==422
        # Reopen persisted draft without any new Agent call or automatic render.
        with TestClient(create_app(tmp_path),base_url='http://127.0.0.1') as c:
            assert c.get(url+'/image-plans/current').json()['plan']['revision']==saved['revision']
            assert c.get(url+'/image-plans/current').json()['plan']['settings']['question_notes'][0]['answer']=='saved synthetic answer'
            assert len(starts)==2
