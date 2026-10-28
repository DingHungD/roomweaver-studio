"""Compare frozen model outputs under a versioned class migration and one reference."""
import copy
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .tiled import load_masks,merge,settings,public,write,sha


FURNITURE_SOURCES={'cabinet','refrigerator','water_heater','waste_bin','pet_pad','dishwasher'}


def migrate_predictions(rows,classes):
    """Map semantic class names only; retain masks and obsolete outputs, never use labels."""
    ids={c['name']:c['id'] for c in classes}
    unknown=sorted({r['class_name'] for r in rows if r['class_name'] not in ids and r['class_name'] not in FURNITURE_SOURCES})
    extras={name:len(ids)+i for i,name in enumerate(unknown)}
    result=[]
    for row in rows:
        original=row['class_name'];name='furniture' if original in FURNITURE_SOURCES else original
        if name in ids:cid=ids[name]
        else:cid=extras[original];name='unmapped_legacy_'+original
        result.append(dict(row,class_id=cid,class_name=name,legacy_class_id=row['class_id'],legacy_class_name=original))
    return result


def reference_for_training_ids(reference,classes):
    """Canonical IDs and model output IDs are distinct in the revised annotation package."""
    ref=copy.deepcopy(reference);names={c['id']:c['name'] for c in classes}
    for obj in ref['objects']:
        if obj['exclusion_reason']:continue
        cid=obj['training_class_id']
        if names.get(cid)!=obj['class_name']:raise ValueError('Reference/class mapping mismatch')
        obj['canonical_class_id']=obj['class_id'];obj['class_id']=cid
    return ref


def model_groups(raw,config):
    eligible=[r for r in raw if r['confidence']>=config['review_confidence']]
    return dict(full=[r for r in eligible if r['view_id']=='full'],
       full_native=merge([r for r in eligible if r['family'] in ('full','native')],config),
       full_plus_tiles=merge(eligible,config),
       half_tiles=merge([r for r in eligible if r['family']=='context'],config))


def compare(bundles,annotation_path,classes_path,request_path,output):
    """Class migration happens before identical mask merging; ground truth only scores."""
    from .evaluation import reference_masks,score
    output=Path(output)
    if output.exists():raise FileExistsError('Preserve existing comparison')
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
    classes=read(classes_path)['classes'];reference=reference_for_training_ids(read(annotation_path),classes)
    request=read(request_path)
    if reference['source']['original_sha256']!=request['site']['native_dwg']['source_sha256']:raise ValueError('Drawing hash differs')
    inputs={str(Path(p).resolve()):sha(p) for p in [annotation_path,classes_path,request_path]}
    configs={name:read(Path(folder)/'config.json') for name,folder in bundles.items()}
    option_values=list(configs.values());expected=option_values[0]['options'];image_hash=option_values[0]['sha256']['image']
    if any(c['options']!=expected or c['sha256']['image']!=image_hash for c in configs.values()):raise ValueError('Comparison views/settings differ')
    for c in configs.values():
        if sha(c['image'])!=image_hash or sha(c['checkpoint'])!=c['sha256']['checkpoint']:raise ValueError('Model/source changed')
    source=Image.open(option_values[0]['image']);gt=reference_masks(reference,request['site']['source_view'],source.size)
    if len(gt)!=71:raise ValueError('The selected revision must contain 71 active references')
    output.mkdir(parents=True)
    write(output/'reference-pixel-masks.json',[public(r) for r in gt])
    np.savez_compressed(output/'reference-pixel-masks.npz',**{r['id']:np.packbits(r['mask']) for r in gt})
    summary=dict(test_type='same_DWG_fixed_new_taxonomy_development_comparison_not_independent',reference_objects=len(gt),
        training_classes=len(classes),annotation_sha256=sha(annotation_path),training_classes_sha256=sha(classes_path),
        source_image_sha256=image_hash,mask_iou=.5,strict_mask_iou=.9,confidence=.25,models={},
        migration=dict(furniture_sources=sorted(FURNITURE_SOURCES),mask_coordinates_or_pixels_modified=False,
            merges='same generic class mask duplicate/fragment policy after name mapping',
            obsolete_classes='retained as unmatched false positives, not silently discarded',
            wall_instance_geometry='old predictions are not unioned to imitate reference connected walls'),
        reference_not_provided_to_inference=True,agent_corrections_counted_as_model_success=False,
        thresholds_selected_from_test=False,model_deployed=False,precision_target_99_verified=False)
    for name,folder in bundles.items():
        config=configs[name];raw=load_masks(folder,'raw')
        if name=='new_v3':
            if any(r['class_id']>=len(classes) or classes[r['class_id']]['name']!=r['class_name'] for r in raw):raise ValueError('New checkpoint taxonomy mismatch')
        mapped=migrate_predictions(raw,classes);groups=model_groups(mapped,settings(config['options']))
        dest=output/name;dest.mkdir()
        write(dest/'mapped-raw.json',[public(r) for r in mapped])
        rows=groups['full_plus_tiles']
        write(dest/'merged.json',[public(r) for r in rows]);np.savez_compressed(dest/'merged-masks.npz',**{r['id']:np.packbits(r['mask']) for r in rows})
        record=dict(model_sha256=config['sha256']['checkpoint'],raw_predictions_sha256=sha(Path(folder)/'raw.json'),
            raw_masks_sha256=sha(Path(folder)/'raw-masks.npz'),
            bundle=str(Path(folder).resolve()),groups={},unmapped_merged_predictions=sum(r['class_name'].startswith('unmapped_legacy_') for r in rows))
        for group,items in groups.items():
            scored=score(gt,items);write(dest/(group+'.json'),scored)
            record['groups'][group]={k:v for k,v in scored.items() if k not in ('matches','missed','unmatched','per_class')}
            record['groups'][group]['strict_mask_iou_090']=score(gt,items,.9)['true_positive']
        summary['models'][name]=record
    if 'new_v3' in bundles:
        new=read(output/'new_v3/full_plus_tiles.json');new_ids={r['object_id'] for r in new['matches']}
        for name in bundles:
            if name=='new_v3':continue
            old=read(output/name/'full_plus_tiles.json');old_ids={r['object_id'] for r in old['matches']}
            summary['models'][name]['new_model_recovered']=[dict(id=r['id'],name=r['name'],class_name=r['class_name']) for r in gt if r['id'] in new_ids-old_ids]
            summary['models'][name]['new_model_regressions']=[dict(id=r['id'],name=r['name'],class_name=r['class_name']) for r in gt if r['id'] in old_ids-new_ids]
    if not all(sha(p)==h for p,h in inputs.items()):raise ValueError('Reference inputs changed during scoring')
    write(output/'summary.json',summary);return summary
