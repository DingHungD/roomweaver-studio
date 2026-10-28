"""Render a prepared source model without applying an editor revision."""
from pathlib import Path
import re
import shutil
import subprocess
from pydantic import Field
from .models import Strict, LightingSetup
from .service import digest
from ..storage import Conflict, now, read_json, write_json


class SourceSiteRequest(Strict):
    operation_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,100}$')
    model_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    quality: str = Field(default='preview',pattern=r'^(preview|final)$')
    views: int = Field(default=3,ge=1,le=8)
    lighting: str = Field(default='preview',pattern=r'^(native|preview|fixtures)$')
    exposure: float = Field(default=0,ge=-3,le=3)
    mode: str = Field(default='render',pattern=r'^(render|sync-production)$')


def checked_model(root, model_id, source_sha):
    root=Path(root).resolve()
    if not re.fullmatch(r'[a-f0-9]{32}',model_id):raise ValueError('模型識別碼無效')
    folder=(root/'runs/interior-studio'/model_id).resolve()
    if not folder.is_relative_to(root):raise ValueError('原模型超出案件範圍')
    model=read_json(folder/'model.json')
    if model['source_sha256']!=source_sha:raise Conflict('來源已變更，請重新準備原模型')
    native=(folder/'model.blend').resolve()
    if not native.is_relative_to(folder):raise ValueError('原模型超出執行範圍')
    if digest(native)!=model['native_sha256']:raise Conflict('原模型檔案雜湊不符')
    return native,model


class SourceSites:
    def __init__(self,studio):self.studio=studio

    def current(self,project_id):
        root=self.studio.root(project_id)
        source=self.studio.configured_source(project_id)
        sha=digest(root/source['native'])
        if source.get('sha256') and source['sha256']!=sha:raise Conflict('來源雜湊不符')
        metadata=read_json(root/'project.json')
        if metadata.get('studio_intake',{}).get('route','glb')!='glb':raise ValueError('此入口用於完整 3D 模型')
        session=root/'workflows/project-session/intake.json'
        preferred=read_json(session).get('job_id') if session.exists() else None
        candidates=self.studio.jobs.list(project_id)
        candidates=sorted(candidates,key=lambda j:(j['id']==preferred,j['created_at']),reverse=True)
        model_id=None
        for job in candidates:
            if job['operation']!='studio.prepare' or job['status']!='completed':continue
            path=root/'runs/interior-studio'/job['id']/'model.json'
            if path.exists() and read_json(path).get('source_sha256')==sha:
                model_id=job['id'];break
        # Legacy imports can predate the durable queue, but must still match the
        # immutable configured source rather than a replacement model hash.
        scene=self.studio.current(project_id)['scene']
        if not model_id and scene:
            path=root/'runs/interior-studio'/scene['model_id']/'model.json'
            if path.exists() and read_json(path).get('source_sha256')==sha:model_id=scene['model_id']
        fixtures=bool(scene and scene['model_id']==model_id and scene.get('lighting_setup',{}).get('enabled'))
        runs=[j for j in candidates if j['operation']=='studio.source-site']
        matching=[]
        for job in runs:
            request=read_json(self.studio.store.state_dir/'jobs'/job['id']/'request.json')['parameters']
            if request.get('source_sha256')==sha and request.get('model_id')==model_id:matching.append(job)
        known={j['id'] for j in matching}
        for path in (root/'runs/interior-studio').glob('*/source-site.json'):
            record=read_json(path)
            if record['id'] not in known and record.get('source_sha256')==sha and record.get('model_id')==model_id:
                matching.append(record)
        matching.sort(key=lambda j:j['created_at'],reverse=True)
        return dict(model_id=model_id,source_sha256=sha,fixtures_available=fixtures,
                    upstream_available=(root/'workflows/source-website/upstream.json').is_file(),
                    jobs=matching,source_name=metadata.get('studio_intake',{}).get('source_name',Path(source['native']).name))

    def start(self,project_id,body):
        current=self.current(project_id)
        if not current['model_id'] or body.model_id!=current['model_id']:raise Conflict('原模型尚未準備完成或來源已更新')
        root=self.studio.root(project_id)
        checked_model(root,body.model_id,current['source_sha256'])
        if body.mode=='sync-production':
            from .production_site import production_input
            upstream=production_input(root,read_json(root/'workflows/source-website/upstream.json'))
            params=dict(model_id=body.model_id,source_sha256=current['source_sha256'],upstream=upstream,
                        title=read_json(root/'project.json')['name'])
            return self.studio.jobs.submit_studio(project_id,'source-site',params,body.operation_id)
        scene=self.studio.current(project_id)['scene']
        setup=None
        if body.lighting=='fixtures':
            if not current['fixtures_available']:raise Conflict('沒有與原模型相符的燈具照明')
            setup=LightingSetup.model_validate(scene['lighting_setup']).model_dump(mode='json')
        # Freeze ONLY cameras and lighting. No material, furniture, door or group
        # mutation from the editor can enter the renderer through this contract.
        cameras=(scene.get('viewpoints',[]) if scene and scene['model_id']==body.model_id else [])
        params=dict(model_id=body.model_id,source_sha256=current['source_sha256'],quality=body.quality,
                    views=body.views,lighting=body.lighting,lighting_setup=setup,exposure=body.exposure,
                    viewpoints=[dict(name=p['name'],eye=p['eye']) for p in cameras],
                    title=read_json(root/'project.json')['name'])
        return self.studio.jobs.submit_studio(project_id,'source-site',params,body.operation_id)

    def artifact(self,project_id,job_id,name):
        if not re.fullmatch(r'[a-f0-9]{32}',job_id):raise ValueError('網站識別碼無效')
        try:job=self.studio.jobs.get(job_id)
        except (FileNotFoundError,KeyError):
            job=read_json(self.studio.root(project_id)/'runs/interior-studio'/job_id/'source-site.json')
        if job['project_id']!=project_id or job['operation']!='studio.source-site' or job['status']!='completed':raise ValueError('網站尚未完成或不屬於本案')
        if job['output']!='runs/interior-studio/'+job_id:raise ValueError('網站輸出路徑不符')
        base=(self.studio.root(project_id)/job['output']).resolve()
        if not base.is_relative_to(self.studio.root(project_id).resolve()/'runs/interior-studio'):raise ValueError('網站超出案件範圍')
        path=(base/name).resolve()
        if not path.is_relative_to(base) or path.suffix.lower() not in ('.html','.js','.css','.json','.jpg','.zip') or not path.is_file():raise ValueError('網站檔案不存在')
        return path


