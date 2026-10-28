"""A drawing is original CAD, never the polygons created for a future model."""
import copy
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

import ezdxf
import pytest
from fastapi.testclient import TestClient

from test_plan_semantics import system
from interior.workbench.jobs import Jobs
from interior.workbench.server import create_app
from interior.workbench.studio.cad_source import source_geometry,generate,raw_frame,SourceContext
from interior.workbench.studio.plan_import import parse_dxf,suggested_settings
from interior.workbench.studio.plan_semantics import site_packet


def source(path,offset=(0,0)):
    doc=ezdxf.new();doc.units=6;m=doc.modelspace();x,y=offset
    floor=m.add_lwpolyline([(x,y),(x+8,y),(x+8,y+6),(x,y+6)],close=True,dxfattribs={'layer':'floor'})
    circle=m.add_circle((x+3,y+3),2,dxfattribs={'layer':'furniture'})
    text=m.add_text('Living room',dxfattribs={'insert':(x+2,y+3),'height':.2})
    hatch=m.add_hatch(color=3,dxfattribs={'layer':'floor-pattern'})
    hatch.paths.add_polyline_path([(x,y),(x+8,y),(x+8,y+6),(x,y+6)],is_closed=True,flags=1)
    hatch.paths.add_polyline_path([(x+5,y+4),(x+6,y+4),(x+6,y+5),(x+5,y+5)],is_closed=True,flags=0)
    hatch.set_pattern_fill('ANSI31',scale=.3)
    dim=m.add_linear_dim(base=(x,y-1),p1=(x,y),p2=(x+8,y));dim.render()
    doc.saveas(path)
    return doc,dict(floor=floor.dxf.handle,circle=circle.dxf.handle,text=text.dxf.handle,hatch=hatch.dxf.handle)


@pytest.mark.parametrize('offset',[(0,0),(-20,40)])
def test_curve_outline_is_not_its_prepared_triangle_mesh(tmp_path,offset):
    path=tmp_path/'synthetic.dxf';_,ids=source(path,offset)
    parsed=parse_dxf(path,prepare=True)
    pieces=[f for f in parsed['features'] if f.get('source_handle')==ids['circle']]
    assert len(pieces)>1  # The old display incorrectly drew these triangle edges.
    graph=source_geometry(path,1,list(offset))
    circles=[g for g in graph if g['kind']=='CIRCLE']
    assert len(circles)==1 and len(circles[0]['points'])>100 and circles[0]['closed']
    assert all('-part-' not in g['id'] for g in graph)
    boundaries=[g for g in graph if g['kind']=='HATCH']
    assert len(boundaries)==2 and all(g['closed'] for g in boundaries)


def test_adopted_semantic_shapes_never_become_source_drawing(tmp_path):
    path=tmp_path/'unrelated.dxf';source(path)
    parsed=parse_dxf(path,prepare=True);settings=suggested_settings(parsed)
    settings['cad_unit_confirmed']=True
    packet=dict(parsed=parsed,settings=settings,revision='v1',source={'path':path.name},_root=str(tmp_path))
    before=site_packet(packet)['geometry']
    parsed['features'].append(dict(id='fake-adopted-triangle',kind='SEMANTIC',layer='floor',points=[[0,0],[8,6],[8,0]],closed=True))
    settings['assignments'].append(dict(id='fake-adopted-triangle',name='Model-only piece',role='ignore',offset=[0,0]))
    after=site_packet(packet)['geometry']
    assert after==before
    assert all(g['kind'] not in ('INFERRED_FLOOR','SEMANTIC') for g in after)


def test_svg_preserves_hatching_dimensions_curves_and_real_source_handles(tmp_path):
    path=tmp_path/'drawing.dxf';_,ids=source(path)
    before=path.read_bytes();drawing=generate(path)
    root=ET.fromstring('<svg>'+drawing['markup']+'</svg>')
    handles={n.get('data-cad-handle') for n in root.iter()}
    assert ids['circle'] in handles and ids['hatch'] in handles
    assert 'floor-pattern' in drawing['layers']
    paths=[n for n in root.iter() if n.tag=='path']
    assert any('c' in n.get('d','') for n in paths),'Circular paths retain curves instead of polygon chords'
    assert drawing['drawing_paths']>len(ids)
    assert all(not any(k.startswith('on') for k in n.attrib) for n in root.iter())
    assert not any(n.tag in ('script','foreignObject','image') for n in root.iter())
    assert path.read_bytes()==before


