"""Prediction-only admission guard: proposals cannot silently discard or relabel objects."""
import numpy as np

from .tiled import mask_iou


POLICY=dict(version='conservative-v1',same_class_iou=.50,duplicate_containment=.80,
            thin_projection_containment=.90,thin_classes=['shower_screen','track_light','pendant_light','light_symbol','drying_rod','shower_head'])


def overlap(a,b):
    iou=mask_iou(a,b);intersection=iou*(a['area']+b['area'])/(1+iou)
    return iou,intersection/max(1,min(a['area'],b['area']))


def guard(original,proposed,decisions):
    """Apply bounded geometry changes; retain disputed raw outputs with explicit pending."""
    final={r['id']:r for r in proposed};audit={d['id']:d for d in decisions if d.get('id')};pending=[];checks=[]
    # Class/geometry disputes are restored before validating duplicate destinations.
    for raw in original:
        candidate=final.get(raw['id'])
        if candidate is None:continue
        iou,ios=overlap(raw,candidate)
        same=raw['class_id']==candidate['class_id']
        thin_shrink=(same and raw['class_name'] in POLICY['thin_classes'] and candidate['area']<=raw['area'] and ios>=POLICY['thin_projection_containment'])
        if same and (iou>=POLICY['same_class_iou'] or thin_shrink):continue
        reason='Agent建議更改模型類別，需再核對原圖及用途依據' if not same else '原生來源建議與既有整件輪廓差異過大，保留模型候選待複核'
        final[raw['id']]=dict(raw,accepted=False,route='agent_review',reason=reason)
        item=dict(id=raw['id'],issue='class_conflict' if not same else 'outline_conflict',reason=reason,
            proposed_class=candidate['class_name'],model_class=raw['class_name'],proposal_iou=iou,source_ids=candidate.get('source_ids',[]))
        pending.append(item);checks.append(item)
    removed={r['id']:r for r in original if r['id'] not in final}
    for key,raw in removed.items():
        d=audit.get(key,{});other=final.get(d.get('duplicate_of'))
        iou,ios=overlap(raw,other) if other else (0.,0.)
        duplicate=other is not None and raw['class_id']==other['class_id'] and (iou>=POLICY['same_class_iou'] or ios>=POLICY['duplicate_containment'])
        if duplicate:checks.append(dict(id=key,action='verified_duplicate',duplicate_of=other['id'],iou=iou,containment=ios))
        else:
            reason='移除建議缺少與保留代表的一致重疊證據，保留原候選待複核'
            final[key]=dict(raw,accepted=False,route='agent_review',reason=reason)
            item=dict(id=key,issue='unverified_removal',reason=reason,source_ids=d.get('source_ids',[]),proposed_duplicate_of=d.get('duplicate_of'))
            pending.append(item);checks.append(item)
    return list(final.values()),pending,checks
