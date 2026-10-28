"""Keep conflicting fill/outline evidence visible instead of trusting one contour."""
import math
from shapely.geometry import Polygon


def straight_hatch_loops(entity):
    if entity.get('entity')!='HATCH' or not entity.get('is_solid_fill') or entity.get('extrusion',[0,0,1])!=[0,0,1]:return []
    paths=entity.get('paths',[])
    if len(paths)!=1:return []  # Holes and multi-boundary topology need separate support.
    path=paths[0]
    if 'polyline_paths' in path:
        if not path.get('closed') or any(v.get('bulge',0) for v in path['polyline_paths']):return []
        points=[v['point'] for v in path['polyline_paths']]
    else:
        segments=path.get('segs',[])
        if not segments or any(s.get('curve_type')!=1 for s in segments):return []
        if any(math.dist(s['second_endpoint'],segments[(n+1)%len(segments)]['first_endpoint'])>1e-7 for n,s in enumerate(segments)):return []
        points=[s['first_endpoint'] for s in segments]
    shape=Polygon(points)
    return [(0,points)] if shape.is_valid and not shape.is_empty else []


def outline_conflicts(site,source):
    shape=Polygon(source['points']);result=[]
    for fill in site.get('geometry',[]):
        if not fill.get('native_exact_fill'):continue
        solid=Polygon(fill['points'])
        if not solid.is_valid or not .8<solid.area/max(shape.area,1e-9)<1.25:continue
        if shape.intersection(solid).area/min(shape.area,solid.area)<.9:continue
        delta=shape.symmetric_difference(solid).area
        if delta>1e-6 and shape.hausdorff_distance(solid)>.002:
            result.append(dict(id=fill['id'],difference_m2=delta,max_edge_difference_m=shape.hausdorff_distance(solid)))
    return result
