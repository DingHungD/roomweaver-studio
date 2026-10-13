"""Rebuild the Project04-derived teaching apartment with Blender 4.5 LTS (offline).

All asset inputs are hash-verified. Only the sanitized teaching layout and bundled CC0 assets are used.
Native .blend preserves HDRI, area lights and camera settings; GLB is the
portable editing alternative and cannot preserve Blender world lighting.
"""
from pathlib import Path
import bpy, math, json, hashlib, random
from mathutils import Vector, Matrix
import numpy as np
ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/'assets'
for asset in json.loads((ASSETS/'manifest.json').read_text())['assets']:
    assert asset['license']=='CC0-1.0'
    assert hashlib.sha256((ASSETS/asset['file']).read_bytes()).hexdigest()==asset['sha256']
bpy.ops.wm.read_factory_settings(use_empty=True)
random.seed(42)
scene=bpy.context.scene
scene.unit_settings.system='METRIC'
scene.render.engine='CYCLES';scene.cycles.samples=96;scene.cycles.use_denoising=True
scene.cycles.max_bounces=10;scene.cycles.transparent_max_bounces=12
scene.view_settings.view_transform='AgX'
try:
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
    for d in prefs.devices:d.use=d.type!='CPU'
    scene.cycles.device='GPU' if any(d.use for d in prefs.devices) else 'CPU'
except Exception:scene.cycles.device='CPU'

images={}
for key in ['oak-floor','oak-furniture','fabric','plaster']:
    with bpy.data.libraries.load(str(ASSETS/(key+'.blend')),link=False) as (src,dst):dst.materials=src.materials
    images[key]=[n.image for m in dst.materials if m and m.use_nodes for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image]

def image_for(key,words):
    return next((i for i in images[key] if any(w in i.name.lower() for w in words)),None)

def tinted_image(image,name,color):
    if not image:return None
    a=np.empty(len(image.pixels),dtype=np.float32);image.pixels.foreach_get(a);a=a.reshape(-1,4)
    mean=np.mean(a[:,:3],axis=0)

    if 'oak' in name.lower():
        a[:,:3]=np.clip(a[:,:3]*np.array(color)/np.maximum(mean,.02),0,1)
    else:
        gray=np.mean(a[:,:3],axis=1);grain=(gray/max(float(gray.mean()),.02)-1)*.045
        a[:,:3]=np.clip(np.array(color)*(1+grain[:,None]),0,1)
    out=bpy.data.images.new(name,width=image.size[0],height=image.size[1]);out.pixels.foreach_set(a.ravel());out.pack()
    return out

def material(name,key,color=None,rough=.6,metal=0,normal_strength=.25):
    m=bpy.data.materials.new(name);m.use_nodes=True
    ns=m.node_tree.nodes;ls=m.node_tree.links;p=ns.get('Principled BSDF')
    p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal
    base=image_for(key,['color','diff','albedo']);normal=image_for(key,['normal','_nor_']);r=image_for(key,['rough'])
    if color and base:base=tinted_image(base,name+' color',color)
    for image,socket in [(base,'Base Color'),(r,'Roughness')]:
        if image:
            tex=ns.new('ShaderNodeTexImage');tex.image=image;ls.new(tex.outputs['Color'],p.inputs[socket])
    if not r:
        # Fabric scan height carries the visible weave microvariation.
        r=image_for(key,['height']);
        if r:
            tex=ns.new('ShaderNodeTexImage');tex.image=r
            bump=ns.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.001
            ls.new(tex.outputs['Color'],bump.inputs['Height']);ls.new(bump.outputs['Normal'],p.inputs['Normal'])
    if normal:
        tex=ns.new('ShaderNodeTexImage');tex.image=normal
        normal.colorspace_settings.name='Non-Color'
        nm=ns.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=normal_strength
        ls.new(tex.outputs['Color'],nm.inputs['Color']);ls.new(nm.outputs['Normal'],p.inputs['Normal'])

    coord=ns.new('ShaderNodeTexCoord');mapping=ns.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value=(12,12,12) if key=='fabric' else ((4,4,4) if key=='plaster' else (1,1,1))
    ls.new(coord.outputs['UV'],mapping.inputs['Vector'])
    for tex in [n for n in ns if n.type=='TEX_IMAGE']:ls.new(mapping.outputs['Vector'],tex.inputs['Vector'])
    m.diffuse_color=(*(color or (.65,.55,.4)),1)
    return m
