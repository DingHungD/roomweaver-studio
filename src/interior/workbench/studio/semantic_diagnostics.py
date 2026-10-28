"""Versioned, read-only dependency diagnostics for source-bound plan reviews."""
import hashlib
import json

from shapely.geometry import LineString,Polygon,MultiPoint
from shapely.ops import unary_union

VERSION = 'dwg-review-2'
ORDER = ('source', 'boundary', 'openings', 'geometry', 'projection', 'access', 'coverage', 'confirmation')
LABELS = dict(source='來源與尺度', boundary='地板與外牆範圍', openings='牆與門窗關係',
              geometry='物件幾何', projection='物件交接', access='入口連通性',
              coverage='來源覆蓋', confirmation='人工確認')


def stable_id(code, targets):
    value=json.dumps([code, sorted(set(targets))], ensure_ascii=False).encode()
    return 'check-'+hashlib.sha256(value).hexdigest()[:20]


def classify(message):
    for domain, code, terms in (
        ('access','sealed_room',('疑似沒有可連通',)),
        ('boundary','outside',('超出已提供',)),
        ('boundary','outline',('地板候選','地板範圍','範圍證據')),
        ('openings','binding',('來源綁定未通過',)),
        ('openings','host',('宿主','洞口未對齊')),
        ('openings','overlap',('洞口與',)),
        ('source','source_support',('來源線條','不存在的來源','尺度','單位')),
        ('coverage','pending_sources',('組來源候選',)),
        ('projection','recognition_pending',('物件複核／套層','物件用途／建模對應')),
        ('geometry','wall_thickness',('4 cm',)),
        ('geometry','furniture_outline',('家具需有封閉',)),
        ('geometry','convex_parts',('需使用凸輪廓',)),
        ('geometry','structure_role',('必須保留結構幾何',)),
        ('openings','missing_walls',('缺少主要牆體',)),
        ('geometry','missing_objects',('聲稱存在但沒有',)),
        ('geometry','unexpected_objects',('聲稱沒有卻產生',)),
        ('geometry','uncertain_presence',('是否存在仍待核對',)),
        ('geometry','mark',('修正項',)),
    ):
        if any(t in message for t in terms):return domain,code
    return 'geometry', 'validation:'+message.split(' ',1)[-1]


def opening_groups(candidate):
    """Hosts and their openings are atomic; unrelated neighbours are only context."""
    rows={r['id']:r for r in candidate.get('elements',[])}
    groups=[]
    for r in rows.values():
        if r.get('role') not in ('door','window'):continue
        members={r['id']}
        if r.get('host_id') in rows:members.add(r['host_id'])
        # A portal using the same two jambs is part of this opening assembly.
        refs={json.dumps(x,sort_keys=True) for x in (r.get('source_binding') or {}).get('refs',[])}
        sources=set(r.get('source_ids',[]))|{x['id'] for x in (r.get('source_binding') or {}).get('refs',[])}
        for wall in rows.values():
            if wall.get('role')!='wall':continue
            binding=wall.get('source_binding') or {}
            if refs and binding.get('method')=='portal' and refs=={json.dumps(x,sort_keys=True) for x in binding.get('refs',[])}:
                members.add(wall['id'])
            # A source-bound jamb/over-opening wall joins the assembly only
            # where its actual geometry touches the opening. Nearby windows
            # without shared source evidence remain read-only context.
            wall_sources=set(wall.get('source_ids',[]))|{x['id'] for x in binding.get('refs',[])}
            if sources&wall_sources and len(r.get('points',[]))>=2 and len(wall.get('points',[]))>=2:
                body=Polygon(wall['points']) if wall.get('closed') else LineString(wall['points']).buffer(wall.get('thickness',0)/2)
                if body.is_valid and LineString(r['points']).distance(body)<=.02:members.add(wall['id'])
        intersecting=[g for g in groups if g & members]
        for g in intersecting:members |= g;groups.remove(g)
        groups.append(members)
    return [sorted(g) for g in groups]


