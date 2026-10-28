"""Synthetic source ledgers and scoped local reviews; never client CAD fixtures."""
import copy
import json
from pathlib import Path

import pytest
from PIL import Image
from test_plan_semantics import system,candidate
from interior.workbench.studio.cad_candidates import VERSION,inventory,assess,apply_report,fingerprint
from interior.workbench.studio.semantic_local_review import apply_patch,local_packet,run_local_reviews
from interior.workbench.studio.plan_semantics import validate
from interior.workbench.agent_runtime.codex import ModelAccessError


def fixture(system):
    _,_,_,original=system;site=copy.deepcopy(original)
    site['coverage_version']=VERSION
    site['texts'].append(dict(id='text-fridge',text='冰箱 60×60',point=[5.3,2.3]))
    site['geometry'].append(dict(id='g-fridge',kind='LWPOLYLINE',layer='furniture',native_exact=True,closed=True,points=[[5,2],[5.6,2],[5.6,2.6],[5,2.6]]))
    raw=candidate(site);raw,report=validate(site,raw)
    item=next(i for i in assess(site,raw,report)['items'] if i['kind']=='furniture')
    return site,raw,report,item


def response(item,action='mapped',patch=None):
    return dict(decisions=[dict(candidate_id=item['id'],action=action,object_ids=['fridge'],source_ids=item['source_ids'],reason='Native appliance label and its closed footprint',ask='請確認此註記是否為既有冰箱或新增需求？' if action=='question' else '')],patch=patch or {})


def fridge_patch():
    return dict(elements=[dict(id='fridge',name='冰箱',role='furniture',room_id='living',points=[[5,2],[5.6,2],[5.6,2.6],[5,2.6]],closed=True,height=1.8,base=0,category='appliance',source_ids=['g-fridge','text-fridge'],evidence='Native label and outline')])


def test_reviewed_symbolic_glass_door_uses_exact_native_source_not_automatic_guess():
    from interior.workbench.studio.cad_candidates import matches
    row=dict(id='arc-candidate',kind='door',source_ids=['arc'],box=[0,0,1,1])
    proposal=dict(rooms=[],elements=[],lighting=[],drawing_objects=[dict(id='screen',name='淋浴玻璃門',source_ids=['arc','frame'],layer='other',category='other')])
    assert matches(row,proposal)==[]
    assert matches(row,proposal,components=True)==['screen']
    proposal['drawing_objects'][0]['source_ids']=['other-arc']
    assert matches(row,proposal,components=True)==[]


def test_saved_local_proposals_are_revalidated_only_for_same_source_and_selection(system,tmp_path):
    from interior.workbench.studio.semantic_local_review import replay_saved_reviews
    from interior.workbench.storage import write_json
    site,base,report,item=fixture(system)
    previous='1'*32;site['previous_review']=dict(task_id=previous)
    site['correction_batch']=dict(draft_revision='2'*32,items=[dict(id='cor-'+'3'*32,comment='Keep the appliance',marks=[])],selected_ids=['cor-'+'3'*32])
    original=copy.deepcopy(site)
    write_json(tmp_path/previous/'request.json',dict(source_revision=site['reference_revision'],site=original))
    folder=tmp_path/previous/'local-reviews/01'
    write_json(folder/'request.json',dict(packet=local_packet(site,base,[item])))
    write_json(folder/'response-1.json',response(item,patch=fridge_patch()))
    updated,_,decisions,evidence=replay_saved_reviews(site,base,report,tmp_path/'new',validate)
    assert any(e['id']=='fridge' for e in updated['elements']) and item['id'] in decisions and evidence
    assert site==original and not any(e['id']=='fridge' for e in base['elements'])
    changed=copy.deepcopy(site);changed['correction_batch']['selected_ids']=[]
    assert replay_saved_reviews(changed,base,report,tmp_path/'other',validate)[2:]==({},[])
    changed=copy.deepcopy(site);changed['geometry'][0]['points'][0][0]+=.1
    assert replay_saved_reviews(changed,base,report,tmp_path/'other',validate)[2:]==({},[])


