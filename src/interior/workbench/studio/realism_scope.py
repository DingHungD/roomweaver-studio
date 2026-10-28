"""Review every room, reject cross-room regressions and conflicting shared edits."""
import copy
import json
from ...visualization.realism_scope import manifest_for_point
from ..storage import write_json


def review_rooms(review,verdict_type,folder,baseline_folder,baseline_manifest,candidate_folder,candidate_manifest,facts,original,stop,model):
    reviews=[];records=[]
    for index,room in enumerate(facts['rooms']):
        if stop.exists():raise ValueError('已停止整屋判圖')
        room=copy.deepcopy(room)
        for key in ('requirements_record','shelf_results','opening_results','completion_results','installation_results'):room[key]=facts.get(key,[] if key=='shelf_results' else '')
        point=room['point'];where=folder/('review-'+point['id']);where.mkdir(exist_ok=True)
        write_json(folder.parent/'progress.json',dict(completed=index,total=len(facts['rooms']),current='Agent 逐空間判圖 · '+point['name']))
        result=review(where,baseline_folder,manifest_for_point(baseline_manifest,point['id']),candidate_folder,manifest_for_point(candidate_manifest,point['id']) if candidate_manifest else None,room,original,stop,model)
        reviews.append((point,result));records.append(dict(point=point,**result.model_dump(mode='json')))
        write_json(folder/'room-reviews.json',records)
    return merge_reviews(reviews,verdict_type,candidate_folder is not None)


def merge_reviews(reviews,verdict_type,has_candidate):
    # Shared edits must agree; never let the last room silently override another.
    merged={key:[] for key in ('materials','lights','shelves','exteriors','ceilings','cameras')};remaining=[];conflicts=[]
    for key,id_key in (('materials','object_id'),('lights','light_id'),('shelves','object_id')):
        proposals={}
        for point,result in reviews:
            for item in getattr(result,key):
                value=item.model_dump(mode='json');identifier=value[id_key]
                compare={k:v for k,v in value.items() if k not in ('reason','evidence')}
                proposals.setdefault(identifier,[]).append((json.dumps(compare,sort_keys=True),value))
        for identifier,options in proposals.items():
            if len({x[0] for x in options})==1:merged[key].append(options[0][1])
            else:conflicts.append(f'共用構件 {identifier} 的跨空間提案不同，保留目前設定，待下輪整體判讀。')
    for key in ('exteriors','ceilings','cameras'):
        merged[key]=list(dict.fromkeys(v for _,result in reviews for v in getattr(result,key)))
    for point,result in reviews:remaining.extend(f"{point['name']}：{text}" for text in result.remaining)
    preferences=[v.preference for _,v in reviews]
    preference='candidate' if has_candidate and 'candidate' in preferences and 'baseline' not in preferences else 'baseline'
    if has_candidate and all(p=='equivalent' for p in preferences):preference='equivalent'
    return verdict_type(summary='\n'.join(p['name']+'：'+v.summary for p,v in reviews),preference=preference,
        reviewed_files=list(dict.fromkeys(f for _,v in reviews for f in v.reviewed_files)),remaining=remaining+conflicts,**merged)


def restore_unpreferred_cameras(candidate,best,reviews,proposals):
    """An unchanged camera proposal must not silently retain a rejected view."""
    changed=[];approved={c.get('point_id') for c in proposals if c.get('kind')=='camera'}
    prior={p['id']:p for p in best['viewpoints']}
    restore={r['point']['id'] for r in reviews if r['preference']=='baseline'}-approved
    for point in candidate['viewpoints']:
        base=prior.get(point['id'])
        if point['id'] in restore and base and point['shots']!=base['shots']:
            point['shots']=copy.deepcopy(base['shots'])
            changed.append(dict(kind='camera_restore',point_id=point['id'],name=point['name'],reason='此空間的新取景未優於基準，且沒有通過檢查的新鏡位提案；恢復較佳比較版本的效果圖鏡位再試渲染，全景眼位及家具不動。'))
    return changed


def select_reviewed_camera_rooms(best,candidate,reviews):
    """Combine independent reviewed cameras only; shared scene changes forbid mixing."""
    a=copy.deepcopy(best);b=copy.deepcopy(candidate)
    before=a.pop('viewpoints');after=b.pop('viewpoints')
    if a!=b:return copy.deepcopy(best),[]
    old={p['id']:p for p in before};new={p['id']:p for p in after}
    reviewed={r['point']['id']:r for r in reviews}
    if len(reviewed)!=len(reviews) or set(old)!=set(new) or set(reviewed)!=set(old):return copy.deepcopy(best),[]
    selected=copy.deepcopy(best);chosen=[]
    for point in selected['viewpoints']:
        pid=point['id'];candidate_point=new[pid]
        # Panorama eyes and room identity are never silently selected as camera edits.
        if {k:v for k,v in point.items() if k!='shots'}!={k:v for k,v in candidate_point.items() if k!='shots'}:return copy.deepcopy(best),[]
        if reviewed[pid]['preference']=='candidate' and point['shots']!=candidate_point['shots']:
            point['shots']=copy.deepcopy(candidate_point['shots']);chosen.append(pid)
    return selected,chosen
