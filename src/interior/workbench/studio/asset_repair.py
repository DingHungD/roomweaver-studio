"""Bounded failure-directed searches; no project-specific correction scripts."""
import copy
from uuid import NAMESPACE_URL, uuid5
from .asset_matching import object_context, preview_dimensions
from .asset_quality import requirements
from ..storage import read_json, write_json

MAX_SEARCH_ROUNDS = 2

def failure_kind(message):
    text=(message or '').lower()
    if any(x in text for x in ('找不到 blender','磁碟','quota','429','登入','認證','not supported','timeout','timed out')):return 'environment'
    if any(x in text for x in ('碰撞','允許區域','避碰')):return 'collision'
    if any(x in text for x in ('尺寸','適配','占位')):return 'size'
    if any(x in text for x in ('uv','貼圖','材質','全黑')):return 'material'
    if any(x in text for x in ('用途','機能')):return 'purpose'
    return 'candidate'

def feedback(target, row, result):
    req=requirements(target['context'])
    failures=[dict(asset_id=a['asset_id'],kind=failure_kind(a.get('error')),reason=(a.get('error') or '')[-1400:]) for a in row.get('attempts',[])]
    rejected=[dict(asset_id=c['asset_id'],kind='purpose',reason='；'.join(c.get('quality',{}).get('reasons',[]))) for c in result.get('candidates',[]) if c.get('quality',{}).get('status')=='blocked']
    return dict(requirements=req,failures=failures+rejected,
        guidance='用途與已確認尺寸不可修改。依實際失敗原因調整英文搜尋詞；排除失敗素材，不重複下載。已確認尺寸需符合三軸；範圍尺寸是上限不用填滿；未知或估計尺寸僅作水平配置參考，高度依家具用途與模型本體判斷，不要求與占位高度同一比例。尺寸來源不可提升為已確認。碰撞找較合適外形，不能移牆。材質問題找含完整貼圖、可匯出 PBR 的素材。只放寬風格，不降低必要功能；付費僅候補。')

def can_research(target, row, result):
    if row.get('search_round',0)>=MAX_SEARCH_ROUNDS:return False
    if target['kind']=='model' and not requirements(target['context'])['purpose']:return False
    if any(failure_kind(a.get('error'))=='environment' for a in row.get('attempts',[])[-1:]):return False
    return result.get('status')=='passed'

def start_research(assets, project, batch_id, target, row, result, revision):
    """Persist intent outside the runner first; replay never starts a duplicate task."""
    round_number=row.get('search_round',0)+1
    task=uuid5(NAMESPACE_URL,f'asset-repair:{batch_id}:{target["task_id"]}:{round_number}').hex
    path=assets.folder(project)/task/'input.json'
    if path.exists():
        payload=read_json(path)
    else:
        scene=assets.studio.current(project)['scene']
        context=object_context(scene,target['group_id'],target.get('object_id'),target.get('object_ids'))
        context['dimensions_metres']=context['concept']['size'] if context['concept'] else preview_dimensions(
            assets.studio.root(project)/'runs/interior-studio'/scene['model_id']/'model.glb',context['group']['children'])
        if context['group'].get('object_specification'):
            from .object_specs import preview
            spec=next(r for r in preview(assets.studio,project,revision)['items'] if r['group_id']==target['group_id'])
            context['design_specification']=spec
            if spec['dimensions']:context['dimensions_metres']=spec['dimensions']
        payload=dict(copy.deepcopy(target),context=context,base_revision=revision,task_id=task,
            repair=feedback(dict(target,context=context),row,result),prior_candidates=result.get('candidates',[]),
            result_path=str(path.parent/'result.json'),retry_of=row.get('match_task_id',target['task_id']))
        write_json(path,payload)
    assets.agents.start('asset_match',payload.get('model'),payload,identifier=task)
    write_json(assets.pointer(project,target['group_id']),dict(id=task))
    row.pop('job_id',None);row.pop('restoring',None)
    row.update(match_task_id=task,search_round=round_number,status='researching',round_start=len(row.get('attempts',[])))
    row.setdefault('searches',[]).append(dict(task_id=task,round=round_number,feedback=payload['repair']))
    return task