def test_inventory_is_stable_and_noise_is_not_one_object_per_stroke(system):
    site,base,report,item=fixture(system);before=copy.deepcopy(site)
    for n in range(100):site['geometry'].append(dict(id='hatch-'+str(n),kind='HATCH',closed=False,points=[[0,n*.01],[1,n*.01]]))
    first=inventory(site);other=copy.deepcopy(site);other['geometry'].reverse();other['texts'].reverse()
    assert {i['id'] for i in first}=={i['id'] for i in inventory(other)}
    assert len(first)==2 and all(not any(r.startswith('hatch-') for r in i['source_ids']) for i in first)
    assert before['texts']==site['texts']
    coverage=assess(site,base,report);assert coverage['counts']['matched']==1 and coverage['counts']['pending']==1
    # Citing a text on a wall is not a correctly typed furniture interpretation.
    base['elements'][0]['source_ids'].append('text-fridge')
    assert next(i for i in assess(site,base,report)['items'] if i['id']==item['id'])['status']=='pending'


def test_local_patch_fixes_an_omission_without_deleting_necessary_furniture(system):
    site,base,report,item=fixture(system);old=copy.deepcopy(base);source=copy.deepcopy(site)
    updated,report,decisions=apply_patch(site,base,[item],response(item,patch=fridge_patch()),validate)
    assert next(i for i in updated['elements'] if i['id']=='desk')==next(i for i in base['elements'] if i['id']=='desk')
    assert assess(site,updated,report,decisions)['counts']['pending']==0
    assert base==old and site==source


def test_local_coordinate_fix_cannot_succeed_when_binding_restores_old_shape(system):
    site,base,report,item=fixture(system)
    base,_,_=apply_patch(site,base,[item],response(item,patch=fridge_patch()),validate)
    def source_owned(site,raw):
        raw=copy.deepcopy(raw)
        next(e for e in raw['elements'] if e['id']=='fridge')['points']=fridge_patch()['elements'][0]['points']
        return validate(site,raw)
    raw=response(item,patch=dict(elements=[dict(id='fridge',points=[[5,2],[5.5,2],[5.5,2.6],[5,2.6]],evidence='Claimed repaired')]))
    with pytest.raises(ValueError,match='幾何修正未生效'):
        apply_patch(site,base,[item],raw,source_owned)


@pytest.mark.parametrize('change',[
    lambda raw:raw['decisions'].append(copy.deepcopy(raw['decisions'][0])),
    lambda raw:raw['decisions'][0].update(source_ids=['invented']),
    lambda raw:raw['decisions'][0].update(reason=''),
    lambda raw:raw.update(patch=dict(remove_ids=['desk'])),
    lambda raw:raw.update(patch=dict(elements=[dict(id='desk',height=.3)])),
    lambda raw:raw.update(patch=dict(elements=[dict(id='desk',points=[[0,0],[1,0],[1,1],[0,1]])])),
    lambda raw:raw['patch']['elements'][0].update(points=[[20,20],[21,20],[21,21],[20,21]]),
])
def test_invalid_unrelated_or_unsupported_patches_cannot_clear_ledger(system,change):
    site,base,report,item=fixture(system);before=copy.deepcopy(base);raw=response(item,patch=fridge_patch());change(raw)
    with pytest.raises((ValueError,KeyError)):apply_patch(site,base,[item],raw,validate)
    assert base==before and assess(site,base,report)['counts']['pending']==1


def test_mapped_claim_needs_actual_mapping_and_ignore_needs_provenance(system):
    site,base,report,item=fixture(system)
    with pytest.raises(ValueError,match='仍不符'):apply_patch(site,base,[item],response(item),validate)
    updated,checked,decisions=apply_patch(site,base,[item],response(item,'ignore'),validate)
    ledger=assess(site,updated,checked,decisions);assert ledger['counts']['ignored']==1
    saved=copy.deepcopy(ledger);assert apply_report(site,base,copy.deepcopy(report),saved)['coverage']['counts']['ignored']==1
    # A changed candidate cannot borrow a previous ignore decision.
    altered=copy.deepcopy(base);altered['summary']='Different review'
    assert apply_report(site,altered,copy.deepcopy(report),saved)['coverage']['counts']['pending']==1


