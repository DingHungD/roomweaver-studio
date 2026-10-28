"""Source-grounded outlines and question locations, independent of any case."""
import base64
import math
from pathlib import Path
from xml.sax.saxutils import escape

from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union
from shapely.validation import explain_validity

from ..storage import write_json


def referenced_lines(site,identifiers):
    lines=[]
    for g in site['geometry']:
        if g['id'] not in identifiers or len(g['points'])<2:continue
        points=g['points']+g['points'][:1] if g['closed'] else g['points']
        lines.append(LineString(points))
    return lines


def floor_proof(site,proposal,reference_geometry=()):
    """A provisional floor may be replaced only by an evidenced outline candidate."""
    original=unary_union([Polygon(f['points'],f.get('holes',[])) for f in site['floors']])
    outline=proposal.get('floor_outline')
    if not outline:
        if not site.get('native_dwg'):return original,[],None
        # An inferred tessellation is not proof of the building perimeter.
        support=referenced_lines(site,{g['id'] for g in site['geometry']
            if g.get('kind') not in ('INFERRED_FLOOR',) and g.get('source_role')!='floor'})
        unsupported=original.boundary.difference(unary_union(support).buffer(.08)) if support else original.boundary
        walls=[LineString(e['points']).buffer(e['thickness']/2+.08) if not e['closed'] else Polygon(e['points']).buffer(.08)
               for e in proposal['elements'] if e['role']=='wall']
        outer=unary_union([p.exterior for p in getattr(original,'geoms',[original]) if p.geom_type=='Polygon'])
        gaps=outer.difference(unary_union(walls)) if walls else outer
        sufficient=unsupported.length<=max(.03,original.length*.02) and gaps.length<=max(.1,outer.length*.05)
        def segments(value):return [list(g.coords) for g in getattr(value,'geoms',[value]) if g.geom_type=='LineString'][:30]
        proof=dict(status='preview' if sufficient else 'blocked',evidence_sufficient=sufficient,user_confirmed=bool(site.get('floor_locked',True)),
                   area_m2=original.area,previous_area_m2=original.area,unsupported_boundary_m=unsupported.length,
                   unsupported_segments=segments(unsupported),exterior_wall_gaps=segments(gaps),
                   source_ids=[],evidence='由原生線條及牆帶核對既有推定範圍')
        return original,([] if sufficient else ['地板範圍證據不足，需對照原生外牆與門檻核對']),proof
    known={g['id'] for g in site['geometry']}
    errors=[];shape=Polygon(outline['points'],outline['holes'])
    if not shape.is_valid or shape.is_empty or shape.area<.1:raise ValueError('地板候選輪廓無效：'+explain_validity(shape))
    if not set(outline['source_ids']).issubset(known):raise ValueError('地板候選引用不存在的來源線條')
    if not all(math.isfinite(v) for ring in [outline['points'],*outline['holes']] for p in ring for v in p):raise ValueError('地板候選有非有限座標')
    if site.get('floor_locked',True) and original.symmetric_difference(shape).area>1e-6:errors.append('地板範圍已確認，不能以候選改寫')
    support=referenced_lines(site,set(outline['source_ids']))
    # Only verified model segments supplement CAD support. A partially measured
    # reference does not prove the remainder of its candidate boundary.
    support.extend(LineString(line) for record in reference_geometry if record['collection']=='floor_outline' for line in record.get('support_lines',[]))
    # Door/window thresholds may bridge a genuine break in the source outlines,
    # but a fabricated opening cannot prove the whole perimeter of a building.
    support.extend(LineString(e['points']) for e in proposal['elements'] if e['role'] in ('door','window') and len(e['points'])==2)
    missing=shape.boundary.difference(unary_union(support).buffer(.08)) if support else shape.boundary
    added=[]
    # A missed citation is different from missing geometry. Add only native
    # strokes that actually coincide with the candidate perimeter; no resizing.
    if missing.length>.03 and len(outline['source_ids'])<100:
        for g in site['geometry']:
            if g['id'] in outline['source_ids'] or g['kind'] in ('HATCH','INFERRED_FLOOR') or g.get('source_role')=='floor':continue
            line=LineString(g['points']+g['points'][:1] if g['closed'] else g['points'])
            if missing.distance(line)>.02 or missing.intersection(line.buffer(.02)).length<.04:continue
            outline['source_ids'].append(g['id']);support.append(line);added.append(g['id'])
            if len(outline['source_ids'])>=100:break
    unsupported=shape.boundary.difference(unary_union(support).buffer(.08)).length if support else shape.length
    if unsupported>max(.03,shape.length*.02):errors.append(f'地板候選外框有 {unsupported:.2f} m 缺少來源邊線，請對照原圖修正')
    walls=[LineString(e['points']).buffer(e['thickness']/2+.08) if not e['closed'] else Polygon(e['points']).buffer(.08) for e in proposal['elements'] if e['role']=='wall']
    wall_gaps=shape.exterior.difference(unary_union(walls)) if walls else shape.exterior
    if wall_gaps.length>max(.1,shape.exterior.length*.05):errors.append('地板候選外框未貼合已辨認外牆，不能以圖框或任意大外框補滿')
    def segments(value):return [list(g.coords) for g in getattr(value,'geoms',[value]) if g.geom_type=='LineString' and not g.is_empty][:30]
    proof=dict(area_m2=shape.area,previous_area_m2=original.area,unsupported_boundary_m=unsupported,unsupported_segments=segments(shape.boundary.difference(unary_union(support).buffer(.08))) if support else [],exterior_wall_gaps=segments(wall_gaps),evidence=outline['evidence'],source_ids=outline['source_ids'],added_source_ids=added,status='blocked' if errors else 'preview',evidence_sufficient=not errors,user_confirmed=bool(site.get('floor_locked',True)))
    return (original if site.get('floor_locked',True) else shape),errors,proof


