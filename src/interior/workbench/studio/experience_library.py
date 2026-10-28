"""Local, explicitly confirmed CAD experiences with bounded multimodal retrieval."""
import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .cad_candidates import fingerprint
from .experience_features import VERSION, similarity
from ..storage import now, read_json, write_json, Conflict


class ExperienceLibrary:
    def __init__(self, root):
        self.root=Path(root)

    @contextmanager
    def connect(self):
        self.root.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.root/'index.sqlite3',timeout=5)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, revision TEXT NOT NULL, arc_flag INTEGER, edge_bin INTEGER, descriptor TEXT NOT NULL, record TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)')
            db.execute('CREATE INDEX IF NOT EXISTS raw_shape ON entries(active,arc_flag,edge_bin)')
            db.execute('CREATE INDEX IF NOT EXISTS raw_complexity ON entries(active,edge_bin)')
            db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS annotation_index USING fts5(id UNINDEXED,tokens)')
            db.execute('CREATE TABLE IF NOT EXISTS examples (entry_id TEXT NOT NULL, sample_id TEXT NOT NULL, edge_bin INTEGER, descriptor TEXT NOT NULL, PRIMARY KEY(entry_id,sample_id))')
            db.execute('CREATE INDEX IF NOT EXISTS example_shapes ON examples(edge_bin)')
            with db:yield db
        finally:db.close()

    def _publish_confirmed(self, record, image):
        """Called only after version-bound, explicit user confirmation."""
        image_bytes=Path(image).read_bytes();image_hash=hashlib.sha256(image_bytes).hexdigest()
        identity=fingerprint(dict(descriptor=record['descriptor'],image=image_hash,interpretation=record['interpretation'],reason=record['reason'],applies=record['applies'],exceptions=record['exceptions']))
        identifier='exp-'+identity[:24]
        with self.connect() as db:
            previous=db.execute('SELECT record,active FROM entries WHERE id=?',(identifier,)).fetchone()
            if previous and previous[1]:return json.loads(previous[0])
            if previous:raise Conflict('相同經驗已停用；請先核對並修正內容，再建立新版本')
            value=dict(record,id=identifier,revision=identity,confirmed_at=now(),confirmation='explicit-user',image_sha256=image_hash,image=f'blobs/{image_hash}.png',active=True)
            path=self.root/value['image'];path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():path.write_bytes(image_bytes)
            write_json(self.root/'entries'/identifier/f'{identity}.json',value)
            feature=value['descriptor']['geometry']
            compact=dict(value['descriptor'],geometry={k:v for k,v in feature.items() if k!='normalized'})
            db.execute('INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,1)',(identifier,identity,feature['arc_flag'],feature['edge_bin'],json.dumps(compact),json.dumps(value,ensure_ascii=False)))
            db.execute('DELETE FROM annotation_index WHERE id=?',(identifier,))
            db.execute('INSERT INTO annotation_index VALUES (?,?)',(identifier,' '.join(value['descriptor']['tokens'])))
        (self.root/'README.md').write_text('# CAD修正經驗庫\n\n所有者：此應用程式工作區，跨案件共用。只有使用者明確確認的局部修正入庫；不是設計採用。index.sqlite3為可由entries重建的搜尋索引，entries及blobs為不可當快取刪除的確認內容與局部圖。草稿留在各案workflows。案例只供比對，不可套用歷史座標、尺寸或來源ID；停用保留歷史。備份整個資料夾。\n',encoding='utf-8')
        return value

    def search(self, descriptor, limit=5):
        started=time.perf_counter();limit=max(1,min(5,limit))
        if not (self.root/'index.sqlite3').exists():return dict(hits=[],library_count=0,examined=0,elapsed_ms=round((time.perf_counter()-started)*1000,3),version=VERSION)
        # Both pools are geometric. The broad pool prevents an ARC/count error
        # in the reader from excluding an otherwise relevant interpretation.
        g=descriptor['geometry']
        with self.connect() as db:
            total=db.execute('SELECT count(*) FROM entries WHERE active=1').fetchone()[0]
            buckets=sorted(range(25),key=lambda n:abs(n-g['edge_bin']))
            selected=[]
            for bucket in buckets:
                selected+=db.execute('SELECT id,descriptor FROM entries WHERE active=1 AND arc_flag=? AND edge_bin=? LIMIT ?',(g['arc_flag'],bucket,256-len(selected))).fetchall()
                if len(selected)>=256:break
            broad=[]
            for bucket in buckets:
                broad+=db.execute('SELECT id,descriptor FROM entries WHERE active=1 AND edge_bin=? LIMIT ?',(bucket,128-len(broad))).fetchall()
                if len(broad)>=128:break
            selected+=broad
            tokens=descriptor['tokens'][:24]
            if tokens:
                expression=' OR '.join('"'+t.replace('"','""')+'"' for t in tokens)
                selected+=db.execute('SELECT e.id,e.descriptor FROM annotation_index f JOIN entries e ON e.id=f.id WHERE annotation_index MATCH ? AND e.active=1 LIMIT 48',(expression,)).fetchall()
        with self.connect() as db:
            selected+=db.execute('SELECT s.entry_id,s.descriptor FROM examples s JOIN entries e ON e.id=s.entry_id WHERE e.active=1 ORDER BY ABS(s.edge_bin-?) LIMIT 128',(g['edge_bin'],)).fetchall()
        pool=list(dict.fromkeys(selected))[:512];ranked=[]
        scores_by_id={}
        best_features={}
        for identifier,features in pool:
            scores=similarity(descriptor,json.loads(features))
            if scores['geometry']<.45 and scores['image']<.7:continue
            if scores['score']<.55:continue
            if identifier not in scores_by_id or scores['score']>scores_by_id[identifier]['score']:
                scores_by_id[identifier]=scores;best_features[identifier]=json.loads(features)
        identifiers=sorted(scores_by_id,key=lambda k:(-scores_by_id[k]['score'],k))[:32]
        if identifiers:
            with self.connect() as db: records=db.execute('SELECT id,record FROM entries WHERE id IN ('+','.join('?' for _ in identifiers)+')',identifiers).fetchall()
            for identifier,raw in records:
                record=json.loads(raw)
                normalized=[dict(g,points=g['points'][:24]) for g in best_features[identifier]['geometry'].get('normalized',record['descriptor']['geometry']['normalized'])[:20]]
                ranked.append(dict(id=identifier,revision=record['revision'],title=record['title'],interpretation=record['interpretation'],mistake=record['mistake'],reason=record['reason'],applies=record['applies'],exceptions=record['exceptions'],scores=scores_by_id[identifier],image=record['image'],image_sha256=record['image_sha256'],geometry=normalized,annotations=record['annotations'][:12]))
        ranked.sort(key=lambda r:(-r['scores']['score'],r['id']))
        # Diversity is applied AFTER category-free retrieval, never as a filter.
        hits=[];answers=set()
        for hit in ranked:
            if hit['interpretation'] not in answers and (not hits or hit['scores']['score']>=ranked[0]['scores']['score']-.15):
                hits.append(hit);answers.add(hit['interpretation'])
            if len(hits)==min(3,limit):break
        for hit in ranked:
            if len(hits)>=limit:break
            if not any(h['id']==hit['id'] for h in hits):hits.append(hit)
        return dict(hits=hits,library_count=total,examined=len(pool),elapsed_ms=round((time.perf_counter()-started)*1000,3),version=VERSION)

    def catalog(self, limit=200, offset=0):
        if not (self.root/'index.sqlite3').exists():return dict(entries=[],total=0)
        with self.connect() as db:
            total=db.execute('SELECT count(*) FROM entries').fetchone()[0]
            rows=db.execute('SELECT record,active FROM entries ORDER BY rowid DESC LIMIT ? OFFSET ?',(max(1,min(200,limit)),max(0,offset))).fetchall()
        return dict(entries=[dict(json.loads(raw),active=bool(active)) for raw,active in rows],total=total)

    def publish_groups(self, groups, provenance):
        """Atomically publish a user-selected batch, retaining every source exemplar."""
        published=[]
        with self.connect() as db:
            # Detect stale merge targets before publishing any member of the batch.
            for group in groups:
                if not group.get('existing_id'):continue
                row=db.execute('SELECT revision,active FROM entries WHERE id=?',(group['existing_id'],)).fetchone()
                if not row or not row[1] or row[0]!=group['existing_revision']:raise Conflict('待合併的經驗已變動，請重新整理批次')
            for group in groups:
                previous=None
                if group.get('existing_id'):
                    previous=json.loads(db.execute('SELECT record FROM entries WHERE id=?',(group['existing_id'],)).fetchone()[0])
                samples=list((previous or {}).get('examples',[]))
                if previous and not samples:samples=[dict(id=previous['id'],descriptor=previous['descriptor'],image=previous['image'],image_sha256=previous['image_sha256'],provenance=previous['provenance'])]
                for sample in group['examples']:
                    if any(s['id']==sample['id'] for s in samples):continue
                    data=Path(sample['source_image']).read_bytes();image_hash=hashlib.sha256(data).hexdigest()
                    image_path=f'blobs/{image_hash}.png';path=self.root/image_path;path.parent.mkdir(parents=True,exist_ok=True)
                    if not path.exists():path.write_bytes(data)
                    samples.append(dict(id=sample['id'],descriptor=sample['descriptor'],image=image_path,image_sha256=image_hash,provenance=sample['provenance']))
                fields={k:group[k] for k in ('title','interpretation','mistake','reason','applies','exceptions')}
                identifier=group.get('existing_id') or 'exp-'+fingerprint(dict(operation=provenance['batch_id'],members=group['member_ids']))[:24]
                first=samples[0];value=dict(fields,id=identifier,descriptor=first['descriptor'],annotations=group.get('annotations',[]),image=first['image'],image_sha256=first['image_sha256'],examples=samples,provenance=provenance,confirmed_at=now(),confirmation='explicit-user-selected-batch',active=True)
                value['revision']=fingerprint(value)
                write_json(self.root/'entries'/identifier/(value['revision']+'.json'),value)
                feature=value['descriptor']['geometry'];compact=dict(value['descriptor'],geometry={k:v for k,v in feature.items() if k!='normalized'})
                db.execute('INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,1)',(identifier,value['revision'],feature['arc_flag'],feature['edge_bin'],json.dumps(compact),json.dumps(value,ensure_ascii=False)))
                db.execute('DELETE FROM annotation_index WHERE id=?',(identifier,))
                db.execute('INSERT INTO annotation_index VALUES (?,?)',(identifier,' '.join(value['descriptor']['tokens'])))
                for sample in samples:db.execute('INSERT OR REPLACE INTO examples VALUES (?,?,?,?)',(identifier,sample['id'],sample['descriptor']['geometry']['edge_bin'],json.dumps(sample['descriptor'])))
                published.append(dict(id=identifier,revision=value['revision'],member_ids=group['member_ids']))
        readme=self.root/'README.md'
        if not readme.exists():readme.write_text('# CAD修正經驗庫\n\n所有者：應用工作區，跨案件共用。僅明確確認或使用者勾選批次入庫後發佈。entries保存不可變版本，blobs以雜湊共用原圖局部，index.sqlite3保存有界檢索索引及多案例描述子。相同問題合併為一項並保留各來源，停用保留歷史；不是設計採用，不可當快取清理。\n',encoding='utf-8')
        return published

    def image_path(self, identifier):
        if not re.fullmatch(r'exp-[a-f0-9]{24}',identifier):raise ValueError('經驗識別碼無效')
        with self.connect() as db: row=db.execute('SELECT record FROM entries WHERE id=?',(identifier,)).fetchone()
        if not row:raise FileNotFoundError('找不到修正經驗')
        record=json.loads(row[0]);path=self.root/record['image']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['image_sha256']:raise Conflict('經驗圖片已變更，請檢查資料庫')
        return path

    def summary(self):
        if not (self.root/'index.sqlite3').exists():return dict(active=0,path=str(self.root))
        with self.connect() as db:count=db.execute('SELECT count(*) FROM entries WHERE active=1').fetchone()[0]
        return dict(active=count,path=str(self.root))

    def states(self, identifiers):
        if not identifiers or not (self.root/'index.sqlite3').exists():return {}
        with self.connect() as db:rows=db.execute('SELECT id,active FROM entries WHERE id IN ('+','.join('?' for _ in identifiers)+')',identifiers).fetchall()
        return {key:bool(active) for key,active in rows}

    def deactivate(self,identifier,revision):
        if not re.fullmatch(r'exp-[a-f0-9]{24}',identifier):raise ValueError('經驗識別碼無效')
        with self.connect() as db:
            row=db.execute('SELECT revision FROM entries WHERE id=?',(identifier,)).fetchone()
            if not row or row[0]!=revision:raise Conflict('經驗版本已變動，請重新開啟')
            write_json(self.root/'entries'/identifier/('deactivated-'+str(time.time_ns())+'.json'),dict(id=identifier,revision=revision,deactivated_at=now()))
            db.execute('UPDATE entries SET active=0 WHERE id=?',(identifier,))
        return dict(id=identifier,active=False)
