"""Deterministic CAD semantic geometry from immutable source edges, never AI coordinates."""
import math
from shapely.geometry import Polygon


def overlapping_openings(proposal):
    """Find duplicate aperture volumes, independently of names and host IDs."""
    rows=[r for r in proposal.get('elements',[]) if r.get('role') in ('door','window') and len(r.get('points',[]))==2]
    pairs=[]
    for index,a in enumerate(rows):
        p,q=a['points'];length=math.dist(p,q)
        if length<.001:continue
        u=[(q[k]-p[k])/length for k in (0,1)];v=[-u[1],u[0]]
        for b in rows[index+1:]:
            if min(a.get('base',0)+a.get('height',2.8),b.get('base',0)+b.get('height',2.8))-max(a.get('base',0),b.get('base',0))<=.001:continue
            c,d=b['points']
            if max(abs(sum((r[k]-p[k])*v[k] for k in (0,1))) for r in (c,d))>.005:continue
            ends=sorted(sum((r[k]-p[k])*u[k] for k in (0,1)) for r in (c,d))
            overlap=min(length,ends[1])-max(0,ends[0])
            if overlap>.005:pairs.append(dict(object_ids=sorted([a['id'],b['id']]),overlap_m=overlap))
    return pairs


def axis_options(g):
    """List real parallel edge pairs; never use a fitted bounding rectangle as wall."""
    if not g.get('native_exact') or not g.get('closed'):
        return []
    pts=g['points'];result=[]
    for i,a in enumerate(pts):
        b=pts[(i+1)%len(pts)];length=math.dist(a,b)
        if length<.1:continue
        u=[(b[k]-a[k])/length for k in (0,1)];v=[-u[1],u[0]]
        for j in range(i+1,len(pts)):
            c,d=pts[j],pts[(j+1)%len(pts)];other=math.dist(c,d)
            if other<.1:continue
            if abs(sum((d[k]-c[k])*v[k] for k in (0,1)))/other>.005:continue
            offset=sum(((c[k]+d[k])/2-a[k])*v[k] for k in (0,1))
            lo=max(0,min(sum((p[k]-a[k])*u[k] for k in (0,1)) for p in (c,d)))
            hi=min(length,max(sum((p[k]-a[k])*u[k] for k in (0,1)) for p in (c,d)))
            if hi-lo<.1 or not .001<=abs(offset)<=1:continue
            result.append(dict(refs=[dict(id=g['id'],edge=i),dict(id=g['id'],edge=j)],
                length=hi-lo,thickness=abs(offset),points=[[a[k]+t*u[k]+offset/2*v[k] for k in (0,1)] for t in (lo,hi)]))
    return sorted(result,key=lambda o:o['length'],reverse=True)


def door_options(geometry, arcs):
    """Find source jamb pairs supported by a hinge arc; these remain candidates."""
    jambs=[]
    for g in geometry:
        options=axis_options(g)
        if len(g['points'])!=4 or not options:continue
        best=options[0]
        if not .04<=best['length']<=.45 or not .005<=best['thickness']<=.15:continue
        mids=[]
        for ref in best['refs']:
            a,b=g['points'][ref['edge']],g['points'][(ref['edge']+1)%4]
            mids.append((ref,[(a[k]+b[k])/2 for k in (0,1)]))
        centre=[sum(p[k] for p in g['points'])/4 for k in (0,1)]
        jambs.append((centre,mids))
    result=[]
    for arc in arcs:
        if arc['kind']!='ARC' or not .35<=arc['radius']<=1.6:continue
        sweep=(arc['end_angle']-arc['start_angle'])%(2*math.pi)
        if not .6<=sweep<=2.8:continue
        centre=arc['center'];r=arc['radius'];options=[]
        near=[j for j in jambs if math.dist(j[0],centre)<.16]
        for angle in (arc['start_angle'],arc['end_angle']):
            end=[centre[0]+r*math.cos(angle),centre[1]+r*math.sin(angle)]
            far=[j for j in jambs if math.dist(j[0],end)<.16]
            for a in near:
                for b in far:
                    choices=[(math.dist(p,q),ra,rb,p,q) for ra,p in a[1] for rb,q in b[1]]
                    distance,ra,rb,p,q=min(choices,key=lambda v:v[0])
                    if abs(distance-r)>.2 or distance<.3:continue
                    score=math.dist(a[0],centre)+math.dist(b[0],end)+abs(distance-r)
                    options.append((score,ra,rb,p,q))
        if options:
            score,ra,rb,p,q=min(options,key=lambda x:x[0])
            existing=next((o for o in result if min(math.dist(o['points'][0],p)+math.dist(o['points'][1],q),math.dist(o['points'][0],q)+math.dist(o['points'][1],p))<.01),None)
            if existing:existing['arc_ids'].append(arc['id']);continue
            result.append(dict(id='door-source-'+arc['id'],method='between',refs=[ra,rb],points=[p,q],width=math.dist(p,q),arc_ids=[arc['id']],status='source_supported_candidate'))
    return result