def questions_on_source(site,proposal):
    """Only Agent-declared uncertainty becomes a human question; checks stay checks."""
    sources={g['id']:g.get('points') or [g['point']] for kind in ('geometry','texts','dimensions') for g in site[kind] if g.get('points') or g.get('point')}
    sources.update({d['id']:[d['start'],d['end']] for d in site['dimensions']})
    result=[];seen=set()
    for i,raw in enumerate(proposal['questions']):
        if isinstance(raw,str):
            items=[e for e in proposal['elements']+proposal['rooms'] if e['name'] in raw]
            q=dict(id='legacy-'+str(i+1),title=raw[:80],ask=raw,reason='上一版文字疑點，尚未提供完整定位證據',source_ids=list(dict.fromkeys(s for e in items for s in e['source_ids'])),box=None)
        else:q=dict(raw)
        if q['id'] in seen:raise ValueError('疑點 ID 重複')
        seen.add(q['id'])
        if not set(q['source_ids']).issubset(sources):raise ValueError('疑點引用不存在的來源 ID')
        pts=[p for s in q['source_ids'] for p in sources[s]]
        box=q.get('box')
        if box:
            if not all(math.isfinite(v) for v in box) or not(box[0]<box[2] and box[1]<box[3]):raise ValueError('疑點定位框無效')
            supports=[LineString(sources[s]) if len(sources[s])>1 else Point(sources[s][0]) for s in q['source_ids']]
            if supports and not Polygon([(box[0],box[1]),(box[2],box[1]),(box[2],box[3]),(box[0],box[3])]).buffer(.1).intersects(unary_union(supports)):raise ValueError('疑點定位與引用來源不相交')
        elif pts:
            box=[min(p[0] for p in pts)-.1,min(p[1] for p in pts)-.1,max(p[0] for p in pts)+.1,max(p[1] for p in pts)+.1]
        q.update(label='Q'+str(i+1),box=box,located=bool(box));result.append(q)
    return result


