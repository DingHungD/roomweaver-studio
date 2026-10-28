"""Category-free CAD geometry, local raster and annotation descriptors."""
import math
import re
from collections import Counter

from PIL import Image, ImageFilter, ImageOps
from shapely.geometry import LineString, box as shape_box


VERSION = 'cad-experience-v1'


def text_tokens(text):
    words = re.findall(r'[a-z][a-z0-9_-]*', text.lower())
    for block in re.findall(r'[\u3400-\u9fff]+', text):
        words.extend(block[n:n+2] for n in range(max(1, len(block)-1)))
    return sorted(set(words))[:120]


def select_source(site, bounds, source_ids=()):
    """Select raw CAD by coordinates/references, never interpreted categories."""
    x0, y0, x1, y1 = bounds
    pad = max(.15, min(x1-x0, y1-y0)*.2)
    cx, cy = (x0+x1)/2, (y0+y1)/2
    def nearby(points):
        return points and min(p[0] for p in points) <= x1+pad and max(p[0] for p in points) >= x0-pad and min(p[1] for p in points) <= y1+pad and max(p[1] for p in points) >= y0-pad
    selected = [g for g in site['geometry'] if (g.get('kind')!='HATCH' and nearby(g['points'])) or g['id'] in source_ids]
    selected.sort(key=lambda g: (g['id'] not in source_ids, min((p[0]-cx)**2+(p[1]-cy)**2 for p in g['points'])))
    selected = selected[:160]
    keys = {g['id'] for g in selected}
    arcs = [a for a in (site.get('native_dwg') or {}).get('entities', []) if a.get('kind') == 'ARC' and a['id'] in keys]
    known_arcs={a['id'] for a in arcs}
    # DXF keeps sampled native ARC strokes even without a LibreDWG inventory.
    # Recover their sweep from three native samples, never from an Agent label.
    for g in selected:
        if g['kind']!='ARC' or g['id'] in known_arcs or len(g['points'])<3:continue
        pts=g['points'];(ax,ay),(bx,by),(cx,cy)=pts[0],pts[len(pts)//2],pts[-1]
        den=2*(ax*(by-cy)+bx*(cy-ay)+cx*(ay-by))
        if abs(den)<1e-10:continue
        aa,bb,cc=ax*ax+ay*ay,bx*bx+by*by,cx*cx+cy*cy
        ox=(aa*(by-cy)+bb*(cy-ay)+cc*(ay-by))/den;oy=(aa*(cx-bx)+bb*(ax-cx)+cc*(bx-ax))/den
        angles=[math.atan2(y-oy,x-ox) for x,y in pts]
        sweep=sum(abs(math.atan2(math.sin(b-a),math.cos(b-a))) for a,b in zip(angles,angles[1:]))
        arcs.append(dict(id=g['id'],start_angle=0,end_angle=round(sweep,6)))
    texts = [t for t in site.get('texts', []) if x0-pad <= t['point'][0] <= x1+pad and y0-pad <= t['point'][1] <= y1+pad or t['id'] in source_ids][:40]
    return dict(geometry=selected, arcs=arcs, texts=texts, box=list(bounds))


def geometry_descriptor(raw):
    geometry=[];region=shape_box(*raw['box']).buffer(.15)
    for original in raw['geometry']:
        pts=original['points']
        if len(pts)<2:continue
        clipped=LineString(pts+pts[:1] if original.get('closed') else pts).intersection(region)
        parts=list(clipped.geoms) if hasattr(clipped,'geoms') else [clipped]
        for part in parts:
            if part.is_empty or part.geom_type!='LineString':continue
            local=[list(p) for p in part.coords];closed=local[0]==local[-1]
            geometry.append(dict(original,points=local[:-1] if closed else local,closed=closed))
    points = [p for g in geometry for p in g['points']]
    if not points: raise ValueError('框選區域沒有可比對的原生幾何，請調整範圍')
    xs, ys = zip(*points); span = max(max(xs)-min(xs), max(ys)-min(ys), 1e-6)
    lengths, directions, ends = [], [], []
    closed = 0
    for g in geometry:
        pts = g['points']; closed += bool(g.get('closed'))
        if g.get('kind') == 'ARC': continue
        for a, b in zip(pts, pts[1:]+pts[:1] if g.get('closed') else pts[1:]):
            length = math.dist(a,b)
            if length < span*1e-6: continue
            lengths.append(length/span); directions.append(math.atan2(b[1]-a[1],b[0]-a[0]) % (math.pi/2)); ends.extend((a,b))
    bins = [0.]*12
    for length in lengths: bins[min(11, int(length*12))] += 1
    total = max(1,len(lengths)); bins = [n/total for n in bins]
    nodes = Counter((round((p[0]-min(xs))/span,3),round((p[1]-min(ys))/span,3)) for p in ends)
    arc_sweeps = [((a['end_angle']-a['start_angle']) % (2*math.pi))/(2*math.pi) for a in raw['arcs']]
    sweep_bins = [sum(n/8 <= v < (n+1)/8 for v in arc_sweeps)/max(1,len(arc_sweeps)) for n in range(8)]
    width, height = max(xs)-min(xs), max(ys)-min(ys)
    vector = bins+sweep_bins+[
        min(width,height)/max(width,height,1e-6),closed/max(1,len(raw['geometry'])),
        len(raw['arcs'])/max(1,len(raw['geometry'])),
        sum(v>1 for v in nodes.values())/max(1,len(nodes)),
        min(1,math.log1p(len(lengths))/8),min(1,math.log1p(len(raw['geometry']))/6),
    ]
    # Store normalized raw shapes for the Agent; absolute coordinates and
    # confirmed dimensions from this case must not become another case's target.
    normalized = [dict(kind=g['kind'],closed=bool(g.get('closed')),points=[[round((p[0]-min(xs))/span,5),round((p[1]-min(ys))/span,5)] for p in g['points'][:64]]) for g in geometry[:40]]
    return dict(version=VERSION,vector=vector,arc_flag=int(bool(raw['arcs'])),edge_bin=min(24,int(math.log2(max(1,len(lengths))))),geometry_count=len(raw['geometry']),normalized=normalized)


def crop_source(source, view, bounds, destination):
    a,b,c,d=bounds; padding=max(.15,min(c-a,d-b)*.1)
    a-=padding;b-=padding;c+=padding;d+=padding
    x0,_,_,y1=view['bounds']; scale=view['scale']; pad=view['pad']
    with Image.open(source) as image:
        region=(max(0,int(pad+(a-x0)*scale)),max(0,int(pad+(y1-d)*scale)),min(image.width,math.ceil(pad+(c-x0)*scale)),min(image.height,math.ceil(pad+(y1-b)*scale)))
        if region[2]<=region[0] or region[3]<=region[1]:raise ValueError('局部圖超出原始圖面')
        result=image.crop(region).convert('RGB');result.thumbnail((768,768));result.save(destination)


def image_descriptor(source):
    """Bounded coarse visual comparison; final interpretation still uses vision."""
    with Image.open(source) as image:
        image=ImageOps.autocontrast(ImageOps.grayscale(image)).resize((64,64))
        edge=image.filter(ImageFilter.FIND_EDGES).crop((2,2,62,62))
        vectors=[]
        for angle in (0,90,180,270):
            values=[v/255 for v in edge.rotate(angle).resize((8,8)).getdata()]
            norm=math.sqrt(sum(v*v for v in values))
            vectors.append([round(v/norm,5) if norm else 0 for v in values])
        return vectors


def similarity(query, reference):
    a,b=query['geometry']['vector'],reference['geometry']['vector']
    geom=max(0,1-sum(abs(x-y) for x,y in zip(a,b))/6)
    image=max((sum(x*y for x,y in zip(a,b)) for a in query['image'] for b in reference['image']),default=0)
    ta,tb=set(query['tokens']),set(reference['tokens']);text=len(ta&tb)/max(1,len(ta|tb))
    score=.65*geom+.25*image+.10*text
    return dict(score=round(score,5),geometry=round(geom,5),image=round(image,5),annotations=round(text,5))
