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

class AssetReview(Strict):
    base_revision: str = Field(pattern=r'^[a-f0-9]{32}$')
    keep_original: list[str] = Field(default_factory=list,max_length=100)

def install(app, store, jobs):
    studio=Studio(store,jobs)
    agents=AgentTasks(store.state_dir)
    coordinator=Coordinator(studio,agents)
    app.state.studio=studio
    app.state.studio_coordinator=coordinator
    app.state.studio_agents=agents
    jobs.close_callbacks.extend([agents.close,coordinator.close])
    from .plan_import import PlanIntake, SavePlan, BuildPlan, RectifyPlan
    plans=PlanIntake(studio)
    from .image_evidence import EvidenceRefinement, FeedbackInput
    from .image_plan import ImageIntake, RecognizeImage
    images=ImageIntake(studio,agents)
    from .layout_design import LayoutDesign, LayoutRequest, AdoptLayout, LayoutBrief, ReviseLayout, LayoutAnswers
    layouts=LayoutDesign(studio,agents)
    from .asset_matching import AssetMatching, MatchRequest, SelectAsset, LinkAsset
    assets=AssetMatching(studio,agents)
    from .asset_batch import AssetBatch, BatchRequest, inventory
    batches=AssetBatch(assets)
    from .staging import Staging, StageRequest, StageApply, StageRetry
    staging=Staging(studio,batches)

    @app.post('/api/studio/projects/{project_id}/staging')
    def stage_preview(project_id:str,body:StageRequest):return staging.preview(project_id,body)

    @app.get('/api/studio/projects/{project_id}/staging/current')
    def stage_current(project_id:str,kind:Literal['decor','lighting']):return staging.current(project_id,kind)

    @app.post('/api/studio/projects/{project_id}/staging/{identifier}/apply')
    def stage_apply(project_id:str,identifier:str,body:StageApply):return staging.apply(project_id,identifier,body)

    @app.post('/api/studio/projects/{project_id}/staging/{identifier}/retry')
    def stage_retry(project_id:str,identifier:str,body:StageRetry):return staging.retry(project_id,identifier,body)
    jobs.close_callbacks.append(batches.automation.close)
    from .asset_storage import clean_replacements, source_history

    @app.post('/api/studio/projects/{project_id}/asset-storage/cleanup')
    def asset_cleanup(project_id:str,body:ConfirmWorkflow):
        latest=batches.current(project_id)
        if latest and latest['settings'].get('auto_apply') and not latest.get('confirmed'):
            raise Conflict('請先在一鍵配置中確認所有家具，再清理未使用模型')
        return clean_replacements(studio,project_id,body.base_revision)

    @app.get('/api/studio/projects/{project_id}/asset-history')
    def asset_history(project_id:str,group_id:str):return source_history(studio,project_id,group_id)

    @app.get('/api/studio/projects/{project_id}/asset-batches/inventory')
    def asset_inventory(project_id:str):return inventory(studio.current(project_id)['scene'])

    @app.post('/api/studio/projects/{project_id}/asset-style-images')
    async def asset_style_image(project_id:str,file:UploadFile=File(...)):
        return batches.upload(project_id,await file.read(5*1024**2+1))

    @app.get('/api/studio/projects/{project_id}/asset-style-images/{identifier}')
    def get_asset_style_image(project_id:str,identifier:str):return FileResponse(batches.image(project_id,identifier),media_type='image/jpeg')

    @app.get('/api/studio/projects/{project_id}/asset-batches/current')
    def current_asset_batch(project_id:str):return batches.current(project_id)

    @app.post('/api/studio/projects/{project_id}/asset-batches')
    def start_asset_batch(project_id:str,body:BatchRequest):return batches.start(project_id,body)

    @app.get('/api/studio/projects/{project_id}/asset-batches/{identifier}')
    def get_asset_batch(project_id:str,identifier:str):return batches.get(project_id,identifier)

    @app.post('/api/studio/projects/{project_id}/asset-batches/{identifier}/stop')
    def stop_asset_batch(project_id:str,identifier:str):return batches.automation.stop(project_id,identifier)

    @app.post('/api/studio/projects/{project_id}/asset-batches/{identifier}/resume')
    def resume_asset_batch(project_id:str,identifier:str,body:ConfirmWorkflow):
        batches.get(project_id,identifier)
        batches.automation.start(project_id,identifier,body.base_revision)
        return batches.get(project_id,identifier)

    @app.post('/api/studio/projects/{project_id}/asset-batches/{identifier}/confirm')
    def confirm_asset_batch(project_id:str,identifier:str,body:AssetReview):
        return batches.automation.confirm(project_id,identifier,body.base_revision,body.keep_original)

    @app.get('/api/studio/projects/{project_id}/asset-matches/current')
    def current_assets(project_id:str,group_id:str):return assets.current(project_id,group_id)

    @app.post('/api/studio/projects/{project_id}/asset-matches')
    def match_assets(project_id:str,body:MatchRequest):return assets.start(project_id,body)

    @app.post('/api/studio/projects/{project_id}/asset-links')
    def link_asset(project_id:str,body:LinkAsset):return assets.from_link(project_id,body)

    @app.get('/api/studio/projects/{project_id}/asset-matches/{task_id}')
    def get_assets(project_id:str,task_id:str):return assets.get(project_id,task_id)

    @app.post('/api/studio/projects/{project_id}/asset-matches/{task_id}/reference')
    def reference_asset(project_id:str,task_id:str,body:SelectAsset):return assets.reference(project_id,task_id,body)

    @app.post('/api/studio/projects/{project_id}/asset-matches/{task_id}/replace')
    def replace_asset(project_id:str,task_id:str,body:SelectAsset):return assets.replace(project_id,task_id,body)

    @app.post('/api/studio/projects/{project_id}/asset-replacements/{job_id}/adopt')
    def adopt_asset(project_id:str,job_id:str,body:ConfirmWorkflow):
        if body.confirmation_id!=job_id:raise ValueError('替換確認識別碼不符')
        return assets.adopt(project_id,job_id,body.base_revision)

    @app.post('/api/studio/projects/{project_id}/asset-replacements/restore')
    def restore_asset(project_id:str,body:ConfirmWorkflow):return assets.restore(project_id,body.base_revision)
    from .models import ConceptFurniture

    @app.get('/api/studio/concept-furniture')
    def concept_catalog():
        from ...visualization.concept_geometry import CATALOG
        return CATALOG

    @app.post('/api/studio/concept-furniture')
    def concept_preview(body:ConceptFurniture):return body.model_dump(mode='json')

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/layout/brief')
    def layout_brief(project_id:str,plan_id:str):return layouts.brief(project_id,plan_id)

    @app.put('/api/studio/projects/{project_id}/plans/{plan_id}/layout/brief')
    def save_layout_brief(project_id:str,plan_id:str,body:LayoutBrief):return layouts.save_brief(project_id,plan_id,body)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/layout/current')
    def current_layout(project_id:str,plan_id:str):
        return layouts.current(project_id,plan_id)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/layout')
    def start_layout(project_id:str,plan_id:str,body:LayoutRequest):
        return layouts.start(project_id,plan_id,body)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/layout/{identifier}')
    def get_layout(project_id:str,plan_id:str,identifier:str):
        return layouts.get(project_id,plan_id,identifier)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/layout/{identifier}/adopt')
    def adopt_layout(project_id:str,plan_id:str,identifier:str,body:AdoptLayout):
        return layouts.adopt(project_id,plan_id,identifier,body)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/layout/{identifier}/revise')
    def revise_layout(project_id:str,plan_id:str,identifier:str,body:ReviseLayout):
        return layouts.revise(project_id,plan_id,identifier,body)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/layout/{identifier}/answers')
    def layout_answers(project_id:str,plan_id:str,identifier:str):
        return layouts.answers(project_id,plan_id,identifier)

    @app.put('/api/studio/projects/{project_id}/plans/{plan_id}/layout/{identifier}/answers')
    def save_layout_answers(project_id:str,plan_id:str,identifier:str,body:LayoutAnswers):
        return layouts.save_answers(project_id,plan_id,identifier,body)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/layout/{identifier}/stop')
    def stop_layout(project_id:str,plan_id:str,identifier:str):
        layouts.get(project_id,plan_id,identifier)
        agents.stop(identifier)
        return layouts.get(project_id,plan_id,identifier)

    @app.post('/api/studio/projects/{project_id}/image-plans/upload')
    async def upload_image_plan(project_id:str,file:UploadFile=File(...)):
        try:
            content=await file.read(20_000_001)
            from starlette.concurrency import run_in_threadpool
            return await run_in_threadpool(images.upload,project_id,file.filename or '',content)
        finally:await file.close()

    @app.get('/api/studio/projects/{project_id}/image-plans/current')
    def current_image_plan(project_id:str):return images.current(project_id)

    @app.get('/api/studio/projects/{project_id}/image-plans/{image_id}')
    def image_plan(project_id:str,image_id:str):return images.get(project_id,image_id)

    @app.get('/api/studio/projects/{project_id}/image-plans/{image_id}/image')
    def image_plan_source(project_id:str,image_id:str):
        return FileResponse(images.folder(project_id,image_id)/'normalized.png',media_type='image/png')

    @app.post('/api/studio/projects/{project_id}/image-plans/{image_id}/recognize')
    def recognize_image_plan(project_id:str,image_id:str,body:RecognizeImage):return images.start(project_id,image_id,body)

    @app.post('/api/studio/projects/{project_id}/image-plans/{image_id}/draft')
    def image_plan_draft(project_id:str,image_id:str):return images.draft(project_id,image_id)

    @app.post('/api/studio/projects/{project_id}/image-plans/{image_id}/refine')
    def refine_image_plan(project_id:str,image_id:str,body:EvidenceRefinement):return images.refine(project_id,image_id,body)

    @app.get('/api/studio/projects/{project_id}/image-plans/{image_id}/feedback')
    def image_feedback(project_id:str,image_id:str):return images.feedback(project_id,image_id)

    @app.put('/api/studio/projects/{project_id}/image-plans/{image_id}/feedback')
    def save_image_feedback(project_id:str,image_id:str,body:FeedbackInput):return images.save_feedback(project_id,image_id,body)

    @app.post('/api/studio/projects/{project_id}/plans/upload')
    async def upload_plan(project_id:str,file:UploadFile=File(...)):
        try:
            if Path(file.filename or '').suffix.lower()!='.dxf':raise ValueError('此入口支援 ASCII DXF；PNG／JPG 請使用圖片入口，DWG／SKP 尚未開放')
            content=await file.read(10_000_001)
            if len(content)>10_000_000:raise ValueError('DXF 超過 10 MB 上限')
            from starlette.concurrency import run_in_threadpool
            return await run_in_threadpool(plans.create,project_id,file.filename,content)
        finally:await file.close()

    @app.get('/api/studio/projects/{project_id}/plans/current')
    def current_plan(project_id:str):return plans.current(project_id)

    @app.put('/api/studio/projects/{project_id}/plans/{plan_id}')
    def save_plan(project_id:str,plan_id:str,body:SavePlan):return plans.save(project_id,plan_id,body)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/rectify')
    def rectify_plan(project_id:str,plan_id:str,body:RectifyPlan):return plans.rectify(project_id,plan_id,body)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/build')
    def build_plan(project_id:str,plan_id:str,body:BuildPlan):return plans.build(project_id,plan_id,body)

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
            raise ValueError('此入口只接受 GLB；DXF 請使用電子平面入口，PNG／JPG 請使用圖片入口。DWG／SKP 尚未開放。')
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
