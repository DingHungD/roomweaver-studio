"""Synthetic Studio regression: conflicts, replay, identity and recovery boundaries."""
import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from interior.workbench.storage import Store, Conflict, write_json, read_json
from interior.workbench.jobs import Jobs
from interior.workbench.studio.service import Studio
from interior.workbench.studio.models import Scene
from interior.workbench.orchestration.studio_graph import Coordinator
from interior.workbench.studio.backup import create_backup,restore_backup

MODEL='a'*32

def synthetic_scene():
    return dict(model_id=MODEL,rooms=[dict(id='living',name='Living')],
        objects=[dict(id='wall',name='Wall',room_id='living',material={}),dict(id='sofa',name='Sofa',room_id=None,material={})],
        viewpoints=[dict(id=p,room_id='living',name=p,eye=[i,0,1.5],shots=[dict(id='front',name='Front',yaw=0)]) for i,p in enumerate(('one','two','five'))],
        links=[['one','two'],['one','five']])

class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        write_json(self.root/'projects/synthetic/project.json',dict(id='TEST',name='Synthetic',kind='synthetic',entries={}))
        self.store=Store(self.root,self.root/'state')
        self.loop=patch.object(Jobs,'loop',return_value=None);self.loop.start()
        self.jobs=Jobs(self.store)
        self.studio=Studio(self.store,self.jobs)
        self.graph=Coordinator(self.studio)
        write_json(self.studio.root('TEST')/'runs/interior-studio'/MODEL/'model.json',dict(objects=[dict(id='wall',name='Wall'),dict(id='sofa',name='Sofa')]))

    def tearDown(self):
        self.graph.close();self.jobs.close();self.loop.stop();self.temp.cleanup()

    def save(self):
        return self.studio.save('TEST',synthetic_scene(),None)

    def test_empty_before_import_and_revision_conflict(self):
        self.assertIsNone(self.studio.current('TEST')['scene'])
        initial=self.save()
        changed=copy.deepcopy(initial['scene']);changed['objects'][0]['name']='Renamed wall'
        second=self.studio.save('TEST',changed,initial['revision'])
        self.assertNotEqual(initial['revision'],second['revision'])
        self.assertEqual(self.studio.revision('TEST',initial['revision'])['scene']['objects'][0]['name'],'Wall')
        self.assertEqual(second['scene']['objects'][0]['id'],'wall')
        with self.assertRaises(Conflict):self.studio.save('TEST',changed,initial['revision'])

    def test_lighting_revision_binding_and_deduplicated_proposal(self):
        from interior.workbench.studio.models import LightingSetup,StudioLight
        first=self.save()
        proposal=self.studio.propose_lighting('TEST',first['revision'],'lighting-proposal')
        again=self.studio.propose_lighting('TEST',first['revision'],'lighting-proposal')
        self.assertEqual(proposal['id'],again['id'])
        scene=copy.deepcopy(first['scene'])
        scene['lighting_setup']=LightingSetup(enabled=True,lights=[StudioLight(id='lamp',name='Lamp',position=(0,0,2),locked=True,group_id=scene['groups'][0]['id'])]).model_dump(mode='json')
        second=self.studio.save('TEST',scene,first['revision'])
        self.assertTrue(self.studio.current('TEST')['scene']['lighting_setup']['lights'][0]['locked'])
        with self.assertRaises(Conflict):self.studio.propose_lighting('TEST',first['revision'],'lighting-old-revision')
        scene['lighting_setup']['lights'][0]['group_id']='missing'
        with self.assertRaises(ValueError):self.studio.save('TEST',scene,second['revision'])

    def test_model_membership_and_room_references(self):
        bad=synthetic_scene();bad['objects'][0]['id']='wrong'
        with self.assertRaises(ValueError):self.studio.save('TEST',bad,None)
        bad=synthetic_scene();bad['objects'][0]['room_id']='missing'
        with self.assertRaises(ValueError):Scene.model_validate(bad)

    def test_bidirectional_branches_and_deleted_point(self):
        data=synthetic_scene();data['links'].append(['two','one'])
        scene=Scene.model_validate(data)
        self.assertEqual(len(scene.links),2)
        data['viewpoints']=data['viewpoints'][:2]
        with self.assertRaises(ValueError):Scene.model_validate(data)
        data['links']=[['one','two']]
        self.assertEqual(len(Scene.model_validate(data).links),1)

    def test_assembly_moves_deletion_and_child_material_survive_reopen(self):
        first=self.save();data=copy.deepcopy(first['scene'])
        group=next(g for g in data['groups'] if 'sofa' in g['children'])
        group.update(name='Whole sofa',translation=[.4,-.2,.1],deleted=True)
        data['objects'][1]['material']['color']='#123456'
        saved=self.studio.save('TEST',data,first['revision'])
        reopened=Studio(self.store,self.jobs).current('TEST')
        self.assertEqual(reopened['scene']['groups'],saved['scene']['groups'])
        self.assertEqual(reopened['scene']['objects'][0]['material']['color'],None)
        self.assertEqual(reopened['scene']['objects'][1]['material']['color'],'#123456')
        self.assertFalse(self.studio.revision('TEST',first['revision'])['scene']['groups'][1]['deleted'])
        bad=copy.deepcopy(data);bad['groups'][0]['children'].append('sofa')
        with self.assertRaises(ValueError):Scene.model_validate(bad)
        bad=copy.deepcopy(data);bad['groups'][0]['children']=['missing']
        with self.assertRaises(ValueError):Scene.model_validate(bad)

    def test_assembly_identity_separates_chairs_and_preserves_raw_mesh_ids(self):
        import struct
        from interior.workbench.studio.grouping import assembly_groups
        import json
        path=self.root/'two-chairs.glb'
        nodes=[dict(name=name,mesh=i,extras=dict(studio_id=str(i),source_id=group))
               for i,(name,group) in enumerate([('Chair1__leg','chair-one'),('Chair1__seat','chair-one'),('Chair2__leg','chair-two'),('Chair2__seat','chair-two')])]
        payload=json.dumps(dict(nodes=nodes)).encode();payload+=b' '*((-len(payload))%4)
        path.write_bytes(struct.pack('<III',0x46546c67,2,20+len(payload))+struct.pack('<II',len(payload),0x4e4f534a)+payload)
        objects=[dict(id=str(i),name=n['name']) for i,n in enumerate(nodes)]
        groups=assembly_groups(objects,path)
        self.assertEqual([g['children'] for g in groups],[['0','1'],['2','3']])
        objects[0]['name']='Renamed chair leg'
        self.assertEqual(assembly_groups(objects,path),groups)
        plain=assembly_groups([dict(id='a',name='nearby'),dict(id='b',name='nearby')],self.root/'absent.glb')
        self.assertEqual(len(plain),2)  # Proximity or identical display names alone are insufficient.

    def test_duplicate_submit_has_one_effect_and_conflicting_key_rejected(self):
        revision=self.save()['revision']
        params=dict(revision=revision,quality='preview')
        a=self.jobs.submit_studio('TEST','render',params,'same-operation')
        b=self.jobs.submit_studio('TEST','render',params,'same-operation')
        self.assertEqual(a['id'],b['id']);self.assertEqual(len(self.jobs.list()),1)
        with self.assertRaises(Conflict):self.jobs.submit_studio('TEST','render',dict(params,quality='final'),'same-operation')

    def test_stale_confirmation_rejected(self):
        first=self.save()
        run=self.graph.start('TEST',first['revision'],'stale-confirmation','preview')
        self.studio.save('TEST',first['scene'],first['revision'])
        with self.assertRaises(Conflict):self.graph.resume(run['run_id'],run['revision'],run['confirmation_id'])
        self.assertEqual(len(self.jobs.list()),0)

    def test_reopen_before_confirmation_and_repeated_confirm(self):
        first=self.save()
        run=self.graph.start('TEST',first['revision'],'restart-confirmation','preview')
        self.graph.close();self.graph=Coordinator(self.studio)
        resumed=self.graph.resume(run['run_id'],run['revision'],run['confirmation_id'])
        repeated=self.graph.resume(run['run_id'],run['revision'],run['confirmation_id'])
        self.assertEqual(resumed['job_id'],repeated['job_id'])
        self.graph.close();self.graph=Coordinator(self.studio)
        self.assertEqual(self.graph.get(run['run_id'])['job_id'],resumed['job_id'])
        self.assertEqual(len(self.jobs.list()),1)

    def test_result_reconciliation_and_stale_outputs(self):
        revision=self.save()
        job=self.jobs.submit_studio('TEST','render',dict(revision=revision['revision'],quality='preview'),'result-recovery')
        job.update(status='running');self.jobs.write(job)
        write_json(self.store.state_dir/'jobs'/job['id']/'result.json',dict(status='completed',result=dict(images=[dict(file='one.png')]),error=None))
        replacement=Jobs(self.store)
        try:self.assertEqual(replacement.get(job['id'])['status'],'completed')
        finally:replacement.close()
        self.studio.save('TEST',revision['scene'],revision['revision'])
        self.assertTrue(self.studio.outputs('TEST')[0]['stale'])

    def test_stop_queued_but_not_running(self):
        r=self.save();run=self.graph.start('TEST',r['revision'],'stop-render-task','preview')
        run=self.graph.resume(run['run_id'],r['revision'],run['confirmation_id'])
        job=self.jobs.get(run['job_id']);job['status']='running';self.jobs.write(job)
        with self.assertRaises(ValueError):self.graph.stop(run['run_id'])
        job['status']='queued';self.jobs.write(job)
        self.assertEqual(self.graph.stop(run['run_id'])['status'],'stopped')
        self.assertEqual(self.jobs.get(job['id'])['status'],'cancelled')

    def test_backup_reopen_has_no_new_job(self):
        r=self.save();run=self.graph.start('TEST',r['revision'],'backup-confirmation','preview')
        result=create_backup(self.studio,self.graph)
        root=Path(result['path'])
        self.assertEqual(read_json(root/'manifest.json')['projects'][0]['revision'],r['revision'])
        with sqlite3.connect(root/'jobs.sqlite3') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
        db.close()
        self.assertEqual(self.graph.get(run['run_id'])['status'],'awaiting_confirmation')
        self.assertEqual(len(self.jobs.list()),0)

    def test_artifact_traversal_rejected(self):
        r=self.save();job=self.jobs.submit_studio('TEST','render',dict(revision=r['revision'],quality='preview'),'path-traversal-test')
        with self.assertRaises(PermissionError):self.studio.artifact('TEST',job['id'],'../../../source.png')

    def test_old_outputs_trash_restore_and_restart_preserve_files(self):
        first=self.save()
        old=self.jobs.submit_studio('TEST','render',dict(revision=first['revision'],quality='preview'),'trash-old-output')
        old.update(status='completed',result=dict(images=[dict(file='one.png',thumbnail='thumb-one.png')]))
        self.jobs.write(old)
        path=self.studio.root('TEST')/old['output']/'one.png';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'original pixels')
        second=self.studio.save('TEST',first['scene'],first['revision'])
        latest=self.jobs.submit_studio('TEST','render',dict(revision=second['revision'],quality='preview'),'trash-new-output')
        latest.update(status='completed',result=dict(images=[dict(file='new.png')]))
        self.jobs.write(latest)
        self.studio.trash_outputs('TEST',second['revision'],[old['id']])
        self.studio.trash_outputs('TEST',second['revision'],[old['id']])
        reopened=Studio(self.store,self.jobs)
        self.assertEqual([o['job_id'] for o in reopened.outputs('TEST')],[latest['id']])
        self.assertEqual(sum(o['deleted'] for o in reopened.outputs('TEST',True)),1)
        self.assertEqual(path.read_bytes(),b'original pixels')
        self.assertEqual(self.jobs.get(old['id'])['result'],old['result'])
        self.studio.trash_outputs('TEST',second['revision'],[old['id']],restore=True)
        self.assertEqual(len(self.studio.outputs('TEST')),2)

    def test_cleanup_rejects_stale_revision_current_results_and_non_render_atomically(self):
        first=self.save()
        old=self.jobs.submit_studio('TEST','render',dict(revision=first['revision'],quality='preview'),'cleanup-old')
        old.update(status='completed',result=dict(images=[dict(file='old.png')]))
        self.jobs.write(old)
        second=self.studio.save('TEST',first['scene'],first['revision'])
        current=self.jobs.submit_studio('TEST','render',dict(revision=second['revision'],quality='preview'),'cleanup-current')
        current.update(status='completed',result=dict(images=[dict(file='new.png')]))
        self.jobs.write(current)
        with self.assertRaises(Conflict):self.studio.trash_outputs('TEST',first['revision'],[old['id']])
        with self.assertRaises(ValueError):self.studio.trash_outputs('TEST',second['revision'],[old['id'],current['id']])
        self.assertEqual(len(self.studio.outputs('TEST')),2)
        old['status']='running';self.jobs.write(old)
        with self.assertRaises(ValueError):self.studio.trash_outputs('TEST',second['revision'],[old['id']])
        old.update(status='completed',operation='studio.prepare');self.jobs.write(old)
        with self.assertRaises(ValueError):self.studio.trash_outputs('TEST',second['revision'],[old['id']])
        old.update(operation='studio.render',project_id='OTHER');self.jobs.write(old)
        with self.assertRaises(ValueError):self.studio.trash_outputs('TEST',second['revision'],[old['id']])

    def test_cleanup_http_requires_session_and_can_restore(self):
        from fastapi.testclient import TestClient
        from interior.workbench.server import create_app
        first=self.save()
        app=create_app(self.root,self.root/'cleanup-http-state')
        with TestClient(app,base_url='http://127.0.0.1') as client:
            studio=app.state.studio
            old=studio.jobs.submit_studio('TEST','render',dict(revision=first['revision'],quality='preview'),'http-cleanup')
            old.update(status='completed',result=dict(images=[dict(file='old.png')]))
            studio.jobs.write(old)
            second=studio.save('TEST',first['scene'],first['revision'])
            endpoint='/api/studio/projects/TEST/outputs'
            body=dict(base_revision=second['revision'],job_ids=[old['id']])
            self.assertEqual(client.post(endpoint+'/trash',json=body).status_code,403)
            headers={'X-Workbench-Token':client.get('/api/session').json()['token']}
            self.assertEqual(client.post(endpoint+'/trash',json=body,headers=headers).status_code,200)
            self.assertEqual(client.get(endpoint).json(),[])
            self.assertTrue(client.get(endpoint+'?include_deleted=true').json()[0]['deleted'])
            self.assertEqual(client.post(endpoint+'/restore',json=body,headers=headers).status_code,200)
            self.assertEqual(len(client.get(endpoint).json()),1)

    def test_design_gates_follow_revisions_and_resume_after_restart(self):
        first=self.save()
        run=self.graph.design('TEST')
        self.assertEqual(run['status'],'awaiting_spaces')
        with self.assertRaises(Conflict):self.graph.advance_design('TEST','materials',first['revision'])
        second=self.studio.save('TEST',first['scene'],first['revision'])
        run=self.graph.advance_design('TEST','spaces',second['revision'])
        self.assertEqual(run['revision'],second['revision'])
        self.graph.close();self.graph=Coordinator(self.studio)
        self.assertEqual(self.graph.get(run['run_id'])['status'],'awaiting_materials')
        self.graph.advance_design('TEST','materials',second['revision'])
        final=self.graph.advance_design('TEST','viewpoints',second['revision'])
        self.assertEqual(final['status'],'ready')
        self.assertEqual(len(self.jobs.list()),0)

    def test_reserved_panorama_direction_rejected(self):
        scene=synthetic_scene();scene['viewpoints'][0]['shots'][0]['id']='panorama'
        with self.assertRaises(ValueError):Scene.model_validate(scene)

    def test_known_missing_lighting_blocks_workflow_before_queue(self):
        r=self.save()
        path=self.studio.root('TEST')/'runs/interior-studio'/MODEL/'model.json'
        model=read_json(path);model['render_readiness']=dict(status='blocked',issues=['缺少照明'])
        write_json(path,model)
        with self.assertRaisesRegex(ValueError,'缺少照明'):
            self.graph.start('TEST',r['revision'],'missing-lighting','preview')
        self.assertEqual(self.jobs.list(),[])

    def test_http_merged_confirmation_saves_points_without_submitting_render(self):
        from fastapi.testclient import TestClient
        from interior.workbench.server import create_app
        initial=self.save()
        app=create_app(self.root,self.root/'merged-http-state')
        with TestClient(app,base_url='http://127.0.0.1') as client:
            headers={'X-Workbench-Token':client.get('/api/session').json()['token']}
            scene=copy.deepcopy(initial['scene'])
            scene['viewpoints'][0]['eye']=[3.25,-1.75,1.6]
            scene['viewpoints'][0]['shots'][0]['yaw']=270
            saved=client.put('/api/studio/projects/TEST/scene',headers=headers,
                json=dict(base_revision=initial['revision'],scene=scene))
            self.assertEqual(saved.status_code,200,saved.text)
            revision=saved.json()['revision']
            for phase in ('spaces','materials','viewpoints'):
                result=client.post('/api/studio/projects/TEST/design/confirm',headers=headers,
                    json=dict(phase=phase,base_revision=revision))
                self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(result.json()['status'],'ready')
            self.assertEqual(client.get('/api/studio/projects/TEST/scene').json()['scene']['viewpoints'][0]['eye'],[3.25,-1.75,1.6])
            self.assertTrue(any(r['revision']==revision and r['status']=='ready'
                for r in client.get('/api/studio/projects/TEST/design').json()))
            self.assertEqual(app.state.jobs.list(),[])
            scene['viewpoints'][0]['eye'][0]=4.5
            changed=client.put('/api/studio/projects/TEST/scene',headers=headers,
                json=dict(base_revision=revision,scene=scene)).json()
            self.assertNotEqual(changed['revision'],revision)
            self.assertEqual(client.post('/api/studio/projects/TEST/design/confirm',headers=headers,
                json=dict(phase='viewpoints',base_revision=revision)).status_code,409)
            self.assertEqual(app.state.jobs.list(),[])

    def test_reference_rejects_local_address_before_fetch(self):
        from interior.workbench.agent_runtime.reference import validate_public_url
        with self.assertRaises(ValueError):validate_public_url('http://127.0.0.1/private')
        with self.assertRaises(ValueError):validate_public_url('file:///C:/private')

    def test_backup_restore_reconciles_without_resubmitting(self):
        first=self.save()
        run=self.graph.start('TEST',first['revision'],'restore-waiting-flow','preview')
        backup=create_backup(self.studio,self.graph)
        changed=self.studio.save('TEST',first['scene'],first['revision'])
        self.graph.close()
        restored=restore_backup(self.store,backup['path'])
        self.graph=Coordinator(self.studio)
        self.assertEqual(restored['automatic_jobs_submitted'],0)
        self.assertEqual(self.studio.current('TEST')['revision'],first['revision'])
        self.assertTrue((self.studio.folder('TEST')/'revisions'/f"{changed['revision']}.json").exists())
        self.assertEqual(self.graph.get(run['run_id'])['status'],'awaiting_confirmation')
        self.assertEqual(len(self.jobs.list()),0)

    def test_lease_rejects_concurrent_service_and_restore(self):
        from interior.workbench.studio.lease import Lease
        lease=Lease(self.store.state_dir)
        try:
            with self.assertRaises(ValueError):Lease(self.store.state_dir)
        finally:lease.close()

    def test_replay_after_effect_before_checkpoint_does_not_duplicate_render(self):
        first=self.save();run=self.graph.start('TEST',first['revision'],'effect-before-checkpoint','preview')
        original=self.jobs.submit_studio
        def interrupted(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('simulated failure after queue commit')
        with patch.object(self.jobs,'submit_studio',side_effect=interrupted):
            with self.assertRaises(RuntimeError):self.graph.resume(run['run_id'],run['revision'],run['confirmation_id'])
        self.graph.close();self.graph=Coordinator(self.studio)
        recovered=self.graph.resume(run['run_id'],run['revision'],run['confirmation_id'])
        self.assertEqual(len(self.jobs.list()),1)
        self.assertEqual(recovered['job_id'],self.jobs.list()[0]['id'])

    def test_http_material_adoption_is_targeted_and_version_bound(self):
        from fastapi.testclient import TestClient
        from interior.workbench.server import create_app
        r=self.save();task_id='b'*32
        app=create_app(self.root,self.root/'http-state')
        with TestClient(app,base_url='http://127.0.0.1') as client:
            headers={'X-Workbench-Token':client.get('/api/session').json()['token']}
            write_json(app.state.studio_agents.root/task_id/'task.json',dict(id=task_id,status='passed',candidate=dict(
                project_id='TEST',revision=r['revision'],object_id='wall',color='#aabbcc',roughness=.8)))
            body=dict(base_revision=r['revision'],confirmation_id=task_id)
            response=client.post('/api/studio/projects/TEST/candidates/'+task_id+'/adopt',json=body,headers=headers)
            self.assertEqual(response.status_code,200,response.text)
            result=response.json()['scene']
            self.assertEqual(result['objects'][0]['material']['color'],'#aabbcc')
            self.assertEqual(result['objects'][1],r['scene']['objects'][1])
            self.assertEqual(client.post('/api/studio/projects/TEST/candidates/'+task_id+'/adopt',json=body,headers=headers).status_code,409)
            self.assertEqual(client.post('/api/studio/projects/TEST/import/upload',files={'file':('broken.png',b'not a model','image/png')},headers=headers).status_code,422)
            self.assertEqual(client.get('/api/studio/projects/TEST/scene').json()['scene'],result)

    def test_disk_full_fails_before_blender(self):
        from interior.workbench.studio.engine import execute
        from collections import namedtuple
        usage=namedtuple('Usage','total used free')(100,99,1)
        with patch('shutil.disk_usage',return_value=usage),patch('subprocess.run') as run:
            with self.assertRaisesRegex(ValueError,'6 GB'):
                execute(self.studio.root('TEST'),'studio.prepare',dict(output='runs/interior-studio/'+MODEL,job_id=MODEL,source={}))
            run.assert_not_called()

    def test_agent_task_checkpoint_replay_reuses_task(self):
        class FakeAgent:
            def __init__(self):self.tasks={};self.calls=0
            def start(self,kind,model,payload,identifier):
                self.calls+=1
                self.tasks.setdefault(identifier,dict(id=identifier,status='running'))
                return self.tasks[identifier]
            def get(self,identifier):return self.tasks[identifier]
        agent=FakeAgent();self.graph.close();self.graph=Coordinator(self.studio,agent)
        r=self.save()
        task=self.graph.candidate('TEST',r['revision'],'wall',None,'candidate-operation')
        again=self.graph.candidate('TEST',r['revision'],'wall',None,'candidate-operation')
        self.assertEqual(task['id'],again['id']);self.assertEqual(agent.calls,1)
        self.graph.close();self.graph=Coordinator(self.studio,agent)
        agent.tasks[task['id']]['status']='passed'
        self.assertEqual(self.graph.get(task['id'])['status'],'completed')
        self.assertEqual(agent.calls,1)

    def test_restart_recognizes_live_external_worker(self):
        r=self.save()
        job=self.jobs.submit_studio('TEST','render',dict(revision=r['revision'],quality='preview'),'external-recovery')
        job.update(status='interrupted',worker_process=dict(pid=123,identity='test'))
        self.jobs.write(job)
        with patch.object(Jobs,'external_alive',return_value=True):
            other=Jobs(self.store)
            try:
                recovered=other.get(job['id'])
                self.assertEqual(recovered['status'],'running')
                self.assertTrue(recovered['external_running'])
                self.assertEqual(len(other.list()),1)
            finally:other.close()

    def test_process_identity_does_not_accept_reused_pid(self):
        import os
        from interior.workbench.studio.processes import identity,alive
        current=identity(os.getpid())
        self.assertTrue(current)
        self.assertTrue(alive(dict(pid=os.getpid(),identity=current)))
        self.assertFalse(alive(dict(pid=os.getpid(),identity=current+'not-same-process')))

if __name__=='__main__':unittest.main()
