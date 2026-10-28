"""Bounded same-candidate retry used by the automatic placement workflow."""
from uuid import NAMESPACE_URL, uuid5
from .asset_quality import requirements
from .selected_repair import validate_plan
from ..storage import read_json, write_json


def request_repair(row, reason):
    asset=row.get('asset_id')
    if asset and asset!='generated' and asset not in row.get('adjusted_assets',[]):
        row['pending_adjust']=dict(asset_id=asset,reason=reason)


def advance(runner,project,identifier,target,row,state,path,payload,match_task):
    pending=row.get('pending_adjust')
    if not pending:return False
    asset_id=pending['asset_id'];req=requirements(target['context'])
    task=uuid5(NAMESPACE_URL,f"batch-adjust:{identifier}:{target['task_id']}:{asset_id}").hex
    row['adjust_task_id']=task;state.update(status='applying',phase='Agent 依檢查修正同一模型：'+target['name'])
    write_json(path,state)
    try:agent=runner.batches.agents.get(task)
    except FileNotFoundError:
        runner.batches.agents.start('asset_adjust',payload['settings'].get('model') or runner.batches.agents.get(identifier).get('model'),
            dict(requirements=req,asset=dict(asset_id=asset_id),previous=dict(scale=1,fit='uniform'),failures=row['attempts'][-3:]),identifier=task)
        return True
    if agent['status'] in ('queued','running','stopping'):return True
    if agent['status']!='passed':
        row.pop('pending_adjust');row.update(status='needs_attention',error='Agent 修正未完成；保留原件與候選：'+str(agent.get('error') or agent['status']))
        write_json(path,state);return True
    plan=validate_plan(agent['repair'],req).model_dump()
    previous_job=runner.studio.jobs.get(row['attempts'][-1]['job_id'])
    previous_report=runner.studio.root(project)/previous_job['output']/'replacement-report.json'
    previous=read_json(previous_report) if previous_report.exists() else {}
    changed=plan['scale']!=1 or (plan['fit']=='adapt' and not previous.get('dimension_adjustment'))
    if not plan['can_repair'] or not changed:
        row.setdefault('adjusted_assets',[]).append(asset_id);row.pop('pending_adjust');row.pop('adjust_task_id',None)
        row.setdefault('repair_notes',[]).append(plan['reason']);write_json(path,state);return False
    # The candidate is revalidated against the current revision, purpose and lineage.
    from .asset_matching import SelectAsset
    from .asset_quality import assess
    _,selected,item=runner.assets.candidate(project,match_task,SelectAsset(base_revision=state['revision'],asset_id=asset_id,accept_license=True,operation_id=task))
    if not item['is_free'] or assess(selected['context'],item,'model')['status']!='eligible':
        raise ValueError('修正候選的用途或免費資格已變更；不自動套用')
    job=runner.studio.jobs.submit_studio(project,'replace',dict(revision=state['revision'],task_id=match_task,
        asset=item,asset_requirements=req,dimension_fit=plan['fit'],repair_scale=plan['scale'],group_id=target['group_id'],
        rotation=0,auto_fit=True),'batch-adjust-'+task)
    row.setdefault('adjusted_assets',[]).append(asset_id);row.pop('pending_adjust');row.pop('adjust_task_id',None)
    row.update(job_id=job['id'],status='applying',asset_id=asset_id,adjustment=plan)
    write_json(path,state);return True
