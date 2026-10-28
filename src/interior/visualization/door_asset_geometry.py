"""Fit catalog door leaves to the existing parametric opening, retaining hinges."""
import math
import bpy
from mathutils import Vector
_CACHE={}
FILES={}

def load_asset(spec):
    key=(spec['path'],spec['kind'])
    if key in _CACHE:return _CACHE[key]
    prior=set(bpy.data.images)
    if spec['kind']=='material':
        with bpy.data.libraries.load(spec['path'],link=False) as (src,dst):dst.materials=src.materials
        mats=[m for m in dst.materials if m]
        if len(mats)!=1:raise ValueError('門材質檔包含多個材質，請改選單一材質候選')
        result=mats[0]
    else:
        with bpy.data.libraries.load(spec['path'],link=False) as (src,dst):dst.objects=src.objects
        loaded=[o for o in dst.objects if o];meshes=[]
        try:
            for o in loaded:bpy.context.scene.collection.objects.link(o)
            bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
            for o in loaded:
                if o.type not in ('MESH','CURVE'):continue
                if any(t in o.name.lower() for t in ('frame','wall','jamb')):
                    continue
                data=bpy.data.meshes.new_from_object(o.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps)
                if not data.vertices:continue
                data.transform(o.matrix_world)
                node=bpy.data.objects.new('Door template',data);bpy.context.scene.collection.objects.link(node);meshes.append(node)
            if not meshes or len(meshes)>100:raise ValueError('門片模型沒有有效幾何或組成過多')
            bpy.ops.object.select_all(action='DESELECT')
            for o in meshes:o.select_set(True)
            bpy.context.view_layer.objects.active=meshes[0];bpy.ops.object.join()
            joined=bpy.context.view_layer.objects.active
            result=joined.data.copy();bpy.data.objects.remove(joined,do_unlink=True);meshes=[]
        finally:
            for o in loaded+meshes:
                if o.name in bpy.data.objects:bpy.data.objects.remove(o,do_unlink=True)
    for image in set(bpy.data.images)-prior:
        if image.source in ('FILE','TILED') and not image.packed_file and not image.has_data:raise ValueError('門素材缺少貼圖，保留原件')
        if image.has_data and not image.packed_file:image.pack()
    _CACHE[key]=result
    return result

def apply(obj,spec,origin,direction,normal,x,y,z,w,d,h,transform):
    asset=load_asset(spec)
    if spec['kind']=='material':
        obj.data.materials.clear();obj.data.materials.append(asset)
        from surface_uv import ensure_uv
        ensure_uv(obj)
        return
    points=[v.co.copy() for v in asset.vertices]
    lo=Vector([min(p[i] for p in points) for i in range(3)]);hi=Vector([max(p[i] for p in points) for i in range(3)]);extent=hi-lo
    if min(extent)<=.00001:raise ValueError('門片模型尺寸無效')
    # Vertical source geometry only; a flat or complete-room asset is not a leaf.
    depth=0 if extent.x<extent.y else 1;width=1-depth
    if extent[depth]/min(extent[width],extent.z)>.30:raise ValueError('候選過厚，不像單片門；請改選門片模型')
    if not .5<=w/extent[width]/(h/extent.z)<=2:raise ValueError('門片寬高比例差距過大，請改選候選')
    mesh=asset.copy();center=(lo+hi)/2
    for v in mesh.vertices:
        q=v.co-center
        position=origin+direction*(x+q[width]*w/extent[width])+normal*(y+q[depth]*d/extent[depth]*(-1 if depth==0 else 1))+Vector((0,0,z+q.z*h/extent.z))
        v.co=transform@position if transform is not None else position
    mesh.update();obj.data=mesh
