"""Same-origin Studio endpoints; agent outputs remain candidates until adopted."""
import copy
from pathlib import Path
from typing import Literal
from fastapi import UploadFile, File, Query
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

class OpenExample(Strict):
    route: Literal['image','dxf','glb']
    operation_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    project_id: str | None = None

class NewLibraryProject(Strict):
    folder_token: str = Field(pattern=r'^[a-f0-9]{32}$')
    name: str = Field(min_length=1,max_length=120)
    operation_id: str = Field(pattern=r'^[a-f0-9]{32}$')

class ProjectView(Strict):
    revision: str = Field(pattern=r'^[a-f0-9]{32}$')
    step: Literal[1,2,3,4,5,6]

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

class SceneReviewAdoption(Strict):
    base_revision: str = Field(pattern=r'^[a-f0-9]{32}$')

class PrepareDetails(SceneReviewAdoption):
    realism_all: bool = False
    prepare_openings: bool = False
    operation_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,100}$')
    point_id: str
    brief: str = Field(default='',max_length=12000)
    model: str | None = None

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
    from .fixture_lighting import FixtureLighting, FixtureLightingRequest, FixtureLightingApply
    fixture_lighting=FixtureLighting(studio,agents)
    from .source_site import SourceSites, SourceSiteRequest
    source_sites=SourceSites(studio)

    @app.get('/api/studio/projects/{project_id}/source-site')
    def source_site_current(project_id:str):
        return source_sites.current(project_id)

    @app.post('/api/studio/projects/{project_id}/source-site')
    def source_site_start(project_id:str,body:SourceSiteRequest):
        return source_sites.start(project_id,body)

    @app.get('/api/studio/projects/{project_id}/source-site/{job_id}/files/{name:path}')
    def source_site_file(project_id:str,job_id:str,name:str):
        path=source_sites.artifact(project_id,job_id,name)
        return FileResponse(path,headers={'Cache-Control':'no-cache','X-Content-Type-Options':'nosniff'},
                            filename='website.zip' if path.suffix=='.zip' else None)

    @app.post('/api/studio/projects/{project_id}/fixture-lighting')
    def fixture_lighting_start(project_id:str,body:FixtureLightingRequest):
        return fixture_lighting.start(project_id,body)

    @app.get('/api/studio/projects/{project_id}/fixture-lighting/current')
    def fixture_lighting_current(project_id:str):
        return fixture_lighting.current(project_id)

    @app.get('/api/studio/projects/{project_id}/fixture-lighting/{identifier}')
    def fixture_lighting_get(project_id:str,identifier:str):
        return fixture_lighting.get(project_id,identifier)

    @app.get('/api/studio/projects/{project_id}/fixture-lighting/{identifier}/images/{candidate}/{view}')
    def fixture_lighting_image(project_id:str,identifier:str,candidate:int,view:Literal['object','reverse','bottom']):
        if candidate<0 or candidate>10000:raise ValueError('燈具圖像識別碼無效')
        request=fixture_lighting.request(project_id,identifier)
        path=Path(request['output'])/f'fixture-{candidate}'/f'model-{view}.png'
        if not path.is_file():raise FileNotFoundError('燈具圖像尚未產生')
        return FileResponse(path)

    @app.post('/api/studio/projects/{project_id}/fixture-lighting/{identifier}/apply')
    def fixture_lighting_apply(project_id:str,identifier:str,body:FixtureLightingApply):
        return fixture_lighting.apply(project_id,identifier,body.base_revision)
    jobs.close_callbacks.extend([agents.close,coordinator.close])
    from .plan_import import PlanIntake, SavePlan, BuildPlan, RectifyPlan, PrepareCAD
    plans=PlanIntake(studio)
    from .plan_semantics import PlanSemantics, SemanticRequest, AdoptSemantics, SaveSemanticAnswers
    semantics=PlanSemantics(studio,agents)
    from .semantic_corrections import SaveCorrections,get_drafts,save_drafts
    app.state.plan_semantics=semantics
    from .experience_review import ExperienceReview, CreateExperience, ExperienceAnswer, ExperienceFields, DeactivateExperience
    experiences=ExperienceReview(semantics)
    from .experience_batch import ExperienceBatches, BatchExperienceRequest
    experience_batches=ExperienceBatches(experiences)
    app.state.cad_experiences=experiences
    from .image_evidence import EvidenceRefinement, FeedbackInput
    from .image_plan import ImageIntake, RecognizeImage
    images=ImageIntake(studio,agents)
    from .intake import IntakeSessions,LIMITS
    intake=IntakeSessions(studio,images,plans)
    from .project_library import ProjectLibrary
    library=ProjectLibrary(studio,intake)
    app.state.project_library=library

    @app.get('/api/studio/project-library')
    def project_cards():return library.cards()

    @app.post('/api/studio/project-library/folders/pick')
    def pick_project_folder():return library.pick()

    @app.post('/api/studio/project-library')
    def create_library_project(body:NewLibraryProject):return library.create(body.folder_token,body.name,body.operation_id)

    @app.get('/api/studio/project-library/{identifier}/resume')
    def resume_library_project(identifier:str):return library.resume(identifier)

    @app.put('/api/studio/project-library/{identifier}/view')
    def save_project_view(identifier:str,body:ProjectView):
        library.save_view(identifier,body.revision,body.step)
        return dict(saved=True)

    @app.get('/api/studio/intake')
    def intake_status():return intake.current()

    @app.post('/api/studio/intake/upload')
    async def intake_upload(route:Literal['image','dxf','glb'],operation_id:str,file:UploadFile=File(...),project_id:str|None=None):
        try:
            content=await file.read(LIMITS[route]+1)
            from starlette.concurrency import run_in_threadpool
            return await run_in_threadpool(intake.open,route,file.filename or '',content,operation_id,False,project_id)
        finally:await file.close()

    @app.post('/api/studio/intake/examples')
    def intake_example(body:OpenExample):return intake.open(body.route,'',b'',body.operation_id,True,body.project_id)
    from .layout_design import LayoutDesign, LayoutRequest, AdoptLayout, LayoutBrief, ReviseLayout, LayoutAnswers
    layouts=LayoutDesign(studio,agents)
    from .asset_matching import AssetMatching, MatchRequest, SelectAsset, LinkAsset
    assets=AssetMatching(studio,agents)
    from .selected_repair import SelectedRepair, AssistedSelection
    selected_repairs=SelectedRepair(assets)
    from .asset_batch import AssetBatch, BatchRequest, inventory
    batches=AssetBatch(assets)
    from .editor_repair import EditorRepairs, EditorRepairRequest
    editor_repairs=EditorRepairs(studio,agents,batches)

    @app.get('/api/studio/projects/{project_id}/editor-repairs')
    def repair_records(project_id:str):return editor_repairs.records(project_id)

    @app.get('/api/studio/projects/{project_id}/editor-repairs/{identifier}')
    def repair_state(project_id:str,identifier:str):return editor_repairs.get(project_id,identifier)

    @app.post('/api/studio/projects/{project_id}/editor-repairs')
    def repair_item(project_id:str,body:EditorRepairRequest):return editor_repairs.start(project_id,body)
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

    from . import object_specs

    @app.post('/api/studio/projects/{project_id}/object-specifications/understand')
    def specification_understand(project_id:str,body:object_specs.UnderstandInput):
        from uuid import uuid5, NAMESPACE_URL
        report=object_specs.preview(studio,project_id,body.base_revision)
        if set(body.group_ids)-{r['group_id'] for r in report['items']}:raise ValueError('物件範圍已變更')
        for row in report['items']:
            if row['group_id'] in body.specifications:
                spec=body.specifications[row['group_id']].model_dump()
                if row['purpose_reason']=='已確認規格' and spec['purpose']!=row['specification']['purpose']:raise ValueError('不能覆蓋已確認用途')
                row['specification']=spec
        identifier=uuid5(NAMESPACE_URL,'object-spec:'+project_id+':'+body.base_revision+':'+body.operation_id).hex
        path=studio.folder(project_id)/'object-specifications'/f'task-{identifier}.json'
        payload=dict(project_id=project_id,preview=report,design_notes=studio.current(project_id)['scene'].get('design_notes',[]),group_ids=body.group_ids,style=body.style,object_styles=body.object_styles)
        write_json(path,dict(id=identifier,base_revision=body.base_revision))
        write_json(path.parent/'current-task.json',dict(id=identifier))
        return agents.start('object_specs',body.model,payload,identifier=identifier)

    @app.get('/api/studio/projects/{project_id}/object-specifications/current')
    def current_specification_task(project_id:str):
        path=studio.folder(project_id)/'object-specifications/current-task.json'
        return agents.get(read_json(path)['id']) if path.is_file() else None

    @app.get('/api/studio/projects/{project_id}/object-specifications/tasks/{identifier}')
    def specification_task(project_id:str,identifier:str):
        import re
        if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('任務 ID 無效')
        read_json(studio.folder(project_id)/'object-specifications'/f'task-{identifier}.json')
        return agents.get(identifier)

    @app.post('/api/studio/projects/{project_id}/object-specifications/preview')
    def specification_preview(project_id:str,body:object_specs.SpecificationInput):
        return object_specs.preview(studio,project_id,body.base_revision)

    @app.post('/api/studio/projects/{project_id}/object-specifications/save')
    def specification_save(project_id:str,body:object_specs.SpecificationInput):
        return object_specs.save(studio,project_id,body)

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

    @app.post('/api/studio/projects/{project_id}/asset-batches/{identifier}/repair')
    def repair_asset_batch(project_id:str,identifier:str,body:ConfirmWorkflow):
        return batches.automation.repair(project_id,identifier,body.base_revision)

    @app.post('/api/studio/projects/{project_id}/asset-batches/{identifier}/generate-missing')
    def generate_missing_furniture(project_id:str,identifier:str,body:ConfirmWorkflow):
        return batches.automation.generate_missing(project_id,identifier,body.base_revision)

    @app.post('/api/studio/projects/{project_id}/asset-batches/{identifier}/confirm')
    def confirm_asset_batch(project_id:str,identifier:str,body:AssetReview):
        return batches.automation.confirm(project_id,identifier,body.base_revision,body.keep_original)

    from .asset_matching import PreviewRepair
    @app.get('/api/studio/projects/{project_id}/asset-preview-repair')
    def preview_repair_job(project_id:str,group_id:str):return assets.preview_job(project_id,group_id)

    @app.post('/api/studio/projects/{project_id}/asset-preview-repair')
    def repair_material_preview(project_id:str,body:PreviewRepair):return assets.repair_preview(project_id,body)

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

    @app.post('/api/studio/projects/{project_id}/asset-matches/{task_id}/replace-assisted')
    def replace_assisted(project_id:str,task_id:str,body:AssistedSelection):return selected_repairs.start(project_id,task_id,body)

    @app.get('/api/studio/projects/{project_id}/asset-matches/{task_id}/replacement-flow')
    def current_replacement_flow(project_id:str,task_id:str):return selected_repairs.current(project_id,task_id)

    @app.get('/api/studio/projects/{project_id}/replacement-flows/{identifier}')
    def replacement_flow(project_id:str,identifier:str):return selected_repairs.get(project_id,identifier)

    @app.post('/api/studio/projects/{project_id}/replacement-flows/{identifier}/resume')
    def resume_replacement_flow(project_id:str,identifier:str,body:ConfirmWorkflow):return selected_repairs.resume(project_id,identifier,body.base_revision)

    @app.post('/api/studio/projects/{project_id}/replacement-flows/{identifier}/stop')
    def stop_replacement_flow(project_id:str,identifier:str):return selected_repairs.stop(project_id,identifier)

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
            if Path(file.filename or '').suffix.lower() not in ('.dxf','.dwg'):raise ValueError('此入口支援 DXF／DWG 平面圖；PNG／JPG 請使用圖片入口，SKP 尚未開放')
            content=await file.read(10_000_001)
            if len(content)>10_000_000:raise ValueError('電子平面超過 10 MB 上限')
            from starlette.concurrency import run_in_threadpool
            return await run_in_threadpool(plans.create,project_id,file.filename,content)
        finally:await file.close()

    @app.get('/api/studio/projects/{project_id}/plans/current')
    def current_plan(project_id:str):return plans.current(project_id)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/source-drawing')
    def cad_source_drawing(project_id:str,plan_id:str):return plans.source_drawing(project_id,plan_id)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/prepare')
    def prepare_cad_plan(project_id:str,plan_id:str,body:PrepareCAD):return plans.prepare(project_id,plan_id,body)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/semantics')
    def start_plan_semantics(project_id:str,plan_id:str,body:SemanticRequest):return semantics.start(project_id,plan_id,body)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/semantics')
    def current_plan_semantics(project_id:str,plan_id:str):return semantics.get(project_id,plan_id)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/corrections')
    def plan_correction_drafts(project_id:str,plan_id:str):return get_drafts(semantics,project_id,plan_id)

    @app.put('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/corrections')
    def save_plan_correction_drafts(project_id:str,plan_id:str,body:SaveCorrections):return save_drafts(semantics,project_id,plan_id,body)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/{task_id}')
    def plan_semantics_task(project_id:str,plan_id:str,task_id:str):return semantics.get(project_id,plan_id,task_id)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/{task_id}/reconcile-batch')
    def reconcile_plan_batch(project_id:str,plan_id:str,task_id:str,body:AdoptSemantics):return semantics.reconcile_batch(project_id,plan_id,task_id,body)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/experience-drafts')
    def experience_drafts(project_id:str,plan_id:str):
        result=experiences.list(project_id,plan_id)
        result['adoptions']=experience_batches.adoptions(project_id,plan_id)
        return result

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/experience-drafts')
    def create_experience(project_id:str,plan_id:str,body:CreateExperience):return experiences.create(project_id,plan_id,body)

    @app.put('/api/studio/projects/{project_id}/plans/{plan_id}/experience-drafts/{identifier}')
    def save_experience(project_id:str,plan_id:str,identifier:str,body:ExperienceFields):return experiences.save(project_id,plan_id,identifier,body)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/experience-drafts/{identifier}/confirm')
    def confirm_experience(project_id:str,plan_id:str,identifier:str,body:ExperienceAnswer):return experiences.confirm(project_id,plan_id,identifier,body)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/experience-drafts/{identifier}/search')
    def search_experience(project_id:str,plan_id:str,identifier:str):return experiences.search(project_id,plan_id,identifier)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/experience-drafts/{identifier}/image')
    def experience_image(project_id:str,plan_id:str,identifier:str):
        experiences.get(project_id,plan_id,identifier)
        return FileResponse(experiences.folder(project_id,plan_id)/identifier/'source.png',media_type='image/png')

    @app.get('/api/studio/cad-experiences')
    def experience_catalog(offset:int=0):
        result=experiences.library.catalog(offset=offset)
        result['entries']=[{k:v for k,v in e.items() if k not in ('descriptor','examples')}|{'example_count':len(e.get('examples',[])) or 1} for e in result['entries']]
        return result

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/{task_id}/question-history')
    def plan_question_history(project_id:str,plan_id:str,task_id:str):
        from .question_history import question_history
        return question_history(semantics,project_id,plan_id,task_id)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/experience-batches')
    def start_experience_batch(project_id:str,plan_id:str,body:BatchExperienceRequest):return experience_batches.start(project_id,plan_id,body)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/experience-batches')
    def latest_experience_batch(project_id:str,plan_id:str,review_id:str):return experience_batches.latest(project_id,plan_id,review_id)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/experience-batches/{identifier}')
    def get_experience_batch(project_id:str,plan_id:str,identifier:str):return experience_batches.get(project_id,plan_id,identifier)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/experience-batches/{identifier}/apply')
    def apply_experience_batch(project_id:str,plan_id:str,identifier:str):return experience_batches.apply(project_id,plan_id,identifier)

    @app.get('/api/studio/cad-experiences/{identifier}/image')
    def confirmed_experience_image(identifier:str):return FileResponse(experiences.library.image_path(identifier),media_type='image/png')

    @app.post('/api/studio/cad-experiences/{identifier}/deactivate')
    def deactivate_experience(identifier:str,body:DeactivateExperience):return experiences.library.deactivate(identifier,body.revision)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/{task_id}/source')
    def plan_semantics_source(project_id:str,plan_id:str,task_id:str):
        semantics.get(project_id,plan_id,task_id)
        return FileResponse(semantics.folder(project_id,plan_id)/'runs'/task_id/'source.png',media_type='image/png')

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/{task_id}/annotations')
    def plan_semantics_annotations(project_id:str,plan_id:str,task_id:str):
        semantics.get(project_id,plan_id,task_id)
        return FileResponse(semantics.folder(project_id,plan_id)/'runs'/task_id/'questions.svg',media_type='image/svg+xml')

    @app.put('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/{task_id}/answers')
    def plan_semantics_answers(project_id:str,plan_id:str,task_id:str,body:SaveSemanticAnswers):return semantics.save_answers(project_id,plan_id,task_id,body)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/{task_id}/adopt')
    def adopt_plan_semantics(project_id:str,plan_id:str,task_id:str,body:AdoptSemantics):return semantics.adopt(project_id,plan_id,task_id,body)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/{task_id}/preview-3d')
    def preview_plan_semantics(project_id:str,plan_id:str,task_id:str,body:AdoptSemantics):
        from .plan_handoff import preview
        return preview(semantics,project_id,plan_id,task_id,body)

    @app.get('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/{task_id}/preview-3d')
    def get_plan_preview(project_id:str,plan_id:str,task_id:str):
        semantics.get(project_id,plan_id,task_id)
        path=semantics.folder(project_id,plan_id)/'runs'/task_id/'preview-job.json'
        if not path.exists():return None
        job=jobs.get(read_json(path)['job_id'])
        scene=None
        if job['status']=='completed':
            from .plan_handoff import model_scene
            scene=model_scene(studio,project_id,job['id'])
        return dict(job=job,scene=scene,preview_only=True)

    @app.post('/api/studio/projects/{project_id}/plans/{plan_id}/semantics/{task_id}/stop')
    def stop_plan_semantics(project_id:str,plan_id:str,task_id:str):
        semantics.get(project_id,plan_id,task_id)
        agents.stop(task_id)
        return semantics.get(project_id,plan_id,task_id)

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

    @app.post('/api/studio/projects/{project_id}/regroup-structure')
    def regroup_structure(project_id:str,body:AssetReview):
        batch=batches.current(project_id)
        if batch and batch['status'] in ('queued','running','stopping','matching','applying','paused'):
            raise Conflict('請先停止目前的一鍵配置，再整理牆地分組')
        return studio.regroup(project_id,body.base_revision)

    @app.get('/api/studio/projects/{project_id}/models/{model_id}')
    def model(project_id:str,model_id:str):
        return studio.model(project_id,model_id)

    @app.get('/api/studio/projects/{project_id}/models/{model_id}/doors')
    def doors(project_id:str,model_id:str):
        from .opening_details import source_openings
        source=source_openings(studio.root(project_id),studio.model(project_id,model_id))
        return dict(items=[i for i in source['items'] if i['role']=='door'],reason=source.get('reason'))

    from .door_assets import DoorAssets, DoorMatch, DoorSelection
    door_assets=DoorAssets(studio,agents)
    @app.post('/api/studio/projects/{project_id}/door-assets')
    def match_door_asset(project_id:str,body:DoorMatch):return door_assets.start(project_id,body)
    @app.get('/api/studio/projects/{project_id}/door-assets/current')
    def current_door_asset(project_id:str,opening:str,part:str):return door_assets.current(project_id,opening,part)
    @app.get('/api/studio/projects/{project_id}/door-assets/{key}')
    def door_asset_status(project_id:str,key:str):return door_assets.get(project_id,key)
    @app.post('/api/studio/projects/{project_id}/door-assets/{key}/select')
    def select_door_asset(project_id:str,key:str,body:DoorSelection):return door_assets.select(project_id,key,body)
    @app.get('/api/studio/projects/{project_id}/door-assets/{key}/selection')
    def door_asset_selection(project_id:str,key:str):return door_assets.status(project_id,key)
    @app.get('/api/studio/projects/{project_id}/door-assets/{key}/preview')
    def preview_door_asset(project_id:str,key:str):
        if door_assets.status(project_id,key)['status']!='completed':raise ValueError('門素材尚未完成檢查')
        return read_json(door_assets.path(project_id,key)/'proposal.json')
    @app.post('/api/studio/projects/{project_id}/door-assets/{key}/adopt')
    def adopt_door_asset(project_id:str,key:str,body:SceneReviewAdoption):return door_assets.adopt(project_id,key,body.base_revision)
    @app.get('/api/studio/projects/{project_id}/doors/previews/{key}')
    def door_asset_preview(project_id:str,key:str):
        import re
        if not re.fullmatch('[a-f0-9]{64}',key):raise ValueError('無效門預覽')
        return FileResponse(studio.root(project_id)/'runs/interior-studio/door-poses'/key/'doors.glb',media_type='model/gltf-binary')

    from .door_design import DoorDesignRequest

    @app.post('/api/studio/projects/{project_id}/doors/poses')
    def door_poses(project_id:str,body:DoorDesignRequest):
        from .opening_details import source_openings
        from .door_collision import check_poses
        model=studio.model(project_id,body.scene.model_id)
        source=source_openings(studio.root(project_id),model)
        return check_poses(studio.root(project_id),model,body.scene.model_dump(mode='json'),source)

    @app.post('/api/studio/projects/{project_id}/doors/width-preview')
    def width_preview(project_id:str,body:DoorDesignRequest):
        from .opening_details import source_openings
        from .door_collision import width_candidates
        model=studio.model(project_id,body.scene.model_id)
        source=source_openings(studio.root(project_id),model)
        controls=[c.model_dump(mode='json') for c in body.scene.door_controls]
        fits=width_candidates(dict(collision_context=dict(blend=str(studio.root(project_id)/'runs/interior-studio'/body.scene.model_id/'model.blend'),sha256=model['native_sha256'],scene=body.scene.model_dump(mode='json')),openings=[i for i in source['items'] if i['role']=='door']+[d.model_dump(mode='json') for d in body.scene.manual_doors],controls=controls))
        for c in controls:
            fit=fits.get(c['opening_id'])
            if fit and not fit.get('no_fit'):c['assembly_width']=fit['recommended_width']
        return dict(controls=controls,width_candidates=fits,review_status='agent_pending')

    @app.get('/api/studio/projects/{project_id}/editor-issues')
    def read_editor_issues(project_id:str,revision:str):
        from .editor_issues import editor_issues
        return editor_issues(studio,agents,project_id,revision)

    @app.post('/api/studio/projects/{project_id}/doors/design')
    def design_doors(project_id:str,body:DoorDesignRequest):
        from .opening_details import source_openings
        model=studio.model(project_id,body.scene.model_id)
        source=source_openings(studio.root(project_id),model)
        openings=[i for i in source['items'] if i['role']=='door']
        openings.extend(d.model_dump(mode='json') for d in body.scene.manual_doors)
        deleted={c.opening_id for c in body.scene.door_controls if c.deleted}
        openings=[o for o in openings if o['id'] not in deleted]
        if not openings:raise ValueError('找不到可追溯門洞；請先以兩點標示門的位置')
        task=agents.start('door_design',model='gpt-6-sol',payload=dict(collision_context=dict(blend=str(studio.root(project_id)/'runs/interior-studio'/body.scene.model_id/'model.blend'),sha256=model['native_sha256'],scene=body.scene.model_dump(mode='json')),openings=openings,plan=source.get('plan_items',[]),
            controls=[d.model_dump() for d in body.scene.door_controls],rooms=[r.model_dump() for r in body.scene.rooms],
            objects=[dict(name=g.name,translation=g.translation,spec=g.object_specification.model_dump() if g.object_specification else None) for g in body.scene.groups if not g.deleted]))

        from .editor_issues import remember_door_task
        remember_door_task(studio,project_id,task,body.scene.model_dump(mode='json'))
        return task

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
        if Path(name).suffix.lower() not in ('.glb','.skp'):
            await file.close()
            raise ValueError('此入口接受 GLB／SKP；DWG／DXF 請使用電子平面入口，PNG／JPG 請使用圖片入口。')
        limit=512_000_000
        content=await file.read(limit+1)
        await file.close()
        if len(content)>limit:raise ValueError('3D 模型超過 512 MB 大小上限')
        from uuid import uuid4
        return studio.upload_glb(project_id,name,content,uuid4().hex)

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

    @app.get('/api/studio/jobs/{job_id}/scene-review')
    def scene_review(job_id:str):
        job=jobs.get(job_id)
        if job['operation']!='studio.render':raise ValueError('非渲染工作')
        path=studio.root(job['project_id'])/job['output']/'scene-review.json'
        return read_json(path) if path.exists() else dict(status='pending',attempts=[],revision=job['source_revision'])

    @app.get('/api/studio/jobs/{job_id}/realism-review')
    def realism_review(job_id:str):
        job=jobs.get(job_id)
        if job['operation']!='studio.render':raise ValueError('非渲染工作')
        path=studio.root(job['project_id'])/job['output']/'realism-review.json'
        return read_json(path) if path.exists() else dict(status='pending',attempts=[])

    @app.post('/api/studio/projects/{project_id}/realism-prepare')
    def prepare_details(project_id:str,body:PrepareDetails):
        with studio.store.lock:
            current=studio.current(project_id)
            if current['revision']!=body.base_revision:raise Conflict('請先保存目前編輯，再準備預覽')
            if not any(p['id']==body.point_id for p in current['scene']['viewpoints']):raise ValueError('請選擇已有觀看點作預覽範圍')
            return jobs.submit_studio(project_id,'render',dict(revision=body.base_revision,quality='preview',realism_point_id=body.point_id,realism_brief=body.brief,agent_model=body.model,prepare_only=True,realism_all=body.realism_all,prepare_openings=body.prepare_openings),body.operation_id)

    @app.get('/api/studio/projects/{project_id}/realism-prepare')
    def current_preparation(project_id:str):
        revision=studio.current(project_id)['revision']
        for job in jobs.list(project_id):
            if job['operation']!='studio.render' or job['source_revision']!=revision:continue
            path=store.state_dir/'jobs'/job['id']/'request.json'
            if path.exists():
                params=read_json(path)['parameters']
                if params.get('prepare_only'):return dict(job,preparation_context=dict(brief=params.get('realism_brief','')))

        return None

    @app.post('/api/studio/projects/{project_id}/realism-review/{job_id}/adopt')
    def adopt_realism(project_id:str,job_id:str,body:SceneReviewAdoption):
        from .realism import adopt
        return adopt(studio,project_id,job_id,body.base_revision)

    @app.get('/api/studio/projects/{project_id}/realism-review/{job_id}/preview')
    def realism_model_preview(project_id:str,job_id:str):
        from .realism import model_preview
        return model_preview(studio,project_id,job_id)

    @app.post('/api/studio/projects/{project_id}/scene-review/{job_id}/adopt')
    def adopt_scene_review(project_id:str,job_id:str,body:SceneReviewAdoption):
        from .scene_review import adopt
        return adopt(studio,project_id,job_id,body.base_revision)

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
        return coordinator.start(project_id,body.base_revision,body.operation_id,body.quality,body.scene_review,body.agent_model,body.realism_point_id,body.realism_brief,body.realism_all,body.prepare_openings)

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

    @app.get('/api/studio/agent/tasks')
    def agent_worklist(history_limit:int=Query(default=20,ge=1,le=200),history_offset:int=Query(default=0,ge=0)):
        return agents.list(history_limit,history_offset)

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
