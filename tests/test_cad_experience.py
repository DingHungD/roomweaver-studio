"""Synthetic, isolated confirmation and cross-drawing retrieval contracts."""
import copy
import json
import math
from pathlib import Path
from uuid import uuid4

import ezdxf
import pytest
from PIL import Image,ImageDraw
from pydantic import ValidationError

from test_plan_semantics import system,candidate
from test_semantic_corrections import Agents
from interior.workbench.storage import write_json,Conflict
from interior.workbench.studio.plan_import import SavePlan
from interior.workbench.studio.plan_semantics import PlanSemantics,SemanticRequest
from interior.workbench.studio.experience_features import select_source,geometry_descriptor,image_descriptor,text_tokens,similarity
from interior.workbench.studio.experience_library import ExperienceLibrary
from interior.workbench.studio.experience_review import ExperienceReview,CreateExperience,ExperienceAnswer
from interior.workbench.studio.experience_retrieval import retrieve


def symbol(tmp_path,kind='swing',rotation=0,scale=1,offset=(0,0)):
    def p(x,y):return [offset[0]+scale*(x*math.cos(rotation)-y*math.sin(rotation)),offset[1]+scale*(x*math.sin(rotation)+y*math.cos(rotation))]
    pts=[p(math.cos(n*math.pi/24),math.sin(n*math.pi/24)) for n in range(13)]
    lines=[[[0,0],[1,0]],[[0,0],[0,1]]] if kind=='swing' else [[[0,.3],[1,.3]],[[0,.6],[1,.6]]]
    geometry=[dict(id='arc',kind='ARC',points=pts,closed=False)]+[dict(id='line'+str(n),kind='LINE',points=[p(*a) for a in pair],closed=False) for n,pair in enumerate(lines)]
    site=dict(geometry=geometry,texts=[],native_dwg=dict(entities=[dict(id='arc',kind='ARC',start_angle=rotation,end_angle=rotation+math.pi/2)]))
    points=[p for g in geometry for p in g['points']];xs,ys=zip(*points);bounds=[min(xs)-.02,min(ys)-.02,max(xs)+.02,max(ys)+.02]
    image=tmp_path/(uuid4().hex+'.png');pic=Image.new('RGB',(160,160),'white');d=ImageDraw.Draw(pic)
    for g in geometry:d.line([((p[0]-bounds[0])/(bounds[2]-bounds[0])*140+10,150-(p[1]-bounds[1])/(bounds[3]-bounds[1])*140) for p in g['points']],fill='black',width=3)
    pic.save(image);raw=select_source(site,bounds)
    descriptor=dict(geometry=geometry_descriptor(raw),image=image_descriptor(image),tokens=[])
    return site,bounds,descriptor,image


def entry(descriptor,interpretation='單開門'):
    return dict(title='Synthetic correction',interpretation=interpretation,mistake='椅子',reason='原生弧連接兩端徑向直線，需合看相鄰圖形',applies='本圖幾何與周邊一致時參考',exceptions='圓弧本身不能證明是門',descriptor=descriptor,annotations=[],provenance=dict(project='SYNTHETIC-TRAIN',synthetic=True))


@pytest.fixture
def service_case(system,tmp_path):
    studio,plans,_,_=system
    doc=ezdxf.new();doc.units=6;m=doc.modelspace();m.add_lwpolyline([(0,0),(8,0),(8,6),(0,6)],close=True,dxfattribs={'layer':'floor'});m.add_line((0,0),(8,0),dxfattribs={'layer':'wall'});m.add_text('Living room',dxfattribs={'insert':(2,3)});m.add_lwpolyline([(2,2),(3.4,2),(3.4,2.7),(2,2.7)],close=True,dxfattribs={'layer':'desk'})
    path=tmp_path/'new-furnished.dxf';doc.saveas(path);packet=plans.create('UNRELATED',path.name,path.read_bytes());settings=copy.deepcopy(packet['settings']);settings['cad_unit_confirmed']=True;settings['reviewed']=[q['id'] for q in packet['parsed']['cad_preparation']['questions']];packet=plans.save('UNRELATED',packet['id'],SavePlan(base_revision=packet['revision'],settings=settings))
    class NativeAgents(Agents):
        def start(self,kind,model,payload,identifier):
            super().start(kind,model,payload,identifier)
            desk=next(g for g in payload['site']['geometry'] if g['layer']=='desk')
            next(i for i in self.tasks[identifier]['candidate']['elements'] if i['id']=='desk')['source_ids']=[desk['id']]
    agents=NativeAgents();semantics=PlanSemantics(studio,agents);run=semantics.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='synthetic',operation_id=uuid4().hex))
    return ExperienceReview(semantics),packet,run,agents


