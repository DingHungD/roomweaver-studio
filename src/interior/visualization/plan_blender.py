"""Deterministic straight-wall plan builder; runs inside Blender only."""
import math
from pathlib import Path
from uuid import UUID, uuid5

import bpy
from mathutils import Vector


def build_plan(request):
    plan=request['plan']
    namespace=UUID(request['source_sha256'][:32])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
    materials={}
    for key,color in dict(wall=(.76,.72,.65,1),floor=(.46,.31,.17,1),furniture=(.25,.36,.40,1),window=(.48,.64,.72,1)).items():
        mat=bpy.data.materials.new(key);mat.diffuse_color=color;mat.use_nodes=True
        bsdf=mat.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=color;bsdf.inputs['Roughness'].default_value=.65
        materials[key]=mat

    def identify(obj,item,suffix):
        obj.name=f"{item['role']}-{item['id']}__{suffix}"
        obj['studio_id']=uuid5(namespace,item['id']+'/'+suffix).hex
        obj['assembly_id']=item['name']+' ['+item['id']+']'
        obj['studio_role']=item['role']
        obj['source_entity_id']=item['id'];obj['room_id']='interior'
        return obj

    def prism(item,points,base,height,suffix,material):
        n=len(points)
        area=sum(points[i][0]*points[(i+1)%n][1]-points[(i+1)%n][0]*points[i][1] for i in range(n))
        if area<0:points=list(reversed(points))
        vertices=[(x,y,z) for z in (base,base+height) for x,y in points]
        faces=[tuple(reversed(range(n))),tuple(range(n,n*2))]
        faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
        mesh=bpy.data.meshes.new(suffix);mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new(suffix,mesh);scene.collection.objects.link(obj)
        identify(obj,item,suffix)
        if material:obj.data.materials.append(materials[material])
        return obj

    def line_box(item,a,b,depth,base,height,suffix,material):
        length=math.dist(a,b);nx=-(b[1]-a[1])/length*depth/2;ny=(b[0]-a[0])/length*depth/2
        return prism(item,[(a[0]-nx,a[1]-ny),(b[0]-nx,b[1]-ny),(b[0]+nx,b[1]+ny),(a[0]+nx,a[1]+ny)],base,height,suffix,material)

    def design_furniture(item):
        # These are owned, generic concept models, not commercial assets.
        pts=item['points'];p,q,r=pts[:3];w=math.dist(p,q);d=math.dist(q,r)
        if min(w,d)<.1:return False
        u=((q[0]-p[0])/w,(q[1]-p[1])/w);v=((r[0]-q[0])/d,(r[1]-q[1])/d)
        center=(sum(x for x,y in pts)/len(pts),sum(y for x,y in pts)/len(pts))
        h=item['height'];base=item['base'];kind=item['design_asset']
        def part(name,x,y,sx,sy,z,sz):
            poly=[(center[0]+a*u[0]+b*v[0],center[1]+a*u[1]+b*v[1]) for a,b in [(x-sx/2,y-sy/2),(x+sx/2,y-sy/2),(x+sx/2,y+sy/2),(x-sx/2,y+sy/2)]]
            obj=prism(item,poly,base+z,sz,name,'furniture')
            bevel=obj.modifiers.new('Soft concept edges','BEVEL');bevel.width=min(.025,sx/8,sy/8,sz/8);bevel.segments=2
            return obj
        if kind in ('table','desk','chair'):
            top=h if kind!='chair' else h*.53
            part('top',0,0,w,d,top-.06,.06)
            for i,x in enumerate((-w*.4,w*.4)):
                for j,y in enumerate((-d*.4,d*.4)):part(f'leg-{i}-{j}',x,y,.05,.05,0,top-.06)
            if kind=='chair':part('back',0,d*.44,w,.06,top,h-top)
        elif kind=='bed':
            part('frame',0,0,w,d,0,h*.45);part('mattress',0,0,w*.98,d*.96,h*.45,h*.55)
            for i,x in enumerate((-w*.25,w*.25)):part('pillow-'+str(i),x,d*.32,w*.4,d*.18,h*.92,h*.08)
        elif kind=='sofa':
            part('base',0,0,w,d,0,h*.3);part('seat',0,-d*.05,w*.88,d*.8,h*.3,h*.25)
            part('back',0,d*.4,w,d*.2,h*.3,h*.7)
            for i,x in enumerate((-w*.46,w*.46)):part('arm-'+str(i),x,0,w*.08,d,h*.3,h*.45)
        elif kind=='cabinet':
            part('case',0,0,w,d,0,h)
            for i,x in enumerate((-w*.25,w*.25)):part('door-'+str(i),x,-d*.49,w*.49,d*.02,.025,h-.05)
        elif kind=='bunk_bed':
            for i,z in enumerate((h*.17,h*.7)):
                part('bed-frame-'+str(i),0,0,w,d,z,h*.06)
                part('mattress-'+str(i),0,0,w*.9,d*.9,z+h*.06,h*.06)
            for i,x in enumerate((-w*.46,w*.46)):
                for j,y in enumerate((-d*.46,d*.46)):part(f'post-{i}-{j}',x,y,.06,.06,0,h)
                part('upper-rail-'+str(i),x,0,.05,d,h*.93,.05)
            for i in range(5):part('ladder-rung-'+str(i),0,-d*.47,w*.42,.06,.2+i*h*.14,.04)
        elif kind in ('cooker','washer'):
            part('body',0,0,w,d,0,h*.94)
            if kind=='cooker':
                part('hob',0,0,w,d,h*.94,h*.06)
                for i,x in enumerate((-w*.24,w*.24)):part('burner-'+str(i),x,0,w*.25,d*.4,h*.985,h*.015)
            else:
                part('control-panel',0,-d*.49,w*.9,d*.02,h*.82,h*.09)
                part('drum-front',0,-d*.49,w*.65,d*.02,h*.2,h*.55)
        elif kind=='television':
            part('stand-base',0,0,w*.5,d,0,.04)
            part('stand',0,0,.06,.06,.04,h*.25)
            part('screen',0,0,w,min(d,.06),h*.25,h*.75)
        else:return False
        return True

    walls={}
    for item in plan['items']:
        role=item['role'];points=item['points']
        if role=='wall':
            if item['closed']:
                walls[item['id']]=[prism(item,points,item['base'],item['height'],'body','wall')]
            else:
                walls[item['id']]=[line_box(item,a,b,item['thickness'],item['base'],item['height'],f'segment-{i}','wall') for i,(a,b) in enumerate(zip(points,points[1:]))]
        elif role in ('floor','furniture'):
            if role=='furniture' and item.get('design_asset') and len(points)==4 and design_furniture(item):continue
            base=-item['height'] if role=='floor' else item['base']
            prism(item,points,base,item['height'],'surface' if role=='floor' else 'placeholder',role)
    cuts=[]
    for item in plan['items']:
        if item['role'] not in ('door','window'):continue
        a,b=item['points'];host=next(w for w in plan['items'] if w['id']==item['host_id'])
        # The validated host is isolated; extend through its depth, never cut neighbours.
        depth=max(math.dist(p,q) for p in host['points'] for q in host['points'])+1 if host['closed'] else host['thickness']+.1
        cutter=line_box(item,a,b,depth,item['base']-.002,item['height']+.004,'cutter',None)
        before=sum(len(o.data.polygons) for o in walls[item['host_id']])
        for wall in walls[item['host_id']]:
            bpy.context.view_layer.objects.active=wall
            modifier=wall.modifiers.new('Plan opening','BOOLEAN');modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=cutter
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.data.objects.remove(cutter,do_unlink=True)
        after=sum(len(o.data.polygons) for o in walls[item['host_id']])
        cuts.append(dict(id=item['id'],host_id=item['host_id'],polygons_before=before,polygons_after=after))
        # Keep windows transparent to day light; small frame strips identify the opening.
        if item['role']=='window':
            for index,z in enumerate((item['base'],item['base']+item['height']-.045)):
                line_box(item,a,b,.06,z,.045,f'frame-{index}','window')
    floors=[a for a in plan['items'] if a['role']=='floor']
    bounds=[p for f in floors for p in f['points']]
    cx=(min(p[0] for p in bounds)+max(p[0] for p in bounds))/2
    cy=(min(p[1] for p in bounds)+max(p[1] for p in bounds))/2
    scene.world=bpy.data.worlds.new('Plan daylight proposal');scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.7,.8,1,1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.35
    sun=bpy.data.lights.new('Daylight proposal','SUN');sun.energy=2;sun.angle=.12
    light=bpy.data.objects.new('Daylight proposal',sun);scene.collection.objects.link(light)
    light.rotation_euler=(math.radians(25),math.radians(-30),math.radians(-25))
    area=bpy.data.lights.new('Open ceiling soft fill','AREA');area.energy=350;area.shape='DISK';area.size=5
    light=bpy.data.objects.new('Open ceiling soft fill',area);scene.collection.objects.link(light);light.location=(cx,cy,4.5)
    scene.view_settings.view_transform='AgX';scene.view_settings.exposure=0
    scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
    # Geometry-only browser derivative. Native lights/world are retained by prepare.
    from surface_uv import ensure_uv
    for obj in scene.objects:
        if obj.type=='MESH' and obj.get('studio_role') in ('wall','floor'):ensure_uv(obj)
    bpy.ops.export_scene.gltf(filepath=request['preview'],export_format='GLB',export_extras=True,export_lights=False,export_cameras=False)
    return dict(openings=cuts,source='confirmed-plan',source_origin_metres=plan['source_origin_metres'],notes=['概念白模／通用占位家具，無天花；照明為提案，請在光影頁確認。'])
