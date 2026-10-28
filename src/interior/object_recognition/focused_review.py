"""Bounded Agent correction of explicitly selected candidates; other masks stay frozen."""
import copy
import colorsys
import json
from pathlib import Path

from PIL import Image

from .agent_review import RULES,packet,apply_response,save_state,compact_geometry
from .review_report import export_svg,freeze_review
from .tiled import load_masks,public,render,write,sha


FOCUS_RULES='''這是限定目標的CAD複核；沒有人工答案的mask、IoU或物件總數提供給你。
只修正targets，nearby_objects提供相鄰物件及既有候選ID作關聯判斷，不能刪除或重畫非targets。
不是每一筆被點名都必須刪掉；依CAD原生圖樣決定保留、更正、重複或不確定。
重複片段請選一個完整代表並以duplicate_of指出。若targets中沒有完整物件，優先replace其中一筆為來源推導的完整輪廓，再刪其他重複；避免另增一件又保留原片段。
若非targets中已有同一件完整代表，應保留該代表、reject本批重複並duplicate_of它，不能因為它不在targets就保留兩件。
垃圾桶、尿片、回收桶、熱水器等主要靠文字區分的方框設備使用furniture，床桌椅沙發等明確圖樣保留原類。
相連黑色實心牆為一件，窗各自獨立且只標窗，不補上／下推測牆。不能把相鄰但中間有門洞／窗的黑牆一律合併。
隔屏／淋浴玻璃門要核對整件外框與門扇，不用內部排水、蓮蓬頭或文字的包絡取代外框。
有明確封閉外框的家具、設備、窗依既定規則標示整件占位，包含框內空白，不只描細邊線。
玻璃隔屏及開啟門扇按各自原生封閉實體的投影聯集；開啟弧線只作參照。不能把隔屏與斜向門扇之間的空白或開門範圍填成玻璃實體，也不把淋浴使用區當成隔屏。
每個decision（包括reject/defer）需引用提供的真實source_ids作證據；文字只作佐證。keep只能原樣保留mask，改邊界一定replace。
如有additions，只能是本批目標所代表之真實物件的完整替代，不能順便全面重判。無法安全確定時defer，宿主會保留原候選並列待辦，不以刪除來美化分數。
'''


def validate_scope(proposal,targets,current,geometry_ids,text_ids):
    """Reject invented evidence, hidden keep edits, and invalid duplicate references."""
    decisions=proposal.get('decisions',[]);expected={r['id'] for r in targets}
    if len(decisions)!=len(expected) or {d.get('id') for d in decisions}!=expected:
        raise ValueError('Exactly one decision per scoped target is required')
    actions={d['id']:d.get('action') for d in decisions};known={r['id'] for r in current}
    for d in decisions:
        if not d.get('source_ids') or not set(d['source_ids'])<=geometry_ids:
            raise ValueError('Every decision must cite provided CAD geometry')
        if not set(d.get('text_ids',[]))<=text_ids:raise ValueError('Unknown CAD text')
        if d.get('action')=='keep':
            spec=d.get('mask_spec',dict(method='yolo',candidate_id=d['id']))
            if spec!={'method':'yolo','candidate_id':d['id']}:raise ValueError('keep cannot modify the source mask')
        duplicate=d.get('duplicate_of')
        if duplicate:
            if d.get('action')!='reject' or duplicate==d['id'] or duplicate not in known or actions.get(duplicate) in ('reject','defer'):
                raise ValueError('duplicate_of must identify a surviving known object')


def apply_scoped(site,targets,proposal,current,classes,raw_lookup,size,stage,geometry_ids):
    validate_scope(proposal,targets,current,geometry_ids,{t['id'] for t in site['texts']})
    # keep means the current reviewed shape, not the earlier pre-correction model mask.
    proposal=copy.deepcopy(proposal);target_lookup={r['id']:r for r in targets}
    for d in proposal['decisions']:
        if d['action']=='keep':
            original=target_lookup[d['id']]
            d['mask_spec']=copy.deepcopy(original.get('mask_spec') or dict(method='yolo',candidate_id=d['id']))
    current_lookup=dict(raw_lookup,**{r['id']:r for r in current})
    updated,audit,pending=apply_response(site,targets,proposal,current,classes,current_lookup,size,stage,geometry_ids)
    # Uncertain objects count as retained predictions; they do not disappear from scoring.
    deferred={d['id'] for d in pending};present={r['id'] for r in updated}
    updated.extend(copy.copy(r) for r in current if r['id'] in deferred and r['id'] not in present)
    protected={r['id']:r for r in current if r['id'] not in {t['id'] for t in targets}}
    final={r['id']:r for r in updated}
    if not set(protected)<=set(final):raise ValueError('A non-target object was removed')
    for key,row in protected.items():
        other=final[key]
        if row['class_id']!=other['class_id'] or row['mask_box']!=other['mask_box'] or (row['mask']!=other['mask']).any():
            raise ValueError('A non-target class or mask changed')
    return updated,audit,pending


