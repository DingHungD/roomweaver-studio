"""Source-only Cycles pictures and panoramas; never execute the editor pipeline."""
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def fingerprint(objects):
    """Cover original mesh data, placements, assignments and shader values."""
    import numpy as np
    digest=hashlib.sha256()
    def add(value):digest.update(repr(value).encode())
    def bulk(collection,property,width=1,dtype='float32'):
        data=np.empty(len(collection)*width,dtype=dtype)
        collection.foreach_get(property,data);digest.update(data.tobytes())
    meshes=set();materials=set()
    for obj in objects:
        add((obj.name,obj.type,tuple(tuple(row) for row in obj.matrix_world),obj.hide_render))
        if obj.type!='MESH':continue
        add((obj.data.name,tuple(s.material.name if s.material else None for s in obj.material_slots)))
        meshes.add(obj.data);materials.update(s.material for s in obj.material_slots if s.material)
    for mesh in sorted(meshes,key=lambda m:m.name):
        add(mesh.name)
        bulk(mesh.vertices,'co',3)
        bulk(mesh.loops,'vertex_index',dtype='int32')
        for property in ('loop_start','loop_total','material_index'):bulk(mesh.polygons,property,dtype='int32')
        bulk(mesh.polygons,'use_smooth',dtype='bool')
        for layer in mesh.uv_layers:
            add(layer.name)
            bulk(layer.data,'uv',2)
    for mat in sorted(materials,key=lambda m:m.name):
        add((mat.name,tuple(mat.diffuse_color),mat.use_nodes))
        if mat.node_tree:
            for node in mat.node_tree.nodes:
                add((node.name,node.bl_idname))
                for socket in node.inputs:
                    if hasattr(socket,'default_value'):
                        value=socket.default_value
                        try:value=tuple(value)
                        except TypeError:pass
                        add((socket.name,value))
                if hasattr(node,'image') and node.image:add((node.image.name,node.image.filepath))
            add(sorted((l.from_node.name,l.from_socket.name,l.to_node.name,l.to_socket.name) for l in mat.node_tree.links))
    return digest.hexdigest()


def auto_eyes(scene,count):
    """Sample walkable floor candidates; avoid using the whole SKP bounding box."""
    import numpy as np
    candidates=[];floors={}
    for obj in scene.objects:
        if obj.type!='MESH' or obj.hide_render:continue
        mesh=obj.data;rotation=obj.matrix_world.to_3x3().inverted_safe().transposed()
        for poly in mesh.polygons:
            normal=(rotation@poly.normal).normalized()
            if abs(normal.z)<.95:continue
            center=obj.matrix_world@poly.center
            # Area weights prevent tiny cabinet/fixture faces dominating floors.
            area=poly.area*abs(obj.matrix_world.to_3x3().determinant())**(2/3)
            if area<.15:continue
            key=round(center.z/.15)
            floors[key]=floors.get(key,0)+area
            candidates.append((center,area,key))
    if not floors:raise ValueError('無法辨識可站立地面；請先提供觀看點')
    # Floors are normally the lowest substantial horizontal surface. The large
    # ceiling level is excluded when a similarly substantial lower level exists.
    peak=max(floors.values());levels=[k for k,a in floors.items() if a>peak*.2]
    level=min(levels);floor=sum(c.z*a for c,a,k in candidates if k==level)/floors[level]
    deps=bpy.context.evaluated_depsgraph_get()
    floor_faces=[c for c,a,k in candidates if k==level]
    lo=np.min([tuple(c) for c in floor_faces],axis=0);hi=np.max([tuple(c) for c in floor_faces],axis=0)
    spacing=max(.65,math.sqrt(max((hi[0]-lo[0])*(hi[1]-lo[1]),1)/1800))
    points=[]
    for x in np.arange(lo[0],hi[0]+spacing/2,spacing):
        for y in np.arange(lo[1],hi[1]+spacing/2,spacing):
            origin=Vector((float(x),float(y),floor+.12))
            hit,loc,*_=scene.ray_cast(deps,origin,Vector((0,0,-1)),distance=.25)
            if not hit or abs(loc.z-floor)>.2:continue
            eye=Vector((float(x),float(y),floor+1.55))
            # Vertical test rejects furniture, solid walls and low ceiling voids.
            hit,*_=scene.ray_cast(deps,origin,Vector((0,0,1)),distance=1.75)
            if hit:continue
            # Reject open outdoor reference planes common in SketchUp files.
            ceiling,*_=scene.ray_cast(deps,eye,Vector((0,0,1)),distance=4.5)
            if not ceiling:continue
            distances=[]
            for i in range(12):
                direction=Vector((math.sin(i*math.tau/12),math.cos(i*math.tau/12),0))
                hit,loc,*_=scene.ray_cast(deps,eye,direction,distance=8)
                distances.append((loc-eye).length if hit else 8)
            if min(distances)<.4:continue
            points.append((eye,min(distances),distances.index(max(distances))*math.tau/12))
    if not points:raise ValueError('找不到安全的自動觀看點；請先提供觀看點')
    chosen=[max(points,key=lambda p:p[1])]
    while len(chosen)<count and len(chosen)<len(points):
        next_point=max(points,key=lambda p:min((p[0]-q[0]).length for q in chosen)*min(p[1],1))
        if min((next_point[0]-q[0]).length for q in chosen)<1.5:break
        chosen.append(next_point)
    return [dict(name=f'視點 {i+1:02}',eye=list(p[0]),yaw=p[2]) for i,p in enumerate(chosen)]