def connected_run(g, geometry):
    """Join touching collinear native LINE fragments, retaining every support ID."""
    a,b=g['points'];size=math.dist(a,b)
    if size<.001:return a,b,[g['id']]
    u=[(b[k]-a[k])/size for k in (0,1)];v=[-u[1],u[0]]
    candidates=[]
    for other in geometry.values():
        if not other.get('native_exact') or other['kind']!='LINE':continue
        c,d=other['points'];length=math.dist(c,d)
        if length<.001:continue
        if max(abs(sum((p[k]-a[k])*v[k] for k in (0,1))) for p in (c,d))>.001:continue
        ends=sorted(sum((p[k]-a[k])*u[k] for k in (0,1)) for p in (c,d))
        candidates.append((ends[0],ends[1],other['id']))
    lo,hi=0,size;refs={g['id']}
    for _ in range(len(candidates)+1):
        changed=False
        for x,y,key in candidates:
            if key not in refs and x<=hi+.005 and y>=lo-.005:
                lo,hi=min(lo,x),max(hi,y);refs.add(key);changed=True
        if not changed:break
    return [a[k]+lo*u[k] for k in (0,1)],[a[k]+hi*u[k] for k in (0,1)],sorted(refs)


def frame_options(geometry):
    """Parallel native runs are geometric options, not automatic window classification."""
    mapping={g['id']:g for g in geometry}
    runs={}
    for g in geometry:
        if g['kind']!='LINE' or not g.get('native_exact') or math.dist(*g['points'])<.15:continue
        a,b,refs=connected_run(g,mapping)
        if .45<=math.dist(a,b)<=4:runs[tuple(refs)]=(a,b,refs)
    rows=list(runs.values());options=[]
    for i,(a,b,refs) in enumerate(rows):
        length=math.dist(a,b);u=[(b[k]-a[k])/length for k in (0,1)];v=[-u[1],u[0]]
        for c,d,other in rows[i+1:]:
            if abs(sum((d[k]-c[k])*v[k] for k in (0,1)))/math.dist(c,d)>.001:continue
            width=abs(sum((c[k]-a[k])*v[k] for k in (0,1)))
            if not .015<=width<=.16:continue
            project=lambda p:sum((p[k]-a[k])*u[k] for k in (0,1))
            lo,hi=max(0,min(project(c),project(d))),min(length,max(project(c),project(d)))
            if hi-lo<.45 or hi-lo<width*4:continue
            shift=sum((c[k]-a[k])*v[k] for k in (0,1))/2
            options.append(dict(method='pair',refs=[dict(id=refs[0],edge=0),dict(id=other[0],edge=0)],
                points=[[a[k]+t*u[k]+shift*v[k] for k in (0,1)] for t in (lo,hi)],
                width=hi-lo,frame_depth=width,source_ids=refs+other,status='parallel_source_runs_not_window_proof'))
    return sorted(options,key=lambda o:o['width'],reverse=True)[:250]


