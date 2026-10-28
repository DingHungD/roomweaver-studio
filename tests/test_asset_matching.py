"""Synthetic catalog contracts and revision-safe replacement workflow."""
import copy,json
from unittest.mock import patch
import pytest
from interior.workbench.studio import blenderkit_client as catalog
from interior.workbench.studio.asset_matching import run_matching,AssetMatching,MatchRequest,SelectAsset
from interior.workbench.studio.models import Scene,AssetReference
from interior.workbench.storage import Store,write_json,Conflict
from interior.workbench.jobs import Jobs
from interior.workbench.studio.service import Studio
from test_workbench_studio import synthetic_scene,MODEL

FREE='11111111-1111-4111-8111-111111111111'
PAID='22222222-2222-4222-8222-222222222222'
VERSION='33333333-3333-4333-8333-333333333333'
def raw(base=FREE,free=True):
    return dict(id=VERSION,assetBaseId=base,assetType='model',name='Synthetic chair',isFree=free,license='cc_zero',
        canDownload=True,dictParameters=dict(dimensionX=.5,dimensionY=.6,dimensionZ=.9),
        files=[dict(fileType='blend',downloadUrl=catalog.API+'downloads/'+VERSION+'/',fileUploadSize=100)])

def test_catalog_price_unknown_sizes_and_url_validation():
    r=raw();r['isFree']=None;r['dictParameters']['dimensionZ']=float('nan')
    item=catalog.normalize(r);assert not item['is_free'] and item['dimensions'] is None
    for url in ['http://www.blenderkit.com/a','https://assets.blenderkit.com.evil.test/x','https://localhost/x','https://user@assets.blenderkit.com/x']:
        with pytest.raises(ValueError):catalog.trusted_url(url)
    r['files'][0]['downloadUrl']='https://public.blenderkit.com/private'
    with pytest.raises(ValueError):catalog.normalize(r)

def test_catalog_filters_cannot_be_injected():
    with patch.object(catalog,'request',return_value={'results':[raw(),raw(PAID,False)]}) as call:
        result=catalog.search('chair+asset_type:scene','model',True)
        assert len(result)==1 and result[0]['is_free']
        assert call.call_args.kwargs['params']['query']=='chair asset_type scene+asset_type:model+is_free:true'

def test_large_material_prefers_official_2k_native_package():
    a=raw();a['assetType']='material';a['files'][0]['fileUploadSize']=275_000_000
    a['files'].append(dict(fileType='resolution_2K',downloadUrl=catalog.API+'downloads/'+FREE+'/',fileUploadSize=18_000_000))
    item=catalog.normalize(a)
    assert item['download_resolution']=='resolution_2K' and item['bytes']==18_000_000
    assert item['download_url'].endswith(FREE+'/')

def test_agent_must_select_real_catalog_ids_and_free_sorted_first(tmp_path):
    class Client:
        calls=0
        def run(self,prompt,**kwargs):
            self.calls+=1
            return dict(text=json.dumps({'queries':['dining chair']} if self.calls==1 else {'matches':[{'asset_id':PAID,'reason':'Paid backup'},{'asset_id':FREE,'reason':'Free match'}]}))
    with patch.object(catalog,'search',side_effect=lambda q,k,f:[catalog.normalize(raw(FREE if f else PAID,f))]):
        result=run_matching(Client(),tmp_path,dict(context={},description='wood chair',kind='model'),'test',lambda p:None,lambda e:None)
    assert [c['asset_id'] for c in result['candidates']]==[FREE,PAID]
    assert result['candidates'][0]['url'].endswith(FREE+'/')
    with patch.object(catalog,'search',return_value=[catalog.normalize(raw())]):
        with pytest.raises(ValueError,match='未查核'):run_matching(Client(),tmp_path,dict(context={},description='',kind='model'),'test',lambda p:None,lambda e:None)

def test_download_rechecks_price_version_license_before_network(tmp_path):
    item=catalog.normalize(raw())
    for key,value in [('version_id',FREE),('is_free',False),('license','royalty_free')]:
        with patch.object(catalog,'detail',return_value=dict(item,**{key:value})),patch.object(catalog,'request') as get:
            with pytest.raises(ValueError,match='已變更'):catalog.download(item,tmp_path/'asset.blend','a'*32)
            get.assert_not_called()
    paid=catalog.normalize(raw(PAID,False))
    with patch.dict('os.environ',{},clear=True),patch.object(catalog,'detail',return_value=paid):
        with pytest.raises(ValueError,match='付費'):catalog.download(paid,tmp_path/'asset.blend','a'*32)

