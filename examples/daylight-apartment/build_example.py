"""Rebuild the CC0 daylight apartment with Blender 4.5 LTS (offline).

All asset inputs are hash-verified. No customer files or model calls are used.
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

# One compact apartment, kept deliberately navigable for manual editing.
box('floor__base',(3.4,2.9,-.08),(6.96,5.96,.16),floor)
for row in range(29):
    y=.1+row*.2;offset=(row%3)*.55
    for col in range(-1,5):
        a=max(0,col*1.7+offset);b=min(6.8,(col+1)*1.7+offset)
        if b>a:box(f'floor__plank-{row}-{col}',((a+b)/2,y,.012),(b-a-.004,.196,.024),floor,.001)
box('wall-north__living',(2.14,5.88,1.45),(4.44,.16,2.9),wall)
box('wall-north__end',(6.67,5.88,1.45),(.42,.16,2.9),wall)
box('wall-north__sill',(5.4,5.88,.3),(2.15,.16,.6),wall)
box('wall-north__header',(5.4,5.88,2.8),(2.15,.16,.2),wall)
for x in [4.35,5.4,6.45]:box('bedroom-window__mullion-'+str(x),(x,5.82,1.64),(.05,.09,2.1),paint,.003)
for z in [.6,2.68]:box('bedroom-window__rail-'+str(z),(5.4,5.82,z),(2.15,.09,.05),paint,.003)
box('wall-east',(6.88,2.9,1.45),(.16,5.8,2.9),wall)
box('wall-south-left',(1.1,-.08,1.45),(2.2,.16,2.9),wall)
box('wall-south-right',(5.2,-.08,1.45),(3.2,.16,2.9),wall)
box('entrance__lintel',(2.9,-.08,2.65),(1.4,.16,.5),wall)
ceiling=box('ceiling',(3.4,2.9,3),(6.96,5.96,.2),wall)
# West facade has a real large opening, jambs, sill and three framed panes.
for name,y,length in [('end-1',.4,.8),('end-2',5.5,.6)]:box('wall-west__'+name,(-.08,y,1.45),(.16,length,2.9),wall)
box('wall-west__sill',(-.08,3,.25),(.16,4.4,.5),wall)
box('wall-west__header',(-.08,3,2.8),(.16,4.4,.2),wall)
for y in [.8,2.2667,3.7333,5.2]:box('window__mullion-'+str(y),(0,y,1.6),(.095,.055,2.2),paint,.004)
for z in [.53,2.67]:box('window__rail-'+str(z),(0,3,z),(.11,4.48,.06),paint,.004)
box('window__ledge',(.08,3,.49),(.36,4.55,.055),wood)
# Clear opening: glass omitted in the portable model to avoid glTF transmission shadows.
box('skirting__north',(3.4,5.77,.055),(6.8,.035,.11),paint,.003)
box('skirting__east',(6.77,2.9,.055),(.035,5.8,.11),paint,.003)
box('bedroom-divider',(4.28,4.63,1.45),(.12,2.5,2.9),wall)
asset('sofa-soft','sofa',(1.97,4.96,0),2.8)
asset('coffee-table','coffee-table',(2.05,3.32,.015),1.28)
asset('bed','bed',(5.54,4.58,.02),1.65)
# Draped duvet with small diagonal folds, side overhang and a stitched front hem.
def draped_bed_cloth(name,ymin,ymax,mat,thickness):
 verts=[];faces=[];nx=64;ny=56
 for j in range(ny+1):
  y=ymin+(ymax-ymin)*j/ny
  for i in range(nx+1):
   x=4.62+1.82*i/nx
   fall=max(0,abs(x-5.53)-.76)*2.6+max(0,3.48-y)*1.15
   z=.59+thickness-fall+.018*math.sin(x*18+y*12)+.008*math.sin(y*34-x*5)
   verts.append((x,y,z))
 for j in range(ny):
  for i in range(nx):
   k=j*(nx+1)+i;faces.append((k,k+1,k+nx+2,k+nx+1))
 mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.uv_layers.new()
 for poly in mesh.polygons:
  poly.use_smooth=True
  for li in poly.loop_indices:
   v=mesh.vertices[mesh.loops[li].vertex_index].co;mesh.uv_layers.active.data[li].uv=(v.x,v.y)
 o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);finish(o,name,mat)
 solid=o.modifiers.new('Quilt edge thickness','SOLIDIFY');solid.thickness=.014
 return o

draped_bed_cloth('bed__duvet',3.22,5.17,linen,0)
draped_bed_cloth('bed__folded-throw',3.43,3.89,fabric,.027)
for i,x in enumerate([5.12,5.94]):
 p=box('bed__pillow-'+str(i),(x,5.25,.67),(.70,.48,.20),linen,.095)
 p.rotation_euler[0]=-.08
# Rounded pillows on the sofa.

for i,x in enumerate([.67,2.97]):
    o=box('sofa__pillow-'+str(i),(x,4.84,.78),(.44,.16,.43),linen,.078);o.rotation_euler[1]=(-.2 if i==0 else .15)
# Area rug and dining setting.
box('rug',(2.05,3.45,.034),(2.8,1.95,.015),linen,.006)
box('dining-table__top',(2.25,1.38,.765),(1.55,.84,.07),wood,.045)
for x in [1.64,2.86]:
 for y in [1.1,1.66]:box(f'dining-table__leg-{x}-{y}',(x,y,.375),(.055,.055,.75),metal)
asset('chair','chair-1',(2.25,.56,0),.49,0)
asset('chair','chair-2',(2.25,2.15,0),.49,math.pi)
# Cabinet reveals are physical gaps, not lines painted over the front.
box('kitchen__carcass',(6.45,1.35,.47),(.7,2.2,.9),wood)
box('kitchen__worktop',(6.43,1.35,.945),(.78,2.26,.05),ceramic)
for i in range(4):
 y=.52+i*.55
 box('kitchen__door-'+str(i),(6.065,y,.49),(.04,.533,.8),paint,.006)
 box('kitchen__handle-'+str(i),(6.027,y,.78),(.018,.2,.014),metal,.004)
box('kitchen__backsplash',(6.775,1.35,1.25),(.025,2.26,.55),ceramic)
for i in range(3):box('kitchen-upper__door-'+str(i),(6.52,.62+i*.73,2.12),(.48,.712,.72),paint,.006)
# Ivory curtains: real sinusoidal folds and weighted hem.
for side,ystart in [('a',.86),('b',4.57)]:
 verts=[];faces=[];nu=64;nv=18
 for j in range(nv+1):
  z=.12+j*(2.6/nv)
  for i in range(nu+1):
   y=ystart+i*.58/nu;x=.15+.042*math.sin(i/nu*math.pi*10)+.008*math.sin(z*4+i*.3)
   verts.append((x,y,z))
 for j in range(nv):
  for i in range(nu):
   k=j*(nu+1)+i;faces.append((k,k+1,k+nu+2,k+nu+1))
 mesh=bpy.data.meshes.new('Draped linen');mesh.from_pydata(verts,[],faces);mesh.uv_layers.new()
 for poly in mesh.polygons:
  poly.use_smooth=True
  for li in poly.loop_indices:
   v=mesh.vertices[mesh.loops[li].vertex_index].co;mesh.uv_layers.active.data[li].uv=(v.y*2,v.z*2)
 o=bpy.data.objects.new('curtain-'+side,mesh);bpy.context.collection.objects.link(o);finish(o,o.name,linen)
 solid=o.modifiers.new('Fabric thickness','SOLIDIFY');solid.thickness=.002
# A ceramic vase, books and a small sculptural branch.
for i in range(3):box('books__book-'+str(i),(2.05,3.32,.59+i*.026),(.3,.22,.024),paint if i%2 else wood,.004)
bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=24,location=(1.69,3.34,.69));vase=bpy.context.object;vase.scale=(.07,.07,.13);finish(vase,'vase',ceramic)
# Small balcony and neighboring facade: actual geometry supplies near parallax.
box('balcony__slab',(-.68,3,-.06),(1.2,4.7,.12),wall)
for y in [1,2,3,4,5]:box('balcony__post-'+str(y),(-1.22,y,.58),(.022,.025,1.16),metal,.003)
box('balcony__rail',(-1.22,3,1.15),(.03,4.4,.03),metal,.003)
box('neighbor__facade',(-4.5,7,2.1),(.2,3.8,6.6),wall)
for y in [5.7,7.2,8.7]:
 for z in [.3,2.2,4.1]:
  box(f'neighbor__window-{y}-{z}',(-4.37,y,z),(.04,.8,1.05),metal,.008)
  box(f'neighbor__sill-{y}-{z}',(-4.24,y,z-.55),(.28,1,.04),wood,.005)
# Only exterior daylight; no uniform ceiling fill in every room.
world=bpy.data.worlds.new('CC0 illustrative city sky');world.use_nodes=True;scene.world=world
nodes=world.node_tree.nodes;env=nodes.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(ASSETS/'city-sky.exr'));env.image.pack()
world.node_tree.links.new(env.outputs['Color'],nodes.get('Background').inputs['Color']);nodes.get('Background').inputs['Strength'].default_value=.65
sun=bpy.data.lights.new('Window daylight','SUN');sun.energy=1.8;sun.angle=math.radians(5);sun.color=(1,.92,.81)
o=bpy.data.objects.new('Window daylight',sun);bpy.context.collection.objects.link(o);o.rotation_euler=Vector((1,.35,-.55)).to_track_quat('-Z','Y').to_euler()
area=bpy.data.lights.new('Exterior sky opening','AREA');area.energy=110;area.shape='RECTANGLE';area.size=4;area.size_y=2
light=bpy.data.objects.new(area.name,area);bpy.context.collection.objects.link(light);light.location=(-.45,3,1.9);light.rotation_euler=Vector((1,0,-.08)).to_track_quat('-Z','Y').to_euler()
north=bpy.data.lights.new('North sky opening','AREA');north.energy=95;north.shape='RECTANGLE';north.size=2;north.size_y=2
north_obj=bpy.data.objects.new(north.name,north);bpy.context.collection.objects.link(north_obj);north_obj.location=(5.4,6.15,1.9);north_obj.rotation_euler=Vector((0,-1,-.05)).to_track_quat('-Z','Y').to_euler()
# Apply all modifiers so Blender IDs and GLB nodes retain one-to-one names.
for o in list(bpy.data.objects):
 if o.type=='MESH':
  bpy.context.view_layer.objects.active=o
  for mod in list(o.modifiers):
   try:bpy.ops.object.modifier_apply(modifier=mod.name)
   except RuntimeError:o.modifiers.remove(mod)
# Remove stale absolute paths and unused source data before packing the public model.
for image in bpy.data.images:
 if image.type=='IMAGE' and image.size[0]:
  if not image.packed_file:image.pack()
  image.filepath='//textures/'+Path(image.name).name
for m in bpy.data.materials:m.use_fake_user=False
for t in list(bpy.data.texts):bpy.data.texts.remove(t)
bpy.ops.outliner.orphans_purge(do_recursive=True)
bpy.context.view_layer.update()
# glTF has punctual lights, no Blender area/world lights: explicit window-spot approximation.
for name in ['Exterior sky opening','North sky opening']:
 bpy.data.lights[name].type='SPOT'
 source=bpy.data.lights[name];source.spot_size=math.radians(155);source.spot_blend=1;source.shadow_soft_size=.6
bpy.ops.export_scene.gltf(filepath=str(ROOT/'daylight-apartment.glb'),export_format='GLB',export_extras=True,export_lights=True)
for name,width in [('Exterior sky opening',4),('North sky opening',2)]:
 bpy.data.lights[name].type='AREA'
 source=bpy.data.lights[name];source.shape='RECTANGLE';source.size=width;source.size_y=2
cam_data=bpy.data.cameras.new('Editorial camera');cam=bpy.data.objects.new(cam_data.name,cam_data);bpy.context.collection.objects.link(cam);scene.camera=cam
cam.location=(5.65,.9,1.48);target=Vector((1.9,4.2,1.48));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=32
scene.render.resolution_x=1440;scene.render.resolution_y=1080;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(ROOT/'preview-living.png')
scene.render.filepath='//preview-living.png'
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'daylight-apartment.blend'),compress=True)
scene.render.filepath=str(ROOT/'preview-living.png')
bpy.ops.render.render(write_still=True)
cam.location=(5.5,1.4,1.4);cam.rotation_euler=(Vector((5.5,4.8,1.4))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=32
scene.render.filepath=str(ROOT/'preview-bedroom.png');bpy.ops.render.render(write_still=True)
ceiling.hide_render=True;scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.color_type='MATERIAL';scene.display.shading.light='STUDIO'
cam.location=(3.4,2.9,14);cam.rotation_euler=(0,0,0);cam.data.type='ORTHO';cam.data.ortho_scale=8.5
scene.render.resolution_x=1000;scene.render.resolution_y=900;scene.render.filepath=str(ROOT/'layout.png');bpy.ops.render.render(write_still=True)
manifest={'name':'Daylight apartment','kind':'synthetic','units':'metres','native':'daylight-apartment.blend','preview':'daylight-apartment.glb','exterior':'Illustrative city sky and original neighboring facade; not a site photograph','suggested_viewpoints':[{'name':'Living','eye':[5.65,.9,1.48],'yaw':138.65,'pitch':0,'lens':32},{'name':'Bedroom','eye':[5.5,1.4,1.4],'yaw':90,'pitch':0,'lens':32}], 'sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['daylight-apartment.blend','daylight-apartment.glb','preview-living.png','preview-bedroom.png','layout.png']}}
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
