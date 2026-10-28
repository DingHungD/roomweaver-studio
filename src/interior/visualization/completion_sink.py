"""Complete an existing concept sink support without plugging its basin or scaling it."""
from uuid import uuid5,NAMESPACE_URL
import bpy
from mathutils import Vector
from completion_geometry import bounds,Obstacles

def finish_sinks(design,by):
    from completion_details import purpose,selected_tree,wall_gap
    from realism_ceiling import structural
    rows=[];walls=selected_tree(structural(design,by,'wall'))
    for group in design['groups']:
        if group.get('deleted') or purpose(group) not in ('sink','vanity'):continue
        objects=[by[k] for k in group['children'] if k in by and not by[k].hide_render]
        # An authored product cabinet is not a license to add generic panels.
        sides=[o for o in objects if 'Repair installation side' in o.name]
        bowls=[o for o in objects if 'bowl' in o.name.lower() or 'basin' in o.name.lower()]
        if len(sides)!=2 or len(bowls)!=1:continue
        row=dict(id=group['id'],name=group['name']+' · 水槽收邊',kind='sink_finishing',status='checked',changes=[])
        lo,hi=bounds(sides);a,b=bounds(bowls);width=max((0,1),key=lambda i:abs(sum(bounds([sides[0]]),Vector())[i]-sum(bounds([sides[1]]),Vector())[i]));depth=1-width
        candidates=[]
        for sign in (-1,1):
            d=Vector((0,0,0));d[depth]=sign;gap=wall_gap(sides,walls,d)
            if gap and gap['distance']<.2:candidates.append(sign)
        if len(candidates)!=1:
            row.update(status='unresolved',reason='水槽背牆不唯一，未封住可能的使用側');rows.append(row);continue
        front=-candidates[0]
        existing=[o for o in bpy.context.scene.objects if o.get('studio_sink_finish')==group['id']]
        if existing:rows.append(row);continue
        # Panels stay inside the existing support/basin envelope. Inspect every
        # new panel against all retained meshes, including basin and drain pipe.
        guard=Obstacles(sides);created=[];blocked=[]
        def panel(label,p,q):
            if min(q-p)<.006:return
            bpy.ops.mesh.primitive_cube_add(size=1,location=(p+q)/2);o=bpy.context.object;o.name='Sink finish '+label;o.dimensions=q-p
            bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
            collisions=guard.collisions([o])
            if collisions:
                blocked.append(dict(part=label,blockers=sorted(collisions)));bpy.data.objects.remove(o,do_unlink=True);return
            o['studio_id']=uuid5(NAMESPACE_URL,group['id']+'/sink-finish/'+label).hex;o['studio_refined_from']=sides[0]['studio_id'];o['studio_sink_finish']=group['id']
            if sides[0].data.materials:o.data.materials.append(sides[0].data.materials[0])
            bevel=o.modifiers.new('Edge finish','BEVEL');bevel.width=.001;bevel.segments=2;created.append(o)
            row['changes'].append(dict(action='sink_finish',part=label,bounds=[list(p),list(q)]))
        # Two cabinet fronts, separated by a small join; top stops beneath basin.
        for index in range(2):
            p=lo.copy();q=hi.copy();p.z+=.04;q.z=min(a.z-.004,hi.z)
            p[width]=lo[width]+.025+(hi[width]-lo[width]-.05)*index/2+.002
            q[width]=lo[width]+.025+(hi[width]-lo[width]-.05)*(index+1)/2-.002
            if front>0:p[depth]=hi[depth]-.018;q[depth]=hi[depth]-.001
            else:p[depth]=lo[depth]+.001;q[depth]=lo[depth]+.018
            panel('front-'+str(index),p,q)
        p=lo.copy();q=hi.copy();p.z=a.z+.003;q.z=hi.z
        p[width]+=.025;q[width]-=.025
        if front>0:p[depth]=hi[depth]-.018;q[depth]=hi[depth]-.001
        else:p[depth]=lo[depth]+.001;q[depth]=lo[depth]+.018
        panel('upper-fascia',p,q)
        # Four independent rim strips around, never across, the basin bounds.
        for axis in (0,1):
            for sign in (-1,1):
                p=lo.copy();q=hi.copy();p.z=min(hi.z,b.z-.02);q.z=b.z
                if sign<0:q[axis]=a[axis]-.002
                else:p[axis]=b[axis]+.002
                other=1-axis
                if axis==1:p[other]=max(lo[other],a[other]);q[other]=min(hi[other],b[other])
                panel('rim-'+str(axis)+'-'+str(sign),p,q)
        if blocked:row.update(status='unresolved',reason='部分收邊會碰到保留的盆體／排水或相鄰物件，未強行封板',blocked_parts=blocked)
        elif created:row['status']='corrected'
        rows.append(row)
    return rows
