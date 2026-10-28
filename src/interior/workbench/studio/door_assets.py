"""Door-part catalog matching and validated, revision-bound asset proposals.

Door geometry remains owned by the opening assembly. Catalog leaves are fitted
inside that assembly, not substituted as unrelated furniture.
"""
import copy
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal
from uuid import uuid4
from pydantic import Field
from .models import Strict
from ..storage import read_json, write_json, Conflict

class DoorMatch(Strict):
    base_revision: str = Field(pattern=r'^[a-f0-9]{32}$')
    opening_id: str
    part: Literal['frame','leaf-0','leaf-1']
    kind: Literal['model','material']
    description: str = Field(default='',max_length=2000)
    model: str | None = None

class DoorSelection(Strict):
    base_revision: str = Field(pattern=r'^[a-f0-9]{32}$')
    asset_id: str
    accept_license: bool = False
    accept_paid: bool = False

def resolve(scene,root):
    """Only server-issued bundles can supply local file paths to Blender."""
    from .service import digest
    scene=copy.deepcopy(scene)
    for control in scene.get('door_controls',[]):
        files={}
        for part,binding in control.get('assets',{}).items():
            key=binding['bundle']
            if not re.fullmatch('[a-f0-9]{32}',key):raise ValueError('無效門素材識別碼')
            folder=Path(root)/'workflows/interior-studio/door-assets'/key
            packet=read_json(folder/'bundle.json');path=folder/'asset.blend'
            if digest(path)!=packet['sha256'] or packet['reference']!=binding['reference'] or packet['opening_id']!=control['opening_id'] or packet['part']!=part:
                raise ValueError('門素材來源或雜湊不符')
            files[part]=dict(path=str(path),kind=packet['reference']['kind'])
        control['_asset_files']=files
    return scene

