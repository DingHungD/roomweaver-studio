"""Source-bound segmentation crops and exact quarter-turn augmentation."""
import json
from pathlib import Path

from PIL import Image,ImageDraw
from shapely.geometry import Polygon,box
from shapely.affinity import scale as scale_shape,translate

from .tiled import pyramid_views,settings,write,sha


def rotate_points(points,width,height,turns):
    turns%=4
    if turns==0:return points
    if turns==1:return [[height-y,x] for x,y in points]
    if turns==2:return [[width-x,height-y] for x,y in points]
    return [[y,width-x] for x,y in points]


def polygons(shape):
    if shape.is_empty:return []
    if shape.geom_type=='Polygon':return [shape]
    return [p for g in getattr(shape,'geoms',[]) for p in polygons(g)]


def build_dataset(image_path,label_path,label_map_path,classes_path,output,source_group):
    """All variants stay in one source group; none are independent validation images."""
    output=Path(output)
    if output.exists():raise FileExistsError('Preserve previous augmented dataset')
    import yaml
    inputs=[Path(p) for p in (image_path,label_path,label_map_path,classes_path)]
    hashes={str(p.resolve()):sha(p) for p in inputs}
    image=Image.open(image_path).convert('RGB');width,height=image.size
    mapping=json.loads(Path(label_map_path).read_text(encoding='utf-8'));original=[]
    for line,meta in zip(Path(label_path).read_text(encoding='utf-8').splitlines(),mapping,strict=True):
        values=line.split();coords=list(map(float,values[1:]));pts=[[coords[i]*width,coords[i+1]*height] for i in range(0,len(coords),2)]
        shape=Polygon(pts)
        if not shape.is_valid or shape.is_empty:raise ValueError('Invalid source polygon '+meta['object_id'])
        original.append(dict(meta,class_id=int(values[0]),shape=shape))
    output.mkdir(parents=True);(output/'images/train').mkdir(parents=True);(output/'labels/train').mkdir(parents=True)
    records=[];variants=pyramid_views(image.size,settings());transposes=[None,Image.Transpose.ROTATE_270,Image.Transpose.ROTATE_180,Image.Transpose.ROTATE_90]
    for view in variants:
        sx,sy=view['scale_xy'];x,y,r,b=view['scaled_box']
        scaled=image.resize(tuple(view['scaled_size']),Image.Resampling.LANCZOS);crop=scaled.crop((x,y,r,b))
        if view['id']!='full':
            padded=Image.new('RGB',(640,640),'white');padded.paste(crop,(0,0));crop=padded
        labels=[]
        region=box(x,y,r,b)
        for obj in original:
            s=scale_shape(obj['shape'],xfact=sx,yfact=sy,origin=(0,0)).intersection(region)
            for component,p in enumerate(polygons(s)):
                if p.area<.05:continue
                if p.interiors:raise ValueError('YOLO polygon export cannot silently fill a mask hole')
                p=translate(p,xoff=-x,yoff=-y)
                labels.append(dict(source_object_id=obj['object_id'],class_id=obj['class_id'],quality=obj['contour_quality'],
                                   component=component,partial=p.area+1e-6<obj['shape'].area*sx*sy,points=list(p.exterior.coords)[:-1]))
        for turns,transpose in enumerate(transposes):
            sample=crop if transpose is None else crop.transpose(transpose);name=f"{view['id']}-r{turns*90}"
            lines=[];line_map=[]
            for label in labels:
                pts=rotate_points(label['points'],crop.width,crop.height,turns)
                # Format accepts visible fragments; drop only genuinely empty raster targets.
                raster=Image.new('1',sample.size);ImageDraw.Draw(raster).polygon([tuple(p) for p in pts],fill=1)
                if raster.getbbox() is None:continue
                normalized=[[min(1.,max(0.,px/sample.width)),min(1.,max(0.,py/sample.height))] for px,py in pts]
                lines.append(str(label['class_id'])+' '+' '.join(f'{v:.9f}' for p in normalized for v in p))
                line_map.append({k:v for k,v in label.items() if k!='points'})
            sample.save(output/'images/train'/(name+'.png'))
            (output/'labels/train'/(name+'.txt')).write_text('\n'.join(lines)+ ('\n' if lines else ''),encoding='utf-8')
            records.append(dict(id=name,view=view,rotation_clockwise=turns*90,instances=len(lines),labels=line_map,
                                image_size=list(sample.size),source_group=source_group))
    classes=json.loads(Path(classes_path).read_text(encoding='utf-8'))['classes']
    data=dict(path=str(output.resolve()).replace('\\','/'),train='images/train',val='images/train',names={c['id']:c['name'] for c in classes})
    (output/'data.yaml').write_text(yaml.safe_dump(data,sort_keys=False),encoding='utf-8')
    represented={l['source_object_id'] for r in records for l in r['labels']}
    if represented!={o['object_id'] for o in original}:raise ValueError('Source objects lost in augmentation')
    manifest=dict(source_images=1,source_objects=len(original),derived_images=len(records),
                  instances=sum(r['instances'] for r in records),background_images=sum(not r['instances'] for r in records),
                  source_group=source_group,source_hashes=hashes,unique_objects_covered=len(represented),
                  independent_validation=False,validation='same_training_variants_fit_diagnostic_only',
                  note='Fragments preserve source IDs; augmentations do not create new independent CAD projects.',records=records)
    write(output/'manifest.json',manifest)
    if not all(sha(p)==h for p,h in hashes.items()):raise ValueError('Augmentation input changed')
    return {k:v for k,v in manifest.items() if k!='records'}
