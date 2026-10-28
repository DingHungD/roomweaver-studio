"""Append registered native props, preserving shape, UVs and source provenance."""
import hashlib
import math
from pathlib import Path
import bpy
from mathutils import Vector,Matrix


def place(asset, kind, host, lo, hi, thickness, width, depth, front, tier, created):
    path=Path(asset['file'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']:raise ValueError('精修素材雜湊不符')
    previous=set(bpy.data.objects)
    with bpy.data.libraries.load(str(path),link=False) as (source,target):target.objects=list(source.objects)
    loaded=[o for o in target.objects if o]
    meshes=[];repairs=[]
    try:
        for o in loaded:
            if not o.users_collection:bpy.context.scene.collection.objects.link(o)
        bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
        angles={'+X':0,'+Y':math.pi/2,'-X':math.pi,'-Y':-math.pi/2}
        rotation=Matrix.Rotation(angles[front]-angles[asset['front']],4,'Z')
        for o in loaded:
            if o.type not in ('MESH','CURVE') or o.hide_render:continue
            mesh=bpy.data.meshes.new_from_object(o.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps)
            mesh.transform(rotation@o.matrix_world)
            part=bpy.data.objects.new('Shelf '+kind+' '+o.name,mesh);bpy.context.scene.collection.objects.link(part);meshes.append(part)
        from studio_render_checks import connected_nodes
        replacements={}
        for part in meshes:
            for i,mat in enumerate(part.data.materials):
                if not mat:continue
                bad=[n for n in connected_nodes(mat) if n.type in ('TEX_IMAGE','TEX_ENVIRONMENT') and (not n.image or n.image.source=='FILE' and not n.image.packed_file and not Path(bpy.path.abspath(n.image.filepath,library=n.image.library)).is_file())]
                if not bad:continue
                # Page edges have an unambiguous role. Retain all cover materials;
                # do not invent or recolor an unknown missing product texture.
                if kind!='magazines' or 'page' not in mat.name.lower():raise ValueError('原素材有缺失貼圖，不能安全修復：'+mat.name)
                if mat.name not in replacements:
                    fixed=bpy.data.materials.new('Repaired paper edges');fixed.use_nodes=True
                    shader=fixed.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(.78,.76,.69,1);shader.inputs['Roughness'].default_value=.85
                    replacements[mat.name]=fixed;repairs.append(dict(material=mat.name,reason='缺失頁緣貼圖，改為中性紙張表面；封面原貼圖保持'))
                part.data.materials[i]=replacements[mat.name]
        points=[v.co for o in meshes for v in o.data.vertices]
        if not points:raise ValueError('素材無可見網格')
        a=Vector([min(v[i] for v in points) for i in range(3)]);b=Vector([max(v[i] for v in points) for i in range(3)])
        size=b-a;units=Vector([max(abs(s),1e-5) for s in host.matrix_world.to_scale()]);span=hi-lo
        room=Vector([(span[i]-2*thickness[i])*units[i]-.03 for i in range(3)])
        room.z=((span.z-thickness[2])*.25-thickness[2])*units.z-.02
        factor=min(1,*[room[i]/max(size[i],1e-5) for i in range(3)])
        minimum=asset.get('min_scale',.85)
        if factor<minimum:raise ValueError(f'原件尺寸 {tuple(round(v,3) for v in size)} m，層板淨空 {tuple(round(v,3) for v in room)} m，需縮至 {factor:.1%}，低於允許 {minimum:.0%}')
        center=(lo+hi)/2;center.z=lo.z+(span.z-thickness[2])*.25*tier+thickness[2]
        offset=(a+b)/2;offset.z=a.z
        transform=host.matrix_world@Matrix.Translation(center)@Matrix.Diagonal((factor/units.x,factor/units.y,factor/units.z,1))@Matrix.Translation(-offset)
        for part in meshes:
            part.matrix_world=transform;part['studio_refined_from']=host.get('studio_id');part['studio_content_asset']=kind
            created.append(part)
        return dict(kind=kind,status='placed',tier=tier,source='registered_native_asset',source_url=asset['source_url'],license=asset['license'],sha256=asset['sha256'],scale=factor,dimensions=list(size*factor),dimension_source='source_model',material_repairs=repairs,installation_verified=False)
    except Exception:
        for o in meshes:bpy.data.objects.remove(o,do_unlink=True)
        raise
    finally:
        for o in loaded:
            if o not in previous:bpy.data.objects.remove(o,do_unlink=True)
