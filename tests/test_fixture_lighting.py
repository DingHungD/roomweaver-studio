"""Synthetic additive lighting, geometry bounds, revision and recovery contracts."""
import copy
import json
import math
from unittest.mock import patch

import pytest
from interior.workbench.storage import Conflict, write_json, read_json
from interior.workbench.studio import fixture_lighting as fl
from interior.workbench.studio.models import StudioLight, LightingSetup, Scene
from interior.workbench.studio.service import digest
from test_asset_matching import environment


class Agents:
    def __init__(self):self.tasks={};self.calls=0
    def start(self,kind,model,payload,identifier):
        self.calls+=1
        assert kind=='fixture_lighting'
        self.tasks[identifier]=dict(id=identifier,status='queued')
    def get(self,identifier):return copy.deepcopy(self.tasks[identifier])


def proposal(**patches):
    return fl.FixtureProposal.model_validate(dict(status='fixture',reason='Measured diffuser',
        emitters=[dict(anchor_id='a0',kind='AREA',power=30,kelvin=3000,size=.1,angle=60)],**patches))


ANCHORS=[dict(id='a0',position=[2,3,2.5],normal=[0,0,-1],max_size=.3)]
GROUP=dict(id='fixture',name='Anonymous fixture')


def test_measured_base_coordinates_outward_direction_stable_ids_and_no_mutation():
    original=copy.deepcopy(ANCHORS)
    light=fl.build_lights(GROUP,proposal(),ANCHORS,'a'*64)[0]
    assert light['position']==[2,3,2.485]
    assert light['rotation']==[0,0,0]
    assert light['group_id']=='fixture' and light['origin']=='proposal'
    assert light['id']==fl.build_lights(GROUP,proposal(),ANCHORS,'a'*64)[0]['id']
    assert light['id']!=fl.build_lights(GROUP,proposal(),ANCHORS,'b'*64)[0]['id']
    assert ANCHORS==original
    side=[dict(ANCHORS[0],normal=[1,0,0])]
    rotation=fl.build_lights(GROUP,proposal(),side,'a'*64)[0]['rotation']
    assert rotation[1]==pytest.approx(math.pi/2)
    assert abs(rotation[2])==pytest.approx(math.pi)


@pytest.mark.parametrize('change',[dict(anchor_id='invented'),dict(power=float('nan')),dict(power=900),dict(kelvin=10000),dict(size=.5)])
def test_invalid_emitters_do_not_apply(change):
    emitter=proposal().emitters[0].model_dump();emitter.update(change)
    with pytest.raises(ValueError):
        value=fl.FixtureProposal(status='fixture',reason='test',emitters=[emitter])
        fl.build_lights(GROUP,value,ANCHORS,'a'*64)


def test_duplicate_surface_and_uncertain_emitter_rejected():
    value=proposal();value.emitters*=2
    with pytest.raises(ValueError,match='重複'):fl.build_lights(GROUP,value,ANCHORS,'a'*64)
    value=proposal();value.status='uncertain'
    with pytest.raises(ValueError):fl.build_lights(GROUP,value,ANCHORS,'a'*64)


@pytest.fixture
def service(tmp_path):
    studio,jobs,first=environment(tmp_path)
    native=studio.root('ASSETS')/'runs/interior-studio'/first['scene']['model_id']/'model.blend'
    native.write_bytes(b'synthetic native source')
    model=studio.model('ASSETS',first['scene']['model_id']);model['native_sha256']=digest(native)
    write_json(native.with_name('model.json'),model)
    agents=Agents();workflow=fl.FixtureLighting(studio,agents)
    yield workflow,studio,agents,first,native
    jobs.close()


def start(service):
    workflow,studio,agents,first,native=service
    body=fl.FixtureLightingRequest(base_revision=first['revision'],operation_id='fixture-test-operation',model='selected-model')
    return workflow.start('ASSETS',body),body


def finish(service,task):
    workflow,studio,agents,first,native=service
    setup=copy.deepcopy(first['scene']['lighting_setup'])
    setup['lights'].append(StudioLight(id='new-light',name='New fixture',position=[1,2,2]).model_dump(mode='json'))
    setup['enabled']=True
    agents.tasks[task['id']].update(status='passed',lighting_setup=setup,report=dict(added_count=1,items=[],notes=[]))


