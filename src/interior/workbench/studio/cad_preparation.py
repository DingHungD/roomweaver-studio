"""Evidence-based 2D CAD preparation; never edits source coordinates or dimensions."""
from collections import Counter
import math
import re

from ezdxf.path import make_path, from_hatch_boundary_path
from shapely import constrained_delaunay_triangles, make_valid
from shapely.geometry import LineString, Point, Polygon
from shapely.errors import GEOSException
from shapely.ops import polygonize, unary_union

FACTORS=dict(mm=.001,cm=.01,m=1,inch=.0254,foot=.3048)
ROOM=re.compile(r'^(?:客廳|主臥室?|臥室.{0,3}|兒童房|書房|廚房|浴廁|衛浴|浴室|餐廳|玄關|陽台|前陽台|後陽台|living(?: room)?|bedroom.{0,8}|kitchen|bathroom|study|balcony)$',re.I)
VOID=re.compile(r'挑空|天井|管道間|電梯井|void|shaft',re.I)
UNIT=re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(mm|cm|m|公分|毫米|公尺|英吋|inch|inches)\b',re.I)


def polygons(shape):
    if shape.geom_type=='Polygon':return [shape]
    return [p for child in getattr(shape,'geoms',[]) for p in polygons(child)]


def convex_parts(shape,factor):
    """Merge adjacent constrained triangles without changing their footprint."""
    parts=list(constrained_delaunay_triangles(shape).geoms)
    # Intersections of coincident drafting strokes can produce numerical slivers.
    # Only sub-square-millimetre pieces can be retired; total loss is verified.
    dropped=sum(p.area for p in parts if p.area*factor**2<1e-8)
    parts=[p for p in parts if p.area*factor**2>=1e-8]
    if dropped*factor**2>1e-6:raise ValueError('地板細碎區合計超過數值容差，需核對來源')
    changed=True
    while changed:
        changed=False;edge_map={}
        for i,p in enumerate(parts):
            coords=list(p.exterior.coords)
            for a,b in zip(coords,coords[1:]):edge_map.setdefault(tuple(sorted((a,b))),[]).append(i)
        used=set();merged=[]
        for indices in edge_map.values():
            if len(indices)!=2:continue
            a,b=indices
            if a in used or b in used:continue
            joined=parts[a].union(parts[b])
            if joined.geom_type=='Polygon' and not joined.interiors and len(joined.exterior.coords)<=100 and abs(joined.convex_hull.area-joined.area)<max(1e-8,joined.area*1e-10):
                merged.append(joined);used.update((a,b));changed=True
        parts=[p for i,p in enumerate(parts) if i not in used]+merged
    return parts


def evidence(doc):
    texts=[];dimensions=[];anchors=[]
    for e in doc.modelspace():
        kind=e.dxftype()
        if kind in ('TEXT','MTEXT'):
            texts.append(dict(handle=e.dxf.handle,text=e.plain_text(),point=list(e.dxf.insert)[:2]))
        elif kind=='DIMENSION' and e.dimtype in (0,1):
            a=e.dxf.get('defpoint2');b=e.dxf.get('defpoint3')
            if a is None or b is None:continue
            raw=float(e.get_measurement())
            if not math.isfinite(raw) or raw<=0:continue
            labels=[]
            block=e.get_geometry_block()
            if block:
                labels=[x.plain_text() for x in block if x.dxftype() in ('TEXT','MTEXT')]
            text=e.dxf.text.strip() or ' / '.join(labels) or f'{raw:g}'
            match=UNIT.search(text)
            unit=None;display=None
            if match:
                display=float(match[1]);unit={'公分':'cm','毫米':'mm','公尺':'m','英吋':'inch','inches':'inch'}.get(match[2].lower(),match[2].lower())
                # A displayed unit is only a scale anchor when its number equals
                # the actual dimension, accounting for the dimension style.
                factor=float(e.override().get('dimlfac',1) or 1)
                if abs(display-raw*abs(factor))<=max(.02,display*.001):
                    anchors.append(dict(unit=unit,raw_to_metres=display*FACTORS[unit]/raw,handle=e.dxf.handle,text=text))
            override=e.dxf.text.strip()
            conflict=None
            if override and override not in ('<>',' '):
                num=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|m|公分|毫米|公尺|英吋|inch)?\s*',override,re.I)
                factor=float(e.override().get('dimlfac',1) or 1)
                if num and abs(float(num[1])-raw*abs(factor))>max(.02,raw*.001):conflict='標註覆寫值與端點幾何不符，未移動端點'
            dimensions.append(dict(handle=e.dxf.handle,text=text,raw_measurement=raw,start=list(a)[:2],end=list(b)[:2],conflict=conflict))
    return texts,dimensions,anchors


