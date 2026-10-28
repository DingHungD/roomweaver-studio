"""Real Blender counterexample: an actual bulb hidden behind a shade and pole."""
import json
import math
from pathlib import Path
import sys
import bpy

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src/interior/visualization'))
from fixture_lighting_evidence import surface_anchors,same_mesh_lights
from mathutils import Vector

bpy.ops.wm.read_factory_settings(use_empty=True)
n=32;vertices=[]
for radius,z in ((.4,1.0),(.25,1.5)):
    vertices.extend((radius*math.cos(i*math.tau/n),radius*math.sin(i*math.tau/n),z) for i in range(n))
faces=[(i,(i+1)%n,n+(i+1)%n,n+i) for i in range(n)]+[tuple(range(n,2*n))]
mesh=bpy.data.meshes.new('Actual hollow shade');mesh.from_pydata(vertices,[],faces);mesh.update()
shade=bpy.data.objects.new('Shade',mesh);bpy.context.scene.collection.objects.link(shade);shade['studio_id']='shade'
bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,radius=.06,location=(0,0,1.25))
bulb=bpy.context.object;bulb['studio_id']='bulb'
bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.02,depth=1.2,location=(0,0,.6))
pole=bpy.context.object;pole['studio_id']='pole'
bpy.context.view_layer.update()
anchors=surface_anchors([shade,pole,bulb])
assert len(anchors)<=256
assert any(a['object_id']=='bulb' and a['surface_scope']=='component' and a['normal'][2]<-.5 for a in anchors)
assert all(abs(sum(v*v for v in a['normal'])-1)<1e-4 for a in anchors)
bulb.scale.x=-1;bpy.context.view_layer.update()
mirrored=surface_anchors([shade,pole,bulb])
assert any(a['object_id']=='bulb' and a['normal'][2]<-.5 for a in mirrored)
bulb.scale.x=1
twin=bulb.copy();twin.data=bulb.data;bpy.context.scene.collection.objects.link(twin);twin['studio_id']='twin';twin.location.x=2
bpy.context.view_layer.update()
anchor=next(a for a in anchors if a['object_id']=='bulb' and a['normal'][2]<-.5)
normal=Vector(anchor['normal']);position=Vector(anchor['position'])+normal*.015
design=dict(groups=[dict(id='source',children=['bulb'],deleted=False)],lighting_setup=dict(lights=[dict(id='fixture-confirmed',origin='proposal',enabled=True,power=8,
    group_id='source',position=list(position),rotation=list(normal.to_track_quat('-Z','Y').to_euler()),kind='POINT',color=[1,1,1],size=.02)]))
matched=same_mesh_lights(design,{'bulb':bulb},[twin])
assert matched['twin'][0]['source_light_id']=='fixture-confirmed'
twin.scale*=2;bpy.context.view_layer.update()
assert not same_mesh_lights(design,{'bulb':bulb},[twin])
twin.scale*=.5;twin.data=bulb.data.copy();bpy.context.view_layer.update()
assert not same_mesh_lights(design,{'bulb':bulb},[twin])
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
(output/'inner-surface-verification.json').write_text(json.dumps(dict(status='passed',anchors=len(anchors),
    bulb_anchors=sum(a['object_id']=='bulb' for a in anchors),mirrored_anchors=len(mirrored),
    tests=['real inner bulb sampled despite envelope occlusion','outward normals','mirrored component winding','bounded anchor inventory',
           'exact linked emitting mesh recognition','different scale and different mesh datablock rejected'])),encoding='utf-8')
print('Real Blender inner bulb and reflection checks passed')