def attach(site, candidate, report):
    """Refresh derived checks, preserving original failures and confirmation gates."""
    previous=report.get('diagnostics',{})
    for key in ('errors','repair_errors'):
        report[key]=[e for e in report.get(key,[]) if e not in previous.get('generated_messages',[])]
    rows=candidate.get('elements',[])+candidate.get('rooms',[])+candidate.get('drawing_objects',[])
    issues=[]
    for message in report.get('repair_errors',[]):
        if any(i['message']==message for i in report.get('reference_issues',[])):continue
        targets=[r for r in rows if r.get('name') and message.startswith(r['name']+' ')]
        description=message[len(targets[0]['name'])+1:] if targets else message
        domain,code=classify(description)
        if domain=='openings' and targets and all(r.get('role') not in ('wall','door','window') for r in targets):domain='geometry'
        ids=sorted(r['id'] for r in targets)
        points=[p for r in targets for p in r.get('points',[])]
        bounds=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)] if points else None
        issues.append(dict(id=stable_id(domain+':'+code,ids),code=code,check=domain,message=message,
                           object_ids=ids,source_ids=sorted({s for r in targets for s in r.get('source_ids',[])}),box=bounds))
    issues.extend(report.get('reference_issues',[]))
    proof=report.get('floor_outline') or {}
    for pair in report.get('opening_overlaps',[]):
        targets=[r for r in rows if r['id'] in pair['object_ids']]
        issues=[i for i in issues if not (i['code']=='overlap' and set(i['object_ids'])&set(pair['object_ids']))]
        points=[p for r in targets for p in r.get('points',[])]
        issues.append(dict(id=stable_id('openings:overlap',pair['object_ids']),code='overlap',check='openings',
            message='洞口體積重疊 %.3f m，需核對完整窗框與兩側樘邊'%pair['overlap_m'],
            object_ids=pair['object_ids'],source_ids=sorted({s for r in targets for s in r.get('source_ids',[])}),
            box=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)] if points else None))
    for link in report.get('object_links',{}).get('items',[]):
        if link['status']=='pending':
            issues.append(dict(id=stable_id('projection',[link['object_id']]),code='projection',check='projection',
                message=link['reason'],object_ids=[t['id'] for t in link['targets']],source_ids=link['source_ids'],box=link.get('box')))
    reliable=proof.get('status')!='blocked' and proof.get('evidence_sufficient',True) and not any(i['check']=='boundary' for i in report.get('reference_issues',[]))
    checks=[];generated=[]
    dependencies=dict(source=[],boundary=['source'],openings=['source'],geometry=['source','boundary'],
                      projection=['source'],access=['boundary','openings'],coverage=['source'],confirmation=[])
    for name in ORDER:
        own=[i for i in issues if i['check']==name]
        status='failed' if own else 'passed'
        reason=''
        if name=='boundary' and not reliable:status='failed';reason='範圍證據不足，先核對外框與牆帶'
        if name=='geometry' and not reliable and not own:status='deferred';reason='範圍未定，越界結果待確認'
        if name=='access' and not report.get('access_checked',True):status='deferred';reason='地板或牆門證據不足，尚未檢查入口連通性'
        if name=='coverage' and report.get('coverage',{}).get('counts',{}).get('pending',0):status='failed'
        if name=='confirmation' and (report.get('questions') or report.get('pending_source_confirmations')):status='failed';reason='原圖疑點仍待確認'
        if name=='projection' and report.get('object_links',{}).get('pending',0):status='failed';reason='物件用途／建模對應仍需核對'
        checks.append(dict(id=name,label=LABELS[name],status=status,reason=reason,depends_on=dependencies[name]))
        if status=='deferred':generated.append(reason)
    groups=[]
    for check in checks:
        own=[i for i in issues if i['check']==check['id']]
        if check['id']=='boundary' and not reliable:
            own += [i for i in issues if i['code']=='outside' and i not in own]
        if check['status']=='passed':continue
        groups.append(dict(id='group:'+check['id'],check=check['id'],title=check['label'],status=check['status'],
                           reason=check['reason'],issues=own,depends_on=check['depends_on'],
                           object_ids=sorted({k for i in own for k in i['object_ids']})))
    report['diagnostics']=dict(version=VERSION,checks=checks,groups=groups,issues=issues,
        boundary=dict(evidence_sufficient=reliable,user_confirmed=bool(site.get('floor_locked',True))),
        opening_groups=opening_groups(candidate),generated_messages=generated)
    for message in generated:
        for key in ('errors','repair_errors'):
            if message not in report[key]:report[key].append(message)
    report['status']='blocked' if report['errors'] else 'preview'
    return report


