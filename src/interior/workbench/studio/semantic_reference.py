"""Read hash-bound, case-owned reference findings; never infer semantics from a mesh bbox."""
import hashlib
import json
import copy
import math
from pathlib import Path


def load(site):
    """Verify the case-owned proof and every immutable authority source before use."""
    record=site.get('reference_evidence')
    if not record:return None
    from .cad_candidates import source_hash
    data=Path(record['path']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('比對紀錄雜湊不符')
    proof=json.loads(data)
    if proof['version']!=1 or proof['source_hash']!=source_hash(site) or proof['source_revision']!=site['reference_revision']:
        raise ValueError('比對紀錄與目前圖面／尺度／版本不符')
    if not proof['reference_sources']:raise ValueError('缺少參考模型來源')
    for source in proof['reference_sources']:
        with Path(source['path']).open('rb') as handle:
            if hashlib.file_digest(handle,'sha256').hexdigest()!=source['sha256']:raise ValueError('參考模型雜湊不符')
    return proof


def resolve(site,candidate,proof):
    """Apply only explicitly authorized, hash-bound model measurements, atomically."""
    corrections=(proof or {}).get('corrections',[])
    if not corrections:return []
    if proof.get('authority',{}).get('mode')!='user_designated_model':raise ValueError('模型優先修正缺少使用者指定基準')
    if not proof['authority'].get('instruction'):raise ValueError('缺少使用者指定原文')
    result=copy.deepcopy(candidate);records=[]
    for correction in corrections:
        collection=correction['collection'];identifier=correction['id'];values=correction['values']
        if collection=='floor_outline':
            if site.get('floor_locked',True):raise ValueError('地板範圍已確認，模型參考不能自動覆寫')
            row=result.get('floor_outline')
            allowed={'points','holes'}
        elif collection in ('elements','drawing_objects'):
            row=next((r for r in result[collection] if r['id']==identifier),None)
            allowed={'points','base','height','thickness'} if collection=='elements' else {'model_dimensions'}
            if row and row.get('source_binding')!=correction.get('expected_binding'):raise ValueError('模型修正目標來源綁定已變更：'+identifier)
        else:raise ValueError('模型修正集合不支援')
        if not row or set(values)-allowed:raise ValueError('模型修正目標或欄位不符：'+identifier)
        confirmation=correction.get('user_confirmation')
        if confirmation:
            source=dict(path=confirmation.get('path'),sha256=confirmation.get('sha256'))
            if source not in proof.get('reference_sources',[]) or not confirmation.get('statement'):
                raise ValueError('人工尺寸／收邊答覆缺少已綁定的來源證據')
        if not (correction.get('model_objects') or confirmation) or not correction.get('reason'):raise ValueError('模型修正缺少可追溯物件與理由')
        if collection=='drawing_objects' and row.get('category')!='beam':raise ValueError('模型梁尺寸只能對應梁圖樣')
        if collection=='floor_outline' and row.get('holes',[]) not in [correction.get('original_holes',[]),values.get('holes',[])]:raise ValueError('既有地板孔洞已變更，不能由舊模型修正覆寫')
        original={k:copy.deepcopy(row.get(k)) for k in values}
        row.update(copy.deepcopy(values))
        if collection=='elements':
            if len(row['points'])!=2 or any(not math.isfinite(x) for p in row['points'] for x in p):raise ValueError('模型牆窗軸線無效')
            if not .1<=row['height']<=5 or not 0<=row['base']<=4 or not .001<=row['thickness']<=1:raise ValueError('模型尺寸超出支援範圍')
            row.setdefault('derivation',{})
            row['derivation']=dict(row.get('derivation') or {},reference_correction=dict(evidence_sha256=site['reference_evidence']['sha256'],model_objects=correction.get('model_objects',[]),values=values))
        if collection=='drawing_objects':
            dims=row['model_dimensions']
            dims.setdefault('height',None)
            if not 0<=dims['base']<=4 or (dims['height'] is not None and not .01<=dims['height']<=5) or dims['datum']!='model_finish_floor':raise ValueError('模型梁標高／深度無效')
        record=dict(id=identifier,collection=collection,original=original,resolved=values,model_objects=correction.get('model_objects',[]),reason=correction['reason'],support_lines=correction.get('support_lines',[]))
        if confirmation:record['user_confirmation']=copy.deepcopy(confirmation)
        records.append(record)
    candidate.clear();candidate.update(result)
    return records


def inspect(site, candidate, proof=None):
    """Keep independent reference disagreements blocking through reopen and adoption."""
    record=site.get('reference_evidence')
    if not record:
        if any(r.get('model_dimensions') for r in candidate.get('drawing_objects',[])):
            return [dict(id='reference-missing-dimensions',code='reference:integrity',check='source',message='梁高度缺少經驗證的模型依據',object_ids=[],source_ids=[],box=None)]
        return []
    from .semantic_diagnostics import stable_id
    def issue(code,check,message,ids=(),sources=(),box=None):
        return dict(id=stable_id('reference:'+code,ids or sources or [code]),code='reference:'+code,
                    check=check,message=message,object_ids=list(ids),source_ids=list(sources),box=box)
    try:
        proof=proof if proof is not None else load(site)
        result=[]
        approved={r['id']:{'height':None,**r['values']['model_dimensions']} for r in proof.get('corrections',[]) if r['collection']=='drawing_objects' and 'model_dimensions' in r['values']}
        for row in candidate.get('drawing_objects',[]):
            if row.get('model_dimensions') and approved.get(row['id'])!=row['model_dimensions']:
                result.append(issue('dimensions','geometry',row['name']+' 梁尺寸與模型依據不符',[row['id']],row['source_ids']))
            if row.get('model_dimensions') and row['model_dimensions'].get('height') is None:
                matching=next((f for f in proof['findings'] if f.get('type')=='unresolved' and f.get('missing_dimension')=='height' and row['id'] in f.get('object_ids',[])),{})
                if not matching:
                    pts=[p for g in site.get('geometry',[]) if g['id'] in row['source_ids'] for p in g.get('points',[])]
                    bounds=[min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)] if pts else None
                    result.append(issue('beam-depth','geometry',row['name']+' 梁底淨高已保存；梁深尚須確認，不以天花面推算',[row['id']],row['source_ids'],bounds))
        for finding in proof['findings']:
            if finding['type']=='prohibited_role':
                for row in candidate.get('elements',[]):
                    refs={r['id'] for r in (row.get('source_binding') or {}).get('refs',[])}
                    if row.get('role') in finding['roles'] and refs.intersection(finding['source_ids']):
                        result.append(issue(finding['id'],'geometry',row['name']+' '+finding['reason'],[row['id']],finding['source_ids'],finding.get('box')))
            elif finding['type']=='unresolved':
                result.append(issue(finding['id'],finding['check'],finding['reason'],finding.get('object_ids',[]),finding['source_ids'],finding.get('box')))
            else:raise ValueError('不支援的參考判斷種類')
        return result
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return [issue('integrity','source','參考模型證據無法驗證：'+str(exc))]