def test_only_evidence_backed_uncertainty_becomes_stable_located_question(system):
    site,base,report,item=fixture(system)
    updated,checked,decisions=apply_patch(site,base,[item],response(item,'question'),validate)
    ledger=assess(site,updated,checked,decisions);merged=apply_report(site,updated,checked,ledger)
    q=merged['questions'][0]
    assert q['id']=='audit-'+item['id'][4:] and q['box']==item['box'] and q['located']
    assert merged['coverage']['counts']['question']==1 and merged['status']=='blocked'
    assert not merged['repair_errors'] and merged['requires_confirmation']
    assert q['source_ids']==item['source_ids']


def test_real_source_options_merge_alternatives_but_keep_separate_frames():
    site=dict(geometry=[],texts=[],dimensions=[],native_dwg=dict(frame_options=[
        dict(points=[[0,0],[1,0]],refs=[dict(id='a',edge=0),dict(id='b',edge=0)],source_ids=['a','b']),
        dict(points=[[0,.02],[1,.02]],refs=[dict(id='c',edge=0),dict(id='d',edge=0)],source_ids=['c','d']),
        dict(points=[[2,0],[3,0]],refs=[dict(id='e',edge=0),dict(id='f',edge=0)],source_ids=['e','f'])]))
    rows=inventory(site);assert len(rows)==2
    assert len(next(i for i in rows if len(i['source_ids'])==4)['options'])==2


def test_bounded_local_review_crops_and_persists_actual_patch(system,tmp_path):
    site,base,report,item=fixture(system);site['source_view']=dict(width=800,height=600,bounds=[0,0,8,6],scale=100,pad=0)
    image=tmp_path/'source.png';Image.new('RGB',(800,600),'white').save(image)
    class Client:
        calls=[]
        def run(self,prompt,**kwargs):self.calls.append((prompt,kwargs));return dict(text=json.dumps(response(item,patch=fridge_patch())))
    client=Client();payload=dict(site=site,image=str(image),result_path=str(tmp_path/'result.json'))
    updated,report,coverage,rounds=run_local_reviews(client,tmp_path,payload,'fixture',base,report,lambda x:None,lambda x:None,validate)
    assert len(client.calls)==1 and client.calls[0][1]['images']
    assert coverage['counts']['pending']==0 and len(rounds)==1
    assert (tmp_path/'coverage.json').exists() and (tmp_path/'local-reviews/01/request.json').exists()
    assert Image.open(client.calls[0][1]['images'][0]).size!=(800,600)
    assert next(i for i in updated['elements'] if i['id']=='fridge')['height']==1.8


def test_invalid_local_reply_retries_but_stays_pending_not_a_fake_human_q(system,tmp_path):
    site,base,report,item=fixture(system);site['source_view']=dict(width=800,height=600,bounds=[0,0,8,6],scale=100,pad=0)
    image=tmp_path/'source.png';Image.new('RGB',(800,600),'white').save(image)
    class Client:
        calls=0
        def run(self,*args,**kwargs):self.calls+=1;return dict(text='{"decisions":[],"patch":{}}')
    client=Client();before=copy.deepcopy(base)
    updated,report,coverage,rounds=run_local_reviews(client,tmp_path,dict(site=site,image=str(image)),'fixture',base,report,lambda x:None,lambda x:None,validate)
    assert client.calls==2 and updated==before
    assert coverage['counts']['pending']==1 and coverage['counts']['question']==0 and not report['questions']
    assert report['status']=='blocked' and rounds[0]['error']
    rechecked=apply_report(site,updated,validate(site,updated)[1],coverage)
    assert '未通過' in next(i for i in rechecked['coverage']['items'] if i['status']=='pending')['reason']


def test_account_model_failure_stops_without_repeated_calls_or_fallback(system,tmp_path):
    site,base,report,item=fixture(system);site['source_view']=dict(width=800,height=600,bounds=[0,0,8,6],scale=100,pad=0)
    image=tmp_path/'source.png';Image.new('RGB',(800,600),'white').save(image)
    class Client:
        calls=0
        def run(self,*args,**kwargs):self.calls+=1;raise ModelAccessError('unavailable')
    client=Client()
    with pytest.raises(ModelAccessError):run_local_reviews(client,tmp_path,dict(site=site,image=str(image)),'fixture',base,report,lambda x:None,lambda x:None,validate)
    assert client.calls==1

