"""Repeatable, preview-only completion checks on the actual transformed model.

No source file writes, rescaling or furniture deletion. Uncertain geometry is
reported to the visual review, never converted into confirmed design evidence.
"""
import math
from uuid import uuid5,NAMESPACE_URL
import bpy
from mathutils import Vector,Matrix
from completion_geometry import Obstacles,bounds
from realism_ceiling import structural,ceiling_options,add_ceilings


def purpose(group):
    return (group.get('object_specification') or {}).get('purpose') or (group.get('asset_requirements') or {}).get('purpose','')


def measured_front(objects):
    """Only named functional parts establish a front, not the longest bbox side."""
    bowls=[o for o in objects if any(t in o.name.lower() for t in ('bowl','basin'))]
    taps=[o for o in objects if 'faucet' in o.name.lower() and o.type=='MESH']
    if len(bowls)==1 and len(taps)==1:
        # The faucet mounting base, not its curved spout or an arbitrary bounding
        # box side, establishes the back of a freestanding sink assembly.
        bowl_lo,bowl_hi=bounds(bowls);tap=taps[0]
        points=[tap.matrix_world@v.co for v in tap.data.vertices]
        if points:
            bottom=min(p.z for p in points);top=max(p.z for p in points)
            base=[p for p in points if p.z<=bottom+max(.002,(top-bottom)*.04)]
            delta=(bowl_lo+bowl_hi)/2-sum(base,Vector())/len(base)
            axis=max((0,1),key=lambda i:abs(delta[i]))
            if .04<abs(delta[axis])<(bowl_hi[axis]-bowl_lo[axis])*.7 and abs(delta[1-axis])<abs(delta[axis])*.25:
                direction=Vector((0,0,0));direction[axis]=1 if delta[axis]>0 else -1
                return direction,[tap.name+' 實測底座位於盆體後緣',bowls[0].name]
    lo,hi=bounds(objects);center=(lo+hi)/2
    evidence=[o for o in objects if any(t in o.name.lower() for t in ('handle','control panel','drawer front','把手','抽屜面'))]
    votes=[]
    for o in evidence:
        p=sum(bounds([o]),Vector())/2-center
        ratios=[abs(p[i])/max(.01,(hi[i]-lo[i])/2) for i in (0,1)];axis=max((0,1),key=lambda i:ratios[i])
        if ratios[axis]>.65:votes.append((axis,1 if p[axis]>0 else -1))
    if not votes or len(set(votes))!=1:return None
    axis,sign=votes[0];direction=Vector((0,0,0));direction[axis]=sign
    return direction,[o.name for o in evidence]


def wall_gap(objects,walls,direction):
    lo,hi=bounds(objects);axis=max((0,1),key=lambda i:abs(direction[i]));other=1-axis
    gaps=[];names=[]
    for fraction in (.15,.5,.85):
        for z in (.3,.65):
            p=(lo+hi)/2;p[axis]=hi[axis] if direction[axis]>0 else lo[axis]
            p[other]=lo[other]+(hi[other]-lo[other])*fraction;p.z=lo.z+(hi.z-lo.z)*z
            hit=walls.ray(p+direction*.002,direction,1.5)
            if not hit:return None
            if abs(hit[3].dot(direction))<.95:return None
            gaps.append(hit[0]+.002);names.append(hit[1].name)
    if max(gaps)-min(gaps)>.015:return None
    return dict(distance=min(gaps),walls=sorted(set(names)))


def enclosure_contact(objects,direction,gap):
    """A projecting shelf touching a wall does not prove the enclosure fits it."""
    lo,hi=bounds(objects);axis=max((0,1),key=lambda i:abs(direction[i]));other=1-axis
    tree=selected_tree(objects);distances=[]
    for u in (.2,.5,.8):
        for z in (.35,.7):
            p=(lo+hi)/2;p[axis]=(hi[axis] if direction[axis]>0 else lo[axis])+direction[axis]*gap
            p[other]=lo[other]+u*(hi[other]-lo[other]);p.z=lo.z+z*(hi.z-lo.z)
            hit=tree.ray(p,-direction,.5)
            if hit:distances.append(hit[0])
    return dict(samples=len(distances),maximum_gap=max(distances) if distances else None,minimum_gap=min(distances) if distances else None)


