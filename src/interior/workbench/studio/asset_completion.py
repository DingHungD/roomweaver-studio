"""Reconcile historical unfinished rows with verified, currently adopted assets.

This is a read-only projection. It never rewrites the old batch, adopts a trial,
or treats a saved URL (or an Agent's success message) as a replacement.
"""
from ..storage import read_json


def adopted_completion(studio, asset_folder, project, scene, target, lineage):
    group = next((g for g in scene['groups'] if g['id'] == target['group_id'] and not g.get('deleted')), None)
    if not group:
        return None
    members = target.get('object_ids') or ([target['object_id']] if target.get('object_id') else group['children'])
    if target['kind'] == 'model':
        refs = [group.get('asset_reference')]
    else:
        by_id = {o['id']: o for o in scene['objects']}
        refs = [by_id.get(i, {}).get('material', {}).get('asset_reference') for i in members]
    if not refs or any(not r or r.get('status') != 'applied' for r in refs):
        return None
    # Every selected surface must belong to the same verified replacement.
    ref = refs[0]
    if any(r != ref for r in refs):
        return None
    baseline = target['context']
    if target['kind'] == 'model' and baseline['group'].get('asset_reference') == ref and baseline['group']['children'] == group['children']:
        return None
    if target['kind'] == 'material' and all(o.get('material', {}).get('asset_reference') == ref for o in baseline['parts']):
        return None
    pointer = asset_folder / ref['task_id'] / 'replacement.json'
    pointed = read_json(pointer)['job_id'] if pointer.exists() else None
    # A later failed alternative can overwrite the task's last-job pointer.
    # Its unadopted trial must not make a still-used replacement unfinished.
    candidates = [pointed] if pointed in lineage else lineage
    for job_id in candidates:
        try:
            result = verified_job(studio,project,job_id,target,group,ref,members)
        except (FileNotFoundError,KeyError,ValueError):
            continue
        if result:return result
    return None


def verified_job(studio,project,job_id,target,group,ref,members):
    job = studio.jobs.get(job_id)
    if job['status'] != 'completed' or job['project_id'] != project or job['operation'] != 'studio.replace':
        return None
    folder = studio.root(project) / job['output']
    request = read_json(folder / 'request.json')
    if request.get('target_group') != group['id'] or request.get('task_id') != ref['task_id']:
        return None
    if (request.get('asset') or {}).get('asset_id') != ref['asset_id']:
        return None
    expected = read_json(folder / 'replacement-scene.json')
    installed = next((g for g in expected['groups'] if g['id'] == group['id']), None)
    if target['kind'] == 'model':
        report = read_json(folder / 'replacement-report.json')
        if report.get('model_check', {}).get('status') != 'passed':
            return None
        if not installed or installed.get('asset_reference') != ref or installed['children'] != group['children']:
            return None
    else:
        expected_objects = {o['id']: o for o in expected['objects']}
        applied_ids = request.get('target_objects') or ([request['target_object']] if request.get('target_object') else [])
        if not set(members).issubset(applied_ids) or any(expected_objects.get(i, {}).get('material', {}).get('asset_reference') != ref for i in members):
            return None
    return dict(status='installed', job_id=job_id, resolution='adopted_replacement',
                installation_verified=bool(installed and (installed.get('fixture_installation') or {}).get('verified')))


def failure_details(row):
    """Bounded candidate/check evidence for per-item display."""
    details = []
    for attempt in row.get('attempts', []):
        if attempt.get('error'):
            details.append(dict(asset_id=attempt.get('asset_id'), job_id=attempt.get('job_id'),
                                stage='模型／安裝檢查', reason=str(attempt['error'])[:4000]))
    for candidate in row.get('rejected', []):
        if candidate.get('reasons'):
            details.append(dict(asset_id=candidate.get('asset_id'), name=candidate.get('name'),
                                stage='候選用途檢查', reason='；'.join(candidate['reasons'])[:4000]))
    if row.get('error') and not details:
        details.append(dict(stage='配置', reason=str(row['error'])[:4000]))
    return details[-12:]
