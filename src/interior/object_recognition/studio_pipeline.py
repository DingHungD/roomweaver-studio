"""Reference-free Studio workflow: model candidates, source repair, layers and omissions."""
import json
from pathlib import Path

from PIL import Image
from shapely.geometry import Point,Polygon

from .agent_review import run as review_all,meter,packet,RULES
from .agent_finish import finish
from .focused_review import color_layers
from .review_report import export_svg,freeze_review
from .tiled import load_masks,write,sha,public
from .conservative_review import guard,POLICY
from .native_policy import VERSION,normalized_site


LAYERS={'wall':('walls','wall'),'column':('other','column'),'beam':('other','beam'),
    'door_opening':('openings','door'),'window':('openings','window'),
    'sink':('equipment','sink'),'toilet':('equipment','toilet'),'kitchen_counter':('equipment','kitchen'),
    'cooktop':('equipment','kitchen'),'shower_area':('equipment','shower'),'shower_screen':('equipment','shower'),
    'shower_head':('equipment','shower'),'drying_rod':('equipment','appliance'),
    'track_light':('lighting','track'),'pendant_light':('lighting','pendant'),'light_symbol':('lighting','unknown'),
    'rug':('decoration','rug')}


def layer_data(site,rows):
    """Convert every mask ring to local CAD metres, retaining concavities and holes."""
    items=[]
    for row in rows:
        rings=[dict(points=[meter(site['source_view'],p) for p in c['points']],hole=c.get('hole',False)) for c in row.get('contours',[]) if len(c['points'])>=3]
        areas=[dict(points=r['points'],holes=[]) for r in rings if not r['hole']]
        for hole in [r for r in rings if r['hole']]:
            hosts=[a for a in areas if Polygon(a['points']).buffer(1e-8).covers(Point(hole['points'][0]))]
            if hosts:min(hosts,key=lambda a:Polygon(a['points']).area)['holes'].append(hole['points'])
        if not areas:continue
        layer,category=LAYERS.get(row['class_name'],('furniture',row['class_name'] if row['class_name'] in ('bed','table','chair','sofa') else 'other'))
        pending=not row.get('accepted',False)
        items.append(dict(id='recognition:'+row['id'],name=row.get('name') or row['class_name'],layer=layer,category=category,
            role='mask',points=[p for a in areas for p in a['points']],closed=True,areas=areas,
            source_ids=row.get('source_ids',[]),evidence=row.get('reason') or '模型候選，尚待原生來源複核',
            status='reference' if pending else 'interpreted',
            details=dict(parameters=[],notes=['待複核模型候選' if pending else 'Agent原生來源修正' if row.get('provenance')=='agent_native' else 'Agent核對的模型候選'])))
    return dict(items=items,lighting_reviewed=True)