class FakeAgents:
    def __init__(self):self.tasks={};self.calls=0
    def start(self,kind,model,payload,identifier):
        self.calls+=1;self.tasks[identifier]=dict(id=identifier,status='passed',candidates=[dict(catalog.normalize(raw()),name='Synthetic sofa'),dict(catalog.normalize(raw(PAID,False)),name='Synthetic sofa')])
    def get(self,identifier):return copy.deepcopy(self.tasks[identifier])

def environment(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='ASSETS',name='Synthetic'))
    with patch.object(Jobs,'loop',return_value=None):jobs=Jobs(store)
    studio=Studio(store,jobs);scene=synthetic_scene()
    write_json(studio.root('ASSETS')/'runs/interior-studio'/MODEL/'model.json',dict(objects=scene['objects']))
    import struct
    gltf=json.dumps(dict(nodes=[])).encode();gltf+=b' '*((-len(gltf))%4)
    (studio.root('ASSETS')/'runs/interior-studio'/MODEL/'model.glb').write_bytes(struct.pack('<IIIII',0x46546c67,2,20+len(gltf),len(gltf),0x4e4f534a)+gltf)
    first=studio.save('ASSETS',scene,None)
    return studio,jobs,first

def test_matching_scoped_to_group_deduplicated_reference_saved_and_stale_rejected(tmp_path):
    studio,jobs,first=environment(tmp_path)
    try:
        agents=FakeAgents();service=AssetMatching(studio,agents);gid=next(g['id'] for g in first['scene']['groups'] if 'sofa' in g['children'])
        body=MatchRequest(base_revision=first['revision'],group_id=gid,operation_id='match-0001')
        task=service.start('ASSETS',body);assert service.start('ASSETS',body)['id']==task['id'] and agents.calls==1
        with pytest.raises(Conflict):service.start('ASSETS',body.model_copy(update={'description':'changed'}))
        selection=SelectAsset(base_revision=first['revision'],asset_id=FREE,operation_id='replace-001')
        saved=service.reference('ASSETS',task['id'],selection)
        assert next(g for g in saved['scene']['groups'] if g['id']==gid)['asset_reference']['url'].endswith(FREE+'/')
        selection.base_revision=saved['revision']
        with pytest.raises(ValueError,match='授權'):service.replace('ASSETS',task['id'],selection)
        selection.accept_license=True
        job=service.replace('ASSETS',task['id'],selection)
        assert service.replace('ASSETS',task['id'],selection)['id']==job['id']
        assert job['operation']=='studio.replace'
        moved=copy.deepcopy(saved['scene']);next(g for g in moved['groups'] if g['id']==gid)['translation']=[1,0,0]
        changed=studio.save('ASSETS',moved,saved['revision']);selection.base_revision=changed['revision']
        with pytest.raises(Conflict,match='單物件'):service.replace('ASSETS',task['id'],selection)
        assert service.current('ASSETS',gid)['replacement']['job_id']==job['id']
    finally:jobs.close()

def test_material_target_and_reference_url_are_validated(tmp_path):
    studio,jobs,first=environment(tmp_path)
    try:
        service=AssetMatching(studio,FakeAgents());gid=next(g['id'] for g in first['scene']['groups'] if 'sofa' in g['children'])
        with pytest.raises(ValueError,match='子物件'):service.start('ASSETS',MatchRequest(base_revision=first['revision'],group_id=gid,kind='material',operation_id='match-0001'))
        wall=next(g for g in first['scene']['groups'] if 'wall' in g['children'])
        result=service.start('ASSETS',MatchRequest(base_revision=first['revision'],group_id=wall['id'],kind='material',operation_id='whole-wall'))
        assert result['target']['object_ids']==wall['children']
        with pytest.raises(ValueError):AssetReference(asset_id=FREE,version_id=VERSION,task_id='a'*32,name='test',url='javascript:alert(1)',kind='model',license='cc_zero',is_free=True)
    finally:jobs.close()

