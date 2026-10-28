"""Versioned user corrections on a source drawing, separate from adopted design."""
import math
from pathlib import Path
from typing import Literal
from uuid import uuid4

from PIL import Image,ImageDraw,ImageFont
from pydantic import Field
from .models import Strict
from ..storage import Conflict,read_json,write_json,now
from .service import digest


class CorrectionMark(Strict):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    kind:Literal['box','line','text']
    points:list[tuple[float,float]]=Field(min_length=1,max_length=2)
    text:str=Field(default='',max_length=500)


class CorrectionItem(Strict):
    id:str=Field(pattern=r'^cor-[a-f0-9]{32}$')
    title:str=Field(min_length=1,max_length=120)
    comment:str=Field(default='',max_length=3000)
    marks:list[CorrectionMark]=Field(default_factory=list,max_length=50)
    target_id:str|None=Field(default=None,max_length=120)
    target_kind:Literal['object','question','correction']|None=None
    mode:Literal['object','region']|None=None
    target_domain:Literal['objects','plan']|None=None


class SaveCorrections(Strict):
    base_revision:str
    source_task_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    correction_revision:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    items:list[CorrectionItem]=Field(default_factory=list,max_length=40)


class MarkResult(Strict):
    mark_id:str
    status:Literal['corrected','no_change','needs_confirmation','unresolved']
    expected_kind:Literal['wall','column','wall_junction','door','window','furniture','room','floor','lighting','drawing']
    object_ids:list[str]=Field(default_factory=list,max_length=100)
    summary:str=Field(min_length=1,max_length=1500)


class CorrectionResult(Strict):
    id:str=Field(pattern=r'^cor-[a-f0-9]{32}$')
    status:Literal['corrected','no_change','needs_confirmation','unresolved']
    summary:str=Field(min_length=1,max_length=1500)
    mark_results:list[MarkResult]=Field(default_factory=list,max_length=50)


def draft_folder(service,project,plan,revision):
    # Revision comes from the application's current packet, never a request path.
    return service.folder(project,plan)/'corrections'/revision


def get_drafts(service,project,plan):
    packet=service.plans.current(project,plan)
    path=draft_folder(service,project,plan,packet['revision'])/'current.json'
    return read_json(path) if path.exists() else dict(revision=None,source_revision=packet['revision'],source_task_id=None,items=[])


def confirmed_vertical_updates(service, project, record, plan=None):
    """Only immutable, user-confirmed source records authorize height changes."""
    approval=record['site'].get('dimension_confirmation') or {}
    if not approval and plan:
        from .cad_candidates import same_source
        ancestor=record;seen=set()
        for _ in range(64):
            identifier=(ancestor['site'].get('previous_review') or {}).get('task_id','')
            if not identifier or identifier in seen:break
            import re
            if not re.fullmatch('[a-f0-9]{32}',identifier):break
            seen.add(identifier);path=service.folder(project,plan)/'runs'/identifier/'request.json'
            if not path.exists():break
            ancestor=read_json(path)
            if ancestor['source_revision']!=record['source_revision'] or not same_source(ancestor['site'],record['site']):break
            approval=ancestor['site'].get('dimension_confirmation') or {}
            if approval:break
    relative=approval.get('path','')
    if not relative:return {}
    root=service.studio.root(project).resolve()
    path=(root/relative).resolve()
    if not path.is_relative_to(root/'workflows') or not path.is_file():return {}
    if digest(path)!=approval.get('sha256'):return {}
    saved=read_json(path)
    if saved.get('source_revision')!=record['source_revision'] or saved.get('confirmed_by')!='user':return {}
    source=saved.get('user_source') or {}
    user_path=(root/source.get('path','')).resolve()
    if not user_path.is_relative_to(root/'sources') or not user_path.is_file() or digest(user_path)!=source.get('sha256'):return {}
    native=record['site'].get('native_dwg') or {}
    if saved.get('original_sha256')!=native.get('source_sha256'):return {}
    record['site']['dimension_confirmation']=copy_approval=dict(approval)
    copy_approval['updates']=saved.get('vertical_updates',{})
    return saved.get('vertical_updates',{})


