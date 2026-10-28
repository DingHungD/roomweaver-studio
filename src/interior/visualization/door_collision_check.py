"""Check folding poses against the actual design without saving the model."""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).parent))
from concept_geometry import add_blender_furniture
from opening_details import add_openings


def run(packet):
    originals = {c['opening_id']: c for c in packet['originals']}
    openings = {o['id']: o for o in packet['openings']}
    controls = packet['controls']
    checks, uncertainties = [], []
    for control in controls:
        if control.get('kind') != 'folding' or control.get('deleted'):
            continue
        original = originals.get(control['opening_id'], {})
        choices = [(control.get('hinge'), control.get('side'))]
        choices += [(h, s) for h in ('A', 'B') for s in ('positive', 'negative')]
        tried = set()
        passed = False
        for hinge, side in choices:
            if hinge not in ('A', 'B') or side not in ('positive', 'negative') or (hinge, side) in tried:
                continue
            if any(original.get(k) not in (None, 'auto', v) for k, v in [('hinge', hinge), ('side', side)]):
                continue
            tried.add((hinge, side))
            bpy.ops.wm.open_mainfile(filepath=packet['blend'])
            scene = packet['scene']
            add_blender_furniture(scene.get('concept_furniture', []))
            objects = {o.get('studio_id'): o for o in bpy.data.objects if o.type in ('MESH', 'CURVE')}
            for group in scene['groups']:
                pivot = Vector(group.get('rotation_pivot', [0, 0, 0]))
                transform = Matrix.Translation(Vector(group['translation'])+pivot) @ Matrix.Rotation(math.radians(group.get('rotation', 0)), 4, 'Z') @ Matrix.Translation(-pivot)
                for key in group['children']:
                    obj = objects.get(key)
                    if obj is None:
                        raise ValueError('碰撞檢查缺少模型物件：'+key)
                    obj.matrix_world = transform @ obj.matrix_world
                    if group['deleted']:
                        obj.hide_render = True
                        obj.hide_set(True)
            candidate = dict(control, hinge=hinge, side=side)
            scene = dict(scene, opening_details=True, door_controls=[candidate])
            bpy.context.view_layer.update()
            report = add_openings(scene, objects, dict(items=[openings[control['opening_id']]],source_sha256=packet['sha256']))
            checks.append(dict(control=candidate, report=report))
            if report['items'] and report['items'][0].get('opening', {}).get('state') == 'open':
                if (control.get('hinge'), control.get('side')) != (hinge, side):
                    uncertainties.append(control.get('name', control['opening_id'])+'：原推定折向碰撞檢查未通過，已改為收至 '+hinge+' 端、A→B '+('左側' if side=='positive' else '右側')+'；此結果取代先前方向建議')
                control.update(candidate)
                passed = True
                break
        if not passed:
            uncertainties.append(control.get('name', control['opening_id'])+'：折疊路徑受阻，保留尺寸與已指定方向，需確認安裝方向')
            if original.get('side') in (None, 'auto'):
                control['side'] = None
    return dict(controls=controls, uncertainties=uncertainties, checks=checks)


if __name__ == '__main__':
    source, target = sys.argv[sys.argv.index('--')+1:]
    Path(target).write_text(json.dumps(run(json.loads(Path(source).read_text(encoding='utf-8'))), ensure_ascii=False, indent=2), encoding='utf-8')
