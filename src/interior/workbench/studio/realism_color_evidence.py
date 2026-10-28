"""Measure rendered wall samples without claiming a photographic white balance."""
from statistics import median
from PIL import Image


def wall_colors(folder, facts):
    images={};result={}
    try:
        for obj in facts.get('objects',[]):
            if not obj.get('editable') or not any(s in obj['name'].lower() for s in ('wall-','wall_','牆')):continue
            for region in obj.get('screen_regions',[]):
                points=region.get('sample_uv',[])
                if len(points)<12:continue
                file=region['file']
                if file not in images:
                    with Image.open(folder/file) as image:images[file]=image.convert('RGB')
                image=images[file];w,h=image.size
                samples=[image.getpixel((min(w-1,max(0,int(u*w))),min(h-1,max(0,int(v*h))))) for u,v in points]
                rgb=[round(median(p[i] for p in samples)/255,4) for i in range(3)]
                result[(obj['id'],file)]=dict(name=obj['name'],samples=len(points),median_srgb=rgb,red_blue_ratio=round(rgb[0]/max(.001,rgb[2]),4))
    finally:
        for image in images.values():image.close()
    return result


def compare_wall_colors(before_folder,before_facts,after_folder,after_facts):
    before=wall_colors(before_folder,before_facts);after=wall_colors(after_folder,after_facts)
    return [dict(object_id=key[0],file=key[1],before=before[key],after=after[key]) for key in sorted(before.keys()&after.keys())]
