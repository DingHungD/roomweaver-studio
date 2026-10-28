"""Synthetic work monitoring: no model calls, replay or workflow side effects."""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from interior.workbench.agent_runtime.service import AgentTasks
from interior.workbench.agent_runtime.activity import record_phase
from interior.workbench.jobs import Jobs
from interior.workbench.server import create_app
from interior.workbench.storage import read_json, write_json


def save_task(agents, digit, status, **extra):
    task = dict(id=digit * 32, kind='plan_semantics', status=status,
                created_at=f'2026-10-25T10:00:0{digit}+00:00', **extra)
    write_json(agents.root / task['id'] / 'task.json', task)
    return task


def test_snapshots_separate_pending_history_and_do_not_expose_payloads_or_write(tmp_path):
    agents = AgentTasks(tmp_path)
    queued = save_task(agents, '1', 'queued')
    running = save_task(agents, '2', 'running', phase='來源候選局部複核 2')
    save_task(agents, '3', 'failed', error='原生來源不一致', finished_at='2026-10-25T11:00:00+00:00',
              response={'text': 'private model output'}, candidate={'private': True})
    save_task(agents, '4', 'passed', finished_at='2026-10-25T12:00:00+00:00')
    write_json(agents.root / running['id'] / 'input.json', dict(
        private='never return input', experience_context=dict(project='SYNTHETIC', plan='PLAN'),
        site=dict(correction_batch=dict(items=[dict(id='m-a', title='修正合成窗戶')]))))
    before = {p: p.read_bytes() for p in agents.root.rglob('*') if p.is_file()}
    with patch('interior.workbench.agent_runtime.service.CodexRuntime', side_effect=AssertionError('no model')):
        result = agents.list(history_limit=1)
        older = agents.list(history_limit=1, history_offset=1)
    assert [t['id'] for t in result['active']] == [running['id'], queued['id']]
    assert result['active'][0]['activity'] == dict(title='批次修改平面物件', project_id='SYNTHETIC', plan_id='PLAN', items=['修正合成窗戶'])
    assert result['history'][0]['status'] == 'passed' and result['history_total'] == 2
    assert older['history'][0]['error'] == '原生來源不一致'
    assert 'private' not in json.dumps(result) + json.dumps(older)
    assert before == {p: p.read_bytes() for p in agents.root.rglob('*') if p.is_file()}


def test_one_unreadable_record_does_not_hide_other_work(tmp_path):
    agents = AgentTasks(tmp_path)
    save_task(agents, '1', 'stopping')
    damaged = agents.root / ('a' * 32) / 'task.json'
    damaged.parent.mkdir();damaged.write_text('{invalid json', encoding='utf-8')
    result = agents.list()
    assert len(result['active']) == 1 and result['unavailable'] == 1


def test_polling_reuses_unchanged_history_and_refreshes_changed_work(tmp_path):
    agents = AgentTasks(tmp_path)
    task = save_task(agents, '1', 'running', phase='讀取來源')
    agents.list()
    with patch('interior.workbench.agent_runtime.service.read_json', side_effect=AssertionError('unchanged records must be cached')):
        assert agents.list()['active'][0]['phase'] == '讀取來源'
    task.update(status='passed', finished_at='2026-10-25T12:00:00+00:00')
    write_json(agents.root / task['id'] / 'task.json', task)
    assert agents.list()['active'] == [] and agents.list()['history'][0]['status'] == 'passed'


def test_submission_metadata_is_saved_without_starting_extra_work(tmp_path):
    agents = AgentTasks(tmp_path)
    with patch('interior.workbench.agent_runtime.service.threading.Thread') as thread:
        first = agents.start('plan_semantics', payload=dict(site=dict(confirmed_answers=[
            dict(question=dict(label='Q7', title='合成窗戶用途'), answer='窗戶')
        ])), identifier='a' * 32)
        repeated = agents.start('plan_semantics', identifier='a' * 32)
    assert thread.call_count == 1 and first == repeated
    assert first['activity']['title'] == '依疑點答覆複核平面'
    assert first['activity']['items'] == ['Q7 · 合成窗戶用途']
    assert first['phase'] == '等待 Agent 工作槽' and first['phase_started_at']


