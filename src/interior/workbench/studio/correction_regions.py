"""Check each user mark against resolved preview geometry, not source ID claims."""
import re

from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

VERSION = 'mark-regions-v1'
WALL_CABINET_RULE = '牆與櫃體緊靠時須分開判讀：櫃體文字只證明櫃體，不可涵蓋背後或相鄰的實體牆帶。逐一核對填色、雙線厚度、端點連續性及家具外輪廓；相同來源可提供背景，但牆必須有獨立原生邊線綁定及實際幾何，不可用櫃體的來源引用冒充牆已完成。'
STRUCTURE_RULE = '牆端、轉角及牆體交接處也要逐區盤點柱體、加厚段及交接構件。厚度突變或方形填色只是線索，不足以獨自定為柱；須合看原生封閉輪廓、實際邊線、相鄰牆的連接、註解及有效人工確認。正常等厚的T形或L形牆接續不代表另有柱，不可在每個交點憑空增件。已確認柱體以role=wall、category=column獨立記錄，交接構件可用category=wall_junction；保留原ID，不與相鄰等厚牆合併，也不重複建件。必須交叉核對同處的實心填色、封閉輪廓與相鄰牆邊；同處來源矛盾不可只憑native_exact就信任斜線。真正斜柱可用outline保留凸輪廓；native_exact_fill=true為兩個讀取器已核對的原生實心邊界，依原圖及有效人工意見確認後可用solid_outline，不能任意直角化原點。分類不等於確認承重、材料或施工可拆性。'


def explicit_wall(item):
    # A narrow, unambiguous instruction only. Mixed requests remain Agent-labelled.
    title = item.get('title', '')
    text = title + ' ' + item.get('comment', '')
    return bool(re.search(r'(?:牆|墙|牆體|墙体)$|\bwall\b', title, re.I) or re.search(r'^(?:此處|這裡|框選處)(?:為|是)(?:矮)?[牆墙]', item.get('comment',''))) and not re.search(r'不(?:是|為)牆|非牆|刪.*牆|移除.*牆|非墙|not.*wall|remove.*wall', text, re.I)


def check_mark(site, proposal, mark, result, expected=None):
    from .semantic_batch import footprint
    errors = []
    if result.get('status') not in ('corrected', 'no_change'):
        return [result.get('summary') or '尚未完成此標註']
    kind = expected or result.get('expected_kind')
    collections = {'room': 'rooms', 'lighting': 'lighting', 'drawing': 'drawing_objects'}
    rows = proposal.get(collections.get(kind, 'elements')) or []
    if kind in ('column','wall_junction'):
        rows = [r for r in rows if r.get('role')=='wall' and r.get('category')==kind]
    elif kind in ('wall', 'door', 'window', 'furniture'):
        rows = [r for r in rows if r.get('role') == kind]
    ids = result.get('object_ids', [])
    targets = [r for r in rows if r['id'] in ids]
    if len(targets) != len(set(ids)) or not targets:
        return ['缺少符合用途的實際物件，不能只引用來源或其他類別']
    points = mark['points']; xs, ys = zip(*points)
    area = (Point(points[0]).buffer(.25) if mark['kind'] == 'text' else
            LineString(points).buffer(.08) if mark['kind'] == 'line' else
            box(min(xs), min(ys), max(xs), max(ys)).buffer(.04))
    shapes = [_shape(site, r) for r in targets]
    if any(s.is_empty or not s.intersects(area) for s in shapes):
        errors.append('對應物件不在此標註區域')
    if kind in ('column','wall_junction') and mark['kind']=='box':
        target=box(min(xs),min(ys),max(xs),max(ys))
        overlap=unary_union(shapes).intersection(target).area/max(target.area,.001)
        if overlap < .5:errors.append(f'柱體／交接構件僅覆蓋標註區域 {overlap:.0%}，不可拿相鄰薄牆代替')
    # Thin wall boxes are explicit spans: a small end post must not satisfy a
    # whole horizontal wall request. Union actual spans, never source references.
    if kind == 'wall' and mark['kind'] != 'text':
        dx, dy = max(xs)-min(xs), max(ys)-min(ys)
        if mark['kind'] == 'line' or max(dx, dy) >= 3*max(min(dx, dy), .001):
            axis = 0 if dx >= dy else 1
            low, high = (min(xs), max(xs)) if axis == 0 else (min(ys), max(ys))
            spans = []
            for shape in shapes:
                clipped = shape.intersection(area)
                if not clipped.is_empty:
                    bounds = clipped.bounds; a, b = max(low, bounds[axis]), min(high, bounds[axis+2])
                    if b > a:spans.append(LineString([(a, 0), (b, 0)]))
            covered = unary_union(spans).length/max(high-low, .001)
            if covered < .8:errors.append(f'實際牆段僅覆蓋標註長度 {covered:.0%}，仍有牆段未對應')
    return errors


def verify_regions(site, proposal, item, row, strict=True):
    marks = item.get('marks', [])
    supplied = row.get('mark_results') or []
    keys = [r['mark_id'] for r in supplied]
    expected = {m['id'] for m in marks}
    checks = []; errors = []
    if strict and (len(keys) != len(set(keys)) or set(keys) != expected):
        errors.append('必須逐一回報每個標註，不能漏項、重複或混入其他標註')
    by_id = {r['mark_id']: r for r in supplied}
    wall = explicit_wall(item)
    column = bool(re.search(r'柱體$|柱子$|柱$',item.get('title','')) or re.search(r'^(?:此處|這裡|框選處|這)(?:屬於|為|是)柱',item.get('comment','')))
    for number, mark in enumerate(marks, 1):
        result = by_id.get(mark['id'])
        # Read-only audit of historical wall claims; never invent Agent proofs.
        if result is None and not strict and wall:
            result = dict(status='no_change', expected_kind='wall', object_ids=[r['id'] for r in proposal.get('elements', []) if r.get('role') == 'wall' and _near(site, r, mark)])
        failures = check_mark(site, proposal, mark, result, 'column' if column else 'wall' if wall else None) if result else (['缺少逐標註核對紀錄'] if strict else [])
        checks.append(dict(mark_id=mark['id'], number=number, passed=not failures, errors=failures))
        errors.extend(f'標註 {number}：{e}' for e in failures)
    return checks, list(dict.fromkeys(errors))


def _near(site, row, mark):
    xs, ys = zip(*mark['points'])
    return _shape(site, row).intersects(box(min(xs), min(ys), max(xs), max(ys)).buffer(.04))


def _shape(site, row):
    from .semantic_batch import footprint
    shape=footprint(site,row)
    return shape.buffer(row['thickness']/2,cap_style=2) if row.get('role')=='wall' and not row.get('closed') and row.get('thickness',0)>0 else shape
