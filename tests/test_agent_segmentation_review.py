"""Source-constrained mask corrections; reference answers are never an Agent input."""
import copy
import json

import numpy as np
import pytest

from interior.object_recognition.agent_review import source_shape,raster,apply_response


def site():
    return dict(source_view=dict(pad=0,scale=10,bounds=[0,0,10,10]),texts=[dict(id='t',text='櫃',point=[1,1])],
                geometry=[dict(id='g',kind='LWPOLYLINE',closed=True,points=[[1,1],[3,1],[3,2],[1,2]])])


def target():
    m=np.ones((10,20),bool)
    return dict(id='Y001',class_name='cabinet',class_id=0,mask_box=[10,80,30,90],box=[10,80,30,90],
                mask=m,area=200,contours=[],confidence=.8)


def test_outline_and_pair_use_real_edges():
    s=site();outline=source_shape(s,dict(method='outline',refs=[dict(id='g')]))
    assert outline.area==2
    pair=source_shape(s,dict(method='pair',refs=[dict(id='g',edge=0),dict(id='g',edge=2)]))
    assert pair.equals(outline)
    with pytest.raises(ValueError):source_shape(s,dict(method='pair',refs=[dict(id='g',edge=0),dict(id='g',edge=1)]))
    with pytest.raises(ValueError):source_shape(s,dict(method='outline',refs=[dict(id='invented')]))
    assert raster(s,outline,(100,100))['area']>0


def test_corrected_object_requires_geometry_not_just_text():
    s=site();p=target();before=copy.deepcopy(s)
    d=dict(id='Y001',action='replace',name='cabinet',class_name='cabinet',source_ids=['g'],text_ids=['t'],reason='visible frame',mask_spec=dict(method='outline',refs=[dict(id='g')]))
    rows,audit,pending=apply_response(s,[p],dict(decisions=[d]),[],{'cabinet':0},{p['id']:p},(100,100),'stage',{'g'})
    assert len(rows)==1 and rows[0]['provenance']=='agent_native' and not pending and s==before
    with pytest.raises(ValueError):apply_response(s,[p],dict(decisions=[dict(d,source_ids=[])]),[],{'cabinet':0},{p['id']:p},(100,100),'stage')
    with pytest.raises(ValueError):apply_response(s,[p],dict(decisions=[d]),[],{'cabinet':0},{p['id']:p},(100,100),'stage',set())


def test_reject_defer_and_missing_decisions_are_not_successes():
    s=site();p=target()
    rows,audit,pending=apply_response(s,[p],dict(decisions=[dict(id='Y001',action='defer',reason='uncertain')]),[],{'cabinet':0},{p['id']:p},(100,100),'stage')
    assert not rows and len(pending)==1
    with pytest.raises(ValueError):apply_response(s,[p],dict(decisions=[]),[],{'cabinet':0},{},(100,100),'stage')


def test_added_object_cannot_reuse_raw_yolo_mask_as_native_correction():
    s=site();p=target();d=dict(name='new',class_name='cabinet',source_ids=['g'],reason='visible source',mask_spec=dict(method='yolo',candidate_id='Y001'))
    with pytest.raises(ValueError):apply_response(s,[],dict(decisions=[],additions=[d]),[],{'cabinet':0},{p['id']:p},(100,100),'stage')


def test_final_repair_resolves_pending_and_freezes_without_reference(tmp_path):
    from PIL import Image
    from interior.object_recognition.agent_finish import finish
    from interior.object_recognition.agent_review import save_state
    from interior.object_recognition.review_report import freeze_review
    from interior.object_recognition.tiled import write,public,sha
    s=site();p=target();source=tmp_path/'source.png';image=Image.new('RGB',(100,100),'white');image.save(source)
    bundle=tmp_path/'bundle';bundle.mkdir();folder=tmp_path/'review';folder.mkdir()
    write(bundle/'candidates.json',[public(p)]);np.savez_compressed(bundle/'candidates-masks.npz',Y001=np.packbits(p['mask']))
    save_state(folder,[],image,'corrected');write(folder/'pending.json',[dict(id='Y001',action='defer',reason='check')])
    write(folder/'layer-verification.json',dict(reviewed_regions=list(range(6)),findings=[]))
    write(folder/'protocol.json',dict(regions=[[0,0,100,100]]*6))
    class Client:
        calls=0
        def run(self,instruction,**kwargs):
            self.calls+=1
            if self.calls==1:
                return dict(text=json.dumps(dict(decisions=[dict(id='Y001',action='keep',name='cabinet',source_ids=['g'],reason='visible source')],additions=[])))
            return dict(text=json.dumps(dict(reviewed_regions=list(range(6)),findings=[],summary='checked')))
    client=Client();result=finish(client,s,source,bundle,folder,{'cabinet':0},'selected',lambda _:None)
    assert client.calls==2 and result['final_objects']==1 and result['pending']==0
    frozen=freeze_review(folder,'corrected-final','layers-final.json','layer-verification-final.json')
    assert frozen['reference_labels_provided_to_agent'] is False
    assert all(sha(folder/f)==h for f,h in frozen['files'].items())


def test_source_binding_repairs_only_flagged_objects_and_keeps_pending(tmp_path):
    from PIL import Image
    from interior.object_recognition.source_bind_review import bind_and_verify
    from interior.object_recognition.agent_review import save_state
    from interior.object_recognition.tiled import write,load_masks
    s=site();before=copy.deepcopy(s);p=target()
    p.update(source_ids=['g'],mask_spec=dict(method='yolo',candidate_id='Y001'),name='cabinet',route='agent_reviewed')
    other=dict(p,id='Y002',source_ids=[],mask_spec=dict(method='yolo',candidate_id='Y002'))
    folder=tmp_path/'previous';folder.mkdir();source=tmp_path/'source.png'
    image=Image.new('RGB',(100,100),'white');image.save(source)
    save_state(folder,[p,other],image,'corrected-final')
    write(folder/'layer-verification-final.json',dict(findings=[dict(object_ids=['Y001'])]))
    write(folder/'pending-final.json',[dict(id='uncertain',reason='old'),dict(id='uncertain',reason='latest')])
    write(folder/'protocol.json',dict(classes={'cabinet':0},regions=[[0,0,100,100]]*6))
    class Client:
        def run(self,instruction,**kwargs):
            return dict(text=json.dumps(dict(reviewed_regions=list(range(6)),findings=[],pending_confirmed=['uncertain'])))
    output=tmp_path/'bound'
    result=bind_and_verify(Client(),s,source,folder,output,'selected',lambda _:None)
    rows={r['id']:r for r in load_masks(output,'corrected')}
    assert result['source_bound_corrections']==1 and result['pending_unique']==1
    assert rows['Y001']['mask_spec']['method']=='outline' and rows['Y001']['class_name']=='cabinet'
    assert rows['Y002']['mask_spec']==other['mask_spec'] and np.array_equal(rows['Y002']['mask'],other['mask'])
    assert s==before
    with pytest.raises(FileExistsError):bind_and_verify(Client(),s,source,folder,output,'selected',lambda _:None)
