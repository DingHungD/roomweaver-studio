"""Short LangGraph invocations; interrupts release the coordinator and job worker."""
import json
import os
import sqlite3
import threading
from typing import TypedDict
from uuid import uuid4
from ..storage import Conflict, now

# Local execution history is sufficient; never opt into remote trace upload.
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.sqlite import SqliteSaver

class State(TypedDict, total=False):
    kind: str
    model_id: str
    task_id: str
    object_id: str
    agent_model: str | None
    run_id: str
    project_id: str
    revision: str
    quality: str
    scene_review: bool
    realism_point_id: str | None
    realism_all: bool
    prepare_openings: bool
    realism_brief: str
    confirmation_id: str
    job_id: str
    status: str

class Coordinator:
    def __init__(self, studio, agents=None):
        self.studio = studio
        self.agents = agents
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(studio.store.state_dir/'agent-checkpoints.sqlite3', check_same_thread=False)
        graph = StateGraph(State)
        graph.add_node('confirm', self._confirm)
        graph.add_node('submit', self._submit)
        graph.add_node('wait', self._wait)
        graph.add_node('spaces',lambda state:self._design_gate(state,'spaces','materials'))
        graph.add_node('materials',lambda state:self._design_gate(state,'materials','viewpoints'))
        graph.add_node('viewpoints',lambda state:self._design_gate(state,'viewpoints','ready'))
        graph.add_node('agent_submit',self._agent_submit)
        graph.add_node('agent_wait',self._agent_wait)
        graph.add_conditional_edges(START,lambda state:{'design':'spaces','agent':'agent_submit'}.get(state.get('kind'),'confirm'))
        graph.add_edge('agent_submit','agent_wait')
        graph.add_edge('agent_wait',END)
        graph.add_edge('spaces','materials')
        graph.add_edge('materials','viewpoints')
        graph.add_edge('viewpoints',END)
        graph.add_edge('confirm', 'submit')
        graph.add_edge('submit', 'wait')
        graph.add_edge('wait', END)
        self.graph = graph.compile(checkpointer=SqliteSaver(self.connection))

    def _config(self, identifier):
        return {'configurable': {'thread_id': identifier}}

    def _agent_submit(self,state):
        scene=self.studio.revision(state['project_id'],state['revision'])['scene']
        obj=next(o for o in scene['objects'] if o['id']==state['object_id'])
        task=self.agents.start('material',state.get('agent_model'),dict(project_id=state['project_id'],
            revision=state['revision'],object_id=obj['id'],name=obj['name'],**obj['material']),identifier=state['run_id'])
        return dict(task_id=task['id'],status='awaiting_agent')

    def _agent_wait(self,state):
        interrupt(dict(kind='agent_completion',task_id=state['task_id']))
        task=self.agents.get(state['task_id'])
        if task['status'] in ('queued','running','stopping'):raise ValueError('Agent 仍在執行')
        return dict(status='completed' if task['status']=='passed' else task['status'])

    def candidate(self,project_id,revision,object_id,model,operation_id):
        with self.lock,self.studio.store.lock:
            current=self.studio.current(project_id)
            if current['revision']!=revision:raise Conflict('請先保存最新設定')
            if object_id not in {o['id'] for o in current['scene']['objects']}:raise ValueError('物件不存在')
            with self.studio.jobs.connect() as db:
                row=db.execute('SELECT data FROM studio_workflows WHERE operation_id=?',(operation_id,)).fetchone()
            if row:
                previous=json.loads(row[0])
                if (previous['project_id'],previous['revision'],previous.get('object_id'),previous.get('agent_model'))!=(project_id,revision,object_id,model):
                    raise Conflict('候選任務操作識別碼已用於其他內容')
                run=previous
            else:
                run=dict(run_id=uuid4().hex,project_id=project_id,revision=revision,object_id=object_id,
                    agent_model=model,kind='agent',operation_id=operation_id,status='starting_agent',created_at=now())
                self._persist(run)
            config=self._config(run['run_id'])
            snapshot=self.graph.get_state(config)
            if not snapshot.values:
                self.graph.invoke({k:v for k,v in run.items() if k in State.__annotations__},config)
            elif snapshot.next==('agent_submit',):
                self.graph.invoke(None,config)
            run=self.get(run['run_id'])
            return self.agents.get(run['task_id'])

    def _design_gate(self,state,phase,next_phase):
        response=interrupt(dict(kind='design_'+phase,revision=state['revision']))
        current=self.studio.current(state['project_id'])
        if response.get('phase')!=phase or current['revision']!=response.get('revision'):
            raise Conflict('設計確認版本已過期')
        if current['scene']['model_id']!=state['model_id']:
            raise Conflict('模型已重新匯入，請建立新設計流程')
        return dict(revision=current['revision'],status='awaiting_'+next_phase if next_phase!='ready' else 'ready')

    def design(self,project_id):
        with self.lock:
            current=self.studio.current(project_id)
            if not current['scene']:
                raise ValueError('請先匯入模型')
            operation_id='design-'+project_id+'-'+current['scene']['model_id']
            with self.studio.jobs.connect() as db:
                rows=db.execute('SELECT data FROM studio_workflows WHERE project_id=?',(project_id,)).fetchall()
            previous=sorted((json.loads(r[0]) for r in rows),key=lambda r:r['created_at'],reverse=True)
            previous=next((r for r in previous if r.get('kind')=='design' and r.get('model_id')==current['scene']['model_id']),None)
            if previous:
                prior=self.get(previous['run_id'])
                if prior['status'] not in ('ready','stopped') or prior['revision']==current['revision']:
                    return prior
                operation_id+='-'+current['revision']
            run=dict(run_id=uuid4().hex,project_id=project_id,revision=current['revision'],
                model_id=current['scene']['model_id'],kind='design',operation_id=operation_id,
                confirmation_id=uuid4().hex,status='awaiting_spaces',created_at=now())
            self._persist(run)
            self.graph.invoke({k:v for k,v in run.items() if k in State.__annotations__},self._config(run['run_id']))
            return self.get(run['run_id'])

    def advance_design(self,project_id,phase,revision):
        with self.lock,self.studio.store.lock:
            run=self.design(project_id)
            order=['spaces','materials','viewpoints']
            if phase not in order:raise ValueError('設計步驟無效')
            if self.studio.current(project_id)['revision']!=revision:raise Conflict('場景版本已變動')
            if run['status']=='ready':return run
            expected=run['status'].removeprefix('awaiting_')
            if order.index(phase)<order.index(expected):return run
            if phase!=expected:raise Conflict('請先確認前一個設計步驟')
            self.graph.invoke(Command(resume=dict(phase=phase,revision=revision)),self._config(run['run_id']))
            return self.get(run['run_id'])

    def _confirm(self, state):
        response = interrupt(dict(kind='design_confirmation', confirmation_id=state['confirmation_id'], revision=state['revision']))
        if response != state['confirmation_id']:
            raise ValueError('確認項目不符')
        if self.studio.current(state['project_id'])['revision'] != state['revision']:
            raise Conflict('此確認已過期，請以新修訂建立流程')
        return {'status': 'confirmed'}

    def _submit(self, state):
        scene=self.studio.revision(state['project_id'],state['revision'])['scene']
        self.studio.check_render_readiness(state['project_id'],scene['model_id'],scene.get('lighting_setup'))
        job = self.studio.jobs.submit_studio(state['project_id'], 'render',
            dict(revision=state['revision'], quality=state['quality'], scene_review=state.get('scene_review',False), realism_point_id=state.get('realism_point_id'), realism_brief=state.get('realism_brief',''), agent_model=state.get('agent_model'),realism_all=state.get('realism_all',False),prepare_openings=state.get('prepare_openings',False)), 'workflow-'+state['run_id'])
        return dict(job_id=job['id'], status='rendering')

    def _wait(self, state):
        interrupt(dict(kind='render_completion', job_id=state['job_id']))
        job = self.studio.jobs.get(state['job_id'])
        if job['status'] in ('queued', 'running'):
            raise ValueError('渲染仍在執行')
        return dict(status=job['status'])

    def _persist(self, run):
        with self.studio.jobs.connect() as db:
            db.execute('INSERT OR REPLACE INTO studio_workflows VALUES (?,?,?,?)',
                (run['run_id'], run['project_id'], run['operation_id'], json.dumps(run,ensure_ascii=False)))
        return run

    def start(self, project_id, revision, operation_id, quality, scene_review=False, agent_model=None, realism_point_id=None, realism_brief="", realism_all=False, prepare_openings=False):
        with self.lock, self.studio.store.lock:
            with self.studio.jobs.connect() as db:
                row = db.execute('SELECT data FROM studio_workflows WHERE operation_id=?', (operation_id,)).fetchone()
            if row:
                prior=json.loads(row[0])
                if (prior['project_id'],prior['revision'],prior['quality'],prior.get('scene_review',False),prior.get('agent_model'),prior.get('realism_point_id'),prior.get('realism_brief',''),prior.get('realism_all',False),prior.get('prepare_openings',False)) != (project_id,revision,quality,scene_review,agent_model,realism_point_id,realism_brief,realism_all,prepare_openings):
                    raise Conflict('流程操作識別碼已用於不同內容')
                return self.get(prior['run_id'])
            if self.studio.current(project_id)['revision'] != revision:
                raise Conflict('場景版本已變動')
            scene=self.studio.revision(project_id,revision)['scene']
            self.studio.check_render_readiness(project_id,scene['model_id'],scene.get('lighting_setup'))
            if not scene['viewpoints']:
                raise ValueError('請先設定觀看點')
            if (realism_all or prepare_openings) and not realism_point_id:raise ValueError("請選擇寫實精修範圍")
            if realism_all and any(not p["shots"] for p in scene["viewpoints"]):raise ValueError("全案精修需要每個觀看點至少一個效果圖方向")
            if realism_point_id and not any(p['id']==realism_point_id and p['shots'] for p in scene['viewpoints']):
                raise ValueError('寫實試作需選擇含效果圖方向的觀看點')
            if realism_point_id and (scene_review or quality!='preview'):
                raise ValueError('寫實精修先使用獨立試作；採用後再整屋檢查與正式出圖')
            run=dict(run_id=uuid4().hex,project_id=project_id,revision=revision,operation_id=operation_id,
                quality=quality,scene_review=scene_review,realism_point_id=realism_point_id,realism_brief=realism_brief,realism_all=realism_all,prepare_openings=prepare_openings,agent_model=agent_model,confirmation_id=uuid4().hex,status='awaiting_confirmation',created_at=now())
            self._persist(run)
            self.graph.invoke({k:v for k,v in run.items() if k in State.__annotations__},self._config(run['run_id']))
            return self.get(run['run_id'])

    def get(self, identifier):
        with self.lock:
            with self.studio.jobs.connect() as db:
                row=db.execute('SELECT data FROM studio_workflows WHERE id=?',(identifier,)).fetchone()
            if not row:
                raise FileNotFoundError('流程不存在')
            run=json.loads(row[0])
            state=self.graph.get_state(self._config(identifier))
            if run['status']!='stopped':
                run.update(state.values)
                if run.get('task_id') and self.agents:
                    task=self.agents.get(run['task_id'])
                    if state.next and task['status'] not in ('queued','running','stopping'):
                        self.graph.invoke(Command(resume=task['status']),self._config(identifier))
                        run.update(self.graph.get_state(self._config(identifier)).values)
                if run.get('job_id'):
                    job=self.studio.jobs.get(run['job_id'])
                    run['job_status']=job['status']
                    run['error']=job.get('error')
                    if state.next and job['status'] not in ('queued','running'):
                        self.graph.invoke(Command(resume=job['status']),self._config(identifier))
                        run.update(self.graph.get_state(self._config(identifier)).values)
            return self._persist(run)

    def resume(self, identifier, revision, confirmation_id):
        with self.lock, self.studio.store.lock:
            run=self.get(identifier)
            if run.get('kind') in ('agent','design'):
                raise ValueError('請使用對應的設計或 Agent 接續入口')
            if run['revision']!=revision or run['confirmation_id']!=confirmation_id:
                raise Conflict('確認項目與版本不符')
            if run['status']=='stopped':
                raise Conflict('流程已停止')
            if run.get('job_id'):
                return run
            if self.studio.current(run['project_id'])['revision']!=revision:
                raise Conflict('確認已過期')
            config=self._config(identifier)
            snapshot=self.graph.get_state(config)
            if not snapshot.values:
                self.graph.invoke({k:v for k,v in run.items() if k in State.__annotations__},config)
            self.graph.invoke(Command(resume=confirmation_id),config)
            return self.get(identifier)

    def stop(self, identifier):
        with self.lock:
            run=self.get(identifier)
            if run.get('task_id') and self.agents:
                self.agents.stop(run['task_id'])
            if run.get('job_id'):
                job=self.studio.jobs.get(run['job_id'])
                if job['status']=='running':
                    raise ValueError('渲染執行中，無法安全中止；本次渲染仍會完成')
                self.studio.jobs.cancel(job['id'])
            run['status']='stopped'
            return self._persist(run)

    def close(self):
        with self.lock:
            self.connection.close()
