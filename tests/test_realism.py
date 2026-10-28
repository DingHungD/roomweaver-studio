"""Look-development contracts: scoped changes, rejected candidates, durable adoption."""
import copy
from types import SimpleNamespace
import pytest
from interior.workbench.studio import realism
from interior.workbench.studio.models import Scene,RenderFinish
from interior.workbench.storage import read_json,write_json,Conflict


def scene():
    return Scene.model_validate(dict(model_id='a'*32,rooms=[dict(id='new-room',name='New room')],objects=[dict(id='wood',name='Desk',room_id='new-room')],groups=[dict(id='desk',name='Desk',children=['wood'],asset_requirements=dict(purpose='desk',dimension_source='confirmed',dimensions=[1.2,.6,.75],evidence='owner'))],viewpoints=[dict(id='new-view',name='New room',room_id='new-room',eye=[1,1,1.6],shots=[dict(id='front',name='Front',yaw=0)])],lighting_setup=dict(enabled=True,lights=[dict(id='lamp',name='Lamp',position=[0,0,2.5],power=100,size=1)]))).model_dump(mode='json')


def facts():
    return dict(objects=[dict(id='wood',name='Desk',editable=True)],lights=[dict(id='lamp',name='Lamp',editable=True,scope='local')])


def verdict(**kw):
    return realism.Verdict.model_validate(dict(summary='synthetic judgment',preference='baseline',reviewed_files=[],**kw))


def test_shelf_requires_target_bound_evidence_and_preserves_confirmed_envelope():
    original=scene();original['groups'][0]['name']='Utility unit';original['groups'][0]['asset_requirements']['purpose']='cabinet'
    proof='Utility unit: confirmed open shelf for equipment. Source: owner record.'
    native=facts();native['details']={'shelves':[dict(object_id='wood',name='Utility unit')]};native['requirements_record']=proof
    proposal=verdict(shelves=[dict(object_id='wood',front='+X',evidence=proof)])
    result,changes,rejected=realism.apply_plan(original,original,native,proposal)
    assert changes and not rejected
    assert result['groups']==original['groups'] and result['objects']==original['objects']
    native['requirements_record']='Other furniture: open shelf'
    _,changes,rejected=realism.apply_plan(original,original,native,proposal)
    assert rejected and not changes
    native['requirements_record']=proof
    original['groups'][0]['object_specification']={'front':'-X'}
    _,changes,rejected=realism.apply_plan(original,original,native,proposal)
    assert rejected and not changes


def test_scoped_finish_preserves_geometry_dimensions_uv_intent():
    original=scene();proposal=verdict(materials=[dict(object_id='wood',finish={'bump_factor':.5},reason='exaggerated grain')])
    actual,changes,rejected=realism.apply_plan(original,original,facts(),proposal)
    assert actual['groups']==original['groups'] and actual['viewpoints']==original['viewpoints']
    assert actual['objects'][0]['material']['render_finish']['bump_factor']==.5
    assert original['objects'][0]['material']['render_finish'] is None
    assert changes and not rejected


def test_shelf_contents_need_named_evidence_not_just_a_shelf():
    original=scene();original['groups'][0]['name']='Utility unit';original['groups'][0]['asset_requirements']['purpose']='cabinet'
    proof='Utility unit: open shelf for microwave and magazines.'
    native=facts();native['details']={'shelves':[dict(object_id='wood',name='Utility unit')]};native['requirements_record']=proof
    for contents,allowed in [(['microwave','magazines'],True),(['coffee_machine'],False),(['magazines','magazines'],False)]:
        result,changes,rejected=realism.apply_plan(original,original,native,verdict(shelves=[dict(object_id='wood',front='+X',evidence=proof,contents=contents)]))
        assert bool(changes)==allowed and bool(rejected)!=allowed
        assert result['groups']==original['groups']