def run(client,payload,bundle,output,model,progress,event=None,max_repairs=2):
    """No case IDs, known false positives, training labels or test references are accepted."""
    bundle=Path(bundle);output=Path(output);read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    source=Path(payload['image']);site=payload['site']
    if not site.get('geometry') or not site.get('source_view'):raise ValueError('原生來源複核需要圖面幾何及座標映射')
    if not (bundle/'taxonomy.json').is_file():raise ValueError('舊推論未附模型類別表，請建立新的判讀工作')
    config=read(bundle/'config.json');taxonomy=read(bundle/'taxonomy.json')['classes']
    if sha(source)!=config['sha256']['image']:raise ValueError('物件複核原圖與推論來源不同')
    classes={c['name']:c['id'] for c in taxonomy}
    if len(classes)!=len(taxonomy) or len(set(classes.values()))!=len(classes):raise ValueError('模型類別表重複')
    original=load_masks(bundle)
    if any(classes.get(r['class_name'])!=r['class_id'] for r in original):raise ValueError('模型候選與類別表不一致')
    binding=dict(image=sha(source),model=config['sha256']['checkpoint'],candidates=sha(bundle/'candidates.json'),
        masks=sha(bundle/'candidates-masks.npz'),taxonomy=sha(bundle/'taxonomy.json'),model_name=model,max_repairs=max_repairs,
        site=__import__('hashlib').sha256(json.dumps({k:site.get(k) for k in ('source_view','geometry','texts','native_dwg','confirmed_answers','user_source_reviews','dimension_confirmation')},sort_keys=True,ensure_ascii=False).encode()).hexdigest(),admission=POLICY,native_policy=VERSION)
    if output.exists():
        if not (output/'pipeline-summary.json').exists():raise ValueError('物件複核尚未完成，請用新的判讀工作重新執行；中間結果保留')
        if read(output/'binding.json')!=binding:raise ValueError('物件複核快取來源、模型或設定已改變')
        frozen=read(output/'frozen-result.json')
        if not all(sha(output/f)==h for f,h in frozen['files'].items()):raise ValueError('物件複核結果雜湊不一致')
        return read(output/'pipeline-summary.json')
    output.mkdir(parents=True);write(output/'binding.json',binding)
    class Events:
        def run(self,*args,**kwargs):
            kwargs.setdefault('on_event',event);return client.run(*args,**kwargs)
    agent=Events();native={k:site[k] for k in ('source_view','geometry','texts','dimensions','confirmed_unit','native_dwg','confirmed_answers','user_source_reviews','dimension_confirmation') if k in site}
    native,closure_audit=normalized_site(native)
    write(output/'native-policy.json',dict(version=VERSION,closure_normalization=closure_audit,source_coordinates_unchanged=True))
    review_all(agent,native,source,bundle,output,classes,model,progress,omission_review=False)
    finish(agent,native,source,bundle,output,classes,model,progress,max_rounds=max_repairs)
    rows=load_masks(output,'corrected-final');pending=read(output/'pending-final.json');verification=read(output/'layer-verification-final.json')
    decisions=read(output/'decisions.json')
    for folder in sorted(output.glob('layer-repair-*')):
        if (folder/'checked.json').exists():decisions+=read(folder/'checked.json').get('decisions',[])
    proposed=rows
    rows,guard_pending,admission=guard(original,proposed,decisions)
    pending+=guard_pending
    write(output/'admission.json',dict(policy=POLICY,checks=admission,pending=guard_pending,
        input_proposals='corrected-final.json',principle='do not silently remove or relabel existing predictions'))
    pending=list({p.get('id',p.get('stage',str(i))):p for i,p in enumerate(pending)}.values())
    write(output/'pending-final.json',pending)
    # Deferred or failed targets remain visible, instead of silently reducing recall.
    ids={r['id'] for r in rows};unresolved={i for p in pending for i in ([p['id']] if p.get('id') else p.get('target_ids',[]))}
    retained=[dict(r,accepted=False,route='agent_review',reason='來源複核尚未完成，保留模型候選待核對') for r in original if r['id'] in unresolved and r['id'] not in ids]
    combined=rows+retained
    from .agent_review import save_state
    image=Image.open(source).convert('RGB');save_state(output,combined,image,'objects')
    color_layers(image,combined,output,'class-layers');export_svg(source,combined,output/'class-layers.svg')
    layers=layer_data(native,combined);write(output/'object-layers.json',layers)
    if guard_pending or retained:
        regions=read(output/'protocol.json')['regions'];images=[]
        for i,region in enumerate(regions):
            path=output/f'admitted-region-{i+1}.png'
            with Image.open(output/'class-layers.png') as overlay:overlay.crop(region).save(path)
            images.append(path)
        data=packet(native,combined,[0,0,*image.size],combined);data.update(pending=pending,regions=regions)
        write(output/'admission-verification-request.json',data)
        progress('Agent回看保守合併後實際圖層；有爭議的候選保留待辦')
        response=agent.run(RULES+'\n本次只驗證保守合併後的實際圖層，無充分證據的改類／移除／大幅改輪廓已保留原候選。待辦不能因回查無發現而清空。回覆JSON {reviewed_regions:[0,1,2,3,4,5],findings:[{issue,name,object_ids:[],source_ids:[],reason}],summary}。\n'+json.dumps(data,ensure_ascii=False,separators=(',',':')),
            model=model,image=source,images=images,timeout=600)
        write(output/'admission-verification-response.json',response)
        text=response['text'];verification=json.loads(text[text.find('{'):text.rfind('}')+1])
        if set(verification.get('reviewed_regions',[]))!=set(range(6)):raise ValueError('保守合併後六區回查未完成')
    write(output/'layer-verification-admitted.json',verification)
    freeze_review(output,'objects','object-layers.json','layer-verification-admitted.json')
    frozen=read(output/'frozen-result.json')
    for name in ['corrected-final.json','corrected-final-masks.npz','class-layers.png','class-layers.svg','pending-final.json','admission.json','native-policy.json']:
        frozen['files'][name]=sha(output/name)
    write(output/'frozen-result.json',frozen)
    findings=verification.get('findings',[])
    summary=dict(workflow='agent_native_v1',status='blocked' if pending or findings else 'reviewed_preview',
        candidates=len(original),objects=len(combined),reviewed=sum(r.get('accepted',False) for r in rows),pending=len(pending),retained_unresolved=len(retained)+len(guard_pending),
        findings=len(findings),deferred=len(pending),scan_findings=len(findings),scan_failures=0,
        accepted=sum(r.get('provenance')=='yolo_agent_reviewed' for r in rows),
        native_corrected=sum(r.get('provenance')=='agent_native' for r in rows),
        rejected=sum(r['id'] not in {p['id'] for p in combined} for r in original),
        model=model,native_policy=VERSION,precision=None,recall=None,precision_target_verified=False,
        reference_labels_provided=False,known_error_ids_used=False,
        artifacts='yolo-native-review',layers=layers,layer_findings=findings,pending_items=pending)
    write(output/'pipeline-summary.json',summary);return summary