def whole_frame(site, refs):
    """Prefer a complete native frame with two end caps over one sliding leaf overlap."""
    ids={r['id'] for r in refs}
    options=(site.get('native_dwg') or {}).get('frame_options',[])
    original=[o for o in options if {r['id'] for r in o['refs']}==ids]
    if not original:
        mapping={g['id']:g for g in site['geometry']}
        if len(refs)!=2 or any(r['id'] not in mapping or mapping[r['id']]['kind']!='LINE' for r in refs):return None
        a,b,_=connected_run(mapping[refs[0]['id']],mapping);c,d,_=connected_run(mapping[refs[1]['id']],mapping)
        length=math.dist(a,b)
        if length<.001:return None
        u=[(b[k]-a[k])/length for k in (0,1)];v=[-u[1],u[0]]
        project=lambda p:sum((p[k]-a[k])*u[k] for k in (0,1))
        lo,hi=max(0,min(project(c),project(d))),min(length,max(project(c),project(d)))
        shift=sum((c[k]-a[k])*v[k] for k in (0,1))/2
        if hi-lo<.1:return None
        original=dict(points=[[a[k]+t*u[k]+shift*v[k] for k in (0,1)] for t in (lo,hi)],width=hi-lo)
    else:original=max(original,key=lambda o:o['width'])
    a,b=original['points'];size=math.dist(a,b)
    edges=[]
    for g in site['geometry']:
        if not g.get('native_exact'):continue
        points=g['points']+(g['points'][:1] if g['closed'] else [])
        edges.extend(zip(points,points[1:]))
    choices=[]
    for o in options:
        if not ids.intersection(r['id'] for r in o['refs']) or o['width']<size*1.1:continue
        c,d=o['points'];length=math.dist(c,d);u=[(d[k]-c[k])/length for k in (0,1)];v=[-u[1],u[0]]
        if abs((b[0]-a[0])*v[0]+(b[1]-a[1])*v[1])/size>.005:continue
        if any(not -.01<=sum((p[k]-c[k])*u[k] for k in (0,1))<=length+.01 or abs(sum((p[k]-c[k])*v[k] for k in (0,1)))>.12 for p in (a,b)):continue
        # A full-width end cap inside the proposed span separates two windows.
        # Ignore drafting ticks protruding outside the frame, and short sash bars.
        divided=False
        for x,y in edges:
            along=[sum((p[k]-c[k])*u[k] for k in (0,1)) for p in (x,y)]
            across=sorted(sum((p[k]-c[k])*v[k] for k in (0,1)) for p in (x,y))
            half=o['frame_depth']/2
            if .08<sum(along)/2<length-.08 and abs(along[0]-along[1])<.007 and -half-.007<=across[0]<=-half+.007 and half-.007<=across[1]<=half+.007:
                divided=True;break
        if divided:continue
        def capped(p):
            ranges=[]
            for x,y in edges:
                if max(abs(sum((q[k]-p[k])*u[k] for k in (0,1))) for q in (x,y))>.007:continue
                ranges.append(sorted(sum((q[k]-p[k])*v[k] for k in (0,1)) for q in (x,y)))
            end=-o['frame_depth']/2
            for lo,hi in sorted(ranges):
                if lo<=end+.005 and hi>=end:end=max(end,hi)
            return end>=o['frame_depth']/2-.005
        if capped(c) and capped(d):choices.append(o)
    return max(choices,key=lambda o:o['width']) if choices else None