def test_frame_can_be_a_verified_part_of_a_complete_native_furniture():
    from test_native_intake import source_case
    site,raw=source_case();site['geometry'].append(dict(id='sofa-source',layer='mixed',kind='LWPOLYLINE',closed=True,native_exact=True,points=[[2,4],[6,4],[6,5],[2,5]]))
    base,report=validate(site,raw)
    row=dict(id='cad-frame-fixture',kind='frame',label='A small furniture frame segment',source_ids=['sofa-source'],box=[5.42,3.92,6.08,4.08],options=[dict(points=[[5.5,4],[6,4]])])
    new=dict(id='sofa',name='Sofa',role='furniture',room_id='living',points=[[2,4],[6,4],[6,5],[2,5]],closed=True,height=.8,base=0,category='sofa',source_ids=['sofa-source'],evidence='Complete native parent outline',source_binding=dict(method='outline',refs=[dict(id='sofa-source',edge=0)]))
    reply=response(row,patch=dict(elements=[new]));reply['decisions'][0]['object_ids']=['sofa']
    updated,report,decisions=apply_patch(site,base,[row],reply,validate)
    assert next(i for i in updated['elements'] if i['id']=='sofa')['points']==new['points']
    assert assess(site,updated,report,decisions,records=[row])['counts']['matched']==1
    assert next(i for i in updated['elements'] if i['id']=='cabinet')==next(i for i in base['elements'] if i['id']=='cabinet')


def test_human_question_is_challenged_before_reaching_ui(system,tmp_path):
    site,base,report,item=fixture(system);site['source_view']=dict(width=800,height=600,bounds=[0,0,8,6],scale=100,pad=0)
    image=tmp_path/'source.png';Image.new('RGB',(800,600),'white').save(image)
    class Client:
        calls=0
        def run(self,prompt,**kwargs):
            self.calls+=1
            if self.calls==2:assert '提出Q前再次查證' in prompt
            return dict(text=json.dumps(response(item,'question') if self.calls==1 else response(item,patch=fridge_patch())))
    client=Client();updated,checked,coverage,rounds=run_local_reviews(client,tmp_path,dict(site=site,image=str(image)),'fixture',base,report,lambda x:None,lambda x:None,validate)
    assert client.calls==2 and coverage['counts']['pending']==0 and coverage['counts']['question']==0
    assert (tmp_path/'local-reviews/01/question-recheck.json').exists()
    assert not checked['questions']


def test_stopped_task_can_preview_bound_checkpoint_but_cannot_adopt(system):
    from test_semantic_corrections import setup
    from interior.workbench.storage import write_json,Conflict
    from interior.workbench.studio.plan_semantics import AdoptSemantics
    from interior.workbench.studio.cad_candidates import source_hash
    service,packet,run,agents=setup(system);folder=service.folder('UNRELATED',packet['id'])/'runs'/run['id']
    proposal=run['task']['candidate'];report=run['task']['semantic_report'];coverage=assess(run['site'],proposal,report)
    checkpoint=dict(candidate=proposal,coverage=coverage,source_revision=run['source_revision'],source_hash=source_hash(run['site']))
    write_json(folder/'local-checkpoint.json',checkpoint);agents.tasks[run['id']]={'status':'stopped'}
    recovered=service.get('UNRELATED',packet['id'],run['id'])
    assert recovered['task']['candidate']==proposal and recovered['task']['status']=='stopped'
    with pytest.raises(Conflict,match='未完成'):service.adopt('UNRELATED',packet['id'],run['id'],AdoptSemantics(base_revision=packet['revision']))
    checkpoint['source_hash']='wrong';write_json(folder/'local-checkpoint.json',checkpoint)
    assert 'candidate' not in service.get('UNRELATED',packet['id'],run['id'])['task']
    assert service.plans.current('UNRELATED',packet['id'])==packet