def test_projection_to_saved_question_frame_preserves_coordinates():
    view=dict(width=1000,height=800,bounds=[-1,-2,9,6],scale=90,pad=40)
    assert raw_frame(view,.01,[30,-20])==pytest.approx([2855.55555556,-2244.44444444,3966.66666667,-1355.55555556])


def test_font_resolution_does_not_read_attribute_tags_from_other_entity_schemas():
    doc=ezdxf.new();m=doc.modelspace();context=SourceContext(doc)
    for entity in [m.add_text(''),m.add_line((0,0),(1,1)),m.add_attdef('圖名',text='')]:
        context.resolve_font(entity)


def test_hidden_source_layers_do_not_become_visible_interpreted_objects(tmp_path):
    path=tmp_path/'layers.dxf';doc,_=source(path)
    layer=doc.layers.new('old-hidden');line=doc.modelspace().add_line((2,2),(6,4),dxfattribs={'layer':layer.dxf.name})
    hidden=doc.modelspace().add_line((0,0),(6,5),dxfattribs={'invisible':1})
    layer.off();doc.saveas(path)
    ids={g['id'] for g in source_geometry(path,1,[0,0])}
    assert 'e-'+line.dxf.handle not in ids and 'e-'+hidden.dxf.handle not in ids
    assert 'old-hidden' not in generate(path)['layers']


def test_preview_api_works_before_unit_confirmation_and_caches_without_plan_changes(tmp_path):
    path=tmp_path/'source.dxf';source(path)
    with patch.object(Jobs,'loop',return_value=None):
        with TestClient(create_app(tmp_path/'workspace'),base_url='http://127.0.0.1') as c:
            c.headers['X-Workbench-Token']=c.get('/api/session').json()['token']
            c.app.state.store.create_project(dict(id='PREVIEW',name='Synthetic'))
            packet=c.post('/api/studio/projects/PREVIEW/plans/upload',files={'file':('source.dxf',path.read_bytes())}).json()
            url=f"/api/studio/projects/PREVIEW/plans/{packet['id']}/source-drawing"
            first=c.get(url);assert first.status_code==200,first.text
            with patch('interior.workbench.studio.cad_source.generate',side_effect=AssertionError('Cached source drawing must not be recomputed')):
                assert c.get(url).json()==first.json()
            assert c.get('/api/studio/projects/PREVIEW/plans/current').json()['revision']==packet['revision']
            current=c.app.state.store.project('PREVIEW').root/packet['source']['path']
            current.write_bytes(current.read_bytes()+b'changed')
            assert c.get(url).status_code==422


def test_legacy_source_candidate_cannot_be_adopted_after_display_contract_changes(system):
    from uuid import uuid4
    from test_plan_semantics import candidate
    from interior.workbench.storage import read_json,write_json
    from interior.workbench.studio.plan_semantics import PlanSemantics,SemanticRequest,AdoptSemantics
    studio,plans,packet,_=system
    class Agents:
        def start(self,kind,model,payload,identifier):self.result=dict(status='passed',candidate=candidate(payload['site']))
        def get(self,identifier):return self.result
    service=PlanSemantics(studio,Agents())
    run=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='test',operation_id=uuid4().hex))
    path=service.folder('UNRELATED',packet['id'])/'runs'/run['id']/'request.json'
    old=read_json(path);old['site'].pop('source_graph_version');write_json(path,old)
    with pytest.raises(ValueError,match='舊版 CAD'):
        service.adopt('UNRELATED',packet['id'],run['id'],AdoptSemantics(base_revision=packet['revision']))
    assert plans.current('UNRELATED',packet['id'])['revision']==packet['revision']
