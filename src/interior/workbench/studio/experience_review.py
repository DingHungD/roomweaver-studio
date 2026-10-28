"""Case-bound review drafts; publishing is independent of design adoption."""
import copy
import math
import re
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from .models import Strict
from .cad_candidates import fingerprint, extent, source_hash
from .experience_features import select_source, geometry_descriptor, image_descriptor, crop_source, text_tokens
from .experience_library import ExperienceLibrary
from .service import digest
from ..storage import read_json, write_json, Conflict, now


class CreateExperience(Strict):
    base_revision: str
    review_id: str=Field(pattern=r'^[a-f0-9]{32}$')
    kind: Literal['object','correction']='object'
    target_id: str=Field(min_length=1,max_length=100)


class ExperienceFields(Strict):
    draft_revision: str=Field(pattern=r'^[a-f0-9]{32}$')
    title: str=Field(min_length=1,max_length=120)
    interpretation: str=Field(min_length=1,max_length=500)
    mistake: str=Field(default='',max_length=500)
    reason: str=Field(min_length=1,max_length=1500)
    applies: str=Field(min_length=1,max_length=1200)
    exceptions: str=Field(default='',max_length=1200)


class ExperienceAnswer(ExperienceFields):
    confirmed: Literal[True]


class DeactivateExperience(Strict):
    revision: str=Field(pattern=r'^[a-f0-9]{64}$')


def correction_target(item,outcome):
    points=[p for mark in item['marks'] for p in mark['points']]
    if not points:raise ValueError('修正經驗需要圖上位置，請先為修正項標註方框或線條')
    outcome={k:outcome[k] for k in ('id','status','summary','preview_ready','mark_results','mark_checks') if k in outcome and (k not in ('mark_results','mark_checks') or outcome.get('mark_results'))}
    return dict(box=extent(points,.1),source_ids=[],value=dict(item=item,outcome=outcome),title=item['title'],interpretation=outcome['summary'],reason=item['comment'] or outcome['summary'])


def prepare_batch_experiences(payload,candidate,report):
    """Prepare private cards at the worker boundary; never publish or adopt."""
    context=payload.get('experience_context');batch=payload['site'].get('correction_batch')
    if not context or not batch or payload['site'].get('source_is_image'):return None
    output=Path(payload['result_path']).parent
    record=read_json(output/'request.json')
    record['task']=dict(status='passed',candidate=candidate,semantic_report=report)
    outcomes={r['id']:r for r in report.get('corrections',[])}
    results=[]
    for item in batch['items']:
        outcome=outcomes.get(item['id'])
        if not outcome or outcome['status'] not in ('corrected','no_change') or not outcome.get('preview_ready'):
            results.append(dict(target_id=item['id'],title=item['title'],status='skipped',reason=(outcome or {}).get('summary','沒有通過本次逐項檢查')));continue
        try:
            target=correction_target(item,outcome)
            draft=write_target_draft(output.parent.parent/'experience-drafts',record,target,context['project'],context['plan'],'correction',item['id'],output/'source.png',automatic=True)
            results.append(dict(target_id=item['id'],status='confirmed' if draft['confirmed'] else 'draft',draft_id=draft['id'],title=draft['title']))
        except (ValueError,OSError,KeyError) as exc:
            results.append(dict(target_id=item['id'],title=item['title'],status='error',reason=str(exc)))
    result=dict(review_id=record['id'],draft_revision=batch['draft_revision'],items=results)
    write_json(output/'batch-experiences.json',result)
    return result


