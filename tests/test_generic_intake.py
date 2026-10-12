"""Generic question feedback and editable concepts, using synthetic data only."""
import copy,json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from interior.workbench.server import create_app
from interior.workbench.storage import Store,write_json
from interior.workbench.jobs import Jobs
from interior.workbench.studio.image_plan import validate_recognition
from interior.workbench.studio.image_review import prepare_review,question_notes
from interior.workbench.studio.image_evidence import apply_reconciliation
from interior.workbench.studio.models import ConceptFurniture,Scene
from interior.workbench.studio.service import Studio
from test_image_plan import proposal,png
from test_workbench_studio import synthetic_scene,MODEL

def test_bounded_agent_retry_does_not_expand_evidence_scope(tmp_path):
    from test_image_evidence import inputs
    from interior.workbench.studio.image_evidence import run_refinement
    from PIL import Image
    p,records,response=inputs();records[0]['dimensions']=[]
    invalid=copy.deepcopy(response);invalid['features']=[dict(feature=p['features'][0],evidence_ids=['source'])]
    source=tmp_path/'new.png';Image.new('RGB',(400,300),'white').save(source)
    class Client:
        calls=0
        def run(self,prompt,**kw):
            self.calls+=1
            if self.calls==2:assert '可修改 ID' in prompt
            return dict(text=json.dumps(invalid if self.calls==1 else response))
    client=Client();result=run_refinement(client,tmp_path,dict(image=source,candidate=p,evidence=records,width=400,height=300),'fake',lambda p:None,lambda e:None)
    assert client.calls==2 and result['candidate']['features']==p['features']
    assert [a['status'] for a in result['evidence_review']['attempts']]==['rejected','passed']

def test_missing_region_allows_only_local_supported_addition():
    from test_image_evidence import inputs
    p,records,response=inputs();p['review'][0].update(kind='missing',regions=[[10,10,100,100]])
    new=copy.deepcopy(p['features'][1]);new.update(id='missing-wall',role='wall',points=[[20,20],[80,20]],closed=False)
    response['features']=[dict(feature=new,evidence_ids=['source'])]
    result,_=apply_reconciliation(p,json.dumps(response),records,400,300)
    assert len(result['features'])==len(p['features'])+1
    new['points'][1]=[300,20]
    with pytest.raises(ValueError,match='超出'):apply_reconciliation(p,json.dumps(response),records,400,300)

@pytest.mark.parametrize('count',[0,1,3])
def test_questions_follow_each_new_input_and_pixel_bounds(count):
    p=proposal();p['review']=[dict(id=f'new{i}',kind='classification',feature_ids=['window'] if i%2==0 else [],question=f'Unknown symbol {i}?') for i in range(count)]
    p=validate_recognition(json.dumps(p),400,300)
    p,a,q=prepare_review(p,400,300,reviewed=True)
    notes=question_notes(p,q,400,300)
    for i in range(count):
        note=next(n for n in notes if n['question_id']==f'agent-new{i}')
        box=note['regions'][0]['box'];assert 0<=box[0]<box[2]<=400 and 0<=box[1]<box[3]<=300
        if i%2:assert '無可靠局部位置' in note['ask']
    assert not any('Project03' in str(n) or 'Q2' in n['question_id'] for n in notes)

def test_confirmed_numeric_value_and_provenance_cannot_be_erased():
    from test_image_evidence import inputs
    p,records,r=inputs();p['dimensions'][0].update(source_refs=['previous-confirmation'],metres=2.216,raw_text='231.6')
    records[0]['dimensions']=[]
    d=copy.deepcopy(p['dimensions'][0]);d.update(source_refs=[],metres=2.316)
    r['dimensions']=[dict(dimension=d,evidence_ids=['source'])]
    with pytest.raises(ValueError,match='已確認尺寸'):apply_reconciliation(p,json.dumps(r),records,400,300)
    d['metres']=2.216
    result,_=apply_reconciliation(p,json.dumps(r),records,400,300)
    assert set(result['dimensions'][0]['source_refs'])=={'previous-confirmation','source'}

