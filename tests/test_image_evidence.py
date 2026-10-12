"""Synthetic evidence reconciliation: provenance, bounded edits and immutable forks."""
import copy
import json
from unittest.mock import patch
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from interior.workbench.server import create_app
from interior.workbench.storage import Store, write_json
from interior.workbench.jobs import Jobs
from interior.workbench.studio.image_plan import validate_recognition
from interior.workbench.studio.image_evidence import (
    apply_reconciliation, validate_evidence, digit_images, digit_prompt, run_refinement,
)
from test_image_plan import proposal, png


def inputs():
    p=proposal()
    p['dimensions']=[dict(id='d',text='231.6',metres=2.316,start=None,end=None,
        confidence='medium',endpoint_evidence='endpoint unknown')]
    p['review']=[dict(id='q',kind='classification',question='Door or window?',feature_ids=['window']),
        dict(id='n',kind='dimension',question='Value and endpoint?',feature_ids=['d'])]
    p=validate_recognition(json.dumps(p),400,300)
    records=[dict(id='source',source='synthetic confirmation',text='It is a window; measured value accepted, endpoint unknown.',
        question_ids=['q','n'],resolves=['q'],dimensions=[dict(dimension_id='d',text='221.6',metres=2.216,text_box=[10,10,50,30])])]
    response=dict(features=[],dimensions=[],resolutions=[
        dict(question_id='q',status='resolved',answer='Confirmed window',evidence_ids=['source']),
        dict(question_id='n',status='partial',answer='Accepted value',evidence_ids=['source'],remaining_question='Which endpoint?')])
    return p,records,response


def test_confirmed_value_overrides_ocr_without_inventing_endpoints():
    p,records,response=inputs();original=copy.deepcopy(p)
    result,audit=apply_reconciliation(p,json.dumps(response),records,400,300)
    assert p==original and result['features']==p['features']
    d=result['dimensions'][0]
    assert (d['text'],d['raw_text'],d['metres'],d['start'])==('221.6','231.6',2.216,None)
    assert d['source_refs']==['source']
    assert [q['question'] for q in result['review']]==['Which endpoint?']
    assert audit['resolutions'][0]['status']=='resolved'


@pytest.mark.parametrize('change',['close_partial','wrong_source','unresolved_fake_source','missing_answer','duplicate_answer','unrelated_feature','unrelated_new_feature'])
def test_reject_unsupported_or_out_of_scope_repair(change):
    p,records,r=inputs()
    if change=='close_partial':r['resolutions'][1]['status']='resolved'
    if change=='wrong_source':r['resolutions'][0]['evidence_ids']=['absent']
    if change=='unresolved_fake_source':r['resolutions'][1].update(status='unresolved',evidence_ids=['absent'])
    if change=='missing_answer':r['resolutions'].pop()
    if change=='duplicate_answer':r['resolutions'][1]=r['resolutions'][0]
    if change in ('unrelated_feature','unrelated_new_feature'):
        f=copy.deepcopy(p['features'][1]);f['points'][0][0]=30
        if change=='unrelated_new_feature':f['id']='new'
        r['features']=[dict(feature=f,evidence_ids=['source'])]
    with pytest.raises(ValueError):apply_reconciliation(p,json.dumps(r),records,400,300)


@pytest.mark.parametrize('change',['conflict','unknown_question','unknown_dimension','crop_outside'])
def test_invalid_evidence_rejected_before_model_call(change):
    p,records,_=inputs()
    if change=='conflict':
        other=copy.deepcopy(records[0]);other['id']='other';other['dimensions'][0]['metres']=7;records.append(other)
    if change=='unknown_question':records[0]['resolves']=['absent']
    if change=='unknown_dimension':records[0]['dimensions'][0]['dimension_id']='absent'
    if change=='crop_outside':records[0]['dimensions'][0]['text_box']=[10,10,999,999]
    with pytest.raises(ValueError):validate_evidence(records,p,400,300)


