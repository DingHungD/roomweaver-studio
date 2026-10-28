"""Source-bound intake supplements; private previews never adopt a design."""
import copy
import json
import math
import re
from pathlib import Path
from uuid import uuid4

from pydantic import Field
from shapely.geometry import Polygon, LineString, Point
from .models import Strict
from ..storage import write_json


class Requirement(Strict):
    id: str
    target_ids: list[str] = Field(min_length=1, max_length=30)
    kind: str = Field(max_length=60)
    text: str = Field(min_length=1, max_length=1200)
    source_ids: list[str] = Field(min_length=1, max_length=30)


class OpeningSpec(Strict):
    element_id: str
    kind: str = Field(pattern='^(single|double|sliding|folding|frame|window|unknown)$')
    hinge: str = Field(default='auto', pattern='^(A|B|auto)$')
    side: str | None = Field(default=None, pattern='^(positive|negative)$')
    source_ids: list[str] = Field(min_length=1, max_length=30)
    evidence: str = Field(min_length=1, max_length=1000)


class FunctionalPart(Strict):
    id: str
    parent_id: str
    name: str
    category: str
    points: list[tuple[float, float]] = Field(min_length=4, max_length=4)
    base: float = Field(default=0, ge=0, le=4)
    height: float = Field(default=.1, gt=.005, le=4)
    source_ids: list[str] = Field(min_length=1, max_length=30)
    evidence: str = Field(min_length=1, max_length=1000)


class DimensionLink(Strict):
    dimension_id: str
    target_ids: list[str] = Field(default_factory=list, max_length=10)
    status: str = Field(pattern='^(matched|reference|unresolved)$')
    reason: str = Field(min_length=1, max_length=500)


class HandoffSpec(Strict):
    requirements: list[Requirement] = Field(default_factory=list, max_length=120)
    openings: list[OpeningSpec] = Field(default_factory=list, max_length=100)
    parts: list[FunctionalPart] = Field(default_factory=list, max_length=100)
    dimensions: list[DimensionLink] = Field(default_factory=list, max_length=200)
    text_dispositions: dict[str, str] = Field(default_factory=dict, max_length=300)
    user_confirmations: str = Field(default='', max_length=6000)