def test_ui_feedback_persistence_scope_conflicts_and_stale_fork(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='NEW',name='Synthetic new image'))
    def start(self,kind,model,payload,identifier):
        candidate=payload.get('candidate') or validate_recognition(json.dumps(dict(proposal(),review=[dict(id='symbol',kind='classification',question='What is this?',feature_ids=['window'])])),400,300)
        task=dict(id=identifier,status='passed',candidate=candidate,review_complete=True,model=model)
        write_json(self.root/identifier/'task.json',task);return task
    with patch.object(Jobs,'loop',return_value=None),patch('interior.workbench.agent_runtime.service.AgentTasks.start',start),TestClient(create_app(tmp_path),base_url='http://127.0.0.1') as c:
        h={'x-workbench-token':c.get('/api/session').json()['token']};base='/api/studio/projects/NEW'
        image=c.post(base+'/image-plans/upload',files={'file':('new.png',png())},headers=h).json();url=base+'/image-plans/'+image['id']
        assert c.post(url+'/recognize',json=dict(model='fake'),headers=h).status_code==200
        p=c.post(url+'/draft',headers=h).json();assert p['settings']['question_notes']
        records=[dict(id='receipt',source='Synthetic owner response',text='It is a window.',question_ids=['agent-symbol'],resolves=['agent-symbol'],dimensions=[])]
        body=dict(base_revision=p['revision'],base_feedback_id=None,evidence=records)
        saved=c.put(url+'/feedback',json=body,headers=h);assert saved.status_code==200,saved.text
        assert c.get(url+'/feedback').json()['evidence'][0]['text']=='It is a window.'
        assert c.put(url+'/feedback',json=body,headers=h).status_code==409
        bad=copy.deepcopy(body);bad['base_feedback_id']=saved.json()['id'];bad['evidence'][0]['question_ids']=['foreign']
        assert c.put(url+'/feedback',json=bad,headers=h).status_code==422
        child=c.post(url+'/refine',json=dict(base_revision=p['revision'],model='fake',evidence=records),headers=h);assert child.status_code==200,child.text
        settings=copy.deepcopy(p['settings']);settings['assignments'][0]['height']=.22
        assert c.put(base+'/plans/'+image['id'],json=dict(base_revision=p['revision'],settings=settings),headers=h).status_code==200
        result=c.post(base+'/image-plans/'+child.json()['id']+'/draft',headers=h)
        assert result.status_code==409 and '更新' in result.text

def test_new_furniture_roundtrip_undo_and_reject_forged_parts(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='CONCEPT',name='Synthetic'))
    with patch.object(Jobs,'loop',return_value=None):jobs=Jobs(store)
    try:
        studio=Studio(store,jobs)
        write_json(studio.root('CONCEPT')/'runs/interior-studio'/MODEL/'model.json',dict(objects=[dict(id='wall',name='Wall'),dict(id='sofa',name='Sofa')]))
        first=studio.save('CONCEPT',synthetic_scene(),None);s=copy.deepcopy(first['scene'])
        f=ConceptFurniture(id='concept-'+'b'*32,name='New chair',asset='chair',size=(.5,.5,.85)).model_dump(mode='json')
        s['concept_furniture']=[f];s['objects'] +=[dict(id=p['id'],name=p['name'],material={}) for p in f['parts']]
        s['groups'].append(dict(id=f['id'],name=f['name'],children=[p['id'] for p in f['parts']],translation=[2,3,0],deleted=False,method='concept'))
        saved=studio.save('CONCEPT',s,first['revision']);assert len(studio.current('CONCEPT')['scene']['concept_furniture'])==1
        s['groups'][-1]['deleted']=True;deleted=studio.save('CONCEPT',s,saved['revision']);assert deleted['scene']['groups'][-1]['deleted']
        reverted=studio.save('CONCEPT',first['scene'],deleted['revision']);assert reverted['scene']['concept_furniture']==[]
        bad=copy.deepcopy(s);bad['concept_furniture'][0]['parts'][0]['size'][0]=9
        with pytest.raises(ValueError):Scene.model_validate(bad)
        bad=copy.deepcopy(s);bad['objects'].pop()
        with pytest.raises(ValueError):Scene.model_validate(bad)
    finally:jobs.close()