def write_target_draft(draft_root,record,target,project,plan,kind,target_id,source,automatic=False):
    draft_root=Path(draft_root)
    for path in draft_root.glob('*/draft.json'):
        existing=read_json(path)
        if existing['review_id']==record['id'] and existing['target_kind']==kind and existing['target_id']==target_id and existing['target_hash']==fingerprint(target['value']):return existing
        if automatic and record.get('reconciled_from')==existing['review_id'] and existing['target_kind']==kind and existing['target_id']==target_id and existing['target_hash']==fingerprint(target['value']) and existing['source_hash']==source_hash(record['site']):
            if existing['confirmed']:return existing
            write_json(path.parent/'revisions'/f"{existing['revision']}.json",existing)
            updated=dict(existing,review_id=record['id'],revision=uuid4().hex,reconciled_from_review=existing['review_id'])
            write_json(path,updated)
            return updated
    identifier=uuid4().hex;folder=draft_root/identifier;folder.mkdir(parents=True)
    image=folder/'source.png'
    crop_source(source,record['site']['source_view'],target['box'],image)
    raw=select_source(record['site'],target['box'],target['source_ids'])
    descriptor=dict(geometry=geometry_descriptor(raw),image=image_descriptor(image),tokens=text_tokens(' '.join(t['text'] for t in raw['texts'])))
    value=dict(id=identifier,revision=uuid4().hex,project=project,plan=plan,review_id=record['id'],source_revision=record['source_revision'],source_hash=source_hash(record['site']),target_kind=kind,target_id=target_id,target_hash=fingerprint(target['value']),box=target['box'],descriptor=descriptor,annotations=[t['text'][:300] for t in raw['texts']],title=target['title'],interpretation=target['interpretation'],mistake='',reason=target['reason'],applies='原生幾何、局部圖與附近註解同時符合時參考；需核對相鄰線段與整體用途。',exceptions='不得套用此案座標、尺寸、層名或既有用途至其他案件。',created_at=now(),status='draft',confirmed=False)
    if kind=='object':
        previous=record['site'].get('previous_review')
        for _ in range(8):
            if not previous:break
            old=next((i for i in previous.get('candidate',{}).get('elements',[]) if i['id']==target_id),None)
            if old and (old['name']!=target['title'] or old.get('category')!=target['value'].get('category')):
                value['mistake']=old['name'];value['before_candidate']=old;break
            task=previous.get('task_id','')
            if not re.fullmatch('[a-f0-9]{32}',task):break
            historical=draft_root.parent/'runs'/task/'request.json'
            if not historical.exists():break
            historical=read_json(historical)
            if historical['source_revision']!=record['source_revision']:break
            previous=historical['site'].get('previous_review')
    value['automatic']=automatic
    # Full user feedback and the complete outcome remain in the immutable run.
    value['interpretation']=value['interpretation'][:500]
    value['reason']=value['reason'][:1500]
    if kind=='correction':
        value['correction_revision']=target.get('correction_revision') or (record['site'].get('correction_batch') or {}).get('draft_revision')
        value['correction_status']=target['value']['outcome']['status']
        value['mistake']='原判讀與使用者修正意見不一致；請核對原圖與修正前後結果。' if target['value']['outcome']['status']=='corrected' else '原判讀已符合本次意見，複核後保留；沒有將它記為誤判。'
    value['crop_sha256']=digest(image)
    write_json(folder/'draft.json',value)
    (folder.parent/'README.md').write_text('# 修正經驗待確認草稿\n\n所有者：本案。保存來源版本、局部圖、原生描述子、判讀結果與使用者確認內容。草稿不可被跨案檢索；只有UI明確確認後才複製最小案例至應用工作區shared/knowledge/cad-experience。不是設計採用，不修改原件或尺寸，不當快取清理。\n',encoding='utf-8')
    return value

