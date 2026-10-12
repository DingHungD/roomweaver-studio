"""Bounded DXF intake and immutable, user-confirmed plan revisions.

Source coordinates remain untouched. Units and semantic assignments are explicit;
this module never infers approved rooms or submits an Agent task.
"""
from collections import Counter
import math
from pathlib import Path
import re
from typing import Literal
from uuid import uuid4

import ezdxf
from pydantic import Field
from .models import Strict
from .service import digest
from ..storage import Conflict, read_json, write_json, now


class Assignment(Strict):
    id: str
    name: str = Field(min_length=1, max_length=100)
    role: Literal['ignore', 'wall', 'floor', 'door', 'window', 'furniture'] = 'ignore'
    height: float = Field(default=2.8, ge=.02, le=12)
    base: float = Field(default=0, ge=0, le=10)
    thickness: float = Field(default=.18, ge=.04, le=1)
    offset: tuple[float, float] = (0, 0)
    host_id: str | None = None
    points: list[tuple[float, float]] | None = Field(default=None, min_length=2, max_length=100)
    design_asset: Literal['sofa','bed','table','desk','chair','cabinet','bunk_bed','cooker','washer','television'] | None = None


class Calibration(Strict):
    start: tuple[float, float]
    end: tuple[float, float]
    metres: float = Field(gt=.01, le=100)
    confirmed: bool = False


class ManualFeature(Strict):
    id: str = Field(pattern=r'^manual-[a-f0-9]{32}$')
    layer: Literal['wall','floor','door','window','furniture']
    kind: Literal['MANUAL'] = 'MANUAL'
    points: list[tuple[float,float]] = Field(min_length=2, max_length=100)
    closed: bool


class PlanSettings(Strict):
    units: Literal['mm', 'cm', 'm', 'inch', 'foot']
    assignments: list[Assignment] = Field(min_length=1, max_length=2000)
    calibration: Calibration | None = None
    reviewed: list[str] = Field(default_factory=list, max_length=500)
    additions: list[ManualFeature] = Field(default_factory=list, max_length=100)
    question_notes: list['QuestionNote'] = Field(default_factory=list, max_length=60)
    source_marks: list['SourceMark'] = Field(default_factory=list, max_length=100)
    dimension_cautions: list['DimensionCaution'] = Field(default_factory=list, max_length=120)
    reconstruction: 'ReconstructionRecord | None' = None
    layout_adoption: 'LayoutAdoption | None' = None


class LayoutAdoption(Strict):
    proposal_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    source_revision: str
    concept_only: bool = False
    remaining_issues: list[str] = Field(default_factory=list,max_length=1000)
    requirements: list[dict] = Field(default_factory=list,max_length=25)
    coverage: list[dict] = Field(default_factory=list,max_length=25)


class QuestionRegion(Strict):
    label: str = Field(min_length=1,max_length=100)
    box: tuple[float,float,float,float]


class QuestionNote(Strict):
    question_id: str
    title: str = Field(min_length=1,max_length=150)
    known: str = Field(max_length=2000)
    ask: str = Field(min_length=1,max_length=2000)
    regions: list[QuestionRegion] = Field(min_length=1,max_length=10)
    answer: str = Field(default='',max_length=4000)


class DimensionAnchor(Strict):
    feature_id: str
    vertex: int = Field(ge=0,le=99)


class SourceMark(Strict):
    id: str = Field(min_length=1,max_length=80)
    start: tuple[float,float]
    end: tuple[float,float]
    description: str = Field(default='',max_length=2000)
    question_id: str | None = None


class DimensionCaution(Strict):
    dimension_id: str
    reason: str = Field(min_length=1,max_length=2000)
    source: str = Field(min_length=1,max_length=500)


class DimensionBinding(Strict):
    dimension_id: str
    start: DimensionAnchor
    end: DimensionAnchor
    axis: Literal['x','y']
    mode: Literal['vertices','opening_width'] = 'vertices'


class ReconstructionRecord(Strict):
    source_revision: str
    orthogonal: Literal[True] = True
    changed_features: int = Field(ge=0,le=2100)
    bindings: list[DimensionBinding] = Field(default_factory=list,max_length=120)
    note: str = Field(max_length=2000)


class RectifyPlan(Strict):
    base_revision: str
    orthogonal_confirmed: Literal[True]
    bindings: list[DimensionBinding] = Field(default_factory=list,max_length=120)


PlanSettings.model_rebuild()


class SavePlan(Strict):
    base_revision: str
    settings: PlanSettings


class BuildPlan(Strict):
    plan_revision: str
    base_revision: str | None = None
    confirmed: bool = False


