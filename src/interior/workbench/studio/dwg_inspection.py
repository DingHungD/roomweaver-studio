"""Read-only native DWG inventory and independent DXF geometry comparison.

LibreDWG is an optional, separately installed executable, not a bundled MIT
dependency. Its JSON retains the original object records. This module does not
classify architecture, flatten blocks, adopt a plan or modify a source file.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess


def handle(reference):
    """Resolve a LibreDWG own handle or already-resolved handle reference."""
    if not reference:
        return None
    return int(reference[3] if len(reference) > 3 else reference[2])


def catalog(document):
    objects = {handle(o['handle']): o for o in document['OBJECTS']}
    model = next(o for o in objects.values()
                 if o.get('object') == 'BLOCK_HEADER' and o['name'] == '*Model_Space')
    references = [handle(r) for r in model.get('entities', [])]
    missing = [f'{h:X}' for h in references if h not in objects]
    if missing:
        raise ValueError('Unresolved model-space handles: ' + ', '.join(missing))
    entities = [objects[h] for h in references]
    layers = {h: o for h, o in objects.items() if o.get('object') == 'LAYER'}

    def layer_name(o):
        return layers.get(handle(o.get('layer')), {}).get('name')

    annotations = []
    dimensions = []
    for o in entities:
        common = dict(handle=f"{handle(o['handle']):X}", layer=layer_name(o))
        if o.get('entity') in ('TEXT', 'MTEXT', 'ATTDEF', 'ATTRIB'):
            annotations.append(dict(common, type=o['entity'],
                text=o.get('text_value', o.get('text', o.get('default_value', ''))),
                tag=o.get('tag'), prompt=o.get('prompt'), insertion=o.get('ins_pt'),
                alignment=o.get('alignment_pt'), rotation_radians=o.get('rotation', 0),
                height=o.get('height'), invisible=o.get('invisible', 0)))
        if o.get('entity', '').startswith('DIMENSION'):
            block = objects.get(handle(o.get('block')), {})
            rendered = [objects.get(handle(r), {}) for r in block.get('entities', [])]
            dimensions.append(dict(common, type=o['entity'],
                measurement=o.get('act_measurement'), override=o.get('user_text'),
                rendered_text=[p.get('text', p.get('text_value')) for p in rendered
                               if p.get('entity') in ('MTEXT', 'TEXT')],
                endpoint_a=o.get('xline1_pt'), endpoint_b=o.get('xline2_pt'),
                dimension_line=o.get('def_pt'), text_position=o.get('text_midpt'),
                rotation_radians=o.get('dim_rotation'), block=block.get('name')))
    inventory = dict(reader=document.get('created_by'), version=document['FILEHEADER']['version'],
        header_insunits=document['HEADER'].get('INSUNITS'), model_handle=f"{handle(model['handle']):X}",
        object_count=len(objects), model_entity_count=len(entities),
        model_types=dict(Counter(o.get('entity', '?') for o in entities)),
        layers=[dict(handle=f'{h:X}', name=o['name'], native_flags=o.get('flag0'),
                     color=o.get('color'),
                     model_types=dict(Counter(e.get('entity', '?') for e in entities
                                              if handle(e.get('layer')) == h)))
                for h, o in layers.items()],
        annotations=annotations, dimensions=dimensions,
        blocks=[dict(handle=f'{h:X}', name=o['name'], base=o.get('base_pt'),
                     xref=bool(o.get('blkisxref')), xref_path=o.get('xref_pname'),
                     xref_loaded=o.get('xref_loaded'), entity_count=len(o.get('entities', [])))
                for h, o in objects.items() if o.get('object') == 'BLOCK_HEADER'],
        groups=[dict(handle=f'{h:X}', name=o.get('name'),
                     members=[f'{handle(r):X}' for r in o.get('groups', [])])
                for h, o in objects.items() if o.get('object') == 'GROUP'])
    return inventory, entities


def _native_signature(o):
    t = o['entity']
    if t == 'LINE':
        return [o['start'], o['end']]
    if t in ('ARC', 'CIRCLE'):
        return [o['center'], o['radius']] + ([o['start_angle'], o['end_angle']] if t == 'ARC' else [])
    if t == 'LWPOLYLINE':
        bulges = o.get('bulges') or [0.] * len(o['points'])
        return [o['points'], bulges, bool(o.get('flag', 0) & 512), o.get('elevation', 0)]
    if t in ('TEXT', 'ATTDEF'):
        return [o.get('text_value', o.get('default_value', '')), o['ins_pt'][:2],
                o.get('alignment_pt', [0, 0])[:2], o.get('rotation', 0), o['height']]
    if t == 'DIMENSION_LINEAR':
        return [o['xline1_pt'], o['xline2_pt'], o['def_pt'], o['text_midpt'][:2],
                o['act_measurement'], o.get('user_text', ''), o['dim_rotation']]
    if t == 'SOLID':
        return [[*o['corner' + str(i)], o.get('elevation', 0)] for i in range(1, 5)]
    if t == 'HATCH':
        paths = []
        for p in o['paths']:
            if 'polyline_paths' in p:
                paths.append(['polyline', bool(p['closed']),
                              [[*v['point'], v.get('bulge', 0)] for v in p['polyline_paths']]])
            elif all(s['curve_type'] == 1 for s in p.get('segs', [])):
                paths.append(['edges', [[s['first_endpoint'], s['second_endpoint']] for s in p['segs']]])
            else:
                return None
        return [o['name'], paths]
    return None


def _dxf_signature(e):
    t = e.dxftype()
    if t == 'LINE':
        return [list(e.dxf.start), list(e.dxf.end)]
    if t in ('ARC', 'CIRCLE'):
        return [list(e.dxf.center), e.dxf.radius] + ([math.radians(e.dxf.start_angle),
                math.radians(e.dxf.end_angle)] if t == 'ARC' else [])
    if t == 'LWPOLYLINE':
        return [[[p[0], p[1]] for p in e.get_points()], [p[4] for p in e.get_points()],
                e.closed, e.dxf.elevation]
    if t in ('TEXT', 'ATTDEF'):
        return [e.dxf.text, list(e.dxf.insert)[:2], list(e.dxf.align_point or (0, 0, 0))[:2],
                math.radians(e.dxf.rotation), e.dxf.height]
    if t == 'DIMENSION':
        return [list(e.dxf.defpoint2), list(e.dxf.defpoint3), list(e.dxf.defpoint),
                list(e.dxf.text_midpoint)[:2], e.dxf.actual_measurement,
                e.dxf.text, math.radians(e.dxf.angle)]
    if t == 'SOLID':
        return [list(e.dxf.get('vtx' + str(i))) for i in range(4)]
    if t == 'HATCH':
        paths = []
        for p in e.paths:
            if hasattr(p, 'vertices'):
                paths.append(['polyline', bool(p.is_closed), [list(v) for v in p.vertices]])
            elif all(s.EDGE_TYPE == 'LineEdge' for s in p.edges):
                paths.append(['edges', [[list(s.start), list(s.end)] for s in p.edges]])
            else:
                return None
        return [e.dxf.pattern_name, paths]
    return None


def _equal(a, b, tolerance):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_equal(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, abs_tol=tolerance, rel_tol=0)
    return a == b


def compare_dxf(document, path, tolerance=1e-7):
    """Compare matched model-space handles; unknown types remain unverified.

    This checks layer membership and selected geometric/annotation fields, not
    identical rendering, font availability, hatch appearance or all CAD data.
    """
    import ezdxf
    inventory, entities = catalog(document)
    dxf = ezdxf.readfile(path)
    dxf_entities = {e.dxf.handle: e for e in dxf.modelspace()}
    layers = {l['handle']: l['name'] for l in inventory['layers']}
    missing, changes, unchecked = [], [], []
    verified = Counter()
    for o in entities:
        key = f"{handle(o['handle']):X}"
        e = dxf_entities.get(key)
        if e is None:
            missing.append(key)
            continue
        expected_type = 'DIMENSION' if o['entity'].startswith('DIMENSION') else o['entity']
        if e.dxftype() != expected_type or e.dxf.layer != layers.get(f"{handle(o.get('layer')):X}"):
            changes.append(dict(handle=key, reason='type_or_layer'))
            continue
        a = _native_signature(o)
        b = _dxf_signature(e) if a is not None else None
        if a is None or b is None:
            unchecked.append(dict(handle=key, type=o['entity']))
        elif not _equal(a, b, tolerance):
            changes.append(dict(handle=key, type=o['entity'], native=a, dxf=b))
        else:
            verified[o['entity']] += 1
    original_handles = {f"{handle(o['handle']):X}" for o in entities}
    return dict(tolerance_source_units=tolerance, fields='geometry, text positioning, dimension values/endpoints, layer membership',
        native_count=len(entities), dxf_count=len(dxf_entities), verified_types=dict(verified),
        missing_in_dxf=missing, extra_in_dxf=sorted(set(dxf_entities) - original_handles),
        differences=changes, unverified=unchecked,
        layer_names_equal=set(l['name'] for l in inventory['layers']) == set(l.dxf.name for l in dxf.layers))


def read_native(source, output, reader, dxf=None):
    """Write a fresh, traceable inspection run without touching the application state."""
    source, output, reader = Path(source).resolve(), Path(output).resolve(), Path(reader).resolve()
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    raw = output / 'native.json'
    result = subprocess.run([str(reader), '-O', 'JSON', '-o', str(raw), str(source)],
                            capture_output=True, timeout=120,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (output / 'reader.stderr.txt').write_bytes(result.stderr)
    (output / 'reader.stdout.txt').write_bytes(result.stdout)
    manifest = dict(source=str(source), source_sha256=original_hash, reader=str(reader),
                    reader_sha256=hashlib.sha256(reader.read_bytes()).hexdigest(), returncode=result.returncode,
                    source_unchanged=hashlib.sha256(source.read_bytes()).hexdigest() == original_hash)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    if result.returncode or not manifest['source_unchanged']:
        raise ValueError('DWG read failed or source changed; inspect reader.stderr.txt and manifest.json')
    document = json.loads(raw.read_text(encoding='utf8'))
    inventory, _ = catalog(document)
    (output / 'inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf8')
    if dxf:
        comparison = compare_dxf(document, dxf)
        (output / 'dxf-comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding='utf8')
    return inventory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--reader', required=True)
    parser.add_argument('--output', required=True, help='New run directory; must not exist')
    parser.add_argument('--dxf', help='Optional independent conversion to compare')
    args = parser.parse_args()
    inventory = read_native(args.source, args.output, args.reader, args.dxf)
    print(json.dumps(dict(model_entity_count=inventory['model_entity_count'],
                         layers=len(inventory['layers']), dimensions=len(inventory['dimensions']))))
