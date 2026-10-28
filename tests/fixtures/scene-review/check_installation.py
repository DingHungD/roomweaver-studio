"""Synthetic corner in a different room, no catalog/network or case-specific IDs."""
import sys
sys.path.insert(0,sys.argv[-1])
import bpy
from installation_replacement import apply
import installation_replacement as module
bpy.ops.wm.read_factory_settings(use_empty=True)
by={};groups=[]
def cube(name,pos,size,kind=None):
    bpy.ops.mesh.primitive_cube_add(size=1,location=pos);obj=bpy.context.object;obj.name=name;obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);obj['studio_id']=name
    if kind:
        by[name]=obj;groups.append(dict(id=name,name=name,children=[name],method='structural_'+kind,deleted=False))
    return obj
cube('floor',(1,1,-.1),(2,2,.2),'floor');cube('east',(2.05,1,1.5),(.1,2,3),'wall');cube('north',(1,2.05,1.5),(2,.1,3),'wall')
original=cube('old-shower',(1.64,1.64,1),(.7,.7,2));by['old-shower']=original
shower=dict(id='new-home-shower',name='shower',children=['old-shower'],asset_requirements={'purpose':'shower','dimension_source':'unknown'},deleted=False);groups.append(shower)
def load(entry):return [cube('candidate-'+entry['asset_id'],(0,0,1),(.9,.9,2) if entry['asset_id']=='too-large' else (.65,.65,2))]
module.load=load
scene=dict(groups=groups,installation_replacements=[dict(group_id=shower['id'],bundle='a'*32)])
assets={shower['id']:[dict(name='too large',asset_id='too-large',url='fixture://bad'),dict(name='fitting',asset_id='fit',url='fixture://good')]}
before=tuple(original.dimensions)
report=apply(scene,by,assets,dict(items=[],remaining=[]))['items'][0]
assert report['status']=='prepared' and len(report['attempts'])==2 and report['selected']['asset_id']=='fit',report
assert original.hide_render and tuple(original.dimensions)==before
for o in list(bpy.data.objects):
    if o.get('studio_installation_candidate'):bpy.data.objects.remove(o,do_unlink=True)
original.hide_render=False;original.hide_set(False)
shower['asset_requirements'].update(dimension_source='confirmed',dimensions=[.7,.7,2])
report=apply(scene,by,assets,dict(items=[],remaining=[]))['items'][0]
assert report['status']=='unresolved' and not original.hide_render,report
print('INSTALLATION_RETRY_AND_CONFIRMED_DIMENSIONS_PASSED')
