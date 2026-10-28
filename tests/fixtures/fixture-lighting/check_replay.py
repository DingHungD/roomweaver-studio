"""Run with Blender: check actual light replay, group rotation and deletion."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector,Matrix,Euler

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src/interior/visualization'))
from studio_lighting import apply

root=Path(sys.argv[sys.argv.index('--')+1]).resolve()
accepted=json.loads((root/'accepted.json').read_text(encoding='utf-8'))['scene']
source=root/'source.blend';original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(source))
def signature():
    return [(o.name,tuple(o.matrix_world),tuple(tuple(v.co) for v in o.data.vertices)) for o in bpy.context.scene.objects if o.type=='MESH']
before=signature()
apply(accepted)
spec=next(l for l in accepted['lighting_setup']['lights'] if l.get('group_id')=='anonymous-01')
obj=next(o for o in bpy.context.scene.objects if o.get('studio_light_id')==spec['id'] and not o.hide_render)
group=next(g for g in accepted['groups'] if g['id']=='anonymous-01')
rotation=Matrix.Rotation(__import__('math').radians(group['rotation']),3,'Z');pivot=Vector(group['rotation_pivot'])
expected=rotation@(Vector(spec['position'])-pivot)+pivot+Vector(group['translation'])
assert (obj.location-expected).length<1e-5
assert (obj.rotation_euler.to_matrix()@Vector((0,0,-1))-rotation@Euler(spec['rotation'],'XYZ').to_matrix()@Vector((0,0,-1))).length<1e-5
assert signature()==before
changed=copy.deepcopy(accepted);next(g for g in changed['groups'] if g['id']=='anonymous-01')['deleted']=True
apply(changed)
assert not any(o.type=='LIGHT' and not o.hide_render for o in bpy.context.scene.objects)
assert signature()==before
assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
(root/'replay-verification.json').write_text(json.dumps(dict(status='passed',position=list(expected),
    tests=['measured emitter location','group translation and rotation exactly once','emission direction','deleted group disables emitter','mesh preservation','source hash preservation'])),encoding='utf-8')
print('Real Blender replay passed')
