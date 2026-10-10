"""Real GLB -> persisted design -> Cycles smoke test, using only the synthetic example.

Run from a clone with its environment installed. --workspace must not already exist.
This does not call a model. Results remain in that workspace for inspection.
"""
import argparse
from pathlib import Path
import time
from uuid import uuid4
from fastapi.testclient import TestClient
from PIL import Image
from interior.workbench.storage import Store,read_json,write_json
from interior.workbench.server import create_app

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--workspace',type=Path,required=True)
parser.add_argument('--example',type=Path,default=Path('examples/demo-apartment'))
parser.add_argument('--native',action='store_true',help='Use the verified native/GLB pair and preserve HDRI')
args=parser.parse_args()
root=args.workspace.resolve()
if root.exists():parser.error('Use a NEW workspace; this test never overwrites a previous run.')
repo=Path(__file__).resolve().parents[1]
example=args.example.resolve()
manifest=read_json(example/'manifest.json')
if args.native:
    from interior.workbench.studio.example import register_example
    register_example(root,example,'DEMO')
else:
    Store(root,root/'artifacts/workbench/local').create_project(dict(id='DEMO',name='Synthetic smoke',kind='synthetic'))
app=create_app(root)
with TestClient(app,base_url='http://127.0.0.1') as client:
    headers={'X-Workbench-Token':client.get('/api/session').json()['token']}
    def request(method,path,**kwargs):
        response=client.request(method,'/api/studio'+path,headers=headers,**kwargs)
        response.raise_for_status();return response.json()
    def wait(job):
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            state=request('GET','/jobs/'+job['id'])
            if state['status'] not in ('queued','running'):
                if state['status']!='completed':raise RuntimeError(state.get('error') or state['status'])
                return state
            time.sleep(.5)
        raise TimeoutError('Blender exceeded ten minutes; inspect the preserved workspace.')
    if args.native:
        job=request('POST','/projects/DEMO/import',json={'operation_id':uuid4().hex})
    else:
        with (example/manifest.get('preview','demo-apartment.glb')).open('rb') as stream:
            job=request('POST','/projects/DEMO/import/upload',files={'file':('example.glb',stream,'model/gltf-binary')})
    wait(job);print('GLB imported',flush=True)
    saved=request('POST','/projects/DEMO/import/adopt',json={'job_id':job['id'],'base_revision':None})
    scene=saved['scene'];assert not scene['lighting_setup']['agent_review']
    scene['viewpoints']=[dict(id='view'+str(i),name=p['name'],room_id=scene['rooms'][0]['id'],eye=p['eye'],shots=[dict(id='front',name='Front',yaw=p['yaw'],pitch=p['pitch'],lens=p['lens'])]) for i,p in enumerate(manifest['suggested_viewpoints'],1)]
    scene['links']=[['view1','view2']]
    saved=request('PUT','/projects/DEMO/scene',json={'base_revision':saved['revision'],'scene':scene})
    for phase in ['spaces','materials','viewpoints']:
        request('POST','/projects/DEMO/design/confirm',json={'base_revision':saved['revision'],'phase':phase})
    run=request('POST','/projects/DEMO/workflows',json={'base_revision':saved['revision'],'operation_id':uuid4().hex,'quality':'preview'})
    run=request('POST','/workflows/'+run['run_id']+'/resume',json={'base_revision':saved['revision'],'confirmation_id':run['confirmation_id']})
    print('Rendering two panoramas and two stills',flush=True)
    result=wait({'id':run['job_id']})
    assert result['result']['quality_check']=='passed'
    images=result['result']['images'];assert len(images)==4
    for image in images:
        with Image.open(root/'projects/demo'/result['output']/image['file']) as picture:
            assert picture.size==((1024,512) if image['kind']=='panorama' else (640,480))
    workflow=request('GET','/workflows/'+run['run_id']);assert workflow['status']=='completed'
    write_json(root/'smoke-report.json',dict(status='passed',render_job=run['job_id'],image_count=len(images),agent_called=False,revision=saved['revision']))
    print('PASS: four actual images; no cloud model calls. '+str(root/'smoke-report.json'),flush=True)