def validate_handoff(site, candidate):
    """Validate references and installation envelopes without changing confirmed geometry."""
    if not candidate.get('handoff'): return []
    h=HandoffSpec.model_validate(candidate['handoff']).model_dump(mode='json')
    candidate['handoff']=h
    elements={e['id']:e for e in candidate['elements']}
    targets=set(elements)|{r['id'] for r in candidate['rooms']}|{s['id'] for k in ('lighting','drawing_objects') for s in candidate.get(k) or []}|{p['id'] for p in h['parts']}
    sources={s['id'] for k in ('geometry','texts','dimensions') for s in site.get(k,[])}
    errors=[]
    if len({p['id'] for p in h['parts']})!=len(h['parts']) or {p['id'] for p in h['parts']}.intersection(set(elements)):errors.append('設備子項識別碼重複或覆蓋既有物件')
    for row in h['requirements']+h['openings']+h['parts']:
        if not set(row['source_ids']).issubset(sources): errors.append('交接引用不存在的原圖來源：'+','.join(sorted(set(row['source_ids'])-sources)))
    for row in h['requirements']:
        if not set(row['target_ids']).issubset(targets):errors.append(row['id']+' 需求未綁定有效物件／區域')
    if len({o['element_id'] for o in h['openings']})!=len(h['openings']):errors.append('門窗交接規格重複')
    for row in h['openings']:
        item=elements.get(row['element_id'])
        if not item or item['role'] not in ('door','window'):errors.append('門窗規格對應無效物件')
        elif item['role']=='window' and row['kind'] not in ('window','unknown'):errors.append('不可將窗規格套成房門')
        elif item['role']=='door' and row['kind']=='window':errors.append('不可將房門規格套成窗')
    if {o['element_id'] for o in h['openings']}!={e['id'] for e in candidate['elements'] if e['role'] in ('door','window')}:errors.append('每個已辨識門窗皆須保留交接規格，未知型式可明示unknown')
    for part in h['parts']:
        parent=elements.get(part['parent_id']);shape=Polygon(part['points'])
        if not parent or parent['role']!='furniture' or not parent['closed']:errors.append(part['name']+' 缺少家具宿主');continue
        if not shape.is_valid or shape.area<1e-5 or shape.convex_hull.area-shape.area>1e-7:errors.append(part['name']+' 功能占位無效');continue
        if not Polygon(parent['points']).buffer(.035).covers(shape):errors.append(part['name']+' 超出原家具範圍')
        # A text label alone is insufficient to invent a device position.
        gs=[g for g in site['geometry'] if g['id'] in part['source_ids']]
        if not gs or not any(LineString(g['points']).distance(shape)<.08 for g in gs if len(g['points'])>1):errors.append(part['name']+' 缺少相鄰原圖幾何定位')
    dims={d['id'] for d in site.get('dimensions',[])}
    if {d['dimension_id'] for d in h['dimensions']}!=dims or len(h['dimensions'])!=len(dims):errors.append('尺寸交接須逐筆說明原尺寸的對應或未定原因')
    for row in h['dimensions']:
        if not set(row['target_ids']).issubset(targets):errors.append('尺寸對應不存在的物件')
        if row['status']=='matched' and not row['target_ids']:errors.append('尺寸聲稱已對應但沒有物件')
        if row['status']=='matched' and row['target_ids']:
            dimension=next((d for d in site['dimensions'] if d['id']==row['dimension_id']),None)
            objects=[elements[t] for t in row['target_ids'] if t in elements]
            if dimension and objects:
                from shapely.ops import unary_union
                shape=unary_union([Polygon(o['points']).boundary if o['closed'] else LineString(o['points']) for o in objects])
                if any(shape.distance(Point(dimension[k]))>.05 for k in ('start','end')):errors.append(row['dimension_id']+' 端點未對應所選物件，應保留reference而非聲稱matched')
    texts={t['id'] for t in site.get('texts',[])}
    linked={s for r in h['requirements'] for s in r['source_ids'] if s in texts}
    linked|={s for k in ('elements','rooms','lighting','drawing_objects') for item in candidate.get(k) or [] for s in item['source_ids'] if s in texts}
    if texts-linked-set(h['text_dispositions']):errors.append('仍有原圖文字未承接或說明用途')
    required={t['id'] for t in site.get('texts',[]) if re.search(r'不做|做天花|保留|需要|不得|咖啡|收納|窗簾|封.*板|平台|不鏽鋼|木皮|磐瓷|無吊櫃|電箱|鑰匙',t['text'])}
    if required-{s for r in h['requirements'] for s in r['source_ids']}:errors.append('明確設計要求不可只放文字略過紀錄：'+','.join(sorted(required-{s for r in h['requirements'] for s in r['source_ids']})))
    if not set(h['text_dispositions']).issubset(texts):errors.append('文字處理紀錄引用不存在的來源')
    return list(dict.fromkeys(errors))


