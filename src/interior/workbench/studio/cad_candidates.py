"""Trace bounded CAD evidence groups, not individual hatch or dimension strokes."""
import copy
import hashlib
import json
import math
import re
from collections import Counter

from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union

VERSION='cad-coverage-v1'
ROOM=re.compile(r'^(主臥(?:室|房)?|次臥(?:室|房)?|客廳|餐廳|廚房|浴廁|衛浴|浴室|廁所|書房|臥室[一二三四五\d]?|兒童房|小孩房|(?:前|後|工作)?陽台|玄關|儲藏室|洗衣間|更衣室|工作室|餐區|開放用餐區|living\s*(?:room)?|bedroom\s*\d*|kitchen|bathroom|study|balcony)$',re.I)
FURNITURE=re.compile(r'床|沙發|茶几|桌|椅|櫃|櫥|馬桶|洗手|面盆|水槽|淋浴|浴缸|冰箱|洗衣機|微波|爐|抽油煙機|熱水器|曬衣桿|回收桶|垃圾桶|電器|寵物尿片|層板|抽屜|sofa|couch|cabinet|wardrobe|desk|chair|table|toilet|sink|shower|refrigerator|\bbed\b',re.I)
LIGHT=re.compile(r'軌道燈|吊燈|崁燈|嵌燈|壁燈|吸頂燈|落地燈|燈具|pendant|downlight|track light',re.I)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def source_hash(site):
    value={k:site.get(k) for k in ('reference_revision','geometry','texts','dimensions','origin','factor','floor_locked')}
    # Additional independent verification is provenance, not a changed drawing.
    value['geometry']=[{k:v for k,v in g.items() if k!='native_exact_fill'} for g in value.get('geometry') or []]
    return fingerprint(value)


def same_source(a,b):
    """Compare immutable coordinates, tolerating only cyclic closed-loop encoding."""
    if source_hash(a)==source_hash(b):return True
    def normalized(site):
        value={k:site.get(k) for k in ('reference_revision','texts','dimensions','origin','factor','floor_locked')}
        rows=[]
        for g in site.get('geometry',[]):
            row={k:v for k,v in g.items() if k!='native_exact_fill'}
            if g.get('closed') and len(g['points'])>2:
                pts=[tuple(round(v,9) for v in p) for p in g['points']]
                row['points']=min(tuple(seq[n:]+seq[:n]) for seq in (pts,pts[::-1]) for n in range(len(pts)))
            rows.append(row)
        value['geometry']=rows
        return value
    return fingerprint(normalized(a))==fingerprint(normalized(b))


def extent(points,padding=0):
    return [min(p[0] for p in points)-padding,min(p[1] for p in points)-padding,max(p[0] for p in points)+padding,max(p[1] for p in points)+padding]


def shape(item):
    points=item['points']
    return Polygon(points) if item.get('closed',False) or item.get('role')=='room' else LineString(points) if len(points)>1 else Point(points[0])


def inventory(site):
    """A stable source ledger; supported signals are explicit, not all-CAD completeness."""
    geometry={g['id']:g for g in site['geometry']};rows=[];seen=set()
    def add(kind,label,refs,points,**extra):
        refs=sorted(set(refs));identity=dict(kind=kind,refs=refs)
        if kind=='frame':identity['axis']=[[round(v,3) for v in p] for p in points]
        key='cad-'+kind+'-'+fingerprint(identity)[:16]
        if key in seen:return
        seen.add(key);rows.append(dict(id=key,kind=kind,label=label,source_ids=refs,box=extent(points,.08),**extra))
    for text in site.get('texts',[]):
        label=text['text'].strip();compact=re.sub(r'\s+',' ',label)
        if ROOM.fullmatch(compact):add('room','用途文字：'+label,[text['id']],[text['point']],text=label)
        elif len(label)<=160 and LIGHT.search(label):add('light','燈具註記：'+label,[text['id']],[text['point']],text=label)
        elif len(label)<=160 and FURNITURE.search(label):add('furniture','家具／設備註記：'+label,[text['id']],[text['point']],text=label)
    native=site.get('native_dwg') or {}
    for entity in native.get('entities',[]):
        if entity.get('kind')=='INSERT' and entity['id'] not in geometry and entity.get('insertion'):
            add('unsupported','原生圖塊尚未展開，待工具處理',[entity['id']],[entity['insertion']])
    used_arcs={key for option in native.get('door_options',[]) for key in option.get('arc_ids',[])}
    for arc in native.get('entities',[]):
        if arc.get('kind')!='ARC' or arc['id'] in used_arcs or not .35<=arc.get('radius',0)<=1.6:continue
        sweep=(arc['end_angle']-arc['start_angle'])%(2*math.pi)
        if not .6<=sweep<=2.8:continue
        c=arc['center'];r=arc['radius'];pts=[[c[0]+r*math.cos(a),c[1]+r*math.sin(a)] for a in (arc['start_angle'],arc['end_angle'])]
        if arc['id'] in geometry:add('door','開門弧候選（需核對門樘或家具用途）',[arc['id']],pts,arc_center=c,arc_radius=r)
    for option in native.get('door_options',[]):
        refs=[r['id'] for r in option['refs']]+option.get('arc_ids',[])
        refs=[key for key in refs if key in geometry]
        if refs:add('door','門弧與門樘候選',refs,option['points'],options=[option])
    # Co-located parallel pairs are alternatives for one physical frame, never
    # separate windows. Preserve all references and choices for local review.
    frames=[]
    for option in native.get('frame_options',[]):
        line=LineString(option['points']);length=line.length
        same=None
        for group in frames:
            other=LineString(group['points'])
            if line.difference(other.buffer(.06)).length<=length*.25 and other.difference(line.buffer(.06)).length<=other.length*.25:
                same=group;break
        if same:same['options'].append(option)
        else:frames.append(dict(points=option['points'],options=[option]))
    for group in frames:
        refs=[key for o in group['options'] for key in o.get('source_ids',[r['id'] for r in o['refs']])]
        add('frame','平行框線候選',refs,group['points'],options=group['options'])
    for g in geometry.values():
        axes=g.get('axes',[])
        if g.get('native_exact') and g.get('closed') and axes:
            axis=axes[0]
            if axis['length']>=.5 and .04<=axis['thickness']<=.4:
                add('outline','封閉牆帶／家具輪廓',[g['id']],g['points'])
    for group in native.get('groups',[]):
        refs=[k for k in group['source_ids'] if k in geometry]
        pts=[p for k in refs for p in geometry[k]['points']]
        if pts:add('group','原生群組候選',refs,pts)
    return rows


