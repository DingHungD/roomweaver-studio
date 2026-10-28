"""Reversible, envelope-preserving shelf studies for evidenced box placeholders."""
import bpy
from mathutils import Vector, Matrix


def eligible_box(obj):
    if obj.type!='MESH' or len(obj.data.vertices)>24 or len(obj.data.vertices)<8:return False
    lo=Vector([min(v.co[i] for v in obj.data.vertices) for i in range(3)])
    hi=Vector([max(v.co[i] for v in obj.data.vertices) for i in range(3)])
    return all(hi[i]-lo[i]>.05 for i in range(3)) and all(all(min(abs(v.co[i]-lo[i]),abs(v.co[i]-hi[i]))<1e-5 for i in range(3)) for v in obj.data.vertices)


def apply_shelves(design, by_id, assets=None):
    reports=[]
    for spec in design.get('shelf_refinements',[]):
        obj=by_id[spec['object_id']]
        group=next(g for g in design['groups'] if spec['object_id'] in g['children'])
        if group.get('deleted'):continue
        if len(group['children'])!=1 or not eligible_box(obj):raise ValueError('層架細化限單一矩形占位，原模型已變更')
        lo=Vector([min(v.co[i] for v in obj.data.vertices) for i in range(3)])
        hi=Vector([max(v.co[i] for v in obj.data.vertices) for i in range(3)])
        depth='XY'.index(spec['front'][1]);width=1-depth
        sizes=hi-lo;scale=obj.matrix_world.to_scale();thickness=[min(sizes[i]*.08,.025/max(abs(scale[i]),1e-5)) for i in range(3)]
        created=[]
        def board(label,lower,upper):
            bpy.ops.mesh.primitive_cube_add(size=1)
            part=bpy.context.object;part.name='Refined shelf '+label
            center=(lower+upper)/2;size=upper-lower
            part.matrix_world=obj.matrix_world@Matrix.Translation(center)@Matrix.Diagonal((*size,1))
            part['studio_refined_from']=spec['object_id']
            for mat in obj.data.materials:part.data.materials.append(mat)
            created.append(part)
            return part
        for side in (0,1):
            a=lo.copy();b=hi.copy()
            if side:b[width]=hi[width];a[width]=hi[width]-thickness[width]
            else:b[width]=lo[width]+thickness[width]
            board('side',a,b)
        # Back is opposite the user-facing side. Four open tiers are a proposal,
        # not a claim that specific appliances fit or ventilation is sufficient.
        a=lo.copy();b=hi.copy()
        if spec['front'][0]=='+':b[depth]=lo[depth]+thickness[depth]
        else:a[depth]=hi[depth]-thickness[depth]
        board('back',a,b)
        for fraction in (0,.25,.5,.75,1):
            a=lo.copy();b=hi.copy();a.z=lo.z+(sizes.z-thickness[2])*fraction;b.z=a.z+thickness[2]
            board('level',a,b)
        from realism_contents import populate
        selected=(assets or {}).get(spec['object_id'],assets)
        contents=populate(spec,lo,hi,thickness,scale,width,depth,board,selected,obj,created) if spec.get('contents') else []
        original_world=[obj.matrix_world@Vector(c) for c in obj.bound_box]
        bpy.context.view_layer.update()
        inv=obj.matrix_world.inverted()
        for part in created:
            for corner in part.bound_box:
                v=inv@part.matrix_world@Vector(corner)
                if any(v[i]<lo[i]-1e-4 or v[i]>hi[i]+1e-4 for i in range(3)):raise ValueError('層架細化越過原占地')
        obj.hide_render=True;obj.hide_set(True)
        clearance=[(sizes[i]-2*thickness[i])*abs(scale[i])-.03 for i in (width,depth)]+[((sizes.z-thickness[2])*.25-thickness[2])*abs(scale.z)-.02]
        reports.append(dict(object_id=spec['object_id'],parts=len(created),contents=contents,clearance=clearance,front=spec['front'],evidence=spec['evidence'],original_retained=True,envelope_preserved=True,world_bounds=[list(Vector([f(v[i] for v in original_world) for i in range(3)])) for f in (min,max)],quality='concept_shelf_not_appliance_or_construction_design'))
    bpy.context.view_layer.update()
    return reports