FACTORS = dict(mm=.001, cm=.01, m=1, inch=.0254, foot=.3048)
ROLES = ('wall', 'floor', 'door', 'window', 'furniture')


def parse_dxf(path):
    """Read bounded ASCII 2D primitives; report all unsupported content."""
    path = Path(path)
    if path.stat().st_size > 10_000_000:
        raise ValueError('DXF 超過 10 MB 上限')
    if path.read_bytes().startswith(b'AutoCAD Binary DXF'):
        raise ValueError('請另存為 ASCII DXF；目前不讀取二進位 DXF')
    try:
        doc = ezdxf.readfile(path)
    except Exception as exc:
        raise ValueError('無法讀取 DXF，請檢查檔案格式') from exc
    features, issues, annotations = [], [], Counter()
    entities = list(doc.modelspace())
    if len(entities) > 2000:
        raise ValueError('此版最多接受 2,000 個模型空間元件，請先整理圖面')
    for i, entity in enumerate(entities):
        kind = entity.dxftype()
        if kind in ('TEXT', 'MTEXT', 'DIMENSION'):
            annotations[kind] += 1
            continue
        reason = None
        points, closed = [], False
        if kind == 'LINE':
            points = [list(entity.dxf.start), list(entity.dxf.end)]
        elif kind == 'LWPOLYLINE':
            closed = bool(entity.closed)
            if any(abs(p[4]) > 1e-9 for p in entity.get_points()):
                reason = '含圓弧 bulge，請先改成受支援的直邊輪廓'
            if entity.dxf.get('const_width',0) or any(p[2] or p[3] for p in entity.get_points()):
                reason = '含多段線寬度，請轉成明確輪廓或無寬度中心線'
            points = [[p[0], p[1], entity.dxf.elevation] for p in entity.get_points()]
        else:
            reason = '尚未支援；圖塊請先 EXPLODE，曲線請先整理成直邊輪廓'
        if tuple(entity.dxf.get('extrusion', (0, 0, 1))) != (0, 0, 1) or entity.dxf.get('thickness', 0):
            reason = '不是世界 XY 平面的 2D 元件'
        if points and (len(points) > 100 or any(not all(math.isfinite(v) and abs(v) < 1e8 for v in p) or abs(p[2]) > 1e-7 for p in points)):
            reason = '非零高程、非有限座標或超過單元件 100 頂點限制'
        if reason:
            issues.append(dict(handle=entity.dxf.handle, layer=entity.dxf.layer, kind=kind, reason=reason))
            continue
        points = [p[:2] for p in points]
        if len(points) > 2 and points[0] == points[-1]:
            points.pop(); closed = True
        if len(points) < 2:
            issues.append(dict(handle=entity.dxf.handle, layer=entity.dxf.layer, kind=kind, reason='有效頂點不足'))
            continue
        features.append(dict(id=f'e-{entity.dxf.handle or i}', layer=entity.dxf.layer, kind=kind, points=points, closed=closed))
    if sum(len(f['points']) for f in features)>20000:
        raise ValueError('平面頂點總數超過 20,000，請先簡化圖面')
    if not features:
        detail='；'.join(f"{x['kind']}：{x['reason']}" for x in issues[:3])
        raise ValueError('沒有受支援的平面直線／多段線。僅支援 ASCII DXF 模型空間的 LINE、直邊 LWPOLYLINE。'+detail)
    unit = {1:'inch', 2:'foot', 4:'mm', 5:'cm', 6:'m'}.get(doc.units)
    return dict(features=features, issues=issues, annotations=dict(annotations), detected_units=unit)


def suggested_settings(parsed):
    assignments = []
    for f in parsed['features']:
        layer = f['layer'].lower()
        role = next((r for r in ROLES if r in re.split(r'[\s_-]+',layer)), 'ignore')
        assignments.append(dict(id=f['id'], name=f['layer']+' · '+f['id'], role=role,
            height={'floor':.12, 'door':2.1, 'window':1.3, 'furniture':.75}.get(role, 2.8),
            base=1 if role=='window' else 0, thickness=.18, offset=[0,0], host_id=None))
    return dict(units=parsed['detected_units'] or 'mm', assignments=assignments)


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])


def convex(points):
    turns = [cross(points[i-1], points[i], points[(i+1)%len(points)]) for i in range(len(points))]
    # A simple convex polygon only. Reject repeated vertices and crossing edges.
    if len(set(map(tuple, points))) != len(points):return False
    for i in range(len(points)):
        a,b=points[i],points[(i+1)%len(points)]
        for j in range(i+2,len(points)):
            if i==0 and j==len(points)-1:continue
            c,d=points[j],points[(j+1)%len(points)]
            if cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0:return False
    return (all(t>=-1e-8 for t in turns) or all(t<=1e-8 for t in turns)) and any(abs(t)>1e-5 for t in turns)