def test_unexpanded_insert_is_not_silently_lost_or_turned_into_a_human_question():
    site=dict(geometry=[],texts=[],dimensions=[],native_dwg=dict(entities=[dict(id='insert-1',kind='INSERT',insertion=[18,-3])]))
    proposal=dict(rooms=[],elements=[],lighting=[],drawing_objects=[])
    ledger=assess(site,proposal,dict(repair_errors=[]))
    assert ledger['counts']['pending']==1 and ledger['counts']['question']==0
    row=ledger['items'][0];assert row['kind']=='unsupported' and row['box']==pytest.approx([17.92,-3.08,18.08,-2.92])
    assert '工具待處理' in row['reason']

@pytest.mark.parametrize('upstream_blocked',[True,False])
def test_newly_unmasked_connectivity_does_not_discard_an_upstream_fix(system,upstream_blocked):
    site,base,report,item=fixture(system);calls=[]
    def staged_validate(_site,value):
        calls.append(value)
        proposal,checked=validate(_site,value)
        if len(calls)==1:
            checked.update(repair_errors=['Living room 疑似沒有可連通的入口，需對照原圖補回門洞或通道'],room_access=[dict(name='Living room')],access_checked=True)
        else:checked.update(repair_errors=['Upstream floor check'] if upstream_blocked else [],room_access=[],access_checked=not upstream_blocked)
        from interior.workbench.studio.semantic_diagnostics import attach
        return proposal,attach(_site,proposal,checked)
    if upstream_blocked:
        updated,checked,_=apply_patch(site,base,[item],response(item,patch=fridge_patch()),staged_validate)
        assert checked['repair_errors'] and updated!=base
    else:
        with pytest.raises(ValueError,match='新增檢查錯誤'):apply_patch(site,base,[item],response(item,patch=fridge_patch()),staged_validate)


def test_partial_salvage_keeps_valid_fix_and_records_invalid_item(system):
    from interior.workbench.studio.semantic_local_review import salvage
    site,base,report,item=fixture(system)
    site['texts'].append(dict(id='text-chair',text='椅子',point=[1,1]))
    second=next(i for i in inventory(site) if 'text-chair' in i['source_ids'])
    raw=response(item,patch=fridge_patch())
    raw['decisions']+=response(second)['decisions']
    updated,checked,decisions,failures=salvage(site,base,[item,second],raw,validate,set())
    assert item['id'] in decisions and second['id'] in failures
    assert any(i['id']=='fridge' for i in updated['elements'])
    assert next(i for i in updated['elements'] if i['id']=='desk')==next(i for i in base['elements'] if i['id']=='desk')
    assert base!=updated and assess(site,updated,checked,decisions)['counts']['pending']==1


def test_swing_arc_matches_hinge_radius_instead_of_arc_chord():
    from interior.workbench.studio.cad_candidates import matches
    row=dict(kind='door',source_ids=['swing'],box=[-.08,-.08,.98,.98],arc_center=[0,0],arc_radius=.9)
    proposal=dict(rooms=[],elements=[dict(id='door',role='door',points=[[0,0],[.9,0]],source_ids=['swing'])])
    assert matches(row,proposal)==['door']
    proposal['elements'][0]['points']=[[.9,0],[1.8,0]]
    assert matches(row,proposal)==[]


def test_new_question_introduced_on_retry_stays_pending(system,tmp_path):
    site,base,report,item=fixture(system);site['source_view']=dict(width=800,height=600,bounds=[0,0,8,6],scale=100,pad=0)
    image=tmp_path/'source.png';Image.new('RGB',(800,600),'white').save(image)
    class Client:
        calls=0
        def run(self,*args,**kwargs):
            self.calls+=1
            return dict(text=json.dumps(response(item) if self.calls==1 else response(item,'question')))
    client=Client();updated,checked,coverage,_=run_local_reviews(client,tmp_path,dict(site=site,image=str(image)),'fixture',base,report,lambda x:None,lambda x:None,validate)
    assert client.calls==2 and coverage['counts']['question']==0 and coverage['counts']['pending']==1
    assert not checked['questions'] and updated==base


