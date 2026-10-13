"""Conservative local placement search in metres, independent of Blender/cases."""
import math

class PlacementError(ValueError):
    def __init__(self,message,parts,obstacles):
        super().__init__(message)
        self.details=[dict(obstacle=o['name'],part_bounds=p,obstacle_bounds=o['bounds'],
            penetration=[min(p[1][i],o['bounds'][1][i])-max(p[0][i],o['bounds'][0][i]) for i in range(3)])
            for p in parts for o in obstacles if overlaps(p,o['bounds'])][:12]

def shifted(box, delta):
    return [[v+delta[i] for i,v in enumerate(end)] for end in box]

def overlaps(a,b):
    # Touching support surfaces are allowed; actual penetration over 5 mm is not.
    return all(min(a[1][i],b[1][i])-max(a[0][i],b[0][i])>.005 for i in range(3))

def local_placement(parts, obstacles, policy=None):
    policy=policy or {};area=policy.get('area');radius=policy.get('max_distance',0)
    def problems(delta):
        moved=[shifted(p,delta) for p in parts];issues=[]
        if area and any(p[0][0]<area[0]-.001 or p[0][1]<area[1]-.001 or p[1][0]>area[2]+.001 or p[1][1]>area[3]+.001 for p in moved):issues.append('超出允許區域')
        for obstacle in obstacles:
            if any(overlaps(p,obstacle['bounds']) for p in moved):issues.append(obstacle['name'])
        for i,zone in enumerate(policy.get('keep_out',[])):
            if any(overlaps(p,[[zone[0],zone[1],-10000],[zone[2],zone[3],10000]]) for p in moved):issues.append(f'保留通道／門區 {i+1}')
        return sorted(set(issues))
    initial=problems([0,0,0])
    if not initial:return dict(status='clear',translation=[0,0,0],checked_obstacles=len(obstacles))
    if not area or not radius:raise PlacementError('碰撞檢查：'+', '.join(initial[:8])+'；尚未設定允許移動區域，保留原位置',parts,obstacles)
    # 5 cm lattice, at most 317 positions within 50 cm. Never change Z or scale.
    n=int(radius/.05+1e-8)
    offsets=sorted(((x*.05,y*.05,0) for x in range(-n,n+1) for y in range(-n,n+1) if 0<math.hypot(x*.05,y*.05)<=radius+.00001),key=lambda v:(math.hypot(*v[:2]),v))
    for delta in offsets:
        if not problems(delta):return dict(status='moved',translation=list(delta),resolved=initial,checked_obstacles=len(obstacles))
    raise PlacementError('局部避碰失敗：'+', '.join(initial[:8])+'；允許區域內無安全位置，保留原件',parts,obstacles)