def inside(p, poly):
    values=[cross(poly[i-1],poly[i],p) for i in range(len(poly))]
    return all(v>=-1e-6 for v in values) or all(v<=1e-6 for v in values)


def segments(item):
    p=item['points']
    return list(zip(p,p[1:]+([p[0]] if item['closed'] else [])))


def check_plan(parsed, settings):
    settings = PlanSettings.model_validate(settings).model_dump(mode='json')
    if not parsed.get('image') and any(f['layer']!='furniture' for f in settings['additions']):raise ValueError('DXF 僅開放新增配置家具；固定元件請回來源修改')
    all_features=parsed['features']+settings['additions']
    features = {f['id']:f for f in all_features}
    if len(features)!=len(all_features):raise ValueError('平面元件 ID 重複')
    assignments = settings['assignments']
    if len({a['id'] for a in assignments}) != len(assignments) or set(features) != {a['id'] for a in assignments}:
        raise ValueError('平面設定必須完整對應來源與人工新增元件')
    factor = FACTORS[settings['units']]
    image = parsed.get('image')
    notes=settings['question_notes'];question_ids={q['id'] for q in parsed.get('questions',[])}
    if len({n['question_id'] for n in notes})!=len(notes):raise ValueError('標註疑點不可重複')
    for note in notes:
        if not image or note['question_id'] not in question_ids:raise ValueError('標註必須對應本版圖片疑點')
        for region in note['regions']:
            x0,y0,x1,y1=region['box']
            if not (0<=x0<x1<=image['width'] and 0<=y0<y1<=image['height']):raise ValueError('標註區域超出原圖')
    marks=settings['source_marks']
    if len({m['id'] for m in marks})!=len(marks):raise ValueError('A→B 標記 ID 不可重複')
    for mark in marks:
        if not image or any(not (0<=p[0]<=image['width'] and 0<=p[1]<=image['height']) for p in (mark['start'],mark['end'])):raise ValueError('A→B 端點超出原圖')
        if math.dist(mark['start'],mark['end'])<1:raise ValueError('A→B 端點不可重合')
        if mark['question_id'] and mark['question_id'] not in question_ids:raise ValueError('A→B 必須對應本版問題')
    dimensions={d['id']:d for d in parsed.get('dimensions',[])}
    if any(c['dimension_id'] not in dimensions for c in settings['dimension_cautions']):raise ValueError('尺寸差異必須對應現有尺寸')
    active = []
    errors = [f"{x['kind']} #{x['handle']}（{x['layer']}）：{x['reason']}" for x in parsed['issues']]
    if image:
        calibration=settings['calibration']
        factor=.01  # provisional display only; never passes without calibration
        if not calibration or math.dist(calibration['start'],calibration['end'])<5:
            errors.append('請在原圖上指定至少相距 5 像素的比例尺兩端與實際長度')
        else:
            if any(not (0<=p[0]<=image['width'] and 0<=p[1]<=image['height']) for p in (calibration['start'],calibration['end'])):
                raise ValueError('比例尺端點超出原圖')
            factor=calibration['metres']/math.dist(calibration['start'],calibration['end'])
            if not calibration['confirmed']:errors.append('請確認比例尺；手繪比例不等於精確實測尺寸')
        required={q['id'] for q in parsed.get('questions',[])}
        if not required.issubset(set(settings['reviewed'])):errors.append('請逐項核對辨識疑點，修正或接受為概念模型假設')
    for a in assignments:
        if any(not math.isfinite(v) or abs(v)>100 for v in a['offset']):raise ValueError('移動範圍超過 100 m')
        if a['role']=='ignore':continue
        f=features[a['id']]
        raw=a['points'] if a['points'] is not None else f['points']
        if image and any(not (0<=p[0]<=image['width'] and 0<=p[1]<=image['height']) for p in raw):raise ValueError('元件頂點超出原圖')
        if not image and a['points'] is not None and a['role']!='furniture':raise ValueError('DXF 固定元件請在來源修改頂點；僅配置家具可另存位置')
        if a['design_asset'] and a['role']!='furniture':raise ValueError('通用家具模型僅能用於家具元件')
        points=[[p[0]*factor+a['offset'][0], (image['height']-p[1] if image else p[1])*factor+a['offset'][1]] for p in raw]
        item=dict(a,points=points,closed=f['closed'])
        if any(math.dist(x,y)<.005 for x,y in segments(item)):
            errors.append(a['name']+'：線段短於 5 mm，請檢查尺度')
        if a['role'] in ('floor','furniture') and not f['closed']:
            errors.append(a['name']+'：地板／家具需要封閉輪廓')
        if f['closed'] and not convex(points):
            errors.append(a['name']+'：此版封閉輪廓需為無自交的凸多邊形；凹形請拆成數個凸形')
        if a['role'] in ('door','window') and (f['closed'] or len(points)!=2):
            errors.append(a['name']+'：門窗請以沿牆的單一直線表示開口寬度')
        active.append(item)
    walls=[a for a in active if a['role']=='wall']
    floors=[a for a in active if a['role']=='floor']
    reconstruction=settings.get('reconstruction')
    if reconstruction:
        for wall in walls:
            if any(abs(p[0]-q[0])>1e-7 and abs(p[1]-q[1])>1e-7 for p,q in segments(wall)):
                errors.append(wall['name']+'：修改後不再符合已採用的直角原則，請重新校正')
        items_by_id={a['id']:a for a in active};dimensions={d['id']:d for d in parsed.get('dimensions',[])}
        for binding in reconstruction['bindings']:
            try:
                from .plan_rectify import confirmed_dimension
                if not confirmed_dimension(parsed,dimensions.get(binding['dimension_id'])):raise ValueError('unconfirmed')
                p,q=[items_by_id[binding[k]['feature_id']]['points'][binding[k]['vertex']] for k in ('start','end')]
                expected=dimensions[binding['dimension_id']]['metres'];axis=0 if binding['axis']=='x' else 1
                if expected is None or abs(abs(p[axis]-q[axis])-expected)>1e-6:raise ValueError('constraint changed')
            except (KeyError,IndexError,ValueError):
                errors.append('已綁定尺寸 '+binding['dimension_id']+' 與目前幾何不符，請重新核對端點／校正')
    if not floors:errors.append('至少指定一個封閉地板輪廓，作為室內範圍')
    if not walls:errors.append('至少指定一道牆')
    all_points=[p for a in active for p in a['points']]
    if all_points:
        span=max(max(p[i] for p in all_points)-min(p[i] for p in all_points) for i in (0,1))
        if span<1 or span>100:errors.append('建模範圍需介於 1～100 m，請確認單位與圖面範圍')
    # Openings must have a unique, geometrically compatible host. Missing hosts
    # are blockers, never decorative rectangles that leave a wall uncut.
    for opening in [a for a in active if a['role'] in ('door','window') and len(a['points'])==2]:
        a,b=opening['points'];length=math.dist(a,b)
        if length<.1:errors.append(opening['name']+'：開口寬度不足 0.1 m');continue
        candidates=[]
        for wall in walls:
            if opening['host_id'] and wall['id']!=opening['host_id']:continue
            if wall['closed']:
                if inside(a,wall['points']) and inside(b,wall['points']):candidates.append(wall)
            else:
                from .plan_rectify import straight_runs
                for i,j in straight_runs(wall['points']):
                    p,q=wall['points'][i],wall['points'][j]
                    size=math.dist(p,q)
                    if size<.005:continue
                    u=[(q[i]-p[i])/size for i in (0,1)]
                    def projection(v):return sum((v[i]-p[i])*u[i] for i in (0,1))
                    def distance(v):return abs((v[0]-p[0])*u[1]-(v[1]-p[1])*u[0])
                    if all(-.001<=projection(v)<=size+.001 and distance(v)<.005 for v in (a,b)):
                        candidates.append(wall);break
        if len(candidates)!=1:
            errors.append(opening['name']+'：需對齊且對應唯一牆體，請調整位置或指定宿主牆')
        else:
            wall=candidates[0]
            opening['host_id']=wall['id']
            if opening['base']<wall['base'] or opening['base']+opening['height']>wall['base']+wall['height']:
                errors.append(opening['name']+'：開口超出牆體高度')
    origin=[min(p[i] for f in floors for p in f['points']) for i in (0,1)] if floors else [0,0]
    # CAD survey/world coordinates may be far from the origin. Keep the exact
    # offset in the confirmed manifest; build locally for reliable WebGL precision.
    for item in active:item['points']=[[p[i]-origin[i] for i in (0,1)] for p in item['points']]
    from .plan_rectify import dimension_report
    return dict(status='blocked' if errors else 'ready',errors=errors,items=active,source_origin_metres=origin,
        dimension_report=dimension_report(parsed,settings,factor) if image else [],
        warnings=['高度、材質及家具模型為提案，需由使用者確認；未自動辨認房間。',
                  '家具輪廓先建立占位模型，可在後續編輯調整材質。'],
        counts=dict(Counter(a['role'] for a in active)),ignored=sum(a['role']=='ignore' for a in assignments))


