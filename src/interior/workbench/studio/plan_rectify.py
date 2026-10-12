"""Rectilinear reconstruction with explicit, exact measurement constraints.

Works on a revision's editable vertices, never on source pixels. A dimension
requires an explicit vertex/axis binding: text position is not an endpoint.
"""
import copy
import math


def straight_runs(points):
    """Index pairs for contiguous, collinear, forward wall segments."""
    start=0
    for end in range(1,len(points)-1):
        a,b,c=points[start],points[end],points[end+1]
        u=[b[k]-a[k] for k in (0,1)];v=[c[k]-b[k] for k in (0,1)]
        if abs(u[0]*v[1]-u[1]*v[0])>1e-7 or sum(u[k]*v[k] for k in (0,1))<=0:
            yield start,end
            start=end
    yield start,len(points)-1


def confirmed_dimension(parsed, dimension):
    records=((parsed.get('recognition_audit') or {}).get('evidence_review') or {}).get('records',[])
    return bool(dimension and dimension.get('metres') and any(
        r['id'] in dimension.get('source_refs',[]) and any(v['dimension_id']==dimension['id'] and abs(v['metres']-dimension['metres'])<1e-8 for v in r.get('dimensions',[])) for r in records))


def dimension_report(parsed, settings, factor):
    """Recompute current measurements; historical cautions are never solver results."""
    source={f['id']:f for f in parsed['features']+settings.get('additions',[])}
    assignments={a['id']:a for a in settings['assignments']}
    bindings=(settings.get('reconstruction') or {}).get('bindings',[])
    rows=[]
    for d in parsed.get('dimensions',[]):
        if not confirmed_dimension(parsed,d):continue
        bound=[b for b in bindings if b['dimension_id']==d['id']]
        row=dict(dimension_id=d['id'],text=d.get('text',d['id']),metres=d['metres'],status='pending',measured_m=None,difference_m=None,bindings=bound)
        if bound:
            measurements=[]
            try:
                for b in bound:
                    axis=0 if b['axis']=='x' else 1
                    points=[]
                    for k in ('start','end'):
                        a=assignments[b[k]['feature_id']]
                        if a['role']=='ignore':raise ValueError('ignored')
                        p=(a.get('points') or source[a['id']]['points'])[b[k]['vertex']]
                        points.append(p[axis]*factor+a['offset'][axis]*(1 if axis==0 else -1))
                    measurements.append(abs(points[1]-points[0]))
                value=max(measurements,key=lambda v:abs(v-d['metres']))
                row.update(measured_m=value,difference_m=value-d['metres'],status='applied' if abs(value-d['metres'])<1e-6 else 'conflict')
            except (KeyError,IndexError,ValueError):row['status']='conflict'
        row['cautions']=[c for c in settings.get('dimension_cautions',[]) if c['dimension_id']==d['id']]
        rows.append(row)
    return rows


