"""Persisted, bounded house matching using the same per-object candidate contracts."""
import hashlib
import io
import re
from uuid import NAMESPACE_URL, uuid5
from PIL import Image, ImageOps
from pydantic import Field
from .models import Strict
from .asset_matching import object_context, preview_dimensions, run_matching
from ..storage import Conflict, read_json, write_json

TYPES = {'chair':'椅子','bed':'床','cabinet':'櫃子','wall':'牆壁','floor':'地板',
         'sofa':'沙發','table':'桌子','light':'燈具','surface':'門窗／天花材質','other':'其他'}
WORDS = {'chair':r'chair|stool|椅|凳', 'bed':r'\bbed\b|bunk|床',
         'cabinet':r'cabinet|wardrobe|shelf|櫃|架', 'wall':r'wall|牆',
         'floor':r'floor|地板|地坪', 'sofa':r'sofa|couch|沙發',
         'table':r'table|desk|桌', 'light':r'lamp|light|燈'}

class ObjectStyle(Strict):
    enabled: bool = True
    use_global: bool = True
    description: str = Field(default='',max_length=2000)
    image_id: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')
    category: str | None = None

class BatchRequest(Strict):
    base_revision: str = Field(pattern=r'^[a-f0-9]{32}$')
    operation_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,100}$')
    room_ids: list[str] = Field(default_factory=list,max_length=100)
    categories: list[str] = Field(default_factory=list,max_length=20)
    use_global: bool = True
    description: str = Field(default='',max_length=2000)
    image_id: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')
    overrides: dict[str,ObjectStyle] = Field(default_factory=dict,max_length=2000)
    model: str | None = None
    auto_apply: bool = True

def inventory(scene):
    items=[]
    for g in scene['groups']:
        if g['deleted']:continue
        concept=next((f for f in scene.get('concept_furniture',[]) if f['id']==g['id']),None)
        parts=[o for o in scene['objects'] if o['id'] in g['children']]
        label=' '.join([(concept or {}).get('asset',''),g['name'],*[p.get('name','') for p in parts]])
        category=next((k for k,p in WORDS.items() if re.search(p,label,re.I)),'other')
        # Host names may follow generated names ("天花燈具 · floor").
        # The object's own purpose takes priority over its support's category.
        if re.search(r'^(天花燈具|落地燈)|ceiling.light|floor.lamp',g['name'],re.I):category='light'
        if re.search(r'^(花瓶|書籍|鍋具|餐具|洗手用品|洗手乳|地毯|植栽|盆栽)',g['name']):category='other'
        if re.search(r'window|door|ceiling|窗|門|天花',g['name'],re.I) and not re.search(WORDS['light'],label,re.I):category='surface'
        items.append(dict(id=g['id'],name=g['name'],category=category,
            room_ids=sorted({p['room_id'] for p in parts if p['room_id']}),parts=[p['id'] for p in parts]))
    return items

def select_targets(scene,body):
    items=inventory(scene);known={g['id'] for g in items}
    if set(body.overrides)-known:raise ValueError('物件已變更，請重新開啟配置')
    if set(body.categories)-TYPES.keys():raise ValueError('未知家具類型')
    if set(body.room_ids)-{r['id'] for r in scene['rooms']}:raise ValueError('空間已變更')
    selected=[]
    for g in items:
        override=body.overrides.get(g['id'],ObjectStyle())
        category=override.category or g['category']
        if category not in TYPES:raise ValueError('未知家具類型')
        if not override.enabled or (body.categories and category not in body.categories):continue
        if body.room_ids and not set(body.room_ids).intersection(g['room_ids']):continue
        global_on=body.use_global and override.use_global
        description='\n'.join(x for x in [body.description if global_on else '',override.description] if x)
        images=list(dict.fromkeys(x for x in [body.image_id if global_on else None,override.image_id] if x))
        # Structural surfaces are material targets, never replaced with furniture geometry.
        kind='material' if category in ('wall','floor','surface') else 'model'
        for part in g['parts'] if kind=='material' else [None]:
            selected.append(dict(group_id=g['id'],object_id=part,kind=kind,name=g['name'],category=category,
                description=description,image_ids=images))
    if not selected:raise ValueError('這個範圍沒有可配對的物件，請調整範圍或物件勾選')
    if len(selected)>100:raise ValueError('一次最多配對 100 個目標；請縮小空間或類型範圍')
    return selected

