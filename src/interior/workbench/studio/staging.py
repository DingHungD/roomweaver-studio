"""Revision-bound decor and lighting placements using actual model supports.

Geometry proposes bounded positions; the existing Agent/catalog batch selects
real assets. No project IDs, client scripts or fabricated catalog URLs.
"""
import copy
import math
import re
from typing import Literal
from uuid import NAMESPACE_URL, uuid5
from pydantic import Field
from .models import Strict, ConceptFurniture, Scene, StudioLight
from .asset_matching import preview_dimensions
from .asset_batch import BatchRequest
from .handoff import read_glb
from ..storage import Conflict, read_json, write_json
from ...visualization.concept_geometry import CATALOG


class StageRequest(Strict):
    base_revision: str = Field(pattern=r'^[a-f0-9]{32}$')
    operation_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,100}$')
    kind: Literal['decor','lighting']
    room_ids: list[str] = Field(default_factory=list,max_length=100)
    description: str = Field(default='',max_length=1500)
    ceiling_height: float = Field(default=2.7,ge=2.1,le=5)
    optional_lamps: bool = False
    model: str | None = None


class StageApply(Strict):
    base_revision: str = Field(pattern=r'^[a-f0-9]{32}$')
    selected_ids: list[str] = Field(default_factory=list,max_length=30)

class StageRetry(Strict):
    base_revision: str = Field(pattern=r'^[a-f0-9]{32}$')
    operation_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,100}$')


def world_bounds(scene, gltf):
    result={}
    concepts={f['id']:f for f in scene.get('concept_furniture',[])}
    for g in scene['groups']:
        if g['deleted']:continue
        f=concepts.get(g['id'])
        b=([-f['size'][0]/2,-f['size'][1]/2,0],[f['size'][0]/2,f['size'][1]/2,f['size'][2]]) if f else preview_dimensions(gltf,g['children'],return_bounds=True)
        if not b:continue
        a=math.radians(g.get('rotation',0));ca,sa=math.cos(a),math.sin(a)
        px,py,pz=g.get('rotation_pivot',[0,0,0]);tx,ty,tz=g['translation']
        corners=[(ca*(x-px)-sa*(y-py)+px+tx,sa*(x-px)+ca*(y-py)+py+ty,z+tz) for x in (b[0][0],b[1][0]) for y in (b[0][1],b[1][1]) for z in (b[0][2],b[1][2])]
        result[g['id']]=([min(p[i] for p in corners) for i in range(3)],[max(p[i] for p in corners) for i in range(3)])
    return result


