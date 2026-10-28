"""Native source binding is reusable across unrelated drawings, units and origins."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from interior.workbench.studio.plan_semantics import validate, prompt
from interior.workbench.studio.native_intake import reader_executable
from interior.workbench.studio.source_binding import host_compatible
from test_plan_semantics import system


def source_case(dx=0,dy=0):
    def points(values):return [[x+dx,y+dy] for x,y in values]
    def geom(id,p,closed=True):return dict(id=id,layer='mixed',kind='LWPOLYLINE' if closed else 'LINE',closed=closed,points=points(p),native_exact=True)
    geometry=[geom('perimeter',[[0,0],[8,0],[8,6],[0,6]]),geom('wall-band',[[0,0],[8,0],[8,.2],[0,.2]]),
              geom('jamb-a',[[1,0],[1,.2]],False),geom('jamb-b',[[2,0],[2,.2]],False),
              geom('window-frame',[[4,.04],[5,.04],[5,.16],[4,.16]]),geom('furniture',[[2,2],[3,2],[3,3],[2,3]])]
    def binding(method,*refs):return dict(method=method,refs=[dict(id=id,edge=edge) for id,edge in refs])
    def item(id,role,b,closed=False):return dict(id=id,name=id,room_id='living',role=role,
        points=[[60,60],[61,60],[61,61],[60,61]] if closed else [[60,60],[61,60]],
        closed=closed,height=.75 if role=='furniture' else 2.1,thickness=.2,base=0,
        host_id='wall' if role in ('door','window') else None,source_ids=['label'],evidence='Native drawing references',source_binding=b)
    site=dict(native_dwg=dict(schema='source-bound-v2',source_sha256='a'*64),source_graph_version='source-only-v2',units='m',source_is_image=False,geometry=geometry,
        texts=[dict(id='label',point=points([[3,3]])[0],text='Living')],dimensions=[],
        floors=[dict(id='perimeter',points=geometry[0]['points'])],floor_locked=True)
    proposal=dict(summary='Original coordinates',rooms=[dict(id='living',name='Living',points=geometry[0]['points'],source_ids=['label'],evidence='Native label')],
        elements=[item('wall','wall',binding('pair',('wall-band',0),('wall-band',2))),
                  item('door','door',binding('between',('jamb-a',0),('jamb-b',0))),
                  item('window','window',binding('pair',('window-frame',0),('window-frame',2))),
                  item('cabinet','furniture',binding('outline',('furniture',0)),True)],
        door_state='present',window_state='present',furniture_state='present',inventory_evidence='Existing source furniture',questions=[])
    return site,proposal


@pytest.mark.parametrize('offset',[(0,0),(17.39,-4.62)])
def test_native_coordinates_override_ai_points_without_changing_source(offset):
    site,raw=source_case(*offset);before=copy.deepcopy(site)
    candidate,report=validate(site,raw)
    assert report['status']=='preview',report
    assert len(report['source_bindings'])==4
    assert candidate['elements'][1]['points'][0]==pytest.approx([1+offset[0],.1+offset[1]])
    assert candidate['elements'][0]['thickness']==pytest.approx(.2)
    assert candidate['elements'][-1]['points']==site['geometry'][-1]['points']
    assert site==before
    assert '原生DWG來源綁定模式' in prompt(site)


def test_unbound_wall_or_furniture_cannot_pass_by_citing_correct_text():
    site,raw=source_case()
    # Keep plausible coordinates to verify failure comes from missing binding.
    correct=validate(site,raw)[0]
    for item in correct['elements']:item['source_binding']=None
    candidate,report=validate(site,correct)
    assert len([e for e in report['errors'] if '原生來源綁定' in e])==4
    assert not report['requires_confirmation']


def test_wrong_jamb_edges_and_invented_indices_do_not_move_opening_to_pass():
    site,raw=source_case();raw=validate(site,raw)[0]
    raw['elements'][1]['source_binding']['refs'][1]=dict(id='jamb-a',edge=0)
    assert any('原生來源綁定' in s for s in validate(site,raw)[1]['errors'])
    raw['elements'][1]['source_binding']['refs'][1]=dict(id='jamb-b',edge=99)
    assert any('索引' in s for s in validate(site,raw)[1]['errors'])


def test_host_checks_physical_wall_band_without_projecting_native_opening():
    site,raw=source_case();candidate,_=validate(site,raw)
    wall,door=candidate['elements'][:2]
    door['points']=[[1,.18],[2,.18]]
    assert host_compatible(door,wall) and door['points']==[[1,.18],[2,.18]]
    door['points']=[[1,.4],[2,.4]]
    assert not host_compatible(door,wall)


def test_reader_configuration_is_explicit_and_invalid_path_never_falls_back(tmp_path,monkeypatch):
    exe=tmp_path/'dwgread.exe';exe.touch()
    monkeypatch.setenv('LIBREDWG_DWGREAD',str(exe))
    assert reader_executable(tmp_path)==exe.resolve()
    exe.unlink()
    with pytest.raises(ValueError,match='路徑不存在'):reader_executable(tmp_path)


def test_long_wall_faces_are_recovered_from_wrong_end_cap_indices():
    site,raw=source_case()
    raw['elements'][0]['source_binding']['refs']=[dict(id='wall-band',edge=1),dict(id='wall-band',edge=3)]
    candidate,report=validate(site,raw)
    assert report['status']=='preview'
    assert candidate['elements'][0]['points']==[[0,.1],[8,.1]]
    assert candidate['elements'][0]['derivation']['automatic_correction']


def test_fragmented_window_runs_are_joined_only_when_original_lines_touch():
    from interior.workbench.studio.source_binding import connected_run
    def line(id,a,b):return dict(id=id,kind='LINE',points=[a,b],closed=False,native_exact=True)
    a=line('a',[0,0],[1,0]);b=line('b',[1,0],[2,0]);far=line('far',[2.2,0],[3,0]);parallel=line('parallel',[1,.02],[2,.02])
    mapping={g['id']:g for g in [a,b,far,parallel]}
    start,end,refs=connected_run(a,mapping)
    assert start==[0,0] and end==[2,0] and refs==['a','b']
    assert a['points']==[[0,0],[1,0]]


def test_portal_host_uses_same_original_jambs_without_moving_opening():
    site,raw=source_case()
    door=raw['elements'][1]
    raw['elements'][0]['source_binding']=dict(method='portal',refs=copy.deepcopy(door['source_binding']['refs']))
    # This isolated host only spans the source opening, so no unrelated window.
    raw['elements']=[raw['elements'][0],door,raw['elements'][3]]
    raw['window_state']='absent'
    result,report=validate(site,raw)
    assert report['status']=='preview',report
    assert result['elements'][0]['points']==result['elements'][1]['points']==[[1,.1],[2,.1]]
    raw['elements'][1]['source_binding']['refs'][1]=dict(id='jamb-a',edge=0)
    assert any('portal' in e for e in validate(site,raw)[1]['errors'])


def test_native_evidence_cache_preserves_originals_and_detects_tampering(tmp_path):
    import ezdxf
    from types import SimpleNamespace
    from interior.workbench.studio.native_intake import attach_native
    from interior.workbench.studio.dwg_inspection import catalog,compare_dxf
    from interior.workbench.studio.service import digest
    from interior.workbench.storage import write_json
    root=tmp_path/'project';root.mkdir();state=tmp_path/'state';state.mkdir()
    native_source=root/'source.dwg';native_source.write_bytes(b'AC1032-synthetic-reader-boundary')
    dxf=root/'source.dxf';doc=ezdxf.new();line=doc.modelspace().add_line((10,20),(210,20));doc.saveas(dxf)
    model=int(doc.modelspace().block_record_handle,16)
    native=dict(created_by='synthetic reader',FILEHEADER=dict(version='AC1032'),HEADER=dict(INSUNITS=1),OBJECTS=[
        *[dict(object='LAYER',handle=[0,2,int(l.dxf.handle,16)],name=l.dxf.name) for l in doc.layers],
        dict(object='BLOCK_HEADER',handle=[0,2,model],name='*Model_Space',entities=[[3,2,int(line.dxf.handle,16),int(line.dxf.handle,16)]]),
        dict(entity='LINE',handle=[0,2,int(line.dxf.handle,16)],layer=[5,2,int(doc.layers.get('0').dxf.handle,16),int(doc.layers.get('0').dxf.handle,16)],start=[10.,20.,0.],end=[210.,20.,0.])])
    reader=tmp_path/'dwgread.exe';reader.write_bytes(b'synthetic-executable')
    source=dict(path=dxf.name,sha256=digest(dxf),original=dict(path=native_source.name,sha256=digest(native_source)))
    studio=SimpleNamespace(root=lambda _:root,store=SimpleNamespace(state_dir=state))
    def fake_read(source_path,output,exe,derived):
        output.mkdir(parents=True);write_json(output/'native.json',native);write_json(output/'inventory.json',catalog(native)[0]);write_json(output/'dxf-comparison.json',compare_dxf(native,derived))
    with patch('interior.workbench.studio.native_intake.reader_executable',return_value=reader),patch('interior.workbench.studio.native_intake.read_native',side_effect=fake_read) as run:
        result=attach_native(studio,'DIFFERENT',source)
        assert attach_native(studio,'DIFFERENT',source)==result and run.call_count==1
        assert native_source.read_bytes()==b'AC1032-synthetic-reader-boundary'
        (root/result['path']/'native.json').write_text('{}')
        with pytest.raises(ValueError,match='證據已變動'):attach_native(studio,'DIFFERENT',source)


def test_complete_window_uses_end_caps_and_revalidation_is_stable():
    from interior.workbench.studio.source_binding import frame_options,resolve
    def line(id,a,b):return dict(id=id,layer='arbitrary',kind='LINE',points=[a,b],closed=False,native_exact=True)
    lines=[line('centre',[0,0],[0,1.8]),line('leaf',[-.03,0],[-.03,.95]),
           line('outside',[-.08,0],[-.08,1.8]),line('bottom',[-.08,0],[0,0]),line('top',[-.08,1.8],[0,1.8])]
    site=dict(geometry=lines,native_dwg=dict(source_sha256='b'*64,frame_options=frame_options(lines)))
    item=dict(id='window',name='window',role='window',points=[[4,4],[5,5]],closed=False,source_ids=['centre'],source_binding=dict(method='pair',refs=[dict(id='centre',edge=0),dict(id='leaf',edge=0)]))
    proposal=dict(elements=[item]);before=copy.deepcopy(site)
    errors,records=resolve(site,proposal)
    assert not errors and __import__('math').dist(*item['points'])==pytest.approx(1.8)
    first=copy.deepcopy(item['points']);resolve(site,proposal)
    assert item['points']==first and site==before
    assert item['source_binding']['refs'][1]['id']=='leaf'  # Preserve requested support; proof stores corrected refs.
    assert records[0]['automatic_correction']


def test_full_width_internal_separator_prevents_merging_adjacent_windows():
    from interior.workbench.studio.source_binding import frame_options,whole_frame
    def line(id,a,b):return dict(id=id,layer='arbitrary',kind='LINE',points=[a,b],closed=False,native_exact=True)
    lines=[line('whole-left',[0,0],[0,3]),line('whole-right',[.1,0],[.1,3]),
           line('lower-leaf',[.03,0],[.03,1.4]),line('bottom',[0,0],[.1,0]),line('top',[0,3],[.1,3]),line('divider',[0,1.5],[.1,1.5])]
    site=dict(geometry=lines,native_dwg=dict(frame_options=frame_options(lines)))
    selected=whole_frame(site,[dict(id='whole-left',edge=0),dict(id='lower-leaf',edge=0)])
    assert selected is None or selected['width']<2


def test_native_adoption_carries_source_proof_and_rejects_changed_graph(system):
    from uuid import uuid4
    from interior.workbench.studio.plan_semantics import PlanSemantics,SemanticRequest,AdoptSemantics
    from interior.workbench.studio.service import digest
    studio,plans,old,_=system
    source=copy.deepcopy(old['source']);original=studio.root('UNRELATED')/'synthetic.dwg';original.write_bytes(b'AC1032-synthetic')
    source['original']=dict(path=original.name,sha256=digest(original))
    packet=plans._create('UNRELATED',source,old['parsed'])
    site,proposal=source_case();site.update(origin=[0,0],factor=1,image_height=None,reference_revision=packet['revision'],confirmed_unit='m')
    class Agents:
        def start(self,kind,model,payload,identifier):self.task=dict(status='passed',candidate=copy.deepcopy(proposal))
        def get(self,identifier):return self.task
    service=PlanSemantics(studio,Agents())
    with patch('interior.workbench.studio.native_intake.attach_native',return_value={}),patch('interior.workbench.studio.plan_semantics.site_packet',side_effect=lambda *args:copy.deepcopy(site)):
        run=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='synthetic-model',operation_id=uuid4().hex))
        adopted=service.adopt('UNRELATED',packet['id'],run['id'],AdoptSemantics(base_revision=packet['revision']))
    assert adopted['check']['status']=='ready'
    active=[f for f in adopted['parsed']['features'] if f['kind']=='SEMANTIC']
    assert len(active)==4 and all(f['source_geometry']['source_sha256']=='a'*64 for f in active)
    assert plans.current('UNRELATED',packet['id'])['revision']==adopted['revision']
    assert original.read_bytes()==b'AC1032-synthetic'

    # A fresh plan/task, then a changed source graph at the adoption boundary.
    packet=plans._create('UNRELATED',source,old['parsed']);site['reference_revision']=packet['revision']
    with patch('interior.workbench.studio.native_intake.attach_native',return_value={}),patch('interior.workbench.studio.plan_semantics.site_packet',side_effect=lambda *args:copy.deepcopy(site)):
        run=service.start('UNRELATED',packet['id'],SemanticRequest(base_revision=packet['revision'],model='synthetic-model',operation_id=uuid4().hex))
        site['geometry'][1]['points'][0][0]+=.2
        with pytest.raises(ValueError,match='來源幾何'):
            service.adopt('UNRELATED',packet['id'],run['id'],AdoptSemantics(base_revision=packet['revision']))
    assert plans.current('UNRELATED',packet['id'])['revision']==packet['revision']
