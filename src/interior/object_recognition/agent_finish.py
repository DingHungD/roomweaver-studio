"""Bounded, source-only repair of final layer findings before any scoring."""
import json
from pathlib import Path

from PIL import Image

from .agent_review import RULES,packet,apply_response,save_state,compact_geometry
from .tiled import load_masks,mask_iou,public,write


def finish(client,site,image_path,bundle,folder,classes,model,progress,max_rounds=2):
    folder=Path(folder);source=Image.open(image_path).convert('RGB');current=load_masks(folder,'corrected')
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
    pending=read(folder/'pending.json');verification=read(folder/'layer-verification.json')
    raw_lookup={p['id']:p for p in load_masks(bundle)};regions=read(folder/'protocol.json')['regions'];rounds=[]
    for n in range(max_rounds):
        findings=verification.get('findings',[])
        if not findings and not pending:break
        stage=f'layer-repair-{n+1:02d}';out=folder/stage;out.mkdir(exist_ok=True)
        refs={r for f in findings for r in f.get('source_ids',[])}
        ids={i for f in findings for i in f.get('object_ids',[])}|{p['id'] for p in pending if p.get('id')}
        targets=[p for p in current if p['id'] in ids or refs&set(p.get('source_ids',[]))]
        targets += [raw_lookup[i] for i in ids if i in raw_lookup and not any(p['id']==i for p in current)]
        if not targets and not refs:targets=current
        data=packet(site,targets,[0,0,*source.size],current)
        data.update(classes=classes,findings=findings,pending=pending,stage='修正完整套層回查發現，不重做已正確物件；缺少圖樣的文字只保留需求。')
        write(out/'request.json',data);error=None;accepted=False;decisions=[]
        progress(f'Agent套層問題修正 {n+1}/{max_rounds}：{len(findings)}項發現，{len(targets)}個目標')
        for attempt in range(2):
            saved=out/f'response-{attempt+1}.json'
            if saved.exists():response=read(saved)
            else:
                prompt=RULES+'\n本輪只修正以下套層問題及待處理目標。Agent原生物件的confidence=0表示沒有YOLO分數，不能因此否定物件。\n'+json.dumps(data,ensure_ascii=False,separators=(',',':'))
                if error:prompt+='\n前次來源檢查錯誤，請修正：'+error
                response=client.run(prompt,model=model,image=Path(image_path),images=[folder/('corrected.png' if n==0 else f'corrected-repair-{n:02d}.png')],timeout=600);write(saved,response)
            try:
                text=response['text'];proposal=json.loads(text[text.find('{'):text.rfind('}')+1])
                updated,decisions,new_pending=apply_response(site,targets,proposal,current,classes,raw_lookup,source.size,stage,{g['id'] for g in data['geometry']})
                current=updated
                resolved={d['id'] for d in decisions if d.get('action')!='defer'}
                pending=[p for p in pending if p.get('id') not in resolved]+new_pending
                accepted=True;break
            except (ValueError,KeyError,TypeError,IndexError) as exc:error=str(exc);write(out/f'error-{attempt+1}.json',dict(error=error))
        if not accepted:pending.append(dict(stage=stage,error=error))
        deduped=[];duplicates=[]
        for p in current:
            other=next((q for q in deduped if q['class_id']==p['class_id'] and mask_iou(p,q)>=.95),None)
            if other:duplicates.append(dict(id=p['id'],duplicate_of=other['id']))
            else:deduped.append(p)
        current=deduped;save_state(folder,current,source,f'corrected-repair-{n+1:02d}')
        write(out/'checked.json',dict(accepted=accepted,decisions=decisions,pending=pending,duplicates=duplicates))
        images=[]
        with Image.open(folder/f'corrected-repair-{n+1:02d}.png') as im:
            for i,r in enumerate(regions):
                path=out/f'region-{i+1}.png';im.crop(r).save(path);images.append(path)
        data=dict(regions=regions,objects=[{k:v for k,v in public(p).items() if k not in ('contours','members')} for p in current],
                  geometry=[compact_geometry(g,site['source_view']) for g in site['geometry'] if len(g.get('points',[]))>=2],texts=site['texts'])
        write(out/'verification-request.json',data);saved=out/'verification-response.json'
        progress(f'Agent修正後再次查閱全圖與6區 {n+1}/{max_rounds}')
        if saved.exists():response=read(saved)
        else:
            response=client.run(RULES+'\n僅檢查套層後是否仍有具體錯誤或遺漏，回覆JSON {reviewed_regions:[0,1,2,3,4,5],findings:[{issue,name,object_ids:[],source_ids:[],reason}],summary}。不得輸出精確率或猜測缺失輪廓。\n'+json.dumps(data,ensure_ascii=False,separators=(',',':')),
                model=model,image=Path(image_path),images=images,timeout=600);write(saved,response)
        text=response['text'];verification=json.loads(text[text.find('{'):text.rfind('}')+1])
        if set(verification.get('reviewed_regions',[]))!=set(range(6)):raise ValueError('Incomplete layer recheck coverage')
        rounds.append(dict(stage=stage,accepted=accepted,findings=len(verification.get('findings',[])),pending=len(pending)))
        write(out/'layer-verification.json',verification)
    save_state(folder,current,source,'corrected-final')
    write(folder/'layers-final.json',dict(status='agent_reviewed_preview',coordinate_system='original_image_pixels',
        layers={c:[public(p) for p in current if p['class_name']==c] for c in classes if any(p['class_name']==c for p in current)}))
    write(folder/'layer-verification-final.json',verification);write(folder/'pending-final.json',pending)
    result=dict(rounds=rounds,final_objects=len(current),pending=len(pending),findings=len(verification.get('findings',[])),
                reference_labels_provided=False,model=model)
    write(folder/'finish-status.json',result);return result