@pytest.mark.parametrize('fail', [False, True])
def test_runtime_progress_and_terminal_status_remain_visible(tmp_path, fail):
    agents = AgentTasks(tmp_path)
    task = save_task(agents, '1', 'queued')
    observed = []
    class Runtime:
        def __init__(self, directory): pass
        def status(self):
            return dict(authenticated=True, auth_type='chatgpt', version='synthetic', models=[dict(id='model', isDefault=True)])
        def run(self, prompt, **kwargs):
            observed.append(agents.list()['active'][0])
            kwargs['on_event'](dict(method='item/completed', params={}))
            if fail:
                raise ValueError('合成模型拒絕')
            return dict(text='STUDIO_READY')
        def close(self): pass
    with patch('interior.workbench.agent_runtime.service.CodexRuntime', Runtime):
        task.update(kind='connection', model=None)
        agents._run(task, {})
    final = agents.list()['history'][0]
    assert observed[0]['status'] == 'running' and observed[0]['started_at']
    assert len(observed[0]['phase_history']) == 2
    assert final['status'] == ('failed' if fail else 'passed')
    assert final['finished_at'] and final['last_activity_at'] and final['model'] == 'model'
    if fail: assert final['error'] == '合成模型拒絕'


def test_phase_history_is_bounded_and_does_not_duplicate_same_phase():
    task = {}
    for i in range(25): record_phase(task, str(i))
    started = task['phase_started_at']
    record_phase(task, '24')
    assert len(task['phase_history']) == 20 and task['phase_history'][0]['phase'] == '5'
    assert task['phase_started_at'] == started


def test_late_model_event_cannot_erase_stop_request(tmp_path):
    agents = AgentTasks(tmp_path)
    task = save_task(agents, '1', 'queued')
    class Runtime:
        def __init__(self, directory): pass
        def status(self):
            return dict(authenticated=True, auth_type='chatgpt', version='synthetic', models=[dict(id='model', isDefault=True)])
        def run(self, prompt, **kwargs):
            agents.stop(task['id'])
            kwargs['on_event'](dict(method='item/completed', params={}))
            assert agents.get(task['id'])['status'] == 'stopping'
            return dict(text='STUDIO_READY')
        def stop(self): pass
        def close(self): pass
    task.update(kind='connection', model=None)
    with patch('interior.workbench.agent_runtime.service.CodexRuntime', Runtime):
        agents._run(task, {})
    assert agents.list()['history'][0]['status'] == 'stopped'


def test_restart_retains_interruption_without_resubmitting(tmp_path):
    first = AgentTasks(tmp_path)
    pending = save_task(first, '1', 'running', phase='等待原圖複核')
    with patch('interior.workbench.agent_runtime.service.threading.Thread') as thread:
        restarted = AgentTasks(tmp_path)
    assert not thread.called
    result = restarted.list()
    assert result['active'] == [] and result['history'][0]['status'] == 'interrupted'
    assert result['history'][0]['phase'] == pending['phase'] and result['history'][0]['finished_at']


def test_http_list_is_readonly_and_pagination_is_validated(tmp_path):
    with patch.object(Jobs, 'loop', return_value=None):
        app = create_app(tmp_path)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            agents = app.state.studio_agents
            save_task(agents, '1', 'passed')
            with patch.object(agents, 'start', side_effect=AssertionError('no submission')), patch.object(agents, 'status', side_effect=AssertionError('no connection')):
                response = client.get('/api/studio/agent/tasks?history_limit=1')
                assert response.status_code == 200 and response.json()['history_total'] == 1
                assert client.get('/api/studio/agent/tasks?history_offset=1').json()['history'] == []
                assert client.get('/api/studio/agent/tasks?history_limit=201').status_code == 422
                assert client.get('/api/studio/agent/tasks?history_offset=-1').status_code == 422