def test_operation_dedup_input_binding_and_read_only_recovery(service):
    task,body=start(service);workflow,studio,agents,first,native=service
    assert workflow.start('ASSETS',body)['id']==task['id'] and agents.calls==1
    assert workflow.current('ASSETS')['id']==task['id']
    assert studio.current('ASSETS')['revision']==first['revision']
    with pytest.raises(Conflict):workflow.start('ASSETS',body.model_copy(update=dict(model='different-model')))
    with pytest.raises(ValueError):workflow.get('ASSETS','../bad')
    with pytest.raises(FileNotFoundError):workflow.get('ASSETS','b'*32)


def test_apply_adds_only_lighting_and_is_idempotent(service):
    task,body=start(service);workflow,studio,agents,first,native=service
    finish(service,task)
    accepted=workflow.apply('ASSETS',task['id'],body.base_revision)
    assert accepted['revision']!=first['revision']
    expected=copy.deepcopy(first['scene']);expected['lighting_setup']=accepted['scene']['lighting_setup']
    assert accepted['scene']==Scene.model_validate(expected).model_dump(mode='json')
    assert workflow.apply('ASSETS',task['id'],body.base_revision)==accepted
    assert fl.FixtureLighting(studio,agents).current('ASSETS')['adoption']['revision']==accepted['revision']
    assert native.read_bytes()==b'synthetic native source'


@pytest.mark.parametrize('change',['revision','native','running','stopped','interrupted'])
def test_stale_source_or_noncomplete_task_cannot_apply(service,change):
    task,body=start(service);workflow,studio,agents,first,native=service;finish(service,task)
    if change=='revision':studio.save('ASSETS',first['scene'],first['revision'])
    elif change=='native':native.write_bytes(b'changed source')
    else:agents.tasks[task['id']]['status']=change
    current=studio.current('ASSETS')
    with pytest.raises(Conflict):workflow.apply('ASSETS',task['id'],body.base_revision)
    assert studio.current('ASSETS')==current


def test_preserve_all_existing_locked_manual_disabled_lights_and_native_priority(tmp_path):
    light=StudioLight(id='manual',name='Manual',position=[9,9,2],locked=True,enabled=False,group_id='existing').model_dump(mode='json')
    setup=LightingSetup(enabled=False,exposure=.7,auto_adjust=False,agent_review=False,lights=[light]).model_dump(mode='json')
    scene=dict(lighting_setup=setup)
    native=StudioLight(id='native',name='Native',position=[0,0,2.5],origin='native').model_dump(mode='json')
    groups=[dict(id='existing',name='Existing'),dict(id='native-group',name='Native',bounds=[[-.1,-.1,2],[.1,.1,3]])]
    payload=dict(output=str(tmp_path),scene=scene,base_revision='a'*32,native_sha256='c'*64)
    class NoCalls:
        def run(self,*a,**kw):raise AssertionError('bound fixtures must not call Agent')
    with patch.object(fl,'native_evidence',return_value=dict(native_lights=[native],groups=groups)):
        result=fl.run_fixture_lighting(NoCalls(),tmp_path,payload,'chosen',lambda _:None,lambda _:None)
    assert result['lighting_setup']['lights']==[light,native]
    assert result['lighting_setup']['exposure']==.7 and not result['lighting_setup']['agent_review']
    assert setup['lights']==[light] and not setup['enabled']
    assert result['report']['added_count']==0 and result['report']['restored_count']==1


def test_agent_visual_two_pass_unknowns_and_coverage_validation(tmp_path):
    group=dict(GROUP,dimensions=[.4,.4,.2],components=[],sampled=False,triangles=[],bounds=[[0,0,2],[1,1,3]])
    payload=dict(output=str(tmp_path),scene=dict(lighting_setup={}),base_revision='a'*32,native_sha256='a'*64)
    detail=dict(anchors=ANCHORS,images=['one.png'],directory=str(tmp_path))
    class Client:
        def __init__(self):self.calls=[]
        def run(self,prompt,**kwargs):
            self.calls.append(kwargs)
            value=dict(items=[dict(group_id='fixture',status='fixture',reason='visible fitting')]) if len(self.calls)==1 else proposal().model_dump()
            return dict(text=json.dumps(value))
    client=Client()
    with patch.object(fl,'native_evidence',side_effect=[dict(native_lights=[],groups=[group]),detail]):
        result=fl.run_fixture_lighting(client,tmp_path,payload,'chosen',lambda _:None,lambda _:None)
    assert result['report']['added_count']==1
    assert client.calls[0]['model']=='chosen' and client.calls[0]['image'].exists()
    assert client.calls[1]['images']==[tmp_path/'one.png']
    assert (tmp_path/'report.json').exists()
    class BadClient:
        def run(self,*a,**kw):return dict(text='{"items":[]}')
    with patch.object(fl,'native_evidence',return_value=dict(native_lights=[],groups=[group])):
        with pytest.raises(ValueError,match='盤點'):fl.run_fixture_lighting(BadClient(),tmp_path,payload,'chosen',lambda _:None,lambda _:None)