def create_draft(service_case):
    service,packet,run,_=service_case
    return service.create('UNRELATED',packet['id'],CreateExperience(base_revision=packet['revision'],review_id=run['id'],target_id='desk'))


def answer(draft):
    return ExperienceAnswer(draft_revision=draft['revision'],title='Synthetic desk confirmation',interpretation='桌子',mistake='櫃子',reason='閉合桌面及周邊使用空間',applies='僅幾何與註解相符時參考',exceptions='不可照搬尺寸',confirmed=True)


def test_draft_is_private_until_explicit_confirmation_and_never_adopts(service_case):
    service,packet,run,_=service_case;before=copy.deepcopy(packet)
    draft=create_draft(service_case)
    assert service.library.summary()['active']==0 and not service.search('UNRELATED',packet['id'],draft['id'])['hits']
    assert service.list('UNRELATED',packet['id'])['drafts'][0]['id']==draft['id']
    confirmed=service.confirm('UNRELATED',packet['id'],draft['id'],answer(draft))
    assert confirmed['confirmed'] and service.library.summary()['active']==1
    assert service.search('UNRELATED',packet['id'],draft['id'])['hits'][0]['interpretation']=='桌子'
    assert service.semantics.plans.current('UNRELATED',packet['id'])==before
    with pytest.raises(Conflict):service.confirm('UNRELATED',packet['id'],draft['id'],answer(draft))


@pytest.mark.parametrize('update',[dict(confirmed=False),dict(confirmed=None)])
def test_confirmation_cannot_be_inferred_from_saving_a_draft(service_case,update):
    draft=create_draft(service_case)
    data=answer(draft).model_dump();data.update(update)
    with pytest.raises(ValidationError):ExperienceAnswer(**data)
    assert service_case[0].library.summary()['active']==0


def test_changed_crop_cannot_be_confirmed(service_case):
    service,packet,_,_=service_case;draft=create_draft(service_case)
    Image.new('RGB',(20,20),'red').save(service.folder('UNRELATED',packet['id'])/draft['id']/'source.png')
    with pytest.raises(Conflict,match='圖片已變動'):service.confirm('UNRELATED',packet['id'],draft['id'],answer(draft))
    assert service.library.summary()['active']==0


def test_new_review_invalidates_old_confirmation_without_erasing_draft(service_case):
    service,packet,run,_=service_case;draft=create_draft(service_case)
    service.semantics.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='synthetic',operation_id=uuid4().hex))
    with pytest.raises(Conflict,match='判讀已更新'):service.confirm('UNRELATED',packet['id'],draft['id'],answer(draft))
    assert service.get('UNRELATED',packet['id'],draft['id'])['status']=='draft'


def test_search_uses_native_shapes_even_when_agent_category_is_wrong(tmp_path):
    site,bounds,desc,image=symbol(tmp_path);before=copy.deepcopy(site)
    site['agent_guess']='chair';raw=select_source(site,bounds);assert geometry_descriptor(raw)==desc['geometry']
    assert all(k not in desc for k in ('category','role','agent_guess'))
    library=ExperienceLibrary(tmp_path/'library');correct=library._publish_confirmed(entry(desc),image)
    other,_,chair,picture=symbol(tmp_path,'chair');library._publish_confirmed(entry(chair,'椅子'),picture)
    results=library.search(desc);assert results['hits'][0]['id']==correct['id'] and len(results['hits'])==2
    assert site['geometry']==before['geometry']


def test_native_signature_generalizes_rotation_translation_and_scale(tmp_path):
    _,_,base,_=symbol(tmp_path)
    _,_,changed,_=symbol(tmp_path,rotation=math.pi/2,scale=2,offset=(200,-90))
    assert changed['geometry']['vector']==pytest.approx(base['geometry']['vector'],abs=.001)
    assert similarity(changed,base)['image']>.85


def test_confirmed_dedup_retains_counterexamples_and_bounds_context(tmp_path):
    _,_,desc,image=symbol(tmp_path);lib=ExperienceLibrary(tmp_path/'library')
    first=lib._publish_confirmed(entry(desc),image);assert lib._publish_confirmed(entry(desc),image)['id']==first['id']
    for n in range(8):lib._publish_confirmed(entry(desc,'不同解釋'+str(n)),image)
    result=lib.search(desc,100);assert len(result['hits'])==5 and result['library_count']==9 and result['examined']<=432
    assert len({i['interpretation'] for i in result['hits']})>1


def test_annotations_and_pixels_are_independent_inputs(tmp_path):
    _,_,desc,image=symbol(tmp_path);changed=copy.deepcopy(desc);changed['tokens']=text_tokens('門扇開啟');changed['image']=[[0.]*64]*4
    assert similarity(desc,desc)['image']>similarity(desc,changed)['image']
    assert similarity(dict(desc,tokens=changed['tokens']),dict(desc,tokens=changed['tokens']))['annotations']==1