def safe_change(objects,change,obstacles,floors):
    original={o:o.matrix_world.copy() for o in objects};old=bounds(objects);before=obstacles.collisions(objects)
    for obj in objects:obj.matrix_world=change@original[obj]
    bpy.context.view_layer.update();new=bounds(objects)
    after=obstacles.collisions(objects)
    safe=not (after-before) and all(abs((old[1]-old[0])[i]-(new[1]-new[0])[i])<.005 for i in range(3))
    # Keep all footprint samples supported by an actual floor, not an overall hull.
    for u,v in ((.1,.1),(.1,.9),(.9,.1),(.9,.9),(.5,.5)):
        p=Vector((new[0].x+(new[1].x-new[0].x)*u,new[0].y+(new[1].y-new[0].y)*v,new[0].z+.1))
        if floors.ray(p,Vector((0,0,-1)),max(.3,new[0].z+1)) is None:safe=False
    # Existing overlap cannot become a deeper penetration.
    for other in obstacles.objects:
        if other.name not in before:continue
        a,b=obstacles.boxes[other.name]
        penetration=lambda bb:min(max(0,min(bb[1][i],b[i])-max(bb[0][i],a[i])) for i in range(3))
        if penetration(new)>penetration(old)+.005:safe=False
    if not safe:
        for obj,matrix in original.items():obj.matrix_world=matrix
        bpy.context.view_layer.update()
    return safe


def selected_tree(objects):
    tree=Obstacles();tree.objects=list(objects);tree.boxes={o.name:bounds([o]) for o in objects};return tree


def placement(design,by_id):
    rows=[];walls=selected_tree(structural(design,by_id,'wall'));floors=selected_tree(structural(design,by_id,'floor'))
    if not walls.objects or not floors.objects:return [dict(name='擺放檢查',status='unresolved',reason='缺少結構牆／地板分類，不能自動推定使用側或靠牆')]
    for g in design['groups']:
        kind=purpose(g)
        if g.get('deleted') or kind not in ('cabinet','shoe_cabinet','wardrobe','bookcase','dishwasher','cooker','fridge','shower','sink','vanity'):continue
        objects=[by_id[k] for k in g['children'] if k in by_id and not by_id[k].hide_render]
        if not objects:continue
        dependents=[by_id[k] for child in design['groups'] if (child.get('decor_context') or {}).get('support_group_id')==g['id'] for k in child['children'] if k in by_id and not by_id[k].hide_render]
        all_objects=objects+dependents;obstacles=Obstacles(all_objects)
        row=dict(id=g['id'],name=g['name'],kind=kind,status='checked',changes=[])
        if kind=='shower':
            # Translate to a measured parallel wall; never stretch a bought enclosure.
            candidates=[]
            for d in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0)):
                direction=Vector(d);gap=wall_gap(objects,walls,direction)
                if gap and .008<gap['distance']<=.25:candidates.append((gap['distance'],direction,gap))
            used=set()
            for distance,direction,gap in sorted(candidates,key=lambda c:c[0]):
                axis=max((0,1),key=lambda i:abs(direction[i]))
                if axis in used:continue
                delta=direction*(distance-.003)
                if safe_change(all_objects,Matrix.Translation(delta),obstacles,floors):
                    contact=enclosure_contact(objects,direction,.003)
                    row['changes'].append(dict(action='wall_fit',translation=list(delta),gap_before=distance,outer_envelope_gap_after=.003,enclosure_contact=contact,walls=gap['walls']));used.add(axis)
                    if contact['samples']<6 or contact['maximum_gap']>.025:
                        tray=[o for o in objects if any(t in o.name.lower() for t in ('tray','底盤'))]
                        projection=[]
                        if tray:
                            a,b=bounds(tray)
                            for obj in objects:
                                l,h=bounds([obj]);excess=(h[axis]-b[axis]) if direction[axis]>0 else (a[axis]-l[axis])
                                if excess>.025:projection.append(dict(part=obj.name,projection=excess))
                        row.update(status='unresolved',reason='已保留尺寸平移，但實際圍板仍有牆縫；外凸構件占據靠牆安裝面，繼續平移會穿牆。需改用可貼牆產品或確認外凸配件處理，不拉伸／刪件掩蓋',installation_conflicts=projection)
            if candidates and not row['changes']:row.update(status='unresolved',reason='靠牆平移會碰撞／失去地板支承，保留尺寸，需檢查相鄰物件')
            if not candidates:row['reason']='未發現可安全平移消除的 8–250 mm 平行牆縫；不縮放淋浴間填滿空間'
        else:
            from completion_fronts import front as evidence_front
            front=measured_front(objects) or evidence_front(design,g,objects)
            if not front:row.update(status='unresolved',reason='原模型沒有可追溯的把手／控制面使用側，需 Agent 對照正反面判讀，不能僅憑外框轉向')
            else:
                direction,parts=front;gap=wall_gap(objects,walls,direction);opposite=wall_gap(objects,walls,-direction)
                row.update(front=list(direction),front_evidence=parts,wall_clearance=gap)
                if gap and gap['distance']<.25 and (opposite is None or opposite['distance']>.65):
                    spec=g.get('object_specification') or {}
                    if spec.get('front_source')=='user':row.update(status='unresolved',reason='已確認使用側與牆前淨空衝突，未覆寫確認方向')
                    else:
                        pivot=sum(bounds(objects),Vector())/2;change=Matrix.Translation(pivot)@Matrix.Rotation(math.pi,4,'Z')@Matrix.Translation(-pivot)
                        if safe_change(all_objects,change,obstacles,floors):row['changes'].append(dict(action='rotate',degrees=180,pivot=list(pivot),reason='把手／控制面朝近牆，反向具開放使用空間'))
                        else:row.update(status='unresolved',reason='轉向會增加碰撞或失去支承，保留原件')
        if row['changes']:
            if row['status']!='unresolved':row['status']='corrected'
            # Bound emitters must follow the same rigid correction as their fixture.
            for light in design.get('lighting_setup',{}).get('lights',[]):
                if light.get('group_id')==g['id']:
                    for obj in bpy.context.scene.objects:
                        if obj.type=='LIGHT' and obj.get('studio_light_id')==light['id']:
                            for change in row['changes']:
                                m=Matrix.Translation(Vector(change['translation'])) if change['action']=='wall_fit' else Matrix.Translation(Vector(change['pivot']))@Matrix.Rotation(math.pi,4,'Z')@Matrix.Translation(-Vector(change['pivot']))
                                obj.matrix_world=m@obj.matrix_world
        rows.append(row)
    return rows


