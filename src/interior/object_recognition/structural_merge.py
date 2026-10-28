"""Prediction-only structural stitching; source masks and legacy policy stay intact."""
import numpy as np

from .tiled import mask_iou, merge_legacy


POLICY = dict(version='structural_v2', revision=2, classes=['wall', 'beam', 'track_light'],
              containment=.60, axis_overlap=.60, axis_aspect=5., normal_slack=2.,
              minimum_extension_views=2, line_vote=.50)


def axis(row):
    x,y,r,b=row['mask_box'];w,h=r-x,b-y
    if max(w,h)<min(w,h)*POLICY['axis_aspect']:return None
    return 0 if w>=h else 1


def same_structure(a,b):
    """Require real pixel overlap for walls, and collinearity for thin line symbols."""
    if a['class_id']!=b['class_id']:return False
    iou=mask_iou(a,b)
    intersection=iou*(a['area']+b['area'])/(1+iou)
    ios=intersection/max(1,min(a['area'],b['area']))
    if a['class_name']=='wall':return ios>=POLICY['containment']
    aa,ba=axis(a),axis(b)
    if aa is not None and ba is not None:
        if aa!=ba:return False
        ab,bb=a['mask_box'],b['mask_box'];normal=1-aa
        lengths=[ab[aa+2]-ab[aa],bb[aa+2]-bb[aa]]
        overlap=max(0,min(ab[aa+2],bb[aa+2])-max(ab[aa],bb[aa]))/min(lengths)
        widths=[ab[normal+2]-ab[normal],bb[normal+2]-bb[normal]]
        offset=abs((ab[normal]+ab[normal+2]-bb[normal]-bb[normal+2])/2)
        aligned=overlap>=POLICY['axis_overlap'] and offset<=max(widths)*.5+POLICY['normal_slack']
        if a['class_name']=='track_light':return aligned
        return aligned and ios>=POLICY['containment']
    return ios>=POLICY['containment']


def put(canvas,row,bounds):
    x,y,r,b=row['mask_box'];canvas[y-bounds[1]:b-bounds[1],x-bounds[0]:r-bounds[0]]|=row['mask']


def fuse(group,raw):
    """Keep a complete anchor, add independently supported pixels, vote skinny lines."""
    ordered=sorted(group,key=lambda r:(r['clipped'],r['view_id']!='full',-r['area'],-r['confidence'],r['id']))
    anchor=ordered[0]
    members=sorted({m for r in group for m in r['members']})
    evidence=[raw[m] for m in members]
    boxes=[r['mask_box'] for r in evidence]
    bounds=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
    shape=(bounds[3]-bounds[1],bounds[2]-bounds[0])
    seed=np.zeros(shape,bool);put(seed,anchor,bounds)
    # Two overlapping whole-wall predictions may each omit a different branch.
    if anchor['class_name']=='wall':
        for r in group:
            if not r['clipped'] and r['view_id']=='full':put(seed,r,bounds)
    views={}
    coverage={}
    direction=axis(anchor)
    for r in evidence:
        view=r['view_id'];views.setdefault(view,np.zeros(shape,bool));put(views[view],r,bounds)
        coverage.setdefault(view,np.zeros(shape,bool))
        if direction is not None:
            start=r['mask_box'][direction]-bounds[direction];end=r['mask_box'][direction+2]-bounds[direction]
            if direction==0:coverage[view][:,start:end]=True
            else:coverage[view][start:end,:]=True
    support=sum((m.astype('uint16') for m in views.values()),np.zeros(shape,'uint16'))
    fused=seed|(support>=POLICY['minimum_extension_views'])
    if anchor['class_name']=='track_light' and direction is not None:
        observed=sum((m.astype('uint16') for m in coverage.values()),np.zeros(shape,'uint16'))
        consensus=(support>=POLICY['minimum_extension_views'])&(support>=observed*POLICY['line_vote'])
        # Do not erase a unique observation simply because no other crop covers it.
        fused=consensus|(seed&(observed<2))
        if fused.sum()<seed.sum()*.4:fused=seed
    # Only components touching the anchor can extend it; never bridge blank gaps.
    import cv2
    n,labels=cv2.connectedComponents(fused.astype('uint8'),connectivity=8)
    touched=np.unique(labels[seed&fused]);touched=touched[touched!=0]
    fused=np.isin(labels,touched)
    if not fused.any():fused=seed
    yy,xx=np.nonzero(fused);x,y,r,b=int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1
    mask=fused[y:b,x:r].copy();global_box=[bounds[0]+x,bounds[1]+y,bounds[0]+r,bounds[1]+b]
    contours,hierarchy=cv2.findContours(mask.astype('uint8'),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    rings=[]
    if hierarchy is not None:
        for c,h in zip(contours,hierarchy[0]):
            if len(c)>=3:rings.append(dict(hole=bool(h[3]>=0),points=[[int(px)+global_box[0],int(py)+global_box[1]] for px,py in c.reshape(-1,2)]))
    return dict(anchor,mask=mask,mask_box=global_box,box=global_box.copy(),area=int(mask.sum()),contours=rings,
        members=members,views=sorted(views),contained_fragments=sorted({m for g in group for m in g['contained_fragments']}),
        support=[],route='agent_review',accepted=False,conflicts=[],
        merge_policy=POLICY['version'],anchor_raw_id=next(r['id'] for r in evidence if r['view_id']==anchor['view_id'] and r['mask_box']==anchor['mask_box']),
        fusion=dict(legacy_candidates=[r['id'] for r in group],source_pixels_only=True,
                    added_pixels=int((fused&~seed).sum()),removed_pixels=int((seed&~fused).sum()),independent_views=len(views)))


def merge_structures(rows,config):
    """Strong-overlap groups, no neighbour-only merging, and auditable mask provenance."""
    base=merge_legacy(rows,config);raw={r['id']:r for r in rows}
    pending=[r for r in base if r['class_name'] in POLICY['classes']]
    output=[dict(r,conflicts=[]) for r in base if r['class_name'] not in POLICY['classes']]
    while pending:
        group=[pending.pop(0)]
        # Membership uses original predictions, never the progressively enlarged union.
        changed=True
        while changed:
            changed=False;rest=[]
            for r in pending:
                whole=[a for a in group if a['view_id']=='full' and not a['clipped']]
                # A short fragment cannot bridge two distinct whole-wall predictions.
                anchors=whole if whole and r['class_name']=='wall' else group
                if any(same_structure(r,a) for a in anchors):group.append(r);changed=True
                else:rest.append(r)
            pending=rest
        output.append(fuse(group,raw))
    output.sort(key=lambda r:(r['clipped'],r['view_id']!='full',-r['confidence'],r['id']))
    for n,r in enumerate(output,1):r['id']=f'Y{n:03d}'
    for i,a in enumerate(output):
        for b in output[i+1:]:
            if a['class_id']!=b['class_id'] and mask_iou(a,b)>=.65:
                a['conflicts'].append(b['id']);b['conflicts'].append(a['id'])
                a['route']=b['route']='agent_review'
    return output
