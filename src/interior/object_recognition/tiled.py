"""Full image and overlapping tiles, with lossless mask provenance and cautious routing."""
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


DEFAULTS = dict(imgsz=1536, tile_size=640, overlap=.25, confidence=.05,
                review_confidence=.25, priority_confidence=.85, duplicate_iou=.5,
                agreement_iou=.8, fragment_ios=.9, pyramid_scales=[1.,.5], max_det=300, device=0,
                merge_policy='legacy')


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def settings(overrides=None):
    value = dict(DEFAULTS, **(overrides or {}))
    if set(value) - set(DEFAULTS):
        raise ValueError('Unknown inference option')
    if value['merge_policy'] not in ('legacy', 'structural_v2'):
        raise ValueError('Unknown merge policy')
    for key in ('imgsz', 'tile_size', 'max_det'):
        if not isinstance(value[key], int) or isinstance(value[key], bool) or value[key] < 32:
            raise ValueError('Invalid ' + key)
    for key in ('overlap', 'confidence', 'review_confidence', 'priority_confidence', 'duplicate_iou', 'agreement_iou', 'fragment_ios'):
        if not isinstance(value[key], (int, float)) or not math.isfinite(value[key]) or not 0 < value[key] < 1:
            raise ValueError('Invalid ' + key)
    if not value['confidence'] <= value['review_confidence'] <= value['priority_confidence']:
        raise ValueError('Confidence thresholds must be ordered')
    if value['tile_size'] % 32:
        raise ValueError('Native-pixel tiles must be multiples of model stride 32')
    scales=value['pyramid_scales']
    if not isinstance(scales,list) or not scales or any(not isinstance(s,(int,float)) or isinstance(s,bool) or not math.isfinite(s) or not 0<s<=1 for s in scales) or len(set(scales))!=len(scales):
        raise ValueError('Pyramid scales must be unique numbers in (0,1]')
    return value


def windows(width, height, tile_size, overlap):
    """Cover every source pixel with fixed stride; border tiles are padded by caller."""
    if width < 1 or height < 1 or tile_size < 1 or not 0 <= overlap < 1:
        raise ValueError('Invalid tile geometry')
    def starts(length):
        end = max(0, length - tile_size)
        step = max(1, int(tile_size * (1 - overlap)))
        return list(range(0, math.ceil(end / step) * step + 1, step))
    return [[x, y, min(width, x + tile_size), min(height, y + tile_size)]
            for y in starts(height) for x in starts(width)]


def mask_iou(a, b):
    ab, bb = a['mask_box'], b['mask_box']
    x0, y0, x1, y1 = max(ab[0], bb[0]), max(ab[1], bb[1]), min(ab[2], bb[2]), min(ab[3], bb[3])
    if x1 <= x0 or y1 <= y0:
        return 0.
    am = a['mask'][y0-ab[1]:y1-ab[1], x0-ab[0]:x1-ab[0]]
    bm = b['mask'][y0-bb[1]:y1-bb[1], x0-bb[0]:x1-bb[0]]
    intersection = int(np.count_nonzero(am & bm))
    return intersection / (a['area'] + b['area'] - intersection)


def pyramid_views(size, config):
    """Every tile has a scale-space crop AND an explicit original-image region."""
    width,height=size;views=[dict(id='full',box=[0,0,width,height],scaled_box=[0,0,width,height],
                               scale=1.,scale_xy=[1.,1.],scaled_size=[width,height],family='full')]
    for scale in config['pyramid_scales']:
        sw,sh=max(1,math.ceil(width*scale)),max(1,math.ceil(height*scale));sx,sy=sw/width,sh/height
        for n,b in enumerate(windows(sw,sh,config['tile_size'],config['overlap'])):
            prefix='tile' if scale==1 else f's{scale:g}-tile'
            original=[max(0,math.floor(b[0]/sx)),max(0,math.floor(b[1]/sy)),
                      min(width,math.ceil(b[2]/sx)),min(height,math.ceil(b[3]/sy))]
            views.append(dict(id=f'{prefix}-{n:02d}',box=original,scaled_box=b,scale=scale,
                              scale_xy=[sx,sy],scaled_size=[sw,sh],family='native' if scale==1 else 'context'))
    return views