def test_empty_and_uncertain_models_keep_lights_unchanged(tmp_path):
    payload=dict(output=str(tmp_path),scene=dict(lighting_setup={}),base_revision='a'*32,native_sha256='a'*64)
    class NoCalls:
        def run(self,*a,**kw):raise AssertionError('no eligible geometry')
    with patch.object(fl,'native_evidence',return_value=dict(native_lights=[],groups=[dict(id='missing',name='Unknown',error='No geometry')])):
        result=fl.run_fixture_lighting(NoCalls(),tmp_path,payload,'chosen',lambda _:None,lambda _:None)
    assert not result['lighting_setup']['lights'] and not result['lighting_setup']['enabled']
    assert result['report']['uncertain_count']==1


def test_bounded_retry_validates_scope_and_leaves_unselected_groups_out(tmp_path):
    payload=dict(output=str(tmp_path),scene=dict(lighting_setup={}),base_revision='a'*32,native_sha256='a'*64,focus_group_ids=['selected'])
    evidence=dict(native_lights=[],groups=[dict(id='selected',name='Selected',error='No reliable surface'),dict(id='other',name='Unselected',error='No geometry')])
    class NoCalls:
        def run(self,*a,**kw):raise AssertionError('no eligible surfaces')
    with patch.object(fl,'native_evidence',return_value=evidence):
        result=fl.run_fixture_lighting(NoCalls(),tmp_path,payload,'chosen',lambda _:None,lambda _:None)
    assert [i['group_id'] for i in result['report']['items']]==['selected']
    assert result['report']['total_groups']==1 and result['report']['inventoried_groups']==2
    for focus in ([],['missing']):
        with patch.object(fl,'native_evidence',return_value=evidence):
            with pytest.raises(ValueError,match='限定複核'):fl.run_fixture_lighting(NoCalls(),tmp_path,dict(payload,focus_group_ids=focus),'chosen',lambda _:None,lambda _:None)


def test_later_candidates_receive_validated_private_light_evidence_without_mutating_scene(tmp_path):
    groups=[dict(GROUP,id=g,name=g,dimensions=[.4,.4,.2],components=[],sampled=False,triangles=[],bounds=[[0,0,2],[1,1,3]]) for g in ('one','two')]
    payload=dict(output=str(tmp_path),scene=dict(lighting_setup={}),base_revision='a'*32,native_sha256='a'*64)
    counts=[]
    def native(directory,packet,mode,*args,**kwargs):
        counts.append(len(packet['scene']['lighting_setup'].get('lights',[])))
        return dict(native_lights=[],groups=groups) if mode=='inventory' else dict(anchors=ANCHORS,images=[],directory=str(tmp_path))
    class Client:
        calls=0
        def run(self,*args,**kwargs):
            self.calls+=1
            return dict(text=json.dumps(dict(items=[dict(group_id=g['id'],status='fixture',reason='fixture') for g in groups]) if self.calls==1 else proposal().model_dump()))
    with patch.object(fl,'native_evidence',side_effect=native):
        result=fl.run_fixture_lighting(Client(),tmp_path,payload,'chosen',lambda _:None,lambda _:None)
    assert counts==[0,0,1] and len(result['lighting_setup']['lights'])==2
    assert payload['scene']['lighting_setup']=={}


def test_unsupported_malformed_agent_cannot_supply_arbitrary_coordinates():
    with pytest.raises(ValueError):fl.parse_response(dict(text='not json'),fl.FixtureProposal)
    raw=proposal().model_dump();raw['emitters'][0]['position']=[0,0,100]
    with pytest.raises(ValueError):fl.FixtureProposal.model_validate(raw)


def test_adoption_rejects_modified_existing_light(service):
    workflow,studio,agents,first,native=service
    scene=copy.deepcopy(first['scene'])
    scene['lighting_setup']['lights']=[StudioLight(id='keep',name='Keep',position=[1,1,1],locked=True).model_dump(mode='json')]
    saved=studio.save('ASSETS',scene,first['revision'])
    task=workflow.start('ASSETS',fl.FixtureLightingRequest(base_revision=saved['revision'],operation_id='tampered-existing'))
    modified=copy.deepcopy(saved['scene']['lighting_setup']);modified['lights'][0]['power']=99
    agents.tasks[task['id']].update(status='passed',lighting_setup=modified)
    with pytest.raises(Conflict,match='既有'):workflow.apply('ASSETS',task['id'],saved['revision'])
    assert studio.current('ASSETS')==saved


