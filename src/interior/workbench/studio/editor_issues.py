"""Read existing editor evidence without resuming workflows or invoking an Agent."""
import json
from ..storage import read_json, write_json


def remember_door_task(studio, project, task, scene):
    write_json(studio.folder(project)/'doors/current-design.json',
               dict(id=task['id'], model_id=scene['model_id']))


def _door_target(note, openings):
    try:
        value=json.loads(note)
        if isinstance(value,dict):return value.get('opening_id'),str(value.get('reason',note))
    except (ValueError,TypeError):pass
    matches={o['id'] for o in openings if any(note.startswith(label+sep)
             for label in (o['id'],o.get('name','')) if label for sep in (':','：'))}
    return (next(iter(matches)) if len(matches)==1 else None),note


def editor_issues(studio, agents, project, revision):
    saved=studio.revision(project,revision);scene=saved['scene'];issues=[]
    folder=studio.folder(project)
    pointer=folder/'doors/current-design.json'
    if pointer.exists():
        link=read_json(pointer)
        if link['model_id']==scene['model_id']:
            task=agents.get(link['id'])
            packet=read_json(agents.root/link['id']/'input.json')
            if task['kind']!='door_design':raise ValueError('門配置紀錄類型不符')
            for note in task.get('uncertainties',[]):
                if note.startswith('[原推定，方向已由碰撞檢查修正]'):continue
                target,reason=_door_target(note,packet.get('openings',[]))
                issues.append(dict(category='door',target_id=target,source_task=link['id'],reason='上次 Agent 配置待確認：'+reason,status='需要確認'))
            if task['status'] in ('failed','stopped','interrupted'):
                issues.append(dict(category='door',target_id=None,reason=task.get('error') or '門配置任務未完成',status='未完成'))
    for pointer in (folder/'door-assets').glob('current-*.json'):
        key=read_json(pointer)['id'];task=agents.get(key)
        location=folder/'door-assets'/key;packet=read_json(location/'input.json')
        origin=studio.revision(project,packet['base_revision'])['scene']
        if origin['model_id']!=scene['model_id']:continue
        control=next((c for c in scene.get('door_controls',[]) if c['opening_id']==packet['opening_id']),{})
        if control.get('deleted'):continue
        binding=control.get('assets',{}).get(packet['part'],{})
        if binding.get('reference',{}).get('task_id')==key:continue
        selection=read_json(location/'selection.json') if (location/'selection.json').exists() else {}
        if selection.get('status')=='failed' or task['status'] in ('failed','stopped','interrupted'):
            issues.append(dict(category='door',target_id=packet['opening_id'],part=packet['part'],
                reason=selection.get('error') or task.get('error') or '門素材配對或替換未完成',status='素材未完成'))
    # Read raw workflow rows: Coordinator.get can resume nodes and is deliberately
    # not used by this read-only diagnostic endpoint.
    with studio.jobs.connect() as db:
        rows=db.execute('SELECT data FROM studio_workflows WHERE project_id=?',(project,)).fetchall()
    runs=sorted((json.loads(r[0]) for r in rows),key=lambda r:r.get('created_at',''),reverse=True)
    for run in runs:
        if run.get('revision')!=revision or not run.get('job_id'):continue
        job=studio.jobs.get(run['job_id'])
        if job['project_id']!=project or job.get('operation')!='studio.render':continue
        root=studio.root(project).resolve();path=(root/job['output']/'scene-review.json').resolve()
        if not path.is_relative_to(root):raise ValueError('檢查紀錄超出案件範圍')
        if not path.exists():continue
        report=read_json(path)
        if report.get('revision')!=revision or 'pending' not in report:continue
        model=studio.model(project,scene['model_id'])
        if report.get('source_sha256') and report['source_sha256']!=model.get('native_sha256'):continue
        for issue in report['pending']:
            if issue.get('category')=='viewpoint' and issue.get('action')!='cleared':
                issues.append(dict(category='viewpoint',target_id=issue.get('target_id'),shot_id=issue.get('shot_id'),
                    reason=issue.get('confirmation_question') or issue['reason'],status='取景待處理'))
        break
    # Only a verified adopted repair can resolve historical Agent notes. Current
    # native collisions are recomputed separately by the editor and never hidden.
    for file in (folder/'editor-repairs').glob('*/state.json'):
        repair=read_json(file);proof=repair.get('proof') or {}
        if repair.get('status')!='completed':continue
        if proof.get('door_id') and proof.get('model_id')==scene['model_id'] and next((c for c in scene.get('door_controls',[]) if c['opening_id']==proof['door_id']),None)==proof['control']:
            issues=[i for i in issues if not (i['category']=='door' and i['target_id']==proof['door_id'] and i.get('source_task')==proof.get('resolved_design_task') and i.get('source_task'))]
    return dict(revision=revision,issues=issues)
