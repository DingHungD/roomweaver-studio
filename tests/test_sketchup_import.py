"""Synthetic SKP coverage: scale, instancing, visibility and source binding."""
import hashlib
import io
import json
import math
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

openskp=pytest.importorskip('openskp')
from interior.visualization.sketchup import convert
from interior.workbench.jobs import Jobs
from interior.workbench.server import create_app
from interior.workbench.storage import read_json
from interior.workbench.studio.handoff import read_glb


def synthetic(path,size=100,translation=(0,0,0),shear=False):
    from PIL import Image
    image=io.BytesIO();Image.new('RGB',(4,4),'#885533').save(image,format='PNG')
    builder=openskp.create()
    texture=path.with_suffix('.png');texture.write_bytes(image.getvalue())
    paint=builder.add_texture_material('Wood',str(texture))
    hidden_layer=builder.add_layer('Hidden layer',hidden=True)
    with builder.add_component_definition('Table') as part:
        part.add_face([(0,0,0),(size,0,0),(size,size/2,0),(0,size/2,0)],material=paint)
    builder.add_instance(part,name='Table A',translation=translation,
        matrix3x3=(1,0,0,.3,1,0,0,0,1) if shear else None)
    builder.add_instance(part,name='Table B',translation=(translation[0]+size*2,translation[1],translation[2]),rotation=((0,0,1),math.pi/2))
    builder.add_instance(part,name='Hidden instance',hidden=True)
    builder.add_instance(part,name='Hidden tag',layer=hidden_layer)
    builder.save(str(path))
    return path


@pytest.mark.parametrize('size,translation',[(100,(0,0,0)),(20,(100,-50,12))])
def test_metres_textures_instances_visibility_and_replay(tmp_path,size,translation):
    source=synthetic(tmp_path/'source.skp',size,translation)
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    first=convert(source,tmp_path/'one');second=convert(source,tmp_path/'two')
    doc=read_glb(tmp_path/'one/model.glb')
    nodes=[n for n in doc['nodes'] if 'mesh' in n]
    assert len(nodes)==2 and len({n['mesh'] for n in nodes})==1
    assert len(doc['meshes'])==1 and len(doc['images'])==1
    assert all('Hidden' not in n['name'] for n in doc['nodes'])
    assert len({n['name'] for n in nodes})==2
    assert nodes[0]['extras']['skp_name']=='Table A'
    assert nodes[0]['matrix'][12:15]==pytest.approx([translation[0]*.0254,translation[2]*.0254,-translation[1]*.0254])
    assert nodes[1]['matrix'][:3]==pytest.approx([0,0,-1],abs=1e-7)
    position=doc['accessors'][doc['meshes'][0]['primitives'][0]['attributes']['POSITION']]
    assert position['max'][0]-position['min'][0]==pytest.approx(size*.0254)
    assert first['excluded_hidden']['instances']==2
    assert first['derived']['sha256']==second['derived']['sha256']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    with pytest.raises(FileExistsError):convert(source,tmp_path/'one')


def test_wrong_format_and_changed_source_fail_with_record(tmp_path):
    source=tmp_path/'fake.skp';source.write_bytes(b'not a sketchup file')
    with pytest.raises(ValueError,match='檔頭'):convert(source,tmp_path/'bad')
    assert read_json(tmp_path/'bad/conversion.json')['status']=='failed'
    source=synthetic(tmp_path/'source.skp')
    from interior.visualization.sketchup import write_glb
    def mutate(scene,dest):
        result=write_glb(scene,dest);source.write_bytes(source.read_bytes()+b'changed');return result
    with patch('interior.visualization.sketchup.write_glb',side_effect=mutate):
        with pytest.raises(ValueError,match='變動'):convert(source,tmp_path/'changed')
    assert read_json(tmp_path/'changed/conversion.json')['status']=='failed'


def test_shear_is_preserved_as_parented_trs_without_baking_mesh(tmp_path):
    import numpy as np
    source=synthetic(tmp_path/'shear.skp',shear=True)
    result=convert(source,tmp_path/'result')
    doc=read_glb(tmp_path/'result/model.glb')
    assert result['geometry']['affine_nodes_factored']==1
    wrapper=next(n for n in doc['nodes'] if n.get('extras',{}).get('skp_affine_factor'))
    child=doc['nodes'][wrapper['children'][0]]
    a=np.asarray(wrapper['matrix']).reshape(4,4,order='F')
    b=np.asarray(child['matrix']).reshape(4,4,order='F')
    expected=np.array([[1,0,0,0],[0,1,0,0],[-.3,0,1,0],[0,0,0,1]])
    assert a@b==pytest.approx(expected)
    assert len(doc['meshes'])==1


def test_skp_intake_is_queued_preserved_deduplicated_and_not_adopted(tmp_path):
    source=synthetic(tmp_path/'source.skp');content=source.read_bytes()
    with patch.object(Jobs,'loop',return_value=None):
        app=create_app(tmp_path/'workspace')
        with TestClient(app,base_url='http://127.0.0.1') as client:
            client.headers['X-Workbench-Token']=client.get('/api/session').json()['token']
            def upload(data):return client.post('/api/studio/intake/upload?route=glb&operation_id='+'a'*32,files={'file':('source.skp',data)})
            result=upload(content);assert result.status_code==200,result.text
            first=result.json();assert first['job']['status']=='queued'
            assert upload(content).json()==first
            assert upload(content+b'changed').status_code==409
            identifier=first['project']['id'];studio=app.state.studio
            config=studio.configured_source(identifier)
            assert config['format']=='skp' and config['sha256']==hashlib.sha256(content).hexdigest()
            assert (studio.root(identifier)/config['native']).read_bytes()==content
            assert studio.current(identifier)['revision'] is None
            bad=client.post('/api/studio/intake/upload?route=glb&operation_id='+'b'*32,files={'file':('invalid.skp',b'glTFfake')})
            assert bad.status_code==422
            assert len(studio.store.projects())==1
