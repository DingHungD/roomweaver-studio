"""Read-only, source-bound Q history, including completed and superseded answers."""
import copy
import re

from ..storage import read_json
from .cad_candidates import same_source


def question_history(service, project, plan, review_id):
    live=service.get(project,plan,review_id)
    folder=service.folder(project,plan)/'runs'
    labels=live['site'].get('question_labels',{})
    current_questions=[*live['task'].get('semantic_report',{}).get('questions',[]),*live.get('source_questions',[])]
    active={q['id'] for q in current_questions}
    records={};seen=set()

    def remember(question, answer='', annotations=None, **meta):
        key=question['id']
        row=records.setdefault(key,dict(question=copy.deepcopy(question),versions=[]))
        version=dict(question=copy.deepcopy(question),answer=answer,annotations=copy.deepcopy(annotations or []),**meta)
        identity=(question.get('ask'),answer,str(version['annotations']))
        reference={k:v for k,v in meta.items() if v is not None}
        existing=next((v for v in row['versions'] if (v['question'].get('ask'),v['answer'],str(v['annotations']))==identity),None)
        if existing:
            if reference not in existing['references']:existing['references'].append(reference)
        else:
            version['references']=[reference];row['versions'].append(version)

    # Current questions appear first even while their answer is deliberately blank.
    for question in current_questions:
        remember(question,live['answers']['answers'].get(question['id'],''),live['answers'].get('annotations',{}).get(question['id'],[]),review_id=review_id,answer_revision=live['answers']['revision'],created_at=live['answers'].get('created_at',live['created_at']))
    cursor=review_id
    for _ in range(64):
        if cursor in seen or not re.fullmatch('[a-f0-9]{32}',cursor):break
        seen.add(cursor);path=folder/cursor/'request.json'
        if not path.exists():break
        request=read_json(path)
        if request['source_revision']!=live['source_revision'] or not same_source(request['site'],live['site']):break
        result=folder/cursor/'result.json';task=read_json(result) if result.exists() else {}
        known={q['id']:q for q in task.get('semantic_report',{}).get('questions',[]) if isinstance(q,dict)}
        for row in [*request['site'].get('confirmed_answers',[]),*request['site'].get('user_source_reviews',[])]:
            q=row['question'];known.setdefault(q['id'],q)
            remember(q,row.get('answer',''),row.get('annotations',[]),review_id=row.get('source_task',cursor),answer_revision=row.get('answer_revision'),created_at=request.get('created_at'),user_source=row.get('user_source'),confirmed=row.get('confirmed',False))
        for answer_file in [folder/cursor/'answers.json',*sorted((folder/cursor/'answer-revisions').glob('*.json'),reverse=True)]:
            if not answer_file.exists():continue
            saved=read_json(answer_file)
            for source in saved.get('source_reviews',[]):known.setdefault(source['question']['id'],source['question'])
            for key in set(saved.get('answers',{}))|set(saved.get('annotations',{})):
                question=known.get(key)
                if question:remember(question,saved.get('answers',{}).get(key,''),saved.get('annotations',{}).get(key,[]),review_id=cursor,answer_revision=saved.get('revision'),created_at=saved.get('created_at',request.get('created_at')))
        for q in known.values():
            if q['id'] not in records:remember(q,review_id=cursor,created_at=request.get('created_at'))
        cursor=(request['site'].get('previous_review') or {}).get('task_id','')
    rows=[]
    for key,record in records.items():
        versions=record['versions'];current=versions[0] if key in active else next((v for v in versions if v['answer'].strip() or v['annotations']),versions[0])
        q=copy.deepcopy(record['question']);q['label']=labels.get(key,q.get('label','Q'))
        rows.append(dict(**q,answer=current['answer'],annotations=current['annotations'],active=key in active,status='confirmed' if key in live.get('source_confirmations',[]) else 'pending' if key in active else 'resolved',versions=versions))
    return dict(review_id=review_id,source_revision=live['source_revision'],questions=rows)
