"""Ordinary DXF conversion automatically fixes safe seams before GLB/native handoff."""
from unittest.mock import patch
import ezdxf
import pytest
from interior.workbench.storage import Store,read_json
from interior.workbench.jobs import Jobs
from interior.workbench.studio.service import Studio,digest
from interior.workbench.studio.plan_import import PlanIntake,BuildPlan,check_plan
from interior.workbench.studio.engine import execute

@pytest.mark.parametrize('rotation',[0,.35])
def test_import_automatically_repairs_floor_seams_before_handoff(tmp_path,rotation):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='FLOOR',name='Synthetic floor seams'))
    with patch.object(Jobs,'loop',return_value=None):jobs=Jobs(store)
    try:
        studio=Studio(store,jobs);plans=PlanIntake(studio)
        d=ezdxf.new();d.units=6;m=d.modelspace()
        for a,b in [((0,0),(5,0)),((5,0),(5,4)),((5,4),(0,4)),((0,4),(0,0)),((2.5,0),(2.5,4))]:m.add_line(a,b,dxfattribs={'layer':'wall'})
        for points,layer in [([(0,0),(2.4,0),(2.4,4),(0,4)],'floor'),([(2.6,0),(5,0),(5,4),(2.6,4)],'floor'),([(1,1),(1.5,1),(1.5,1.5),(1,1.5)],'furniture')]:m.add_lwpolyline(points,close=True,dxfattribs={'layer':layer})
        m.add_line((2.5,1),(2.5,2.2),dxfattribs={'layer':'door'})
        if rotation:
            from ezdxf.math import Matrix44
            for entity in m:entity.transform(Matrix44.z_rotate(rotation))
        source=tmp_path/'seams.dxf';d.saveas(source)
        original_hash=digest(source)
        plan=plans.create('FLOOR',source.name,source.read_bytes())
        def run(job):
            request=read_json(store.state_dir/'jobs'/job['id']/'request.json')
            result=execute(request['project'],request['operation'],request['parameters']);job.update(status='completed',result=result);jobs.write(job);return result
        checked=check_plan(plan['parsed'],plan['settings'])
        expected=checked['floor_continuity'];assert expected['patches']
        # Ordinary create-3D request: no repair flag, separate button or second job.
        initial=plans.build('FLOOR',plan['id'],BuildPlan(plan_revision=plan['revision']))
        assert plans.build('FLOOR',plan['id'],BuildPlan(plan_revision=plan['revision']))['id']==initial['id']
        result=run(initial);assert result['handoff']['status']=='passed'
        folder=studio.root('FLOOR')/initial['output']
        audit=read_json(folder/'plan-build.json')['floor_continuity']
        assert audit['status']=='repaired_and_verified'
        assert audit['patch_count']==len(expected['patches'])
        assert audit['added_area']==pytest.approx(expected['repair_area'],abs=.00001)
        from interior.workbench.studio.handoff import read_glb
        nodes=read_glb(folder/'model.glb')['nodes']
        patches=[n for n in nodes if n.get('extras',{}).get('floor_repair_id')]
        assert len(patches)==len(expected['patches'])
        assert digest(source)==original_hash
        assert read_json(folder/'confirmed-plan.json')['settings']==plan['settings']
        rev=studio.adopt_import('FLOOR',initial['id'])
        assert len([g for g in rev['scene']['groups'] if g['method']=='structural_floor'])==1
        assert any(i['role']=='furniture' for i in checked['items'])
        assert len(rev['scene']['groups'])>=3  # floor, walls and the necessary furniture
    finally:jobs.close()
