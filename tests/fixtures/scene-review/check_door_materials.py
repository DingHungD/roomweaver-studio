import sys
sys.path.insert(0,sys.argv[-1])
import bpy
from opening_details import assembly
item=dict(id='door-test',name='Door',role='door',points=[[0,0],[.9,0]],height=2.1,base=0,control=dict(kind='folding',hinge='A',side='positive',swing='auto',materials={'leaf-0':dict(color='#336699',roughness=.82)}))
result=assembly(item,'a'*64)
leaf=next(o for o in bpy.data.objects if o.name=='Door · leaf-0')
other=next(o for o in bpy.data.objects if o.name=='Door · leaf-1')
frame=next(o for o in bpy.data.objects if o.name=='Door · head')
s=leaf.active_material.node_tree.nodes.get('Principled BSDF')
assert abs(s.inputs['Roughness'].default_value-.82)<1e-6
assert abs(s.inputs['Base Color'].default_value[0]-.03310477)<1e-6
assert leaf.active_material!=other.active_material and leaf.active_material!=frame.active_material
assert result['width']==.9 and result['height']==2.1
print('DOOR_PART_MATERIALS_PASSED')
