"""Restore one original assembly without reverting unrelated work or deleting files."""
import copy
import bpy

def restore_group(asset,design,group,targets):
    context=asset['context'];wanted=set(context['group']['children'])
    if context.get('concept'):
        from concept_geometry import add_blender_furniture
        # Concept source is a validated procedural specification, not external code.
        add_blender_furniture([context['concept']])
    else:
        with bpy.data.libraries.load(asset['path'],link=False) as (src,dst):dst.objects=src.objects
        loaded=[o for o in dst.objects if o]
        for obj in loaded:bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();found=set()
        for obj in loaded:
            identifier=obj.get('studio_id')
            if identifier not in wanted or obj.type not in ('MESH','CURVE'):continue
            mesh=bpy.data.meshes.new_from_object(obj.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps)
            name=next(p['name'] for p in context['parts'] if p['id']==identifier)
            node=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(node)
            node.matrix_world=obj.matrix_world.copy();node['studio_id']=identifier;node['source_id']=group['id'];found.add(identifier)
        for obj in loaded:bpy.data.objects.remove(obj,do_unlink=True)
        if found!=wanted:raise ValueError('原件子物件不完整，停止回復')
    replaced=set(group['children'])
    for obj in targets:
        for child in list(obj.children):
            if child not in targets:
                matrix=child.matrix_world.copy();child.parent=None;child.matrix_world=matrix
        bpy.data.objects.remove(obj,do_unlink=True)
    design['objects']=[o for o in design['objects'] if o['id'] not in replaced]+copy.deepcopy(context['parts'])
    group.update(children=context['group']['children'],method=context['group']['method'],asset_reference=context['group'].get('asset_reference'),generated_reference=context['group'].get('generated_reference'))
    # Generated restored meshes are now native. Keep the current transform and intent.
    return dict(restored_original=True,group_id=group['id'],object_ids=sorted(wanted),reason='purpose_mismatch',old_files_preserved=True)
