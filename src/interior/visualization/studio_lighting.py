"""Blender lighting proposals and replay; no modification of source files."""
import math
import hashlib
import bpy
from mathutils import Vector


def restore_world(source):
    if not source or not source.get('world'):return
    with bpy.data.libraries.load(source['path'],link=False) as (available,loaded):
        name=source.get('world')
        if name not in available.worlds:raise ValueError('照明來源 World 不存在')
        loaded.worlds=[name]
    bpy.context.scene.world=loaded.worlds[0]


def propose(design, source=None):
    scene=bpy.context.scene
    native=[o for o in scene.objects if o.type=='LIGHT']
    origin='native'
    if not any(not o.hide_render and o.data.energy>0 for o in native) and source:
        with bpy.data.libraries.load(source['path'],link=False) as (available,loaded):
            loaded.objects=list(available.objects)
        # Library-loaded objects have unevaluated world matrices until linked and updated.
        # Include their dependencies for parenting/constraints; this inspection process never saves them.
        for obj in loaded.objects:
            if obj:scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        native=[o for o in loaded.objects if o and o.type=='LIGHT']
        origin='restored'
    lights=[]
    groups={g['id']:g for g in design.get('groups',[])}
    child_groups={c:g['id'] for g in groups.values() for c in g['children']}
    for obj in native:
        data=obj.data
        if data.use_nodes:
            raise ValueError('光源 '+obj.name+' 使用自訂節點；本輪自動配置只支援基本光源，請保留原模型照明以免丟失設定。')
        group=child_groups.get(obj.parent.get('studio_id')) if obj.parent else None
        lights.append(dict(id=hashlib.sha256(obj.name.encode()).hexdigest()[:24],name=obj.name,kind=data.type,
            position=list(obj.matrix_world.translation),rotation=list(obj.matrix_world.to_euler()),power=data.energy,
            color=list(data.color),size=max(.01,min(10,getattr(data,'size',getattr(data,'shadow_soft_size',.1)))),
            angle=math.degrees(data.spot_size) if data.type=='SPOT' else 90,
            shape=data.shape if data.type=='AREA' else 'DISK',size_y=max(.01,min(10,getattr(data,'size_y',1))),
            sun_angle=data.angle if data.type=='SUN' else .00918,spot_blend=data.spot_blend if data.type=='SPOT' else .5,
            enabled=not obj.hide_render,locked=False,group_id=group,origin=origin))
    notes=[]
    if not any(l['enabled'] and l['power']>0 for l in lights):
        # Fallback proposals use confirmed viewpoints and real ceiling ray hits, not invented room bounds.
        graph=bpy.context.evaluated_depsgraph_get()
        for point in design['viewpoints']:
            eye=Vector(point['eye'])
            hit,pos,normal,*_=scene.ray_cast(graph,eye,Vector((0,0,1)),distance=6)
            if not hit or pos.z-eye.z<.35:
                notes.append(point['name']+'：沒有可靠天花位置，請手動放置光源。');continue
            position=pos-Vector((0,0,.15))
            if any(l['enabled'] and l['power']>0 and (Vector(l['position'])-position).length<2 for l in lights):continue
            lights.append(dict(id='ceiling-'+point['id'],name=point['name']+' · 建議天花補光',kind='AREA',
                position=list(position),rotation=[0,0,0],power=180,color=[1,.85,.68],size=1,
                angle=90,enabled=True,locked=False,group_id=None,origin='proposal'))
        if not lights:notes.append('請先設定室內觀看點，或手動新增光源。')
    # Existing user locks survive reconfiguration. Do not duplicate a locked native ID.
    locked=[l for l in design.get('lighting_setup',{}).get('lights',[]) if l.get('locked')]
    lights=[l for l in lights if l['id'] not in {v['id'] for v in locked}]+locked
    return dict(enabled=True,mode='existing',exposure=design.get('lighting_setup',{}).get('exposure',scene.view_settings.exposure),
        auto_adjust=True,agent_review=False,lights=lights),notes


def apply(design, source=None):
    setup=design.get('lighting_setup',{})
    if not setup.get('enabled'):return
    scene=bpy.context.scene
    if source:restore_world(source)
    # Replace the managed lighting set as a whole, preventing imported/generated duplicates.
    for obj in list(scene.objects):
        if obj.type=='LIGHT':obj.hide_render=True
    mode=setup.get('mode','existing')
    if mode!='existing':
        world=bpy.data.worlds.new('Studio environment');world.use_nodes=True;scene.world=world
        bg=world.node_tree.nodes.get('Background');bg.inputs['Color'].default_value=(.8,.88,1,1)
        bg.inputs['Strength'].default_value=.25 if mode=='day' else 0
    scene.view_settings.exposure=setup.get('exposure',0)
    groups={g['id']:g for g in design.get('groups',[])}
    for spec in setup['lights']:
        group=groups.get(spec.get('group_id'))
        if not spec['enabled'] or (group and group.get('deleted')):continue
        if mode=='indoor' and spec['kind']=='SUN':continue
        data=bpy.data.lights.new('Studio '+spec['id'],spec['kind'])
        data.energy=spec['power'];data.color=spec['color']
        if data.type=='AREA':data.shape=spec.get('shape','DISK');data.size=spec['size'];data.size_y=spec.get('size_y',spec['size'])
        elif data.type in ('POINT','SPOT'):data.shadow_soft_size=spec['size']/2
        if data.type=='SPOT':data.spot_size=math.radians(spec['angle']);data.spot_blend=spec.get('spot_blend',.5)
        if data.type=='SUN':data.angle=spec.get('sun_angle',.00918)
        obj=bpy.data.objects.new('Studio '+spec['id'],data);scene.collection.objects.link(obj)
        obj.location=Vector(spec['position'])+Vector(group.get('translation',[0,0,0]) if group else [0,0,0])
        obj.rotation_euler=spec['rotation'];obj['studio_light_id']=spec['id']
    bpy.context.view_layer.update()
