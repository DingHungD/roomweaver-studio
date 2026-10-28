import copy,sys
from pathlib import Path
import bpy

root=Path(sys.argv[sys.argv.index('--')+1]);sys.path.insert(0,sys.argv[-1])
from scene_review_checks import validate_moves,override_roughness
bpy.ops.wm.open_mainfile(filepath=str(root/'lit.blend'))
objects={o.get('studio_id'):o for o in bpy.data.objects if o.type=='MESH'}
groups=[dict(id=k,name=k,children=[k],translation=[0,0,0],rotation=0,rotation_pivot=[0,0,0],deleted=False,placement_constraints=dict(area=[-4,-4,4,4],keep_out=[])) for k in objects]
before=dict(groups=groups);after=copy.deepcopy(before)
next(g for g in after['groups'] if g['id']=='table')['translation']=[.1,0,0]
assert validate_moves(after,before,objects)['checked_groups']==['table']
next(g for g in after['groups'] if g['id']=='table')['translation']=[2.8,0,0]
try:validate_moves(after,before,objects)
except ValueError:pass
else:raise AssertionError('must reject newly intersecting wall')
table=objects['table'];original=table.active_material;rough=original.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value
override_roughness(table,.8)
assert table.active_material!=original
assert original.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value==rough
assert abs(table.active_material.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value-.8)<1e-6
nodes=table.active_material.node_tree.nodes;noise=nodes.new('ShaderNodeTexNoise');table.active_material.node_tree.links.new(noise.outputs['Fac'],nodes.get('Principled BSDF').inputs['Roughness'])
try:override_roughness(table,.9)
except ValueError:pass
else:raise AssertionError('must keep linked texture nodes')
print('NATIVE_SCENE_REVIEW_CHECKS_PASSED')
