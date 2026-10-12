"""One checked model package for every intake route; no renderer-specific UI."""
import json
import math
from pathlib import Path
import struct
from .service import digest
from ..storage import read_json, write_json


def read_glb(path):
    data=Path(path).read_bytes()
    if len(data)<20:raise ValueError('GLB 檔頭不完整')
    magic,version,length,size,kind=struct.unpack_from('<IIIII',data)
    if magic!=0x46546c67 or version!=2 or length!=len(data) or kind!=0x4e4f534a or size>len(data)-20:
        raise ValueError('GLB 2 格式或長度不符')
    return json.loads(data[20:20+size])


def validate_package(folder, persist=False):
    """Recheck bytes and identity before adoption, including resumed jobs."""
    folder=Path(folder);model=read_json(folder/'model.json')
    for key,file in [('native_sha256','model.blend'),('preview_sha256','model.glb')]:
        if model.get(key)!=digest(folder/file):raise ValueError('模型交接雜湊不符：'+file)
    native=model['objects'];ids=[o['id'] for o in native]
    if not ids or len(ids)!=len(set(ids)):raise ValueError('原生模型物件 ID 為空或重複')
    gltf=read_glb(folder/'model.glb')
    nodes=[n for n in gltf.get('nodes',[]) if 'mesh' in n]
    mapped=[n.get('extras',{}).get('studio_id') for n in nodes]
    if not mapped or len(mapped)!=len(set(mapped)) or any(i not in ids for i in mapped):
        raise ValueError('GLB 物件無法唯一對應 Blender 物件')
    if set(model['selectable_ids'])!=set(mapped):raise ValueError('可選取物件索引不一致')
    if not model.get('spatial_check',{}).get('passed'):raise ValueError('缺少 GLB／BLEND 尺度與座標核對')
    for obj in native:
        if not all(math.isfinite(v) for v in obj['center']):raise ValueError('物件座標無效')
    if any(x.get('uri') and not x['uri'].startswith('data:') for x in gltf.get('images',[])+gltf.get('buffers',[])):
        raise ValueError('GLB 引用外部資源，請嵌入貼圖後匯入')
    report=dict(status='passed',native_objects=len(ids),selectable_objects=len(mapped),
        native_only_objects=sorted(set(ids)-set(mapped)),spatial_check=model['spatial_check'],
        render_readiness=model['render_readiness'],native_sha256=model['native_sha256'],preview_sha256=model['preview_sha256'])
    if persist:write_json(folder/'handoff.json',report)
    return report