class AssetBatch:
    def __init__(self,assets):
        self.assets=assets;self.studio=assets.studio;self.agents=assets.agents
        from .asset_automation import AutoPlacement
        self.automation=AutoPlacement(self)
    def folder(self,project):return self.assets.folder(project)/'batches'
    def upload(self,project,data):
        if len(data)>5*1024**2:raise ValueError('風格圖片上限 5 MB')
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ('PNG','JPEG') or source.width*source.height>25_000_000:raise ValueError('請使用 2500 萬像素內的 PNG／JPG')
                image=ImageOps.exif_transpose(source).convert('RGB');image.thumbnail((1600,1600))
                out=io.BytesIO();image.save(out,format='JPEG',quality=90)
        except (OSError,Image.DecompressionBombError) as exc:raise ValueError('無法讀取風格圖片') from exc
        raw=out.getvalue();identifier=hashlib.sha256(raw).hexdigest()
        path=self.folder(project)/'images'/f'{identifier}.jpg';path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():path.write_bytes(raw)
        return dict(id=identifier)
    def image(self,project,identifier):
        if not re.fullmatch('[a-f0-9]{64}',identifier):raise ValueError('圖片識別碼無效')
        path=self.folder(project)/'images'/f'{identifier}.jpg'
        if not path.is_file():raise ValueError('風格圖片不存在，請重新選取')
        return path
    def get(self,project,identifier):
        if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('批次識別碼無效')
        payload=read_json(self.folder(project)/identifier/'input.json')
        if payload['project_id']!=project:raise ValueError('批次不屬於本案')
        result=self.agents.get(identifier)
        rows=[]
        for target in payload['targets']:
            item=self.assets.get(project,target['task_id'])
            if result['status'] not in ('running','queued','stopping') and item['status'] in ('running','queued'):
                item.update(status='interrupted',error='批次已中斷；此項尚未完成，可重新配對')
                write_json(self.assets.folder(project)/target['task_id']/'result.json',item)
            rows.append(dict(task_id=target['task_id'],group_id=target['group_id'],object_id=target['object_id'],name=target['name'],
                kind=target['kind'],status=item['status'],error=item.get('error'),count=len(item.get('candidates',[])),
                free_count=sum(c['is_free'] for c in item.get('candidates',[]))))
        response=dict(id=identifier,status=result['status'],phase=result.get('phase'),error=result.get('error'),items=rows,settings=payload['settings'])
        return self.automation.decorate(project,identifier,response)
    def current(self,project):
        pointer=self.folder(project)/'current.json'
        return self.get(project,read_json(pointer)['id']) if pointer.exists() else None
    def start(self,project,body):
        with self.automation.lock,self.studio.store.lock:
            current=self.studio.current(project)
            if current['revision']!=body.base_revision:raise Conflict('請先保存最新設計')
            identifier=uuid5(NAMESPACE_URL,'blenderkit-batch:'+project+':'+body.operation_id).hex
            path=self.folder(project)/identifier/'input.json'
            if path.exists():
                if read_json(path)['settings']!=body.model_dump():raise Conflict('同一操作識別碼已使用不同設定')
                return self.get(project,identifier)
            previous=self.current(project)
            if previous and previous['status'] in ('queued','running','stopping','matching','applying'):raise Conflict('已有配置進行中，請等候或停止')
            targets=select_targets(current['scene'],body)
            for i,target in enumerate(targets):
                context=object_context(current['scene'],target['group_id'],target['object_id'])
                context['dimensions_metres']=context['concept']['size'] if context['concept'] else preview_dimensions(
                    self.studio.root(project)/'runs/interior-studio'/current['scene']['model_id']/'model.glb',context['group']['children'])
                task=uuid5(NAMESPACE_URL,identifier+':'+str(i)).hex
                images=[str(self.image(project,x)) for x in target.pop('image_ids')]
                target.update(task_id=task,images=images,context=context,base_revision=body.base_revision,project_id=project,
                    result_path=str(self.assets.folder(project)/task/'result.json'),model=body.model,batch_id=identifier)
            # Validate every target before publishing any child record.
            for target in targets:
                write_json(self.assets.folder(project)/target['task_id']/'input.json',target)
                write_json(self.assets.folder(project)/target['task_id']/'result.json',dict(id=target['task_id'],status='queued'))
                write_json(self.assets.pointer(project,target['group_id']),dict(id=target['task_id']))
            payload=dict(project_id=project,targets=targets,settings=body.model_dump(),result_path=str(path.parent/'result.json'))
            write_json(path,payload);write_json(self.folder(project)/'current.json',dict(id=identifier))
            self.agents.start('asset_batch',body.model,payload,identifier=identifier)
            if body.auto_apply:self.automation.start(project,identifier,body.base_revision)
            return self.get(project,identifier)

def run_batch(client,directory,payload,model,progress,event):
    done=[]
    for i,target in enumerate(payload['targets']):
        progress(f'配對 {i+1}／{len(payload["targets"])}：{target["name"]}')
        from pathlib import Path
        result_path=Path(target['result_path'])
        result=dict(id=target['task_id'],status='running')
        write_json(result_path,result)
        try:
            def match_with_retry(settings):
                for attempt in range(3):
                    progress(f'{i+1}／{len(payload["targets"])} · {target["name"]}：搜尋第 {attempt+1} 次')
                    try:
                        return run_matching(client,result_path.parent,settings,model,progress,event)
                    except Exception as exc:
                        if attempt==2 or not any(word in str(exc).lower() for word in ('serveroverloaded','at capacity','timeout','timed out','429','503')):raise
                        result.setdefault('retries',[]).append(str(exc))
                        write_json(result_path,result)
                        progress('服務暫忙，沿用同一模型重試；不切換供應商')
            result.update(match_with_retry(target))
            # A narrower style query may miss all free assets. Retry with purpose
            # and dimensions intact, relaxing style only, never dropping the target.
            if not any(c.get('is_free') for c in result.get('candidates',[])):
                prior=result.get('candidates',[])
                fallback=dict(target,description=target.get('description','')+'\n保留上述必要機能與尺寸，只放寬顏色風格。以最簡短用途英文主詞搜尋，例如 washing machine、desk chair；不要把顏色、腳數、front等修飾都塞入關鍵字。完整家具不能用零件替代。')
                retry=match_with_retry(fallback)
                merged={c['asset_id']:c for c in [*retry.get('candidates',[]),*prior]}
                result.update(retry,candidates=sorted(merged.values(),key=lambda c:not c.get('is_free')),style_relaxed=True)
            result['status']='passed'
        except Exception as exc:
            result.update(status='failed',error=str(exc))
            write_json(result_path,result)
            progress('已記錄失敗；繼續其他物件')  # also checks stop before another cloud call
        write_json(result_path,result);done.append(result['id'])
    return dict(completed=done,phase='搜尋已完成；逐件核對下載與替換狀態')
