"""Durable first-version placement, serialized through the existing Blender queue.

Candidate links survive every attempt. No binary is reclaimed until review is
explicitly confirmed; a stopped or restarted runner never resubmits a known job.
"""
import threading
from .asset_matching import SelectAsset, target_reference
from .asset_quality import VERSION, assess
from .asset_repair import can_research, start_research, failure_kind
from ..storage import Conflict, read_json, write_json
from ...visualization.asset_fit import FIT_VERSION

ACTIVE = ('matching', 'applying')

def size_retry_targets(payload, state):
    if state.get('fit_policy_version',1)>=FIT_VERSION:return []
    return [t for t in payload['targets'] if t['kind']=='model' and not t.get('keep_original')
            and state['items'].get(t['task_id'],{}).get('status')=='needs_attention'
            and any(failure_kind(a.get('error'))=='size' for a in state['items'][t['task_id']].get('attempts',[]))]

def missing_blender(error):
    return '找不到 Blender' in (error or '')

def generation_targets(payload,state):
    from .parametric_assets import recipe,GENERATION_VERSION
    return [t for t in payload['targets'] if state['items'].get(t['task_id'],{}).get('status')=='needs_attention'
            and (state['items'][t['task_id']].get('generation_version',0)<GENERATION_VERSION or state['items'][t['task_id']].get('generation_failed') or (state['items'][t['task_id']].get('error') or '').startswith('Agent 概念建模未完成')) and recipe(t)
            and not any(failure_kind(a.get('error'))=='environment' for a in state['items'][t['task_id']].get('attempts',[])[-1:])]

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
                write_json(path,dict(status='matching',revision=revision,items={},stop=False,fit_policy_version=FIT_VERSION))
            state=read_json(path)
            if state['revision']!=revision:raise Conflict('設計已變更；請重新配置，既有成果與候選保留')
            if self.studio.current(project)['revision']!=revision:raise Conflict('設計已變更；請先載入最新修訂')
            payload=read_json(path.parent/'input.json')
            # Explicit resume upgrades only size failures; installed/kept/materials stay intact.
            for target in size_retry_targets(payload,state):
                row=state['items'][target['task_id']]
                history=row.get('previous_passes',[])+[{k:v for k,v in row.items() if k!='previous_passes'}]
                state['items'][target['task_id']]=dict(status='waiting',attempts=[],error=None,
                    previous_passes=history,generation=row.get('generation',0)+1,search_round=0)
            state['fit_policy_version']=FIT_VERSION
            # Upgrade legacy results through the same UI retry, never silently on load.
            if state.get('quality_version',0)<VERSION:
                payload=read_json(path.parent/'input.json')
                for target in payload['targets']:
                    row=state['items'].get(target['task_id'])
                    if not row:continue
                    result=self.assets.get(project,target['task_id'])
                    selected=next((c for c in result.get('candidates',[]) if c['asset_id']==row.get('asset_id')),None)
                    recheck=target['kind']=='material' or row['status']=='needs_attention' or (selected and assess(target['context'],selected,target['kind'])['status']=='blocked')
                    environment_retry=row['status']!='installed' and ((bool(row.get('attempts')) and missing_blender(row['attempts'][-1].get('error'))) or (row.get('job_id') and missing_blender(self.studio.jobs.get(row['job_id']).get('error'))))
                    if recheck and not environment_retry:
                        row.setdefault('previous_passes',[]).append({k:v for k,v in row.items() if k!='previous_passes'})
                        row.update(status='waiting',attempts=[],error=None,generation=row.get('generation',0)+1)
                        row.pop('job_id',None)
                state['quality_version']=VERSION
            # Retry environment failures from their saved candidates, retaining audit history.
            for row in state['items'].values():
                if row.get('job_id') and row['status']=='applying':
                    job=self.studio.jobs.get(row['job_id'])
                    if job['status']=='failed' and missing_blender(job.get('error')):
                        row['attempts'].append(dict(asset_id=row['asset_id'],job_id=job['id'],error=job['error']))
                        row.pop('job_id',None)
                        row.update(status='waiting',error=None)
                if row['status']=='needs_attention' and not row.get('restoring'):
                    payload=read_json(path.parent/'input.json')
                    target=next((t for t in payload['targets'] if t['task_id'] in state['items'] and state['items'][t['task_id']] is row),None)
                    if target:
                        result=self.assets.get(project,target['task_id']);ref=target_reference(self.studio.current(project)['scene'],target)
                        if any(ref and c['asset_id']==ref['asset_id'] and c.get('quality',{}).get('status')=='blocked' for c in result.get('candidates',[])):
                            row.update(status='waiting',error=None)
                if row['status']=='needs_attention' and any(missing_blender(a.get('error')) for a in row.get('attempts',[])):
                    row.update(status='waiting',error=None)
            state.update(stop=False,status='matching',error=None);write_json(path,state)
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
            current=self.studio.current(project)['scene']
            for row in result['items']:
                row['placement']=state['items'].get(row['task_id'],dict(status='waiting'))
                actual_ref=target_reference(current,row)
                checks=row.pop('_candidate_checks',{})
                row['quality']=checks.get(actual_ref['asset_id']) if actual_ref else None
                group=next((g for g in current['groups'] if g['id']==row['group_id'] and not g['deleted']),None)
                ref=target_reference(current,row)
                row['needs_keep_confirmation']=bool(group and not group.get('generated_reference') and row['placement']['status']!='kept' and (not ref or ref.get('status')!='applied'))
            result.update(status=state['status'],phase=state.get('phase',result.get('phase')),
                          error=state.get('error'),placement_revision=state['revision'])
            result['quality_version']=state.get('quality_version',0)
            result['fit_policy_version']=state.get('fit_policy_version',1)
            result['size_retry_count']=len(size_retry_targets(read_json(path.parent/'input.json'),state))
            result['generation_missing_count']=len(generation_targets(read_json(path.parent/'input.json'),state))
            result['confirmed']=state.get('confirmed_revision')==self.studio.current(project)['revision']
            return result

    def stop(self, project, identifier):
        self.batches.get(project,identifier)  # validates ownership and identifier
        with self.lock:
            path=self.path(project,identifier)
            if path.exists():
                state=read_json(path);state['stop']=True;write_json(path,state)
            if path.exists():
                for row in state['items'].values():
                    task=row.get('generation_task_id') or row.get('match_task_id')
                    if task and self.batches.agents.get(task)['status'] in ('queued','running','stopping'):self.batches.agents.stop(task)
            agent=self.batches.agents.get(identifier)
            if agent['status'] in ('queued','running','stopping'):self.batches.agents.stop(identifier)
        return dict(message='停止後續替換；執行中的 Blender 工作會完成，但不自動套用')

    def repair(self,project,identifier,revision):
        """Explicit UI action upgrades completed legacy batches without redoing successes."""
        with self.lock,self.studio.store.lock:
            result=self.batches.get(project,identifier)
            if result['status'] in (*ACTIVE,'queued','running','stopping'):return result
            if self.studio.current(project)['revision']!=revision:raise Conflict('請先保存最新設計')
            path=self.path(project,identifier);state=read_json(path);payload=read_json(path.parent/'input.json')
            if any(r.get('status')=='applying' and r.get('job_id') for r in state['items'].values()):
                raise Conflict('尚有待核對的替換工作；請先沿用候選繼續或檢視結果，不能改用新修訂重搜')
            # New matching contexts use current intent. Old immutable task inputs stay intact.
            from .asset_matching import object_context
            for target in payload['targets']:
                row=state['items'].get(target['task_id'],{})
                if row.get('status')!='needs_attention':continue
                task=row.get('match_task_id',target['task_id']);matched=self.assets.get(project,task)
                try:context=object_context(self.studio.current(project)['scene'],target['group_id'],target.get('object_id'),target.get('object_ids'))
                except ValueError:continue
                fresh=dict(target,context=context)
                if can_research(fresh,row,matched):
                    start_research(self.assets,project,identifier,fresh,row,matched,revision)
                elif not assess(context,{},target['kind'])['requirements']['purpose'] and target['kind']=='model':
                    row['error']='用途未明，請先在配對限制指定必要用途；不耗用搜尋重試'
            state.update(revision=revision,auto_repair=True,status='matching',stop=False,error=None,quality_version=VERSION)
            write_json(path,state)
            self.start(project,identifier,revision)
            return self.batches.get(project,identifier)

    def generate_missing(self,project,identifier,revision):
        with self.lock,self.studio.store.lock:
            result=self.batches.get(project,identifier)
            if result['status'] in (*ACTIVE,'queued','running','stopping'):return result
            if self.studio.current(project)['revision']!=revision:raise Conflict('請先載入最新修訂')
            path=self.path(project,identifier);state=read_json(path);payload=read_json(path.parent/'input.json')
            if state['revision']!=revision:raise Conflict('配置後設計已變更；請依最新物件規格重新配置')
            for target in generation_targets(payload,state):
                row=state['items'].get(target['task_id'],{})
                history=row.get('previous_passes',[])+[{k:v for k,v in row.items() if k!='previous_passes'}]
                retry_agent=row.get('generation_failed') or (row.get('error') or '').startswith('Agent 概念建模未完成')
                state['items'][target['task_id']]=dict(status='waiting',attempts=row.get('attempts',[]) if retry_agent else [],generation=row.get('generation',0)+1,
                    generated_recipe=row.get('generated_recipe') if retry_agent else None,
                    match_task_id=row.get('match_task_id',target['task_id']),force_generate=True,previous_passes=history)
            state.update(revision=revision,status='matching',stop=False,error=None)
            write_json(path,state);self.start(project,identifier,revision)
            return self.batches.get(project,identifier)

    def generate(self,project,identifier,target,row,state,path,match_task,payload):
        from .parametric_assets import recipe,GENERATION_VERSION
        from .asset_quality import requirements
        from uuid import uuid5,NAMESPACE_URL
        base=recipe(target)
        if not base:return False
        attempts=[a for a in row.get('attempts',[]) if a['asset_id']=='generated']
        if len(attempts)>=3:return False
        # Retry only model/placement errors; environment and provider failures stay visible.
        if attempts and failure_kind(attempts[-1].get('error'))=='environment':return False
        task=uuid5(NAMESPACE_URL,f"furniture-generation:{identifier}:{target['task_id']}:{row.get('generation',0)}:{len(attempts)}").hex
        row.update(generation_task_id=task,generation_version=GENERATION_VERSION,status='generating')
        state.update(status='applying',phase=('依錯誤修正概念家具：' if attempts else 'Agent 設計概念家具：')+target['name'])
        write_json(path,state)
        try:agent=self.batches.agents.get(task)
        except FileNotFoundError:
            data=dict(recipe=base,failures=[dict(error=(a.get('error') or '')[-1800:],check=a.get('check')) for a in attempts],previous=row.get('generated_recipe'))
            self.batches.agents.start('asset_generate',payload['settings'].get('model') or self.batches.agents.get(identifier).get('model'),data,identifier=task)
            return True
        if agent['status'] in ('queued','running','stopping'):return True
        if agent['status']!='passed':
            row.update(status='needs_attention',generation_failed=True,error='Agent 概念建模未完成：'+str(agent.get('error') or agent['status']))
            write_json(path,state);return True
        generated=dict(agent['recipe'],agent_task_id=task)
        row.update(status='applying',generated=True,asset_id='generated',generated_recipe=generated)
        state['phase']='建立並檢查概念家具：'+target['name'];write_json(path,state)
        job=self.studio.jobs.submit_studio(project,'replace',dict(revision=state['revision'],task_id=match_task,
            group_id=target['group_id'],generated=generated,rotation=0,auto_fit=True,
            asset_requirements=requirements(target['context'])),'generated-v2-'+identifier+'-'+task)
        row['job_id']=job['id'];write_json(path,state);return True

    def tick(self,project,identifier):
        """One recoverable transition. Never wait while holding the application lock."""
        path=self.path(project,identifier);state=read_json(path)
        if state.get('stop'):
            state['status']='stopped';write_json(path,state);return False
        agent=self.batches.agents.get(identifier)
        if agent['status'] in ('queued','running','stopping'):
            state.update(status='matching',phase=agent.get('phase','等待 Agent 配對'));write_json(path,state);return True
        payload=read_json(path.parent/'input.json')
        if agent['status']=='failed':
            error=agent.get('error') or 'Agent 批次未完成，請檢查設定後重新配置'
            for target in payload['targets']:
                state['items'].setdefault(target['task_id'],dict(status='needs_attention',error=error,attempts=[]))
            state.update(status='failed',phase='Agent 配置已停止，尚未開始自動下載與替換',error=error)
            write_json(path,state);return False
        current=self.studio.current(project)
        # Recover a crash between adopting a completed job and journaling revision.
        if current['revision']!=state['revision']:
            pending=next((r for r in state['items'].values() if r.get('job_id')==current['scene']['model_id'] and r['status']=='applying'),None)
            if pending:
                job=self.studio.jobs.get(pending['job_id'])
                from .models import Scene
                expected=Scene.model_validate(read_json(self.studio.root(project)/job['output']/'replacement-scene.json')).model_dump(mode='json')
                if job['source_revision']==state['revision'] and current['scene']==expected:
                    pending['status']='needs_attention' if pending.get('restoring') else 'installed';state['revision']=current['revision']
                    write_json(path,state);return True
            state.update(status='paused',error='目前設計已另外修改；停止自動套用，保留結果與備選連結')
            write_json(path,state);return False
        for target in payload['targets']:
            task=target['task_id'];row=state['items'].setdefault(task,dict(status='waiting',attempts=[]))
            if row['status'] in ('installed','needs_attention','kept'):continue
            if target.get('keep_original'):
                row.update(status='kept',error=None);write_json(path,state);return True
            match_task=row.get('match_task_id',task)
            if row['status']=='researching':
                search=self.assets.get(project,match_task)
                if search['status'] in ('queued','running','stopping'):
                    state.update(status='matching',phase=f"依失敗原因重新搜尋 {row['search_round']}／2：{target['name']}");write_json(path,state);return True
                if search['status']!='passed':
                    row.update(status='needs_attention',error=search.get('error') or '重新搜尋中斷；保留原件與候選，不自動重送');write_json(path,state);return True
                row['status']='waiting'
            if row.get('job_id'):
                job=self.studio.jobs.get(row['job_id'])
                if job['status'] in ('queued','running'):return True
                if job['status']=='completed':
                    saved=self.assets.adopt(project,job['id'],state['revision'])
                    row.update(status='needs_attention' if row.get('restoring') else 'installed',error='用途錯配已回復原件；沒有合格免費候選，請重新搜尋' if row.get('restoring') else None);state['revision']=saved['revision']
                    report=self.studio.root(project)/job['output']/'replacement-report.json'
                    if report.exists():row['repair_report']=read_json(report)
                    write_json(path,state);return True
                row['attempts'].append(dict(asset_id=row['asset_id'],job_id=job['id'],error=job.get('error',job['status'])))
                check=self.studio.root(project)/job['output']/'generation-check.json'
                if row['asset_id']=='generated' and check.exists():row['attempts'][-1]['check']=read_json(check)
                row.pop('job_id',None)
                if row['asset_id']=='generated':row.setdefault('generation_checks',[]).append(dict(job_id=job['id'],error=job.get('error')))
                if missing_blender(job.get('error')):
                    row.update(status='waiting',error='Blender 尚未設定；候選保留，修正環境後可繼續')
                    state.update(status='paused',phase='等待修正 Blender 執行環境',error=row['error'])
                    write_json(path,state);return False
            result=self.assets.get(project,match_task)
            specification=target.get('context',{}).get('group',{}).get('object_specification') or {}
            if specification.get('material_policy') in ('original','specified'):
                row.update(status='needs_attention',error='候選已保留；此物件要求保留原材質／指定部位材質。跨模型部件對應尚未驗證，不自動覆蓋原件。')
                write_json(path,state);return True
            tried={a['asset_id'] for a in row['attempts'] if not missing_blender(a.get('error'))}
            free=[c for c in result.get('candidates',[]) if c['is_free'] and c.get('license') in ('cc_zero','royalty_free')
                  and c.get('quality',{}).get('status')=='eligible' and c.get('download_url') and (not c.get('bytes') or c['bytes']<=150_000_000) and c['asset_id'] not in tried]
            row['rejected']=[dict(asset_id=c['asset_id'],name=c['name'],reasons=c.get('quality',{}).get('reasons',[])) for c in result.get('candidates',[]) if c.get('quality',{}).get('status')=='blocked']
            round_attempts=row['attempts'][row.get('round_start',0):]
            count=sum(not missing_blender(a.get('error')) for a in round_attempts)
            if count>=3 or row.get('force_generate') or row.get('generation_task_id'):free=[]
            if result['status']!='passed' or not free:
                ref=target_reference(current['scene'],target)
                invalid=next((c for c in result.get('candidates',[]) if ref and c['asset_id']==ref['asset_id'] and c.get('quality',{}).get('status')=='blocked'),None)
                if invalid and not row.get('restoring') and ref.get('task_id')==task:
                    job=self.assets.restore_target(project,task,state['revision'],'restore-purpose-'+identifier+'-'+task)
                    row.update(status='applying',restoring=True,job_id=job['id'])
                    state.update(status='applying',phase='回復用途錯配的原件：'+target['name'])
                    write_json(path,state);return True
                generation_allowed=(row.get('force_generate') or payload['settings'].get('procedural_fallback')) and result['status']=='passed' and not any(failure_kind(a.get('error'))=='environment' for a in row['attempts'][-1:])
                if generation_allowed and self.generate(project,identifier,target,row,state,path,match_task,payload):return True
                if not row.get('generation_task_id') and not row.get('force_generate') and state.get('auto_repair',payload['settings'].get('auto_repair',False)) and can_research(target,row,result):
                    start_research(self.assets,project,identifier,target,row,result,state['revision'])
                    state.update(status='matching',phase='依失敗原因重新搜尋：'+target['name']);write_json(path,state);return True
                row.update(status='needs_attention',error=result.get('error') or ('概念模型三版檢查仍未通過；保留原件與逐版錯誤，不能變更已確認尺寸或必要機能' if row.get('generation_task_id') else '已達兩輪重新搜尋上限；保留原件與全部備選，請查看逐項失敗原因' if row.get('search_round',0)>=2 else '本輪合格免費候選已用盡；保留原件與備選'))
                write_json(path,state);return True
            item=free[0]
            # Persist operation intent before submission: replay uses the same dedup key.
            row.update(status='applying',asset_id=item['asset_id'])
            state.update(status='applying',phase='下載與替換：'+target['name'])
            write_json(path,state)
            body=SelectAsset(base_revision=state['revision'],asset_id=item['asset_id'],accept_license=True,
                             operation_id='auto-q'+str(VERSION)+'-'+identifier+'-'+task+'-'+str(row.get('generation',0))+'-'+str(row.get('search_round',0))+'-'+str(len(row['attempts'])),auto_fit=True)
            job=self.assets.replace(project,match_task,body)
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
                ref=target_reference(current['scene'],target)
                if not target.get('keep_original') and not group.get('generated_reference') and (not ref or ref.get('status')!='applied'):unresolved.append(target['task_id'])
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
