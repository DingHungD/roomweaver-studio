"""Temporary glTF-compatible outputs for light shaders assigned to mesh slots.

Some imported fixtures use Output Light in mesh materials. Cycles renders these
but the glTF exporter cannot discover their emission. Native shaders stay intact.
"""
from contextlib import contextmanager
import bpy


def light_output(material):
    if not material or not material.use_nodes:return None
    nodes=material.node_tree.nodes
    if any(n.type=='OUTPUT_MATERIAL' and n.is_active_output and n.inputs['Surface'].is_linked for n in nodes):return None
    return next((n for n in nodes if n.type=='OUTPUT_LIGHT' and n.inputs['Surface'].is_linked),None)


@contextmanager
def material_overrides(overrides):
    """Swap slots by index. Clearing slots resets polygon material indices."""
    changed=[]
    try:
        for obj,original,materials in overrides:
            if len(original)!=len(materials) or len(obj.data.materials)!=len(original):
                raise ValueError('預覽材質槽數量不符，保留原件')
            for index,material in enumerate(materials):
                changed.append((obj.data,index,obj.data.materials[index]))
                obj.data.materials[index]=material
        yield
    finally:
        for data,index,material in reversed(changed):data.materials[index]=material


@contextmanager
def compatible_emission(objects):
    replacements={};slots=[];created=[]
    try:
        seen=set()
        for obj in objects:
            if obj.type!='MESH' or obj.data in seen:continue
            seen.add(obj.data)
            for index,material in enumerate(list(obj.data.materials)):
                if not material or not material.use_nodes:continue
                light=light_output(material)
                if not light:continue
                if material not in replacements:
                    preview=material.copy();created.append(preview)
                    preview.name=material.name+' preview emission'
                    output=preview.node_tree.nodes.new('ShaderNodeOutputMaterial');output.is_active_output=True
                    source=preview.node_tree.nodes[light.name].inputs['Surface'].links[0].from_socket
                    preview.node_tree.links.new(source,output.inputs['Surface'])
                    replacements[material]=preview
                slots.append((obj.data,index,material))
                obj.data.materials[index]=replacements[material]
        yield [m.name for m in replacements]
    finally:
        for data,index,material in slots:data.materials[index]=material
        for material in created:bpy.data.materials.remove(material)
