"""Project cards, explicit local folder grants and evidence-based resume targets."""
from pathlib import Path
import json
import threading
import time
from uuid import uuid4
from ..storage import Conflict,now,read_json,write_json
from .directory_picker import choose_directory

class ProjectLibrary:
    def __init__(self,studio,intake):
        self.studio,self.store,self.intake=studio,studio.store,intake
        self.folder=self.store.state_dir/'project-library'
        self.grants={};self.picker_lock=threading.Lock()

    @staticmethod
    def empty(root):
        if not root.is_dir():raise ValueError('請選擇已存在的空白資料夾')
        if next(root.iterdir(),None) is not None:raise ValueError('所選資料夾不是空白，請改選空白資料夾；不會覆蓋原有內容')

    def pick(self):
        if not self.picker_lock.acquire(blocking=False):raise Conflict('已有資料夾選擇視窗開啟')
        try:
            selected=choose_directory()
            if not selected:return None
            root=Path(selected).resolve();self.empty(root)
            with self.store.lock:
                if root in self.store.project_roots().values():raise Conflict('此資料夾已登記為專案')
                self.grants={key:value for key,value in self.grants.items() if value['expires']>time.monotonic()}
                token=uuid4().hex;self.grants[token]=dict(root=root,expires=time.monotonic()+900)
            return dict(folder_token=token,path=str(root),name=root.name)
        finally:self.picker_lock.release()

    def create(self,token,name,operation_id):
        name=name.strip()
        if not name or len(name)>120 or any(ord(c)<32 for c in name):raise ValueError('請填寫 1～120 字的專案名稱')
        with self.store.lock:
            grant=self.grants.get(token)
            if not grant or grant['expires']<time.monotonic():raise ValueError('資料夾選擇已失效，請重新選擇')
            root=grant['root']
            if root.resolve()!=root:raise ValueError('資料夾位置已變更，請重新選擇')
            identifier='PROJECT_'+operation_id
            registry=self.folder/'registry.json'
            saved=read_json(registry) if registry.exists() else dict(projects=[])
            previous=next((p for p in saved['projects'] if p['root']==str(root)),None)
            if previous:
                if previous['id']==identifier and previous['name']==name:return self.intake.project_info(identifier)
                raise Conflict('此資料夾已建立專案，請從專案卡片開啟')
            if identifier in self.store.project_roots():raise Conflict('新建識別碼已使用，請重新開啟新建視窗')
            metadata=dict(id=identifier,name=name,kind='user',entries={},created_at=now(),creation_operation=operation_id)
            if (root/'project.json').exists():
                partial=read_json(root/'project.json')
                if partial.get('id')!=identifier or partial.get('name')!=name or partial.get('creation_operation')!=operation_id:raise Conflict('資料夾內容已改變，請重新選擇')
            else:
                self.empty(root)
                self.store.initialize_project(root,metadata)
            saved['projects'].append(dict(id=identifier,root=str(root),name=name,created_at=metadata['created_at']))
            write_json(registry,saved)
            (self.folder/'README.md').write_text('# Local project library\n\nOwner: application runtime. registry.json maps portable project IDs to user-selected absolute folders. Native folder grants exist only in memory until confirmation. Project sources, revisions and outputs remain in their selected folders.\n\nKeep this registry with the workspace databases when backing up the application. Missing folders are reported, never recreated or silently redirected. Project session hints are kept in workflows/project-session inside each project.\n',encoding='utf-8')
            return self.intake.project_info(identifier)

    def resume(self,identifier):
        project=self.intake.project_info(identifier)
        if not project:raise ValueError('此專案已封存')
        current=self.studio.current(identifier);scene=current['scene'];root=self.studio.root(identifier)
        session_path=root/'workflows/project-session/intake.json'
        session=read_json(session_path) if session_path.exists() else None
        job=None;route=project.get('route','glb')
        if route=='glb' and project.get('configured'):
            if session and session.get('job_id'):job=self.studio.jobs.get(session['job_id'])
            ready=not job or job['status']=='completed'
            return dict(project=project,step=7 if ready else 0,route=route,job=job,
                        base_revision=current['revision'],status='原模型出圖／網站' if ready else '正在準備原模型',
                        error=job.get('error') if job else None)
        if session and not session.get('adopted_job_id'):
            route=session['route']
            if session.get('job_id'):job=self.studio.jobs.get(session['job_id'])
            else:
                for candidate in self.studio.jobs.list(identifier):
                    if candidate['operation']!='studio.prepare' or candidate['created_at']<session['created_at']:continue
                    packet=read_json(self.store.state_dir/'jobs'/candidate['id']/'request.json')
                    source=packet['parameters']['source']
                    if source.get('preview_only'):continue
                    if source.get('plan'):
                        path=(root/source['plan']).resolve()
                        if path.is_relative_to(root) and read_json(path)['source']['path']==session.get('source_path'):
                            job=candidate;break
            return dict(project=project,step=0,route=route,job=job,base_revision=session.get('base_revision'),status='正在準備模型' if job and job['status'] in ('queued','running') else '匯入待確認',error=job.get('error') if job else None)
        if scene:
            runs=[r for r in self.workflows(identifier) if r.get('quality') and r.get('revision')==current['revision']]
            outputs=[o for o in self.studio.outputs(identifier) if not o['stale']]
            run=runs[-1] if runs else None
            step=4 if outputs or run else 1
            hint=root/'workflows/project-session/view.json'
            if hint.exists():
                view=read_json(hint)
                if view.get('revision')==current['revision'] and view.get('step') in (1,2,3,4,5,6):step=view['step']
            return dict(project=project,step=step,route=route,job=None,base_revision=current['revision'],status='03 整合輸出' if step==4 else '02 編輯',error=run.get('error') if run else None)
        image=self.intake.images.current(identifier)
        plan=self.intake.plans.current(identifier)
        route='image' if image else 'dxf' if plan else route
        # Legacy queued GLB imports had only the application-level pointer.
        pointer=self.intake.folder/'current.json'
        if pointer.exists():
            previous=read_json(pointer)
            if previous.get('project_id')==identifier and previous.get('job_id'):job=self.studio.jobs.get(previous['job_id'])
        return dict(project=project,step=0,route=route if image or plan or job else 'choose',job=job,base_revision=None,status='平面待確認' if plan else '圖片待辨識' if image else '01 尚未匯入',error=job.get('error') if job else None)

    def workflows(self,identifier):
        with self.studio.jobs.connect() as db:
            rows=db.execute('SELECT data FROM studio_workflows WHERE project_id=?',(identifier,)).fetchall()
        # Coordinator.get can advance an authorized pending graph. Listing cards
        # must only read durable records, never resume a graph or submit a job.
        return sorted((json.loads(row[0]) for row in rows),key=lambda r:r.get('created_at',''))

    def cards(self):
        cards=[]
        registry=self.folder/'registry.json'
        registered=read_json(registry).get('projects',[]) if registry.exists() else []
        for identifier,root in self.store.project_roots().items():
            fallback=next((p for p in registered if p['id']==identifier),{})
            try:
                metadata=read_json(root/'project.json')
                if metadata.get('studio_archived'):continue
                state=self.resume(identifier)
                files=[root/'project.json',root/'workflows/interior-studio/current.json',root/'workflows/plan-import/current.json',root/'workflows/plan-import/image-current.json',root/'workflows/project-session/intake.json',root/'workflows/project-session/view.json']
                updated=max(p.stat().st_mtime for p in files if p.exists())
                thumbnail=None
                if state['step']!=0:
                    images=[o for o in self.studio.outputs(identifier) if not o['stale']]
                    if images:
                        o=next((o for o in images if o['kind']=='still'),images[0]);thumbnail=f'/api/studio/projects/{identifier}/files/{o["job_id"]}/{o["thumbnail"]}'
                if not thumbnail:
                    image=self.intake.images.current(identifier)
                    if image:thumbnail=f'/api/studio/projects/{identifier}/image-plans/{image["id"]}/image'
                cards.append(dict(**state['project'],path=str(root),status=state['status'],error=state['error'],updated_at=updated,thumbnail=thumbnail,available=True))
            except (FileNotFoundError,OSError,ValueError) as exc:
                cards.append(dict(id=identifier,name=fallback.get('name',identifier),path=str(root),status='資料夾或內容無法讀取',error=str(exc),updated_at=0,thumbnail=None,available=False))
        return sorted(cards,key=lambda c:c['updated_at'],reverse=True)

    def save_view(self,identifier,revision,step):
        if self.studio.current(identifier)['revision']!=revision:raise Conflict('設計已變更，不保存過期頁面位置')
        write_json(self.studio.root(identifier)/'workflows/project-session/view.json',dict(revision=revision,step=step))
