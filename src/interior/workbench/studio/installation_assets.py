"""Source-bound installation replacement bundles; preview only, no asset adoption."""
import copy,re
from pathlib import Path
from . import blenderkit_client as catalog
from .service import digest
from ..storage import read_json,write_json

def eligible(c):
    name=c.get('name','').lower()
    return c.get('kind')=='model' and c.get('is_free') is True and c.get('license') in ('cc_zero','royalty_free') and 'shower' in name and any(k in name for k in ('corner','enclosure','cabin'))

def resolve(scene,root,source_hash):
    result={}
    for spec in scene.get('installation_replacements',[]):
        folder=Path(root)/'runs/interior-studio'/spec['bundle']
        packet=read_json(folder/'installation-assets.json')
        if packet['source_sha256']!=source_hash:raise ValueError('安裝候選不屬於此來源模型')
        entries=[]
        for entry in packet['objects'].get(spec['group_id'],[]):
            path=(folder/entry['file']).resolve()
            if not path.is_relative_to(folder.resolve()) or digest(path)!=entry['sha256']:raise ValueError('安裝素材來源或雜湊不符')
            entries.append(dict(entry,file=str(path)))
        result[spec['group_id']]=entries
    return result

def prepare(scene,report,folder,source_hash,stop):
    """Retry only reported installation conflicts; free candidates, bounded and traceable."""
    result=copy.deepcopy(scene);packet=dict(source_sha256=source_hash,objects={},searches=[])
    existing={s['group_id'] for s in scene.get('installation_replacements',[])}
    targets=[r for r in report.get('items',[]) if r.get('kind')=='shower' and r.get('status')=='unresolved' and r.get('id') not in existing]
    if not targets:return result,False
    try:candidates=catalog.search('shower enclosure','model',True)
    except (ValueError,OSError) as exc:
        packet['searches'].append(dict(failures=[dict(reason=str(exc))]))
        write_json(folder/'installation-assets.json',packet)
        return result,False
    for row in targets:
        if stop.exists():raise ValueError('已停止安裝候選準備')
        group=next(g for g in scene['groups'] if g['id']==row['id'])
        old=(group.get('asset_reference') or {}).get('asset_id');choices=[c for c in candidates if eligible(c) and c['asset_id']!=old]
        # Dimensions only rank attempts. The actual evaluated mesh remains authoritative.
        choices.sort(key=lambda c:max(c['dimensions'][:2]) if c.get('dimensions') else 999)
        log=dict(group_id=row['id'],trigger=row.get('reason'),candidates=[dict(name=c['name'],url=c['url'],dimensions=c['dimensions']) for c in choices],failures=[])
        entries=[]
        for c in choices[:3]:
            if stop.exists():raise ValueError('已停止安裝候選準備')
            try:
                path=folder/(c['asset_id']+'.blend');proof=catalog.download(c,path,folder.name)
                entries.append(dict(file=path.name,sha256=proof['sha256'],name=c['name'],url=c['url'],license=c['license'],asset_id=c['asset_id']))
            except (ValueError,OSError) as exc:log['failures'].append(dict(url=c['url'],reason=str(exc)))
        packet['objects'][row['id']]=entries;packet['searches'].append(log)
        if entries:result.setdefault('installation_replacements',[]).append(dict(group_id=row['id'],bundle=folder.name))
    write_json(folder/'installation-assets.json',packet)
    return result,result!=scene
