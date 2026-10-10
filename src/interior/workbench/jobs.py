"""Durable serial work queue with isolated engine subprocesses."""
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from contextlib import contextmanager
from uuid import uuid4
from .storage import now, read_json, write_json

class Jobs:
    def __init__(self, store):
        self.store=store
        self.database=store.state_dir/'jobs.sqlite3'
        self.lock=threading.RLock()
        self.stop=threading.Event()
        self.wake=threading.Event()
        self.close_callbacks=[]
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, project_id TEXT, status TEXT, data TEXT)')
            for (raw,) in db.execute("SELECT data FROM jobs WHERE status IN ('running','queued','interrupted')").fetchall():
                item=json.loads(raw)
                result_path=store.state_dir/'jobs'/item['id']/'result.json'
                if item['operation'].startswith('studio.') and result_path.exists():
                    packet=read_json(result_path)
                    item.update(status=packet['status'],result=packet.get('result'),error=packet.get('error'),updated_at=now())
                    db.execute('UPDATE jobs SET status=?,data=? WHERE id=?',(item['status'],json.dumps(item,ensure_ascii=False),item['id']))
                    continue
                if item['operation'].startswith('studio.') and self.external_alive(item):
                    item.update(status='running',external_running=True,cancel_supported=False,error=None)
                    item['events'].append(dict(time=now(),message='已重新接上仍在執行的本機程序；不另建渲染'))
                    db.execute('UPDATE jobs SET status=?,data=? WHERE id=?',('running',json.dumps(item,ensure_ascii=False),item['id']))
                    continue
                item['status']='interrupted'
                item['updated_at']=now()
                item['error']='服務重新啟動；此工作未自動重跑，請檢查保留產物後建立新工作'
                item['events'].append(dict(time=now(),message=item['error']))
                db.execute('UPDATE jobs SET status=?,data=? WHERE id=?',(item['status'],json.dumps(item,ensure_ascii=False),item['id']))
        self.thread=threading.Thread(target=self.loop,daemon=True,name='interior-workbench-jobs')
        self.thread.start()

    @contextmanager
    def connect(self):
        connection=sqlite3.connect(self.database,timeout=20)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def write(self,item):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?,?)',(item['id'],item['project_id'],item['status'],json.dumps(item,ensure_ascii=False,allow_nan=False)))

    def list(self,project_id=None):
        with self.connect() as db:
            rows=db.execute('SELECT data FROM jobs'+(' WHERE project_id=?' if project_id else ''),(project_id,) if project_id else ()).fetchall()
        return sorted((json.loads(row[0]) for row in rows),key=lambda j:j['created_at'],reverse=True)

    def get(self,identifier):
        with self.connect() as db:
            row=db.execute('SELECT data FROM jobs WHERE id=?',(identifier,)).fetchone()
        if not row:
            raise FileNotFoundError('工作不存在')
        return json.loads(row[0])

    def cancel(self,identifier):
        with self.lock:
            item=self.get(identifier)
            if item['status']=='running':
                raise ValueError('執行中的核心工作不支援安全取消；請等待完成。排隊工作可取消。')
            if item['status']=='queued':
                item.update(status='cancelled',updated_at=now(),cancel_supported=False)
                item['events'].append(dict(time=now(),message='已取消排隊工作'))
                self.write(item)
            return item

    def submit_studio(self,project_id,operation,parameters,operation_id):
        """Reserve one deterministic effect in the same transaction as its queue item."""
        import re
        if operation not in ('prepare','render','lighting') or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',operation_id):
            raise ValueError('Studio 工作識別碼無效')
        project=self.store.project(project_id)
        fingerprint=hashlib.sha256(json.dumps([project_id,operation,parameters],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.lock:
            with self.connect() as db:
                previous=db.execute('SELECT fingerprint,job_id FROM studio_operations WHERE id=?',(operation_id,)).fetchone()
                if previous:
                    if previous[0]!=fingerprint:
                        from .storage import Conflict
                        raise Conflict('操作識別碼已用於不同內容')
                    return self.get(previous[1])
                identifier=uuid4().hex
                output='runs/interior-studio/'+identifier
                item=dict(id=identifier,project_id=project_id,operation='studio.'+operation,status='queued',
                    created_at=now(),updated_at=now(),output=output,source_revision=parameters.get('revision'),
                    events=[dict(time=now(),message='已排入本機 3D 工作佇列')],result=None,error=None,cancel_supported=True)
                write_json(self.store.state_dir/'jobs'/identifier/'request.json',dict(project=str(project.root),operation='studio.'+operation,
                    parameters=dict(parameters,output=output,job_id=identifier)))
                db.execute('INSERT INTO jobs VALUES (?,?,?,?)',(identifier,project_id,'queued',json.dumps(item,ensure_ascii=False)))
                db.execute('INSERT INTO studio_operations VALUES (?,?,?,?)',(operation_id,project_id,fingerprint,identifier))
            self.wake.set()
            return item

    def loop(self):
        while not self.stop.is_set():
            with self.lock:
                external=False
                for pending in self.list():
                    if pending.get('external_running'):
                        result_path=self.store.state_dir/'jobs'/pending['id']/'result.json'
                        if result_path.exists():
                            packet=read_json(result_path)
                            pending.update(status=packet['status'],result=packet.get('result'),error=packet.get('error'),external_running=False,updated_at=now())
                            self.write(pending)
                        elif self.external_alive(pending):
                            external=True
                        else:
                            pending.update(status='interrupted',external_running=False,error='外部程序已結束但未留下完成結果；不自動重跑',updated_at=now())
                            self.write(pending)
                queued=[j for j in reversed(self.list()) if j['status']=='queued']
                item=queued[0] if queued and not external else None
                if item:
                    item.update(status='running',updated_at=now(),cancel_supported=False)
                    item['events'].append(dict(time=now(),message='本機核心執行中；核心結果與設計狀態將分別保存'))
                    self.write(item)
            if not item:
                self.wake.wait(1)
                self.wake.clear()
                continue
            job_dir=self.store.state_dir/'jobs'/item['id']
            try:
                env=os.environ.copy()
                env['PYTHONPATH']=str(Path(__file__).resolve().parents[2])+os.pathsep+env.get('PYTHONPATH','')
                with (job_dir/'process.log').open('w',encoding='utf-8') as log:
                    process=subprocess.Popen([sys.executable,'-m','interior.workbench.worker',str(job_dir/'request.json'),str(job_dir/'result.json')],stdout=log,stderr=log,env=env,cwd=self.store.workspace,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    from .studio.processes import identity
                    item['worker_process']=dict(pid=process.pid,identity=identity(process.pid))
                    self.write(item)
                    try:process.wait(timeout=14400)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        raise
                packet=read_json(job_dir/'result.json')
                item['result']=packet.get('result')
                item['error']=packet.get('error')
                item['status']=packet['status']
            except Exception as exc:
                item['status']='failed'
                item['error']=str(exc)[:2000]
                if item['operation'].startswith('studio.') and self.external_alive(item):
                    item.update(status='running',external_running=True,error='工作程序中斷，但 Blender 仍在執行；等待既有程序結束')
            with self.lock:
                if not self.stop.is_set():
                    item['updated_at']=now()
                    item['events'].append(dict(time=now(),message='執行狀態：'+item['status']))
                    self.write(item)

    def external_alive(self,item):
        from .studio.processes import alive
        if alive(item.get('worker_process')):return True
        if item.get('output'):
            path=self.store.project(item['project_id']).root/item['output']/'blender-process.json'
            if path.exists():
                try:return alive(read_json(path))
                except (ValueError,OSError):return False
        return False

    def close(self):
        with self.lock:
            self.stop.set()
            self.wake.set()
            for item in self.list():
                if item['status'] in ('running','queued'):
                    item.update(status='interrupted',updated_at=now(),cancel_supported=False,error='本機服務停止；外部核心程序可能仍在執行，請檢查結果後再建立新工作')
                    item['events'].append(dict(time=now(),message=item['error']))
                    self.write(item)
        self.thread.join(timeout=2)
        for callback in self.close_callbacks:
            callback()
        self.close_callbacks=[]