def test_model_preview_is_read_only_revision_and_hash_bound(tmp_path):
    import threading
    current=dict(revision='b'*32,scene=scene());folder=tmp_path/'runs/interior-studio/job';folder.mkdir(parents=True)
    native=tmp_path/'runs/interior-studio'/('a'*32)/'model.blend';native.parent.mkdir();native.write_bytes(b'source')
    glb=folder/'model.glb';glb.write_bytes(b'preview');packet=folder/'preview-scene.json';write_json(packet,current['scene'])
    report=dict(revision=current['revision'],point=dict(id='new-view'),source_sha256=realism.digest(native),model_preview=dict(file='model.glb',scene_file='preview-scene.json',sha256=realism.digest(glb),scene_sha256=realism.digest(packet)))
    write_json(folder/'realism-review.json',report)
    studio=SimpleNamespace(store=SimpleNamespace(lock=threading.RLock()),root=lambda p:tmp_path,current=lambda p:copy.deepcopy(current),jobs=SimpleNamespace(get=lambda j:dict(project_id='NEW',status='completed',operation='studio.render',source_revision='b'*32,output='runs/interior-studio/job')))
    assert realism.model_preview(studio,'NEW','job')['readonly']
    with pytest.raises(ValueError):realism.model_preview(studio,'OTHER','job')
    current['revision']='c'*32
    with pytest.raises(Conflict):realism.model_preview(studio,'NEW','job')
    current['revision']='b'*32;write_json(packet,dict(untrusted=True))
    with pytest.raises(Conflict):realism.model_preview(studio,'NEW','job')
    assert native.read_bytes()==b'source' and current['scene']==scene()


@pytest.mark.parametrize('protected', ['original','specified'])
def test_material_policy_is_enforced_against_agent(protected):
    original=scene();original['groups'][0]['object_specification']=dict(material_policy=protected,material_description='retain original')
    proposal=verdict(materials=[dict(object_id='wood',finish={'bump_factor':.5},reason='test')])
    result,changes,rejected=realism.apply_plan(original,original,facts(),proposal)
    assert not changes and rejected
    assert result['objects'][0]['material']['render_finish'] is None


@pytest.mark.parametrize('settings',[{'albedo_gain':[float('nan'),1,1]},{'bevel':.2},{'roughness_delta':.8},{'bump_factor':0},{'albedo_gain':[2,1,1]}])
def test_finish_rejects_unbounded_values(settings):
    with pytest.raises(ValueError):RenderFinish(**settings)


def test_target_light_lock_and_cumulative_bounds():
    original=scene();proposal=verdict(lights=[dict(light_id='lamp',power=201,color=[1,1,1],size=1,reason='too bright')],materials=[dict(object_id='another-room',finish={},reason='outside scope')])
    _,changes,rejected=realism.apply_plan(original,original,facts(),proposal)
    assert not changes and len(rejected)==2
    original['lighting_setup']['lights'][0]['locked']=True
    proposal.lights[0].power=120
    _,changes,rejected=realism.apply_plan(original,original,facts(),proposal)
    assert not changes and len(rejected)==2


def fake_loop(tmp_path,monkeypatch,preferences):
    source=tmp_path/'model.blend';source.write_bytes(b'immutable model');output=tmp_path/'run';output.mkdir();calls=[];comparisons=[]
    request=dict(source=str(source),scene=scene(),revision='b'*32,model_id='a'*32,realism_point_id='new-view',quality='preview')
    def render(payload,folder):
        calls.append(copy.deepcopy(payload));(folder/'image.png').write_bytes(b'test');(folder/'thumb.png').write_bytes(b'thumb')
        write_json(folder/'result.json',dict(quality_check='passed',images=[dict(file='image.png',thumbnail='thumb.png',kind='still',name='view')]))
        write_json(folder/'realism-inventory.json',facts());return 0
    answers=iter(preferences)
    def inspect(folder,base,*args):
        comparisons.append(base.name)
        return realism.Verdict(summary='test',preference=next(answers),reviewed_files=[],materials=[dict(object_id='wood',finish={'bump_factor':.5 if len(comparisons)==1 else .3},reason='soften')])
    monkeypatch.setattr(realism,'inspect',inspect)
    result=realism.optimize(request,output,render)
    return result,read_json(output/'realism-review.json'),read_json(output/'realism-effective.json'),calls,comparisons


def test_later_worse_candidate_does_not_replace_good_preview(tmp_path,monkeypatch):
    result,report,effective,calls,comparisons=fake_loop(tmp_path,monkeypatch,['baseline','candidate','baseline'])
    assert result['realism_status']=='preview_ready'
    assert report['selected_folder']=='realism-attempt-1'
    assert effective['scene']['objects'][0]['material']['render_finish']['bump_factor']==.5
    assert comparisons==['realism-baseline','realism-baseline','realism-attempt-1']
    assert all(c['scene']['groups']==scene()['groups'] for c in calls)
    assert effective['scene']['viewpoints']==scene()['viewpoints']