def test_empty_library_does_not_create_or_search_unconfirmed_data(tmp_path):
    _,_,desc,_=symbol(tmp_path);root=tmp_path/'empty';result=ExperienceLibrary(root).search(desc)
    assert result['hits']==[] and not root.exists()


def test_worker_attaches_bounded_confirmed_examples_and_records_search(tmp_path):
    site,bounds,desc,image=symbol(tmp_path);lib=ExperienceLibrary(tmp_path/'library');lib._publish_confirmed(entry(desc),image)
    payload=dict(site=dict(site,source_view=dict(bounds=bounds,scale=140/(bounds[2]-bounds[0]),pad=10)),image=str(image),experience_library=str(lib.root))
    examples,images=retrieve(payload,[dict(id='unknown-native-symbol',box=bounds,source_ids=['arc'])],tmp_path/'run')
    assert examples['hits'] and len(images)<=3 and (tmp_path/'run/retrieval.json').exists()
    assert examples['hits'][0]['current_candidates']==['unknown-native-symbol']
    assert '歷史來源ID' in examples['policy']


def test_high_pixel_similarity_cannot_override_unrelated_geometry(tmp_path):
    _,_,desc,image=symbol(tmp_path);wrong=copy.deepcopy(desc);wrong['geometry']['vector']=[5.]*len(desc['geometry']['vector'])
    library=ExperienceLibrary(tmp_path/'library');library._publish_confirmed(entry(wrong),image)
    assert library.search(desc)['hits']==[]


def test_saving_edited_experience_stays_private_and_reopens_with_version(service_case):
    from interior.workbench.studio.experience_review import ExperienceFields
    service,packet,_,_=service_case;draft=create_draft(service_case);data=answer(draft).model_dump(exclude={'confirmed'})
    saved=service.save('UNRELATED',packet['id'],draft['id'],ExperienceFields(**data))
    assert saved['revision']!=draft['revision'] and saved['status']=='draft'
    assert service.get('UNRELATED',packet['id'],draft['id'])['mistake']=='櫃子'
    assert service.library.summary()['active']==0
    with pytest.raises(Conflict):service.save('UNRELATED',packet['id'],draft['id'],ExperienceFields(**data))


def test_http_confirmation_requires_token_and_explicit_true_and_does_not_adopt(service_case):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from interior.workbench.server import create_app
    from interior.workbench.jobs import Jobs
    service,packet,run,agents=service_case;store=service.semantics.studio.store
    with patch.object(Jobs,'loop',return_value=None):app=create_app(store.workspace,store.state_dir)
    app.state.plan_semantics.agents=agents
    endpoint=f"/api/studio/projects/UNRELATED/plans/{packet['id']}/experience-drafts"
    with TestClient(app,base_url='http://127.0.0.1') as client:
        headers={'X-Workbench-Token':client.get('/api/session').json()['token']}
        body=dict(base_revision=packet['revision'],review_id=run['id'],target_id='desk')
        assert client.post(endpoint,json=body).status_code==403
        response=client.post(endpoint,json=body,headers=headers);assert response.status_code==200,response.text
        draft=response.json();data=answer(draft).model_dump();data.pop('confirmed')
        assert client.post(endpoint+'/'+draft['id']+'/confirm',json=data,headers=headers).status_code==422
        assert client.get(endpoint).json()['library']['active']==0
        data['confirmed']=True
        response=client.post(endpoint+'/'+draft['id']+'/confirm',json=data,headers=headers);assert response.status_code==200,response.text
        assert client.get(endpoint).json()['library']['active']==1
        assert service.semantics.plans.current('UNRELATED',packet['id'])==packet


def test_deactivation_preserves_history_and_excludes_future_search(tmp_path):
    _,_,desc,image=symbol(tmp_path);library=ExperienceLibrary(tmp_path/'library');item=library._publish_confirmed(entry(desc),image)
    library.deactivate(item['id'],item['revision'])
    assert library.search(desc)['hits']==[] and library.summary()['active']==0
    assert library.image_path(item['id']).exists()
    assert list((library.root/'entries'/item['id']).glob('deactivated-*.json'))
    with pytest.raises(Conflict):library._publish_confirmed(entry(desc),image)