def test_independent_reading_and_original_rotations(tmp_path):
    p,records,_=inputs();records=validate_evidence(records,p,400,300)
    source=tmp_path/'image.png';Image.new('RGB',(400,300),'white').save(source)
    files,manifest=digit_images(source,records,tmp_path)
    assert [Image.open(f).size for f in files]==[(120,60),(60,120),(60,120)]
    assert [m['rotation'] for m in manifest]==[0,90,270]
    assert '221.6' not in digit_prompt(manifest) and '231.6' not in digit_prompt(manifest)


def test_stop_between_digit_and_repair_does_not_call_model_again(tmp_path):
    p,records,_=inputs();source=tmp_path/'image.png';Image.new('RGB',(400,300)).save(source)
    calls=[]
    class Client:
        def run(self,*a,**kw):
            calls.append(a)
            return dict(text=json.dumps(dict(readings=[dict(dimension_id='d',text='231.6',confidence='low')])) )
    phases=[]
    def progress(phase):
        phases.append(phase)
        if len(phases)==2:raise RuntimeError('stopped')
    with pytest.raises(RuntimeError,match='stopped'):
        run_refinement(Client(),tmp_path,dict(image=source,candidate=p,evidence=records,width=400,height=300),'test',progress,lambda e:None)
    assert len(calls)==1 and (tmp_path/'digit-response.json').exists()


def test_refine_http_forks_saved_geometry_preserves_source_and_deduplicates(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='IMAGE',name='synthetic'))
    calls=[];p,records,response=inputs()
    def start(self,kind,model,payload,identifier):
        calls.append((kind,payload))
        if kind=='plan_refine':
            candidate,audit=apply_reconciliation(payload['candidate'],json.dumps(response),payload['evidence'],400,300)
        else:candidate,audit=p,None
        result=dict(id=identifier,status='passed',kind=kind,model=model,candidate=candidate,review_complete=True,evidence_review=audit)
        write_json(self.root/identifier/'task.json',result);return result
    with patch.object(Jobs,'loop',return_value=None),patch('interior.workbench.agent_runtime.service.AgentTasks.start',start):
        with TestClient(create_app(tmp_path),base_url='http://127.0.0.1') as c:
            h={'x-workbench-token':c.get('/api/session').json()['token']};url='/api/studio/projects/IMAGE'
            rec=c.post(url+'/image-plans/upload',files={'file':('plan.png',png())},headers=h).json()
            route=url+'/image-plans/'+rec['id']
            c.post(route+'/recognize',json={'model':'test'},headers=h)
            old=c.post(route+'/draft',headers=h).json()
            settings=copy.deepcopy(old['settings']);settings['assignments'][0]['height']=.25
            settings['assignments'][0]['offset']=[.1,0]
            saved=c.put(url+'/plans/'+rec['id'],json=dict(base_revision=old['revision'],settings=settings),headers=h).json()
            body=dict(base_revision=old['revision'],model='test',evidence=records)
            assert c.post(route+'/refine',json=body,headers=h).status_code==409
            body['base_revision']=saved['revision']
            a=c.post(route+'/refine',json=body,headers=h);assert a.status_code==200,a.text
            child=a.json();assert child['id']!=rec['id']
            assert c.post(route+'/refine',json=body,headers=h).json()['id']==child['id']
            assert len(calls)==2
            assert calls[-1][1]['candidate']['features'][0]['points'][0][0]>20
            new=c.post(url+'/image-plans/'+child['id']+'/draft',headers=h).json()
            assert new['settings']['assignments'][0]['height']==.25
            assert new['settings']['reviewed']==[] and not new['settings']['calibration']['confirmed']
            assert new['parsed']['recognition_audit']['evidence_review']['records'][0]['source']=='synthetic confirmation'
            assert c.get(route).json()['plan']['revision']==saved['revision']
            assert c.get(url+'/scene').json()['scene'] is None
            assert (tmp_path/'projects/image'/old['source']['path']).read_bytes()==png()
            (tmp_path/'projects/image'/old['source']['path']).write_bytes(b'tampered')
            assert c.post(route+'/refine',json=body,headers=h).status_code==422
