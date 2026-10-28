"""Native DWG evidence attached to intake without replacing immutable sources."""
import os
from pathlib import Path
import shutil
import threading
from uuid import uuid4

from .dwg_inspection import read_native, handle
from .service import digest
from ..storage import read_json, write_json

_lock = threading.Lock()


def reader_executable(state_dir):
    runtime = Path(state_dir)/'runtime.json'
    settings = read_json(runtime) if runtime.exists() else {}
    configured = os.environ.get('LIBREDWG_DWGREAD') or settings.get('dwgread')
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise ValueError('LibreDWG 路徑不存在，請修正 LIBREDWG_DWGREAD 或 runtime.json 的 dwgread')
        return path.resolve()
    found = shutil.which('dwgread')
    if found:
        return Path(found).resolve()
    parent = os.environ.get('LOCALAPPDATA')
    if parent:
        matches = sorted((Path(parent)/'Programs/LibreDWG').glob('*/dwgread.exe'))
        if matches:
            return matches[-1].resolve()
    raise ValueError('DWG 原生判讀需要免費 LibreDWG；請安裝並設定 LIBREDWG_DWGREAD 指向 dwgread。原件保留，不改用圖片猜座標')


def attach_native(studio, project, source):
    """Read original DWG and cross-check the adapter DXF once per content/tool hash."""
    original = source.get('original')
    if not original:
        return None
    root = studio.root(project)
    for item in (original, source):
        if digest(root/item['path']) != item['sha256']:
            raise ValueError('DWG／DXF 來源已變動，不能讀取或套用判讀')
    reader = reader_executable(studio.store.state_dir)
    key = original['sha256']+'-'+source['sha256']+'-'+digest(reader)
    index = root/'runs/dwg-reading'/('index-'+key+'.json')
    with _lock:
        if index.exists():
            record = read_json(index)
            for name, sha in record['files'].items():
                if digest(root/record['path']/name) != sha:
                    raise ValueError('原生讀取證據已變動，請另建核對，不覆寫舊證據')
            return record
        run = root/'runs/dwg-reading'/('import-'+uuid4().hex)
        read_native(root/original['path'], run, reader, root/source['path'])
        if digest(root/original['path'])!=original['sha256'] or digest(root/source['path'])!=source['sha256']:
            raise ValueError('來源在原生讀取期間變動，保留證據但不繼續判讀')
        comparison = read_json(run/'dxf-comparison.json')
        if comparison['differences'] or comparison['missing_in_dxf'] or comparison['extra_in_dxf'] or not comparison['layer_names_equal']:
            raise ValueError('原生 DWG 與 DXF 幾何／圖層不一致，已保留比對證據；不以錯位轉檔繼續判讀')
        record = dict(path=run.relative_to(root).as_posix(), source_sha256=original['sha256'],
                      derived_sha256=source['sha256'], reader_sha256=digest(reader),
                      files={p.name:digest(p) for p in [run/'native.json',run/'inventory.json',run/'dxf-comparison.json']})
        write_json(index, record)
        readme = run.parent/'README.md'
        if not readme.exists():
            readme.write_text('# DWG 原生匯入證據\n\n所有者：本案。import-*/ 保存原始DWG直接解碼、圖層／文字／尺寸及DXF比對；index-*按來源與工具雜湊去重。由原件與指定版本工具可重建，修訂仍引用時不清理；不是已確認設計。\n',encoding='utf8')
        return record


def enrich_site(site, root, record):
    """Expose exact native primitives in the same metre-local frame as the UI."""
    from .dwg_inspection import catalog
    document = read_json(Path(root)/record['path']/'native.json')
    inventory, entities = catalog(document)
    factor, origin = site['factor'], site['origin']
    def local(p):
        return [p[k]*factor-origin[k] for k in (0,1)]
    geometry = {g['id']:g for g in site['geometry']}
    native = {}
    for entity in entities:
        key = 'e-'+f"{handle(entity['handle']):X}"
        t = entity['entity']
        if site.get('source_graph_version')=='source-only-v2' and key not in geometry and t not in ('INSERT','HATCH'):continue
        row = dict(id=key,kind=t)
        if t=='HATCH':
            from .structural_evidence import straight_hatch_loops
            from shapely.geometry import Polygon
            for number,points in straight_hatch_loops(entity):
                target=geometry.get(key+f'-boundary-{number}')
                if not target:continue
                exact=[local(p) for p in points]
                # Both independent readers must agree on the same closed fill.
                if target['closed'] and Polygon(exact).hausdorff_distance(Polygon(target['points']))<1e-7:
                    target.update(native_exact_fill=True)
        if t in ('LINE','LWPOLYLINE'):
            points = [entity['start'],entity['end']] if t=='LINE' else entity['points']
            normal = entity.get('extrusion',[0,0,1])
            # No silent OCS transform, bulge interpretation or tilted-source flattening.
            supported = normal==[0,0,1] and not any(entity.get('bulges',[]))
            if key in geometry and supported:
                geometry[key]['points'] = [local(p) for p in points]
                geometry[key]['native_exact'] = True
                geometry[key]['closed'] = bool(entity.get('flag',0)&512) if t=='LWPOLYLINE' else False
        if t in ('ARC','CIRCLE'):
            row.update(center=local(entity['center']), radius=entity['radius']*factor,
                       start_angle=entity.get('start_angle'),end_angle=entity.get('end_angle'))
        if t == 'INSERT':
            row.update(insertion=local(entity['ins_pt']),scale=entity.get('scale'),rotation=entity.get('rotation'))
        if len(row)>2:
            native[key] = row
    texts = []
    allowed_texts={t['id'] for t in site['texts']}
    objects={f"{handle(e['handle']):X}":e for e in entities}
    for a in inventory['annotations']:
        if a['type'] not in ('TEXT','MTEXT') or not a['text'].strip() or not a['insertion']:
            continue
        if site.get('source_graph_version')=='source-only-v2' and 'text-'+a['handle'] not in allowed_texts:continue
        texts.append(dict(id='text-'+a['handle'],text=a['text'],point=local(a['insertion']),
                          alignment_point=local(a['alignment']) if a['alignment'] else None,
                          layer=a['layer'],rotation=a['rotation_radians'],height=(a['height'] or 10)*factor,
                          horizontal_alignment=objects[a['handle']].get('horiz_alignment',0)))
    site['texts'] = texts
    from .source_binding import axis_options,door_options,frame_options
    for g in site['geometry']:
        options=axis_options(g)
        if options:g['axes']=options[:4]
    site['native_dwg'] = dict(schema='source-bound-v2',source_sha256=record['source_sha256'],
        reader=inventory['reader'],layers=inventory['layers'],entities=list(native.values()),
        door_options=door_options(site['geometry'],list(native.values())),
        frame_options=frame_options(site['geometry']),
        groups=[dict(id='group-'+g['handle'],source_ids=['e-'+h for h in g['members'] if 'e-'+h in geometry]) for g in inventory['groups'] if g['members']],
        blocks=[b for b in inventory['blocks'] if b['xref']],
        evidence_path=record['path'],model_entity_count=inventory['model_entity_count'])
    return site
