import sys
sys.path.insert(0,sys.argv[-1])
import bpy
from opening_details import assembly
for kind in ('single','double','sliding','frame'):
 for side in ('positive','negative'):
  bpy.ops.wm.read_factory_settings(use_empty=True)
  result=assembly(dict(id='synthetic',name='door',role='door',points=[[0,0],[1.2,0]],base=0,height=2.1,control=dict(kind=kind,side=side,swing='negative',hinge='auto')),'a'*64)
  leaves=[o for o in bpy.context.scene.objects if 'leaf-' in o.name]
  assert len(leaves)==(0 if kind=='frame' else 2 if kind in ('double','sliding') else 1)
  assert result['opening']['state']=='open',result
  if kind in ('single','double'):
   for obj in leaves:
    center=sum((obj.matrix_world@v.co for v in obj.data.vertices),start=__import__('mathutils').Vector())/8
    assert (center.y>0)==(side=='positive'),(kind,side,center)
print('DOOR_TYPES_SIDES_PASSED')

# Fold both halves around either jamb; the free edge stays on the track.
for hinge in ('A','B'):
 for side in ('positive','negative'):
  bpy.ops.wm.read_factory_settings(use_empty=True)
  item=dict(id='fold',name='bath-fold',role='door',points=[[0,0],[1.2,0]],base=0,height=2.1,control=dict(kind='folding',side=side,swing='auto',hinge=hinge))
  result=assembly(item,'a'*64)
  assert result['opening']['state']=='open',result
  leaves=[o for o in bpy.context.scene.objects if 'leaf-' in o.name]
  assert len(leaves)==2
  for o in leaves:
   center=sum((o.matrix_world@v.co for v in o.data.vertices),start=__import__('mathutils').Vector())/8
   assert (center.y>0)==(side=='positive'),(hinge,side,center)
  from completion_geometry import Obstacles
  guard=Obstacles([o for o in bpy.context.scene.objects if o!=leaves[0]])
  assert not guard.tree(leaves[0]).overlap(guard.tree(leaves[1])),('folded leaves overlap',hinge,side)
  # A solid obstacle across the opening must reject the sweep, not silently flip.
  bpy.ops.mesh.primitive_cube_add(size=1,location=(.6,0,1))
  bpy.context.object.dimensions=(1.3,.5,2)
  result=assembly(dict(item,id='blocked'),'b'*64)
  assert result['opening']['state']=='blocked'
print('FOLDING_SIDES_HINGES_COLLISIONS_PASSED')

# An obstacle beyond an initially safe sweep limits the angle without changing direction.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=1,location=(.4,.8,1))
bpy.context.object.dimensions=(.25,.15,2)
item=dict(id='limited',name='limited',role='door',points=[[0,0],[1.2,0]],base=0,height=2.1,control=dict(kind='single',side='positive',swing='positive',hinge='A'))
r=assembly(item,'c'*64)
assert r['opening']['state']=='limited',r
assert 0<r['opening']['angle']<90,r
assert r['opening']['hinge']=='inferred-A'
assert r['width']==1.2 and r['height']==2.1
assert r['preview_parts'] and all(len(p['vertices'])==8 for p in r['preview_parts'])
print('LIMITED_SWEEP_PREVIEW_PASSED')

# Centred resizing leaves the source endpoints untouched and fills both side gaps.
bpy.ops.wm.read_factory_settings(use_empty=True)
points=[[0,0],[.9,0]]
item=dict(id='fit',name='fit',role='door',points=points,base=0,height=2.1,control=dict(kind='single',side='positive',swing='positive',assembly_width=.85))
r=assembly(item,'d'*64)
assert points==[[0,0],[.9,0]] and abs(r['width']-.85)<1e-8
assert len([o for o in bpy.data.objects if 'infill-' in o.name])==2
assert r['opening']['state']=='open'
assert r['passage_check']['dimension_changed']
assert r['passage_check']['projected_clear_width']>=.7
print('CENTRED_WIDTH_FIT_PASSED')