def propose(scene, bounds, body):
    bounds=copy.deepcopy(bounds)
    plan=[dict(id=g['id'],name=g['name'],lo=bounds[g['id']][0],hi=bounds[g['id']][1]) for g in scene['groups'] if not g['deleted'] and g['id'] in bounds and not re.search(r'exterior|outside|外部|室外',g['name'],re.I)]
    groups={g['id']:g for g in scene['groups'] if not g['deleted']}
    room_for={g['id']:next((o['room_id'] for o in scene['objects'] if o['id'] in g['children']),None) for g in groups.values()}
    if set(body.room_ids)-{r['id'] for r in scene['rooms']}:raise ValueError('未知空間')
    selected=lambda gid:not body.room_ids or room_for[gid] in body.room_ids
    floors=[gid for gid,g in groups.items() if gid in bounds and selected(gid) and re.search(r'floor|地板|地坪',g['name'],re.I) and not re.search(r'exterior|outside|外部|室外',g['name'],re.I)]
    items=[];notes=[];lights=[];ids={g['id'] for g in scene['groups']}
    def add(asset,gid,position,size=None,suffix=''):
        identifier='concept-'+uuid5(NAMESPACE_URL,f'studio-{body.kind}:{gid}:{asset}:{suffix}').hex
        if identifier in ids or len(items)>=24:return
        size=size or CATALOG[asset]['size']
        item=ConceptFurniture(id=identifier,name=CATALOG[asset]['name']+' · '+groups[gid]['name'][:65],asset=asset,size=size).model_dump(mode='json')
        lo=[position[0]-size[0]/2,position[1]-size[1]/2,position[2]];hi=[position[0]+size[0]/2,position[1]+size[1]/2,position[2]+size[2]]
        # Positive-volume collision; touching the support is permitted.
        for other,(a,b) in bounds.items():
            if other==gid:continue
            if all(min(hi[i],b[i])-max(lo[i],a[i])>.012 for i in range(3)):
                notes.append(item['name']+'：候選位置與 '+groups[other]['name']+' 重疊，已略過。');return
        items.append(dict(id=identifier,furniture=item,position=position,room_id=room_for[gid],support_id=gid,
            description=f'{CATALOG[asset]["name"]}，完整單件物品。占位尺寸為可用範圍上限，可等比例適配；保持用途。'+body.description))
        bounds[identifier]=(lo,hi);groups[identifier]={'name':item['name']}
        if asset in ('ceiling_light','floor_lamp'):
            position=[0,0,-.03] if asset=='ceiling_light' else [0,0,size[2]*.7]
            lights.append(StudioLight(id='light-'+identifier,name=item['name']+' 光源',kind='AREA' if asset=='ceiling_light' else 'POINT',position=position,
                power=120 if asset=='ceiling_light' else 45,size=.3 if asset=='ceiling_light' else .15,color=[1,.88,.72],group_id=identifier,origin='proposal').model_dump(mode='json'))
    if body.kind=='lighting':
        notes.append(f'天花燈具採距地板 {body.ceiling_height:g}m 的設定高度；請依實際天花微調，這不是自動量測結果。')
        for gid in floors:
            lo,hi=bounds[gid];w,d=hi[0]-lo[0],hi[1]-lo[1]
            if min(w,d)<1:continue
            nx=min(2,max(1,math.ceil(w/4)));ny=min(2,max(1,math.ceil(d/4)))
            for x in range(nx):
                for y in range(ny):add('ceiling_light',gid,[lo[0]+w*(x+.5)/nx,lo[1]+d*(y+.5)/ny,hi[2]+body.ceiling_height-.12],suffix=f'{x}-{y}')
        old=scene.get('lighting_setup',{}).get('lights',[])
        if not any(l['kind']=='SUN' and l['enabled'] for l in old):
            lights.append(StudioLight(id='staging-daylight',name='室外日光（示意方向）',kind='SUN',position=[0,0,8],rotation=[.55,-.45,-.6],power=1.5,color=[1,.96,.9],size=1,origin='proposal').model_dump(mode='json'))
        windows=[gid for gid,g in list(groups.items()) if gid in room_for and selected(gid) and gid in bounds and re.search(r'window|窗',g['name'],re.I)]
        if not windows:notes.append('未辨識到窗戶：已提供室外日光與天空環境，實際能否入室仍取決於模型開口；不穿牆補亮。')
        notes.append('室外採天空環境＋日光；非基地日照分析、未下載HDRI。模型本身不保證發光，所有新增燈具都有獨立綁定光源。')
        if body.optional_lamps:
            for gid,g in list(groups.items()):
                if gid not in room_for or not selected(gid) or gid not in bounds or not re.search('sofa|沙發',g['name'],re.I):continue
                lo,hi=bounds[gid];x=hi[0]+.3;y=(lo[1]+hi[1])/2
                support=next((f for f in floors if bounds[f][0][0]+.23<x<bounds[f][1][0]-.23 and bounds[f][0][1]+.23<y<bounds[f][1][1]-.23),None)
                if support:add('floor_lamp',support,[x,y,bounds[support][1][2]],suffix=gid)
    else:
        recipes=[(r'cooker|cooktop|爐具|爐台','cookware'),(r'sink|水槽','tableware'),(r'basin|洗手','soap'),(r'desk|書桌','books'),(r'dining|\btable\b|餐桌','vase'),(r'coffee|茶几','books'),(r'bedside|床頭','vase')]
        for gid,g in list(groups.items()):
            if gid not in room_for or not selected(gid) or gid not in bounds:continue
            if re.search(r'chair|椅',g['name'],re.I):continue
            asset=next((a for pattern,a in recipes if re.search(pattern,g['name'],re.I)),None)
            if not asset:continue
            lo,hi=bounds[gid];size=CATALOG[asset]['size'];w,d=hi[0]-lo[0],hi[1]-lo[1]
            if min(w-size[0],d-size[1])<.1 or not .35<hi[2]<1.4:
                notes.append(g['name']+'：沒有足夠或合理高度的檯面，略過裝飾。');continue
            add(asset,gid,[lo[0]+size[0]/2+.06,lo[1]+size[1]/2+.06,hi[2]+.01])
        for gid,g in list(groups.items()):
            if gid not in room_for or not selected(gid) or gid not in bounds or not re.search(r'sofa|沙發',g['name'],re.I):continue
            lo,hi=bounds[gid];width=min(1.6,hi[0]-lo[0]);x=(lo[0]+hi[0])/2;y=lo[1]-.6
            support=next((f for f in floors if bounds[f][0][0]+width/2<x<bounds[f][1][0]-width/2 and bounds[f][0][1]+.5<y<bounds[f][1][1]-.5),None)
            if support:add('rug',support,[x,y,bounds[support][1][2]+.003],[width,1,.015],suffix=gid)
            else:notes.append(g['name']+'：前方沒有可確認的完整地板範圍，未放地毯。')
        notes.append('裝飾依檯面與地板包圍盒安排；不會憑空建立空間。不代表精確表面支撐、人體動線或擬真驗收，請在2D／3D核對。')
    if not items:notes.append('沒有新的可用位置：請核對物件名稱、空間歸屬及是否已配置；已建立項目不會重複加入。')
    return dict(items=items,lights=lights,notes=notes,kind=body.kind,plan=plan)


