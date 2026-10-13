"""Opt-in Blender check of every catalog furniture assembly and handoff."""
from unittest.mock import patch
import ezdxf
from interior.workbench.storage import Store, read_json
from interior.workbench.jobs import Jobs
from interior.workbench.studio.service import Studio
from interior.workbench.studio.plan_import import PlanIntake, SavePlan, BuildPlan, Assignment
from interior.workbench.studio.engine import execute, blender_executable
from interior.workbench.studio.layout_design import CATALOG

PLAN_ASSETS=Assignment.model_json_schema()['properties']['design_asset']['anyOf'][0]['enum']

def test_plan_furniture_assemblies_survive_native_glb_handoff(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='MODELS',name='Synthetic concepts'))
    with patch.object(Jobs,'loop',return_value=None):jobs=Jobs(store)
    try:
        studio=Studio(store,jobs);plans=PlanIntake(studio)
        doc=ezdxf.new();doc.units=6;m=doc.modelspace()
        m.add_lwpolyline([(0,0),(12,0),(12,18),(0,18)],close=True,dxfattribs={'layer':'floor'})
        m.add_line((0,0),(12,0),dxfattribs={'layer':'wall'})
        for i,asset in enumerate(PLAN_ASSETS):
            x=1+(i%3)*4;y=1+(i//3)*4;w,d,h=CATALOG[asset]['size']
            m.add_lwpolyline([(x,y),(x+w,y),(x+w,y+d),(x,y+d)],close=True,dxfattribs={'layer':'furniture'})
        source=tmp_path/'concepts.dxf';doc.saveas(source)
        p=plans.create('MODELS',source.name,source.read_bytes());settings=p['settings'];assets=iter(PLAN_ASSETS)
        for a in settings['assignments']:
            if a['role']=='furniture':
                asset=next(assets);a.update(name=asset,design_asset=asset,height=CATALOG[asset]['size'][2])
        p=plans.save('MODELS',p['id'],SavePlan(base_revision=p['revision'],settings=settings))
        job=plans.build('MODELS',p['id'],BuildPlan(plan_revision=p['revision']))
        request=read_json(store.state_dir/'jobs'/job['id']/'request.json')
        result=execute(request['project'],request['operation'],request['parameters'])
        job.update(status='completed',result=result);jobs.write(job)
        revision=studio.adopt_import('MODELS',job['id'])
        assert result['handoff']['status']=='passed'
        groups=revision['scene']['groups']
        assert len(groups)==2+len(PLAN_ASSETS)  # floor + wall + independent assemblies
        assert len(revision['scene']['objects'])>25  # actual legs, seats, cushions, etc.
        folder=studio.root('MODELS')/job['output']
        assert (folder/'model.blend').is_file() and (folder/'model.glb').is_file()
    finally:jobs.close()


def test_full_editor_catalog_survives_native_glb_handoff(tmp_path):
    """Decor and lights belong to the editor catalog, not the DXF furniture schema."""
    import json
    import subprocess
    from pathlib import Path
    from interior.workbench.studio.models import ConceptFurniture
    from interior.workbench.studio.service import digest
    items=[ConceptFurniture(id='concept-'+f'{i:032x}',name=asset,asset=asset,size=value['size']).model_dump(mode='json') for i,(asset,value) in enumerate(CATALOG.items())]
    source=tmp_path/'sources';source.mkdir()
    script=tmp_path/'catalog.py'
    module=Path(__file__).resolve().parents[2]/'src/interior/visualization'
    script.write_text('import bpy,sys,json\n'
        f'sys.path.insert(0,{str(module)!r})\n'
        'from concept_geometry import add_blender_furniture\n'
        'bpy.ops.wm.read_factory_settings(use_empty=True)\n'
        f'items=json.loads({json.dumps(items)!r})\n'
        'for i,item in enumerate(items):\n'
        ' add_blender_furniture([item])\n'
        ' for obj in bpy.context.scene.objects:\n'
        "  if obj.get('source_id')==item['id']:obj.location.x+=4*(i%4);obj.location.y+=4*(i//4)\n"
        f'bpy.ops.wm.save_as_mainfile(filepath={str(source/"catalog.blend")!r})\n'
        f'bpy.ops.export_scene.gltf(filepath={str(source/"catalog.glb")!r},export_format="GLB",export_extras=True)\n',encoding='utf-8')
    result=subprocess.run([blender_executable(),'--background','--disable-autoexec','--python-exit-code','1','--python',str(script)],capture_output=True,text=True,encoding='utf-8',timeout=90)
    assert result.returncode==0,result.stdout[-4000:]+result.stderr
    hashes={p.name:digest(p) for p in source.iterdir()}
    result=execute(tmp_path,'studio.prepare',dict(job_id='a'*32,output='runs/interior-studio/catalog',source=dict(native='sources/catalog.blend',preview='sources/catalog.glb')))
    assert result['handoff']['status']=='passed'
    model=read_json(tmp_path/'runs/interior-studio/catalog/model.json')
    assert {p['id'] for item in items for p in item['parts']}=={o['id'] for o in model['objects']}
    assert hashes=={p.name:digest(p) for p in source.iterdir()}
