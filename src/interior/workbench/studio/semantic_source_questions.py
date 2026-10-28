"""Present import warnings as version-bound Qs without accepting them implicitly."""
import hashlib
import json
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely import normalize
from ..storage import Conflict


def label_questions(site, questions):
    """Keep Q numbers stable after an answered question leaves the active list."""
    labels=site.setdefault('question_labels',{})
    used={int(value[1:]) for value in labels.values() if isinstance(value,str) and value.startswith('Q') and value[1:].isdigit()}
    number=max(used,default=0)
    for question in questions:
        if question['id'] not in labels:
            number+=1;labels[question['id']]='Q'+str(number)
        question['label']=labels[question['id']]


def source_questions(packet,site,candidate=None):
    parsed=packet['parsed'];settings=packet['settings'];image=parsed.get('image')
    raw=parsed.get('questions',[]) if image else (parsed.get('cad_preparation') or {}).get('questions',[])
    rows=[];geometry={g['id']:g for g in site['geometry']}
    floors=[candidate['floor_outline']] if candidate and candidate.get('floor_outline') else site['floors']
    def local(p):return [p[0]*site['factor']-site['origin'][0],(image['height']-p[1] if image else p[1])*site['factor']-site['origin'][1]]
    for q in raw:
        if q.get('kind')=='units' or q['id'] in settings.get('reviewed',[]):continue
        floor=q.get('kind')=='floor' or q['id']=='cad-floor-outline'
        refs=q.get('feature_ids',[])
        pts=[p for f in floors for p in f['points']] if floor else [p for key in refs if key in geometry for p in geometry[key]['points']]
        if not pts and refs:
            pts=[local(p) for f in parsed['features'] if f['id'] in refs for p in f['points']]
        # No invented location for an unlocatable import warning.
        box=[min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)] if pts else None
        if box:
            for k in (0,1):
                if box[k+2]-box[k]<.02:box[k]-=.05;box[k+2]+=.05
        target=dict(source_revision=packet['revision'],question_id=q['id'],floor=normalize(unary_union([Polygon(f['points'],f.get('holes',[])) for f in floors])).wkb_hex if floor else None)
        fingerprint=hashlib.sha256(json.dumps(target,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        ask='請核對圖上顯示的地板實際外輪廓：有沒有漏掉室內、平台或陽台，或多延伸到室外？若範圍正確，可回答「地板範圍正確」並勾選已核對；有差異請在圖上標出要增加或排除的位置。紅色虛線框只用來定位疑點，地板輪廓才是本項核對範圍。' if floor else q['text']
        rows.append(dict(id='source-'+q['id'],source_question_id=q['id'],target=fingerprint,title='地板範圍核對' if floor else '來源待核對',ask=ask,reason='匯入檢查尚未確認；填寫或標註不等於接受推定結果。請核對後明確確認，來源及已確認尺寸不變。',source_ids=refs,box=box,located=bool(box),source_review=True))
    return rows


def confirmed_ids(record,questions):
    # Confirmations bind to this exact floor proposal, not every later proposal.
    inherited=record['site'].get('user_source_reviews',[])
    current=record.get('answers',{}).get('source_reviews',[])
    accepted={(r['question']['id'],r['question']['target']) for r in [*inherited,*current] if r.get('confirmed')}
    # A saved current answer replaces an inherited confirmation, including revoke.
    for row in current:
        if not row.get('confirmed'):accepted.discard((row['question']['id'],row['question']['target']))
    return [q['id'] for q in questions if (q['id'],q['target']) in accepted]


def review_rows(record,questions,body,annotations):
    known={q['id']:q for q in questions}
    if not set(body.source_confirmations).issubset(known):raise ValueError('確認引用不存在或已取代的來源疑點')
    if len(set(body.source_confirmations))!=len(body.source_confirmations):raise ValueError('來源疑點確認不可重複')
    if any(body.source_targets.get(key)!=known[key]['target'] for key in body.source_confirmations):raise Conflict('來源候選已變更，請重新核對目前 Q 圖面後再確認；不能把舊範圍的確認套到新候選')
    return [dict(question=q,answer=body.answers.get(q['id'],''),annotations=annotations.get(q['id'],[]),confirmed=q['id'] in body.source_confirmations) for q in questions]
