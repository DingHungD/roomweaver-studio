"""Read-only native folding checks for asynchronous door proposals."""
import json
import subprocess
from pathlib import Path


def check_folding(directory, payload, controls):
    from .engine import blender_executable
    from .service import digest
    directory = Path(directory).resolve()
    context = payload['collision_context']
    if digest(Path(context['blend'])) != context['sha256']:
        raise ValueError('門碰撞檢查的原模型已變更，請重新配置')
    request = dict(context, openings=payload['openings'], controls=controls,
                   originals=payload['controls'])
    source = directory/'door-collision-input.json'
    output = directory/'door-collision-result.json'
    source.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
    script = Path(__file__).parents[2]/'visualization'/'door_collision_check.py'
    with (directory/'door-collision.log').open('w', encoding='utf-8') as log:
        subprocess.run([blender_executable(), '-b', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1', '--python', str(script),
                        '--', str(source), str(output)], stdout=log, stderr=subprocess.STDOUT,
                       timeout=240, check=True)
    report = json.loads(output.read_text(encoding='utf-8'))
    return report['controls'], report['uncertainties']


_pose_lock = __import__('threading').Lock()

def check_poses(root, model, scene, source):
    """Cache native pose evidence without saving a design or modifying its source."""
    import hashlib
    from .engine import blender_executable
    from .service import digest
    root = Path(root)
    blend = root/'runs/interior-studio'/scene['model_id']/'model.blend'
    if digest(blend) != model['native_sha256']:
        raise ValueError('原生模型已變更，請重新載入')
    # Colours cannot change collisions; do not launch Blender on each colour edit.
    scene = dict(scene, door_controls=[{k:v for k,v in c.items() if k not in ('materials','name')} for c in scene.get('door_controls',[])])
    from .door_assets import resolve
    scene=resolve(scene,root)
    packet = dict(blend=str(blend),scene=scene,source=source,version=4)
    key=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
    directory=root/'runs/interior-studio/door-poses'/key
    output=directory/'result.json'
    with _pose_lock:
        if output.exists():return dict(json.loads(output.read_text(encoding='utf-8')),preview_key=key if (directory/'doors.glb').exists() else None)
        directory.mkdir(parents=True,exist_ok=True)
        request=directory/'input.json';request.write_text(json.dumps(packet),encoding='utf-8')
        script=Path(__file__).parents[2]/'visualization/door_pose_check.py'
        with (directory/'check.log').open('w',encoding='utf-8') as log:
            subprocess.run([blender_executable(),'-b','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script),'--',str(request),str(output)],stdout=log,stderr=subprocess.STDOUT,timeout=240,check=True)
        return dict(json.loads(output.read_text(encoding='utf-8')),preview_key=key if (directory/'doors.glb').exists() else None)


def width_candidates(payload):
    """Find the widest measured fit only for individually authorised single doors."""
    import math
    import copy
    context=payload['collision_context'];root=Path(context['blend']).parents[3]
    source=dict(items=[o for o in payload['openings'] if 'host_id' in o],source_sha256=context['sha256'])
    results={}
    for control in payload['controls']:
        if not control.get('allow_width_adjustment') or control.get('kind')!='single' or control.get('deleted'):continue
        opening=next((o for o in payload['openings'] if o['id']==control['opening_id']),None)
        if not opening:continue
        original=math.dist(*opening['points']);attempts=[]
        # A finite local search, never a global resize or silent change of swing.
        for step in range(0,16):
            width=round(original-step*.01,4)
            if width<.5:break
            scene=copy.deepcopy(context['scene'])
            c=next(c for c in scene['door_controls'] if c['opening_id']==control['opening_id'])
            c['assembly_width']=width if step else None
            report=check_poses(root,{'native_sha256':context['sha256']},scene,source)
            item=next((i for i in report['items'] if i['id']==control['opening_id']),{})
            state=item.get('opening',{}).get('state');clear=item.get('passage_check',{}).get('projected_clear_width',0)
            attempts.append(dict(width=width,state=state,clear_width=clear))
            if state=='open' and clear>=control.get('min_passage',.70):
                results[control['opening_id']]=dict(recommended_width=width if step else None,attempts=attempts,minimum_passage=control.get('min_passage',.70))
                break
        else:pass
        if control['opening_id'] not in results:results[control['opening_id']]=dict(recommended_width=None,no_fit=True,attempts=attempts)
    return results
