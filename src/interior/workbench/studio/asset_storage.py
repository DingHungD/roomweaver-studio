"""Reclaim superseded replacement binaries, retaining provenance and original imports."""
from pathlib import Path
from .service import digest
from ..storage import Conflict, read_json, write_json, now

def clean_replacements(studio,project,base_revision,discard_jobs=()):
    with studio.store.lock,studio.jobs.lock:
        current=studio.current(project)
        if current['revision']!=base_revision:raise Conflict('設計已變更，請重新讀取後清理')
        jobs=studio.jobs.list(project)
        if any(j['status'] in ('queued','running') or studio.jobs.external_alive(j) for j in jobs):
            return dict(status='deferred',bytes_freed=0,message='仍有工作使用模型，完成後可再清理')
        root=studio.root(project).resolve();runs=(root/'runs/interior-studio').resolve()
        if not runs.is_relative_to(root):raise ValueError('清理目錄超出案件')
        model_id=current['scene']['model_id']
        lineage=set(studio.model(project,model_id).get('ancestor_model_ids',[]))
        protected=set()
        source=studio.folder(project)/'source.json'
        if source.exists():
            for key in ('native','preview'):
                if read_json(source).get(key):protected.add((root/read_json(source)[key]).resolve())
        light=studio.folder(project)/'lighting-source.json'
        refs=[read_json(light)] if light.exists() else []
        source_job=current['scene'].get('lighting_setup',{}).get('source_job_id')
        if source_job:
            result=runs/source_job/'result.json'
            if result.exists():refs.append(read_json(result).get('lighting_source') or {})
        for ref in refs:
            if ref.get('path'):protected.add((root/ref['path']).resolve())
        freed=0;removed=[];skipped=[]
        for job in jobs:
            if job['operation']!='studio.replace' or job['status'] in ('queued','running'):continue
            folder=(root/job['output']).resolve()
            if not folder.is_relative_to(runs) or folder.parent!=runs:raise ValueError('清理目錄超出本案模型範圍')
            obsolete=job['id'] in lineage
            discarded=job['id'] in discard_jobs and job['id']!=model_id
            # Unadopted results stay available until the user chooses; never discard silently.
            if not obsolete and not discarded and job['id']!=model_id:continue
            names=['asset.blend','asset.partial','source.glb','model.blend1']
            if obsolete or discarded:names+=['model.blend','model.glb']
            paths=[folder/name for name in names]
            if any(p.resolve() in protected for p in paths):skipped.append(job['id']);continue
            records=[]
            for path in paths:
                if path.is_symlink() or not path.resolve().is_relative_to(folder):raise ValueError('拒絕清理目錄外的檔案')
                if path.is_file():records.append(dict(file=path.name,bytes=path.stat().st_size,sha256=digest(path)))
            if obsolete or discarded:
                # Journal first: a crash cannot leave a partially deleted model usable as an intact revision.
                marker=folder/'model-retired.json'
                if not marker.exists():write_json(marker,dict(time=now(),replaced_by=model_id,reason='節省空間：只保留來源紀錄',files=records))
            for record in records:
                (folder/record['file']).unlink();freed+=record['bytes']
            if records:removed.append(dict(job_id=job['id'],files=records))
        report=dict(status='completed',time=now(),bytes_freed=freed,removed=removed,protected=skipped,
            message='已清理舊替換模型及下載暫存；來源連結、修訂記錄、原始匯入與成果保留')
        write_json(studio.folder(project)/'asset-matching/storage-last.json',report)
        return report

def source_history(studio,project,group_id):
    history=[];seen=set()
    for path in sorted((studio.folder(project)/'revisions').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        scene=read_json(path)['scene'];group=next((g for g in scene.get('groups',[]) if g['id']==group_id),None)
        if not group:continue
        refs=[group.get('asset_reference')]+[o.get('material',{}).get('asset_reference') for o in scene['objects'] if o['id'] in group['children']]
        for ref in refs:
            if not ref:continue
            key=(ref['asset_id'],ref['version_id'],ref['kind'])
            if key not in seen:history.append(ref);seen.add(key)
    return history