def test_rejected_first_candidate_keeps_original(tmp_path,monkeypatch):
    result,report,effective,_,_=fake_loop(tmp_path,monkeypatch,['baseline','equivalent','baseline'])
    assert result['realism_status']=='needs_attention' and not report['changed']
    assert effective['scene']==scene()


def test_stale_adoption_fails_without_saving(tmp_path):
    write_json(tmp_path/'realism-review.json',dict(status='preview_ready'))
    write_json(tmp_path/'realism-effective.json',dict(source_revision='b'*32))
    import threading
    studio=SimpleNamespace(store=SimpleNamespace(lock=threading.RLock()),jobs=SimpleNamespace(get=lambda j:dict(project_id='test',operation='studio.render',status='completed',source_revision='b'*32,output='.')),root=lambda p:tmp_path,current=lambda p:dict(revision='c'*32))
    with pytest.raises(Conflict):realism.adopt(studio,'test','job','b'*32)


def test_image_check_bulk_copy_preserves_sample_values():
    from interior.visualization.studio_render_checks import inspect_image,luminance_report
    values=[.2,.3,.4,1]*9000
    class Pixels:
        def __len__(self):return len(values)
        def foreach_get(self,out):
            from array import array
            out[:]=array('f',values)
        def __getitem__(self,index):raise AssertionError('RNA per-pixel reads are forbidden')
    actual=inspect_image(SimpleNamespace(pixels=Pixels()))
    expected=luminance_report([(.2,.3,.4)]*4500)
    assert actual['sample_count']==expected['sample_count']
    assert actual['mean_encoded_luminance']==pytest.approx(expected['mean_encoded_luminance'])


def test_detail_changes_require_native_evidence_and_preserve_dimensions():
    original=scene();native=facts();native['point']=original['viewpoints'][0]
    native['details']=dict(textiles=['wood'],cabinets=[],windows=[dict(id='desk',name='synthetic window')],cameras=[dict(id='frame-1',shot_id='front',target='Desk',eye=[1,1,1.6],yaw=20,pitch=-8,lens=24)])
    result,changes,rejected=realism.apply_plan(original,original,native,verdict(materials=[dict(object_id='wood',finish={'textile':.4},reason='fabric evidence')],exteriors=['desk','missing'],cameras=['frame-1','missing']))
    assert len(changes)==3 and len(rejected)==2
    assert result['groups']==original['groups']
    assert result['viewpoints'][0]['eye']==original['viewpoints'][0]['eye']
    assert result['viewpoints'][0]['shots'][0]['pitch']==-8
    assert result['illustrative_exteriors']==['desk']
    _,changes,rejected=realism.apply_plan(original,original,facts(),verdict(materials=[dict(object_id='wood',finish={'cabinet_front':'+X'},reason='no evidence')]))
    assert not changes and rejected


def test_confirmed_cabinet_front_cannot_be_changed_by_agent():
    original=scene();native=facts();native['details']=dict(cabinets=[dict(object_id='wood',front='+X')])
    _,changes,rejected=realism.apply_plan(original,original,native,verdict(materials=[dict(object_id='wood',finish={'cabinet_front':'-X'},reason='wrong side')]))
    assert not changes and rejected


def test_ceiling_requires_native_evidence_and_does_not_change_confirmed_dimensions():
    original=scene();native=facts();native['details']={'ceiling':{'options':[{'id':'wood','name':'Floor patch','height':2.8}]}}
    result,changes,rejected=realism.apply_plan(original,original,native,verdict(ceilings=['wood','unknown']))
    assert result['ceiling_infill']==['wood'] and len(changes)==1 and len(rejected)==1
    assert result['groups']==original['groups'] and result['objects']==original['objects']
    _,again,_=realism.apply_plan(result,original,native,verdict(ceilings=['wood']))
    assert not again
    with pytest.raises(ValueError):Scene.model_validate(dict(original,ceiling_infill=['unknown']))


def test_shift_camera_is_bounded_and_does_not_move_panorama():
    original=scene();native=facts();native['point']=original['viewpoints'][0]
    native['details']={'cameras':[dict(id='composition',shot_id='front',target='Desk',eye=[1,1,1.6],yaw=20,pitch=0,lens=28,shift_y=-.24,aspect='16:9')]}
    result,changes,rejected=realism.apply_plan(original,original,native,verdict(cameras=['composition']))
    assert result['viewpoints'][0]['shots'][0]['shift_y']==-.24
    assert result['viewpoints'][0]['shots'][0]['aspect']=='16:9'
    assert result['viewpoints'][0]['eye']==original['viewpoints'][0]['eye']
    assert result['groups']==original['groups'] and changes and not rejected
    result['viewpoints'][0]['shots'][0]['shift_y']=-.5
    with pytest.raises(ValueError):Scene.model_validate(result)


