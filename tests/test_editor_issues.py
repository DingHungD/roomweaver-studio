"""Synthetic saved evidence; no Codex, Blender, or workflow resume."""
import json
import sqlite3
from types import SimpleNamespace
from interior.workbench.storage import write_json
from interior.workbench.studio.editor_issues import editor_issues, remember_door_task


def setup(tmp_path):
    project=tmp_path/'project';project.mkdir()
    database=tmp_path/'jobs.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE studio_workflows(project_id TEXT,data TEXT)')
    scene=dict(model_id='a'*32,door_controls=[])
    jobs={}
    studio=SimpleNamespace(root=lambda p:project,folder=lambda p:project/'workflows/interior-studio',
        revision=lambda p,r:dict(scene=scene),model=lambda p,m:dict(native_sha256='f'*64),
        jobs=SimpleNamespace(connect=lambda:sqlite3.connect(database),get=lambda key:jobs[key]))
    tasks={}
    agents=SimpleNamespace(root=tmp_path/'agent-tasks',get=lambda key:tasks[key])
    return studio,agents,tasks,jobs,database,scene


def test_door_findings_restore_by_pointer_without_restarting_agent(tmp_path):
    studio,agents,tasks,_,_,scene=setup(tmp_path)
    key='b'*32
    tasks[key]=dict(id=key,kind='door_design',status='passed',uncertainties=['浴室：需確認折向'])
    write_json(agents.root/key/'input.json',dict(openings=[dict(id='bath',name='浴室')]))
    remember_door_task(studio,'P',tasks[key],scene)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result=editor_issues(studio,agents,'P','c'*32)
    assert result['issues'][0]['target_id']=='bath'
    assert '折向' in result['issues'][0]['reason']
    assert all(p.read_bytes()==raw for p,raw in before.items())
    scene['model_id']='d'*32
    assert editor_issues(studio,agents,'P','c'*32)['issues']==[]


def test_latest_same_revision_report_controls_viewpoint_pending_and_cleared(tmp_path):
    studio,agents,_,jobs,database,_=setup(tmp_path)
    revision='c'*32
    for index,(rev,sha) in enumerate([(revision,'f'*64),(revision,'wrong'),('old','f'*64)]):
        job=str(index);jobs[job]=dict(project_id='P',operation='studio.render',output='runs/'+job)
        with sqlite3.connect(database) as db:
            db.execute('INSERT INTO studio_workflows VALUES (?,?)',('P',json.dumps(dict(job_id=job,revision=rev,created_at=str(index)))))
        write_json(studio.root('P')/'runs'/job/'scene-review.json',dict(revision=rev,source_sha256=sha,pending=[dict(category='viewpoint',target_id='living',shot_id='front',reason='前景遮擋')]))
    result=editor_issues(studio,agents,'P',revision)
    assert len(result['issues'])==1 and result['issues'][0]['shot_id']=='front'
    write_json(studio.root('P')/'runs/0/scene-review.json',dict(revision=revision,source_sha256='f'*64,pending=[]))
    assert editor_issues(studio,agents,'P',revision)['issues']==[]


def test_door_asset_failure_is_bound_to_part_and_applied_reference_clears_it(tmp_path):
    studio,agents,tasks,_,_,scene=setup(tmp_path)
    key='e'*32;tasks[key]=dict(status='passed')
    base=studio.folder('P')/'door-assets'
    write_json(base/'current-leaf.json',dict(id=key))
    write_json(base/key/'input.json',dict(base_revision='c'*32,opening_id='entry',part='leaf-0'))
    write_json(base/key/'selection.json',dict(status='failed',error='比例不合'))
    issue=editor_issues(studio,agents,'P','c'*32)['issues'][0]
    assert issue['target_id']=='entry' and issue['part']=='leaf-0'
    scene['door_controls']=[dict(opening_id='entry',assets={'leaf-0':dict(reference=dict(task_id=key))})]
    assert editor_issues(studio,agents,'P','c'*32)['issues']==[]
