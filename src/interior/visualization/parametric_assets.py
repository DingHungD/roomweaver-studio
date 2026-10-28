"""Build bounded Agent-designed assemblies. No model-produced Python is executed."""
import math
import bpy
from mathutils import Matrix, Vector
from generated_parts import parts


def build(recipe,lo,hi):
    purpose=recipe['purpose'];w,d,h=recipe['dimensions']
    if any(not math.isfinite(v) or v<.02 or v>8 for v in (w,d,h)):raise ValueError('參數模型尺寸超出範圍')
    design=recipe.get('design',{});front=recipe.get('front','unknown')
    angle={'-Y':0,'+X':90,'+Y':180,'-X':270}.get(front,0)
    # Build in local coordinates rather than distort the assembled object for a quarter turn.
    lw,ld=(d,w) if angle in (90,270) else (w,d)
    colors={'wood':design.get('wood_color','#C8AD83'),'fabric':design.get('fabric_color','#D6D0C4'),
            'accent':design.get('accent_color','#526674'),'enamel':'#E7E6E2','glass':'#26343B'}
    materials={}
    for key,color in colors.items():
        rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
        linear=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb]
        mat=bpy.data.materials.new('Generated '+key);mat.use_nodes=True;mat.diffuse_color=(*linear,1)
        bsdf=mat.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=(*linear,1)
        bsdf.inputs['Roughness'].default_value=.8 if key=='fabric' else .5 if key=='wood' else .25
        if key in ('wood','fabric'):
            noise=mat.node_tree.nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=35 if key=='wood' else 120
            bump=mat.node_tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.001
            mat.node_tree.links.new(noise.outputs['Fac'],bump.inputs['Height']);mat.node_tree.links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
        materials[key]=mat
    meshes=[]
    for part in parts(purpose,design):
        position=[v*s for v,s in zip(part['center'],(lw,ld,h))];size=[v*s for v,s in zip(part['size'],(lw,ld,h))]
        if part.get('shape')=='lathe':
            position=[v*s for v,s in zip(part['origin'],(lw,ld,h))]
            vertices=[];faces=[];n=48
            for radius,z in part['profile']:
                vertices.extend((math.cos(j*2*math.pi/n)*radius*lw,math.sin(j*2*math.pi/n)*radius*ld,z*h) for j in range(n))
            for ring in range(len(part['profile'])-1):
                for j in range(n):faces.append((ring*n+j,ring*n+(j+1)%n,(ring+1)*n+(j+1)%n,(ring+1)*n+j))
            mesh=bpy.data.meshes.new(part['name']);mesh.from_pydata(vertices,[],faces);mesh.update()
            obj=bpy.data.objects.new('Generated '+part['name'],mesh);bpy.context.scene.collection.objects.link(obj);obj.location=position
            for poly in mesh.polygons:poly.use_smooth=True
        else:
            if part.get('shape')=='sphere':bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=.5,location=position)
            else:bpy.ops.mesh.primitive_cube_add(size=1,location=position)
            obj=bpy.context.object;obj.name='Generated '+part['name'];obj.dimensions=size
            bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
            if part.get('shape')!='sphere':
                bevel=obj.modifiers.new('Concept soft edge','BEVEL');bevel.width=min(.006,min(size)/5);bevel.segments=3
        obj.data.materials.append(materials[part['material']]);meshes.append(obj)
    transform=Matrix.Translation(Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z)))@Matrix.Rotation(math.radians(angle),4,'Z')
    for obj in meshes:obj.matrix_world=transform@obj.matrix_world
    bpy.context.view_layer.update()
    return meshes