def test_review_guide_is_sent_and_snapshotted_for_every_new_project(tmp_path,monkeypatch):
    folder=tmp_path/'baseline';folder.mkdir();(folder/'still.png').write_bytes(b'test-image')
    class Client:
        def __init__(self,path):pass
        def status(self):return {'authenticated':True,'auth_type':'chatgpt'}
        def run(self,prompt,**kwargs):
            assert '天花' in prompt and 'occlusion_fraction' in prompt and '解析度較高不等於更寫實' in prompt
            return {'text':'{"summary":"synthetic review","preference":"baseline","reviewed_files":["baseline/still.png"]}'}
        def close(self):pass
    monkeypatch.setattr(realism,'CodexRuntime',Client)
    realism.inspect(folder,folder,{'images':[{'file':'still.png','kind':'still'}]},None,None,facts(),scene(),tmp_path/'stop',None)
    record=read_json(folder/'review.json')
    assert record['guide_sha256']==realism.digest(folder/'review-guide.txt')


@pytest.mark.parametrize('stale',[False,True])
@pytest.mark.parametrize('other_room',[False,True])
def test_continue_unadopted_preview_only_for_exact_source_and_revision(tmp_path,monkeypatch,stale,other_room):
    previous=tmp_path/'previous';previous.mkdir();original=scene();candidate=copy.deepcopy(original)
    candidate['objects'][0]['material']['render_finish']=RenderFinish(bump_factor=.8).model_dump(mode='json')
    source=tmp_path/'model.blend';source.write_bytes(b'immutable model')
    write_json(previous/'realism-review.json',dict(status='preview_ready',revision=('x' if stale else 'b')*32,source_sha256=realism.digest(source),original_scene_hash=realism.fingerprint(original),effective_scene_hash=realism.fingerprint(candidate),point=dict(id='another-room') if other_room else original['viewpoints'][0]))
    write_json(previous/'realism-effective.json',dict(scene=candidate));write_json(previous/'result.json',dict(quality_check='passed'))
    _,report,_,calls,_=fake_loop(tmp_path,monkeypatch,['baseline','candidate','baseline'])
    assert calls[0]['scene']==(original if stale else candidate)
    assert report.get('baseline_source_job_id')==(None if stale else 'previous')
    assert report['original_scene_hash']==realism.fingerprint(original)


def test_camera_rejection_memory_only_reuses_same_scene_and_revision(tmp_path):
    old=tmp_path/'old';(old/'realism-baseline').mkdir(parents=True)
    current=tmp_path/'new';current.mkdir();baseline=scene()
    camera=dict(eye=[1,2,1.5],yaw=12,pitch=0,lens=28,aspect='16:9')
    source=tmp_path/'source.blend';source.write_bytes(b'synthetic immutable source')
    request=dict(revision='a'*32,realism_point_id='view',source=str(source))
    write_json(old/'realism-review.json',dict(status='preview_ready',source_sha256=realism.digest(source),revision=request['revision'],point={'id':'view'},attempts=[dict(status='not_selected',changes=[dict(kind='camera',parameters=camera)],summary='Too much blank wall')]))
    write_json(old/'realism-baseline/request.json',{'scene':baseline})
    assert realism.prior_camera_failures(current,request,baseline)[0]['parameters']==camera
    assert not realism.prior_camera_failures(current,dict(request,revision='b'*32),baseline)
    modified=copy.deepcopy(baseline);modified['objects'][0]['material']['color']='#998877'
    assert not realism.prior_camera_failures(current,request,modified)
    source.write_bytes(b'new model');assert not realism.prior_camera_failures(current,request,baseline)
    assert realism.camera_signature(camera)==realism.camera_signature(dict(camera,shift_y=0))


def test_color_proposals_are_scoped_bounded_and_do_not_mutate():
    from interior.visualization.realism_color import color_balance_options
    wall=dict(id='a',name='wall-new',editable=True,materials=[dict(editable=True,base_color_linear=[.92,.75,.48],textures=[])],finish=dict(albedo_gain=[.88,.98,1.15]))
    protected=dict(wall,id='b',editable=False)
    wood=dict(wall,id='wood',name='oak cabinet')
    textured=copy.deepcopy(wall);textured['materials'][0]['textures']=['unknown.png']
    original=copy.deepcopy(wall)
    lights=[dict(id='local',editable=True,kind='AREA',color=[1,.88,.72],scope='local'),dict(id='locked',editable=False,kind='AREA',color=[1,.8,.6],scope='local')]
    result=color_balance_options([wall,protected,wood,textured],lights)
    assert wall==original and len(result['walls'])==1
    proposal=result['walls'][0]
    assert all(.65<=v<=1.2 for v in proposal['suggested_albedo_gain'])
    assert proposal['proposed_linear'][0]/proposal['proposed_linear'][2]<1.1
    assert [l['light_id'] for l in result['lights']]==['local']