def color_layers(source,rows,folder,filename):
    classes=sorted({r['class_name'] for r in rows})
    colors={c:tuple(int(v*255) for v in colorsys.hsv_to_rgb(i/max(1,len(classes)),.75,.85)) for i,c in enumerate(classes)}
    render(source,[dict(r,route=r['class_name']) for r in rows],folder/(filename+'.png'),colors)
    write(folder/(filename+'-legend.json'),{c:list(v) for c,v in colors.items()})


def run(client,site,image_path,bundle,output,classes,groups,model,progress,max_repairs=1):
    """Review selected source-bound regions, inspect layers, freeze before evaluation."""
    output=Path(output)
    if (output/'frozen-result.json').exists():raise FileExistsError('Frozen review cannot be resumed for editing')
    output.mkdir(parents=True,exist_ok=True)
    source=Image.open(image_path).convert('RGB');original=load_masks(bundle);current=list(original)
    raw_lookup={r['id']:r for r in original};target_ids=[i for g in groups for i in g['target_ids']]
    if len(set(target_ids))!=len(target_ids) or not set(target_ids)<=set(raw_lookup):raise ValueError('Invalid scoped target IDs')
    inputs={str(Path(p).resolve()):sha(p) for p in [image_path,Path(bundle)/'candidates.json',Path(bundle)/'candidates-masks.npz']}
    write(output/'source-only-input.json',site)
    write(output/'protocol.json',dict(model=model,classes=classes,groups=groups,target_ids=target_ids,
        original_predictions=len(original),protected_non_targets=len(original)-len(target_ids),
        reference_masks_and_scores_provided=False,error_localization_from_previous_evaluation=True,
        pending_policy='retain original candidate, list unresolved evidence',max_repairs=max_repairs,inputs=inputs))
    audit=[];pending=[];calls=[]

    def ask(folder,data,targets,stage,images):
        folder.mkdir(exist_ok=True);write(folder/'request.json',data);error=None
        for attempt in range(2):
            saved=folder/f'response-{attempt+1}.json'
            if saved.exists():response=json.loads(saved.read_text(encoding='utf-8'))
            else:
                progress(f'Agent {stage}：{len(targets)}個目標，嘗試{attempt+1}')
                prompt=RULES+'\n'+FOCUS_RULES+'\n本批資料：'+json.dumps(data,ensure_ascii=False,separators=(',',':'))
                if error:prompt+='\n前次提案來源／範圍檢查未通過，請更正：'+error
                response=client.run(prompt,model=model,image=Path(image_path),images=images,timeout=600)
                write(saved,response)
            calls.append(dict(stage=stage,attempt=attempt+1,thread_id=response.get('thread_id'),turn_id=response.get('turn_id')))
            try:
                text=response['text'];proposal=json.loads(text[text.find('{'):text.rfind('}')+1])
                updated,decisions,deferred=apply_scoped(site,targets,proposal,current,classes,raw_lookup,source.size,stage,{g['id'] for g in data['geometry']})
                write(folder/'checked.json',dict(status='passed',decisions=decisions,pending=deferred))
                return updated,decisions,deferred
            except (ValueError,KeyError,TypeError,IndexError) as exc:
                error=str(exc);write(folder/f'error-{attempt+1}.json',dict(error=error))
        unresolved=[dict(id=r['id'],action='defer',reason='Proposal validation failed: '+str(error)) for r in targets]
        write(folder/'checked.json',dict(status='pending',error=error,pending=unresolved))
        return current,[],unresolved

    for n,g in enumerate(groups,1):
        stage=f'focused-{n:02d}';folder=output/stage;folder.mkdir(exist_ok=True)
        targets=[r for r in current if r['id'] in g['target_ids']]
        data=packet(site,targets,g['region'],current);data.update(classes=classes,scope=g['name'])
        source.crop(g['region']).save(folder/'source-crop.png')
        color_layers(source,current,folder,'context')
        with Image.open(folder/'context.png') as im:im.crop(g['region']).save(folder/'overlay-crop.png')
        current,decisions,deferred=ask(folder,data,targets,stage,[folder/'source-crop.png',folder/'overlay-crop.png'])
        audit+=decisions;pending+=deferred;save_state(output,current,source,'checkpoint-'+stage)
        write(output/'decisions.json',audit);write(output/'pending.json',pending);write(output/'agent-calls.json',calls)

    regions=[[round(x*source.width/3),round(y*source.height/2),round((x+1)*source.width/3),round((y+1)*source.height/2)] for y in range(2) for x in range(3)]
    verification=None
    for check in range(max_repairs+1):
        stage=f'layer-check-{check+1:02d}';folder=output/stage;folder.mkdir(exist_ok=True)
        color_layers(source,current,folder,'layers');images=[]
        for n,region in enumerate(regions):
            path=folder/f'region-{n+1}.png'
            with Image.open(folder/'layers.png') as im:im.crop(region).save(path)
            images.append(path)
        data=dict(classes=classes,regions=regions,scoped_target_ids=target_ids,scope_regions=groups,
            decisions=audit,pending=pending,objects=[{k:v for k,v in public(r).items() if k not in ('contours','members','fusion')} for r in current],
            geometry=[compact_geometry(g,site['source_view']) for g in site['geometry'] if len(g.get('points',[]))>=2],texts=site['texts'])
        write(folder/'request.json',data);saved=folder/'response.json'
        progress(f'Agent套層檢查 {check+1}：全圖與6區，{len(current)}件')
        if saved.exists():response=json.loads(saved.read_text(encoding='utf-8'))
        else:
            prompt=RULES+'\n'+FOCUS_RULES+'''\n本次僅查閱套層，不直接改動。逐區核對被修正處與附近既有物件，檢查是否重複、遺漏、錯類或輪廓錯誤。
完整看6區，沒有依據不要找理由重判其他物件。回覆JSON {reviewed_regions:[0,1,2,3,4,5],findings:[{issue,name,object_ids:[],source_ids:[],reason}],summary}。
指出必須修正的具體來源與物件ID，不回覆precision／recall。'''+'\n'+json.dumps(data,ensure_ascii=False,separators=(',',':'))
            response=client.run(prompt,model=model,image=Path(image_path),images=[folder/'layers.png',*images],timeout=600);write(saved,response)
        calls.append(dict(stage=stage,thread_id=response.get('thread_id'),turn_id=response.get('turn_id')))
        text=response['text'];verification=json.loads(text[text.find('{'):text.rfind('}')+1])
        if set(verification.get('reviewed_regions',[]))!=set(range(6)):raise ValueError('Incomplete six-region layer check')
        write(folder/'checked.json',verification);write(output/'agent-calls.json',calls)
        if not verification.get('findings') or check==max_repairs:break
        # Only targets and native replacements/additions in the authorized regions are editable.
        editable=set(target_ids)|{r['id'] for r in current if r.get('review_stage','').startswith(('focused-','repair-'))}
        ids={i for f in verification['findings'] for i in f.get('object_ids',[]) if i in editable}
        ids|={d['id'] for d in pending if d.get('id') in editable}
        targets=[r for r in current if r['id'] in ids]
        if not targets:break
        data=packet(site,targets,[0,0,*source.size],current)
        data.update(classes=classes,findings=verification['findings'],scope='只修正既定目標的套層問題；其他物件原樣保留')
        stage=f'repair-{check+1:02d}'
        current,decisions,deferred=ask(output/stage,data,targets,stage,[folder/'layers.png'])
        audit+=decisions;resolved={d['id'] for d in decisions if d['action']!='defer'}
        pending=[d for d in pending if d.get('id') not in resolved]+deferred
        save_state(output,current,source,'checkpoint-'+stage)

    save_state(output,current,source,'corrected');color_layers(source,current,output,'class-layers')
    write(output/'layers.json',dict(status='focused_agent_corrected_preview',coordinate_system='original_image_pixels',
        original_untouched_objects=len(original)-len(target_ids),
        layers={c:[public(r) for r in current if r['class_name']==c] for c in classes if any(r['class_name']==c for r in current)}))
    pending={d.get('id',d.get('stage','unknown')):d for d in pending}
    write(output/'pending.json',list(pending.values()));write(output/'decisions.json',audit)
    write(output/'layer-verification.json',verification);write(output/'agent-calls.json',calls)
    protected={r['id']:r for r in original if r['id'] not in target_ids};final={r['id']:r for r in current}
    for key,row in protected.items():
        if key not in final or row['class_id']!=final[key]['class_id'] or row['mask_box']!=final[key]['mask_box'] or (row['mask']!=final[key]['mask']).any():
            raise ValueError('Untargeted baseline changed across stages')
    if not all(sha(p)==h for p,h in inputs.items()):raise ValueError('Source/model bundle changed')
    export_svg(image_path,current,output/'reviewed-layers.svg');freeze_review(output)
    status=dict(status='completed_with_findings' if pending or verification.get('findings') else 'completed_review',
        original_candidates=len(original),target_candidates=len(target_ids),unchanged_non_targets=len(protected),
        after_objects=len(current),pending=len(pending),findings=len(verification.get('findings',[])),
        agent_calls=len(calls),model=model,reference_masks_and_scores_provided=False,
        error_localization_from_previous_evaluation=True,all_untargeted_masks_unchanged=True,model_raw_precision_unchanged=True)
    write(output/'status.json',status);return status
