"""Same-origin Studio endpoints; agent outputs remain candidates until adopted."""
import copy
from pathlib import Path
from typing import Literal
from fastapi import UploadFile, File
from fastapi.responses import FileResponse
from pydantic import Field
from ..storage import Conflict, read_json, write_json
from .models import Strict, SaveScene, StartWorkflow, ConfirmWorkflow
from .service import Studio
from ..orchestration.studio_graph import Coordinator
from ..agent_runtime.service import AgentTasks

class ImportInput(Strict):
    operation_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,100}$')

class AdoptImport(Strict):
    job_id: str
    base_revision: str | None = None

class AgentInput(Strict):
    kind: Literal['connection','vision','tool','browser']
    model: str | None = None

class CandidateInput(Strict):
    base_revision: str
    object_id: str
    model: str | None = None
    operation_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,100}$')

class DesignConfirmation(Strict):
    phase: Literal['spaces','materials','viewpoints']
    base_revision: str

class OutputCleanup(Strict):
    base_revision: str = Field(pattern=r'^[a-f0-9]{32}$')
    job_ids: list[str] = Field(min_length=1,max_length=1000)

def install(app, store, jobs):
    studio=Studio(store,jobs)
    agents=AgentTasks(store.state_dir)
    coordinator=Coordinator(studio,agents)
    app.state.studio=studio
    app.state.studio_coordinator=coordinator
    app.state.studio_agents=agents
    jobs.close_callbacks.extend([agents.close,coordinator.close])

    @app.get('/api/studio/projects')
    def projects():
        return [dict(p,configured=(studio.folder(p['id'])/'source.json').exists(),
            revision=studio.current(p['id'])['revision']) for p in store.projects()]

    @app.get('/api/studio/projects/{project_id}/scene')
    def scene(project_id:str):
        return studio.current(project_id)

    @app.put('/api/studio/projects/{project_id}/scene')
    def save_scene(project_id:str,body:SaveScene):
        return studio.save(project_id,body.scene.model_dump(mode='json'),body.base_revision)

    @app.get('/api/studio/projects/{project_id}/models/{model_id}')
    def model(project_id:str,model_id:str):
        return studio.model(project_id,model_id)

    @app.post('/api/studio/projects/{project_id}/import')
    def import_existing(project_id:str,body:ImportInput):
        return studio.import_existing(project_id,body.operation_id)

    @app.post('/api/studio/projects/{project_id}/import/adopt')
    def adopt(project_id:str,body:AdoptImport):
        result=studio.adopt_import(project_id,body.job_id,body.base_revision)
        coordinator.design(project_id)
        return result

    @app.get('/api/studio/projects/{project_id}/design')
    def design(project_id:str):
        # Reading does not create a checkpoint or perform a side effect.
        with jobs.connect() as db:
            rows=db.execute('SELECT id FROM studio_workflows WHERE project_id=? AND operation_id LIKE ?',(project_id,'design-%')).fetchall()
        return [coordinator.get(row[0]) for row in rows]

    @app.post('/api/studio/projects/{project_id}/design/confirm')
    def confirm_design(project_id:str,body:DesignConfirmation):
        return coordinator.advance_design(project_id,body.phase,body.base_revision)

    @app.post('/api/studio/projects/{project_id}/import/upload')
    async def upload(project_id:str,file:UploadFile=File(...)):
        name=file.filename or 'model.glb'
        if Path(name).suffix.lower()!='.glb':
            await file.close()
            raise ValueError('首輪只支援 GLB 與已登記的 Blender 模型。PNG、CAD、SKP 轉換尚未實作，不會套用示範模型。')
        content=await file.read(85_000_001)
        await file.close()
        if len(content)>85_000_000 or content[:4]!=b'glTF':
            raise ValueError('GLB 無效或超過 85 MB')
        item=store.upload(project_id,name,content)
        from uuid import uuid4
        source=dict(native=item['path'],preview=item['path'],rooms=[dict(id='unassigned',name='待確認空間')],viewpoints=[],links=[])
        folder=studio.folder(project_id)
        write_json(folder/'sources'/f'{uuid4().hex}.json',source)
        write_json(folder/'source.json',source)
        return studio.import_existing(project_id,uuid4().hex)

    @app.get('/api/studio/projects/{project_id}/outputs')
    def outputs(project_id:str,include_deleted:bool=False):
        return studio.outputs(project_id,include_deleted)

    @app.post('/api/studio/projects/{project_id}/lighting')
    def lighting(project_id:str,body:StartWorkflow):
        return studio.propose_lighting(project_id,body.base_revision,body.operation_id)

    @app.post('/api/studio/projects/{project_id}/outputs/trash')
    def trash_outputs(project_id:str,body:OutputCleanup):
        return studio.trash_outputs(project_id,body.base_revision,body.job_ids)

    @app.post('/api/studio/projects/{project_id}/outputs/restore')
    def restore_outputs(project_id:str,body:OutputCleanup):
        return studio.trash_outputs(project_id,body.base_revision,body.job_ids,restore=True)

    @app.get('/api/studio/projects/{project_id}/files/{job_id}/{name:path}')
    def artifact(project_id:str,job_id:str,name:str):
        return FileResponse(studio.artifact(project_id,job_id,name))

    @app.get('/api/studio/jobs/{job_id}/lighting-status')
    def lighting_status(job_id:str):
        job=jobs.get(job_id)
        if job['operation']!='studio.render':raise ValueError('非渲染工作')
        root=studio.root(job['project_id'])/job['output']
        attempts=[]
        for folder in sorted(root.glob('lighting-attempt-*')):
            if not folder.is_dir() or not folder.resolve().is_relative_to(root.resolve()):continue
            images=[p.relative_to(root).as_posix() for p in sorted(folder.glob('probe-*.png'))]
            checks=read_json(folder/'quality-checks.json') if (folder/'quality-checks.json').exists() else {}
            review=read_json(folder/'agent-review.json') if (folder/'agent-review.json').exists() else None
            attempts.append(dict(name=folder.name,images=images,status=checks.get('status'),review=review))
        return dict(revision=job['source_revision'],attempts=attempts,lighting_setup=(job.get('result') or {}).get('lighting_setup'))

    @app.get('/api/studio/jobs/{job_id}')
    def job(job_id:str):
        result=jobs.get(job_id)
        if not result['operation'].startswith('studio.'):
            raise ValueError('非 Studio 工作')
        progress=studio.root(result['project_id'])/result['output']/'progress.json'
        if progress.exists():
            try:
                result['progress']=read_json(progress)
            except ValueError:
                pass
        return result

    @app.post('/api/studio/jobs/{job_id}/stop-lighting')
    def stop_lighting(job_id:str):
        job=jobs.get(job_id)
        if job['operation'] not in ('studio.render','studio.lighting'):raise ValueError('非照明工作')
        if job['status']=='queued':return jobs.cancel(job_id)
        if job['status']=='running':
            write_json(studio.root(job['project_id'])/job['output']/'stop-requested.json',dict(requested=True))
        return dict(status=job['status'],message='已要求停止後續調整；目前 Blender 出圖完成後才會停止，不宣稱已立即中止。')

    @app.get('/api/studio/projects/{project_id}/workflows')
    def workflows(project_id:str):
        with jobs.connect() as db:
            rows=db.execute('SELECT id FROM studio_workflows WHERE project_id=?',(project_id,)).fetchall()
        return [coordinator.get(row[0]) for row in rows]

    @app.post('/api/studio/projects/{project_id}/workflows')
    def start(project_id:str,body:StartWorkflow):
        return coordinator.start(project_id,body.base_revision,body.operation_id,body.quality)

    @app.get('/api/studio/workflows/{run_id}')
    def workflow(run_id:str):
        return coordinator.get(run_id)

    @app.post('/api/studio/workflows/{run_id}/resume')
    def resume(run_id:str,body:ConfirmWorkflow):
        return coordinator.resume(run_id,body.base_revision,body.confirmation_id)

    @app.post('/api/studio/workflows/{run_id}/stop')
    def stop(run_id:str):
        return coordinator.stop(run_id)

    @app.get('/api/studio/agent/status')
    def agent_status():
        return agents.status()

    @app.post('/api/studio/agent/tests')
    def agent_test(body:AgentInput):
        return agents.start(body.kind,body.model)

    @app.get('/api/studio/agent/tasks/{task_id}')
    def agent_task(task_id:str):
        with jobs.connect() as db:
            row=db.execute('SELECT id FROM studio_workflows WHERE id=?',(task_id,)).fetchone()
        if row:coordinator.get(task_id)
        return agents.get(task_id)

    @app.get('/api/studio/agent/tasks/{task_id}/images/{name}')
    def agent_image(task_id:str,name:str):
        agents.get(task_id)
        root=(agents.root/task_id).resolve()
        path=(root/name).resolve()
        if path.parent!=root or path.suffix!='.png' or not path.exists():
            raise FileNotFoundError('測試圖片不存在')
        return FileResponse(path)

    @app.post('/api/studio/agent/tasks/{task_id}/stop')
    def agent_stop(task_id:str):
        return agents.stop(task_id)

    @app.post('/api/studio/projects/{project_id}/candidates')
    def candidate(project_id:str,body:CandidateInput):
        return coordinator.candidate(project_id,body.base_revision,body.object_id,body.model,body.operation_id)

    @app.post('/api/studio/projects/{project_id}/candidates/{task_id}/adopt')
    def adopt_candidate(project_id:str,task_id:str,body:ConfirmWorkflow):
        task=agents.get(task_id)
        candidate=task.get('candidate',{})
        if task['status']!='passed' or candidate.get('project_id')!=project_id or body.confirmation_id!=task_id:
            raise ValueError('候選尚未完成或不屬於本案')
        with store.lock:
            current=studio.current(project_id)
            if current['revision']!=body.base_revision or candidate['revision']!=body.base_revision:
                raise Conflict('候選的依據已過期')
            scene=copy.deepcopy(current['scene'])
            obj=next(o for o in scene['objects'] if o['id']==candidate['object_id'])
            obj['material'].update(color=candidate['color'],roughness=candidate['roughness'],candidate_id=task_id)
            return studio.save(project_id,scene,body.base_revision)

    @app.post('/api/studio/backup')
    def backup():
        from .backup import create_backup
        return create_backup(studio,coordinator)