def main():
    request=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
    output=Path(request['output']);site=output/'site'
    bpy.ops.wm.open_mainfile(filepath=request['native'])
    bpy.context.view_layer.update()
    scene=bpy.context.scene;original=list(scene.objects)
    original_content=fingerprint([o for o in original if o.type!='LIGHT'])
    eyes=request.get('viewpoints',[])[:request['views']]
    if len(eyes)<request['views']:
        try:automatic=auto_eyes(scene,request['views'])
        except ValueError:
            if not eyes:raise
            automatic=[]
        for point in automatic:
            if len(eyes)>=request['views']:break
            if all((Vector(point['eye'])-Vector(existing['eye'])).length>=1.5 for existing in eyes):eyes.append(point)
    if request['lighting']=='fixtures':
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        from studio_lighting import apply
        apply(dict(lighting_setup=request['lighting_setup']))
    scene.view_settings.exposure=max(-6,min(6,scene.view_settings.exposure+request.get('exposure',0)))
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from source_device import configure
    write(output/'device-request.json',configure(scene))
    scene.render.engine='CYCLES';scene.cycles.samples=16 if request['quality']=='preview' else 96
    scene.cycles.use_denoising=True;scene.render.image_settings.file_format='JPEG';scene.render.image_settings.quality=92
    scene.render.resolution_percentage=100
    camera_data=bpy.data.cameras.new('SourceSiteCamera');camera=bpy.data.objects.new('SourceSiteCamera',camera_data);scene.collection.objects.link(camera);scene.camera=camera
    fill=None
    if request['lighting']=='preview':
        light=bpy.data.lights.new('SourceSitePreviewFill','POINT');light.energy=180;light.shadow_soft_size=.6
        fill=bpy.data.objects.new(light.name,light);scene.collection.objects.link(fill)
        world=bpy.data.worlds.new('SourceSitePreviewWorld');world.use_nodes=True
        world.node_tree.nodes['Background'].inputs['Color'].default_value=(.7,.8,1,1)
        world.node_tree.nodes['Background'].inputs['Strength'].default_value=.25;scene.world=world
    entries=[]
    for i,point in enumerate(eyes):
        eye=Vector(point['eye']);camera.location=eye
        yaw=point.get('yaw',0);direction=Vector((math.sin(yaw),math.cos(yaw),-.05))
        camera.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
        if fill:fill.location=eye+Vector((0,0,.3))
        entry=dict(id=str(i+1),name=point['name'],eye=point['eye'],still=f'view-{i+1}.jpg',panorama=f'pano-{i+1}.jpg')
        for kind in ('still','panorama'):
            pano=kind=='panorama';camera_data.type='PANO' if pano else 'PERSP'
            if pano:camera_data.panorama_type='EQUIRECTANGULAR'
            else:camera_data.lens=20
            width=(1024 if request['quality']=='preview' else 4096) if pano else (800 if request['quality']=='preview' else 1920)
            scene.render.resolution_x=width;scene.render.resolution_y=width//2 if pano else width*3//4
            scene.render.filepath=str(site/entry[kind]);bpy.ops.render.render(write_still=True)
            write(output/'source-progress.json',dict(completed=i*2+(2 if pano else 1),total=len(eyes)*2,current=point['name']))
        entries.append(entry)
    # No save_mainfile call is permitted in this worker.
    after=fingerprint([o for o in original if o.type!='LIGHT'])
    # Mesh/camera/empty fingerprint excludes the intentionally overridden lamps.
    # Compare against an independently computed before value for that same set.
    preserved=after==original_content
    write(output/'preservation.json',dict(preserved=preserved,fingerprint_version=2,before=original_content,after=after,view_count=len(entries)))
    if not preserved:raise ValueError('來源模型保留檢查失敗')
    write(site/'tour.json',dict(title=request['title'],quality=request['quality'],kind='360-panorama',lighting=request['lighting'],views=entries))


if __name__=='__main__':
    main()