def run_review(client, directory, payload, model, candidate, report, progress, event, validate):
    """Agent supplies a bounded additive patch; all accepted original geometry is locked."""
    site=payload['site'];output=Path(payload['result_path']).parent
    baseline=copy.deepcopy(candidate);last_errors=[]
    instructions='''你是室內CAD交接審查Agent，完成01→02基本模型交接，不做寫實素材。只回JSON增量，不要重寫既有物件。
格式 {summary,add_rooms:[],add_elements:[],add_drawing_objects:[],lighting_updates:[],handoff:{requirements:[],openings:[],parts:[],dimensions:[],text_dispositions:{},user_confirmations:""},questions:[]}。
add_rooms與add_elements完全沿用候選欄位及source_binding契約（來源位置由程式重新推導）；只補原圖確定漏件／廊道，不移動既有牆門窗、家具、尺寸、高度。小於4cm的收邊不是一般牆；不可放大。新增構件不得與既有物件重複。
add_elements.role只能wall|door|window|furniture，不能other；結構收邊用wall，category=wall_junction（不是column），solid_outline只接受wall的column/wall_junction且refs為native_exact_fill。outline只接受原生閉合凸多段線；一般牆用pair；bounds取整個refs幾何外接框，不能以edge裁切。禁止虛構trim類別。
add_drawing_objects沿用{id,name,layer,category,source_ids,evidence}；燈具更新只可修改kind/evidence，須保留ID、名稱、來源。使用者確認優先：不要再問已確認用途，燈具未確定安裝型態可unknown，02再選。
地毯category=rug,layer=decoration；設備layer=equipment；不要將地毯放other。lighting_updates只送{id,kind,evidence}。
handoff.requirements: [{id,target_ids:[現有/新增物件或區域ID],kind,text,source_ids}]，將所有有設計意義的原文（天花做/不做、平台、窗簾盒、材質、保留、收納、禁止吊櫃、照明需求）綁定對象；原文文字不等於定位點。texts中沒有需求的圖題、尺寸標籤等放text_dispositions{id:理由}。已有name引用不能假裝已承接複合需求。
handoff.openings:[{element_id,kind:single|double|sliding|folding|frame|window|unknown,hinge:A|B|auto,side:positive|negative|null,source_ids,evidence}]，每個門窗各一筆。A/B依候選points順序，positive/negative依AB左/右側法向。依原生門弧、直線、註解判斷，不能依房名猜。不確定保留unknown/auto，不改洞口。
handoff.parts:[{id,parent_id,name,category,points:四點矩形公尺局部XY,base,height,source_ids,evidence}]，原圖有的水槽、洗碗機、爐具、油煙機及櫃體功能分區。須在原家具占位內、有幾何佐證，保留整組家具；base/height未知先以合理概念值明示，02適配，不捏造已確認高度。
handoff.dimensions:[{dimension_id,target_ids,status:matched|reference|unresolved,reason}]，原29筆或新圖所有尺寸各一筆。只有端點對到相同幾何才matched，總長/跨段可reference；不改數字或座標。未知端點不是必須叫人回答。
questions沿用原圖定位Q格式，只列真正影響基本平面且無法從原圖判斷的新疑點；不重複地板既有Q、不將未知模型款式/高度當阻擋。現有家具已配置，不新增不存在的床/家具。
這是通用流程，所有判斷必須引用本次來源，不依案件名字。
'''
    for attempt in range(3):
        progress('補齊02交接：區域、設備、門窗與原圖要求' if not attempt else '依交接檢查修正增量提案')
        data=dict(source=site,candidate=baseline,errors=last_errors)
        prior=site.get('previous_review',{}).get('task_id','')
        if re.fullmatch('[a-f0-9]{32}',prior):
            prior_folder=output.parent/prior
            paths=sorted(prior_folder.glob('handoff-pass-*.json'))
            if paths:
                from ..storage import read_json
                data['previous_unaccepted_patch']=read_json(paths[-1])
        # Avoid recursively sending old runs, coverage logs and screenshots as text.
        data['source']={k:v for k,v in site.items() if k in ('geometry','texts','dimensions','origin','factor','user_feedback','confirmed_answers','user_source_reviews')}
        response=client.run(instructions+'\n資料：'+json.dumps(data,ensure_ascii=False,separators=(',',':')),model=model,image=Path(payload['image']),timeout=600,on_event=event)
        try:
            raw=response['text'];patch=json.loads(raw[raw.find('{'):raw.rfind('}')+1]);write_json(output/f'handoff-pass-{attempt+1}.json',patch)
            updated=copy.deepcopy(baseline)
            for key,target in [('add_rooms','rooms'),('add_elements','elements'),('add_drawing_objects','drawing_objects')]:
                known={e['id'] for e in updated.get(target) or []}
                for item in patch.get(key,[]):
                    if item['id'] in known:raise ValueError('增量不得覆寫原有物件 '+item['id'])
                    updated.setdefault(target,[]).append(item);known.add(item['id'])
            lamps={l['id']:l for l in updated.get('lighting') or []}
            for update in patch.get('lighting_updates',[]):
                if update['id'] not in lamps or any(lamps[update['id']].get(k)!=v for k,v in update.items() if k not in ('id','kind','evidence')):raise ValueError('燈具更新範圍不符；僅可變更kind/evidence，其他欄位須保持')
                lamps[update['id']].update({k:v for k,v in update.items() if k in ('kind','evidence')})
            updated['handoff']=patch['handoff']
            updated['handoff']['user_confirmations']='\n'.join(dict.fromkeys(s for s in ((baseline.get('handoff') or {}).get('user_confirmations',''),site.get('user_feedback','')) if s))[:6000]
            updated['questions']+=patch.get('questions',[])
            updated,checked=validate(site,updated)
            if checked['repair_errors']:raise ValueError('；'.join(checked['repair_errors']))
            write_json(output/'handoff-review.json',dict(status='preview',attempt=attempt+1,summary=patch.get('summary',''),requirements=len(updated['handoff']['requirements']),dimensions=len(updated['handoff']['dimensions']),adopted=False))
            return updated,checked
        except (ValueError,KeyError,TypeError) as exc:
            last_errors=[str(exc)];instructions+='\n上一增量提案：'+json.dumps(patch,ensure_ascii=False) if 'patch' in locals() else ''
            write_json(output/'handoff-review.json',dict(status='blocked',attempt=attempt+1,errors=last_errors,adopted=False))
    report=copy.deepcopy(report);report['errors']+=last_errors;report['repair_errors']+=last_errors;report['status']='blocked'
    return baseline,report


