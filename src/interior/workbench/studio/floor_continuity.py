"""Conservative, source-bound floor seam proposals; never infer a whole slab."""
import hashlib
import json
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union, polygonize, triangulate


def polygons(value):
    if value.geom_type == 'Polygon':
        return [value] if value.area > .0001 else []
    return [p for g in getattr(value, 'geoms', []) for p in polygons(g)]


def inspect(items):
    floors=[i for i in items if i['role']=='floor']
    walls=[i for i in items if i['role']=='wall']
    result=dict(version=1,patches=[],remaining=[],floor_area=0,missing_area=0,repair_area=0,notes=[])
    if not floors:return result
    shapes={f['id']:Polygon(f['points']) for f in floors}
    if any(not p.is_valid for p in shapes.values()):
        result['notes'].append('地板輪廓無效，先修正平面再檢查連續性。');return result
    floor=unary_union(list(shapes.values()));result['floor_area']=floor.area
    lines=[LineString(w['points']) for w in walls if not w['closed']]
    # A convex hull would silently cover yards and recesses. Only closed wall
    # cycles provide an interior bound, with at least some supplied floor.
    cycles=list(polygonize(unary_union(lines)))
    domain=unary_union([p for p in cycles if p.intersection(floor).area>.01])
    if domain.is_empty:
        result['notes'].append('缺少閉合牆線，無法確認室內邊界；未自動推算整片地板。');return result
    solid={w['id']:Polygon(w['points']) if w['closed'] else LineString(w['points']).buffer(w['thickness']/2,cap_style=2,join_style=2) for w in walls}
    if any(not p.is_valid for p in solid.values()):
        result['notes'].append('牆體輪廓無效，未提出補片。');return result
    by_id={w['id']:w for w in walls}
    for opening in items:
        if opening['role']!='door' or opening['base']>.01 or opening.get('host_id') not in solid:continue
        host=by_id[opening['host_id']]
        if host['closed']:continue  # Arbitrary thick/compound hosts need a measured cut.
        solid[host['id']]=solid[host['id']].difference(LineString(opening['points']).buffer(host['thickness']/2+.005,cap_style=2))
    occupied=unary_union(list(solid.values()))
    missing=domain.difference(floor.union(occupied))
    # Close only seams <=20 cm that have floor on both sides. Do not expand
    # the exterior boundary or fill one-sided entrance/outdoor thresholds.
    closed=floor.buffer(.101,join_style=2).buffer(-.101,join_style=2)
    proposal=closed.difference(floor).intersection(missing)
    patches=[]
    for gap in polygons(proposal):
        # Keep enclosed voids explicit; an exterior-only patch must never erase
        # a shaft/courtyard hole when serialized or displayed in the UI.
        if gap.interiors:continue
        neighbours=[f for f in floors if shapes[f['id']].distance(gap)<.00001]
        if len(neighbours)<2 or gap.area>1 or not gap.buffer(-.101).is_empty:continue
        if max(f['height'] for f in neighbours)-min(f['height'] for f in neighbours)>.001:continue
        donor=max(neighbours,key=lambda f:gap.buffer(.00001).intersection(shapes[f['id']].boundary).length)
        coords=[[round(x,6),round(y,6)] for x,y in gap.exterior.coords[:-1]]
        token=hashlib.sha256(json.dumps(coords).encode()).hexdigest()[:20]
        triangles=[list(t.exterior.coords)[:-1] for t in triangulate(gap) if gap.covers(t)]
        if abs(sum(Polygon(t).area for t in triangles)-gap.area)>.00001:continue
        patches.append(dict(id='floor-seam-'+token,name='地板接縫補片',points=coords,triangles=triangles,
            area=gap.area,donor_id=donor['id'],height=donor['height'],neighbours=[f['id'] for f in neighbours]))
    if sum(p['area'] for p in patches)>2:
        result['notes'].append('候選缺口合計超過 2 m²，需重新核對平面，未自動補齊。');patches=[]
    fixed=unary_union([Polygon(p['points']) for p in patches])
    result.update(patches=patches,missing_area=missing.area,repair_area=fixed.area,
        remaining=[dict(area=p.area,points=list(p.exterior.coords)[:-1],reason='單側邊界、開口或非短縫；需核對來源，不自動填滿') for p in polygons(missing.difference(fixed))],
        outline=[list(p.exterior.coords)[:-1] for p in polygons(floor)],
        source_floors=[dict(id=f['id'],points=f['points'],height=f['height']) for f in floors])
    return result