wall=material('Warm grey white plaster','plaster',(.74,.71,.65),normal_strength=.035)
floor=material('Pale oak floor - long grain','oak-floor',(.68,.58,.45),normal_strength=.35)
wood=material('Furniture oak - distinct grain','oak-furniture',(.37,.25,.14))
fabric=material('Blue grey woven upholstery','fabric',(.16,.25,.31),rough=.82,normal_strength=.6)
linen=material('Ivory linen','fabric',(.75,.71,.62),rough=.88,normal_strength=.35)
paint=material('Greige lacquer cabinet','plaster',(.53,.50,.44),rough=.27,normal_strength=.015)
# Lacquer is smoother than plaster although it uses the same CC0 microtexture.
p=paint.node_tree.nodes.get('Principled BSDF')
for link in list(p.inputs['Roughness'].links):paint.node_tree.links.remove(link)
p.inputs['Roughness'].default_value=.28;p.inputs['Coat Weight'].default_value=.22
metal=material('Charcoal metal','plaster',(.055,.063,.068),metal=.8,normal_strength=.02)
ceramic=material('Ivory ceramic','plaster',(.7,.66,.57),normal_strength=.02)
p=ceramic.node_tree.nodes.get('Principled BSDF')
for link in list(p.inputs['Roughness'].links):ceramic.node_tree.links.remove(link)
p.inputs['Roughness'].default_value=.19;p.inputs['Coat Weight'].default_value=.35

def finish(obj,name,mat=None):
    obj.name=name;obj['assembly_id']=name.split('__')[0]
    if mat:obj.data.materials.clear();obj.data.materials.append(mat)
    return obj

def box(name,loc,size,mat,bevel=.008):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);finish(o,name,mat)
    if bevel:
        mod=o.modifiers.new('Manufactured edge','BEVEL');mod.width=bevel;mod.segments=3
        o.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return o

def sphere(name,loc,size,mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=20,location=loc);o=bpy.context.object;o.scale=size;finish(o,name,mat)
    for f in o.data.polygons:f.use_smooth=True
    return o

def asset(key,name,center,width,angle=0):
    before=set(bpy.data.objects)
    with bpy.data.libraries.load(str(ASSETS/(key+'.blend')),link=False) as (src,dst):dst.objects=src.objects
    loaded=[o for o in dst.objects if o]
    for o in loaded:
        if not o.users_collection:bpy.context.collection.objects.link(o)
    bpy.context.view_layer.update()
    meshes=[o for o in loaded if o.type=='MESH']
    # Freeze source modifiers before GLB export so both representations share geometry.
    for o in meshes:
        bpy.context.view_layer.objects.active=o;o.select_set(True)
        for mod in o.modifiers:
            if mod.type=='SUBSURF':mod.levels=min(mod.levels,2);mod.render_levels=mod.levels
        mesh=bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        matrix=o.matrix_world.copy();o.modifiers.clear();o.parent=None;o.data=mesh;o.matrix_world=matrix;o.select_set(False)
    pts=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
    mn=Vector([min(p[i] for p in pts) for i in range(3)]);mx=Vector([max(p[i] for p in pts) for i in range(3)])
    scale=width/(mx.x-mn.x);origin=Vector(((mn.x+mx.x)/2,(mn.y+mx.y)/2,mn.z))
    matrix=Matrix.Translation(Vector(center))@Matrix.Rotation(angle,4,'Z')@Matrix.Scale(scale,4)@Matrix.Translation(-origin)
    for i,o in enumerate(meshes):
        o.matrix_world=matrix@o.matrix_world;finish(o,name+'__part-'+str(i))
        if key.startswith('sofa'):o.data.materials.clear();o.data.materials.append(fabric)
    for o in loaded:
        if o.type!='MESH':bpy.data.objects.remove(o,do_unlink=True)
    return meshes