def handoff_items(site, candidate):
    """Produce concept-only symbol footprints at source locations, with explicit unknown heights."""
    items=[];geometry={g['id']:g for g in site['geometry']}
    for kind in ('lighting','drawing_objects'):
        for obj in candidate.get(kind) or []:
            # A plan establishes a beam footprint, not its elevation or depth.
            # Keep it in the 2D/handoff record until vertical data is confirmed;
            # never turn it into a furniture block resting on the floor.
            if kind=='drawing_objects' and obj.get('category')=='beam':continue
            pts=[p for key in obj['source_ids'] if key in geometry for p in geometry[key]['points']]
            if not pts:continue
            x0,y0=[min(p[k] for p in pts) for k in (0,1)];x1,y1=[max(p[k] for p in pts) for k in (0,1)]
            if x1-x0<.02:x0-=.01;x1+=.01
            if y1-y0<.02:y0-=.01;y1+=.01
            lamp=kind=='lighting';category=obj.get('kind') if lamp else obj['category']
            base=2.6 if lamp and category in ('ceiling','track','pendant') else 1.4 if lamp and category=='wall' else 0
            height=.06 if lamp else .02 if category=='rug' else 1.8 if '玻璃' in obj['name'] else .1
            point=[(x0+x1)/2,(y0+y1)/2]
            room=min(candidate['rooms'],key=lambda r:Polygon(r['points']).distance(Point(point)))['id']
            items.append(dict(id=obj['id'],name=obj['name'],role='furniture',room_id=room,points=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],closed=True,height=height,base=base,thickness=.04,offset=[0,0],host_id=None,design_asset=None,category=category,editor_kind='lighting' if lamp else obj['layer'],source_ids=obj['source_ids'],dimension_source='estimated',evidence=obj['evidence']))
    return items


