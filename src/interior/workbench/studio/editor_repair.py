"""Explicit, revision-bound repair of one unfinished editor item.

No cleanup, source overwrite, silent model fallback, or successful dismissal on
the strength of model prose. Asset repair reuses the measured replacement loop.
"""
import copy
import json
import threading
import time
from uuid import NAMESPACE_URL, uuid5
from typing import Literal
from pydantic import Field
from .models import Strict, Scene
from ..storage import Conflict, read_json, write_json, now


class EditorRepairRequest(Strict):
    base_revision: str = Field(pattern=r'^[a-f0-9]{32}$')
    operation_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,100}$')
    category: Literal['furniture','decor','lighting','door','viewpoint']
    target_id: str = Field(min_length=1,max_length=100)
    batch_id: str | None = Field(default=None,pattern=r'^[a-f0-9]{32}$')
    task_id: str = ''
    shot_id: str | None = None
    part: Literal['frame','leaf-0','leaf-1'] | None = None
    reason: str = Field(min_length=1,max_length=12000)


def protected(before, after, allowed_door_part=None):
    """Guard known dimensions, required identities, and every existing door pose."""
    for key in ('manual_doors','rooms'):
        if before.get(key,[])!=after.get(key,[]):raise ValueError('修正不可更改門洞位置、尺寸或空間定義')
    for old in before.get('door_controls',[]):
        new=next((c for c in after.get('door_controls',[]) if c['opening_id']==old['opening_id']),None)
        if not new:raise ValueError('修正不可移除必要門')
        for key in ('assembly_width','side','swing','hinge','kind','materials','assets','deleted'):
            if allowed_door_part and old['opening_id']==allowed_door_part[0] and key in ('materials','assets'):
                part=allowed_door_part[1]
                if {k:v for k,v in old.get(key,{}).items() if k!=part}!={k:v for k,v in new.get(key,{}).items() if k!=part}:raise ValueError('修正影響其他門組成材質')
                continue
            if old.get(key) not in (None,'auto') and old.get(key)!=new.get(key):raise ValueError('修正不可更改已確認門尺寸、開向、種類或材質')
    for g in before.get('groups',[]):
        new=next((n for n in after['groups'] if n['id']==g['id']),None)
        if not new or bool(g.get('deleted'))!=bool(new.get('deleted')):raise ValueError('修正不可刪除既有必要物件')
        req=g.get('asset_requirements') or {};new_req=new.get('asset_requirements') or {}
        if req.get('dimension_source') in ('confirmed','envelope') and any(req.get(k)!=new_req.get(k) for k in ('dimension_source','dimensions','purpose')):raise ValueError('修正不可更改用途或確認尺寸來源')


