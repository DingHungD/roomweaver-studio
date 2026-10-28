"""Shared, bounded catalog matching for evidenced shelf contents before rendering."""
import copy
import re
from pathlib import Path
from . import blenderkit_client as catalog
from .service import digest
from ..storage import read_json, write_json

QUERIES={'microwave':'microwave','coffee_machine':'espresso machine','magazines':'magazine stack'}


def eligible(candidate,kind,clearance):
    """Catalog dimensions are hints; actual mesh fit is always checked afterwards."""
    name=candidate.get('name','').lower()
    tokens={'microwave':('microwave',),'coffee_machine':('coffee','espresso'),'magazines':('magazine',)}[kind]
    if not any(w in name for w in tokens) or any(w in name for w in ('kitchen set','room','cabinet')):return False
    if not candidate.get('is_free') or candidate.get('license') not in ('cc_zero','royalty_free'):return False
    dims=candidate.get('dimensions')
    return not dims or all(d<=c+.003 for d,c in zip(dims,clearance))


def resolve(scene,root,source_hash,defaults=None):
    """Resolve only verified job-local bundles; no Agent-controlled local paths."""
    result=copy.deepcopy(defaults or {})
    for spec in scene.get('shelf_refinements',[]):
        bundle=spec.get('asset_bundle')
        if not bundle:continue
        if not re.fullmatch('[a-f0-9]{32}',bundle):raise ValueError('無效素材工作識別')
        folder=Path(root)/'runs/interior-studio'/bundle
        index=read_json(folder/'shelf-assets.json')
        if index['source_sha256']!=source_hash:raise ValueError('層架素材不屬於此原生模型')
        choices={}
        for kind,entries in index['objects'].get(spec['object_id'],{}).items():
            choices[kind]=[]
            for entry in entries:
                asset=dict(entry);path=(folder/entry['file']).resolve()
                if not path.is_relative_to(folder.resolve()) or digest(path)!=entry['sha256']:raise ValueError('層架素材來源或雜湊不符')
                asset['file']=str(path);choices[kind].append(asset)
        result[spec['object_id']]=choices
    return result


def match_missing(scene,reports,folder,source_hash,defaults,stop):
    """Download at most three free candidates per missing content, keep every source."""
    folder=Path(folder);index=dict(source_sha256=source_hash,objects={},searches=[])
    cache={};changed=False
    for report in reports:
        object_id=report['object_id'];choices={}
        available=report.get('clearance')
        if not available:continue
        for content in report.get('contents',[]):
            kind=content['kind'];old=(defaults or {}).get(object_id,defaults or {}).get(kind,[])
            old=[old] if isinstance(old,dict) else old
            # Freeze already fitted native files into this job's bundle without deleting originals.
            if content.get('source')=='registered_native_asset':
                selected=[a for a in old if a['sha256']==content['sha256']]
            else:selected=[]
            search=dict(object_id=object_id,kind=kind,clearance=available,candidates=[],failures=[])
            if not selected:
                if stop.exists():raise ValueError('已停止素材準備')
                try:
                    if kind not in cache:cache[kind]=catalog.search(QUERIES[kind],'model',True)
                    candidates=cache[kind]
                    search['candidates']=[dict(url=c['url'],name=c['name'],dimensions=c['dimensions'],eligible=eligible(c,kind,available)) for c in candidates]
                    candidates=[c for c in candidates if eligible(c,kind,available)]
                    # Prefer known original-scale fit; never enlarge or distort an appliance.
                    candidates.sort(key=lambda c:(c['dimensions'] is None,'low poly' in (c['description'] or '').lower()))
                    for c in candidates[:3]:
                        if stop.exists():raise ValueError('已停止素材準備')
                        file=folder/(c['asset_id']+'.blend')
                        try:
                            provenance=catalog.download(c,file,folder.name)
                            selected.append(dict(file=str(file),sha256=provenance['sha256'],source_url=c['url'],license=c['license'],front='-Y',min_scale=.999))
                        except (ValueError,OSError) as exc:search['failures'].append(dict(url=c['url'],reason=str(exc)))
                except (ValueError,OSError) as exc:search['failures'].append(dict(reason=str(exc)))
                changed=changed or bool(selected)
            entries=[]
            for a in selected or old:
                # Content-addressed copy belongs to the new immutable job; old files remain.
                import shutil
                source=Path(a['file']);destination=folder/(a['sha256']+'.blend')
                if digest(source)!=a['sha256']:raise ValueError('原素材雜湊不符')
                if not destination.exists():shutil.copyfile(source,destination)
                entries.append(dict(a,file=destination.name))
            choices[kind]=entries;index['searches'].append(search)
        index['objects'][object_id]=choices
    if not changed:return scene, index, False
    result=copy.deepcopy(scene)
    for spec in result.get('shelf_refinements',[]):
        if spec['object_id'] in index['objects']:spec['asset_bundle']=folder.name
    write_json(folder/'shelf-assets.json',index)
    return result,index,True