def regressions(before, after):
    """A newly executable check can reveal a failure without invalidating its prerequisite fix."""
    old=before.get('diagnostics');new=after.get('diagnostics')
    if not old or not new:return sorted(set(after.get('repair_errors',[]))-set(before.get('repair_errors',[])))
    old_ids={i['id'] for i in old['issues']}
    deferred={c['id'] for c in old['checks'] if c['status']=='deferred'}
    introduced=[i for i in new['issues'] if i['id'] not in old_ids]
    after['newly_discovered']=[i['id'] for i in introduced if i['check'] in deferred or i['code']=='outside' and not old['boundary']['evidence_sufficient']]
    represented={i['message'] for i in new['issues']}|set(new.get('generated_messages',[]))
    external=(set(after.get('repair_errors',[]))-represented)-set(before.get('repair_errors',[]))
    return [i['message'] for i in introduced if i['id'] not in after['newly_discovered']]+sorted(external)


def check_atomic_openings(before,candidate,report):
    old={r['id']:r for r in before.get('elements',[])}
    current={r['id']:r for r in candidate.get('elements',[])}
    touched={key for key in old.keys()|current.keys() if old.get(key)!=current.get(key)}
    groups=opening_groups(before)+opening_groups(candidate)
    affected={k for group in groups if set(group)&touched for k in group}
    if not affected:return
    issues=report.get('diagnostics',{}).get('issues',[])
    failures=[i['message'] for i in issues if affected&set(i['object_ids']) and i['check'] in ('source','openings','boundary')]
    if failures:raise ValueError('牆窗群組尚未整組通過，保留原值：'+'；'.join(failures))


def beam_requirements(rows):
    """A confirmed underside does not supply a beam depth, including split links."""
    rows=list(rows)
    missing_base=not rows or any((r.get('model_dimensions') or {}).get('base') is None for r in rows)
    missing_depth=not rows or any((r.get('model_dimensions') or {}).get('height') is None for r in rows)
    if missing_base and missing_depth:return ['梁標高與梁深尚須確認']
    if missing_base:return ['梁標高尚須確認']
    if missing_depth:return ['梁深尚須確認']
    return []