class EditorRepairs:
    def __init__(self,studio,agents,batches):
        self.studio,self.agents,self.batches=studio,agents,batches
        self.lock=threading.RLock();self.running={};self.closed=threading.Event()
        studio.jobs.close_callbacks.append(self.closed.set)

    def folder(self,p):return self.studio.folder(p)/'editor-repairs'
    def path(self,p,key):
        import re
        if not re.fullmatch('[a-f0-9]{32}',key):raise ValueError('修正識別碼無效')
        return self.folder(p)/key/'state.json'
    def get(self,p,key):
        with self.lock:
            state=read_json(self.path(p,key))
            if state['status']=='running' and (p,key) not in self.running:
                state.update(status='interrupted',error='服務已中斷；既有結果保留，請重新核對後重試')
                write_json(self.path(p,key),state)
            # Include persisted trial reasons for old records too. Reading this
            # evidence never starts/resumes an Agent or changes design state.
            if state.get('batch_id') and state['status'] in ('needs_attention','interrupted'):
                from .asset_completion import failure_details
                placement=self.batches.folder(p)/state['batch_id']/'placement.json'
                if placement.exists():
                    payload=read_json(placement.parent/'input.json')
                    target=next((t for t in payload['targets'] if t['group_id']==state['request']['target_id']),None)
                    row=read_json(placement)['items'].get(target['task_id'],{}) if target else {}
                    state['failure_details']=failure_details(row)
            return state
    def records(self,p):
        return [self.get(p,f.parent.name) for f in sorted(self.folder(p).glob('*/state.json'),key=lambda f:f.stat().st_mtime,reverse=True)[:100]]
    def start(self,p,body):
        with self.lock,self.studio.store.lock:
            key=uuid5(NAMESPACE_URL,'editor-repair:'+p+':'+body.operation_id).hex;path=self.path(p,key)
            request=body.model_dump()
            if path.exists():
                if read_json(path.parent/'input.json')!=request:raise Conflict('操作識別碼已用於其他修正')
                return self.get(p,key)
            if any(project==p for project,_ in self.running):raise Conflict('請先等待目前物件修正完成')
            current=self.studio.current(p)
            if current['revision']!=body.base_revision:raise Conflict('請先保存最新編輯再修正')
            # Reject concurrent automatic adoption rather than racing its revisions.
            for f in self.batches.folder(p).glob('*/placement.json'):
                if read_json(f)['status'] in ('matching','applying'):raise Conflict('尚有配置工作，請先等待或停止')
            if body.category in ('furniture','decor','lighting'):
                if not body.batch_id:raise ValueError('缺少原配置批次，請重新讀取未完成清單')
                prior=self.batches.get(p,body.batch_id)
                if not any(r.get('group_id')==body.target_id and body.task_id in (r['task_id'],r.get('candidate_task_id')) for r in prior['items']):raise ValueError('修正目標不屬於此配置批次')
                if any(r.get('group_id')==body.target_id and r.get('placement',{}).get('status')=='installed' for r in prior['items']):raise Conflict('此物件已成功套用，請更新未完成清單；未重複啟動修正')
            state=dict(id=key,status='running',phase='依失敗原因檢查物件',request=request,created_at=now())
            write_json(path.parent/'input.json',request);write_json(path,state)
            t=threading.Thread(target=self.run,args=(p,key,body,current),daemon=True)
            self.running[p,key]=t;t.start();return state

    def update(self,p,key,**changes):
        with self.lock:
            state=read_json(self.path(p,key));state.update(changes);write_json(self.path(p,key),state)
    def wait(self,read,on_progress=None):
        started=time.monotonic();previous=None
        while not self.closed.is_set():
            value=read()
            if time.monotonic()-started>2400:raise ValueError('修正等待逾時；結果與原件保留，請核對既有工作')
            if on_progress and value.get('phase')!=previous:
                previous=value.get('phase');on_progress(value)
            if value['status'] not in ('running','queued','stopping','matching','applying'):return value
            self.closed.wait(1)
        raise ValueError('服務停止，保留修正證據，不自動採用')
    def run(self,p,key,body,current):
        try:
            if body.category in ('furniture','decor','lighting'):
                prior=self.batches.get(p,body.batch_id);settings=copy.deepcopy(prior['settings'])
                selected=body.target_id
                live={g['id'] for g in current['scene']['groups'] if not g.get('deleted')}
                if selected not in live:raise ValueError('目標已刪除或不存在，未啟動修正')
                settings['overrides']={k:v for k,v in settings.get('overrides',{}).items() if k in live}
                for g in (g for g in current['scene']['groups'] if g['id'] in live):
                    settings.setdefault('overrides',{}).setdefault(g['id'],{})['enabled']=g['id']==selected
                override=settings['overrides'][selected]
                override['keep_original']=False
                override['description']=(override.get('description','')+'\n依失敗證據修正：'+body.reason)[-2000:]
                settings.update(base_revision=body.base_revision,operation_id='editor-'+key,room_ids=[],categories=[],model='gpt-6-sol',auto_apply=True,auto_repair=True,procedural_fallback=True)
                from .asset_batch import BatchRequest
                reusable=next((r for r in self.records(p) if r['id']!=key and r['status']=='needs_attention' and r.get('batch_id') and all(r['request'].get(k)==getattr(body,k) for k in ('base_revision','batch_id','task_id','target_id'))),None)
                batch=None
                if reusable:
                    candidate=self.batches.get(p,reusable['batch_id'])
                    if candidate['status']=='paused' and candidate.get('placement_revision')==body.base_revision:
                        self.batches.automation.start(p,candidate['id'],body.base_revision);batch=candidate
                if batch is None:batch=self.batches.start(p,BatchRequest.model_validate(settings))
                self.update(p,key,batch_id=batch['id'],phase='Agent 重新匹配、適配、檢查；保留原件與候選')
                batch=self.wait(lambda:self.batches.get(p,batch['id']),lambda b:self.update(p,key,phase=b.get('phase') or '正在核對修正證據'))
                row=next(r for r in batch['items'] if r['group_id']==selected)
                if row.get('placement',{}).get('status')!='installed':
                    detail=row.get('placement',{}).get('failure_details',[])
                    self.update(p,key,failure_details=detail)
                    reason=row.get('placement',{}).get('error') or batch.get('error') or '修正尚未通過檢查，原件與候選保留'
                    if detail:reason+='\n最近未通過原因：'+detail[0]['reason']
                    raise ValueError(reason)
                saved=self.studio.current(p);protected(current['scene'],saved['scene'])
                group=next(g for g in saved['scene']['groups'] if g['id']==selected)
                proof=dict(group_id=selected,reference=group.get('asset_reference'),generated=group.get('generated_reference'),materials={o['id']:o['material'].get('asset_reference') for o in saved['scene']['objects'] if o['id'] in group['children']})
            else:
                saved,proof=self.geometry(p,key,body,current)
            self.update(p,key,status='completed',phase='實際檢查通過，已同步新修訂',revision=saved['revision'],proof=proof)
        except Exception as exc:self.update(p,key,status='needs_attention',phase='未通過，保留原件與失敗原因',error=str(exc))
        finally:
            with self.lock:self.running.pop((p,key),None)

    def geometry(self,p,key,body,current):
        scene=copy.deepcopy(current['scene'])
        if body.category=='door':
            if body.part:return self.door_material(p,key,body,current)
            from .opening_details import source_openings
            from .door_collision import check_poses
            model=self.studio.model(p,scene['model_id']);source=source_openings(self.studio.root(p),model)
            openings=[o for o in source['items'] if o['role']=='door']+scene.get('manual_doors',[])
            target=next((o for o in openings if o['id']==body.target_id),None)
            if not target:raise ValueError('找不到原門洞，未修正')
            old=next((c for c in scene['door_controls'] if c['opening_id']==body.target_id),dict(opening_id=body.target_id))
            payload=dict(failure=body.reason,openings=[target],controls=[dict(old,allow_width_adjustment=False)],rooms=scene['rooms'],objects=[],collision_context=dict(blend=str(self.studio.root(p)/'runs/interior-studio'/scene['model_id']/'model.blend'),sha256=model['native_sha256'],scene=scene),preserve_directions=True)
            task=self.agents.start('door_design','gpt-6-sol',payload,identifier=uuid5(NAMESPACE_URL,key+':agent').hex)
            self.update(p,key,agent_task_id=task['id'],phase='Agent 依碰撞證據核對門；尺寸與已選開向鎖定')
            task=self.wait(lambda:self.agents.get(task['id']))
            if task['status']!='passed':raise ValueError(task.get('error') or 'Agent 門修正未完成')
            new=next(c for c in task['controls'] if c['opening_id']==body.target_id);new['allow_width_adjustment']=old.get('allow_width_adjustment',False)
            scene['door_controls']=[c for c in scene['door_controls'] if c['opening_id']!=body.target_id]+[new]
            protected(current['scene'],scene)
            report=check_poses(self.studio.root(p),model,scene,source)
            row=next(r for r in report['items'] if r['id']==body.target_id)
            write_json(self.path(p,key).parent/'verification.json',report)
            if row.get('opening',{}).get('state') in ('blocked','limited'):raise ValueError('依已確認尺寸與開向仍受阻；未改門洞或方向。可先手動調整門組 AB 長度後再檢查。')
            if not new.get('kind') or task.get('uncertainties'):raise ValueError('Agent 仍有待確認項目：'+'；'.join(task.get('uncertainties',[])))
            pointer=self.studio.folder(p)/'doors/current-design.json'
            proof=dict(door_id=body.target_id,control=new,model_id=scene['model_id'],resolved_design_task=read_json(pointer)['id'] if pointer.exists() else None)
        else:
            from .viewpoint_repair import apply_plan
            point=next((v for v in scene['viewpoints'] if v['id']==body.target_id),None)
            if not point or not point['shots']:raise ValueError('此觀看點只有全景；請先新增需要修正的效果圖方向')
            shot=next((s for s in point['shots'] if s['id']==body.shot_id),point['shots'][0])
            failures=[]
            for attempt in range(2):
                task=self.agents.start('editor_viewpoint','gpt-6-sol',dict(phase='plan',failure=body.reason,point=point,shot=shot,previous=failures,rooms=scene['rooms'],groups=[dict(id=g['id'],name=g['name'],translation=g['translation']) for g in scene['groups'] if not g['deleted']]),identifier=uuid5(NAMESPACE_URL,key+f':camera:{attempt}').hex)
                self.update(p,key,agent_task_id=task['id'],phase=f'Agent 修正取景並試渲染 {attempt+1}／2')
                task=self.wait(lambda:self.agents.get(task['id']))
                if task['status']!='passed':raise ValueError(task.get('error') or '取景 Agent 未完成')
                draft=apply_plan(scene,point['id'],shot['id'],task['camera_plan'])
                job=self.studio.jobs.submit_studio(p,'render',dict(revision=body.base_revision,quality='preview',editor_scene=draft,editor_point_id=point['id'],agent_model='gpt-6-sol'),'editor-camera-'+key+'-'+str(attempt))
                self.update(p,key,job_id=job['id'],phase='實際低解析出圖，核對裁切與遮擋')
                job=self.wait(lambda:self.studio.jobs.get(job['id']))
                if job['status']!='completed':
                    failures.append(dict(error=job.get('error')));continue
                folder=self.studio.root(p)/job['output'];manifest=read_json(folder/'result.json')
                files=[folder/i['file'] for i in manifest['images'] if i.get('kind')=='still']
                if not files:raise ValueError('取景試圖沒有實際效果圖，未套用')
                review=self.agents.start('editor_viewpoint','gpt-6-sol',dict(phase='review',failure=body.reason,shot=next(v for v in draft['viewpoints'] if v['id']==point['id']),images=[str(f) for f in files]),identifier=uuid5(NAMESPACE_URL,key+f':camera-review:{attempt}').hex)
                review=self.wait(lambda:self.agents.get(review['id']))
                if review['status']=='passed' and review['camera_review']['status']=='pass':scene=draft;break
                failures.append(dict(plan=task['camera_plan'],review=review.get('camera_review'),error=review.get('error')))
            else:raise ValueError('兩輪取景試圖仍未通過；保留原鏡位及試圖證據：'+json.dumps(failures,ensure_ascii=False)[-1800:])
            proof=dict(point_id=point['id'],point=next(v for v in scene['viewpoints'] if v['id']==point['id']))
        with self.studio.store.lock:
            if self.studio.current(p)['revision']!=body.base_revision:raise Conflict('修正期間設計已變更，結果保留，未覆蓋')
            return self.studio.save(p,Scene.model_validate(scene).model_dump(mode='json'),body.base_revision),proof

    def door_material(self,p,key,body,current):
        from .door_assets import DoorAssets,DoorMatch,DoorSelection
        assets=DoorAssets(self.studio,self.agents)
        previous=assets.current(p,body.target_id,body.part)
        kind=(previous or {}).get('target',{}).get('kind','material')
        task=assets.start(p,DoorMatch(base_revision=body.base_revision,opening_id=body.target_id,part=body.part,kind=kind,description=('免費優先，依失敗原因修正：'+body.reason)[-2000:],model='gpt-6-sol'))
        self.update(p,key,agent_task_id=task['id'],phase='Agent 依門素材失敗原因重新配對，檢查安裝與開門掃掠')
        task=self.wait(lambda:assets.get(p,task['id']))
        if task['status']!='passed':raise ValueError(task.get('error') or '門素材配對未完成')
        errors=[]
        for candidate in [c for c in task.get('candidates',[]) if c.get('is_free')][:3]:
            assets.select(p,task['id'],DoorSelection(base_revision=body.base_revision,asset_id=candidate['asset_id'],accept_license=True))
            state=self.wait(lambda:assets.status(p,task['id']))
            if state['status']!='completed':errors.append(state.get('error') or '安裝檢查未通過');continue
            proposal=read_json(assets.path(p,task['id'])/'proposal.json')
            protected(current['scene'],proposal['scene'],(body.target_id,body.part))
            saved=assets.adopt(p,task['id'],body.base_revision)
            control=next(c for c in saved['scene']['door_controls'] if c['opening_id']==body.target_id)
            return saved,dict(door_id=body.target_id,control=control,model_id=saved['scene']['model_id'])
        raise ValueError('門素材免費候選未通過，保留原件：'+'；'.join(errors))