def matches(row,proposal,components=False):
    """A citation alone cannot prove coverage of an entire candidate frame."""
    from .semantic_layers import furniture_category
    refs=set(row['source_ids']);region=box(*row['box']);result=[]
    candidates=[dict(i,role='room') for i in proposal['rooms']]+proposal['elements']
    candidates+=[dict(i,role='light') for i in proposal.get('lighting') or []]
    candidates+=[dict(i,role='drawing') for i in proposal.get('drawing_objects',[])]
    for item in candidates:
        used=set(item.get('source_ids',[]))|{r['id'] for r in (item.get('source_binding') or {}).get('refs',[])}
        if not refs&used:continue
        kind=row['kind'];role=item['role']
        if kind=='room' and role!='room':continue
        if kind=='room':
            normalize=lambda text:re.sub(r'[\s室房]', '', text.lower())
            label,name=normalize(row['text']),normalize(item['name'])
            if label not in name and name not in label:continue
        if kind=='room' and not region.intersects(Polygon(item['points']).buffer(.1)):continue
        if kind=='furniture' and role not in (('furniture','drawing') if components else ('furniture',)):continue
        if kind=='furniture':
            expected=furniture_category(dict(name=row['text']))
            if expected!='other' and furniture_category(item)!=expected:continue
        if kind=='light' and role!='light':continue
        if kind=='door' and role not in (('door','window','furniture','drawing') if components else ('door','window')):continue
        if kind=='frame' and role not in (('door','window','furniture','wall','drawing') if components else ('door','window')):continue
        if kind=='outline' and role not in ('wall','furniture'):continue
        if kind in ('frame','door'):
            # A reviewed symbolic glass screen/door is drawn from immutable
            # source_ids, with no editable points. Explicit mapped decisions
            # may account for it; a shared arc alone is not automatic proof.
            if role=='drawing':
                if not refs.issubset(used):continue
                result.append(item['id']);continue
            if row.get('arc_center') and role=='door':
                # An opening is a radius from the hinge, not the chord between
                # the ends of the swing arc. Comparing that chord to the door
                # incorrectly flags a correctly sourced door as missing.
                hinge=Point(row['arc_center']);opening=shape(item);radius=row['arc_radius']
                if min(hinge.distance(Point(p)) for p in item['points'])>.12 or abs(opening.length-radius)>max(.12,radius*.15):continue
            else:
                axis=LineString(row.get('options',[{}])[0].get('points',[[row['box'][0],row['box'][1]],[row['box'][2],row['box'][3]]]))
                tolerance=max(.12,float(item.get('thickness') or 0)/2+.02) if role=='wall' else .12
                if axis.difference(shape(item).buffer(tolerance)).length>axis.length*.25:continue
        result.append(item['id'])
    return result


def geometry_findings(site,proposal,report):
    """Locate machine findings for repair; a software error is not a human Q."""
    if report.get('diagnostics'):
        from .semantic_diagnostics import repair_candidates
        return repair_candidates(site,proposal,report)
    rows=[];floor=report.get('floor_outline') or {}
    for field in ('exterior_wall_gaps','unsupported_segments'):
        for segment in floor.get(field,[]):
            if len(segment)<2 or LineString(segment).length<.1:continue
            bounds=extent(segment,.18);near=[g['id'] for g in site['geometry'] if len(g['points'])>1 and box(*bounds).intersects(LineString(g['points']))]
            if near:rows.append(dict(id='cad-check-'+fingerprint(dict(field=field,segment=segment))[:16],kind='check',label='地板邊界／外牆對照',source_ids=sorted(near),box=bounds,errors=report.get('repair_errors',[])))
    for error in report.get('repair_errors',[]):
        if '地板候選外框' in error:continue
        for item in proposal['elements']+proposal['rooms']:
            if item['name'] in error:rows.append(dict(id='cad-check-'+fingerprint(dict(id=item['id'],error=error))[:16],kind='check',label=error,source_ids=item['source_ids'],box=extent(item['points'],.2),errors=[error]))
    return rows