def prepare(doc,strict,unit_hint=None):
    """Return derived primitives and an inspectable ledger, keeping numeric XY intact."""
    texts,dimensions,anchors=evidence(doc)
    header=strict['detected_units']
    anchor_units={a['unit'] for a in anchors if abs(a['raw_to_metres']-FACTORS[a['unit']])<1e-8}
    explicit=next(iter(anchor_units)) if len(anchor_units)==1 else None
    units=unit_hint or explicit or header or 'mm'
    factor=FACTORS[units]
    tolerance=.001/factor
    basic={f['id']:f for f in strict['features']}
    source_issues={i['handle']:i for i in strict['issues']}
    actions=[];questions=[];features=[];issues=[];hatches=[];linework=[];counts=Counter()
    linear=list(doc.modelspace().query('LINE'))
    xyz=[tuple(v) for e in linear for v in (e.dxf.start,e.dxf.end)]
    if not xyz:xyz=[(p[0],p[1],0) for f in strict['features'] for p in f['points']]
    span=max((max((p[i] for p in xyz),default=0)-min((p[i] for p in xyz),default=0) for i in (0,1)),default=0)
    zero=sum(abs(p[2])<1e-7 for p in xyz)/max(1,len(xyz))
    zspan=max((p[2] for p in xyz),default=0)-min((p[2] for p in xyz),default=0)
    tilted_solids=any(e.dxftype() in ('3DSOLID','BODY','REGION','MESH','3DFACE') for e in doc.modelspace())
    allow_projection=zero>=.8 and zspan<=span*.05 and not tilted_solids

    def flattened(path):
        result=[]
        for i,p in enumerate(path.flattening(tolerance)):
            if i>=2000:raise ValueError('單一曲線超過 2,000 折線點，需簡化來源')
            result.append(list(p))
        return result

    def emit(e,pts,closed,suffix='',role=None):
        pts=[list(p) for p in pts]
        if len(pts)>1 and math.dist(pts[0][:2],pts[-1][:2])<1e-8:
            pts=pts[:-1];closed=True
        clean=[]
        for p in pts:
            xy=[float(p[0]),float(p[1])]
            if not all(math.isfinite(v) and abs(v)<1e8 for v in xy):raise ValueError('CAD 座標非有限數值或超出範圍')
            if not clean or math.dist(clean[-1],xy)>1e-8:clean.append(xy)
        if len(clean)<2:
            counts['collapsed']+=1;return
        z=[float(p[2]) if len(p)>2 else 0 for p in pts]
        if any(abs(v)>1e-7 for v in z):
            if not allow_projection:
                issues.append(dict(handle=e.dxf.handle,layer=e.dxf.layer,kind=e.dxftype(),reason='高程可能代表不同樓層或立體內容，缺乏自動投影證據'));return
            counts['projected']+=1
            actions.append(dict(handle=e.dxf.handle,action='project_xy',z_range=[min(z),max(z)],reason='至少八成 LINE 端點位於 Z=0，起伏低於圖幅 5%，無立體實體；僅衍生 XY，不回寫來源'))
        pieces=[clean]
        if len(clean)>100:
            if closed:
                shape=Polygon(clean)
                if not shape.is_valid:raise ValueError('曲線輪廓存在自交，需核對來源')
                pieces=[list(p.exterior.coords)[:-1] for p in constrained_delaunay_triangles(shape).geoms]
            else:pieces=[clean[i:i+90] for i in range(0,len(clean)-1,89)]
        for i,p in enumerate(pieces):
            identifier='e-'+e.dxf.handle+suffix+(f'-part-{i}' if len(pieces)>1 else '')
            f=dict(id=identifier,layer=e.dxf.layer,kind=e.dxftype(),points=[list(v) for v in p],closed=closed,source_handle=e.dxf.handle)
            if role:f['suggested_role']=role
            if max(max(v[k] for v in p)-min(v[k] for v in p) for k in (0,1))*factor<.005:
                f['suggested_role']='ignore';counts['drafting_details']+=1
            f['prepared_geometry']=True
            features.append(f)
        if not suffix and e.dxftype() in ('LINE','LWPOLYLINE','POLYLINE','ARC','CIRCLE','ELLIPSE','SPLINE'):
            seq=clean+([clean[0]] if closed else [])
            linework.append(LineString(seq))

    for e in doc.modelspace():
        kind=e.dxftype();identifier='e-'+e.dxf.handle
        if kind in ('TEXT','MTEXT','DIMENSION'):continue
        if kind in ('ATTDEF','ATTRIB','SOLID','TRACE'):
            # SOLID/TRACE are display/arrow fills, not approved wall footprints.
            counts['reference_only']+=1
            if kind in ('SOLID','TRACE'):
                pts=list(e.wcs_vertices(close=False));emit(e,pts,True,role='ignore')
            continue
        if e.dxf.is_supported('extrusion') and tuple(e.dxf.get('extrusion',(0,0,1))) not in ((0,0,1),(0.0,0.0,1.0)):
            issues.append(dict(handle=e.dxf.handle,layer=e.dxf.layer,kind=kind,reason='傾斜 OCS 平面，不能自動當作水平平面'));continue
        if kind=='HATCH':
            try:
                rings=[]
                for j,boundary in enumerate(e.paths):
                    path=from_hatch_boundary_path(boundary,e.ocs(),elevation=e.dxf.elevation.z)
                    pts=flattened(path)
                    emit(e,pts,True,suffix=f'-boundary-{j}',role='ignore')
                    if len(pts)<4:continue
                    raw=Polygon([(p[0],p[1]) for p in pts]);shape=make_valid(raw)
                    rings.append((boundary.path_type_flags,shape))
                    if not raw.is_valid:counts['hatch_intersections']+=1
                # Deduplicate coincident external loops before resolving holes.
                external=unary_union([g for flags,g in rings if flags&1] or [g for flags,g in rings if flags&16] or [g for _,g in rings])
                holes=unary_union([g for flags,g in rings if not flags&1 and external.contains(g) and not external.equals(g)])
                shape=external if e.dxf.hatch_style==2 else external.difference(holes)
                hatches.append(dict(handle=e.dxf.handle,shape=shape,pattern=e.dxf.pattern_name,solid=bool(e.dxf.solid_fill),layer=e.dxf.layer))
                counts['hatches']+=1
            except (ValueError,TypeError,AttributeError,GEOSException) as exc:
                issues.append(dict(handle=e.dxf.handle,layer=e.dxf.layer,kind=kind,reason='填色邊界無法可靠解析：'+str(exc)[:120]))
            continue
        if identifier in basic:
            f=basic[identifier]
            # Existing straight primitives retain exact source vertices and IDs.
            emit(e,f['points'],f['closed'])
            continue
        if kind in ('LINE','LWPOLYLINE','POLYLINE','ARC','CIRCLE','ELLIPSE','SPLINE'):
            if e.dxf.is_supported('thickness') and e.dxf.get('thickness',0):
                issues.append(dict(handle=e.dxf.handle,layer=e.dxf.layer,kind=kind,reason='有實體厚度，不自動當作平面線'));continue
            if kind=='LWPOLYLINE' and (e.dxf.get('const_width',0) or any(p[2] or p[3] for p in e.get_points())):
                if re.search(r'wall|牆',e.dxf.layer,re.I):
                    issues.append(dict(handle=e.dxf.handle,layer=e.dxf.layer,kind=kind,reason='牆圖層的多段線有線寬，需確認是中心線或牆體外框'));continue
                pts=flattened(make_path(e))
                emit(e,pts,bool(e.closed),role='ignore');counts['reference_widths']+=1
                continue
            try:
                path=make_path(e)
                pts=flattened(path)
                emit(e,pts,path.is_closed)
                if kind!='LINE':counts['curves']+=1
            except (ValueError,TypeError,AttributeError,NotImplementedError) as exc:
                issues.append(dict(handle=e.dxf.handle,layer=e.dxf.layer,kind=kind,reason='不能可靠轉為折線：'+str(exc)[:120]))
            continue
        issues.append(source_issues.get(e.dxf.handle) or dict(handle=e.dxf.handle,layer=e.dxf.layer,kind=kind,reason='目前不支援此 CAD 元件，未自動刪除'))

    # Room labels seed bounded faces; drawing frames and dimension grids without
    # room labels cannot become a floor simply because they are the largest face.
    labels=[t for t in texts if ROOM.fullmatch(t['text'].strip())]
    voids=[Point(t['point']) for t in texts if VOID.search(t['text'])]
    regions=[]
    existing_floor=any(f.get('suggested_role')!='ignore' and re.search(r'(?:^|[\s_-])floor(?:$|[\s_-])',f['layer'],re.I) and f['closed'] for f in features)
    if not existing_floor:
        faces=list(polygonize(unary_union(linework))) if linework else []
        support=unary_union(linework).buffer(.10/factor) if linework else Polygon()
        for t in labels:
            hit=[p for p in faces if p.covers(Point(t['point'])) and p.area*factor**2>=1]
            shape=min(hit,key=lambda p:p.area) if hit else None
            # A room label may sit inside a bed/table outline. Dimension endpoint
            # intervals can recover its surrounding room if all four sides have
            # nearby drawing support and no other room label is swallowed.
            xs=[];ys=[]
            for d in dimensions:
                a,b=d['start'],d['end']
                if abs(abs(a[0]-b[0])-d['raw_measurement'])<.001:xs.append((min(a[0],b[0]),max(a[0],b[0]),d['handle']))
                if abs(abs(a[1]-b[1])-d['raw_measurement'])<.001:ys.append((min(a[1],b[1]),max(a[1],b[1]),d['handle']))
            rectangles=[]
            for x0,x1,hx in xs:
                if not x0<=t['point'][0]<=x1:continue
                for y0,y1,hy in ys:
                    if not y0<=t['point'][1]<=y1:continue
                    rect=Polygon([(x0,y0),(x1,y0),(x1,y1),(x0,y1)])
                    if not 2<=rect.area*factor**2<=80:continue
                    if any(v is not t and rect.contains(Point(v['point'])) for v in labels):continue
                    if any(rect.contains(v) for v in voids):continue
                    coords=list(rect.exterior.coords)
                    fractions=[LineString([a,b]).intersection(support).length/max(1e-8,math.dist(a,b)) for a,b in zip(coords,coords[1:])]
                    if min(fractions)>=.5:rectangles.append((rect,hx,hy))
            if rectangles:
                rect,hx,hy=max(rectangles,key=lambda v:v[0].area)
                if shape is None or rect.area>shape.area*1.5:
                    regions.append(dict(name=t['text'],shape=rect,source='dimension_supported_outline',handles=[t['handle'],hx,hy]));continue
            if shape is not None:regions.append(dict(name=t['text'],shape=shape,source='bounded_room_lines',handles=[t['handle']]))
        for h in hatches:
            if h['solid']:continue
            parts=[p for p in polygons(h['shape']) if p.area*factor**2>=1 and not any(p.covers(v) for v in voids)]
            for p in parts:
                names=[t['text'] for t in labels if p.covers(Point(t['point']))]
                floor_layer=bool(re.search('floor|地板|地坪',h['layer'],re.I))
                wood=bool(re.search('WOOD|PARQUET|HBONE',h['pattern'],re.I))
                if names or floor_layer or wood:
                    regions.append(dict(name='／'.join(names) or '木地板填色區',shape=p,source='hatch_boundary',handles=[h['handle']]))
        floor=unary_union([r['shape'] for r in regions])
        floor_polys=polygons(floor)
        # Triangulation preserves concavity and holes; never fills a convex hull.
        for i,p in enumerate(floor_polys):
            triangles=convex_parts(p,factor)
            if abs(sum(t.area for t in triangles)-p.area)*factor**2>1e-6:raise ValueError('地板分解面積不一致，未套用推定範圍')
            for j,t in enumerate(triangles):
                features.append(dict(id=f'cad-floor-{i}-{j}',layer='floor',kind='INFERRED_FLOOR',points=[list(v) for v in list(t.exterior.coords)[:-1]],closed=True,suggested_role='floor',floor_region=f'cad-floor-{i}',prepared_geometry=True))
        if floor_polys:
            inferred=[r['name'] for r in regions if r['source']=='dimension_supported_outline']
            questions.append(dict(id='cad-floor-outline',text='請核對淡色地板推定範圍'+('，其中'+ '、'.join(inferred)+'依尺寸端點與四側線圖推定' if inferred else '')+'；孔洞與不連通區仍保留，不以大外框填滿。',kind='floor'))
        else:questions.append(dict(id='cad-floor-missing',text='缺少足以封閉的室內邊界或空間標籤，無法安全推定地板。',kind='floor'))
    unit_needed=not header or (header and explicit and explicit!=header) or len(anchor_units)>1 or (not explicit and bool(dimensions))
    if unit_needed:questions.append(dict(id='cad-units',text='尺寸標註沒有一致的明確單位，或與 CAD 標頭不同；請確認實際單位。',kind='units'))
    for d in dimensions:
        if d['conflict']:questions.append(dict(id='cad-dim-'+d['handle'],text=d['text']+'：'+d['conflict'],kind='dimension'))
    # Enforce the same downstream complexity limits after all expansion.
    if not features:raise ValueError('沒有可供確認的平面元件')
    if len(features)>2000 or sum(len(f['points']) for f in features)>20000:raise ValueError('CAD 整理後超過 2,000 元件或 20,000 頂點，請拆分圖面')
    report=dict(version=1,counts=dict(counts),curve_tolerance_raw=tolerance,header_units=header,explicit_units=explicit,
                unit_anchors=anchors,dimensions=dimensions,projection=dict(dominant_zero_ratio=zero,z_span=zspan,allowed=allow_projection),actions=actions,
                floor_area_raw=unary_union([r['shape'] for r in regions]).area if regions else None,
                floor_regions=[dict(id=f'candidate-{i}',name=r['name'],source=r['source'],handles=r['handles'],points=list(r['shape'].exterior.coords)[:-1],holes=[list(v.coords)[:-1] for v in r['shape'].interiors],area_raw=r['shape'].area) for i,r in enumerate(regions)],questions=questions)
    return dict(strict,features=features,issues=issues,detected_units=unit_hint or explicit or header,cad_preparation=report)
