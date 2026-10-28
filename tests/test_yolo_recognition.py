"""Synthetic seam, mask, duplicate and source-review failures; no customer fixtures."""
import json
from types import SimpleNamespace

import pytest
np=pytest.importorskip('numpy')
from PIL import Image

from interior.object_recognition.tiled import windows, settings, extract, merge, infer, load_masks
from interior.workbench.studio.yolo_review import context, validate_decisions, prepare


def row(identifier='a',view='full',rect=(0,0,10,10),class_id=0,confidence=.9,clipped=False):
    x,y,r,b=rect;mask=np.ones((b-y,r-x),dtype=bool)
    return dict(id=identifier,view_id=view,mask_box=list(rect),mask=mask,area=int(mask.sum()),
        class_id=class_id,class_name='wall' if class_id==0 else 'cabinet',confidence=confidence,clipped=clipped,contours=[])


def test_tiles_cover_source_with_fixed_stride_and_border_padding():
    covered=np.zeros((139,211),bool)
    for x,y,r,b in windows(211,139,64,.25):
        assert 0<=x<r<=211 and 0<=y<b<=139
        covered[y:b,x:r]=True
    assert covered.all()
    assert sorted({b[0] for b in windows(211,139,64,.25)})==[0,48,96,144,192]
    assert windows(10,8,64,.25)==[[0,0,10,8]]
    with pytest.raises(ValueError):windows(10,8,64,1)


def test_offset_and_holes_are_preserved_not_polygon_filled():
    pytest.importorskip('cv2')
    mask=np.zeros((20,20),dtype=bool);mask[2:18,2:18]=True;mask[5:15,5:15]=False
    tensor=SimpleNamespace(cpu=lambda:SimpleNamespace(numpy=lambda:mask[None]))
    result=SimpleNamespace(masks=SimpleNamespace(data=tensor),boxes=SimpleNamespace(
        cls=np.array([0]),conf=np.array([.9]),xyxy=np.array([[2,2,18,18]])),names={0:'wall'})
    actual=extract(result,[100,200,120,220],'tile-0',(400,400))[0]
    assert actual['mask_box']==[102,202,118,218]
    assert actual['area']==156 and not actual['mask'][5,5]
    assert any(c['hole'] for c in actual['contours'])
    assert actual['clipped']


def test_agreement_dedupes_but_never_auto_accepts_or_unions():
    a=row();b=row('b','tile-0',rect=(1,0,11,10))
    result=merge([a,b],settings())
    assert len(result)==1 and result[0]['area']==100
    assert not result[0]['accepted'] and result[0]['route']=='priority_review'


def test_clipped_or_weak_second_view_cannot_promote():
    for alternate in [row('b','tile-0',clipped=True),row('b','tile-0',confidence=.1)]:
        assert merge([row(),alternate],settings())[0]['route']=='agent_review'
    assert merge([row()],settings())[0]['route']=='agent_review'


def test_tile_does_not_replace_long_complete_full_mask():
    full=row('full','full',rect=(0,0,100,10),confidence=.6)
    partial=row('tile','tile-0',rect=(0,0,60,10),confidence=.99)
    combined=merge([full,partial],settings())
    assert len(combined)==1 and combined[0]['view_id']=='full' and combined[0]['area']==1000


def test_cross_class_conflict_is_retained_for_review():
    merged=merge([row(),row('b','tile-0'),row('c','tile-1',class_id=1)],settings())
    assert len(merged)==2 and all(p['conflicts'] for p in merged)
    assert all(p['route']=='agent_review' for p in merged)


def test_nearby_text_does_not_assign_class_or_create_an_object():
    site=dict(source_view=dict(pad=0,scale=10,bounds=[0,0,10,10]),geometry=[dict(id='line',points=[[0,9],[1,9]])],
        texts=[dict(id='text',point=[.5,9.5],text='新增軌道燈')])
    r=dict(row(),id='Y001',route='agent_review',views=['full'],conflicts=[])
    items=context(site,[r]);assert items[0]['nearby_texts'][0]['id']=='text'
    accept=dict(id='Y001',action='accept',class_correct=True,mask_correct=True,source_ids=['line'],text_ids=['text'],reason='Checked visible symbol')
    assert validate_decisions(items,dict(decisions=[accept]),site)
    for bad in [dict(accept,source_ids=[]),dict(accept,mask_correct=False),dict(accept,source_ids=['invented'])]:
        with pytest.raises(ValueError):validate_decisions(items,dict(decisions=[bad]),site)
    with pytest.raises(ValueError):validate_decisions(items,dict(decisions=[]),site)