def component_group(row,proposal,object_ids):
    """Verify a previously reviewed long frame covered by separate openings."""
    if row['kind']!='frame' or not row.get('options'):return []
    axis=LineString(row['options'][0]['points']);refs=set(row['source_ids'])
    elements=[e for e in proposal['elements'] if e['id'] in object_ids and e['role'] in ('wall','window','door') and refs&set(e.get('source_ids',[]))]
    openings=[e for e in elements if e['role'] in ('window','door') and axis.intersection(shape(e).buffer(.12)).length>.1]
    if len(openings)<2:return []
    coverage=unary_union([shape(e).buffer(max(.12,float(e.get('thickness',0))/2+.02)) for e in elements])
    if axis.difference(coverage).length>max(.025,axis.length*.05):return []
    return [e['id'] for e in elements]


def assess(site,proposal,report,decisions=None,records=None):
    records=records if records is not None else inventory(site)
    decisions=decisions or {};items=[]
    for row in records+geometry_findings(site,proposal,report):
        linked=matches(row,proposal) if row['kind']!='check' else []
        entry=copy.deepcopy(row);entry.update(status='matched' if linked else 'pending',object_ids=linked,reason='來源及對應物件吻合' if linked else '圖塊尚未展開成可核對幾何；這是工具待處理項，不要求使用者猜用途' if row['kind']=='unsupported' else '來源候選尚未被解釋')
        decision=decisions.get(row['id'])
        if row['kind']!='unsupported' and not linked and decision and decision.get('source_target')==fingerprint(row):
            if decision['action']=='mapped' and row['kind']!='check':
                linked=component_group(row,proposal,decision.get('object_ids',[])) if decision.get('component_group') else [key for key in matches(row,proposal,components=True) if key in decision.get('object_ids',[])]
                if linked:entry.update(status='matched',object_ids=linked,reason=decision['reason'],review_sources=decision['source_ids'])
            elif decision['action']=='ignore' and row['kind']!='check':entry.update(status='ignored',reason=decision['reason'],review_sources=decision['source_ids'])
            elif decision['action']=='question':entry.update(status='question',reason=decision['reason'],ask=decision['ask'],review_sources=decision['source_ids'])
            else:entry['reason']=decision['reason']
        items.append(entry)
    counts=dict(Counter(i['status'] for i in items));counts={key:counts.get(key,0) for key in ('matched','ignored','pending','question')}
    return dict(version=VERSION,candidate_hash=fingerprint(proposal),items=items,counts=counts,total=len(items),decisions=decisions,
                scope='用途文字、家具燈具註記、門弧門樘、平行框線、原生輪廓及群組；不是全部CAD語意正確率',source_geometry_count=len(site['geometry']))


def apply_report(site,proposal,report,saved=None):
    """Recompute coverage before preview/adoption; stale model claims cannot clear it."""
    if site.get('coverage_version')!=VERSION:return report
    from .semantic_batch import inherited_decisions
    saved=saved or {};valid=saved.get('candidate_hash')==fingerprint(proposal)
    decisions=inherited_decisions(site,proposal)
    if valid:decisions.update(saved.get('decisions',{}))
    coverage=assess(site,proposal,report,decisions)
    pending=[i for i in coverage['items'] if i['status']=='pending'];questions=[i for i in coverage['items'] if i['status']=='question']
    report['coverage']=coverage
    if valid:
        coverage['reviews']=saved.get('reviews',[]);coverage['failures']=saved.get('failures',{})
        for item in coverage['items']:
            if item['status']=='pending' and item['id'] in coverage['failures']:item['reason']='局部複核未通過，保留待自動處理：'+str(coverage['failures'][item['id']])
    known={q['id'] for q in report['questions']}
    for item in questions:
        key='audit-'+item['id'][4:]
        if key in known:continue
        report['questions'].append(dict(id=key,label='Q'+str(len(report['questions'])+1),title=item['label'][:100],ask=item['ask'],reason=item['reason'],source_ids=item['review_sources'][:40],box=item['box'],located=True,candidate_id=item['id']))
        report['errors'].append(item['ask'])
    if pending:
        message=f'仍有 {len(pending)} 組來源候選／檢查待局部複核，尚不能視為完整判讀'
        report['errors'].append(message);report['repair_errors'].append(message)
    report['errors']=list(dict.fromkeys(report['errors']));report['repair_errors']=list(dict.fromkeys(report['repair_errors']))
    report['status']='blocked' if report['errors'] else 'preview'
    report['requires_confirmation']=bool(report['questions']) and not report['repair_errors']
    from .semantic_diagnostics import attach
    attach(site,proposal,report)
    return report
