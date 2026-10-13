"""Physical metre UVs and a baked colour tile for procedural surface previews.

Native node trees remain untouched. The preview tile is evaluated by Cycles,
not guessed from node names or an average colour.
"""
import math
import bpy

def ensure_uv(obj):
    if obj.type!='MESH':raise ValueError('材質目標尚非網格，不能驗證 UV')
    mesh=obj.data
    active=mesh.uv_layers.active
    valid=active and all(math.isfinite(v) for uv in active.data for v in uv.uv)
    if valid:
        def area(face):
            points=[active.data[i].uv for i in face.loop_indices]
            return abs(sum(points[i].x*points[(i+1)%len(points)].y-points[(i+1)%len(points)].x*points[i].y for i in range(len(points))))
        valid=all(area(p)>1e-10 for p in mesh.polygons if p.area>1e-10)
    uv=active or mesh.uv_layers.new(name='StudioMetres')
    if not valid:
        normal_matrix=obj.matrix_world.to_3x3().inverted().transposed()
        for face in mesh.polygons:
            normal=normal_matrix@face.normal
            axis=max(range(3),key=lambda i:abs(normal[i]))
            axes=(0,1) if axis==2 else ((0,2) if axis==1 else (1,2))
            for loop in face.loop_indices:
                p=obj.matrix_world@mesh.vertices[mesh.loops[loop].vertex_index].co
                uv.data[loop].uv=(p[axes[0]],p[axes[1]])
    # Explicit UV Map nodes in downloaded materials may use their own layer name.
    for material in mesh.materials:
        if material and material.use_nodes:
            for node in material.node_tree.nodes:
                if node.type=='UVMAP' and node.uv_map and node.uv_map not in mesh.uv_layers:
                    layer=mesh.uv_layers.new(name=node.uv_map)
                    for i,item in enumerate(uv.data):layer.data[i].uv=item.uv
    return 'preserved' if valid else 'generated_metres'

def preview_tile(material, output):
    """Bake a one-metre tile without illumination, validate it, return preview PBR."""
    if not material.use_nodes:return material,dict(mode='constant')
    shaders=[n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED']
    outputs=[n for n in material.node_tree.nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output]
    if len(shaders)!=1 or not outputs or not outputs[0].inputs['Surface'].is_linked or outputs[0].inputs['Surface'].links[0].from_node!=shaders[0]:
        raise ValueError('材質預覽含複合表面節點，不能可靠烘焙；保留原件並改試 PBR 候選')
    source_shader=shaders[0]
    transmission=source_shader.inputs.get('Transmission Weight');alpha=source_shader.inputs.get('Alpha')
    if (transmission and (transmission.is_linked or transmission.default_value>0)) or (alpha and (alpha.is_linked or alpha.default_value<1)):
        return material,dict(mode='native_transparency',native_shader_preserved=True,warning='保留透明／玻璃材質；不套用不透明貼圖近似')
    original_scene=bpy.context.scene
    original_active=bpy.context.view_layer.objects.active;selected=list(bpy.context.selected_objects)
    # AO/geometry nodes must not sample furniture or walls around the room origin.
    scene=bpy.data.scenes.new('Studio material probe');bpy.context.window.scene=scene
    bpy.ops.mesh.primitive_plane_add(size=1)
    plane=bpy.context.object;plane.name='Temporary material probe'
    probe=material.copy();plane.data.materials.append(probe);ensure_uv(plane)
    image=bpy.data.images.new('Studio surface colour',width=512,height=512,alpha=False)
    node=probe.node_tree.nodes.new('ShaderNodeTexImage');node.image=image;probe.node_tree.nodes.active=node
    try:
        scene.render.engine='CYCLES';scene.cycles.samples=4;scene.cycles.device='CPU'
        bpy.ops.object.bake(type='DIFFUSE',pass_filter={'COLOR'},use_clear=True,margin=2)
        pixels=list(image.pixels);rgb=[pixels[i] for i in range(len(pixels)) if i%4!=3]
        if not rgb or any(not math.isfinite(x) for x in rgb) or sum(rgb)/len(rgb)<.003:
            raise ValueError('材質貼圖探針接近全黑或無效；保留原件並改試候選')
        image.filepath_raw=str(output/'surface-preview.png');image.file_format='PNG';image.save();image.pack()
        # Bake roughness independently as data, never as illumination or sRGB colour.
        probe_shader=next(n for n in probe.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        output_node=next(n for n in probe.node_tree.nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output)
        baked={};means={}
        for channel in ('Roughness','Metallic','Normal'):
            texture=bpy.data.images.new('Studio surface '+channel.lower(),width=512,height=512,alpha=False)
            texture.colorspace_settings.name='Non-Color';node.image=texture
            if channel=='Normal':
                probe.node_tree.links.new(probe_shader.outputs['BSDF'],output_node.inputs['Surface'])
                bpy.ops.object.bake(type='NORMAL',normal_space='TANGENT',use_clear=True,margin=2)
            else:
                socket=probe_shader.inputs[channel];emission=probe.node_tree.nodes.new('ShaderNodeEmission')
                if socket.is_linked:probe.node_tree.links.new(socket.links[0].from_socket,emission.inputs['Color'])
                else:emission.inputs['Color'].default_value=(socket.default_value,)*3+(1,)
                probe.node_tree.links.new(emission.outputs[0],output_node.inputs['Surface'])
                bpy.ops.object.bake(type='EMIT',use_clear=True,margin=2)
            values=list(texture.pixels)
            if any(not math.isfinite(x) or x<0 or x>1.001 for x in values):raise ValueError(channel+' 貼圖無效；保留原件')
            texture.filepath_raw=str(output/('surface-'+channel.lower()+'.png'));texture.file_format='PNG';texture.save();texture.pack()
            baked[channel]=texture;means[channel]=sum(values[::4])/len(values[::4])
        preview=material.copy();preview.name=material.name+' · Studio preview'
        shader=next(n for n in preview.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        for key in ('Base Color','Roughness','Metallic','Normal'):
            for link in list(shader.inputs[key].links):preview.node_tree.links.remove(link)
        for channel,texture in baked.items():
            tex_node=preview.node_tree.nodes.new('ShaderNodeTexImage');tex_node.image=texture
            source=tex_node.outputs['Color']
            if channel=='Normal':
                normal=preview.node_tree.nodes.new('ShaderNodeNormalMap')
                preview.node_tree.links.new(source,normal.inputs['Color']);source=normal.outputs['Normal']
            preview.node_tree.links.new(source,shader.inputs[channel])
        tex=preview.node_tree.nodes.new('ShaderNodeTexImage');tex.image=image
        preview.node_tree.links.new(tex.outputs['Color'],shader.inputs['Base Color'])
        preview['studio_preview']='Cycles colour tile; native shader retained'
        return preview,dict(mode='baked_colour_tile',resolution=512,metres_per_tile=1,mean_linear=sum(rgb)/len(rgb),native_shader_preserved=True,roughness_baked=True,metallic_baked=True,normal_baked=True,channel_means=means,other_channels='保留原常數通道；位移、複合表面與非重複座標仍受 GLB 限制')
    finally:
        mesh=plane.data;bpy.data.objects.remove(plane,do_unlink=True);bpy.data.meshes.remove(mesh);bpy.data.materials.remove(probe)
        bpy.context.window.scene=original_scene;bpy.data.scenes.remove(scene)
        for o in selected:
            if o.name in bpy.context.view_layer.objects:o.select_set(True)
        bpy.context.view_layer.objects.active=original_active