def handoff_geometry_intact(baseline, live, updates):
    """Keep Q/M history across evidenced vertical edits, never footprint edits."""
    objects={n['id']:n for n in live.get('elements',[])}
    for old in baseline.get('elements',[]):
        current=objects.get(old['id'])
        if not current:return False
        for key in ('points','closed','role','height','base','thickness','host_id','category'):
            if current.get(key)==old.get(key):continue
            allowed=updates.get(old['id'],{}).get(key,{}) if key in ('height','base') else {}
            if allowed!={'before':old.get(key),'after':current.get(key)}:return False
    return True


def correction_states(service,project,plan,record,task):
    """Bind completion to each immutable item, retaining unrelated batch results.

    Read only the active preview lineage. A later attempt supersedes an older
    result for that item, even if it failed; full rereads and changed sources
    break the lineage. No GET writes history or publishes experience cards.
    """
    from .cad_candidates import fingerprint,source_hash,same_source
    saved=get_drafts(service,project,plan)
    if saved['source_revision']!=record['source_revision']:return []
    remaining={i['id']:i for i in saved['items']};states=[];seen=set()
    revision=record['source_revision'];original=source_hash(record['site']);graph=record['site'].get('source_graph_version')
    current=record;report=task.get('semantic_report',{});status=task.get('status')
    vertical_updates=confirmed_vertical_updates(service,project,record,plan)
    for _ in range(64):
        if current['id'] in seen or current['source_revision']!=revision or current['site'].get('source_graph_version')!=graph or not same_source(current['site'],record['site']):break
        seen.add(current['id']);batch=current['site'].get('correction_batch')
        if not batch:
            if current['site'].get('feedback_version') and current['site'].get('feedback_batch'):
                previous=current['site'].get('previous_review',{});identifier=previous.get('task_id','')
                import re
                if not re.fullmatch('[a-f0-9]{32}',identifier):break
                path=service.folder(project,plan)/'runs'/identifier/'request.json'
                if not path.exists():break
                current=read_json(path);report=previous.get('report',{});status='passed'
                continue
            # A source-bound additive handoff is not a full reread. Retain
            # completed M items only while every existing geometry is intact.
            previous=current['site'].get('previous_review',{})
            baseline=previous.get('candidate',{});live=task.get('candidate') or {}
            intact=handoff_geometry_intact(baseline,live,vertical_updates)
            identifier=previous.get('task_id','')
            import re
            if not current['site'].get('handoff_requested') or not intact or not re.fullmatch('[a-f0-9]{32}',identifier):break
            path=service.folder(project,plan)/'runs'/identifier/'request.json'
            if not path.exists():break
            current=read_json(path);report=previous.get('report',{});status='passed'
            continue
        snapshot=draft_folder(service,project,plan,revision)/'revisions'/f"{batch['draft_revision']}.json"
        if snapshot.exists():
            existing={i['id'] for i in read_json(snapshot)['items']}
            remaining={key:value for key,value in remaining.items() if key in existing}
        outcomes={r['id']:r for r in report.get('corrections',[])}
        for item in batch['items']:
            if item['id'] not in remaining:continue
            present=remaining.pop(item['id'])
            outcome=outcomes.get(item['id']) if status=='passed' else None
            state=outcome or dict(id=item['id'],status='unresolved',summary='本次修正尚未通過檢查',preview_ready=False)
            if outcome and outcome.get('object_fingerprints'):
                from .semantic_feedback import outcome_still_current
                if not outcome_still_current(outcome,task.get('candidate') or {},task.get('yolo_review'),record['site']):
                    state=dict(state,status='unresolved',preview_ready=False,summary='此修正的物件已在後續反饋變更，請重新核對')
            from .correction_regions import verify_regions,explicit_wall
            if outcome and explicit_wall(item) and not record['site'].get('feedback_version'):
                checks,issues=verify_regions(record['site'],task.get('candidate') or {},item,state,strict=bool(batch.get('verification_version')))
                state=dict(state,mark_checks=checks)
                if issues:state.update(status='unresolved',preview_ready=False,summary='逐標註複核未完成：'+'；'.join(issues))
            states.append(dict(state,item_snapshot=item,review_id=current['id'],current=fingerprint(present)==fingerprint(item)))
        if not remaining:break
        previous=current['site'].get('previous_review',{});identifier=previous.get('task_id','')
        import re
        if not re.fullmatch('[a-f0-9]{32}',identifier):break
        path=service.folder(project,plan)/'runs'/identifier/'request.json'
        if not path.exists():break
        current=read_json(path);report=previous.get('report',{});status='passed'
    return states