# Same metric footprint as the PNG / DXF tutorials; never reads the private case.
data=json.loads((ROOT.parent/'from-dxf/layout.json').read_text())
def slab(name,points,z,depth,mat):
    verts=[(*p,z) for p in points]+[(*p,z+depth) for p in points];n=len(points)
    faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);finish(o,name,mat)
    bpy.context.view_layer.objects.active=o;o.select_set(True);bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project();bpy.ops.object.mode_set(mode='OBJECT');o.select_set(False)
    return o
slab('floor',data['floor'],-.12,.12,floor)
ceiling=slab('ceiling',data['floor'],2.8,.12,wall)
for w in data['walls']:
    a=Vector(w['a']);b=Vector(w['b']);v=b-a;length=v.length;u=v.normalized();theta=math.atan2(v.y,v.x)
    holes=sorted([(max(0,(Vector(o['a'])-a).dot(u)),min(length,(Vector(o['b'])-a).dot(u)),o) for o in data['openings'] if o['host']==w['id']],key=lambda x:min(x[:2]))
    holes=[(min(lo,hi),max(lo,hi),o) for lo,hi,o in holes]
    def segment(lo,hi,z,h,suffix):
        if hi-lo<.001 or h<.001:return
        xy=a+u*((lo+hi)/2);o=box('wall-'+w['id']+'__'+suffix,(*xy,z+h/2),(hi-lo,w['thickness'],h),wall,.003);o.rotation_euler.z=theta
    previous=0
    for index,(lo,hi,opening) in enumerate(holes):
        segment(previous,lo,0,2.8,f'solid-{index}')
        base=1 if opening['kind']=='window' else 0;top=2.3 if base else 2.1
        segment(lo,hi,0,base,f'sill-{index}');segment(lo,hi,top,2.8-top,f'header-{index}')
        if base:
            for d in [lo,hi]:
                xy=a+u*d;o=box(opening['id']+'__frame-'+str(d),(*xy,(base+top)/2),(.04,.08,top-base),paint);o.rotation_euler.z=theta
        previous=hi
    segment(previous,length,0,2.8,'end')
for f in data['furniture']:
    name=f['id'];x,y=f['center'];w,h=f['size'];z=f['height'];angle=math.radians(f['angle']);category=f['category']
    key={'bed':'bed','chair':'chair','sofa':'sofa-soft'}.get(category)
    if name=='table-public':key='coffee-table'
    if key:
        meshes=asset(key,name,(0,0,0),w)
        pts=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box];depth=max(p.y for p in pts)-min(p.y for p in pts)
        transform=Matrix.Translation((x,y,0))@Matrix.Rotation(angle,4,'Z')@Matrix.Diagonal((1,h/depth,1,1))
        for o in meshes:o.matrix_world=transform@o.matrix_world
        continue
    parts=[]
    def local(suffix,loc,size,mat,bevel=.01):
        o=box(name+'__'+suffix,loc,size,mat,bevel);o.matrix_world=Matrix.Translation((x,y,0))@Matrix.Rotation(angle,4,'Z')@o.matrix_world;parts.append(o)
    if category=='bunk_bed':
        for height in [.4,1.45]:
            local('frame-'+str(height),(0,0,height),(w,h,.1),paint)
            local('mattress-'+str(height),(0,0,height+.15),(w-.08,h-.06,.22),linen,.07)
            local('pillow-'+str(height),(0,h*.32,height+.31),(w*.7,.42,.15),linen,.07)
        for xx in [-w/2,w/2]:
            for yy in [-h/2,h/2]:local('post-'+str(xx)+str(yy),(xx,yy,.95),(.06,.06,1.9),wood)
    elif category=='table':
        local('top',(0,0,z-.035),(w,h,.07),wood)
        for xx in [-w*.43,w*.43]:
            for yy in [-h*.38,h*.38]:local('leg-'+str(xx)+str(yy),(xx,yy,z/2),(.055,.055,z),metal)
    else:
        local('body',(0,0,z/2),(w,h,z),paint if category=='cabinet' else ceramic)
        local('top',(0,0,z+.02),(w+.015,h+.015,.04),wood if category=='cabinet' else ceramic)
        count=max(1,round(w/.5))
        for i in range(count):local('front-'+str(i),(-w/2+(i+.5)*w/count,-h/2-.015,z/2),(w/count-.014,.025,z-.04),paint,.004)

