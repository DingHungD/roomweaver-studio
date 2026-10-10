"""Immutable case revisions, content-bound jobs and artifact lookup."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4
from ..storage import Conflict, now, read_json, write_json
from .models import Scene

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

class Studio:
    def __init__(self, store, jobs):
        self.store, self.jobs = store, jobs
        with jobs.connect() as db:
            from ..migrations import migrate
            migrate(db)

    def root(self, project_id):
        return self.store.project(project_id).root

    def folder(self, project_id):
        return self.root(project_id)/'workflows/interior-studio'

    def configured_source(self, project_id):
        config = read_json(self.folder(project_id)/'source.json')
        for key in ('native', 'preview'):
            path = (self.root(project_id)/config[key]).resolve()
            if not path.is_relative_to(self.root(project_id)) or not path.is_file():
                raise ValueError('模型來源超出案件或不存在')
        return config

    def current(self, project_id):
        pointer = self.folder(project_id)/'current.json'
        if not pointer.exists():
            return dict(revision=None, scene=None)
        result=self.revision(project_id, read_json(pointer)['revision'])
        # Read-through compatibility; the old revision file remains byte-for-byte intact.
        if not result['scene'].get('groups'):
            result['scene']['groups']=self.groups(project_id,result['scene']['model_id'])
        return result

    def groups(self, project_id, model_id):
        from .grouping import assembly_groups
        model=self.model(project_id,model_id)
        path=self.root(project_id)/'runs/interior-studio'/model_id/'model.glb'
        return assembly_groups(model['objects'],path)

    def revision(self, project_id, revision):
        if not re.fullmatch(r'[a-f0-9]{32}', revision):
            raise ValueError('修訂識別碼無效')
        return read_json(self.folder(project_id)/'revisions'/f'{revision}.json')

    def model(self, project_id, model_id):
        if not re.fullmatch(r'[a-f0-9]{32}', model_id):
            raise ValueError('模型識別碼無效')
        return read_json(self.root(project_id)/'runs/interior-studio'/model_id/'model.json')

    def save(self, project_id, scene, base_revision):
        scene = Scene.model_validate(scene).model_dump(mode='json')
        model = self.model(project_id, scene['model_id'])
        if not scene['groups']:
            scene['groups']=self.groups(project_id,scene['model_id'])
        if {x['id'] for x in scene['objects']} != {x['id'] for x in model['objects']}:
            raise ValueError('場景物件必須與匯入模型一致')
        with self.store.lock:
            if self.current(project_id)['revision'] != base_revision:
                raise Conflict('場景已更新，請重新讀取後再保存')
            revision = uuid4().hex
            result = dict(revision=revision, parent=base_revision, created_at=now(), scene=scene)
            path = self.folder(project_id)/'revisions'/f'{revision}.json'
            write_json(path, result)
            with self.jobs.connect() as db:
                db.execute('INSERT INTO studio_revisions VALUES (?,?,?,?)',
                    (project_id, revision, result['created_at'], str(path.relative_to(self.root(project_id)))))
            write_json(self.folder(project_id)/'current.json', {'revision': revision})
            return result

    def import_existing(self, project_id, operation_id):
        source = self.configured_source(project_id)
        return self.jobs.submit_studio(project_id, 'prepare', {'source': source}, operation_id)

    def check_render_readiness(self, project_id, model_id, lighting_setup=None):
        report=self.model(project_id,model_id).get('render_readiness',{})
        if lighting_setup and lighting_setup.get('enabled') and not report.get('missing_images'):
            return  # The immutable lighting proposal is checked again by Blender.
        if report.get('status')=='blocked':
            raise ValueError('模型可以編輯，但尚不能渲染：'+'；'.join(report.get('issues',[])))

    def propose_lighting(self, project_id, revision, operation_id):
        with self.store.lock:
            if self.current(project_id)['revision']!=revision:raise Conflict('請先保存最新設計')
            return self.jobs.submit_studio(project_id,'lighting',dict(revision=revision,quality='preview'),operation_id)

    def adopt_import(self, project_id, job_id, base_revision=None):
        job = self.jobs.get(job_id)
        if job['project_id'] != project_id or job['operation'] != 'studio.prepare' or job['status'] != 'completed':
            raise ValueError('模型尚未準備完成')
        current = self.current(project_id)
        if current['scene'] and current['scene']['model_id'] == job['id']:
            return current
        source = read_json(self.store.state_dir/'jobs'/job_id/'request.json')['parameters']['source']
        model = self.model(project_id, job['id'])
        return self.save(project_id, dict(model_id=job['id'], rooms=source['rooms'],
            objects=[dict(id=o['id'], name=o['name'], room_id=None, material={}) for o in model['objects']],
            viewpoints=source['viewpoints'], links=source['links']), base_revision)

    def outputs(self, project_id, include_deleted=False):
        current = self.current(project_id)['revision']
        with self.jobs.connect() as db:
            deleted={row[0] for row in db.execute('SELECT job_id FROM studio_output_trash WHERE project_id=?',(project_id,))}
        results = []
        for job in self.jobs.list(project_id):
            if job['id'] in deleted and not include_deleted:
                continue
            if job['operation'] == 'studio.render' and job.get('result'):
                for item in job['result'].get('images', []):
                    results.append(dict(item, job_id=job['id'], revision=job['source_revision'],
                        stale=job['source_revision'] != current, status=job['status'], deleted=job['id'] in deleted))
        return results

    def trash_outputs(self, project_id, base_revision, job_ids, restore=False):
        """Soft-delete explicit completed old runs; never mutate bound run evidence."""
        with self.store.lock:
            if self.current(project_id)['revision'] != base_revision:
                raise Conflict('設計修訂已改變，請重新整理後再清除成果')
            selected=set(job_ids)
            if not selected or len(selected)>1000:
                raise ValueError('請選擇 1 至 1000 個成果批次')
            for identifier in selected:
                job=self.jobs.get(identifier)
                if job['project_id']!=project_id or job['operation']!='studio.render' or job['status']!='completed' or not job.get('result',{}).get('images'):
                    raise ValueError('只可清除本案已完成的渲染成果')
                if not restore and job['source_revision']==base_revision:
                    raise ValueError('目前修訂的成果必須保留')
            with self.jobs.connect() as db:
                for identifier in selected:
                    if restore:
                        db.execute('DELETE FROM studio_output_trash WHERE project_id=? AND job_id=?',(project_id,identifier))
                    else:
                        db.execute('INSERT OR IGNORE INTO studio_output_trash VALUES (?,?,?)',(project_id,identifier,now()))
            return dict(job_count=len(selected),restored=restore)

    def artifact(self, project_id, job_id, name):
        job = self.jobs.get(job_id)
        if job['project_id'] != project_id or not job['operation'].startswith('studio.'):
            raise FileNotFoundError('成果不存在')
        root = (self.root(project_id)/job['output']).resolve()
        path = (root/name).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() not in ('.png', '.jpg', '.glb'):
            raise PermissionError('不支援的成果')
        if not path.is_file():
            raise FileNotFoundError('成果尚未產生')
        return path