def reproject(row, scaled_size, original_size):
    """Nearest-neighbour mask projection on the global grid, including odd image sizes."""
    if tuple(scaled_size)==tuple(original_size):return row
    import cv2
    sx,sy=scaled_size[0]/original_size[0],scaled_size[1]/original_size[1]
    canvas=Image.new('L',tuple(scaled_size));canvas.paste(Image.fromarray(row['mask'].astype('uint8')*255),tuple(row['mask_box'][:2]))
    mask=np.asarray(canvas.resize(tuple(original_size),Image.Resampling.NEAREST))>0
    yy,xx=np.nonzero(mask)
    if not len(xx):raise ValueError('Mask vanished in source projection')
    x,y,r,b=int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1
    cropped=mask[y:b,x:r].copy();rings=[]
    contours,hierarchy=cv2.findContours(cropped.astype('uint8'),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is not None:
        for c,h in zip(contours,hierarchy[0]):
            if len(c)>=3:rings.append(dict(hole=bool(h[3]>=0),points=[[int(px)+x,int(py)+y] for px,py in c.reshape(-1,2)]))
    w=row['window'];box=row['box']
    return dict(row,mask=cropped,mask_box=[x,y,r,b],area=int(cropped.sum()),contours=rings,
                window_scaled=w,window=[math.floor(w[0]/sx),math.floor(w[1]/sy),math.ceil(w[2]/sx),math.ceil(w[3]/sy)],
                box=[box[0]/sx,box[1]/sy,box[2]/sx,box[3]/sy])


def extract(result, window, view_id, full_size, padded_size=None):
    """Translate masks and every contour to the original image, without filling holes."""
    if result.masks is None:
        return []
    import cv2
    x, y, right, bottom = window
    rows = []
    for n, local in enumerate(result.masks.data.cpu().numpy() > .5):
        if padded_size is not None:
            if local.shape != (padded_size,padded_size):
                raise ValueError('Native tile mask shape changed')
            local=local[:bottom-y,:right-x]
        if local.shape != (bottom-y, right-x):
            raise ValueError('retina_masks must match source window dimensions')
        yy, xx = np.nonzero(local)
        if not len(xx):
            continue
        lx, ly, rx, by = int(xx.min()), int(yy.min()), int(xx.max())+1, int(yy.max())+1
        mask = local[ly:by, lx:rx].copy()
        contours, hierarchy = cv2.findContours(mask.astype('uint8'), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        rings = []
        if hierarchy is not None:
            for contour, relation in zip(contours, hierarchy[0]):
                points = contour.reshape(-1, 2)
                if len(points) >= 3:
                    rings.append(dict(hole=bool(relation[3] >= 0), points=[[int(px)+x+lx, int(py)+y+ly] for px, py in points]))
        clipped = view_id != 'full' and any((x > 0 and lx <= 2, y > 0 and ly <= 2,
                     right < full_size[0] and rx >= right-x-2, bottom < full_size[1] and by >= bottom-y-2))
        class_id = int(result.boxes.cls[n].item())
        bounds=[float(v)+[x,y,x,y][i] for i,v in enumerate(result.boxes.xyxy[n].tolist())]
        bounds=[max(x,bounds[0]),max(y,bounds[1]),min(right,bounds[2]),min(bottom,bounds[3])]
        rows.append(dict(id=f'{view_id}-{n:03d}', view_id=view_id, window=window,
                         class_id=class_id, class_name=result.names[class_id], confidence=float(result.boxes.conf[n].item()),
                         box=bounds,
                         mask_box=[x+lx,y+ly,x+rx,y+by], mask=mask, area=int(mask.sum()),
                         contours=rings, clipped=clipped))
    return rows


def merge(rows, config):
    if config.get('merge_policy', 'legacy') == 'structural_v2':
        from .structural_merge import merge_structures
        return merge_structures(rows, config)
    return merge_legacy(rows, config)


def merge_legacy(rows, config):
    """Suppress same-class duplicates against an anchor; never union guessed masks."""
    # Preserve whole-object full-view masks. A confident tile fragment must not
    # replace a valid long wall just because its cropped view looks easier.
    remaining = sorted(rows, key=lambda p: (p['clipped'], p['view_id'] != 'full', -p['confidence'], p['id']))
    merged = []
    while remaining:
        anchor, *rest = remaining
        duplicates, remaining, fragments = [], [], []
        for row in rest:
            iou=mask_iou(row,anchor) if row['class_id']==anchor['class_id'] else 0.
            intersection=iou*(row['area']+anchor['area'])/(1+iou)
            fragment=(row['class_id']==anchor['class_id'] and row['clipped'] and not anchor['clipped']
                      and row['view_id']!=anchor['view_id'] and anchor['area']>=row['area']*1.25
                      and intersection/max(row['area'],1)>=config['fragment_ios'])
            if iou>=config['duplicate_iou']:duplicates.append(row)
            elif fragment:fragments.append(row)
            else:remaining.append(row)
        group = [anchor, *duplicates]
        support = [r for r in duplicates if r['view_id'] != anchor['view_id'] and not r['clipped']
                   and r['confidence'] >= config['review_confidence'] and mask_iou(r, anchor) >= config['agreement_iou']]
        priority = anchor['confidence'] >= config['priority_confidence'] and not anchor['clipped'] and bool(support)
        merged.append(dict(anchor, id=f'Y{len(merged)+1:03d}', members=[r['id'] for r in group+fragments],
                           contained_fragments=[r['id'] for r in fragments],
                           views=sorted({r['view_id'] for r in group}),
                           support=[r['id'] for r in support], conflicts=[],
                           route='priority_review' if priority else 'agent_review', accepted=False))
    for i, a in enumerate(merged):
        for b in merged[i+1:]:
            if a['class_id'] != b['class_id'] and mask_iou(a,b) >= .65:
                a['conflicts'].append(b['id']); b['conflicts'].append(a['id'])
                a['route'] = b['route'] = 'agent_review'
    return merged


def public(row):
    return {k:v for k,v in row.items() if k != 'mask'}


def load_masks(folder, filename='candidates'):
    folder=Path(folder)
    rows=json.loads((folder/(filename+'.json')).read_text(encoding='utf-8'))
    with np.load(folder/(filename+'-masks.npz')) as archive:
        for row in rows:
            x,y,r,b=row['mask_box']; count=(r-x)*(b-y)
            row['mask']=np.unpackbits(archive[row['id']])[:count].reshape(b-y,r-x).astype(bool)
            if int(row['mask'].sum()) != row['area']:
                raise ValueError('Mask area mismatch')
    return rows


def render(source, rows, target, colors=None):
    """Draw the actual binary masks rather than an approximated exterior polygon."""
    image=source.convert('RGBA'); overlay=Image.new('RGBA',image.size); d=ImageDraw.Draw(overlay)
    font=ImageFont.load_default(size=14)
    for row in rows:
        color=(colors or {}).get(row['route'], (30,130,220))
        x,y,r,b=row['mask_box']
        alpha=Image.fromarray(row['mask'].astype('uint8')*65)
        patch=Image.new('RGBA',alpha.size,(*color,0)); patch.putalpha(alpha)
        overlay.alpha_composite(patch,(x,y))
        d.rectangle((x,y,r,b),outline=(*color,230),width=1)
        label=f"{row['id']} {row['class_name']} {row['confidence']:.2f}"
        bb=d.textbbox((x,y),label,font=font);d.rectangle(bb,fill=(255,255,255,230));d.text((x,y),label,font=font,fill=(*color,255))
    Image.alpha_composite(image,overlay).convert('RGB').save(target)


def infer(image_path, checkpoint, output, options=None, model=None):
    """Inference receives pixels only. No reference labels or Agent answers are loaded."""
    config=settings(options); image_path=Path(image_path); checkpoint=Path(checkpoint); output=Path(output)
    if output.exists():
        raise FileExistsError('Choose a fresh inference output')
    before=dict(image=sha(image_path), checkpoint=sha(checkpoint))
    output.mkdir(parents=True)
    write(output/'status.json',dict(status='running'))
    write(output/'config.json',dict(options=config,image=str(image_path.resolve()),checkpoint=str(checkpoint.resolve()),sha256=before))
    try:
        if model is None:
            from ultralytics import YOLO
            model=YOLO(str(checkpoint))
        if getattr(model,'task','segment') != 'segment':
            raise ValueError('A segmentation checkpoint is required')
        names=getattr(model,'names',{})
        if names:
            write(output/'taxonomy.json',dict(classes=[dict(id=int(i),name=name) for i,name in (names.items() if isinstance(names,dict) else enumerate(names))]))
        image=Image.open(image_path).convert('RGB')
        views=pyramid_views(image.size,config)
        scaled_images={size:image.resize(size,Image.Resampling.LANCZOS)
                       for size in {tuple(v['scaled_size']) for v in views if v['id']!='full'}}
        (output/'tiles').mkdir()
        layout=image.copy();layout_draw=ImageDraw.Draw(layout)
        raw=[];started=time.perf_counter()
        for view in views:
            tiled_view=view['id']!='full'
            crop=(scaled_images[tuple(view['scaled_size'])] if tiled_view else image).crop(view['scaled_box'])
            if tiled_view:
                # Padding only for sources smaller than a tile; never resize source pixels.
                padded=Image.new('RGB',(config['tile_size'],config['tile_size']),'white')
                padded.paste(crop,(0,0));crop=padded
                crop.save(output/'tiles'/(view['id']+'.png'))
                layout_draw.rectangle(view['box'],outline=(0,110,210),width=2)
                layout_draw.text((view['box'][0]+4,view['box'][1]+4),view['id'],fill=(0,70,180))
            input_size=config['tile_size'] if tiled_view else config['imgsz']
            result=model.predict(source=crop,imgsz=input_size,conf=config['confidence'],
                                 iou=.7,max_det=config['max_det'],retina_masks=True,device=config['device'],verbose=False,save=False)[0]
            rows=extract(result,view['scaled_box'],view['id'],view['scaled_size'],config['tile_size'] if tiled_view else None)
            rows=[dict(reproject(r,view['scaled_size'],image.size),scale=view['scale'],scale_xy=view['scale_xy'],family=view['family']) for r in rows]
            raw+=rows
            view.update(candidates=len(rows),engine_ms=result.speed,input_imgsz=input_size,
                        source_crop_size=[view['scaled_box'][2]-view['scaled_box'][0],view['scaled_box'][3]-view['scaled_box'][1]],
                        tile_source_resized=view['scale']!=1 if tiled_view else None)
        layout.save(output/'tile-layout.png')
        elapsed=time.perf_counter()-started
        candidates=merge([r for r in raw if r['confidence']>=config['review_confidence']],config)
        for filename,rows in [('raw',raw),('candidates',candidates)]:
            write(output/(filename+'.json'),[public(p) for p in rows])
            np.savez_compressed(output/(filename+'-masks.npz'),**{p['id']:np.packbits(p['mask']) for p in rows})
        write(output/'views.json',views)
        write(output/'layers.json',dict(status='unreviewed_candidates',accepted_count=0,coordinate_system='source_image_pixels',
              layers={c:[public(p) for p in candidates if p['class_name']==c] for c in sorted({p['class_name'] for p in candidates})}))
        render(image,candidates,output/'candidates.png',{'priority_review':(30,150,80),'agent_review':(210,110,20)})
        render(image,[p for p in candidates if p['route']=='priority_review'],output/'priority.png')
        # Every candidate gets a readable local review card. Original context remains available.
        cards=[]
        for row in candidates:
            x,y,r,b=row['mask_box'];box=[max(0,x-70),max(0,y-70),min(image.width,r+70),min(image.height,b+70)]
            local=dict(row,mask_box=[x-box[0],y-box[1],r-box[0],b-box[1]])
            path=output/(row['id']+'.png');render(image.crop(box),[local],path)
            cards.append(dict(id=row['id'],image=path.name,source_box=box))
        write(output/'cards.json',cards)
        after=dict(image=sha(image_path),checkpoint=sha(checkpoint))
        if before != after:
            raise ValueError('Inference input changed during run')
        summary=dict(status='completed',views=len(views),tiles=len(views)-1,raw_candidates=len(raw),
                     native_tiles=sum(v['family']=='native' for v in views),context_tiles=sum(v['family']=='context' for v in views),
                     candidates=len(candidates),priority_review=sum(p['route']=='priority_review' for p in candidates),
                     accepted=0,elapsed_seconds=elapsed,source_unchanged=True,precision=None,
                     precision_target=.99,precision_target_verified=False,reference_used=False,
                     note='All model outputs require Agent source review; confidence and view agreement do not prove correctness.')
        write(output/'status.json',summary)
        return summary
    except Exception as exc:
        write(output/'status.json',dict(status='failed',error=str(exc)))
        raise
