"""Evidence-requested concept props, fitted without shrinking below plausible sizes."""
import bpy
from mathutils import Vector


def populate(spec, lo, hi, thickness, scale, width, depth, board, assets=None, host=None, created=None):
    """Build separate tier contents; report insufficient clearance, never alter the host."""
    palette={}
    for name,color,metal,rough in [('enamel',(.36,.39,.41),.45,.28),('glass',(.015,.022,.027),.15,.19),('chrome',(.6,.62,.65),.85,.22),('paper',(.82,.79,.71),0,.9),('blue',(.035,.12,.18),0,.5),('clay',(.28,.08,.035),0,.65)]:
        mat=bpy.data.materials.new('Concept appliance '+name);mat.use_nodes=True
        shader=mat.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(*color,1)
        shader.inputs['Metallic'].default_value=metal;shader.inputs['Roughness'].default_value=rough
        palette[name]=mat
    sizes=hi-lo;unit=[max(abs(s),1e-5) for s in scale]
    available=[(sizes[i]-2*thickness[i])*unit[i] for i in (width,depth)]
    clear_height=(sizes.z-thickness[2])*.25*unit[2]-thickness[2]*unit[2]
    reports=[]
    for kind in spec.get('contents',[]):
        w,d,h,tier={'microwave':(.46,.36,.28,1),'coffee_machine':(.22,.32,.34,2),'magazines':(.21,.29,.075,0)}[kind]
        fallback=None
        choices=(assets or {}).get(kind,[])
        if isinstance(choices,dict):choices=[choices]
        failures=[];placed=None
        for asset in choices if host is not None else []:
            try:
                from realism_assets import place
                placed=place(asset,kind,host,lo,hi,thickness,width,depth,spec['front'],tier,created)
                placed['candidate_failures']=failures;break
            except (ValueError,OSError,RuntimeError) as exc:
                failures.append(dict(source_url=asset.get('source_url'),reason=str(exc)));fallback=str(exc)
        if placed:reports.append(placed);continue
        if available[0]<w+.02 or available[1]<d+.02 or clear_height<h+.02:
            reports.append(dict(kind=kind,status='needs_space',reason='層板淨空不足；保留原尺寸，不縮小家電',required=[w,d,h],available=[*available,clear_height]));continue
        base=lo.z+(sizes.z-thickness[2])*.25*tier+thickness[2]
        def part(label, bounds, color):
            # x runs across width; y runs from back to user-facing edge.
            a=lo.copy();b=hi.copy()
            for i,axis in enumerate((width,depth,2)):
                start,end=bounds[i],bounds[i+3]
                if axis==2:a.z=base+start/unit[2];b.z=base+end/unit[2]
                elif axis==width:
                    a[axis]=(lo[axis]+hi[axis])/2+(start-w/2)/unit[axis];b[axis]=(lo[axis]+hi[axis])/2+(end-w/2)/unit[axis]
                elif spec['front'][0]=='+':
                    a[axis]=hi[axis]-thickness[axis]-.015/unit[axis]-(d-start)/unit[axis];b[axis]=hi[axis]-thickness[axis]-.015/unit[axis]-(d-end)/unit[axis]
                else:
                    a[axis]=lo[axis]+thickness[axis]+.015/unit[axis]+(d-end)/unit[axis];b[axis]=lo[axis]+thickness[axis]+.015/unit[axis]+(d-start)/unit[axis]
            node=board(kind+' '+label,a,b)
            node.data.materials.clear();node.data.materials.append(palette[color]);node['studio_concept_content']=kind
        if kind=='microwave':
            part('housing',(0,0,0,w,d-.008,h),'enamel')
            part('door glass',(.018,d-.008,.025,w-.095,d,h-.025),'glass')
            part('handle',(w-.12,d,.05,w-.105,d+.009,h-.05),'chrome')
            part('display',(w-.08,d-.008,h-.075,w-.012,d,h-.022),'glass')
            for j in range(4):part('button', (w-.068,d,.07+j*.022,w-.03,d+.002,.08+j*.022),'chrome')
            for j in range(7):part('vent',(.02+j*.045,.015,h-.004,.047+j*.045,.08,h),'glass')
        elif kind=='coffee_machine':
            part('housing',(0,0,.025,w,d*.7,h),'enamel')
            part('recess',(.022,d*.7,.075,w-.022,d*.7+.003,h-.08),'glass')
            part('head',(0,d*.65,h-.1,w,d,h-.045),'glass')
            part('nozzle',(w*.45,d*.86,h-.15,w*.55,d*.92,h-.095),'chrome')
            part('tray',(0,d*.65,.008,w,d,.025),'chrome')
            part('cup',(.07,d*.74,.025,.15,d*.94,.095),'paper')
            part('coffee',(.075,d*.755,.094,.145,d*.925,.096),'glass')
            for j in range(3):part('button',(.035+j*.06,d*.71,h-.035,.055+j*.06,d*.72,h-.016),'chrome')
        else:
            for j in range(5):
                z=j*.015;dx=.004*(j%2)
                part('pages',(dx,.006,z+.002,w-.006,d-.005,z+.012),'paper')
                for dz in (0,.013):part('cover',(dx,0,z+dz,w,d,z+dz+.002),'blue' if j%2 else 'clay')
                part('spine',(dx,d-.003,z,w,d,z+.015),'blue' if j%2 else 'clay')
        reports.append(dict(kind=kind,status='placed',tier=tier,dimensions=[w,d,h],dimension_source='concept_assumption',asset_fallback_reason=fallback,candidate_failures=failures,installation_verified=False))
    return reports
