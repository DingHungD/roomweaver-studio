"""Opt-in Blender check of every catalog furniture assembly and handoff."""
from unittest.mock import patch
import ezdxf
from interior.workbench.storage import Store, read_json
from interior.workbench.jobs import Jobs
from interior.workbench.studio.service import Studio
from interior.workbench.studio.plan_import import PlanIntake, SavePlan, BuildPlan
from interior.workbench.studio.engine import execute
from interior.workbench.studio.layout_design import CATALOG


def test_catalog_assemblies_survive_native_glb_handoff(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='MODELS',name='Synthetic concepts'))
    with patch.object(Jobs,'loop',return_value=None):jobs=Jobs(store)
    try:
        studio=Studio(store,jobs);plans=PlanIntake(studio)
        doc=ezdxf.new();doc.units=6;m=doc.modelspace()
        m.add_lwpolyline([(0,0),(12,0),(12,18),(0,18)],close=True,dxfattribs={'layer':'floor'})
        m.add_line((0,0),(12,0),dxfattribs={'layer':'wall'})
        for i,asset in enumerate(CATALOG):
            x=1+(i%3)*4;y=1+(i//3)*4;w,d,h=CATALOG[asset]['size']
            m.add_lwpolyline([(x,y),(x+w,y),(x+w,y+d),(x,y+d)],close=True,dxfattribs={'layer':'furniture'})
        source=tmp_path/'concepts.dxf';doc.saveas(source)
        p=plans.create('MODELS',source.name,source.read_bytes());settings=p['settings'];assets=iter(CATALOG)
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
        assert len(groups)==2+len(CATALOG)  # floor + wall + independent assemblies
        assert len(revision['scene']['objects'])>25  # actual legs, seats, cushions, etc.
        folder=studio.root('MODELS')/job['output']
        assert (folder/'model.blend').is_file() and (folder/'model.glb').is_file()
    finally:jobs.close()
