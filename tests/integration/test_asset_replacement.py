"""Real Blender replacement using the public CC0 example library, no cloud calls."""
import copy,shutil
from pathlib import Path
from unittest.mock import patch
from interior.workbench.storage import Store,read_json,write_json
from interior.workbench.jobs import Jobs
from interior.workbench.studio.service import Studio,digest
from interior.workbench.studio.plan_import import PlanIntake,BuildPlan
from interior.workbench.studio.models import ConceptFurniture
from interior.workbench.studio.asset_matching import AssetMatching
from interior.workbench.studio.engine import execute

ROOT=Path(__file__).parents[2]

def test_real_model_and_material_replacement_roundtrip_render_and_restore(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='ASSET_TEST',name='Synthetic asset replacement'))
    with patch.object(Jobs,'loop',return_value=None):jobs=Jobs(store)
    try:
        studio=Studio(store,jobs);plans=PlanIntake(studio);assets=AssetMatching(studio,None)
        source=ROOT/'examples/dxf-courtyard/courtyard.dxf'
        packet=plans.create('ASSET_TEST',source.name,source.read_bytes())
        job=plans.build('ASSET_TEST',packet['id'],BuildPlan(plan_revision=packet['revision']))
        def run(job):
            request=read_json(store.state_dir/'jobs'/job['id']/'request.json')
            output=execute(request['project'],request['operation'],request['parameters'])
            job.update(status='completed',result=output);jobs.write(job);return output
        run(job);rev=studio.adopt_import('ASSET_TEST',job['id']);source_model=studio.root('ASSET_TEST')/job['output']/'model.blend'
        original_hash=digest(source_model)
        scene=copy.deepcopy(rev['scene'])
        f=ConceptFurniture(id='concept-'+'b'*32,name='Test chair',asset='chair',size=(.7,.7,1)).model_dump(mode='json')
        scene['concept_furniture']=[f]
        scene['groups'].append(dict(id=f['id'],name=f['name'],children=[p['id'] for p in f['parts']],translation=[3,2,0],rotation=45,rotation_pivot=[0,0,0],method='concept',deleted=False))
        scene['objects'] += [dict(id=p['id'],name=p['name'],room_id='interior',material={}) for p in f['parts']]
        scene['viewpoints']=[dict(id='test',name='Test',room_id='interior',eye=[2.5,1.8,1.6],shots=[dict(id='north',name='North',yaw=0,pitch=0,lens=28)])]
        scene['lighting_setup'].update(enabled=True,mode='day',auto_adjust=False,lights=[dict(id='bound',name='Bound lamp',kind='POINT',group_id=f['id'],position=[0,0,2],power=100)])
        rev=studio.save('ASSET_TEST',scene,rev['revision']);before=copy.deepcopy(rev)
        manifest=read_json(ROOT/'examples/daylight-apartment/assets/manifest.json')['assets']
        def replacement(asset_key,kind,revision,object_id=None):
            a=next(x for x in manifest if x['key']==asset_key)
            item=dict(asset_id=a['asset_id'],version_id=a['version_id'],name=a['name'],url='https://www.blenderkit.com/asset-gallery-detail/'+a['asset_id']+'/',license='cc_zero',is_free=True,kind=kind)
            job=jobs.submit_studio('ASSET_TEST','replace',dict(revision=revision['revision'],task_id='d'*32,asset=item,group_id=f['id'],object_id=object_id,rotation=90),f'replace-{asset_key}')
            def download(candidate,destination,scene_id):
                shutil.copy2(ROOT/'examples/daylight-apartment/assets'/a['file'],destination)
                return dict(sha256=digest(destination),asset_id=a['asset_id'])
            with patch('interior.workbench.studio.blenderkit_client.download',side_effect=download):result=run(job)
            assert result['handoff']['status']=='passed'
            return assets.adopt('ASSET_TEST',job['id'],revision['revision']),job
        replaced,model_job=replacement('chair','model',rev)
        g=next(g for g in replaced['scene']['groups'] if g['id']==f['id'])
        assert g['translation']==[3,2,0] and g['rotation']==45 and g['asset_reference']['status']=='applied'
        assert not replaced['scene']['concept_furniture'] and len(g['children'])>0
        assert replaced['scene']['lighting_setup']['lights'][0]['group_id']==f['id']
        assert set(o['id'] for o in before['scene']['objects'] if o['id'] not in [p['id'] for p in f['parts']]).issubset(o['id'] for o in replaced['scene']['objects'])
        material_rev,material_job=replacement('oak-furniture','material',replaced,g['children'][0])
        mat=next(o['material'] for o in material_rev['scene']['objects'] if o['id']==g['children'][0])
        assert mat['color'] is None and mat['asset_reference']['kind']=='material'
        render=jobs.submit_studio('ASSET_TEST','render',dict(revision=material_rev['revision'],quality='preview'),'asset-test-render')
        rendered=run(render)
        assert len(rendered['images'])==2 and rendered['quality_check']=='passed'
        assert digest(source_model)==original_hash
        old_folder=studio.root('ASSET_TEST')/model_job['output']
        assert (old_folder/'model.blend').exists()  # adopting no longer deletes anything
        from interior.workbench.studio.asset_storage import clean_replacements
        clean_replacements(studio,'ASSET_TEST',material_rev['revision'])
        assert not (old_folder/'model.blend').exists() and (old_folder/'model-retired.json').exists()
        assert not (studio.root('ASSET_TEST')/material_job['output']/'asset.blend').exists()
        from interior.workbench.storage import Conflict
        import pytest
        with pytest.raises(Conflict,match='釋放'):assets.restore('ASSET_TEST',material_rev['revision'])
        assert assets.adopt('ASSET_TEST',material_job['id'],material_rev['revision'])['revision']==material_rev['revision']
    finally:jobs.close()