def object_links(site, candidate, audit):
    """Derive evidence-checked links, never use the existence of a source ID as proof."""
    from .semantic_feedback import shape,kind
    targets=[(key,r) for key in ('elements','lighting','drawing_objects') for r in candidate.get(key) or []]
    objects=(audit or {}).get('layers',{}).get('items',[])
    def geometry(row):
        try:
            value=shape(site,row)
            return value if value.is_valid else None
        except (ValueError,KeyError,TypeError):return None
    originals=[geometry(o) for o in objects];projected=[geometry(r) for _,r in targets]
    def overlaps(a,b):
        if a is None or b is None or a.is_empty or b.is_empty:return False
        if a.area and b.area:return a.intersection(b).area>1e-8
        if a.length and b.length:return min(a.intersection(b.buffer(.005)).length,b.intersection(a.buffer(.005)).length)>.005
        return a.distance(b)<=.005
    related={i:{j for j,(_,r) in enumerate(targets) if set(o.get('source_ids',[]))&set(r.get('source_ids',[])) and overlaps(originals[i],projected[j])} for i,o in enumerate(objects)}
    edges={i:{j for j in js if kind(objects[i],'objects')==kind(targets[j][1],targets[j][0])} for i,js in related.items()}
    def score(a,b):
        if a.area and b.area:return a.intersection(b).area/max(a.union(b).area,1e-9)
        if a.length and b.length:return min(a.intersection(b.buffer(.005)).length/a.length,b.intersection(a.buffer(.005)).length/b.length)
        return float(a.distance(b)<=.005)
    def duplicates(values):
        for i,a in enumerate(values):
            for b in values[i+1:]:
                if a.area and b.area and a.intersection(b).area>min(a.area,b.area)*.2:return True
                if not a.area and not b.area and a.length and b.length and a.intersection(b).length>min(a.length,b.length)*.2:return True
        return False
    checked={};seen=set()
    for start in edges:
        if start in seen or not edges[start]:continue
        parents={start};children=set()
        while True:
            more_children={j for i in parents for j in edges[i]}
            more_parents={i for i,js in edges.items() if js&more_children}
            if more_children==children and more_parents==parents:break
            parents,children=more_parents,more_children
        seen.update(parents)
        left=[originals[i] for i in parents];right=[projected[j] for j in children]
        reason='辨識或設計表示有重複輪廓，不能視為拆合完成' if duplicates(left) or duplicates(right) else ''
        if not reason and score(unary_union(left),unary_union(right))<.8:reason='來源相同但雙向幾何覆蓋不足'
        for i in parents:checked[i]=(parents,children,reason)
    result=[]
    connected=set()
    for i,obj in enumerate(objects):
        parents,children,reason=checked.get(i,({i},related[i],'缺少一致的來源、用途與幾何對應'))
        links=[dict(collection=targets[j][0],id=targets[j][1]['id']) for j in sorted(children)]
        connected.update(children)
        if obj.get('status')=='reference':reason='辨識候選仍待複核'
        bounds=list(originals[i].bounds) if originals[i] is not None and not originals[i].is_empty else None
        result.append(dict(id=stable_id('link',[obj['id']]),object_id=obj['id'],targets=links,
            status='pending' if reason else 'mapped',
            relation='merged' if len(parents)>1 else 'split' if len(links)>1 else 'retained',parent_ids=sorted(objects[p]['id'] for p in parents),
            box=bounds,
            source_ids=obj.get('source_ids',[]),reason=reason or '來源、用途與雙向輪廓已核對',
            modeling_requirements=beam_requirements(targets[j][1] for j in children) if obj.get('category')=='beam' else []))
    for j,(key,row) in enumerate(targets):
        if j in connected or row.get('role')=='wall':continue
        bounds=list(projected[j].bounds) if projected[j] is not None and not projected[j].is_empty else None
        result.append(dict(id=stable_id('target-link',[key,row['id']]),object_id=key+':'+row['id'],targets=[dict(collection=key,id=row['id'])],
            status='pending',relation='pending',parent_ids=[],box=bounds,source_ids=row.get('source_ids',[]),
            reason='設計元件缺少可核對的辨識對應，保留待確認',modeling_requirements=beam_requirements([row]) if row.get('category')=='beam' else []))
    for row in result:
        history=[h for h in (audit or {}).get('lineage_changes',[]) if h['id']==row['object_id']]
        if history and history[-1].get('parent_ids'):row['parent_ids']=history[-1]['parent_ids']
    present={i['object_id'] for i in result}
    for change in (audit or {}).get('lineage_changes',[]):
        if change['collection']=='objects' and change['action']=='remove' and change['id'] not in present:
            result.append(dict(id=stable_id('link',[change['id']]),object_id=change['id'],targets=[],status='excluded',
                relation='excluded',parent_ids=change.get('parent_ids',[]),source_ids=change.get('source_ids',[]),
                reason=change['reason'],box=None,modeling_requirements=[]))
            present.add(change['id'])
    return dict(version=VERSION,items=result,pending=sum(i['status']=='pending' for i in result))