def validate_marks(items,view):
    if len({item.id for item in items})!=len(items):raise ValueError('修正項識別碼重複')
    if sum(len(item.marks) for item in items)>100:raise ValueError('修正草稿最多100筆圖上標註')
    seen=set()
    for item in items:
        if not item.title.strip():raise ValueError('請填寫修正項名稱')
        for mark in item.marks:
            if mark.id in seen:raise ValueError('修正標註識別碼重複')
            seen.add(mark.id)
            if len(mark.points)!=(1 if mark.kind=='text' else 2):raise ValueError('文字需要一個位置，方框及線條需要兩端點')
            if mark.kind=='text' and not mark.text.strip():raise ValueError('圖上文字不可空白')
            if mark.kind!='text' and math.dist(*mark.points)<1e-6:raise ValueError('修正標註需要不同端點')
            if mark.kind=='box' and any(abs(mark.points[0][k]-mark.points[1][k])<1e-6 for k in (0,1)):raise ValueError('方框需要寬度及高度')
            for x,y in mark.points:
                px=view['pad']+(x-view['bounds'][0])*view['scale'];py=view['pad']+(view['bounds'][3]-y)*view['scale']
                if not all(math.isfinite(v) for v in (x,y,px,py)) or not (0<=px<=view['width'] and 0<=py<=view['height']):raise ValueError('修正標註超出來源圖面')


def save_drafts(service,project,plan,body):
    with service.studio.store.lock:
        packet=service.plans.current(project,plan)
        if packet['revision']!=body.base_revision:raise Conflict('平面已更新，修正草稿不能覆蓋新版')
        source=service.get(project,plan,body.source_task_id)
        if source['source_revision']!=packet['revision']:raise Conflict('修正草稿引用舊版來源，請重新核對')
        root=service.studio.root(project)
        for entry in [packet['source'],*([packet['source']['original']] if packet['source'].get('original') else [])]:
            if digest(root/entry['path'])!=entry['sha256']:raise Conflict('原始圖面已變動，不能保存到舊版草稿')
        previous=get_drafts(service,project,plan)
        if previous['revision']!=body.correction_revision:raise Conflict('修正草稿已在其他視窗更新，請重新開啟')
        validate_marks(body.items,source['site']['source_view'])
        saved=dict(revision=uuid4().hex,source_revision=packet['revision'],source_task_id=body.source_task_id,origin=source['site']['origin'],factor=source['site']['factor'],items=[i.model_dump(mode='json',exclude_none=True) for i in body.items],created_at=now())
        folder=draft_folder(service,project,plan,packet['revision'])
        write_json(folder/'revisions'/f"{saved['revision']}.json",saved);write_json(folder/'current.json',saved)
        (folder.parent/'README.md').write_text('# 修正草稿\n\n所有者：本案。依平面修訂分目錄保存來源任務、公尺XY標註與不可變草稿修訂；current.json是同版最近草稿。歷次批次任務引用確切快照，不因後續修改而改寫。圖上方框／線／文字為意見，不是已採用牆門窗。不可當作可丟棄快取；新平面使用新目錄，不覆寫舊確認。\n',encoding='utf-8')
        return saved