def supplement_packet(packet,site,candidate,id_map,raw):
    """Same handoff metadata for private preview and later explicit adoption."""
    semantic=packet['parsed']['intake_semantics'];h=candidate.get('handoff') or {}
    semantic['handoff']=copy.deepcopy(h);semantic['assumptions']=copy.deepcopy(candidate.get('assumptions',[]))
    semantic['dimension_evidence']=copy.deepcopy(site.get('dimensions',[]))
    semantic['id_map']=dict(id_map);semantic['source_origin']=site['origin']
    for element in candidate['elements']:
        feature=next(f for f in packet['parsed']['features'] if f['id']==id_map[element['id']])
        feature['intake_metadata']={k:copy.deepcopy(element.get(k)) for k in ('category','source_ids','evidence')}
        feature['intake_metadata']['semantic_id']=element['id']
        approved=(site.get('dimension_confirmation') or {}).get('updates',{}).get(element['id'],{})
        confirmed={key:change['after'] for key,change in approved.items() if key in ('height','base') and element.get(key)==change.get('after')}
        if confirmed:
            feature['intake_metadata']['confirmed_dimensions']=confirmed
            feature['intake_metadata']['dimension_confirmation']=copy.deepcopy(site['dimension_confirmation'])
    for obj in handoff_items(site,candidate):
        eid='intake-symbol-'+obj['id'];id_map[obj['id']]=eid
        packet['parsed']['features'].append(dict(id=eid,kind='SEMANTIC',layer='furniture',points=[raw(p) for p in obj['points']],closed=True,room_id=obj['room_id'],intake_metadata=dict(obj,semantic_id=obj['id'])))
        packet['settings']['assignments'].append({k:v for k,v in dict(obj,id=eid).items() if k in ('id','name','role','height','base','thickness','offset','host_id','design_asset')})
    semantic['id_map']=dict(id_map)


def private_packet(previous,site,candidate,identifier):
    """Build an unadopted snapshot; never changes current.json or source reviews."""
    packet=copy.deepcopy(previous);factor=site['factor'];origin=site['origin']
    def raw(p):
        x=(p[0]+origin[0])/factor;y=(p[1]+origin[1])/factor
        return [x,site['image_height']-y if site.get('image_height') else y]
    for a in packet['settings']['assignments']:a['role']='ignore'
    from .semantic_evidence import floor_proof
    from .cad_preparation import convex_parts
    shape,errors,_=floor_proof(site,candidate)
    if errors:raise ValueError('預覽地板幾何未通過：'+'；'.join(errors))
    floor_template=next((a for a in previous['settings']['assignments'] if a['role']=='floor'),dict(height=.1,base=0,thickness=.1))
    for i,p in enumerate(convex_parts(shape,1)):
        eid='preview-floor-'+str(i)
        packet['parsed']['features'].append(dict(id=eid,kind='SEMANTIC',layer='floor',points=[raw(p) for p in list(p.exterior.coords)[:-1]],closed=True))
        packet['settings']['assignments'].append(dict(id=eid,name='概念地板',role='floor',height=floor_template['height'],base=floor_template.get('base',0),thickness=floor_template['thickness'],offset=[0,0],host_id=None))
    mapping={e['id']:'preview-'+e['id'] for e in candidate['elements']}
    for e in candidate['elements']:
        eid=mapping[e['id']]
        packet['parsed']['features'].append(dict(id=eid,kind='SEMANTIC',layer=e['role'],points=[raw(p) for p in e['points']],closed=e['closed'],room_id=e['room_id'],source_geometry=e.get('derivation')))
        packet['settings']['assignments'].append(dict(id=eid,name=e['name'],role=e['role'],height=e['height'],base=e['base'],thickness=e['thickness'] if e['role']=='wall' else max(.04,e['thickness']),offset=[0,0],host_id=mapping.get(e.get('host_id')),design_asset=e.get('asset')))
    packet['parsed']['intake_semantics']=dict(rooms=[dict(r,points=[raw(p) for p in r['points']]) for r in candidate['rooms']],door_state=candidate['door_state'],window_state=candidate['window_state'],furniture_state=candidate['furniture_state'],lighting=candidate.get('lighting'),drawing_objects=candidate.get('drawing_objects',[]))
    supplement_packet(packet,site,candidate,mapping,raw)
    # Only this private snapshot may display an unconfirmed floor. Never records a user confirmation.
    packet['parsed']['cad_preparation']=copy.deepcopy(packet['parsed'].get('cad_preparation'))
    if packet['parsed'].get('cad_preparation'):
        packet['parsed']['cad_preparation']['questions']=[q for q in packet['parsed']['cad_preparation'].get('questions',[]) if q['id']!='cad-floor-outline']
    packet['preview_only']=True;packet['preview_review_id']=identifier;packet['revision']='preview-'+identifier
    packet['settings']['intake_review']=dict(purposes=False,structure=False,furniture=False)
    return packet


