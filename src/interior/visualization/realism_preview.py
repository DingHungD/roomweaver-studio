"""Export the actual trial geometry as a separate, non-editable editor snapshot."""
import copy
import json
from uuid import uuid5,NAMESPACE_URL
import bpy


def export_snapshot(design, output):
    visible=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render and not o.get('studio_illustrative_exterior')]
    snapshot=copy.deepcopy(design);snapshot['concept_furniture']=[];snapshot['completion_details']=False;snapshot['completion_fronts']=[]
    snapshot['installation_replacements']=[];snapshot['door_controls']=[];snapshot['opening_details']=False; snapshot['shelf_refinements']=[];snapshot['ceiling_infill']=[];snapshot['illustrative_exteriors']=[]
    owners={k:g['id'] for g in design['groups'] for k in g['children']}
    groups={g['id']:dict(copy.deepcopy(g),children=[],translation=[0,0,0],rotation=0,rotation_pivot=[0,0,0],deleted=False) for g in design['groups'] if not g['deleted']}
    assignments={a['id']:a for a in design['objects']};items=[];backups=[]
    bpy.ops.object.select_all(action='DESELECT')
    try:
        for obj in sorted(visible,key=lambda o:o.name):
            key=obj.get('studio_id') or uuid5(NAMESPACE_URL,'realism-preview:'+obj.name).hex
            obj['studio_id']=key;source=obj.get('studio_refined_from') or key
            gid=owners.get(source)
            if not gid or gid not in groups:
                gid='preview-'+(obj.get('studio_opening_group') or key)
                if gid not in groups:groups[gid]=dict(id=gid,name=obj.get('assembly_id') or obj.name,children=[],translation=[0,0,0],rotation=0,deleted=False,method='single')
            groups[gid]['children'].append(key)
            item=copy.deepcopy(assignments.get(source,dict(id=key,name=obj.name,room_id=None,material={})))
            item['id']=key;item['material']={};items.append(item)
            original=list(obj.data.materials)
            for i,mat in enumerate(original):
                if mat:
                    preview=bpy.data.materials.get(mat.get('studio_preview_material',''))
                    if preview:obj.data.materials[i]=preview
            backups.append((obj,original));obj.hide_set(False);obj.select_set(True)
        bpy.ops.export_scene.gltf(filepath=str(output/'refined-preview.glb'),export_format='GLB',use_selection=True,export_extras=True,export_apply=True,export_cameras=False,export_lights=False)
    finally:
        for obj,materials in backups:
            for i,mat in enumerate(materials):obj.data.materials[i]=mat
    snapshot['groups']=[g for g in groups.values() if g['children']];snapshot['objects']=items
    # All transforms/material edits are already present in this GLB. Reapplying the
    # revision would double translations and regenerate concept furniture.
    (output/'preview-scene.json').write_text(json.dumps(snapshot,ensure_ascii=False),encoding='utf-8')
    return dict(file='refined-preview.glb',scene_file='preview-scene.json',readonly=True,mesh_count=len(visible))