def batch_snapshot(service,project,plan,body,site,previous):
    ids=body.correction_ids
    if not ids:
        continuation=body.mode=='review' and body.use_object_recognition is False
        if body.correction_revision or body.base_review_id and not (continuation or body.mode=='feedback' and body.question_ids):raise ValueError('請選擇要批次修正的項目')
        return None
    if len(set(ids))!=len(ids):raise ValueError('批次修正項重複')
    if not previous or previous['id']!=body.base_review_id or previous['source_revision']!=body.base_revision or not previous['task'].get('candidate'):raise Conflict('判讀預覽已更新，請重新開啟後選擇修正項')
    saved=get_drafts(service,project,plan)
    if not body.correction_revision or saved['revision']!=body.correction_revision or saved['source_revision']!=body.base_revision:raise Conflict('修正草稿版本已更新，請保存後重試')
    if saved['origin']!=site['origin'] or saved['factor']!=site['factor']:raise Conflict('來源座標系已變動，請重新核對修正標註')
    source=service.get(project,plan,saved['source_task_id'])
    if not site.get('source_is_image') and source['site'].get('source_graph_version')!=site.get('source_graph_version'):raise Conflict('來源讀取版本已變動，請重新核對並保存修正標註')
    items={item['id']:item for item in saved['items']}
    if any(key not in items for key in ids):raise ValueError('選取了不存在的修正項')
    selected=[items[key] for key in ids]
    if any(not i['comment'].strip() and not i['marks'] for i in selected):raise ValueError('選取的修正項尚未填寫意見或圖上標註')
    from .correction_regions import VERSION
    return dict(verification_version=VERSION,draft_revision=saved['revision'],source_task_id=saved['source_task_id'],base_review_id=previous['id'],selected_ids=ids,items=selected,item_labels={item['id']:f'M{index+1}' for index,item in enumerate(saved['items']) if item['id'] in ids})


def draw_batch(source,view,batch,folder):
    image=Image.open(source).convert('RGB');draw=ImageDraw.Draw(image)
    font=ImageFont.load_default(size=20)
    for path in ['C:/Windows/Fonts/msjh.ttc','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if Path(path).is_file():font=ImageFont.truetype(path,20);break
    def xy(p):return (view['pad']+(p[0]-view['bounds'][0])*view['scale'],view['pad']+(view['bounds'][3]-p[1])*view['scale'])
    for index,item in enumerate(batch['items']):
        for mark_index,mark in enumerate(item['marks'],1):
            points=[xy(p) for p in mark['points']]
            if mark['kind']=='box':
                a,b=points;draw.rectangle([min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])],outline='#c02d87',width=4)
            elif mark['kind']=='line':draw.line(points,fill='#c02d87',width=4)
            else:draw.text(points[0],mark['text'],font=font,fill='#9c1265',stroke_width=1,stroke_fill='white')
            label=batch.get('item_labels',{}).get(item['id'],f'M{index+1}')
            if len(item['marks'])>1:label+=f'.{mark_index}'
            draw.text((points[0][0]+7,points[0][1]-25),f"{label} {item['title']}",font=font,fill='#9c1265',stroke_width=1,stroke_fill='white')
    target=folder/'correction-batch.png';image.save(target)
    return str(target)


def correction_report(site,proposal,repair_errors):
    batch=site.get('correction_batch')
    if not batch:return [],[]
    rows=proposal.get('correction_results',[]);expected=set(batch['selected_ids'])
    if len({r['id'] for r in rows})!=len(rows) or {r['id'] for r in rows}!=expected:return [],['批次修正回報未逐項對應所選修正項，請保留所有項目並回報原因']
    errors=[f"修正項 {r['id']} 尚未完成：{r['summary']}" for r in rows if r['status'] in ('needs_confirmation','unresolved')]
    # A selected correction may fix classification, but cannot silently drop
    # existing furniture from the full preview. Keep its stable ID for review.
    previous=site.get('previous_review',{}).get('candidate',{})
    retained={e['id'] for e in proposal['elements']}
    for item in previous.get('elements',[]):
        if item['role']=='furniture' and item['id'] not in retained:errors.append('批次修正遺漏原有家具：'+item['id'])
    from .correction_regions import verify_regions
    checked=[];items={i['id']:i for i in batch['items']}
    for r in rows:
        checks,issues=verify_regions(site,proposal,items[r['id']],r,strict=bool(batch.get('verification_version')))
        errors.extend(f"修正項 {r['id']} {issue}" for issue in issues)
        checked.append(dict(r,mark_checks=checks,**({'status':'unresolved','summary':r['summary']+'；逐標註未通過：'+'；'.join(issues)} if issues else {}),preview_ready=not issues and not repair_errors and not any(e.startswith('批次修正遺漏') for e in errors) and r['status'] in ('corrected','no_change')))
    return checked,errors
