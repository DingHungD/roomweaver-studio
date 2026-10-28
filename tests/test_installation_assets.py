import copy
from pathlib import Path
import pytest
from interior.workbench.studio import installation_assets as module
from interior.workbench.studio.models import DoorControl

def test_candidates_exclude_paid_and_wrong_function():
    base=dict(kind='model',is_free=True,license='royalty_free',name='Shower corner')
    assert module.eligible(base)
    for change in ({'is_free':False},{'name':'Shower door'},{'license':'unknown'},{'kind':'material'}):assert not module.eligible(dict(base,**change))

def test_conflict_retries_download_and_preserves_original(tmp_path,monkeypatch):
    folder=tmp_path/('a'*32);folder.mkdir();calls=[]
    candidates=[dict(asset_id=str(n),kind='model',is_free=True,license='cc_zero',name='Shower corner',url='reference'+str(n),dimensions=[.7+n*.01,.7,2]) for n in range(3)]
    monkeypatch.setattr(module.catalog,'search',lambda *a:candidates)
    def download(c,path,scene_id):
        calls.append(c['asset_id'])
        if c['asset_id']=='0':raise ValueError('missing file')
        path.write_bytes(b'fixture');return {'sha256':module.digest(path)}
    monkeypatch.setattr(module.catalog,'download',download)
    scene={'groups':[{'id':'shower','asset_requirements':{'dimension_source':'confirmed','dimensions':[.8,.8,2]}}]};before=copy.deepcopy(scene)
    report={'items':[{'id':'shower','kind':'shower','status':'unresolved','reason':'installation collision'}]}
    result,changed=module.prepare(scene,report,folder,'s'*64,folder/'stop')
    assert changed and calls==['0','1','2'] and scene==before
    assert result['groups']==scene['groups']
    packet=module.read_json(folder/'installation-assets.json')
    assert len(packet['objects']['shower'])==2 and packet['searches'][0]['failures']
    again,changed=module.prepare(result,report,folder,'s'*64,folder/'stop')
    assert not changed and again==result

def test_explicit_door_values_are_validated():
    assert DoorControl(opening_id='different-home-door',hinge='B',swing='negative').hinge=='B'
    with pytest.raises(ValueError):DoorControl(opening_id='door',hinge='unbounded')

@pytest.mark.parametrize("repair", [False, True])
def test_prepare_trials_candidate_and_uses_requested_model(tmp_path,monkeypatch,repair):
    from interior.workbench.studio import realism_prepare,completion_fronts,shelf_assets,scene_review
    from interior.workbench.storage import write_json,read_json
    from test_realism import scene
    design=scene();source=tmp_path/'source.blend';source.write_bytes(b'original')
    output=tmp_path/'project/runs/interior-studio'/('b'*32);output.mkdir(parents=True)
    request=dict(scene=design,source=str(source),revision='revision',realism_point_id='new-view',realism_all=True,agent_model='gpt-6-sol')
    monkeypatch.setattr(completion_fronts,'resolve',lambda req,sc,out,run:copy.deepcopy(sc))
    monkeypatch.setattr(shelf_assets,'resolve',lambda *args:{})
    monkeypatch.setattr(shelf_assets,'match_missing',lambda sc,*args:(sc,{},False))
    monkeypatch.setattr(module,'prepare',lambda sc,*args:(sc,False))
    rendered=[];reviewed=[]
    def run(payload,folder):
        rendered.append(payload)
        write_json(folder/'realism-inventory.json',{})
        write_json(folder/'shelf-refinements.json',[])
        write_json(folder/'opening-details.json',{'items':[],'remaining':[]})
        write_json(folder/'completion-details.json',{'items':[],'remaining':[]})
        write_json(folder/'installation-results.json',{'items':[dict(status='prepared',center=[1,1,1])]})
        (folder/'preview.glb').write_bytes(b'preview')
        write_json(folder/'preview-scene.json',design)
        write_json(folder/'preview-package.json',dict(file='preview.glb',scene_file='preview-scene.json'))
        write_json(folder/'result.json',dict(quality_check='passed',images=[dict(file='view.png',thumbnail='view-thumb.png')]))
        return 0
    def review(folder,sc,manifest,stop,model,**kwargs):
        reviewed.append(model)
        issues=[]
        if repair and len(reviewed)==1:
            shot=design['viewpoints'][0]['shots'][0]
            issues=[dict(id='cropped',category='viewpoint',target_id='new-view',shot_id=shot['id'],file='view.png',reason='head cropped',severity='defect',action='shot',values={'pitch':shot['pitch']+5})]
        return dict(summary='checked',issues=issues,image_hashes={})
    monkeypatch.setattr(scene_review,'review_images',review)
    result=realism_prepare.prepare(request,output,run)
    assert len(rendered)==(3 if repair else 2) and rendered[-1]['prepare_only'] is False
    assert reviewed==['gpt-6-sol']*(2 if repair else 1)
    assert result['images'][0]['file']==('installation-framing/view.png' if repair else 'installation-trial/view.png')
    assert rendered[-1]['scene']['viewpoints'][0]['eye']==design['viewpoints'][0]['eye']
    report=read_json(output/'realism-review.json')
    assert report['model_preview']['readonly'] and not report['prepare_only']
    assert read_json(output/'realism-effective.json')['scene']['groups']==design['groups']
    assert source.read_bytes()==b'original'
