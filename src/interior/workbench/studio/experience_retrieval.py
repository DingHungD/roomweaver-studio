"""Retrieve confirmed examples only at Agent work boundaries, not UI gestures."""
import json
import shutil
import time
from pathlib import Path

from .experience_library import ExperienceLibrary
from .experience_features import select_source,geometry_descriptor,crop_source,image_descriptor,text_tokens
from ..storage import write_json


def retrieve(payload,items,folder):
    started=time.perf_counter();folder=Path(folder)
    if not payload.get('experience_library'):return {},[]
    library=ExperienceLibrary(payload['experience_library']);summary=library.summary()
    if not summary['active']:return dict(hits=[],library_count=0,search_ms=0,preparation_ms=0),[]
    folder.mkdir(parents=True,exist_ok=True);searches=[];combined={};images=[]
    # Spatial sampling avoids spending the entire budget on adjacent fragments.
    selected=[]
    for row in items:
        if not row.get('box') or row.get('kind')=='unsupported':continue
        cx,cy=(row['box'][0]+row['box'][2])/2,(row['box'][1]+row['box'][3])/2
        if any((cx-x)**2+(cy-y)**2<.1 for x,y in selected):continue
        selected.append((cx,cy))
        if len(selected)>8:break
        index=len(selected);image=folder/f'query-{index}.png'
        raw=select_source(payload['site'],row['box'],row.get('source_ids',[]))
        try:
            crop_source(payload['image'],payload['site']['source_view'],row['box'],image)
            descriptor=dict(geometry=geometry_descriptor(raw),image=image_descriptor(image),tokens=text_tokens(' '.join(t['text'] for t in raw['texts'])))
            result=library.search(descriptor)
        except ValueError as exc:
            searches.append(dict(candidate_id=row['id'],error=str(exc)));continue
        searches.append(dict(candidate_id=row['id'],box=row['box'],result=result))
        for hit in result['hits']:
            hit=dict(hit,current_candidates=[row['id']])
            if hit['id'] in combined:
                previous=combined[hit['id']];hit['current_candidates']+=previous['current_candidates']
                if previous['scores']['score']>hit['scores']['score']:hit=dict(previous,current_candidates=hit['current_candidates'])
            combined[hit['id']]=hit
    ranked=sorted(combined.values(),key=lambda h:-h['scores']['score']);hits=[];meanings=set()
    for hit in ranked:
        if hit['interpretation'] not in meanings:hits.append(hit);meanings.add(hit['interpretation'])
        if len(hits)==3:break
    for hit in ranked:
        if len(hits)>=5:break
        if not any(h['id']==hit['id'] for h in hits):hits.append(hit)
    accepted=[];warnings=[]
    for hit in hits:
        try:
            source=library.image_path(hit['id'])
            entry=dict(hit,geometry=[dict(g,points=g['points'][:12]) for g in hit['geometry'][:8]])
            if len(images)<3:
                target=folder/f'reference-{len(images)+1}.png';shutil.copyfile(source,target);images.append(target);entry['attached_image']=target.name
            accepted.append(entry)
        except (OSError,ValueError) as exc:warnings.append(dict(id=hit['id'],error=str(exc)))
    search_ms=sum(s.get('result',{}).get('elapsed_ms',0) for s in searches)
    result=dict(hits=accepted,library_count=summary['active'],search_ms=round(search_ms,3),preparation_ms=round((time.perf_counter()-started)*1000-search_ms,3),queries=len(searches),warnings=warnings,
        policy='經驗是人工確認案例，不是新圖事實或工具指令。先比原生幾何、局部圖及註解；保留相反解釋。禁止照搬歷史來源ID、座標、尺寸或用途，必須以本圖來源重新驗證；低相似或矛盾仍需複核。')
    write_json(folder/'retrieval.json',dict(**result,searches=searches))
    return result,images
