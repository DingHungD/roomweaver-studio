"""General CAD preprocessing on unrelated synthetic plans, never client fixtures."""
import math
from pathlib import Path
from unittest.mock import patch

import ezdxf
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union

from interior.workbench.jobs import Jobs
from interior.workbench.server import create_app
from interior.workbench.storage import read_json
from interior.workbench.studio.plan_import import parse_dxf,suggested_settings,check_plan


def fixture(path,scale=1,offset=(0,0),unit=6,curves=True):
    doc=ezdxf.new();doc.units=unit;m=doc.modelspace()
    x,y=offset
    def p(a,b,z=0):return (x+a*scale,y+b*scale,z*scale)
    m.add_lwpolyline([p(0,0)[:2],p(8,0)[:2],p(8,6)[:2],p(0,6)[:2]],close=True,dxfattribs={'layer':'wall'})
    m.add_text('Living room',dxfattribs={'insert':p(4,3),'height':.2*scale})
    if curves:
        m.add_arc(p(1,1),.7*scale,0,90)
        m.add_circle(p(5,4),.3*scale)
        m.add_line(p(2,0,.01),p(3,0,.01))
        for i in range(15):m.add_line(p(0,i*.2),p(1,i*.2))
    doc.saveas(path);return doc


@pytest.mark.parametrize('scale,offset,unit',[(1,(0,0),6),(100,(8000,-4000),5),(1000,(-30000,50000),4)])
def test_curves_projection_and_floor_inference_scale_offset_independent(tmp_path,scale,offset,unit):
    path=tmp_path/'unrelated.dxf';fixture(path,scale,offset,unit)
    before=path.read_bytes();p=parse_dxf(path,prepare=True);s=suggested_settings(p)
    report=p['cad_preparation']
    assert report['counts']['curves']==2 and report['counts']['projected']==1
    assert not p['issues']
    floors=[f for f in p['features'] if f['kind']=='INFERRED_FLOOR']
    shape=unary_union([Polygon(f['points']) for f in floors])
    assert shape.area/scale**2==pytest.approx(48-math.pi*.3**2,abs=.001)
    assert path.read_bytes()==before
    s['reviewed']=[q['id'] for q in report['questions']]
    assert check_plan(p,s)['status']=='ready'


def test_hatch_hole_and_unknown_units_not_silently_filled_or_accepted(tmp_path):
    path=tmp_path/'courtyard.dxf';doc=fixture(path,curves=False);m=doc.modelspace()
    # Remove room label so only the explicitly named floor hatch supplies area.
    for e in list(m.query('TEXT')):m.delete_entity(e)
    hatch=m.add_hatch(dxfattribs={'layer':'floor'});hatch.dxf.pattern_name='TILE'
    hatch.dxf.solid_fill=0
    hatch.paths.add_polyline_path([(0,0),(8,0),(8,6),(0,6)],is_closed=True,flags=1)
    hatch.paths.add_polyline_path([(3,2),(5,2),(5,4),(3,4)],is_closed=True,flags=0)
    doc.saveas(path)
    p=parse_dxf(path,prepare=True)
    floors=[Polygon(f['points']) for f in p['features'] if f['kind']=='INFERRED_FLOOR']
    shape=unary_union(floors)
    assert shape.area==pytest.approx(44) and not shape.covers(Point(4,3))


def test_multiple_levels_and_tilted_entities_remain_blockers(tmp_path):
    path=tmp_path/'two-levels.dxf';doc=fixture(path,curves=False)
    for z in [0,3]:
        for i in range(10):doc.modelspace().add_line((i,0,z),(i,4,z))
    doc.modelspace().add_circle((1,1),.5,dxfattribs={'extrusion':(0,1,0)})
    doc.saveas(path);p=parse_dxf(path,prepare=True)
    assert any('樓層' in i['reason'] for i in p['issues'])
    assert any('OCS' in i['reason'] for i in p['issues'])
    assert check_plan(p,suggested_settings(p))['status']=='blocked'


def test_dimensions_explicit_unit_conflict_and_confirmed_revision_upgrade(tmp_path):
    path=tmp_path/'source.dxf';doc=fixture(path,100,(3000,2000),1,curves=False)
    d=doc.modelspace().add_linear_dim(base=(3000,1900),p1=(3000,2000),p2=(3800,2000),text='800 cm')
    d.render();doc.saveas(path)
    p=parse_dxf(path,prepare=True)
    assert p['cad_preparation']['header_units']=='inch'
    assert p['cad_preparation']['explicit_units']=='cm'
    assert p['detected_units']=='cm'
    assert any(q['kind']=='units' for q in p['cad_preparation']['questions'])
    with patch.object(Jobs,'loop',return_value=None):
        with TestClient(create_app(tmp_path/'workspace'),base_url='http://127.0.0.1') as c:
            c.headers['X-Workbench-Token']=c.get('/api/session').json()['token']
            c.app.state.store.create_project(dict(id='CAD',name='new case'))
            packet=c.post('/api/studio/projects/CAD/plans/upload',files={'file':('source.dxf',path.read_bytes())}).json()
            settings=packet['settings'];settings['cad_unit_confirmed']=True;settings['cad_unit_evidence']='User confirmed centimetres'
            settings['assignments'][0]['height']=3.1
            saved=c.put(f"/api/studio/projects/CAD/plans/{packet['id']}",json=dict(base_revision=packet['revision'],settings=settings)).json()
            prepared=c.post(f"/api/studio/projects/CAD/plans/{packet['id']}/prepare",json=dict(base_revision=saved['revision']))
            assert prepared.status_code==200,prepared.text
            prepared=prepared.json();assert prepared['settings']['units']=='cm' and prepared['settings']['cad_unit_confirmed']
            assert prepared['settings']['assignments'][0]['height']==3.1
            assert prepared['parsed']['cad_preparation']['dimensions'][0]['raw_measurement']==800
            prior=c.app.state.store.project('CAD').root/'workflows/plan-import'/packet['id']/'revisions'/f"{saved['revision']}.json"
            assert read_json(prior)['settings']['assignments'][0]['height']==3.1
            bad=dict(prepared['settings'],units='m')
            response=c.put(f"/api/studio/projects/CAD/plans/{packet['id']}",json=dict(base_revision=prepared['revision'],settings=bad))
            assert response.status_code==422 and '已確認尺寸' in response.text


def test_unlabelled_dimension_value_never_fixes_header_by_size_heuristic(tmp_path):
    path=tmp_path/'ambiguous.dxf';doc=fixture(path,100,unit=1,curves=False)
    dim=doc.modelspace().add_linear_dim(base=(0,-20),p1=(0,0),p2=(800,0));dim.render();doc.saveas(path)
    p=parse_dxf(path,prepare=True)
    assert p['detected_units']=='inch'
    assert any(q['kind']=='units' for q in p['cad_preparation']['questions'])
    assert any('單位' in e for e in check_plan(p,suggested_settings(p))['errors'])


def test_overridden_dimension_discrepancy_does_not_move_wall_vertices(tmp_path):
    path=tmp_path/'overridden.dxf';doc=fixture(path,curves=False)
    dim=doc.modelspace().add_linear_dim(base=(0,-1),p1=(0,0),p2=(8,0),text='9 m');dim.render();doc.saveas(path)
    p=parse_dxf(path,prepare=True)
    assert p['cad_preparation']['dimensions'][0]['conflict']
    assert next(f for f in p['features'] if f['layer']=='wall')['points'][1]==[8,0]
