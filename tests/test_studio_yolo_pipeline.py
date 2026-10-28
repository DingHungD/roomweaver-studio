"""Studio source correction and omission repair without known test-error IDs or labels."""
import json

import numpy as np
import pytest
from PIL import Image

from interior.object_recognition.agent_review import raster,source_shape,save_state
from interior.object_recognition.studio_pipeline import run,layer_data
from interior.object_recognition.tiled import write,sha,load_masks
from interior.workbench.studio.yolo_review import attach_report,review_native


def fixture(tmp_path):
    site=dict(source_view=dict(pad=0,scale=10,bounds=[0,0,10,10]),texts=[],
        geometry=[dict(id='g',kind='LWPOLYLINE',closed=True,points=[[1,1],[3,1],[3,2],[1,2]]),
                  dict(id='missing',kind='LWPOLYLINE',closed=True,points=[[6,6],[8,6],[8,7],[6,7]])])
    source=tmp_path/'source.png';image=Image.new('RGB',(100,100),'white');image.save(source)
    p=dict(id='Y001',view_id='full',class_name='furniture',class_id=0,confidence=.8,accepted=False,
           route='agent_review',clipped=False,views=['full'],conflicts=[],**raster(site,source_shape(site,dict(method='outline',refs=[dict(id='g')])),image.size))
    bundle=tmp_path/'bundle';bundle.mkdir();save_state(bundle,[p],image,'candidates')
    write(bundle/'config.json',dict(image=str(source),sha256=dict(image=sha(source),checkpoint='synthetic')))
    write(bundle/'taxonomy.json',dict(classes=[dict(id=0,name='furniture')]))
    return site,source,bundle


class Agent:
    def __init__(self,*,defer=False,omit=False):self.defer=defer;self.omit=omit;self.repairs=0;self.events=[]
    def run(self,prompt,**kwargs):
        self.events.append(kwargs.get('on_event'))
        if '僅檢查套層後' in prompt or '本次只驗證' in prompt:
            findings=[dict(issue='missing',name='native object',object_ids=[],source_ids=['missing'],reason='visible source')] if self.omit and not self.repairs else []
            result=dict(reviewed_regions=list(range(6)),findings=findings,summary='checked')
        elif '本輪只修正' in prompt:
            self.repairs+=1
            result=dict(decisions=[],additions=[dict(name='source object',class_name='furniture',source_ids=['missing'],text_ids=[],reason='visible closed object',mask_spec=dict(method='outline',refs=[dict(id='missing')]))])
        else:
            data=json.loads(prompt.split('本批資料：',1)[1])
            result=dict(decisions=[dict(id=r['id'],action='defer' if self.defer else 'keep',source_ids=['g'],text_ids=[],reason='source checked') for r in data['targets']],additions=[])
        return dict(text=json.dumps(result),thread_id='synthetic')


def test_full_pipeline_adds_source_bound_omission_then_freezes(tmp_path):
    site,source,bundle=fixture(tmp_path);agent=Agent(omit=True);event=lambda _:None
    output=tmp_path/'review'
    result=run(agent,dict(site=site,image=str(source)),bundle,output,'selected-model',lambda _:None,event)
    assert result['objects']==2 and result['native_corrected']==1 and result['status']=='reviewed_preview'
    assert result['precision'] is None and not result['known_error_ids_used']
    assert all(e is event for e in agent.events)
    frozen=json.loads((output/'frozen-result.json').read_text())
    assert all(sha(output/f)==h for f,h in frozen['files'].items())
    assert run(agent,dict(site=site,image=str(source)),bundle,output,'selected-model',lambda _:None)==result
    (output/'object-layers.json').write_text('{}')
    with pytest.raises(ValueError,match='雜湊'):run(agent,dict(site=site,image=str(source)),bundle,output,'selected-model',lambda _:None)


def test_deferred_candidate_remains_visible_and_blocks_adoption(tmp_path):
    site,source,bundle=fixture(tmp_path)
    result=run(Agent(defer=True),dict(site=site,image=str(source)),bundle,tmp_path/'review','selected',lambda _:None,max_repairs=0)
    assert result['objects']==1 and result['retained_unresolved']==1 and result['status']=='blocked'
    row=load_masks(tmp_path/'review','objects')[0];assert not row['accepted']
    report=dict(status='preview',errors=[],repair_errors=[])
    attach_report(report,result);attach_report(report,result)
    assert report['status']=='blocked' and len(report['errors'])==1 and len(report['repair_errors'])==1
    assert report['recognition']['objects']==1


def test_native_results_feed_the_subsequent_plan_agent_and_preserve_holes(tmp_path):
    site,source,bundle=fixture(tmp_path);payload=dict(site=site,image=str(source),_yolo_workflow='agent_native_v1')
    result=review_native(Agent(),payload,bundle,tmp_path,'selected',lambda _:None,None)
    assert payload['site']['yolo_reviewed']['objects']==result['layers']['items']
    assert payload['source_images'][-1].endswith('class-layers.png')
    row=load_masks(bundle)[0]
    row['contours'].append(dict(hole=True,points=[[15,83],[25,83],[25,87],[15,87]]))
    converted=layer_data(site,[row])['items'][0]
    assert converted['role']=='mask' and len(converted['areas'][0]['holes'])==1
    assert converted['areas'][0]['holes'][0][0]==[1.5,1.6999999999999993] or np.allclose(converted['areas'][0]['holes'][0][0],[1.5,1.7])


def test_explicit_opt_out_never_invokes_model_even_if_runtime_is_configured(tmp_path,monkeypatch):
    from interior.workbench.studio.yolo_review import prepare
    path=tmp_path/'invalid-config.json';path.write_text('invalid JSON')
    monkeypatch.setenv('ROOMWEAVER_YOLO_CONFIG',str(path))
    assert prepare(dict(use_object_recognition=False),tmp_path,lambda _:None) is None
    monkeypatch.delenv('ROOMWEAVER_YOLO_CONFIG')
    with pytest.raises(ValueError,match='尚未設定'):
        prepare(dict(use_object_recognition=True),tmp_path,lambda _:None)
