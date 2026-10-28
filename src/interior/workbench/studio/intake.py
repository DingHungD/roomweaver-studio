"""File-first intake sessions and clean Project04 teaching copies.

Inputs belong to the selected project, or a new project for legacy callers.
Bundled examples, original sources and earlier scene revisions are preserved.
"""
import hashlib
from pathlib import Path
import re
import threading
from ..storage import Conflict,now,read_json,write_json

ROUTES={'image':('.png','.jpg','.jpeg'),'dxf':('.dxf','.dwg'),'glb':('.glb','.skp')}
LIMITS={'image':20_000_000,'dxf':10_000_000,'glb':512_000_000}
FILES={'image':'from-image/project04-plan.png','dxf':'from-dxf/project04-plan.dxf','glb':'from-3d/project04-apartment.glb'}

class IntakeSessions:
    def __init__(self,studio,images,plans,examples=None):
        self.studio,self.images,self.plans=studio,images,plans
        self.store=studio.store
        self.lock=threading.RLock()
        self.folder=self.store.state_dir/'intake'
        self.examples=Path(examples) if examples is not None else Path(__file__).resolve().parents[4]/'examples'

    def project_info(self,identifier):
        project=self.store.project(identifier)
        metadata=read_json(project.root/'project.json')
        if metadata.get('studio_archived'):return None
        intake=metadata.get('studio_intake',{})
        return dict(id=identifier,name=metadata['name'],revision=self.studio.current(identifier)['revision'],
            configured=(self.studio.folder(identifier)/'source.json').exists(),route=intake.get('route','glb'),has_intake=bool(intake))

    def current(self):
        pointer=self.folder/'current.json'
        current=None;job=None
        if pointer.exists():
            saved=read_json(pointer)
            try:current=self.project_info(saved['project_id'])
            except FileNotFoundError:pass
            if current and saved.get('job_id') and not current['revision']:
                job=self.studio.jobs.get(saved['job_id'])
        # Old workspaces can continue their one retained case without a dropdown.
        if not current:
            projects=self.store.projects()
            retained=next((p for p in projects if p['id']=='EXAMPLE_IMAGE'),None) or next(iter(projects),None)
            if retained:current=self.project_info(retained['id'])
        return dict(current=current,job=job,examples={route:self.available(route) for route in ROUTES})

    def available(self,route):
        if not (self.examples/FILES[route]).is_file():return False
        if route=='glb':return all((self.examples/'from-3d'/name).is_file() for name in ('manifest.json','project04-apartment.blend'))
        return True

    def open(self,route,name,content,operation_id,example=False,project_id=None):
        if route not in ROUTES:raise ValueError('不支援的匯入入口')
        if not re.fullmatch(r'[a-f0-9]{32}',operation_id):raise ValueError('匯入識別碼無效')
        if example:
            if not self.available(route):raise FileNotFoundError('Project04 範例檔案未安裝；請保留 repo 的 examples 目錄')
            source=self.examples/FILES[route];name=source.name
            content=source.read_bytes()
        name=Path(name.replace('\\','/')).name
        if Path(name).suffix.lower() not in ROUTES[route]:raise ValueError('檔案格式與所選入口不符')
        if not content or len(content)>LIMITS[route]:raise ValueError('檔案為空或超過此入口大小上限')
        if route=='glb':
            from ...visualization.sketchup import valid_header
            if Path(name).suffix.lower()=='.glb':
                if content[:4]!=b'glTF':raise ValueError('GLB 檔頭無效')
            elif not valid_header(content[:128]):raise ValueError('SKP 檔頭無效')
        fingerprint=dict(route=route,name=name,sha256=hashlib.sha256(content).hexdigest(),example=example)
        if project_id:fingerprint['project_id']=project_id
        display_name=('Project04｜'+{'image':'圖片','dxf':'DXF','glb':'3D'}[route]+'範例') if example else Path(name).stem
        record=self.folder/'operations'/(operation_id+'.json')
        identifier=project_id or ('P04_' if example else 'DESIGN_')+operation_id
        # Serialise intake IDs without blocking scene reads/saves during ODA.
        with self.lock:
            base_revision=None
            if project_id:
                if not self.project_info(project_id):raise ValueError('此專案已封存')
                base_revision=self.studio.current(project_id)['revision']
            if record.exists():
                old=read_json(record)
                if old['input']!=fingerprint:raise Conflict('同一匯入識別碼不能用於不同檔案')
                if old['status']!='completed':raise Conflict('上次匯入尚未完成或已中斷，請重新選檔重試')
                result=old['result']
                if result.get('job'):result['job']=self.studio.jobs.get(result['job']['id'])
                return result
            if project_id and any(j['status'] in ('queued','running') for j in self.studio.jobs.list(project_id)):raise Conflict('此專案仍有工作執行中，請完成後再匯入新檔案')
            self.folder.mkdir(parents=True,exist_ok=True)
            readme=self.folder/'README.md'
            if not readme.exists():
                readme.write_text('# Local intake sessions\n\nOwner: application runtime. current.json points to the latest independent import project and its initial job. operations/ binds operation IDs to source hashes and results for deduplication.\n\nDesign authority and original files stay in projects/. Back up this folder with the workspace databases; do not clear operation history while jobs or retries depend on it.\n',encoding='utf-8')
            write_json(record,dict(status='starting',input=fingerprint,project_id=identifier,created_at=now()))
            try:
                if project_id:pass
                elif route=='glb' and example:
                    from .example import register_example
                    register_example(self.store.workspace,self.examples/'from-3d',identifier)
                else:self.store.create_project(dict(id=identifier,name=display_name,kind='synthetic' if example else 'user'))
                metadata_path=self.store.project(identifier).root/'project.json'
                metadata=read_json(metadata_path)
                if not project_id:metadata['name']=display_name
                job=None;source_path=None;created_at=now()
                if route=='image':source_path=self.images.upload(identifier,name,content)['source']['path']
                elif route=='dxf':source_path=self.plans.create(identifier,name,content)['source']['path']
                elif example:
                    if project_id:
                        from .example import install_example_source
                        install_example_source(self.examples/'from-3d',self.studio.root(identifier),operation_id)
                    job=self.studio.import_existing(identifier,operation_id)
                else:job=self.studio.upload_glb(identifier,name,content,operation_id)
                metadata['studio_intake']=dict(route=route,example=example,source_name=name)
                write_json(metadata_path,metadata)
                result=dict(project=self.project_info(identifier),route=route,job=job,base_revision=base_revision)
                write_json(self.studio.root(identifier)/'workflows/project-session/intake.json',dict(route=route,source_path=source_path,job_id=job['id'] if job else None,base_revision=base_revision,created_at=created_at))
                write_json(record,dict(status='completed',input=fingerprint,result=result))
                write_json(self.folder/'current.json',dict(project_id=identifier,job_id=job['id'] if job else None))
                return result
            except Exception:
                # Preserve failed inputs for diagnosis, but never present an empty
                # failed project as the user's current design.
                if not project_id:
                    try:
                        path=self.store.project(identifier).root/'project.json'
                        data=read_json(path);data['studio_archived']=True;write_json(path,data)
                    except FileNotFoundError:pass
                write_json(record,dict(status='failed',input=fingerprint,project_id=identifier))
                raise
