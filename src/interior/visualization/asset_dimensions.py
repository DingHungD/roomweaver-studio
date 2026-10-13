"""Bounded rectangular furniture adaptation, retaining edge bands and original shaders."""
import math

ADAPTABLE = {'table','desk','cabinet','bookcase','wardrobe','shoe_cabinet','nightstand'}

def adaptation(target,asset,policy,*,allow_rotate=True):
    """Plan a uniform fit followed by at most 50% extension along individual axes."""
    if policy.get('purpose') not in ADAPTABLE:raise ValueError('此用途不適合自動改造尺寸，保留等比適配')
    if any(not math.isfinite(v) or v<=0 for v in [*target,*asset]):raise ValueError('尺寸改造缺少有效外框')
    desired=list(policy.get('dimensions') or target);source=policy.get('dimension_source','unknown')
    if any(not math.isfinite(v) or v<=0 for v in desired):raise ValueError('目標尺寸無效')
    if source=='confirmed':
        if not policy.get('dimensions') or not policy.get('evidence'):raise ValueError('確認尺寸缺少來源')
        desired=list(policy['dimensions'])
    elif source=='envelope':
        if not policy.get('dimensions') or not policy.get('evidence'):raise ValueError('範圍尺寸缺少來源')
        desired=[min(a,b) for a,b in zip(target,policy['dimensions'])]
    options=[]
    for angle,raw in [(0,list(asset))]+([(90,[asset[1],asset[0],asset[2]])] if allow_rotate else []):
        scale=min(t/a for t,a in zip(desired,raw));fitted=[a*scale for a in raw]
        ratios=[t/a for t,a in zip(desired,fitted)]
        options.append((max(ratios),angle,scale,fitted,ratios))
    stretch,angle,scale,fitted,ratios=min(options,key=lambda x:x[0])
    if stretch>1.5:raise ValueError('尺寸改造超過局部伸展 50% 上限；改試比例更接近的候選')
    return dict(rotation=angle,uniform_scale=scale,source_dimensions=fitted,target_dimensions=desired,
                extension_ratios=ratios,edge_band_metres=.04,dimension_source=source)

def edge_preserving(value,lower,length,target,band=.04):
    """Move vertices piecewise; outer bands translate intact, centre absorbs length."""
    edge=min(band,length*.12,target*.12);x=value-lower
    if x<=edge:return x
    if x>=length-edge:return target-(length-x)
    return edge+(x-edge)*(target-2*edge)/(length-2*edge)

def apply(meshes,lo,hi,plan):
    from mathutils import Vector
    extent=hi-lo;desired=plan['target_dimensions'];center=(lo+hi)/2
    anchor=Vector((center.x-desired[0]/2,center.y-desired[1]/2,lo.z))
    for obj in meshes:
        inverse=obj.matrix_world.inverted()
        for vertex in obj.data.vertices:
            world=obj.matrix_world@vertex.co
            vertex.co=inverse@Vector([anchor[i]+edge_preserving(world[i],lo[i],extent[i],desired[i],plan['edge_band_metres']) for i in range(3)])
        obj.data.update()