class ExperienceReview:
    def __init__(self, semantics):
        self.semantics=semantics
        self.library=ExperienceLibrary(semantics.studio.store.workspace/'shared/knowledge/cad-experience')

    def folder(self,project,plan):return self.semantics.folder(project,plan)/'experience-drafts'

    def list(self,project,plan):
        self.semantics.plans.current(project,plan)
        rows=[read_json(p) for p in self.folder(project,plan).glob('*/draft.json')]
        states=self.library.states([r['entry_id'] for r in rows if r.get('entry_id')])
        rows=[dict(r,entry_active=states.get(r.get('entry_id'),False)) for r in rows]
        return dict(drafts=sorted(rows,key=lambda r:r['created_at'],reverse=True),library=self.library.summary())

    def checked_review(self,project,plan,review_id,revision):
        plan_packet=self.semantics.plans.current(project,plan)
        if plan_packet['revision']!=revision:raise Conflict('平面已更新，請重新整理修正經驗')
        root=self.semantics.studio.root(project)
        for source in [plan_packet['source'],*([plan_packet['source']['original']] if plan_packet['source'].get('original') else [])]:
            if digest(root/source['path'])!=source['sha256']:raise Conflict('原件已變動，不能確認舊圖經驗')
        record=self.semantics.get(project,plan,review_id)
        if record['source_revision']!=revision or record['task']['status']!='passed' or not record['task'].get('candidate'):raise Conflict('需要已完成的同版判讀候選，不能從執行中或失敗工作入庫')
        if record['site'].get('source_is_image'):raise ValueError('本版經驗庫需要原生CAD幾何，圖片入口暫不入庫')
        return record

    def target(self,project,plan,review,kind,target_id):
        candidate=review['task']['candidate']
        if kind=='object':
            items=[*candidate['elements'],*candidate['rooms']]
            item=next((i for i in items if i['id']==target_id),None)
            if not item:raise ValueError('找不到對應判讀物件')
            return dict(box=extent(item['points'],.08),source_ids=item['source_ids'],value=item,title=item['name'],interpretation=item['name'],reason=item['evidence'])
        from .semantic_corrections import get_drafts
        drafts=get_drafts(self.semantics,project,plan);item=next((i for i in drafts['items'] if i['id']==target_id),None)
        from .semantic_corrections import correction_states
        state=next((i for i in correction_states(self.semantics,project,plan,review,review['task']) if i['id']==target_id),None)
        if not item or not state or not state['current'] or state['status'] not in ('corrected','no_change') or not state.get('preview_ready'):raise Conflict('此修正項尚無同版成功回報，請先批次修正並預覽')
        return dict(correction_target(item,state),correction_revision=drafts['revision'])

    def create(self,project,plan,body):
        with self.semantics.studio.store.lock:
            record=self.checked_review(project,plan,body.review_id,body.base_revision)
            target=self.target(project,plan,record,body.kind,body.target_id)
            return write_target_draft(self.folder(project,plan),record,target,project,plan,body.kind,body.target_id,self.semantics.folder(project,plan)/'runs'/body.review_id/'source.png')

    def get(self,project,plan,identifier):
        if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('經驗草稿識別碼無效')
        self.semantics.plans.current(project,plan)
        return read_json(self.folder(project,plan)/identifier/'draft.json')

    def save(self,project,plan,identifier,body):
        with self.semantics.studio.store.lock:
            saved=self.get(project,plan,identifier)
            if saved['revision']!=body.draft_revision or saved['confirmed']:raise Conflict('經驗草稿已變動或已入庫，請重新開啟')
            values=body.model_dump(exclude={'draft_revision'})
            if all(saved[k]==v for k,v in values.items()):return saved
            folder=self.folder(project,plan)/identifier
            write_json(folder/'revisions'/f"{saved['revision']}.json",saved)
            updated=dict(saved,**values,revision=uuid4().hex)
            write_json(folder/'draft.json',updated)
            return updated

    def confirm(self,project,plan,identifier,body):
        with self.semantics.studio.store.lock:
            saved=self.get(project,plan,identifier)
            if saved['revision']!=body.draft_revision:raise Conflict('經驗草稿已在其他視窗變動，請重新開啟')
            record=self.checked_review(project,plan,saved['review_id'],saved['source_revision'])
            latest=self.semantics.get(project,plan)
            if latest['id']!=record['id']:
                state=next((r for r in latest['task'].get('correction_states',[]) if r['id']==saved['target_id']),None)
                if saved['target_kind']!='correction' or latest['task']['status']!='passed' or not state or not state['current'] or not state['preview_ready'] or state['review_id']!=record['id']:raise Conflict('目前判讀已更新，請從最新候選重新整理經驗')
            target=self.target(project,plan,record,saved['target_kind'],saved['target_id'])
            if fingerprint(target['value'])!=saved['target_hash'] or source_hash(record['site'])!=saved['source_hash']:raise Conflict('判讀物件或來源已變動，不能確認舊經驗')
            for key in ('title','interpretation','reason','applies'):
                if not getattr(body,key).strip():raise ValueError('請填寫正確判讀、理由與適用條件')
            image=self.folder(project,plan)/identifier/'source.png'
            if digest(image)!=saved['crop_sha256']:raise Conflict('局部圖片已變動，請重新整理經驗並核對')
            entry=self.library._publish_confirmed(dict(title=body.title.strip(),interpretation=body.interpretation.strip(),mistake=body.mistake.strip(),reason=body.reason.strip(),applies=body.applies.strip(),exceptions=body.exceptions.strip(),descriptor=saved['descriptor'],annotations=saved['annotations'],provenance=dict(project=project,plan=plan,review_id=saved['review_id'],source_revision=saved['source_revision'],source_hash=saved['source_hash'],draft=identifier)),image)
            confirmed=dict(saved,**body.model_dump(exclude={'draft_revision','confirmed'}),revision=uuid4().hex,status='confirmed',confirmed=True,entry_id=entry['id'],entry_revision=entry['revision'],entry_active=True,confirmed_at=entry['confirmed_at'])
            write_json(self.folder(project,plan)/identifier/'confirmation.json',confirmed);write_json(self.folder(project,plan)/identifier/'draft.json',confirmed)
            return confirmed

    def search(self,project,plan,identifier):
        saved=self.get(project,plan,identifier)
        return self.library.search(saved['descriptor'])
