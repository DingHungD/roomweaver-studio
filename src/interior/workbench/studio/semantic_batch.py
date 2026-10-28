"""Host-enforced batch scope and evidence-bound incremental review reuse."""
import copy
from shapely.geometry import box,Point,LineString,Polygon
from shapely.ops import unary_union

from .cad_candidates import fingerprint,inventory,source_hash,component_group

VERSION='selected-corrections-v1'


def region(site,padding=.2):
    batch=site.get('correction_batch') or {}
    areas=[]
    for item in batch.get('items',[]):
        for mark in item['marks']:
            points=mark['points'];xs,ys=zip(*points)
            areas.append(box(min(xs),min(ys),max(xs),max(ys)).buffer(padding))
    return unary_union(areas)


def footprint(site,item):
    if item.get('source_binding') and item.get('role') not in ('wall','door','window','furniture'):
        from ...object_recognition.agent_review import source_shape
        return source_shape(site,item['source_binding'])
    points=item.get('points') or ([item['point']] if item.get('point') else [])
    if not points:
        refs=set(item.get('source_ids',[]))
        shapes=[footprint(site,g) for g in site['geometry'] if g['id'] in refs]
        shapes += [Point(t['point']) for t in site.get('texts',[]) if t['id'] in refs]
        return unary_union(shapes)
    if len(points)==1:return Point(points[0])
    if item.get('closed') or ('role' not in item and 'kind' not in item and len(points)>2):
        shape=Polygon(points)
        if shape.is_valid:return shape
    return LineString(points)


def relevant(site,item,area):
    shape=footprint(site,item)
    if shape.is_empty:return False
    if shape.area>1e-8:return shape.intersection(area).area/shape.area>=.5
    if shape.length>1e-8:return shape.intersection(area).length/shape.length>=.5
    return area.covers(shape)


def constrain(site,raw,resolved=False):
    """Keep untouched records byte-for-byte; proposals outside selection are not applied."""
    previous=site.get('previous_review',{}).get('candidate')
    if not site.get('correction_batch') or not previous:return raw,{}
    value=copy.deepcopy(raw);area=region(site);kept=[];excluded=[]
    if previous.get('handoff'):value['handoff']=copy.deepcopy(previous['handoff'])
    for key in ('rooms','elements','lighting','drawing_objects'):
        old={r['id']:r for r in previous.get(key) or []};incoming={r['id']:r for r in value.get(key) or []};rows=[]
        for identifier,baseline in old.items():
            proposed=incoming.pop(identifier,None)
            allowed=relevant(site,baseline,area)
            # Referenced hosts may extend beyond a window mark, but their actual
            # changed geometry must stay inside the selected neighbourhood.
            if proposed and resolved and proposed.get('points')!=baseline.get('points'):
                before_shape=footprint(site,baseline);after_shape=footprint(site,proposed)
                changed=before_shape.symmetric_difference(after_shape)
                allowed=allowed or (not changed.is_empty and area.buffer(.005).covers(changed))
                # An in-scope native furniture group may be trimmed back to its
                # own source components even if the removed overlarge strip is
                # outside a tightly drawn mark. This never authorizes expansion
                # into another object or changing confirmed heights.
                refs={r['id'] for r in (proposed.get('source_binding') or {}).get('refs',[])}
                added=after_shape.difference(before_shape)
                contraction=allowed and baseline.get('role')==proposed.get('role')=='furniture' and bool(proposed.get('derivation')) and bool(refs) and (added.is_empty or area.buffer(.005).covers(added))
                if not area.buffer(.005).covers(changed) and not contraction:allowed=False
            if not allowed:
                rows.append(copy.deepcopy(baseline))
                if proposed!=baseline:kept.append(identifier)
            elif proposed is not None:
                for field in ('height','base'):
                    if field in baseline:proposed[field]=baseline[field]
                rows.append(proposed)
            # Missing in-scope furniture remains an error in correction_report;
            # missing out-of-scope records have already been restored above.
        for identifier,item in incoming.items():
            if relevant(site,item,area):rows.append(item)
            else:excluded.append(identifier)
        value[key]=rows if previous.get(key) is not None or rows else None
    baseline_q={q['id']:q for q in previous.get('questions',[]) if isinstance(q,dict)}
    confirmed={r['question']['id']:r['question'] for r in site.get('confirmed_answers',[])}
    queries=[]
    for q in value.get('questions',[]):
        known=confirmed.get(q.get('id')) if isinstance(q,dict) else None
        if known and all(known.get(k)==q.get(k) for k in ('ask','source_ids','box')):continue
        if isinstance(q,dict) and q.get('box'):
            shape=box(*q['box']);near=shape.area>0 and shape.intersection(area).area/shape.area>=.5
            if near:queries.append(q)
            elif q['id'] not in baseline_q:excluded.append(q['id'])
        elif q in previous.get('questions',[]):queries.append(q)
    for identifier,q in baseline_q.items():
        known=confirmed.get(identifier)
        if known and all(known.get(k)==q.get(k) for k in ('ask','source_ids','box')):continue
        if not any(isinstance(i,dict) and i['id']==identifier for i in queries):
            shape=box(*q['box']) if q.get('box') else None
            if shape is None or shape.area==0 or shape.intersection(area).area/shape.area<.5:queries.append(copy.deepcopy(q))
    value['questions']=queries
    if previous.get('floor_outline'):
        floor=Polygon(previous['floor_outline']['points'])
        if not area.covers(floor):value['floor_outline']=copy.deepcopy(previous['floor_outline'])
    for role in ('door','window','furniture'):
        value[role+'_state']='present' if any(e['role']==role for e in value['elements']) else previous[role+'_state']
    return value,dict(version=VERSION,preserved=sorted(set(kept)),excluded=sorted(set(excluded)))