def compile_handoff(active, parsed, origin):
    """Retain purpose, child grouping, opening controls and deferred requirements in the model input."""
    semantic=parsed.get('intake_semantics') or {};h=semantic.get('handoff') or {};mapping=copy.deepcopy(semantic.get('id_map',{}))
    old_origin=semantic.get('source_origin',origin);delta=[old_origin[k]-origin[k] for k in (0,1)]
    features={f['id']:f for f in parsed['features']}
    for item in active:
        item['intake_metadata']=copy.deepcopy(features.get(item['id'],{}).get('intake_metadata',{}))
        if item['intake_metadata']:
            item['intake_metadata']['dimension_sources']=dict(width='source_geometry',depth='source_geometry',height='concept',base='concept')
            for key,value in item['intake_metadata'].get('confirmed_dimensions',{}).items():
                if key in ('height','base') and item.get(key)==value:item['intake_metadata']['dimension_sources'][key]='user_confirmed'
    for part in h.get('parts',[]):
        parent=next((i for i in active if i['id']==mapping.get(part['parent_id'])),None)
        if not parent:raise ValueError('交接設備缺少宿主家具')
        active.append(dict(id='intake-part-'+part['id'],name=part['name'],role='furniture',room_id=parent.get('room_id'),points=[[p[k]+delta[k] for k in (0,1)] for p in part['points']],closed=True,height=part['height'],base=part['base'],thickness=.04,host_id=None,design_asset=None,offset=[0,0],parent_assembly_id=parent['id'],parent_assembly_name=parent['name'],intake_metadata=dict(part,semantic_id=part['id'],dimension_source='estimated',editor_kind='furniture')))
        mapping[part['id']]='intake-part-'+part['id']
    openings={o['element_id']:o for o in h.get('openings',[])}
    for semantic_id,spec in openings.items():
        item=next((i for i in active if i['id']==mapping.get(semantic_id)),None)
        if item:item['control']=dict(kind=None if spec['kind'] in ('window','unknown') else spec['kind'],hinge=spec['hinge'],side=spec['side'],swing='auto')
    return dict(requirements=copy.deepcopy(h.get('requirements',[])),dimensions=copy.deepcopy(h.get('dimensions',[])),dimension_evidence=copy.deepcopy(semantic.get('dimension_evidence',[])),coordinate_origin_metres=old_origin,model_origin_metres=origin,assumptions=copy.deepcopy(semantic.get('assumptions',[])),user_confirmations=h.get('user_confirmations',''),id_map=mapping)