def execute_source_site(root,output,parameters,executable):
    root,output=Path(root).resolve(),Path(output).resolve()
    if output.parent!=root/'runs/interior-studio' or not re.fullmatch(r'[a-f0-9]{32}',output.name):raise ValueError('網站輸出必須是本案新的執行目錄')
    if parameters.get('upstream'):
        from .production_site import import_production
        return import_production(root,output,parameters)
    native,model=checked_model(root,parameters['model_id'],parameters['source_sha256'])
    # A source may be replaced while a queued render is waiting.
    source=read_json(root/'workflows/interior-studio/source.json')
    source_path=(root/source['native']).resolve()
    if not source_path.is_relative_to(root) or digest(source_path)!=parameters['source_sha256']:raise Conflict('排隊期間原始來源已變更')
    output.mkdir(parents=True,exist_ok=True)
    if (output/'site').exists() or (output/'website.zip').exists():raise Conflict('此執行目錄已有成果，請建立新工作')
    if shutil.disk_usage(output).free<1024**3:raise ValueError('網站出圖至少需要 1 GB 可用磁碟空間')
    site=output/'site';site.mkdir(exist_ok=True)
    request=dict(parameters,native=str(native),output=str(output))
    write_json(output/'source-request.json',request)
    script=Path(__file__).resolve().parents[2]/'visualization/source_site_blender.py'
    with (output/'blender.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([executable,'--background','--disable-autoexec','--debug-cycles','--python-exit-code','1',
            '--python',str(script),'--',str(output/'source-request.json')],stdout=log,stderr=log,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        from .processes import identity
        write_json(output/'blender-process.json',dict(pid=process.pid,identity=identity(process.pid)))
        try:code=process.wait(timeout=14400)
        except subprocess.TimeoutExpired:
            process.terminate();process.wait(timeout=15);raise
    if code:raise ValueError('原模型渲染失敗，請查看 blender.log')
    device=read_json(output/'device-request.json')
    device['execution_trace']=[line.strip() for line in (output/'blender.log').read_text(encoding='utf-8',errors='replace').splitlines() if 'Path tracing on' in line or 'Denoising on' in line]
    write_json(output/'render-device.json',device)
    if digest(native)!=model['native_sha256']:raise Conflict('原模型在渲染期間變更')
    report=read_json(output/'preservation.json')
    if not report.get('preserved'):raise Conflict('原模型保留檢查失敗')
    from .site_packaging import source_gallery,copy_viewer,archive_site
    source_gallery(site);copy_viewer(site)
    result=dict(model_id=parameters['model_id'],source_sha256=parameters['source_sha256'],native_sha256=model['native_sha256'],
                quality=parameters['quality'],preserved=True,view_count=report['view_count'],site='site/index.html',archive='website.zip',
                website_kind='360-panorama',lighting=parameters['lighting'],exposure=parameters.get('exposure',0),render_device=device)
    write_json(output/'result.json',result)
    archive_site(output)
    record_completed_source_site(root,output,result)
    return result


def record_completed_source_site(root,output,result):
    """Index a completed standalone run, retaining the same artifact boundary."""
    root,output=Path(root).resolve(),Path(output).resolve()
    if output.parent!=root/'runs/interior-studio' or not re.fullmatch(r'[a-f0-9]{32}',output.name):raise ValueError('網站執行路徑無效')
    native,model=checked_model(root,result['model_id'],result['source_sha256'])
    if not result.get('preserved') or not read_json(output/'preservation.json').get('preserved') or not (output/'website.zip').is_file():raise ValueError('網站尚未通過保留檢查')
    write_json(output/'source-site.json',dict(id=output.name,project_id=read_json(root/'project.json')['id'],
        operation='studio.source-site',status='completed',created_at=now(),output=output.relative_to(root).as_posix(),
        model_id=result['model_id'],source_sha256=result['source_sha256'],result=result,error=None))
