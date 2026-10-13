"""Real Blender template fallback through the normal revision/job/handoff pipeline."""
import copy
from unittest.mock import patch
from pathlib import Path
from interior.workbench.storage import Store,read_json
from interior.workbench.jobs import Jobs
from interior.workbench.studio.service import Studio,digest
from interior.workbench.studio.plan_import import PlanIntake,BuildPlan
from interior.workbench.studio.models import ConceptFurniture
from interior.workbench.studio.asset_matching import AssetMatching
from interior.workbench.studio.engine import execute

def test_generated_cabinet_preserves_confirmed_size_other_geometry_and_sources(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='TEMPLATE',name='Synthetic template test'))
    with patch.object(Jobs,'loop',return_value=None):jobs=Jobs(store)
    try:
        studio=Studio(store,jobs);plans=PlanIntake(studio)
        source=Path(__file__).parents[2]/'tests/fixtures/legacy-examples/dxf-courtyard/courtyard.dxf'
        packet=plans.create('TEMPLATE',source.name,source.read_bytes());job=plans.build('TEMPLATE',packet['id'],BuildPlan(plan_revision=packet['revision']))
        def run(job):
            request=read_json(store.state_dir/'jobs'/job['id']/'request.json');result=execute(request['project'],request['operation'],request['parameters'])
            job.update(status='completed',result=result);jobs.write(job);return result
        run(job);rev=studio.adopt_import('TEMPLATE',job['id']);native=studio.root('TEMPLATE')/job['output']/'model.blend';before_hash=digest(native)
        scene=copy.deepcopy(rev['scene']);f=ConceptFurniture(id='concept-'+'b'*32,name='Test cabinet',asset='cabinet',size=(1,.5,1.2)).model_dump(mode='json')
        scene['concept_furniture']=[f];scene['groups'].append(dict(id=f['id'],name=f['name'],children=[p['id'] for p in f['parts']],translation=[15,15,0],rotation=0,rotation_pivot=[0,0,0],method='concept',deleted=False,asset_requirements=dict(purpose='cabinet',dimension_source='confirmed',dimensions=[1,.5,1.2],evidence='synthetic D1')))
        scene['objects'] += [dict(id=p['id'],name=p['name'],room_id='interior',material={}) for p in f['parts']]
        rev=studio.save('TEMPLATE',scene,rev['revision']);before=copy.deepcopy(rev['scene'])
        recipe=dict(purpose='cabinet',dimensions=[1,.5,1.2],front='+X',style='warm oak',version=1)
        replacement=jobs.submit_studio('TEMPLATE','replace',dict(revision=rev['revision'],task_id='d'*32,group_id=f['id'],generated=recipe,rotation=0,auto_fit=True,asset_requirements=before['groups'][-1]['asset_requirements']),'generated-roundtrip')
        with patch('interior.workbench.studio.blenderkit_client.download') as download:
            result=run(replacement);download.assert_not_called()
        assert result['handoff']['status']=='passed'
        adopted=AssetMatching(studio,None).adopt('TEMPLATE',replacement['id'],rev['revision'])
        g=next(g for g in adopted['scene']['groups'] if g['id']==f['id'])
        assert g['generated_reference']['source']=='bounded_parametric_template' and not g['asset_reference']
        assert g['asset_requirements']==before['groups'][-1]['asset_requirements'] and g['translation']==[15,15,0]
        assert [g for g in adopted['scene']['groups'] if g['id']!=f['id']]==[g for g in before['groups'] if g['id']!=f['id']]
        report=read_json(studio.root('TEMPLATE')/replacement['output']/'replacement-report.json')
        assert report['generated'] and report['direction_status']=='needs_review'
        import pytest
        assert report['resulting_dimensions']==pytest.approx([1,.5,1.2],abs=.002)
        assert digest(native)==before_hash
        # A downloaded rectangular model can be resized without changing target
        # requirements or its shader. The asset is synthetic, with no cloud calls.
        import subprocess,os,shutil
        asset=tmp_path/'synthetic-cabinet.blend';script=tmp_path/'make-cabinet.py'
        script.write_text("import bpy\nbpy.ops.object.select_all(action='SELECT')\nbpy.ops.object.delete(use_global=False)\nmat=bpy.data.materials.new('Synthetic oak');mat.diffuse_color=(.5,.3,.1,1)\nfor x in (-.39,.39):\n bpy.ops.mesh.primitive_cube_add(size=1,location=(x,0,.6));o=bpy.context.object;o.dimensions=(.02,.5,1.2);bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat)\nfor z in (.01,1.19):\n bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,z));o=bpy.context.object;o.dimensions=(.76,.5,.02);bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat)\nbpy.ops.wm.save_as_mainfile(filepath="+repr(str(asset))+")\n",encoding='utf-8')
        subprocess.run([os.environ['INTERIOR_BLENDER'],'--background','--factory-startup','--python',str(script)],check=True,capture_output=True)
        item=dict(asset_id='11111111-1111-4111-8111-111111111111',version_id='22222222-2222-4222-8222-222222222222',name='Synthetic cabinet',url='https://www.blenderkit.com/asset-gallery-detail/11111111-1111-4111-8111-111111111111/',kind='model',is_free=True,license='cc_zero')
        resized=jobs.submit_studio('TEMPLATE','replace',dict(revision=adopted['revision'],task_id='d'*32,group_id=f['id'],asset=item,dimension_fit='adapt',rotation=0,auto_fit=True,asset_requirements=g['asset_requirements']),'adapt-cabinet-dimensions')
        with patch('interior.workbench.studio.blenderkit_client.download',side_effect=lambda _a,dest,_job: (shutil.copy2(asset,dest) and {'source':'synthetic'})):
            run(resized)
        final=AssetMatching(studio,None).adopt('TEMPLATE',resized['id'],adopted['revision'])
        fitted=next(g for g in final['scene']['groups'] if g['id']==f['id'])
        assert fitted['asset_requirements']==g['asset_requirements'] and not fitted['generated_reference']
        report=read_json(studio.root('TEMPLATE')/resized['output']/'replacement-report.json')
        assert report['dimension_adjustment']['target_dimensions']==[1,.5,1.2]
        assert report['resulting_dimensions']==pytest.approx([1,.5,1.2],abs=.002)
        assert digest(native)==before_hash
        # A new project's unknown placeholder height must not stretch this product.
        soft_scene=copy.deepcopy(final['scene']);soft=next(g for g in soft_scene['groups'] if g['id']==f['id'])
        soft['asset_requirements']=dict(purpose='cabinet',dimension_source='unknown',dimensions=[1,.5,2.4],evidence='')
        soft_rev=studio.save('TEMPLATE',soft_scene,final['revision'])
        soft_job=jobs.submit_studio('TEMPLATE','replace',dict(revision=soft_rev['revision'],task_id='d'*32,group_id=f['id'],asset=item,dimension_fit='adapt',rotation=0,auto_fit=True,asset_requirements=soft['asset_requirements']),'soft-height-cabinet')
        with patch('interior.workbench.studio.blenderkit_client.download',side_effect=lambda _a,dest,_job: (shutil.copy2(asset,dest) and {'source':'synthetic'})):
            run(soft_job)
        soft_adopted=AssetMatching(studio,None).adopt('TEMPLATE',soft_job['id'],soft_rev['revision'])
        soft_report=read_json(studio.root('TEMPLATE')/soft_job['output']/'replacement-report.json')
        assert soft_report['dimension_adjustment'] is None
        assert soft_report['resulting_dimensions']==pytest.approx([.8,.5,1.2],abs=.002)
        assert soft_report['fit_policy']['height_reference_only']
        assert next(g for g in soft_adopted['scene']['groups'] if g['id']==f['id'])['asset_requirements']==soft['asset_requirements']
        assert digest(native)==before_hash
        # Selected repair keeps a deliberate 90-degree orientation and uniformly scales only soft dimensions.
        repair=jobs.submit_studio('TEMPLATE','replace',dict(revision=soft_adopted['revision'],task_id='d'*32,group_id=f['id'],asset=item,dimension_fit='uniform',rotation=90,auto_fit=True,repair_scale=.9,asset_requirements=soft['asset_requirements']),'selected-soft-repair')
        with patch('interior.workbench.studio.blenderkit_client.download',side_effect=lambda _a,dest,_job: (shutil.copy2(asset,dest) and {'source':'synthetic'})):
            run(repair)
        report=read_json(studio.root('TEMPLATE')/repair['output']/'replacement-report.json')
        assert report['repair_scale']==.9 and report['rotation']==90
        assert report['resulting_dimensions']==pytest.approx([.28125,.45,.675],abs=.003)
        assert digest(native)==before_hash
    finally:jobs.close()