def test_shared_style_survives_save_clear_and_old_candidates_keep_geometry_guards(tmp_path):
    studio,jobs,first=environment(tmp_path)
    try:
        service=AssetMatching(studio,FakeAgents())
        group=next(g for g in first['scene']['groups'] if 'sofa' in g['children'])
        task=service.start('ASSETS',MatchRequest(base_revision=first['revision'],group_id=group['id'],operation_id='style-sync'))
        from interior.workbench.storage import read_json
        path=service.folder('ASSETS')/task['id']/'input.json'
        legacy=read_json(path);legacy['context']['group'].pop('style_prompt',None);write_json(path,legacy)
        scene=copy.deepcopy(first['scene'])
        target=next(g for g in scene['groups'] if g['id']==group['id']);target['style_prompt']='neutral oak'
        saved=studio.save('ASSETS',scene,first['revision'])
        body=SelectAsset(base_revision=saved['revision'],asset_id=FREE,operation_id='style-candidate')
        service.candidate('ASSETS',task['id'],body)
        assert next(g for g in studio.current('ASSETS')['scene']['groups'] if g['id']==group['id'])['style_prompt']=='neutral oak'
        target['style_prompt']='';saved=studio.save('ASSETS',scene,saved['revision']);body.base_revision=saved['revision']
        current,_,_=service.candidate('ASSETS',task['id'],body)
        assert next(g for g in current['scene']['groups'] if g['id']==group['id'])['style_prompt']==''
        target['translation']=[1,0,0];moved=studio.save('ASSETS',scene,saved['revision']);body.base_revision=moved['revision']
        with pytest.raises(Conflict,match='單物件'):service.candidate('ASSETS',task['id'],body)
        assert not jobs.list()
    finally:jobs.close()

def test_glb_dimensions_include_parent_transforms_and_axis_conversion(tmp_path):
    import struct
    from interior.workbench.studio.asset_matching import preview_dimensions
    gltf=dict(nodes=[dict(children=[1],translation=[5,0,0],scale=[2,3,4]),dict(mesh=0,extras=dict(studio_id='part'))],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0))])],accessors=[dict(min=[0,0,0],max=[1,2,3])])
    data=json.dumps(gltf).encode();data+=b' '*((-len(data))%4)
    file=tmp_path/'bounds.glb';file.write_bytes(struct.pack('<IIIII',0x46546c67,2,20+len(data),len(data),0x4e4f534a)+data)
    assert preview_dimensions(file,['part'])==[2,12,6]
    assert preview_dimensions(file,['unknown']) is None

def test_redirects_to_untrusted_hosts_are_rejected_before_contact():
    import httpx
    from contextlib import contextmanager
    calls=[]
    @contextmanager
    def stream(method,url,**kwargs):
        calls.append(url)
        yield httpx.Response(302,headers={'location':'https://127.0.0.1/private'},request=httpx.Request(method,url))
    with patch('httpx.stream',side_effect=stream):
        with pytest.raises(ValueError,match='來源'):catalog.request(catalog.API+'search/')
    assert calls==[catalog.API+'search/']

def test_download_limit_removes_partial_and_sends_no_api_key_to_cdn(tmp_path):
    import httpx
    from contextlib import contextmanager
    @contextmanager
    def stream(method,url,**kwargs):
        assert not kwargs.get('headers',{}).get('Authorization')
        yield httpx.Response(200,content=b'BLENDER'+b'x'*100,request=httpx.Request(method,url))
    item=catalog.normalize(raw());item['bytes']=1
    with patch.dict('os.environ',{'BLENDERKIT_API_KEY':'synthetic-test-key'}),patch.object(catalog,'detail',return_value=item),patch.object(catalog,'request',return_value=dict(filePath='https://assets.blenderkit.com/test.blend')),patch('httpx.stream',side_effect=stream),patch.object(catalog,'MAX_BYTES',30):
        with pytest.raises(ValueError,match='上限'):catalog.download(item,tmp_path/'asset.blend','a'*32)
    assert not (tmp_path/'asset.blend').exists() and not (tmp_path/'asset.partial').exists()

def test_paid_candidate_requires_explicit_paid_consent(tmp_path):
    studio,jobs,first=environment(tmp_path)
    try:
        service=AssetMatching(studio,FakeAgents());gid=next(g['id'] for g in first['scene']['groups'] if 'sofa' in g['children'])
        task=service.start('ASSETS',MatchRequest(base_revision=first['revision'],group_id=gid,operation_id='paid-match'))
        body=SelectAsset(base_revision=first['revision'],asset_id=PAID,operation_id='paid-replace',accept_license=True)
        with pytest.raises(ValueError,match='付費候補'):service.replace('ASSETS',task['id'],body)
        assert not jobs.list()
    finally:jobs.close()
