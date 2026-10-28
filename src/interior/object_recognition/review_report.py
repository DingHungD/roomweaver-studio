"""Frozen Agent-layer comparison and editable class-layer SVG export."""
import base64
import colorsys
import json
from pathlib import Path
from xml.sax.saxutils import escape

from .tiled import sha,write,load_masks


def export_svg(image_path,rows,output):
    from PIL import Image
    source=Path(image_path);size=Image.open(source).size
    classes=sorted({p['class_name'] for p in rows});parts=[f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" width="{size[0]}" height="{size[1]}" viewBox="0 0 {size[0]} {size[1]}">']
    parts.append(f'<image width="{size[0]}" height="{size[1]}" href="data:image/png;base64,{base64.b64encode(source.read_bytes()).decode()}"/>')
    for index,cls in enumerate(classes):
        color='#%02x%02x%02x'%tuple(int(c*255) for c in colorsys.hsv_to_rgb(index/max(1,len(classes)),.75,.85))
        parts.append(f'<g id="class-{escape(cls)}" data-class="{escape(cls)}" fill="{color}" fill-opacity=".22" stroke="{color}" stroke-width="1">')
        for p in rows:
            if p['class_name']!=cls:continue
            rings=[]
            for contour in p.get('contours',[]):
                pts=contour['points']
                if len(pts)>=3:rings.append('M '+' L '.join(f'{x:.3f},{y:.3f}' for x,y in pts)+' Z')
            title=escape(p['id']+' '+p.get('name',cls)+' '+p.get('reason',''))
            parts.append(f'<path id="object-{escape(p["id"])}" d="{" ".join(rings)}" fill-rule="evenodd"><title>{title}</title></path>')
        parts.append('</g>')
    parts.append('</svg>');Path(output).write_text('\n'.join(parts),encoding='utf-8')


def freeze_review(folder,filename='corrected',layers='layers.json',verification='layer-verification.json'):
    """Call before reference labels are loaded. Bind the exact reviewed outputs."""
    folder=Path(folder);files=[folder/(filename+'.json'),folder/(filename+'-masks.npz'),folder/layers,folder/verification]
    frozen=dict(status='frozen_for_evaluation',files={f.name:sha(f) for f in files},
                agent_output=filename,reference_labels_provided_to_agent=False)
    write(folder/'frozen-result.json',frozen);return frozen


def compare_review(review,bundle,reference_path,request_path,output,*,classes_path=None):
    """Evaluation alone reads ground truth, strictly after the review was frozen."""
    from PIL import Image
    from .evaluation import score,reference_masks
    review=Path(review);bundle=Path(bundle);output=Path(output)
    if output.exists():raise FileExistsError('Preserve prior before/after comparison')
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
    frozen=read(review/'frozen-result.json')
    if not all(sha(review/f)==h for f,h in frozen['files'].items()):raise ValueError('Frozen Agent result changed')
    config=read(bundle/'config.json');source=Path(config['image']);request=read(request_path)
    reference=read(reference_path)
    if classes_path is not None:
        from .taxonomy_compare import reference_for_training_ids
        reference=reference_for_training_ids(reference,read(classes_path)['classes'])
    if request['site']['native_dwg']['source_sha256']!=reference['source']['original_sha256']:raise ValueError('Reference does not match CAD source')
    gt=reference_masks(reference,request['site']['source_view'],Image.open(source).size)
    before=load_masks(bundle);after=load_masks(review,frozen['agent_output'])
    output.mkdir(parents=True)
    result=dict(test_type='same_DWG_Agent_assisted_development_comparison_not_independent',reference_objects=len(gt),
       model_sha256=config['sha256']['checkpoint'],reference_sha256=sha(reference_path),source_image_sha256=sha(source),
       reference_not_provided_to_agent=True,frozen_review_sha256=sha(review/'frozen-result.json'),
       confidence_policy='YOLO before: confidence>=0.25. Agent after: all source-validated kept/replaced/added objects; no numeric confidence threshold on native additions.',
       scores={})
    if classes_path is not None:
        result['training_classes_sha256']=sha(classes_path)
        result['reference_class_ids']='explicit training_class_id mapping; canonical IDs preserved in input'
    for name,rows in [('before_yolo',before),('after_agent',after)]:
        s=score(gt,rows);write(output/(name+'.json'),s)
        result['scores'][name]={k:v for k,v in s.items() if k not in ('matches','missed','unmatched','per_class')}
        result['scores'][name]['strict_mask_iou_090']=score(gt,rows,.9)['true_positive']
    old=read(output/'before_yolo.json');new=read(output/'after_agent.json')
    old_ids={m['object_id'] for m in old['matches']};new_ids={m['object_id'] for m in new['matches']}
    result['recovered']=[dict(id=p['id'],name=p['name'],class_name=p['class_name']) for p in gt if p['id'] in new_ids-old_ids]
    result['regressions']=[dict(id=p['id'],name=p['name'],class_name=p['class_name']) for p in gt if p['id'] in old_ids-new_ids]
    result['model_raw_performance_not_changed']=True
    result['precision_target_independently_verified']=False
    write(output/'summary.json',result)
    export_svg(source,after,output/'reviewed-layers.svg')
    # Do not allow evaluation to mutate the frozen correction evidence.
    if not all(sha(review/f)==h for f,h in frozen['files'].items()):raise ValueError('Evaluation altered reviewed evidence')
    return result
