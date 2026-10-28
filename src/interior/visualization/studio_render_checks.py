"""Blender-side lighting inspection and conservative black-frame detection.

Presence checks identify obviously incomplete imports, not visual quality.
Connected procedural shaders are treated as potential emitters and must pass probes.
"""
from pathlib import Path


def connected_nodes(material):
    if not material or not material.use_nodes or not material.node_tree:
        return []
    outputs=[n for n in material.node_tree.nodes if n.type in ('OUTPUT_MATERIAL','OUTPUT_WORLD') and n.is_active_output]
    pending=[link.from_node for node in outputs for socket in node.inputs if socket.name=='Surface' for link in socket.links]
    nodes=[]
    while pending:
        node=pending.pop()
        if node in nodes:
            continue
        nodes.append(node)
        pending.extend(link.from_node for socket in node.inputs for link in socket.links)
    return nodes


def emits(material):
    for node in connected_nodes(material):
        if node.type=='GROUP':
            return True  # Unknown connected shader; a probe decides.
        if node.type not in ('BACKGROUND','EMISSION','BSDF_PRINCIPLED'):
            continue
        strength=node.inputs.get('Strength') or node.inputs.get('Emission Strength')
        color=node.inputs.get('Color') or node.inputs.get('Emission Color')
        if strength and color and (strength.is_linked or strength.default_value>0) and (color.is_linked or max(color.default_value[:3])>0):
            return True
    return False


def inspect_scene(scene):
    import bpy
    lights=[o.name for o in scene.objects if o.type=='LIGHT' and not o.hide_render and o.data.energy>0 and max(o.data.color)>0]
    materials={slot.material for o in scene.objects if o.type in ('MESH','CURVE') and not o.hide_render for slot in o.material_slots if slot.material}
    emitting=[m.name for m in materials if emits(m)]
    world=bool(scene.world and (emits(scene.world) if scene.world.use_nodes else max(scene.world.color)>0))
    missing=[]
    for material in [*materials,scene.world]:
        for node in connected_nodes(material):
            if node.type in ('TEX_IMAGE','TEX_ENVIRONMENT'):
                image=node.image
                if image is None:
                    missing.append(material.name+': '+node.name)
                elif image.source=='FILE' and not image.packed_file and not Path(bpy.path.abspath(image.filepath,library=image.library)).is_file():
                    missing.append(image.name)
    issues=[]
    if not lights and not world and not emitting:
        issues.append('場景沒有可用燈光、環境光或發光材質。GLB 可能只有展示幾何；請接回原生 Blender 場景，或先完成照明設定。')
    if missing:
        issues.append('找不到場景使用的貼圖：'+', '.join(sorted(set(missing))[:10]))
    return dict(status='blocked' if issues else 'needs_probe',light_count=len(lights),world_available=world,
        emissive_materials=emitting,missing_images=sorted(set(missing)),issues=issues,
        note='光源存在不代表亮度或寫實品質合格，仍需試渲染與人工看圖。')


def luminance_report(rgb):
    """Measure reloaded PNG display RGB, without brightening or altering images."""
    values=[max(0,.2126*r+.7152*g+.0722*b) for r,g,b in rgb]
    if not values:
        return dict(status='blocked',reason='圖片沒有可讀像素')
    mean=sum(values)/len(values)
    dark=sum(v<10/255 for v in values)/len(values)
    blocked=mean<5/255 or (dark>.995 and mean<.05)
    return dict(status='blocked' if blocked else 'passed',mean_encoded_luminance=mean,
        bright_fraction=sum(v>.98 for v in values)/len(values),min_luminance=min(values),max_luminance=max(values),
        measurement='sampled PNG RGB; heuristic, not photometric illuminance',
        dark_fraction=dark,sample_count=len(values),reason='畫面接近全黑，請檢查光照、曝光、鏡位與遮擋。' if blocked else None)


def inspect_image(image):
    from array import array
    count=len(image.pixels)//4
    stride=max(1,count//4096)
    # Blender RNA slicing repeatedly copies/validates a large image buffer.
    # Read once, then take the same samples from ordinary memory (also for 4K).
    pixels=array('f',[0])*(count*4)
    image.pixels.foreach_get(pixels)
    return luminance_report(pixels[i*4:i*4+3] for i in range(0,count,stride))