def attach_links(site,candidate,report,audit):
    message='物件用途／建模對應仍需局部核對，尚不能採用。'
    for key in ('errors','repair_errors'):
        report[key]=[e for e in report.get(key,[]) if e!=message]
    if audit:
        report['object_links']=object_links(site,candidate,audit)
        report['object_links']['semantic_lineage']=site.get('semantic_lineage',[])
        if report['object_links']['pending']:
            for key in ('errors','repair_errors'):
                if message not in report[key]:report[key].append(message)
    return attach(site,candidate,report)


def repair_candidates(site,candidate,report):
    """Stable root-cause repair units; never convert deferred checks to human questions."""
    diagnostic=report.get('diagnostics',{})
    issues=diagnostic.get('issues',[]);groups=[]
    assemblies=diagnostic.get('opening_groups',[])
    rows={r['id']:r for r in candidate.get('elements',[])+candidate.get('rooms',[])}
    reliable=diagnostic.get('boundary',{}).get('evidence_sufficient',True)
    buckets={}
    for issue in issues:
        if issue['check'] in ('coverage','confirmation') or not issue.get('box'):continue
        if issue['code']=='outside' and not reliable:key='boundary';priority=0
        elif issue['check']=='boundary' and issue['code']!='outside':key='boundary';priority=0
        elif issue['check']=='openings':
            assembly=next((g for g in assemblies if set(g)&set(issue['object_ids'])),issue['object_ids'])
            key='opening:'+','.join(assembly);priority=1
        else:key=issue['id'];priority=2
        entry=buckets.setdefault(key,dict(issues=[],priority=priority))
        entry['issues'].append(issue)
    if not reliable:buckets.setdefault('boundary',dict(issues=[],priority=0))
    for key,bucket in buckets.items():
        selected=set(k for i in bucket['issues'] for k in i['object_ids'])
        if key.startswith('opening:'):selected.update(key[len('opening:'):].split(','))
        bounds=[MultiPoint([i['box'][:2],i['box'][2:]]).envelope.buffer(.001) for i in bucket['issues'] if i.get('box')]
        refs={r for i in bucket['issues'] for r in i['source_ids']}
        selected_rows=[rows[k] for k in selected if k in rows]
        if key=='boundary':selected_rows=[r for r in rows.values() if r.get('role')=='wall']
        for r in selected_rows:
            points=r.get('points',[])
            if points:bounds.append(MultiPoint(points).envelope.buffer(.001))
            refs.update(r.get('source_ids',[]))
        if not bounds or not refs:continue
        region=unary_union(bounds).envelope.buffer(.2)
        groups.append(dict(id='cad-check-'+stable_id(key,selected)[6:],kind='check',label='地板邊界／外牆對照' if key=='boundary' else '牆窗成組核對' if key.startswith('opening:') else bucket['issues'][0]['message'],
            source_ids=sorted(refs),box=list(region.bounds),errors=[i['message'] for i in bucket['issues']],
            repair_priority=bucket['priority'],atomic_ids=sorted(selected),issue_ids=[i['id'] for i in bucket['issues']]))
    return groups


def select_batch(pending,candidate,limit=24):
    """Fit whole overlapping repair groups within the existing batch budget."""
    assemblies=[set(g) for g in opening_groups(candidate)]
    clusters=[]
    for row in pending:
        ids=set(row.get('atomic_ids',[]))|set(row.get('object_ids',[]))
        for group in assemblies:
            if group&ids:ids|=group
        hits=[c for c in clusters if c[0]&ids and c[1][0].get('repair_priority',3)==row.get('repair_priority',3)]
        members=[row]
        for c in hits:ids|=c[0];members+=c[1];clusters.remove(c)
        clusters.append((ids,members))
    def rank(row):return row.get('repair_priority',3),row['id']
    result=[];skipped=[]
    for _,members in sorted(clusters,key=lambda c:min(rank(i) for i in c[1])):
        if len(members)>limit:skipped.extend(i['id'] for i in members);continue
        if result and min(rank(i)[0] for i in members)!=min(rank(i)[0] for i in result):break
        if len(result)+len(members)<=limit:result+=members
    return result,skipped