class DoorAssets:
    def __init__(self,studio,agents):
        self.studio,self.agents=studio,agents
        self.running=set()
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='door-assets')
    def folder(self,p):return self.studio.folder(p)/'door-assets'
    def path(self,p,key):
        if not re.fullmatch('[a-f0-9]{32}',key):raise ValueError('無效門素材識別碼')
        return self.folder(p)/key
    def pointer(self,p,opening,part):return self.folder(p)/('current-'+hashlib.sha256((opening+'/'+part).encode()).hexdigest()+'.json')
    def current(self,p,opening,part):
        path=self.pointer(p,opening,part)
        return self.get(p,read_json(path)['id']) if path.exists() else None
    def start(self,p,body):
        from .opening_details import source_openings
        current=self.studio.current(p)
        if current['revision']!=body.base_revision:raise Conflict('請先保存設計再配對')
        scene=current['scene'];control=next((c for c in scene['door_controls'] if c['opening_id']==body.opening_id and not c['deleted']),None)
        if not control or not control['kind']:raise ValueError('請先設定門種類')
        if body.part!='frame' and (control['kind']=='frame' or body.part=='leaf-1' and control['kind']=='single'):raise ValueError('此門沒有指定門片')
        if body.part=='frame' and body.kind=='model':raise ValueError('門框保留洞口結構，請配對門框材質；模型配對請選擇門片')
        source=source_openings(self.studio.root(p),self.studio.model(p,scene['model_id']))
        door=next((d for d in source['items']+scene.get('manual_doors',[]) if d['id']==body.opening_id),None)
        if not door:raise ValueError('門洞來源不存在')
        import math
        width=control.get('assembly_width') or math.dist(*door['points'])
        n=2 if control['kind'] in ('double','folding','sliding') else 1
        context=dict(group=dict(id=body.opening_id,name=door['name']+' '+body.part,children=[],deleted=False,method='door_part',asset_requirements=dict(purpose='door',dimension_source='confirmed',dimensions=[(width-.08)/n,.035,door['height']-.052],evidence='既有門洞與開門設定')),parts=[],concept=None,
            dimensions_metres=[(width-.08)/n,.035,door['height']-.052],door_control=control,
            search_guidance='搜尋木質門片；可列可拆分門框與門片的門模型。禁止整個牆面或房間，模型下載後必須擷取單門片；保留洞口、開向與種類。不要把毫米尺寸或原門顏色加到搜尋詞。')
        key=uuid4().hex
        payload=dict(kind=body.kind,description=body.description,context=context,opening_id=body.opening_id,part=body.part,base_revision=body.base_revision)
        folder=self.path(p,key);write_json(folder/'input.json',payload)
        write_json(self.pointer(p,body.opening_id,body.part),dict(id=key))
        self.agents.start('asset_match',body.model or 'gpt-6-sol',dict(payload,result_path=str(folder/'result.json')),identifier=key)
        return dict(id=key,status='running')
    def get(self,p,key):
        folder=self.path(p,key);packet=read_json(folder/'input.json')
        return dict(self.agents.get(key),target=packet)
    def select(self,p,key,body):
        from . import blenderkit_client as catalog
        current=self.studio.current(p);result=self.get(p,key);target=result['target']
        if body.base_revision!=current['revision'] or target['base_revision']!=body.base_revision:raise Conflict('設計已變更，請重新配對')
        candidate=next((c for c in result.get('candidates',[]) if c['asset_id']==body.asset_id),None)
        if result['status']!='passed' or not candidate:raise ValueError('候選尚未完成')
        from .asset_quality import assess
        quality=assess(target['context'],candidate,target['kind'])
        if quality['status']=='blocked':raise ValueError('用途檢查未通過：'+'；'.join(quality['reasons']))
        if candidate['kind']!=target['kind']:raise ValueError('候選素材種類不符')
        if not body.accept_license or not candidate['is_free'] and not body.accept_paid:raise ValueError('請確認授權及付費下載權限')
        folder=self.path(p,key)
        # One in-flight installation per search; clicking twice must not download twice.
        with self.studio.store.lock:
            state_path=folder/'selection.json'
            if (p,key) in self.running:return read_json(state_path)
            state=dict(id=key,status='running',phase='下載素材並檢查門片適配與開門路徑')
            write_json(state_path,state);self.running.add((p,key))
        self.executor.submit(self._prepare,p,key,copy.deepcopy(current),target,candidate)
        return state
    def _prepare(self,p,key,current,target,candidate):
        from . import blenderkit_client as catalog
        from .door_collision import check_poses
        from .opening_details import source_openings
        folder=self.path(p,key);bundle=uuid4().hex;asset_dir=self.path(p,bundle)
        try:
            asset_dir.mkdir(parents=True,exist_ok=True)
            proof=catalog.download(candidate,asset_dir/'asset.blend',bundle)
            reference={k:candidate[k] for k in ('asset_id','version_id','url','name','kind','license','is_free')}
            reference.update(task_id=key,status='applied')
            write_json(asset_dir/'bundle.json',dict(sha256=proof['sha256'],reference=reference,opening_id=target['opening_id'],part=target['part']))
            scene=copy.deepcopy(current['scene']);control=next(c for c in scene['door_controls'] if c['opening_id']==target['opening_id'])
            control.setdefault('assets',{})[target['part']]=dict(bundle=bundle,reference=reference)
            # A catalog material must not be immediately hidden by a legacy tint.
            control.setdefault('materials',{}).pop(target['part'],None)
            model=self.studio.model(p,scene['model_id']);source=source_openings(self.studio.root(p),model)
            before=check_poses(self.studio.root(p),model,current['scene'],source)
            report=check_poses(self.studio.root(p),model,scene,source)
            row=next((r for r in report['items'] if r['id']==target['opening_id']),None)
            old=next((r for r in before['items'] if r['id']==target['opening_id']),{})
            if not row or row.get('status')!='prepared' or row.get('asset_errors'):raise ValueError('門素材無法建立：'+str((row or {}).get('asset_errors') or report.get('remaining')))
            if row.get('opening',{}).get('state')=='blocked' or abs(row.get('opening',{}).get('angle',0))+.1<abs(old.get('opening',{}).get('angle',0)):
                raise ValueError('候選使開門路徑受阻或開啟角度變小；保留原門，請改選備選')
            write_json(folder/'proposal.json',dict(scene=scene,base_revision=current['revision']))
            write_json(folder/'selection.json',dict(id=key,status='completed',phase='門素材與開門路徑檢查完成，待套用',report=row))
        except Exception as exc:write_json(folder/'selection.json',dict(id=key,status='failed',phase='保留原門',error=str(exc)))
        finally:self.running.discard((p,key))
    def status(self,p,key):
        path=self.path(p,key)/'selection.json'
        state=read_json(path) if path.exists() else None
        if state and state['status']=='running' and (p,key) not in self.running:
            state=dict(id=key,status='failed',phase='保留原門',error='服務重啟中斷檢查，請重新選擇候選重試');write_json(path,state)
        return state
    def adopt(self,p,key,base):
        with self.studio.store.lock:
            if self.status(p,key)['status']!='completed':raise ValueError('門素材尚未通過檢查')
            packet=read_json(self.path(p,key)/'proposal.json')
            if base!=packet['base_revision']:raise Conflict('設計已變更，未覆蓋新編輯')
            saved=self.studio.save(p,packet['scene'],base)
            write_json(self.path(p,key)/'selection.json',dict(id=key,status='adopted',phase='已保存門素材修訂',revision=saved['revision']))
            return saved