def model_scene(studio,project,job_id):
    """Read-only 02-compatible scene, also used when explicitly adopting the same package."""
    from .models import Scene
    from ..storage import read_json
    model=studio.model(project,job_id);folder=studio.root(project)/'runs/interior-studio'/job_id
    request=read_json(folder/'request.json');plan=request.get('plan',{})
    groups=studio.groups(project,job_id);notes=[];lights=[]
    for row in plan.get('handoff',{}).get('requirements',[]):notes.append('['+','.join(row['target_ids'])+'] '+row['text'])
    notes+=plan.get('handoff',{}).get('assumptions',[])
    metadata={o['id']:o.get('intake_metadata',{}) for o in model['objects']}
    for group in groups:
        rows=[metadata[k] for k in group['children'] if metadata.get(k)]
        if not rows:continue
        meta=rows[0];ids={r.get('semantic_id') for r in rows};related=[r['text'] for r in plan.get('handoff',{}).get('requirements',[]) if ids.intersection(r['target_ids'])]
        if meta.get('editor_kind') in ('furniture','decor'):group['editor_kind']=meta['editor_kind']
        if meta.get('editor_kind')=='decoration':group['editor_kind']='decor'
        group['intake_metadata']=dict(objects=rows,requirements=related)
        if any(r.get('editor_kind')=='lighting' for r in rows):
            group['object_specification']=dict(purpose='light',front='unknown')
            from .asset_matching import preview_dimensions
            bounds=preview_dimensions(folder/'model.glb',group['children'],return_bounds=True)
            if bounds:
                lo,hi=bounds
                lights.append(dict(id='intake-light-'+group['id'],name=group['name'][:180],kind='AREA',position=[(lo[k]+hi[k])/2 for k in (0,1,2)],power=150,size=.3,enabled=False,locked=False,group_id=group['id'],origin='proposal'))
        group['design_prompt']='；'.join(related)[:2000]
    controls=[dict(item.get('control') or {},opening_id=item['id'],name=item['name']) for item in plan.get('items',[]) if item['role']=='door' and item.get('control')]
    if lights:notes.append('原圖燈具位置與模型已承接；光源預設停用，安裝型態、功率與光色交02確認。')
    return Scene.model_validate(dict(model_id=job_id,intake_handoff=plan.get('handoff',{}),rooms=[dict(id=r['id'],name=r['name']) for r in plan.get('rooms',[])] or [dict(id='interior',name='室內')],objects=[dict(id=o['id'],name=o['name'],room_id=o.get('room_id'),material={}) for o in model['objects']],groups=groups,door_controls=controls,design_notes=notes,lighting_setup=dict(enabled=False,lights=lights))).model_dump(mode='json')


def preview(semantics,project,plan,identifier,body):
    from .plan_import import check_plan
    from .service import digest
    from ..storage import Conflict,read_json
    with semantics.studio.store.lock:
        record=semantics.get(project,plan,identifier);packet=semantics.plans.current(project,plan)
        if packet['revision']!=body.base_revision or record['source_revision']!=body.base_revision:raise Conflict('預覽對應舊版平面')
        if record['task']['status']!='passed' or not record['task'].get('candidate',{}).get('handoff'):raise ValueError('請先完成02交接補齊')
        from .plan_semantics import validate
        candidate,report=validate(record['site'],record['task']['candidate'])
        if report['repair_errors']:raise ValueError('交接仍有幾何或資料錯誤：'+'；'.join(report['repair_errors'][:5]))
        root=semantics.studio.root(project)
        for src in [packet['source'],*([packet['source']['original']] if packet['source'].get('original') else [])]:
            if digest(root/src['path'])!=src['sha256']:raise ValueError('原始圖面已變動')
        private=private_packet(packet,record['site'],candidate,identifier);check=check_plan(private['parsed'],private['settings'])
        if check['errors']:raise ValueError('概念預覽未通過：'+'；'.join(check['errors'][:6]))
        private['check']=check
        folder=semantics.folder(project,plan)/'runs'/identifier
        from .cad_candidates import fingerprint
        signature=fingerprint(private)
        previous_job=folder/'preview-job.json'
        retry='first'
        if previous_job.exists():
            prior=semantics.studio.jobs.get(read_json(previous_job)['job_id'])
            prior_source=read_json(semantics.studio.store.state_dir/'jobs'/prior['id']/'request.json')['parameters']['source']
            if prior['status'] in ('queued','running'):
                if read_json(previous_job).get('signature')!=signature:raise Conflict('上一份預覽仍在執行，請完成後再準備新版')
                return prior
            if prior['status']=='completed' and read_json(previous_job).get('signature')==signature:return prior
            if prior['status']!='completed':retry=prior['id']
        path=folder/('preview-plan-'+signature[:16]+'.json')
        if not path.exists():write_json(path,private)
        source=dict(plan=path.relative_to(root).as_posix(),plan_sha256=digest(path),preview_only=True,review_id=identifier,rooms=[dict(id=r['id'],name=r['name']) for r in check['rooms']],viewpoints=[],links=[])
        job=semantics.studio.jobs.submit_studio(project,'prepare',dict(source=source),'plan-preview-'+identifier+'-'+signature[:12]+'-'+retry[:12])
        write_json(folder/'preview-job.json',dict(job_id=job['id'],preview_only=True,signature=signature))
        return job