def inherited_decisions(site,proposal):
    """Reuse individual unchanged native evidence, never a whole-candidate hash."""
    previous=site.get('previous_review',{});saved=previous.get('report',{}).get('coverage',{})
    if not previous or not saved:return {}
    # New runs carry this independently verified native-source binding. Legacy
    # recovery verifies its source request before adding it to the new run.
    if previous.get('source_hash')!=source_hash(site) and not previous.get('source_compatible',False):return {}
    rows={r['id']:r for r in inventory(site)};result={}
    old_objects={i['id']:i for key in ('rooms','elements','lighting','drawing_objects') for i in previous.get('candidate',{}).get(key) or []}
    new_objects={i['id']:i for key in ('rooms','elements','lighting','drawing_objects') for i in proposal.get(key) or []}
    def material(item):return {k:v for k,v in item.items() if k not in ('evidence','derivation')}
    changed_refs=set()
    physical_refs=set()
    room_ids={r['id'] for c in (previous.get('candidate',{}),proposal) for r in c.get('rooms',[])}
    for identifier in old_objects.keys()|new_objects.keys():
        old=old_objects.get(identifier,{});new=new_objects.get(identifier,{})
        if material(old)!=material(new):
            changed_refs.update(old.get('source_ids',[]));changed_refs.update(new.get('source_ids',[]))
            # Adding an area label may cite a cabinet edge or a light demand;
            # it does not reclassify either physical symbol.
            if identifier not in room_ids:physical_refs.update(old.get('source_ids',[]));physical_refs.update(new.get('source_ids',[]))
    for key,decision in saved.get('decisions',{}).items():
        row=rows.get(key)
        if not row or decision.get('source_target')!=fingerprint(row) or decision.get('action') not in ('mapped','ignore','question'):continue
        if decision['action']=='ignore' and changed_refs&set(row['source_ids']):
            if row['kind']!='room' and not physical_refs&set(row['source_ids']):
                result[key]=copy.deepcopy(decision);continue
            ids=component_group(row,proposal,[i['id'] for i in proposal['elements']])
            if ids:
                result[key]=dict(decision,action='mapped',object_ids=ids,component_group=True,reason='原跨段框線已由多段門窗與相鄰牆體共同覆蓋；逐段核對來源及幾何，不另建重複洞口。',previous_decision=copy.deepcopy(decision))
            continue
        result[key]=copy.deepcopy(decision)
    return result