class PlanIntake:
    def __init__(self, studio):self.studio=studio

    def folder(self, project, identifier):
        if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('平面識別碼無效')
        return self.studio.root(project)/'workflows/plan-import'/identifier

    def create(self, project, name, content):
        with self.studio.store.lock:
            return self._create(project,name,content)

    def _create(self, project, name, content):
        identifier=uuid4().hex
        item=self.studio.store.upload(project,name,content)
        path=self.studio.root(project)/item['path']
        parsed=parse_dxf(path)
        packet=dict(id=identifier,source=dict(item,sha256=digest(path)),parsed=parsed,
                    revision=uuid4().hex,created_at=now(),settings=suggested_settings(parsed))
        packet['check']=check_plan(parsed,packet['settings'])
        folder=self.folder(project,identifier)
        write_json(folder/'source.json',dict(source=packet['source'],parsed=parsed))
        write_json(folder/'revisions'/f"{packet['revision']}.json",packet)
        write_json(folder/'current.json',dict(revision=packet['revision']))
        write_json(folder.parent/'current.json',dict(id=identifier))
        (folder.parent/'README.md').write_text('# 平面匯入設定\n\n所有者：本案。sources/workbench 保留原 DXF；本處保存判讀與不可變修訂。current.json 僅為現行指標。建模結果位於 runs/interior-studio。保留原件與已確認修訂；可據此重建模型，不可當作暫存清除。\n',encoding='utf-8')
        return packet

    def current(self, project, identifier=None):
        if identifier is None:
            pointer=self.studio.root(project)/'workflows/plan-import/current.json'
            if not pointer.exists():return None
            identifier=read_json(pointer)['id']
        folder=self.folder(project,identifier)
        return read_json(folder/'revisions'/f"{read_json(folder/'current.json')['revision']}.json")

    def save(self, project, identifier, body):
        with self.studio.store.lock:
            previous=self.current(project,identifier)
            if previous['revision']!=body.base_revision:raise Conflict('平面已更新，請重新讀取後再保存')
            check=check_plan(previous['parsed'],body.settings.model_dump(mode='json'))
            packet=dict(previous,revision=uuid4().hex,parent=previous['revision'],created_at=now(),
                        settings=body.settings.model_dump(mode='json'),check=check)
            folder=self.folder(project,identifier)
            write_json(folder/'revisions'/f"{packet['revision']}.json",packet)
            write_json(folder/'current.json',dict(revision=packet['revision']))
            return packet

    def rectify(self,project,identifier,body):
        from .plan_rectify import rectify
        with self.studio.store.lock:
            previous=self.current(project,identifier)
            if previous['revision']!=body.base_revision:raise Conflict('平面已更新，請重新讀取後校正')
            settings=rectify(previous['parsed'],previous['settings'],[b.model_dump(mode='json') for b in body.bindings],body.base_revision)
            check=check_plan(previous['parsed'],settings)
            old=check_plan(previous['parsed'],previous['settings'])
            additional=[e for e in check['errors'] if e not in old['errors'] and '辨識疑點' not in e]
            if additional:raise ValueError('校正未套用：'+'；'.join(additional))
            return self.save(project,identifier,SavePlan(base_revision=body.base_revision,settings=settings))

    def build(self, project, identifier, body):
        with self.studio.store.lock:
            packet=self.current(project,identifier)
            if packet['revision']!=body.plan_revision:raise Conflict('平面確認已過期，請重新保存並確認')
            if packet.get('kind')=='image' and not body.confirmed:raise ValueError('圖片辨識必須先由使用者確認平面才能建模')
            if self.studio.current(project)['revision']!=body.base_revision:raise Conflict('設計已更新，請重新開啟匯入頁')
            path=self.studio.root(project)/packet['source']['path']
            if digest(path)!=packet['source']['sha256']:raise ValueError('原始圖面已變動，請重新匯入')
            check=check_plan(packet['parsed'],packet['settings'])
            if check['status']!='ready':raise ValueError('請先完成平面檢查：'+'；'.join(check['errors'][:5]))
            revision_path=self.folder(project,identifier)/'revisions'/f"{packet['revision']}.json"
            source=dict(plan=revision_path.relative_to(self.studio.root(project)).as_posix(),plan_sha256=digest(revision_path),
                        rooms=[dict(id='interior',name='室內（待分區）')],viewpoints=[],links=[])
            return self.studio.jobs.submit_studio(project,'prepare',dict(source=source),
                'dxf-'+identifier+'-'+packet['revision'])
