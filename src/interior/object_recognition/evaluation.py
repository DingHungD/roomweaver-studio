"""Post-inference reference comparison, kept outside the pixel-only inference path."""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.optimize import linear_sum_assignment

from .tiled import load_masks, mask_iou, write, sha,merge,settings


def reference_masks(reference, view, size):
    rows=[]
    for obj in reference['objects']:
        if obj['exclusion_reason']:continue
        polygons=[[[view['pad']+(p[0]-view['bounds'][0])*view['scale'],
                    view['pad']+(view['bounds'][3]-p[1])*view['scale']] for p in poly] for poly in obj['geometry_m']]
        points=[p for poly in polygons for p in poly]
        x=max(0,math.floor(min(p[0] for p in points))); y=max(0,math.floor(min(p[1] for p in points)))
        r=min(size[0],math.ceil(max(p[0] for p in points))+1); b=min(size[1],math.ceil(max(p[1] for p in points))+1)
        image=Image.new('1',(r-x,b-y));draw=ImageDraw.Draw(image)
        for poly in polygons:draw.polygon([(round(px-x),round(py-y)) for px,py in poly],fill=1)
        mask=np.asarray(image).astype(bool)
        rows.append(dict(id=obj['id'],name=obj['name'],class_id=obj['class_id'],class_name=obj['class_name'],
                         quality=obj['contour_quality'],mask_box=[x,y,r,b],mask=mask,area=int(mask.sum())))
    return rows


def score(reference, predictions, threshold=.5):
    if reference and predictions:
        matrix=np.array([[mask_iou(a,b) if a['class_id']==b['class_id'] else 0 for b in predictions] for a in reference])
        eligible=matrix>=threshold
        rows,cols=linear_sum_assignment(np.where(eligible,1000+matrix,0),maximize=True)
        pairs=[(int(i),int(j),float(matrix[i,j])) for i,j in zip(rows,cols) if eligible[i,j]]
    else:pairs=[]
    gi={i for i,j,s in pairs};pj={j for i,j,s in pairs}
    classes=sorted({r['class_id'] for r in reference}|{p['class_id'] for p in predictions})
    per_class=[]
    for c in classes:
        ng=sum(r['class_id']==c for r in reference);npred=sum(p['class_id']==c for p in predictions)
        tp=sum(reference[i]['class_id']==c for i,j,s in pairs)
        name=next(r['class_name'] for r in reference+predictions if r['class_id']==c)
        per_class.append(dict(class_id=c,class_name=name,reference=ng,predictions=npred,true_positive=tp,
                              false_positive=npred-tp,false_negative=ng-tp,
                              precision=tp/npred if npred else None,recall=tp/ng if ng else None))
    return dict(reference=len(reference),predictions=len(predictions),true_positive=len(pairs),per_class=per_class,
        false_positive=len(predictions)-len(pairs),false_negative=len(reference)-len(pairs),
        precision=len(pairs)/len(predictions) if predictions else None,
        recall=len(pairs)/len(reference) if reference else None,mask_iou_threshold=threshold,
        matches=[dict(object_id=reference[i]['id'],prediction_id=predictions[j]['id'],mask_iou=s) for i,j,s in pairs],
        missed=[dict(id=r['id'],name=r['name'],class_name=r['class_name'],mask_box=r['mask_box']) for i,r in enumerate(reference) if i not in gi],
        unmatched=[dict(id=p['id'],class_name=p['class_name'],confidence=p['confidence'],mask_box=p['mask_box']) for j,p in enumerate(predictions) if j not in pj])


def evaluate(bundle, annotation_path, request_path, output):
    bundle=Path(bundle);output=Path(output)
    if output.exists():raise FileExistsError('Preserve previous evaluation')
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
    request=read(request_path);reference=read(annotation_path);config=read(bundle/'config.json')
    if request['site']['native_dwg']['source_sha256']!=reference['source']['original_sha256']:
        raise ValueError('Reference and drawing differ')
    if sha(Path(config['image']))!=config['sha256']['image']:raise ValueError('Image changed')
    image=Image.open(config['image']);gt=reference_masks(reference,request['site']['source_view'],image.size)
    raw=load_masks(bundle,'raw');combined=load_masks(bundle);threshold=config['options']['review_confidence']
    groups=dict(full=[p for p in raw if p['view_id']=='full' and p['confidence']>=threshold],
                full_plus_tiles=combined,priority_review=[p for p in combined if p['route']=='priority_review'])
    if any(p.get('family')=='context' for p in raw):
        options=settings(config['options'])
        groups['full_native']=merge([p for p in raw if p['confidence']>=threshold and p.get('family') in ('full','native')],options)
        groups['half_tiles']=merge([p for p in raw if p['confidence']>=threshold and p.get('family')=='context'],options)
    output.mkdir(parents=True)
    summary=dict(test_type='same_DWG_development_comparison_not_independent',reference_objects=len(gt),
         annotation_sha256=sha(annotation_path),request_sha256=sha(request_path),model_sha256=config['sha256']['checkpoint'],
         thresholds_chosen_from_test=False,precision_target_verified=False,agent_changes_counted_as_model_success=False,groups={})
    for name,rows in groups.items():
        result=score(gt,rows);write(output/(name+'.json'),result)
        summary['groups'][name]={k:v for k,v in result.items() if k not in ('matches','missed','unmatched','per_class')}
        summary['groups'][name]['strict_mask_iou_090']=score(gt,rows,.9)['true_positive']
    # Which missed objects are newly recovered by tiles? Include regressions too.
    baseline=score(gt,groups['full']);combined_score=score(gt,groups['full_plus_tiles'])
    base_ids={m['object_id'] for m in baseline['matches']};new_ids={m['object_id'] for m in combined_score['matches']}
    summary['newly_recovered']=[dict(id=r['id'],name=r['name'],class_name=r['class_name']) for r in gt if r['id'] in new_ids-base_ids]
    summary['regressions']=[dict(id=r['id'],name=r['name'],class_name=r['class_name']) for r in gt if r['id'] in base_ids-new_ids]
    write(output/'summary.json',summary)
    return summary
