"""Opt-in real Blender build, source mapping, aperture and render verification."""
import copy
import json
from pathlib import Path
import subprocess
import struct
from unittest.mock import patch
import pytest
from interior.workbench.storage import Store, write_json, read_json
from interior.workbench.jobs import Jobs
from interior.workbench.studio.service import Studio, digest
from interior.workbench.studio.plan_import import PlanIntake, BuildPlan
from interior.workbench.studio.engine import execute, blender_executable
from interior.workbench.studio.handoff import validate_package

REPO=Path(__file__).parents[2]


def test_dxf_to_scene_and_real_render(tmp_path):
    store=Store(tmp_path,tmp_path/'state');store.create_project(dict(id='PLAN',name='DXF example'))
    with patch.object(Jobs,'loop',return_value=None):jobs=Jobs(store)
    try:
        studio=Studio(store,jobs);plans=PlanIntake(studio)
        source=REPO/'examples/dxf-courtyard/courtyard.dxf'
        packet=plans.create('PLAN',source.name,source.read_bytes())
        job=plans.build('PLAN',packet['id'],BuildPlan(plan_revision=packet['revision']))
        request=read_json(store.state_dir/'jobs'/job['id']/'request.json')
        result=execute(request['project'],request['operation'],request['parameters'])
        job.update(status='completed',result=result);jobs.write(job)
        revision=studio.adopt_import('PLAN',job['id'])
        folder=studio.root('PLAN')/job['output']
        assert result['handoff']['status']=='passed'
        assert (folder/'model.blend').is_file() and (folder/'model.glb').is_file()
        assert len(revision['scene']['groups'])==12  # 5 walls + floor + 4 furniture + 2 windows
        check_script=REPO/'tests/fixtures/visualization/check_plan_apertures.py'
        proof=subprocess.run([blender_executable(),'--background','--disable-autoexec','--python-exit-code','1',str(folder/'model.blend'),'--python',str(check_script)],capture_output=True,timeout=90)
        (folder/'apertures.log').write_bytes(proof.stdout+proof.stderr)
        assert proof.returncode==0,proof.stdout.decode(errors='replace')[-3000:]
        scene=copy.deepcopy(revision['scene'])
        from interior.workbench.studio.models import ConceptFurniture
        furniture=ConceptFurniture(id='concept-'+'c'*32,name='Added chair',asset='chair',size=(.5,.5,.85)).model_dump(mode='json')
        scene['concept_furniture']=[furniture]
        scene['objects'] += [dict(id=p['id'],name=p['name'],room_id='interior',material=dict(color='#315575')) for p in furniture['parts']]
        scene['groups'].append(dict(id=furniture['id'],name=furniture['name'],children=[p['id'] for p in furniture['parts']],translation=[3,2,0],deleted=False,method='concept'))
        scene['viewpoints']=[dict(id='living',room_id='interior',name='Living',eye=[2.5,1.8,1.6],shots=[dict(id='north',name='North',yaw=0,pitch=0,lens=28)])]
        saved=studio.save('PLAN',scene,revision['revision'])
        render=jobs.submit_studio('PLAN','render',dict(revision=saved['revision'],quality='preview'),'test-render-plan')
        req=read_json(store.state_dir/'jobs'/render['id']/'request.json')
        output=execute(req['project'],req['operation'],req['parameters'])
        assert len(output['images'])==2
        assert output['quality_check']=='passed'
        assert set(p['id'] for p in furniture['parts']).issubset(output['applied_object_ids'])
        assert output['material_geometry_preserved']
        assert digest(studio.root('PLAN')/packet['source']['path'])==packet['source']['sha256']
        original=(folder/'model.glb').read_bytes()
        (folder/'model.glb').write_bytes(original+b'changed')
        with pytest.raises(ValueError,match='雜湊'):validate_package(folder)
        (folder/'model.glb').write_bytes(original)
        # A different-scale/offset preview with valid IDs and valid GLB bytes must
        # still fail before adoption. Hash integrity alone is not spatial identity.
        size=struct.unpack_from('<I',original,12)[0]
        gltf=json.loads(original[20:20+size])
        node=next(n for n in gltf['nodes'] if 'mesh' in n)
        if 'matrix' in node:node['matrix'][12]+=1
        else:node['translation']=[node.get('translation',[0,0,0])[0]+1,*node.get('translation',[0,0,0])[1:]]
        data=json.dumps(gltf).encode();data+=b' '*((-len(data))%4)
        rest=original[20+size:]
        preview=folder/'mismatched.glb'
        preview.write_bytes(struct.pack('<IIIII',0x46546c67,2,20+len(data)+len(rest),len(data),0x4e4f534a)+data+rest)
        source=dict(native=(folder/'model.blend').relative_to(studio.root('PLAN')).as_posix(),preview=preview.relative_to(studio.root('PLAN')).as_posix())
        with pytest.raises(ValueError,match='尺度或位置'):
            execute(studio.root('PLAN'),'studio.prepare',dict(source=source,job_id='f'*32,output='runs/interior-studio/mismatch'))
    finally:jobs.close()