def fixture_details(design,by_id):
    """Identify fixture gaps separately from invisible SUN/daylight emitters."""
    rows=[];groups={g['id']:g for g in design['groups']};scene=bpy.context.scene
    for spec in design.get('lighting_setup',{}).get('lights',[]):
        if not spec.get('enabled') or spec['kind']=='SUN':continue
        group=groups.get(spec.get('group_id'));light=next((o for o in scene.objects if o.type=='LIGHT' and o.get('studio_light_id')==spec['id'] and not o.hide_render),None)
        if not light:continue
        if not group:
            rows.append(dict(id=spec['id'],name=spec['name'],status='unresolved',reason='無燈具綁定，可能為窗外／攝影補光；未自動製造燈罩'));continue
        objects=[by_id[k] for k in group['children'] if k in by_id and not by_id[k].hide_render]
        row=dict(id=spec['id'],name=spec['name'],status='checked',changes=[])
        if spec.get('locked'):row.update(status='unresolved',reason='光源已鎖定，保留燈具與發光設定');rows.append(row);continue
        if not objects:row.update(status='unresolved',reason='綁定燈具模型缺件，需重新匹配，不以不可見光源冒充完整燈具');rows.append(row);continue
        lo,hi=bounds(objects);axis=light.matrix_world.to_3x3()@Vector((0,0,1))
        if axis.z<.95:row['reason']='非向下天花燈；保留壁燈／立燈姿態';rows.append(row);continue
        existing_parts=[o for o in scene.objects if o.get('studio_fixture_detail') and o.get('studio_fixture_light')==spec['id']]
        obstacles=Obstacles(objects+existing_parts);hit=obstacles.ray(Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,hi.z+.005)),Vector((0,0,1)),1.2)
        ceiling=hit and abs(hit[3].z)>.8 and (hit[1].get('studio_ceiling_infill') or any(t in hit[1].name.lower() for t in ('ceiling','天花')))
        def part(name,radius,depth,z,emission=False):
            label='Fixture '+uuid5(NAMESPACE_URL,spec['id']).hex[:16]+' '+name
            existing=bpy.data.objects.get(label)
            if existing:return existing
            bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=radius,depth=depth,location=((lo.x+hi.x)/2,(lo.y+hi.y)/2,z))
            obj=bpy.context.object;obj.name=label
            obj['studio_fixture_light']=spec['id'];obj['studio_fixture_part']=name
            obj['studio_id']=uuid5(NAMESPACE_URL,spec['id']+'/'+name).hex;obj['studio_refined_from']=objects[0].get('studio_id');obj['studio_fixture_detail']=True
            mat=bpy.data.materials.new(obj.name);mat.use_nodes=True;shader=mat.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(.72,.72,.70,1);shader.inputs['Roughness'].default_value=.6
            if emission:shader.inputs['Emission Color'].default_value=(*spec['color'],1);shader.inputs['Emission Strength'].default_value=.5
            obj.data.materials.append(mat);return obj
        if ceiling and hit[0]>.025 and not any(o.get('studio_fixture_part')=='mounting-stem' for o in existing_parts):
            # A stem documents the mounting instead of moving a confirmed fixture.
            part('mounting-stem',.012,hit[0]+.005,hi.z+(hit[0]+.005)/2);row['changes'].append(dict(action='mount',length=hit[0]))
        elif not ceiling:row.update(status='unresolved',reason='燈具上方沒有可信天花支承，不能以拉長吊桿掩蓋頂面缺口')
        # Check from below: the emitting surface must actually be visible, not inside an opaque case.
        deps=bpy.context.evaluated_depsgraph_get();p=light.matrix_world.translation
        hit=scene.ray_cast(deps,p-Vector((0,0,.35)),Vector((0,0,1)),distance=.7)
        luminous=False
        if hit[0] and (hit[4] in objects or hit[4] in existing_parts):
            for mat in hit[4].data.materials:
                shader=mat.node_tree.nodes.get('Principled BSDF') if mat and mat.use_nodes else None
                if shader and shader.inputs['Emission Strength'].default_value>0:luminous=True
        if not luminous and abs(p.z-lo.z)<.12 and lo.x-.03<=p.x<=hi.x+.03 and lo.y-.03<=p.y<=hi.y+.03:
            # Above emitter so its real direct light is not blocked by an opaque disk.
            radius=min((hi.x-lo.x)*.36,(hi.y-lo.y)*.36,.25)
            if radius>.015 and p.z+.006<=lo.z:
                part('diffuser',radius,.004,p.z+.006,True);row['changes'].append(dict(action='diffuser',reason='補可見柔光面；保留原光源功率'))
            else:row.update(status='unresolved',reason='發光面位於燈罩內，需核對模型朝向，不任意移動光源')
        if row['changes'] and row['status']!='unresolved':row['status']='corrected'
        rows.append(row)
    return rows