def resolve(site, proposal):
    if not site.get('native_dwg'):
        return [], []
    geometry = {g['id']:g for g in site['geometry']}
    errors, records = [], []
    for item in proposal['elements']:
        binding = item.get('source_binding')
        try:
            if not binding:
                raise ValueError('必須指定原始元件／邊線綁定，不能重畫座標')
            refs = binding['refs']
            sources = [geometry[r['id']] for r in refs]
            method = binding['method']
            automatic=None
            expanded=[]
            if method=='pair' and item['role']=='wall' and item.get('category') in ('column','wall_junction') and len({r['id'] for r in refs})==1 and sources[0].get('closed'):
                original=Polygon(sources[0]['points'])
                if original.is_valid and abs(original.minimum_rotated_rectangle.area-original.area)>1e-8:
                    raise ValueError('柱體／交接構件含斜邊或非矩形輪廓，請改用outline保留原生凸輪廓，不可裁成等厚矩形')
            if method=='pair' and item['role']=='window':
                complete=whole_frame(site,refs)
                if complete:
                    automatic=dict(reason='由原始外框及兩端收邊補齊整窗，避免只取單扇交疊區',requested_refs=refs)
                    refs=complete['refs']
                    sources=[geometry[r['id']] for r in refs]
            if method=='pair' and len(refs)==2 and refs[0]['id']==refs[1]['id'] and sources[0].get('closed'):
                # A rectangle's short end caps are often mistaken for its wall faces.
                # The longest actual parallel sides give one unambiguous thin axis.
                choices=[o for o in axis_options(sources[0]) if (item['role']!='wall' or o['thickness']>=.04) and o['length']>o['thickness']*2]
                if choices:
                    chosen=choices[0]['refs']
                    if chosen!=refs:
                        automatic=dict(reason='依同一來源輪廓的平行長邊修正端頭誤選',requested_refs=refs)
                        refs=chosen
            def edge(ref):
                g = geometry[ref['id']]
                if not g.get('native_exact'):
                    raise ValueError('牆門窗邊線必須來自可驗證的原生 LINE／直邊 LWPOLYLINE')
                points = g['points']
                index = ref['edge']
                if index>=len(points)-(not g['closed']):
                    raise ValueError('邊線索引超出原始元件')
                a,b = points[index],points[(index+1)%len(points)]
                if math.dist(a,b)<.001:
                    raise ValueError('來源邊線過短')
                return a,b
            if method in ('pair','between','portal'):
                if len(refs)!=2:
                    raise ValueError('需指定兩條原始邊線')
                (a,b),(c,d) = [edge(r) for r in refs]
                if method=='pair' and item['role']=='window' and refs[0]['id']!=refs[1]['id'] and all(g['kind']=='LINE' for g in sources):
                    a,b,keys=connected_run(sources[0],geometry);expanded+=keys
                    c,d,keys=connected_run(sources[1],geometry);expanded+=keys
                    if len(set(expanded))>2:
                        if automatic:automatic['expanded_refs']=sorted(set(expanded))
                        else:automatic=dict(reason='沿原始共線且連接的窗框線補齊片段',expanded_refs=sorted(set(expanded)))
                length = math.dist(a,b)
                u = [(b[k]-a[k])/length for k in (0,1)]
                v = [-u[1],u[0]]
                if abs((d[0]-c[0])*v[0]+(d[1]-c[1])*v[1])/math.dist(c,d)>.035:
                    raise ValueError('來源邊線不平行，不能推導同一牆帶／門樘')
                if method in ('between','portal'):
                    if method=='between' and item['role'] not in ('door','window'):
                        raise ValueError('between只用於兩側門樘／窗樘間的洞口')
                    points = [[(p[k]+q[k])/2 for k in (0,1)] for p,q in [(a,b),(c,d)]]
                    delta = [points[1][k]-points[0][k] for k in (0,1)]
                    if math.dist(*points)<.1 or abs(sum(delta[k]*u[k] for k in (0,1)))/math.dist(*points)>.035:
                        raise ValueError('洞口需連接相對的兩側樘邊，不能使用兩條門扇線')
                    if method=='portal':
                        matching=[e for e in proposal['elements'] if e['role'] in ('door','window') and e.get('host_id')==item['id'] and (e.get('source_binding') or {}).get('method')=='between' and (e['source_binding']['refs']==refs or e['source_binding']['refs']==refs[::-1])]
                        if item['role']!='wall' or not matching:
                            raise ValueError('portal只補已綁定門窗的洞口上方宿主牆，須共用相同兩側樘來源')
                        item['thickness']=(math.dist(a,b)+math.dist(c,d))/2
                        if not .04<=item['thickness']<=1:raise ValueError('門窗樘厚度不符合宿主牆範圍')
                else:
                    def project(p):return sum((p[k]-a[k])*u[k] for k in (0,1))
                    lo,hi = max(0,min(project(c),project(d))),min(length,max(project(c),project(d)))
                    separation = sum(((c[k]+d[k])/2-a[k])*v[k] for k in (0,1))
                    if hi-lo<.1 or abs(separation)<.001:
                        raise ValueError('邊線沒有足夠的重疊長度／實際間距')
                    points = [[a[k]+t*u[k]+separation/2*v[k] for k in (0,1)] for t in (lo,hi)]
                    if item['role']=='wall':
                        if not .04<=abs(separation)<=1:
                            raise ValueError('原始牆帶厚度不在4～100cm建模範圍，請重新判斷用途')
                        item['thickness']=abs(separation)
                item['points'],item['closed']=points,False
            elif method in ('outline','solid_outline'):
                structural=item['role']=='wall' and item.get('category') in ('column','wall_junction')
                exact=sources[0].get('native_exact_fill') if method=='solid_outline' else sources[0].get('native_exact')
                if len(sources)!=1 or not exact or not sources[0]['closed']:
                    raise ValueError('outline需指定一個原生封閉直邊輪廓')
                if method=='solid_outline' and not structural:raise ValueError('solid_outline僅限已判讀的柱體／交接構件，不能把任意填色當牆或家具')
                if item['role']!='furniture' and not structural:
                    raise ValueError('牆請使用pair原生兩側邊，門窗使用pair或between')
                if structural and method=='outline':
                    from .structural_evidence import outline_conflicts
                    conflicts=outline_conflicts(site,sources[0])
                    if conflicts:raise ValueError('柱體輪廓與同處原生實心填色不一致：'+str(conflicts)+'；請合看原圖、鄰接與人工意見後選擇真實來源；可用solid_outline綁定已驗證實心邊界，不得硬改原點')
                item['points'],item['closed']=sources[0]['points'],True
                if structural:
                    polygon=Polygon(item['points'])
                    if not polygon.is_valid or abs(polygon.convex_hull.area-polygon.area)>1e-8:raise ValueError('柱體／交接輪廓需為有效原生凸輪廓，凹形須分段並核對，不可改原點')
                    corners=list(polygon.minimum_rotated_rectangle.exterior.coords)
                    item['thickness']=min(math.dist(a,b) for a,b in zip(corners,corners[1:]))
            elif method in ('bounds','edge_bounds'):
                if item['role']!='furniture':
                    raise ValueError('bounds只適用家具概念占位，不能猜牆或門窗')
                if method=='edge_bounds':
                    if len(refs)!=4:raise ValueError('edge_bounds需要四條原生圍護邊：兩條水平／兩條垂直，相對方向可隨圖面旋轉')
                    requested_refs=refs
                    refs=[next((choice['refs'][0] for choice in axis_options(geometry[ref['id']]) if choice['length']>choice['thickness']*2),ref) for ref in refs]
                    edges=[edge(ref) for ref in refs];a,b=edges[0];length=math.dist(a,b)
                    u=[(b[k]-a[k])/length for k in (0,1)];v=[-u[1],u[0]]
                    project=lambda p,axis:sum(p[k]*axis[k] for k in (0,1))
                    center=[sum(p[k] for pair in edges for p in pair)/8 for k in (0,1)]
                    groups=[[],[]];chosen=[]
                    for ref,(a,b) in zip(refs,edges):
                        delta=[b[k]-a[k] for k in (0,1)];span=math.dist(a,b)
                        if abs(sum(delta[k]*v[k] for k in (0,1)))/span<.002:axis,normal,index=u,v,0
                        elif abs(sum(delta[k]*u[k] for k in (0,1)))/span<.002:axis,normal,index=v,u,1
                        else:raise ValueError('edge_bounds圍護邊必須正交，不能將斜門扇或開啟弧當邊界')
                        g=geometry[ref['id']];options=[(ref,a,b)]
                        if g.get('closed'):
                            options=[]
                            for n,p in enumerate(g['points']):
                                q=g['points'][(n+1)%len(g['points'])];size=math.dist(p,q)
                                if size>.001 and abs(sum((q[k]-p[k])*normal[k] for k in (0,1)))/size<.002:options.append((dict(id=ref['id'],edge=n),p,q))
                        selected,a,b=min(options,key=lambda option:abs(project([(option[1][k]+option[2][k])/2 for k in (0,1)],normal)-project(center,normal)))
                        chosen.append(selected);groups[index].append(project(a,normal))
                    if any(len(group)!=2 for group in groups):raise ValueError('edge_bounds需要兩對相對的原生直邊')
                    yy=sorted(groups[0]);xx=sorted(groups[1])
                    if min(xx[1]-xx[0],yy[1]-yy[0])<.1:raise ValueError('edge_bounds內區過窄，請重新選擇圍護邊')
                    points=[[x*u[k]+y*v[k] for k in (0,1)] for x,y in ((xx[0],yy[0]),(xx[1],yy[0]),(xx[1],yy[1]),(xx[0],yy[1]))]
                    if chosen!=requested_refs:automatic=dict(reason='由同一原生封閉輪廓的長邊選擇朝向使用區的內緣，避免端頭誤選；不改來源座標',requested_refs=requested_refs)
                    refs=chosen;item['source_binding']['refs']=chosen
                else:points=[p for g in sources for p in g['points']]
                if method=='bounds':
                    x,y=[min(p[k] for p in points) for k in (0,1)]
                    xx,yy=[max(p[k] for p in points) for k in (0,1)]
                    points=[[x,y],[xx,y],[xx,yy],[x,yy]]
                item['points'],item['closed']=points,True
            else:
                raise ValueError('不支援的來源推導方式')
            item['source_ids']=list(dict.fromkeys(item['source_ids']+[r['id'] for r in refs]+expanded))
            item['derivation']=dict(method=method,refs=refs,points=item['points'],
                source_sha256=site['native_dwg']['source_sha256'],coordinates='source-derived; originals unchanged')
            if automatic:item['derivation']['automatic_correction']=automatic
            records.append(dict(id=item['id'],name=item['name'],role=item['role'],**item['derivation']))
        except (KeyError,IndexError,TypeError,ValueError) as exc:
            item['derivation']=None
            errors.append(item['name']+' 原生來源綁定未通過：'+str(exc))
    # Repair only an actually incompatible window host. Extending every wall
    # run can otherwise alter unrelated, already valid walls during revalidation.
    byid={e['id']:e for e in proposal['elements']}
    for opening in proposal['elements']:
        wall=byid.get(opening.get('host_id'))
        if opening['role']!='window' or not opening.get('derivation') or not wall or not wall.get('derivation') or host_compatible(opening,wall):continue
        refs=wall['derivation']['refs']
        if wall['derivation']['method']!='pair' or len(refs)!=2:continue
        sources=[geometry[r['id']] for r in refs]
        if not all(g['kind']=='LINE' and g.get('native_exact') for g in sources):continue
        a,b,first=connected_run(sources[0],geometry);c,d,second=connected_run(sources[1],geometry)
        length=math.dist(a,b);u=[(b[k]-a[k])/length for k in (0,1)];v=[-u[1],u[0]]
        project=lambda p:sum((p[k]-a[k])*u[k] for k in (0,1))
        lo,hi=max(0,min(project(c),project(d))),min(length,max(project(c),project(d)))
        separation=sum(((c[k]+d[k])/2-a[k])*v[k] for k in (0,1))
        points=[[a[k]+t*u[k]+separation/2*v[k] for k in (0,1)] for t in (lo,hi)]
        if hi-lo<.1 or abs(abs(separation)-wall['thickness'])>.001 or not host_compatible(opening,dict(wall,points=points)):continue
        if site.get('correction_batch'):
            from .semantic_batch import region,relevant
            if not relevant(site,opening,region(site)):
                prior=next((e for e in site.get('previous_review',{}).get('candidate',{}).get('elements',[]) if e['id']==wall['id']),None)
                # Keep a previously repaired host stable in later batches. Its
                # full span must be independently reproduced from native runs;
                # outside scope this may only restore those exact prior points.
                if not prior or len(prior['points'])!=2 or min(sum(math.dist(p,q) for p,q in zip(points,prior['points'])),sum(math.dist(p,q) for p,q in zip(points,prior['points'][::-1])))>1e-6:continue
        wall['points']=points;wall['source_ids']=list(dict.fromkeys(wall['source_ids']+first+second))
        wall['derivation'].update(points=points,automatic_correction=dict(reason='僅補齊未對齊窗洞的連續原生宿主牆邊，不移動窗或跨越斷線',expanded_refs=sorted(set(first+second))))
        for row in records:
            if row['id']==wall['id']:row.update(wall['derivation'])
    return errors, records


def host_compatible(opening, wall):
    """A source-derived opening may lie within the real wall band, not on its axis."""
    from shapely.geometry import LineString, Point
    if wall['closed'] or len(wall['points'])!=2 or len(opening['points'])!=2:
        return False
    axis=LineString(wall['points'])
    a,b=wall['points'];c,d=opening['points']
    length=math.dist(a,b);width=math.dist(c,d)
    if min(length,width)<.001:return False
    u=[(b[k]-a[k])/length for k in (0,1)]
    parallel=abs((d[0]-c[0])*u[1]-(d[1]-c[1])*u[0])/width<.035
    return parallel and all(-.001<=sum((p[k]-a[k])*u[k] for k in (0,1))<=length+.001
        and axis.distance(Point(p))<=wall['thickness']/2+.015 for p in opening['points'])