def test_camera_cannot_drop_a_protected_visible_window():
    original=scene();native=facts();native['point']=original['viewpoints'][0]
    option=dict(id='candidate',shot_id='front',target='sofa',eye=[1,2,1.3],yaw=10,pitch=0,lens=28)
    native['details']=dict(cameras=[option],camera_checks=[dict(shot_id='front',required_windows=['window'])])
    result,changes,rejected=realism.apply_plan(original,original,native,verdict(cameras=['candidate']))
    assert not changes and rejected and result['viewpoints']==original['viewpoints']
    option['preserved_windows']=['window']
    result,changes,rejected=realism.apply_plan(original,original,native,verdict(cameras=['candidate']))
    assert changes and not rejected
    assert result['viewpoints'][0]['eye']==original['viewpoints'][0]['eye']


def test_camera_search_reuse_requires_identical_geometry():
    original=scene();candidate=copy.deepcopy(original)
    candidate['objects'][0]['material']['render_finish']={'albedo_gain':[.8,1,1]}
    candidate['lighting_setup']['lights'][0]['power']=80
    candidate['viewpoints'][0]['shots'][0]['yaw']=20
    assert realism.camera_geometry_key(original)==realism.camera_geometry_key(candidate)
    candidate['groups'][0]['translation']=[1,0,0]
    assert realism.camera_geometry_key(original)!=realism.camera_geometry_key(candidate)
    candidate=copy.deepcopy(original);candidate['ceiling_infill']=['floor']
    assert realism.camera_geometry_key(original)!=realism.camera_geometry_key(candidate)
    candidate=copy.deepcopy(original);candidate['shelf_refinements']=[dict(object_id='wood',contents=['microwave'])]
    assert realism.camera_geometry_key(original)!=realism.camera_geometry_key(candidate)


def test_wall_pixel_evidence_uses_native_masks_and_keeps_facts(tmp_path):
    from PIL import Image
    from interior.workbench.studio.realism_color_evidence import compare_wall_colors
    before=tmp_path/'before';after=tmp_path/'after';before.mkdir();after.mkdir()
    Image.new('RGB',(20,20),(220,190,150)).save(before/'shot.png')
    Image.new('RGB',(20,20),(200,195,190)).save(after/'shot.png')
    facts=dict(objects=[dict(id='wall',name='wall-new',editable=True,screen_regions=[dict(file='shot.png',sample_uv=[[.4,.4]]*12)]),dict(id='wood',name='oak table',editable=True,screen_regions=[dict(file='shot.png',sample_uv=[[.4,.4]]*12)])])
    original=copy.deepcopy(facts);result=compare_wall_colors(before,facts,after,facts)
    assert facts==original and len(result)==1
    assert result[0]['after']['red_blue_ratio']<result[0]['before']['red_blue_ratio']
    assert result[0]['object_id']=='wall'


def test_supplemental_camera_keeps_original_shot_and_furniture():
    original=scene();native=facts();native['point']=original['viewpoints'][0]
    option=dict(id='native-extra',shot_id='coverage-desk',supplemental=True,shot_name='Desk coverage',target='Desk',eye=[1,1,1.6],yaw=90,pitch=-8,lens=24)
    native['details']={'cameras':[option]}
    result,changes,rejected=realism.apply_plan(original,original,native,verdict(cameras=['native-extra']))
    assert not rejected and changes
    assert result['groups']==original['groups'] and result['objects']==original['objects']
    assert result['viewpoints'][0]['shots'][0]==original['viewpoints'][0]['shots'][0]
    assert len(result['viewpoints'][0]['shots'])==2
    repeated,changes,rejected=realism.apply_plan(result,original,native,verdict(cameras=['native-extra']))
    assert repeated==result and not changes
    option['supplemental']=False
    result,changes,rejected=realism.apply_plan(original,original,native,verdict(cameras=['native-extra']))
    assert rejected and not changes and result==original