def test_inference_empty_tiles_records_sources_and_refuses_overwrite(tmp_path):
    source=tmp_path/'source.png';Image.new('RGB',(60,45),'white').save(source)
    checkpoint=tmp_path/'model.pt';checkpoint.write_bytes(b'synthetic')
    class Empty:
        task='segment'
        calls=0
        def predict(self,**kwargs):
            assert kwargs['retina_masks'] and 'reference' not in kwargs
            if self.calls:assert kwargs['source'].size==(32,32)
            self.calls+=1
            return [SimpleNamespace(masks=None,speed={})]
    out=tmp_path/'run';summary=infer(source,checkpoint,out,dict(tile_size=32,imgsz=32),Empty())
    assert summary['tiles']>0 and summary['accepted']==0 and summary['source_unchanged']
    assert load_masks(out)==[]
    with pytest.raises(FileExistsError):infer(source,checkpoint,out,model=Empty())


def test_unconfigured_studio_never_loads_model_or_calls_cloud(tmp_path,monkeypatch):
    monkeypatch.delenv('ROOMWEAVER_YOLO_CONFIG',raising=False)
    assert prepare({},tmp_path,lambda _:None) is None


def test_cached_single_scale_cannot_be_reused_as_multiscale(tmp_path,monkeypatch):
    from interior.object_recognition.tiled import sha
    monkeypatch.delenv('ROOMWEAVER_YOLO_CONFIG',raising=False)
    source=tmp_path/'source.png';Image.new('RGB',(10,10),'white').save(source)
    import sys
    checkpoint=tmp_path/'weights.pt';checkpoint.write_bytes(b'synthetic')
    weight_hash=sha(checkpoint)
    config=tmp_path/'runtime.json';config.write_text(json.dumps(dict(enabled=True,python=sys.executable,checkpoint=str(checkpoint),checkpoint_sha256=weight_hash,options={})),encoding='utf-8')
    bundle=tmp_path/'yolo-inference';bundle.mkdir()
    (bundle/'status.json').write_text(json.dumps(dict(status='completed')),encoding='utf-8')
    (bundle/'config.json').write_text(json.dumps(dict(sha256=dict(image=sha(source),checkpoint=weight_hash),options=settings(dict(pyramid_scales=[1.])))),encoding='utf-8')
    with pytest.raises(ValueError,match='cached options'):
        prepare(dict(image=str(source),yolo_config=str(config)),tmp_path,lambda _:None)


def test_bad_settings_rejected():
    for bad in [dict(tile_size=0),dict(tile_size=639),dict(overlap=float('nan')),dict(unknown=1),dict(confidence=.9,review_confidence=.25)]:
        with pytest.raises(ValueError):settings(bad)


def test_review_outputs_layers_and_scans_even_when_nothing_is_accepted(tmp_path,monkeypatch):
    from interior.workbench.studio.yolo_review import review
    import interior.workbench.studio.semantic_layers as layers
    source=tmp_path/'source.png';Image.new('RGB',(80,80),'white').save(source)
    bundle=tmp_path/'bundle';bundle.mkdir()
    r=dict(row(),id='Y001',route='agent_review',views=['full'],conflicts=[])
    (bundle/'candidates.json').write_text(json.dumps([{k:v for k,v in r.items() if k!='mask'}]),encoding='utf-8')
    np.savez_compressed(bundle/'candidates-masks.npz',Y001=np.packbits(r['mask']))
    (bundle/'views.json').write_text(json.dumps([dict(id='full',box=[0,0,80,80])]),encoding='utf-8')
    Image.new('RGB',(80,80),'white').save(bundle/'Y001.png')
    site=dict(source_view=dict(pad=0,scale=10,bounds=[0,0,8,8]),geometry=[dict(id='g',points=[[0,7],[1,7]])],texts=[])
    monkeypatch.setattr(layers,'review_layers',lambda s,c:dict(items=[]))
    class Reviewer:
        calls=0
        def run(self,instruction,**kwargs):
            self.calls+=1
            if self.calls==1:
                return dict(text=json.dumps(dict(decisions=[dict(id='Y001',action='defer',source_ids=[],text_ids=[],reason='Incomplete mask')])) )
            return dict(text=json.dumps(dict(regions=['full'],findings=[],summary='Scan completed')))
    client=Reviewer();result=review(client,dict(image=str(source),site=site),'selected-model',{},tmp_path,bundle,lambda _:None,None)
    assert client.calls==2 and result['accepted']==0 and result['deferred']==1
    saved=json.loads((tmp_path/'yolo-review/reviewed-yolo-layers.json').read_text(encoding='utf-8'))
    assert saved['items']==[] and not saved['precision_target_verified']
    assert (tmp_path/'yolo-review/semantic-overlay.png').is_file()
