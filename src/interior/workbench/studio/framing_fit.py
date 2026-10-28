"""Fit named subjects using native bounds; keep all camera positions immutable."""
import copy
import itertools
import math


def project(point, eye, shot):
    yaw,pitch=map(math.radians,(shot['yaw'],shot['pitch']))
    forward=(math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),math.sin(pitch))
    right=(math.sin(yaw),-math.cos(yaw),0)
    up=(-math.cos(yaw)*math.sin(pitch),-math.sin(yaw)*math.sin(pitch),math.cos(pitch))
    v=[point[i]-eye[i] for i in range(3)]
    dot=lambda a:sum(a[i]*v[i] for i in range(3))
    depth=dot(forward)
    if depth<=.08:return None
    return dot(right)/depth,dot(up)/depth


def fit_issue(scene, baseline, issue, manifest):
    """Conservative AABB fit, not an occlusion or construction approval."""
    ids=issue.get('framing_group_ids') or []
    if not ids:return issue,None
    if issue.get('category')!='viewpoint' or issue.get('action')!='shot':raise ValueError('入鏡目標僅適用鏡頭修正')
    measurements={m['id']:m for m in manifest.get('measurements',[])}
    groups={g['id'] for g in scene['groups'] if not g.get('deleted')}
    if any(k not in measurements or k not in groups for k in ids):raise ValueError('入鏡目標缺少原生尺寸證據')
    point=next(p for p in scene['viewpoints'] if p['id']==issue['target_id'])
    shot=next(s for s in point['shots'] if s['id']==issue['shot_id'])
    original=next(s for p in baseline['viewpoints'] if p['id']==point['id'] for s in p['shots'] if s['id']==shot['id'])
    eye=shot.get('eye') or point['eye'];height=10.125 if shot.get('aspect')=='16:9' else 13.5
    corners=[v for k in ids for v in itertools.product(*zip(*measurements[k]['bounds']))]
    candidates=[];margin=.94;shift=shot.get('shift_y',0)
    # Keep the narrowest lens that fits all subjects, not repeated blind widening.
    for dy in range(-15,16,2):
        for dp in range(-20,21,2):
            yaw=shot['yaw']+dy;pitch=shot['pitch']+dp
            if not -85<=pitch<=85 or abs(yaw-original['yaw'])>45 or abs(pitch-original['pitch'])>30:continue
            pose=dict(shot,yaw=yaw,pitch=pitch)
            slopes=[project(v,eye,pose) for v in corners]
            if any(v is None for v in slopes):continue
            for step in range(0,289):
                lens=min(shot['lens'],original['lens']+12)-step*.125
                if lens<max(12,original['lens']-12):break
                if all(abs(x*lens)<=18*margin and abs(y*lens-shift*36)<=height*margin for x,y in slopes):
                    candidates.append((lens-.015*(abs(dy)+abs(dp)),pose,lens));break
    if not candidates:raise ValueError('固定眼位與鏡頭範圍無法完整納入指定家具，保留待確認；未移動或縮放家具')
    _,pose,lens=max(candidates,key=lambda c:c[0])
    result=copy.deepcopy(issue);result['values']=dict(yaw=pose['yaw'],pitch=pose['pitch'],lens=lens)
    return result,dict(target_ids=ids,eye=list(eye),margin=margin,method='native_aabb_sensor_fit',values=result['values'],occlusion_checked=False)