def prepare(design,by_id):
    if not design.get('completion_details'):return dict(version=1,enabled=False,items=[],remaining=[])
    def dimensions():
        result={}
        for g in design['groups']:
            objects=[by_id[k] for k in g['children'] if k in by_id and not by_id[k].hide_render and not by_id[k].get('studio_ceiling_infill')]
            if objects and not g.get('deleted'):
                lo,hi=bounds(objects);result[g['id']]=list(hi-lo)
        return result
    before=dimensions()
    ceiling=ceiling_options(design,by_id);copy=dict(design,ceiling_infill=[o['id'] for o in ceiling['options']])
    patches=add_ceilings(copy,by_id)
    rows=placement(design,by_id)+fixture_details(design,by_id)
    from completion_sink import finish_sinks
    rows+=finish_sinks(design,by_id)
    remaining=[r['name']+'：'+r['reason'] for r in rows if r['status']=='unresolved']
    remaining.extend(r['name']+'：'+r['reason'] for r in ceiling['skipped'] if '完整頂面' not in r['reason'] and '露天' not in r['reason'])
    after=dimensions()
    if set(before)!=set(after) or any(max(abs(a-b) for a,b in zip(before[k],after[k]))>.005 for k in before):
        raise ValueError('模型完成度修正改變原組件尺寸或遺失家具；本次預覽拒絕輸出')
    return dict(version=1,enabled=True,ceiling_patches=patches,ceiling_checks=ceiling,items=rows,remaining=remaining,dimensions_preserved=True,dimension_checks=[dict(id=k,before=before[k],after=after[k]) for k in before],quality='geometry_checked_visual_pending')