def room_access(proposal,floor):
    """Find rooms sealed by modeled architecture; this is topology, not code compliance."""
    from .cad_preparation import polygons
    solids=[]
    for e in proposal['elements']:
        if e['role']!='wall':continue
        wall=Polygon(e['points']) if e['closed'] else LineString(e['points']).buffer(e['thickness']/2,cap_style=2,join_style=2)
        for door in proposal['elements']:
            if door['role']=='door' and door['host_id']==e['id'] and door['base']<=.05:
                axis=LineString(e['points'])
                offset=max(axis.distance(Point(p)) for p in door['points']) if not e['closed'] else 0
                wall=wall.difference(LineString(door['points']).buffer(e['thickness']/2+.02+offset,cap_style=2))
        solids.append(wall)
    # Sub-centimetre drafting/join tolerances are not an actual entrance.
    # This changes only the diagnostic clearance, never the source geometry.
    free=floor.buffer(-.01).difference(unary_union(solids).buffer(.01))
    spaces=[p for p in polygons(free) if p.area>.1]
    if len(spaces)<2:return []
    main=max(spaces,key=lambda p:p.area);findings=[]
    for r in proposal['rooms']:
        region=Polygon(r['points']);inside=region.intersection(free)
        if inside.is_empty:continue
        component=max(spaces,key=lambda p:p.intersection(region).area)
        if component!=main and region.intersection(component).area>region.area*.6:
            findings.append(dict(room_id=r['id'],name=r['name'],box=list(region.bounds),reason='目前牆體將此空間與主要活動區隔離；請對照原圖找門洞或開放通道，不能為通過檢查而任意開門',source_ids=r['source_ids']))
    return findings


def write_question_overlay(source,view,questions,directory):
    """Create a derived SVG over an unchanged source rendering; never edit inputs."""
    if not view:return
    source=Path(source);directory=Path(directory)
    encoded=base64.b64encode(source.read_bytes()).decode('ascii')
    width,height=view['width'],view['height'];x0,y0,x1,y1=view['bounds'];scale=view['scale'];pad=view['pad']
    def xy(x,y):return pad+(x-x0)*scale,pad+(y1-y)*scale
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"><image width="{width}" height="{height}" href="data:image/png;base64,{encoded}"/>']
    for q in questions:
        if not q['box']:continue
        a,b,c,d=q['box'];x,y=xy(a,d);w=(c-a)*scale;h=(d-b)*scale
        parts.append(f'<g><title>{escape(q["ask"])}</title><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#d9483218" stroke="#d94832" stroke-width="3" stroke-dasharray="9 5"/><rect x="{x}" y="{max(0,y-28)}" width="46" height="28" rx="5" fill="#b93b29"/><text x="{x+6}" y="{max(0,y-28)+21}" font-family="sans-serif" font-size="20" fill="white">{q["label"]}</text></g>')
    parts.append('</svg>')
    (directory/'questions.svg').write_text(''.join(parts),encoding='utf-8')
    write_json(directory/'questions.json',dict(coordinate_system='local metres XY, +Y up',source_view=view,questions=questions))


def focus_images(source,view,previous,directory):
    """Bounded crops retain original coordinates and pixels for Agent reinspection."""
    from PIL import Image
    if not previous or not view:return [],[]
    candidate=previous['candidate'];report=previous['report'];boxes=[q['box'] for q in report.get('questions',[]) if q.get('box')]
    for item in candidate['elements']+candidate['rooms']:
        if any(item['name'] in e for e in report.get('repair_errors',report['errors'])):
            pts=item['points'];boxes.append([min(p[0] for p in pts)-.25,min(p[1] for p in pts)-.25,max(p[0] for p in pts)+.25,max(p[1] for p in pts)+.25])
    selected=[]
    for box in boxes:
        shape=Polygon([(box[0],box[1]),(box[2],box[1]),(box[2],box[3]),(box[0],box[3])])
        if any(shape.intersection(s).area/max(1e-6,shape.union(s).area)>.75 for _,s in selected):continue
        selected.append((box,shape))
        if len(selected)==6:break
    images=[];records=[]
    with Image.open(source) as image:
        for i,(box,_) in enumerate(selected):
            x0,y0,x1,y1=view['bounds'];scale=view['scale'];pad=view['pad']
            a,b,c,d=box
            pixels=[max(0,int(pad+(a-x0)*scale)),max(0,int(pad+(y1-d)*scale)),min(image.width,int(pad+(c-x0)*scale)+1),min(image.height,int(pad+(y1-b)*scale)+1)]
            if pixels[2]-pixels[0]<2 or pixels[3]-pixels[1]<2:continue
            crop=image.crop(pixels);crop.thumbnail((1400,1400));path=Path(directory)/f'focus-{i+1:02d}.png';crop.save(path)
            images.append(str(path));records.append(dict(image=path.name,box=box,source_pixels=pixels))
    return images,records
