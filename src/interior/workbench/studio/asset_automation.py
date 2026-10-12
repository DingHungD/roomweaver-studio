"""Durable first-version placement, serialized through the existing Blender queue.

Candidate links survive every attempt. No binary is reclaimed until review is
explicitly confirmed; a stopped or restarted runner never resubmits a known job.
"""
import threading
from .asset_matching import SelectAsset
from ..storage import Conflict, read_json, write_json

ACTIVE = ('matching', 'applying')

class AutoPlacement:
    def __init__(self, batches):
        self.batches=batches;self.assets=batches.assets;self.studio=batches.studio
        self.lock=threading.RLock();self.threads={};self.closed=threading.Event()

    def path(self, project, identifier):return self.batches.folder(project)/identifier/'placement.json'

    def close(self):self.closed.set()

    def start(self, project, identifier, revision):
        with self.lock:
            key=(project,identifier)
            if key in self.threads and self.threads[key].is_alive():return
            path=self.path(project,identifier)
            if not path.exists():
                write_json(path,dict(status='matching',revision=revision,items={},stop=False))
            state=read_json(path)
            if state['revision']!=revision:raise Conflict('設計已變更；請重新配置，既有成果與候選保留')
            state.update(stop=False,status='matching');write_json(path,state)
            thread=threading.Thread(target=self.run,args=(project,identifier),daemon=True)
            self.threads[key]=thread;thread.start()

    def decorate(self, project, identifier, result):
        path=self.path(project,identifier)
        if not path.exists():return result
        with self.lock:
            state=read_json(path)
            thread=self.threads.get((project,identifier))
            if state['status'] in ACTIVE and (not thread or not thread.is_alive()):
                state.update(status='paused',error='服務曾中斷；按繼續會先核對既有工作，不重複下載')
                write_json(path,state)
            for row in result['items']:
                row['placement']=state['items'].get(row['task_id'],dict(status='waiting'))
                current=self.studio.current(project)['scene']
                group=next((g for g in current['groups'] if g['id']==row['group_id'] and not g['deleted']),None)
                ref=(group or {}).get('asset_reference') if row['kind']=='model' else next((o.get('material',{}).get('asset_reference') for o in current['objects'] if o['id']==row['object_id']),None)
                row['needs_keep_confirmation']=bool(group and (not ref or ref.get('status')!='applied'))
            result.update(status=state['status'],phase=state.get('phase',result.get('phase')),
                          error=state.get('error'),placement_revision=state['revision'])
            result['confirmed']=state.get('confirmed_revision')==self.studio.current(project)['revision']
            return result

    def stop(self, project, identifier):
        self.batches.get(project,identifier)  # validates ownership and identifier
        with self.lock:
            path=self.path(project,identifier)
            if path.exists():
                state=read_json(path);state['stop']=True;write_json(path,state)
            agent=self.batches.agents.get(identifier)
            if agent['status'] in ('queued','running','stopping'):self.batches.agents.stop(identifier)
        return dict(message='停止後續替換；執行中的 Blender 工作會完成，但不自動套用')

    def tick(self,project,identifier):
        """One recoverable transition. Never wait while holding the application lock."""
        path=self.path(project,identifier);state=read_json(path)
        if state.get('stop'):
            state['status']='stopped';write_json(path,state);return False
        agent=self.batches.agents.get(identifier)
        if agent['status'] in ('queued','running','stopping'):
            state.update(status='matching',phase=agent.get('phase','等待 Agent 配對'));write_json(path,state);return True
        payload=read_json(path.parent/'input.json')
        current=self.studio.current(project)
        # Recover a crash between adopting a completed job and journaling revision.
        if current['revision']!=state['revision']:
            pending=next((r for r in state['items'].values() if r.get('job_id')==current['scene']['model_id'] and r['status']=='applying'),None)
            if pending:
                job=self.studio.jobs.get(pending['job_id'])
                from .models import Scene
                expected=Scene.model_validate(read_json(self.studio.root(project)/job['output']/'replacement-scene.json')).model_dump(mode='json')
                if job['source_revision']==state['revision'] and current['scene']==expected:
                    pending['status']='installed';state['revision']=current['revision']
                    write_json(path,state);return True
            state.update(status='paused',error='目前設計已另外修改；停止自動套用，保留結果與備選連結')
            write_json(path,state);return False
        for target in payload['targets']:
            task=target['task_id'];row=state['items'].setdefault(task,dict(status='waiting',attempts=[]))
            if row['status'] in ('installed','needs_attention','kept'):continue
            if row.get('job_id'):
                job=self.studio.jobs.get(row['job_id'])
                if job['status'] in ('queued','running'):return True
                if job['status']=='completed':
                    saved=self.assets.adopt(project,job['id'],state['revision'])
                    row.update(status='installed',error=None);state['revision']=saved['revision']
                    write_json(path,state);return True
                row['attempts'].append(dict(asset_id=row['asset_id'],job_id=job['id'],error=job.get('error',job['status'])))
                row.pop('job_id',None)
            result=self.assets.get(project,task)
            tried={a['asset_id'] for a in row['attempts']}
            free=[c for c in result.get('candidates',[]) if c['is_free'] and c.get('license') in ('cc_zero','royalty_free')
                  and c.get('download_url') and (not c.get('bytes') or c['bytes']<=150_000_000) and c['asset_id'] not in tried]
            if result['status']!='passed' or not free:
                row.update(status='needs_attention',error=result.get('error') or '沒有可自動套用的免費候選，或免費候選皆下載／建模失敗；保留原件與備選')
                write_json(path,state);return True
            item=free[0]
            # Persist operation intent before submission: replay uses the same dedup key.
            row.update(status='applying',asset_id=item['asset_id'])
            state.update(status='applying',phase='下載與替換：'+target['name'])
            write_json(path,state)
            body=SelectAsset(base_revision=state['revision'],asset_id=item['asset_id'],accept_license=True,
                             operation_id='auto-'+identifier+'-'+task+'-'+str(len(row['attempts'])),auto_fit=True)
            job=self.assets.replace(project,task,body)
            row['job_id']=job['id'];write_json(path,state);return True
        state.update(status='review',phase='第一版處理完成；請檢視每件家具，備選只保留連結')
        write_json(path,state);return False

    def run(self,project,identifier):
        try:
            while not self.closed.is_set():
                with self.lock:
                    if not self.tick(project,identifier):break
                self.closed.wait(1)
        except Exception as exc:
            with self.lock:
                path=self.path(project,identifier);state=read_json(path)
                state.update(status='paused',error=str(exc));write_json(path,state)

    def confirm(self,project,identifier,revision,keep_original):
        from .asset_storage import clean_replacements
        # Explicit review is revision-bound; a later alternative invalidates it.
        with self.lock,self.studio.store.lock:
            result=self.batches.get(project,identifier)
            if result['status'] in (*ACTIVE,'queued','running','stopping'):raise Conflict('請等候配置完成或停止後再確認')
            current=self.studio.current(project)
            if current['revision']!=revision:raise Conflict('請先載入最新家具配置再確認')
            payload=read_json(self.path(project,identifier).parent/'input.json')
            unresolved=[]
            for target in payload['targets']:
                group=next((g for g in current['scene']['groups'] if g['id']==target['group_id'] and not g['deleted']),None)
                if not group:continue
                ref=group.get('asset_reference') if target['kind']=='model' else next((o.get('material',{}).get('asset_reference') for o in current['scene']['objects'] if o['id']==target['object_id']),None)
                if not ref or ref.get('status')!='applied':unresolved.append(target['task_id'])
            if set(keep_original)!=set(unresolved):raise Conflict('請逐項確認未替換項目要保留原件，再確認全部家具')
            state=read_json(self.path(project,identifier))
            owned={r['job_id'] for row in state['items'].values() for r in [row,*row.get('attempts',[])] if r.get('job_id')}
            # Include user-selected alternate jobs from these exact candidate tasks.
            for target in payload['targets']:
                replacement=self.assets.get(project,target['task_id']).get('replacement')
                if replacement:owned.add(replacement['job_id'])
            report=clean_replacements(self.studio,project,revision,discard_jobs=owned)
            state.update(confirmed_revision=revision if report['status']=='completed' else None,kept_original=unresolved)
            write_json(self.path(project,identifier),state)
            return report