world=bpy.data.worlds.new('CC0 illustrative sky');world.use_nodes=True;scene.world=world
nodes=world.node_tree.nodes;env=nodes.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(ASSETS/'city-sky.exr'));env.image.pack()
world.node_tree.links.new(env.outputs['Color'],nodes.get('Background').inputs['Color']);nodes.get('Background').inputs['Strength'].default_value=.65
sun=bpy.data.lights.new('Exterior daylight','SUN');sun.energy=1.8;sun.angle=math.radians(8)
o=bpy.data.objects.new(sun.name,sun);bpy.context.collection.objects.link(o);o.rotation_euler=Vector((1,-.3,-.55)).to_track_quat('-Z','Y').to_euler()
for name,xy,energy in [('living',(5.2,1.7),75),('child',(2.6,2.8),45),('master',(5.5,4.2),55),('kitchen',(1.6,1),35),('bath',(7.4,2.6),25)]:
    box('fixture-'+name,(*xy,2.72),(.4,.4,.04),ceramic)
    light=bpy.data.lights.new('Interior-'+name,'POINT');light.energy=energy;light.shadow_soft_size=.45;light.color=(1,.88,.73)
    o=bpy.data.objects.new(light.name,light);bpy.context.collection.objects.link(o);o.location=(*xy,2.6)
for o in list(bpy.data.objects):
    if o.type=='MESH':
        bpy.context.view_layer.objects.active=o
        for mod in list(o.modifiers):
            try:bpy.ops.object.modifier_apply(modifier=mod.name)
            except RuntimeError:o.modifiers.remove(mod)
for image in bpy.data.images:
    if image.type=='IMAGE' and image.size[0]:
        if not image.packed_file:image.pack()
        image.filepath='//textures/'+Path(image.name).name
for m in bpy.data.materials:m.use_fake_user=False
for t in list(bpy.data.texts):bpy.data.texts.remove(t)
bpy.ops.outliner.orphans_purge(do_recursive=True)
bpy.ops.export_scene.gltf(filepath=str(ROOT/'project04-apartment.glb'),export_format='GLB',export_extras=True,export_lights=True)
cam_data=bpy.data.cameras.new('Preview');cam=bpy.data.objects.new('Preview',cam_data);bpy.context.collection.objects.link(cam);scene.camera=cam
cam.location=(6.25,2.12,1.5);cam.rotation_euler=(Vector((4.7,.35,1.05))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=25
scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.cycles.samples=48
scene.render.filepath='//preview-living.png';bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'project04-apartment.blend'),compress=True)
scene.render.filepath=str(ROOT/'preview-living.png');bpy.ops.render.render(write_still=True)
ceiling.hide_render=True;scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.color_type='MATERIAL';scene.display.shading.light='STUDIO'
cam.location=(4,2.64,14);cam.rotation_euler=(0,0,0);cam.data.type='ORTHO';cam.data.ortho_scale=10
scene.render.resolution_x=1200;scene.render.resolution_y=1100;scene.render.filepath=str(ROOT/'layout.png');bpy.ops.render.render(write_still=True)
manifest={'name':'Project04 teaching apartment','kind':'educational-derivative','units':'metres','native':'project04-apartment.blend','preview':'project04-apartment.glb','provenance':data['provenance'],'suggested_viewpoints':[{'name':'Living','eye':[6.25,2.12,1.5],'yaw':-131.2,'pitch':-10,'lens':25},{'name':'Master','eye':[6.25,3.3,1.5],'yaw':135,'pitch':0,'lens':28}], 'sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['project04-apartment.blend','project04-apartment.glb','preview-living.png','layout.png']}}
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
