"""Synthetic deletion must suppress native source and manually added doors."""
import sys
sys.path.insert(0,sys.argv[-1])
import bpy
from opening_details import add_openings
bpy.ops.mesh.primitive_cube_add()
o=bpy.context.object;o['source_entity_id']='old';o['studio_id']='old-part'
manual=dict(id='new',name='New',points=[[0,0],[1,0]],height=2.1)
design=dict(opening_details=True,groups=[],manual_doors=[manual],door_controls=[dict(opening_id='old',deleted=True),dict(opening_id='new',deleted=True)])
r=add_openings(design,{'old-part':o},dict(items=[dict(id='old',name='Existing')]))
assert o.hide_render and o.hide_get()
assert {i['id'] for i in r['items'] if i['status']=='deleted'}=={'old','new'}
assert len(bpy.data.objects)==4  # factory camera/light plus synthetic cube and original cube
print('DELETED_DOORS_SUPPRESSED')
