"""Real Cycles two-round review; verdicts are synthetic, not live Agent evidence."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import pytest
from interior.workbench.studio import scene_review
from interior.workbench.studio.models import Scene
from interior.workbench.storage import read_json,write_json


def test_native_functional_repair(tmp_path):
    blender=os.environ.get('INTERIOR_BLENDER')
    if not blender:pytest.skip('INTERIOR_BLENDER required')
    root=Path(__file__).resolve().parents[2]
    process=subprocess.run([blender,'--background','--disable-autoexec','--python-exit-code','1','--python',str(root/'tests/fixtures/scene-review/check_functional.py'),'--',str(root/'src/interior/visualization')],capture_output=True,timeout=90)
    (tmp_path/'functional.log').write_bytes(process.stdout+process.stderr)
    assert process.returncode==0,process.stdout[-4000:]
    assert b'FUNCTIONAL_REPAIR_CHECKS_PASSED' in process.stdout


def test_native_preview_repair_and_source_preservation(tmp_path,monkeypatch):
    blender=os.environ.get('INTERIOR_BLENDER')
    if not blender:pytest.skip('INTERIOR_BLENDER required')
    root=Path(__file__).resolve().parents[2]
    build=subprocess.run([blender,'--background','--factory-startup','--python-exit-code','1','--python',str(root/'tests/fixtures/visualization/studio_lighting/build_scene.py'),'--',str(tmp_path)],capture_output=True,timeout=120)
    assert build.returncode==0,build.stderr.decode(errors='replace')
    original=read_json(tmp_path/'scene.json')
    original['groups']=[dict(id=o['id'],name=o['name'],children=[o['id']]) for o in original['objects']]
    original['lighting_setup']=dict(enabled=True,lights=[dict(id='lamp',name='Lamp',position=[0,0,2.8],power=100,size=1)])
    design=Scene.model_validate(original).model_dump(mode='json')
    source=tmp_path/'lit.blend';before=hashlib.sha256(source.read_bytes()).hexdigest();output=tmp_path/'run';output.mkdir()
    calls=[]
    def render(payload,folder):
        write_json(folder/'request.json',payload)
        result=subprocess.run([blender,'--background','--disable-autoexec','--python-exit-code','1','--python',str(root/'src/interior/visualization/studio_blender.py'),'--',str(folder/'request.json')],capture_output=True,timeout=180)
        (folder/'blender.log').write_bytes(result.stdout+result.stderr)
        calls.append(read_json(folder/'result.json'))
        assert result.returncode==0,result.stdout[-4000:]
        return result.returncode
    answers=iter([dict(summary='synthetic correction',issues=[dict(id='light',category='lighting',target_id='lamp',shot_id=None,file='one-front.png',reason='synthetic test',severity='defect',action='light',values={'power':200})]),dict(summary='synthetic pass',issues=[])])
    monkeypatch.setattr(scene_review,'review_images',lambda *args:next(answers))
    result=scene_review.optimize(dict(mode='render',scene=design,source=str(source),revision='b'*32,model_id='a'*32,quality='preview'),output,render)
    assert result['scene_review_status']=='passed' and len(calls)==2
    assert all(len(c['images'])==2 and c['material_geometry_preserved'] for c in calls)
    assert calls[0]['measurements']==calls[1]['measurements']
    for result in calls:
        recorded=next(c for c in result['rendered_cameras'] if c['kind']=='still')
        assert recorded['location']==pytest.approx(design['viewpoints'][0]['shots'][0].get('eye') or design['viewpoints'][0]['eye'])
        assert recorded['lens']==design['viewpoints'][0]['shots'][0]['lens']
        assert recorded['shift_y']==0
    assert calls[0]['images'][1]['sha256']!=calls[1]['images'][1]['sha256']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    assert read_json(output/'scene-review-effective.json')['scene']['groups']==design['groups']
    check=subprocess.run([blender,'--background','--python-exit-code','1','--python',str(root/'tests/fixtures/scene-review/check_native.py'),'--',str(tmp_path),str(root/'src/interior/visualization')],capture_output=True,timeout=90)
    assert check.returncode==0,check.stdout[-4000:]
    assert b'NATIVE_SCENE_REVIEW_CHECKS_PASSED' in check.stdout
