"""Read-only, bounded descriptions of submitted Agent work."""
from ..storage import now


TITLES = {
    'plan_semantics': '判讀平面用途與牆門窗',
    'plan_image': '辨識圖片平面', 'plan_refine': '依答覆修正圖片平面',
    'layout_design': '規劃家具與動線', 'cad_experience_batch': '整理修正經驗',
    'asset_match': '搜尋家具／材質候選', 'asset_batch': '批次搜尋家具／材質',
    'asset_generate': '建立概念家具', 'asset_adjust': '修正家具模型',
    'asset_review': '複核配置結果', 'object_specs': '整理物件規格',
    'fixture_lighting': '依現有燈具建立光源',
    'fixture_install': '檢查燈具安裝', 'door_design': '修正門的設定',
    'editor_viewpoint': '修正觀看點', 'material': '提出材質候選',
    'connection': '測試 Agent 連線', 'vision': '測試 Agent 看圖',
    'tool': '測試 Agent 工具', 'browser': '測試 Agent 瀏覽器操作',
}
ACTIVE = {'queued', 'running', 'stopping'}
SUMMARY_FIELDS = (
    'id', 'kind', 'status', 'model', 'created_at', 'started_at', 'finished_at',
    'updated_at', 'last_activity_at', 'phase_started_at', 'phase', 'error',
    'activity', 'phase_history',
)


def describe(kind, payload):
    site = payload.get('site') or {}
    context = payload.get('experience_context') or {}
    title = TITLES.get(kind, 'Agent 工作')
    items = []
    if kind == 'plan_semantics':
        batch = site.get('correction_batch') or {}
        if batch:
            title = '批次修改平面物件'
            items = [i.get('title') or i.get('id') for i in batch.get('items', [])]
        elif site.get('feedback_batch'):
            title = '局部複核所選疑點'
            items = [i.get('title') or i.get('id') for i in site['feedback_batch'].get('items', [])]
        else:
            answers = site.get('confirmed_answers', []) + site.get('user_source_reviews', [])
            if answers:
                title = '依疑點答覆複核平面'
                items = [
                    ' · '.join(str(v) for v in (a.get('question', {}).get('label'), a.get('question', {}).get('title')) if v)
                    for a in answers
                ]
    elif kind == 'asset_batch':
        items = [i.get('name') or i.get('task_id') for i in payload.get('targets', [])]
    elif payload.get('object_id'):
        items = [payload['object_id']]
    return dict(
        title=title,
        project_id=context.get('project') or payload.get('project_id') or site.get('project_id'),
        plan_id=context.get('plan') or site.get('plan_id'),
        items=list(dict.fromkeys(str(i)[:160] for i in items if i))[:40],
    )


def record_phase(task, phase):
    timestamp = now()
    if task.get('phase') != phase:
        task['phase_started_at'] = timestamp
        task['phase_history'] = [*task.get('phase_history', []), dict(phase=phase, at=timestamp)][-20:]
    task.update(phase=phase, updated_at=timestamp, last_activity_at=timestamp)


def summary(task):
    return {key: task[key] for key in SUMMARY_FIELDS if key in task}