def test_successful_batch_creates_private_cards_in_worker_and_retries_do_not_duplicate(service_case,tmp_path):
    from test_semantic_corrections import item,save,request
    from interior.workbench.studio.plan_semantics import run_semantics
    from interior.workbench.studio.experience_review import prepare_batch_experiences
    service,packet,run,agents=service_case;semantics=service.semantics
    before=copy.deepcopy(packet)
    saved=save(semantics,packet,run,[item(1),item(2),item(3)])
    reviewed=semantics.start('UNRELATED',packet['id'],request(packet,run,saved,[item(1)['id'],item(3)['id']]))
    payload=agents.calls[-1][1];raw=agents.tasks[reviewed['id']]['candidate']
    class Client:
        calls=0
        def run(self,*args,**kwargs):
            item=payload['site']['correction_batch']['items'][self.calls];self.calls+=1
            marks=[dict(mark_id=m['id'],status='no_change',expected_kind='room',object_ids=[raw['rooms'][0]['id']],summary='Source room contains this unchanged mark') for m in item['marks']]
            return dict(text=json.dumps(dict(status='no_change',summary='Retain verified source region',operations=[],mark_results=marks)))
    result=run_semantics(Client(),tmp_path,payload,'synthetic',lambda _:None,lambda _:None)
    agents.tasks[reviewed['id']]=dict(status='passed',**result)
    prepared=result['experience_preparation'];assert len(prepared['items'])==2
    assert all(row['status']=='draft' for row in prepared['items'])
    drafts=service.list('UNRELATED',packet['id'])['drafts']
    assert {d['target_id'] for d in drafts}=={item(1)['id'],item(3)['id']}
    assert all(d['automatic'] and not d['confirmed'] and d['status']=='draft' for d in drafts)
    assert service.library.summary()['active']==0
    again=prepare_batch_experiences(payload,result['candidate'],result['semantic_report'])
    assert again==prepared and len(service.list('UNRELATED',packet['id'])['drafts'])==2
    assert semantics.plans.current('UNRELATED',packet['id'])==before
    # A real explicit confirmation still works against the same successful batch.
    confirmed=service.confirm('UNRELATED',packet['id'],drafts[0]['id'],answer(drafts[0]))
    assert confirmed['confirmed'] and service.library.summary()['active']==1
    assert semantics.plans.current('UNRELATED',packet['id'])==before


def test_automatic_cards_skip_failed_items_and_report_missing_positions(service_case):
    from test_semantic_corrections import item,save,request
    from interior.workbench.studio.experience_review import prepare_batch_experiences
    service,packet,run,agents=service_case;semantics=service.semantics
    rows=[item(1),item(2),item(3)];rows[2]['marks']=[]
    saved=save(semantics,packet,run,rows)
    reviewed=semantics.start('UNRELATED',packet['id'],request(packet,run,saved,[i['id'] for i in rows]))
    payload=agents.calls[-1][1]
    report=dict(corrections=[dict(id=i['id'],status='corrected',preview_ready=True,summary='Validated corrected interpretation') for i in rows])
    report['corrections'][1].update(status='unresolved',preview_ready=False,summary='Source is ambiguous')
    result=prepare_batch_experiences(payload,reviewed['task']['candidate'],report)
    assert [r['status'] for r in result['items']]==['draft','skipped','error']
    assert '圖上位置' in result['items'][2]['reason']
    assert len(service.list('UNRELATED',packet['id'])['drafts'])==1
    assert service.library.summary()['active']==0


def test_unrelated_draft_and_batch_do_not_invalidate_unchanged_correction_card(service_case):
    from test_semantic_corrections import item,save,request
    service,packet,run,_=service_case;semantics=service.semantics
    saved=save(semantics,packet,run,[item(1),item(2)])
    first=semantics.start('UNRELATED',packet['id'],request(packet,run,saved,[item(1)['id']]))
    draft=service.create('UNRELATED',packet['id'],CreateExperience(base_revision=packet['revision'],review_id=first['id'],kind='correction',target_id=item(1)['id']))
    saved=save(semantics,packet,first,[item(1),item(2),item(3)],saved['revision'])
    second=semantics.start('UNRELATED',packet['id'],request(packet,first,saved,[item(2)['id']]))
    assert service.library.summary()['active']==0
    assert service.confirm('UNRELATED',packet['id'],draft['id'],answer(draft))['confirmed']
    assert semantics.plans.current('UNRELATED',packet['id'])==packet
    # A later edit to the item itself still blocks an unconfirmed card.
    next_draft=service.create('UNRELATED',packet['id'],CreateExperience(base_revision=packet['revision'],review_id=second['id'],kind='correction',target_id=item(2)['id']))
    edited=item(2);edited['comment']='Changed source interpretation'
    save(semantics,packet,second,[item(1),edited,item(3)],saved['revision'])
    with pytest.raises(Conflict,match='尚無同版'):service.confirm('UNRELATED',packet['id'],next_draft['id'],answer(next_draft))