def test_capacity_limit_retains_existing_200_lights_without_partial_fixture(tmp_path):
    lights=[StudioLight(id='light-'+str(i),name='Existing',position=[9,9,2]).model_dump(mode='json') for i in range(200)]
    group=dict(GROUP,dimensions=[.4,.4,.2],components=[],sampled=False,triangles=[],bounds=[[0,0,2],[1,1,3]])
    payload=dict(output=str(tmp_path),scene=dict(lighting_setup=dict(lights=lights)),base_revision='a'*32,native_sha256='a'*64)
    class Client:
        calls=0
        def run(self,*a,**kw):
            self.calls+=1
            return dict(text=json.dumps(dict(items=[dict(group_id='fixture',status='fixture',reason='lamp')]) if self.calls==1 else proposal().model_dump()))
    with patch.object(fl,'native_evidence',side_effect=[dict(native_lights=[],groups=[group]),dict(anchors=ANCHORS,images=[],directory=str(tmp_path))]):
        result=fl.run_fixture_lighting(Client(),tmp_path,payload,'chosen',lambda _:None,lambda _:None)
    assert result['lighting_setup']['lights']==lights
    assert result['report']['added_count']==0 and result['report']['uncertain_count']==1


def test_http_start_read_recover_apply_and_validate(tmp_path):
    from fastapi.testclient import TestClient
    from interior.workbench.jobs import Jobs
    from interior.workbench.server import create_app
    from test_workbench_studio import synthetic_scene
    with patch.object(Jobs,'loop',return_value=None):app=create_app(tmp_path)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        store=app.state.store;studio=app.state.studio;agents=app.state.studio_agents
        store.create_project(dict(id='HTTP_FIXTURE',name='Synthetic HTTP fixture'))
        scene=synthetic_scene()
        scene['groups']=[dict(id='fixture',name='Anonymous',children=['wall','sofa'],translation=[0,0,0],deleted=False)]
        model_dir=studio.root('HTTP_FIXTURE')/'runs/interior-studio'/scene['model_id']
        model_dir.mkdir(parents=True);(model_dir/'model.blend').write_bytes(b'native')
        write_json(model_dir/'model.json',dict(objects=scene['objects'],native_sha256=digest(model_dir/'model.blend')))
        saved=studio.save('HTTP_FIXTURE',scene,None)
        headers={'X-Workbench-Token':client.get('/api/session').json()['token']}
        base='/api/studio/projects/HTTP_FIXTURE/fixture-lighting'
        assert client.get(base+'/current').json() is None
        def start_task(kind,model,payload,identifier):
            setup=copy.deepcopy(payload['scene']['lighting_setup']);setup['enabled']=True
            setup['lights']=[StudioLight(id='fixture-new',name='Fixture',group_id='fixture',position=[0,0,2]).model_dump(mode='json')]
            result=dict(id=identifier,kind=kind,status='passed',lighting_setup=setup,report=dict(items=[],notes=[],added_count=1))
            write_json(agents.root/identifier/'task.json',result)
            return result
        with patch.object(agents,'start',side_effect=start_task) as submit:
            request=dict(base_revision=saved['revision'],operation_id='http-fixture-test',model=None)
            result=client.post(base,json=request,headers=headers)
            assert result.status_code==200
            task=result.json();assert task['status']=='passed'
            assert client.post(base,json=request,headers=headers).json()['id']==task['id']
            assert submit.call_count==1
            assert client.get(base+'/current').json()['id']==task['id']
            assert studio.current('HTTP_FIXTURE')['revision']==saved['revision']
            accepted=client.post(base+'/'+task['id']+'/apply',json=dict(base_revision=saved['revision']),headers=headers)
            assert accepted.status_code==200
            assert accepted.json()['scene']['lighting_setup']['lights'][0]['group_id']=='fixture'
            assert client.post(base+'/'+task['id']+'/apply',json=dict(base_revision=saved['revision']),headers=headers).json()==accepted.json()
            assert client.post(base,json=dict(request,base_revision='invalid'),headers=headers).status_code==422
            assert client.get(base+'/'+task['id']+'/images/0/untrusted').status_code==422
