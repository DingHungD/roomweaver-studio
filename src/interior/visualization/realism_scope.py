"""Combine per-view evidence without confusing repeated shot IDs or shared objects."""
import copy
import json


def combine_inventories(rooms):
    if not rooms:raise ValueError('全案精修至少需要一個含效果圖的觀看點')
    rooms=copy.deepcopy(rooms)
    for room in rooms:
        pid=room['point']['id']
        for camera in room.get('details',{}).get('cameras',[]):
            camera['id']=pid+':'+camera['id'];camera['point_id']=pid
        for check in room.get('details',{}).get('camera_checks',[]):check['point_id']=pid
    def unique(values):
        result=[];seen=set()
        for value in values:
            key=json.dumps(value,sort_keys=True)
            if key not in seen:seen.add(key);result.append(value)
        return result
    objects={};lights={};details={}
    for room in rooms:
        for obj in room['objects']:
            if obj['id'] not in objects:objects[obj['id']]=copy.deepcopy(obj)
            else:
                target=objects[obj['id']]
                target['editable']=target['editable'] and obj['editable']
                target['screen_regions']=unique(target.get('screen_regions',[])+obj.get('screen_regions',[]))
        for light in room['lights']:lights[light['id']]=light
        for key,value in room.get('details',{}).items():
            if isinstance(value,list):details[key]=unique(details.get(key,[])+value)
        ceiling=details.setdefault('ceiling',{'options':[],'skipped':[]})
        for key in ('options','skipped'):ceiling[key]=unique(ceiling[key]+room.get('details',{}).get('ceiling',{}).get(key,[]))
    return dict(point=rooms[0]['point'],rooms=rooms,objects=list(objects.values()),lights=list(lights.values()),details=details,scope='all_viewpoints')


def manifest_for_point(manifest,point_id):
    value=copy.deepcopy(manifest)
    value['images']=[e for e in manifest['images'] if e['file'].startswith(point_id+'-')]
    if not value['images']:raise ValueError('觀看點缺少試圖：'+point_id)
    value['rendered_cameras']=[e for e in manifest.get('rendered_cameras',[]) if e['file'].startswith(point_id+'-')]
    return value