def rectify(parsed, settings, bindings, revision):
    if not parsed.get('image'):raise ValueError('直角校正僅適用手繪圖片入口')
    result=copy.deepcopy(settings)
    cal=settings.get('calibration')
    if not cal or math.dist(cal['start'],cal['end'])<5:raise ValueError('請先提供候選比例尺')
    factor=cal['metres']/math.dist(cal['start'],cal['end'])
    source={f['id']:f for f in parsed['features']+settings.get('additions',[])}
    assignments={a['id']:a for a in result['assignments']}
    before={k:[[p[0]+a['offset'][0]/factor,p[1]-a['offset'][1]/factor] for p in (a.get('points') or source[k]['points'])] for k,a in assignments.items()}
    nodes=[];lookup={};refs={}
    for key,a in assignments.items():
        if a['role']=='ignore':continue
        for i,p in enumerate(before[key]):
            token=tuple(round(v,5) for v in p)
            if token not in lookup:lookup[token]=len(nodes);nodes.append(p)
            refs[key,i]=lookup[token]
    parents=[list(range(len(nodes))) for _ in range(2)]
    def find(axis,n):
        while parents[axis][n]!=n:
            parents[axis][n]=parents[axis][parents[axis][n]];n=parents[axis][n]
        return n
    def join(axis,a,b):parents[axis][find(axis,a)]=find(axis,b)
    for key,a in assignments.items():
        if a['role'] not in ('wall','floor'):continue
        pts=before[key];pairs=list(zip(range(len(pts)-1),range(1,len(pts))))
        if source[key]['closed']:pairs.append((len(pts)-1,0))
        for i,j in pairs:
            dx,dy=abs(pts[j][0]-pts[i][0]),abs(pts[j][1]-pts[i][1])
            if max(dx,dy)<.001:raise ValueError('牆線有重複頂點，請先修正')
            # Diagonals of triangulated floor pieces are not architectural walls.
            if min(dx,dy)/max(dx,dy)>.4:
                if a['role']=='wall':raise ValueError(a['name']+'：方向接近斜牆，不能自動判定水平或垂直')
                continue
            axis=1 if dx>=dy else 0
            join(axis,refs[key,i],refs[key,j])
    values=[{},{}];members=[{},{}]
    for axis in (0,1):
        for n,p in enumerate(nodes):members[axis].setdefault(find(axis,n),[]).append(n)
        values[axis]={g:sum(nodes[n][axis] for n in ns)/len(ns) for g,ns in members[axis].items()}
    dims={d['id']:d for d in parsed.get('dimensions',[])}
    opening_bindings={}
    graphs=[{},{}]
    for b in bindings:
        d=dims.get(b['dimension_id'])
        accepted=confirmed_dimension(parsed,d)
        if not accepted:raise ValueError('尺寸約束需有已確認讀值與可核對的來源紀錄')
        if b.get('mode')=='opening_width':
            key=b['start']['feature_id']
            if (key!=b['end']['feature_id'] or key not in assignments or assignments[key]['role'] not in ('door','window') or
                [b['start']['vertex'],b['end']['vertex']]!=[0,1] or len(before[key])!=2):raise ValueError('洞口寬度必須綁定同一門窗的兩端 0、1')
            if key in opening_bindings and abs(d['metres']-dims[opening_bindings[key]['dimension_id']]['metres'])>1e-6:raise ValueError('同一洞口的已確認尺寸互相衝突，未套用')
            opening_bindings[key]=b
            continue
        axis=0 if b['axis']=='x' else 1
        try:ns=[refs[v['feature_id'],v['vertex']] for v in (b['start'],b['end'])]
        except KeyError as exc:raise ValueError('尺寸端點必須綁定現有、未略過元件的頂點') from exc
        if any(assignments[b[k]['feature_id']]['role'] in ('door','window') for k in ('start','end')):
            raise ValueError('洞口淨寬需以牆面端點約束，不以可投影的洞口作固定基準')
        g0,g1=[find(axis,n) for n in ns]
        direction=nodes[ns[1]][axis]-nodes[ns[0]][axis]
        if abs(direction)<.001:raise ValueError('尺寸方向與兩端重合，請確認綁定軸向')
        length=math.copysign(d['metres']/factor,direction)
        graphs[axis].setdefault(g0,[]).append((g1,length))
        graphs[axis].setdefault(g1,[]).append((g0,-length))
    for axis in (0,1):
        seen=set()
        for root in graphs[axis]:
            if root in seen:continue
            offsets={root:0.};stack=[root]
            while stack:
                g=stack.pop()
                for h,length in graphs[axis].get(g,[]):
                    want=offsets[g]+length
                    if h in offsets:
                        if abs(offsets[h]-want)*factor>1e-6:raise ValueError('已確認尺寸互相衝突；保留差額，未套用校正')
                    else:offsets[h]=want;stack.append(h)
            # Only translation remains free; measured lengths are never averaged.
            shift=sum(values[axis][g]-v for g,v in offsets.items())/len(offsets)
            for g,v in offsets.items():values[axis][g]=shift+v
            seen.update(offsets)
    after={k:[[values[axis][find(axis,refs[k,i])] for axis in (0,1)] for i in range(len(pts))] for k,pts in before.items() if assignments[k]['role']!='ignore'}
    # Transport each opening along its original host segment; never guess a host.
    for key,a in assignments.items():
        if a['role'] not in ('door','window'):continue
        host=a['host_id'];candidates=[]
        if host not in after or assignments[host]['role']!='wall':
            if key in opening_bindings:raise ValueError(a['name']+'：缺少明確宿主牆')
            # Preserve an already incomplete user addition. The plan validator
            # still blocks building it; unrelated confirmed lengths can proceed.
            after[key]=before[key]
            continue
        for i,j in straight_runs(before[host]):
            p,q=before[host][i],before[host][j]
            length=math.dist(p,q)**2
            if not length:continue
            ts=[sum((v[axis]-p[axis])*(q[axis]-p[axis]) for axis in (0,1))/length for v in before[key]]
            distances=[math.dist(v,[p[axis]+t*(q[axis]-p[axis]) for axis in (0,1)]) for v,t in zip(before[key],ts)]
            if all(-1e-6<=t<=1+1e-6 for t in ts) and max(distances)<.5:candidates.append((i,j,ts))
        if len(candidates)!=1:raise ValueError(a['name']+'：無法唯一對應原宿主線段')
        i,j,ts=candidates[0];p,q=after[host][i],after[host][j]
        after[key]=[[p[axis]+t*(q[axis]-p[axis]) for axis in (0,1)] for t in ts]
        if key in opening_bindings:
            binding=opening_bindings[key];axis=0 if binding['axis']=='x' else 1
            if abs(p[1-axis]-q[1-axis])>1e-6 or abs(p[axis]-q[axis])<1e-6:raise ValueError('洞口尺寸軸向與宿主牆不符')
            width=dims[binding['dimension_id']]['metres']/factor
            centre=sum(v[axis] for v in after[key])/2
            run=list(after[host][i:j+1]);left=i-1;right=j+1
            while left>=0 and abs(after[host][left][1-axis]-p[1-axis])<1e-6:
                run.append(after[host][left]);left-=1
            while right<len(after[host]) and abs(after[host][right][1-axis]-p[1-axis])<1e-6:
                run.append(after[host][right]);right+=1
            low,high=min(v[axis] for v in run),max(v[axis] for v in run)
            if width>high-low+1e-6:raise ValueError('確認洞口寬度超過宿主牆可用範圍；不延長牆、不縮短已確認尺寸')
            # Width is exact; position remains a proposal. Minimal translation
            # keeps the entire opening inside the existing collinear host run.
            centre=max(low+width/2,min(high-width/2,centre))
            lo,hi=centre-width/2,centre+width/2
            targets=[lo,hi] if after[key][1][axis]>after[key][0][axis] else [hi,lo]
            for point,value in zip(after[key],targets):point[axis]=value
    changed=0;changed_ids=set()
    for key,pts in after.items():
        if any(math.dist(p,q)>.00001 for p,q in zip(before[key],pts)):changed+=1;changed_ids.add(key)
        a=assignments[key];a['points']=pts;a['offset']=[0,0]
    result['reconstruction']=dict(source_revision=revision,orthogonal=True,changed_features=changed,bindings=bindings,
        note='牆體依直角原則校正；已綁定確認尺寸作精確約束。洞口只保證已確認寬度，位置沿既有牆最小平移以容納開口，端面位置仍為提案。未綁定尺寸不套用，原圖保留。')
    affected={q['id'] for q in parsed.get('questions',[]) if changed_ids.intersection(q.get('feature_ids',[]))}
    result['reviewed']=[q for q in settings.get('reviewed',[]) if q not in affected]
    return result