def test_source_linked_misclassification_can_be_renamed_without_moving_it(system):
    site,base,report,item=fixture(system)
    desk=next(i for i in base['elements'] if i['id']=='desk');desk['source_ids'].append('text-fridge')
    packet=local_packet(site,base,[item])
    assert any(i['id']=='desk' for i in packet['current']['elements'])
    raw=response(item,'ignore',dict(elements=[dict(id='desk',name='Source-linked desk')]))
    updated,_,_=apply_patch(site,base,[item],raw,validate)
    assert next(i for i in updated['elements'] if i['id']=='desk')['points']==desk['points']


def test_get_and_adopt_recompute_missing_coverage_instead_of_trusting_passed_task(system):
    from test_semantic_corrections import setup
    from interior.workbench.storage import read_json,write_json,Conflict
    from interior.workbench.studio.plan_semantics import AdoptSemantics
    service,packet,run,agents=setup(system);request=service.folder('UNRELATED',packet['id'])/'runs'/run['id']/'request.json'
    record=read_json(request);record['site']['texts'].append(dict(id='missing-appliance',text='微波爐',point=[5,3]));write_json(request,record)
    current=service.get('UNRELATED',packet['id'],run['id'])
    assert current['task']['status']=='passed' and current['task']['semantic_report']['coverage']['counts']['pending']==1
    with pytest.raises((ValueError,Conflict),match='來源候選'):service.adopt('UNRELATED',packet['id'],run['id'],AdoptSemantics(base_revision=packet['revision']))
    assert service.plans.current('UNRELATED',packet['id'])==packet


def test_native_equipment_note_can_map_to_verified_drawing_object(system):
    site,base,report,_=fixture(system)
    site['texts'].append(dict(id='drying-rail',text='保留曬衣桿',point=[5,2]))
    item=next(i for i in inventory(site) if 'drying-rail' in i['source_ids'])
    raw=response(item,patch=dict(drawing_objects=[dict(id='rail',name='保留曬衣桿',layer='other',category='other',source_ids=['drying-rail','g-fridge'],evidence='Native equipment drawing and label')]))
    raw['decisions'][0]['object_ids']=['rail']
    updated,checked,decisions=apply_patch(site,base,[item],raw,validate)
    assert assess(site,updated,checked,decisions,records=[item])['counts']['matched']==1


def test_first_verified_furniture_updates_absence_state_without_changing_source(system):
    site,base,report,item=fixture(system)
    base['elements']=[i for i in base['elements'] if i['role']!='furniture'];base['furniture_state']='absent'
    updated,checked,_=apply_patch(site,base,[item],response(item,patch=fridge_patch()),validate)
    assert updated['furniture_state']=='present' and base['furniture_state']=='absent'
    assert not any('聲稱沒有' in e for e in checked['errors'])


def test_frame_inside_wall_requires_local_verified_mapping_not_auto_window():
    from interior.workbench.studio.cad_candidates import matches
    row=dict(kind='frame',source_ids=['frame'],box=[0,0,1,.3],options=[dict(points=[[0,.14],[1,.14]])])
    proposal=dict(rooms=[],elements=[dict(id='wall',role='wall',points=[[0,0],[1,0]],thickness=.3,source_ids=['frame'])])
    assert matches(row,proposal)==[]
    assert matches(row,proposal,components=True)==['wall']
    proposal['elements'][0]['points']=[[2,0],[3,0]]
    assert matches(row,proposal,components=True)==[]


def test_explicit_retry_supplies_previous_item_failure_and_clears_it_after_fix(system,tmp_path):
    site,base,report,item=fixture(system);site['source_view']=dict(width=800,height=600,bounds=[0,0,8,6],scale=100,pad=0)
    saved=assess(site,base,report);saved['failures']={item['id']:'Previous source host did not align'}
    site['previous_review']=dict(candidate=base,report=dict(coverage=saved))
    image=tmp_path/'source.png';Image.new('RGB',(800,600),'white').save(image)
    class Client:
        def run(self,prompt,**kwargs):
            assert 'prior_failure' in prompt and 'Previous source host did not align' in prompt
            return dict(text=json.dumps(response(item,patch=fridge_patch())))
    updated,checked,coverage,_=run_local_reviews(Client(),tmp_path,dict(site=site,image=str(image)),'fixture',base,report,lambda x:None,lambda x:None,validate)
    assert coverage['counts']['pending']==0 and not coverage['failures']
    assert item['id'] in coverage['decisions']