class Staging:
    def __init__(self,studio,batches):self.studio,self.batches=studio,batches
    def folder(self,project):return self.studio.folder(project)/'staging'
    def retry(self,project,identifier,body):
        with self.batches.automation.lock,self.studio.store.lock:
            proposal=self.get(project,identifier);path=self.folder(project)/identifier/'adoption.json'
            adopted=read_json(path);previous=self.batches.get(project,adopted['batch_id'])
            current=self.studio.current(project)
            if previous['status'] in ('queued','running','matching','applying','stopping'):raise Conflict('目前配置仍在進行中')
            failed={i['group_id'] for i in previous['items'] if i.get('placement',{}).get('status')!='installed'}
            settings=copy.deepcopy(previous['settings'])
            settings.update(base_revision=body.base_revision,operation_id=body.operation_id)
            for g in current['scene']['groups']:
                if not g['deleted']:settings.setdefault('overrides',{}).setdefault(g['id'],{})['enabled']=g['id'] in failed
            batch=self.batches.start(project,BatchRequest.model_validate(settings))
            adopted.setdefault('previous_batches',[]).append(adopted['batch_id']);adopted['batch_id']=batch['id'];write_json(path,adopted)
            return batch
    def preview(self,project,body):
        current=self.studio.current(project)
        identifier=uuid5(NAMESPACE_URL,project+':staging:'+body.operation_id).hex
        path=self.folder(project)/identifier/'proposal.json'
        if path.exists():
            existing=read_json(path)
            if existing['request']!=body.model_dump():raise Conflict('相同操作識別碼已用於另一提案')
            return existing
        if current['revision']!=body.base_revision:raise Conflict('請先保存最新設計')
        scene=current['scene'];gltf=read_glb(self.studio.root(project)/'runs/interior-studio'/scene['model_id']/'model.glb')
        result=propose(scene,world_bounds(scene,gltf),body)
        result.update(id=identifier,request=body.model_dump(),base_revision=body.base_revision)
        write_json(path,result);write_json(self.folder(project)/(body.kind+'-current.json'),dict(id=identifier))
        return result
    def get(self,project,identifier):
        if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('提案識別碼無效')
        return read_json(self.folder(project)/identifier/'proposal.json')
    def current(self,project,kind):
        path=self.folder(project)/(kind+'-current.json')
        if not path.exists():return None
        result=self.get(project,read_json(path)['id'])
        adoption=self.folder(project)/result['id']/'adoption.json'
        if adoption.exists():
            record=read_json(adoption);result['adoption']=record
            if record.get('batch_id'):result['batch']=self.batches.get(project,record['batch_id'])
        return result
    def apply(self,project,identifier,body):
        with self.batches.automation.lock,self.studio.store.lock:
            proposal=self.get(project,identifier);path=self.folder(project)/identifier/'adoption.json'
            if len(set(body.selected_ids))!=len(body.selected_ids) or set(body.selected_ids)-{i['id'] for i in proposal['items']}:raise ValueError('選取項目不屬於提案')
            adopted=read_json(path) if path.exists() else None
            if adopted and adopted['selected_ids']!=body.selected_ids:raise Conflict('此提案已採用不同選項，請重新預覽')
            if adopted and adopted.get('batch_id'):return dict(revision=self.studio.current(project),batch=self.batches.get(project,adopted['batch_id']))
            current=self.studio.current(project)
            if not adopted:
                if current['revision']!=body.base_revision or proposal['base_revision']!=body.base_revision:raise Conflict('提案已過期，請重新預覽')
                latest=self.batches.current(project)
                if latest and latest['status'] in ('queued','running','stopping','matching','applying'):raise Conflict('請先等候目前配置完成')
                scene=copy.deepcopy(current['scene'])
                for item in proposal['items']:
                    if item['id'] not in body.selected_ids:continue
                    f=item['furniture'];scene.setdefault('concept_furniture',[]).append(f)
                    scene['groups'].append(dict(id=f['id'],name=f['name'],children=[p['id'] for p in f['parts']],translation=item['position'],rotation=0,deleted=False,method='concept',editor_kind='decor' if proposal['kind']=='decor' else 'furniture'))
                    scene['objects'] += [dict(id=p['id'],name=f['name']+' / '+p['name'],room_id=item['room_id'],material={}) for p in f['parts']]
                if proposal['kind']=='lighting':
                    setup=scene.setdefault('lighting_setup',{})
                    existing=setup.setdefault('lights',[]);known={l['id'] for l in existing}
                    existing += [l for l in proposal['lights'] if l['id'] not in known and (not l['group_id'] or l['group_id'] in body.selected_ids)]
                    setup.update(enabled=True,mode='day')
                current=self.studio.save(project,Scene.model_validate(scene).model_dump(mode='json'),body.base_revision)
                adopted=dict(revision=current['revision'],selected_ids=body.selected_ids,batch_id=None);write_json(path,adopted)
            if current['revision']!=adopted['revision']:raise Conflict('配置已另外修改，請重新預覽；已建立的物件保留')
            if not body.selected_ids:return dict(revision=current,batch=None)
            overrides={g['id']:dict(enabled=g['id'] in body.selected_ids) for g in current['scene']['groups'] if not g['deleted']}
            for item in proposal['items']:
                if item['id'] in body.selected_ids:overrides[item['id']].update(description=item['description'],category='light' if proposal['kind']=='lighting' else 'other')
            batch=self.batches.start(project,BatchRequest(base_revision=current['revision'],operation_id='staging-'+identifier,model=proposal['request']['model'],overrides=overrides,auto_apply=True))
            adopted['batch_id']=batch['id'];write_json(path,adopted)
            return dict(revision=current,batch=batch)
