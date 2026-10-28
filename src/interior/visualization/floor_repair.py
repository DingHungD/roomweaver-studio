"""Add reviewed floor patches while preserving all existing geometry/materials."""
import bpy
from surface_uv import ensure_uv


def add_patches(proposal,objects,identify):
    # Older imports have stable entity IDs but predate the studio_role property.
    source_ids={f['id'] for f in proposal['source_floors']}
    sources=[o for o in objects if o.get('source_entity_id') in source_ids and not o.get('floor_repair_id')]
    by_source={o.get('source_entity_id'):o for o in sources}
    if len(sources)!=len(by_source):raise ValueError('地板來源 ID 重複，不能安全選擇補片依據')
    if len(by_source)!=len(source_ids):raise ValueError('地板來源對照不完整，保留原件')
    # The plan cannot authorize patching a floor subsequently edited in Blender.
    for f in proposal['source_floors']:
        obj=by_source.get(f['id'])
        if obj is None:raise ValueError('地板與確認平面無法對應；請重新核對來源')
        vertices=[obj.matrix_world@v.co for v in obj.data.vertices]
        top=max(v.z for v in vertices)
        if abs(top)>.001:raise ValueError('地板有高差，不能依舊平面補齊')
        actual={(round(v.x,4),round(v.y,4)) for v in vertices if abs(v.z-top)<.0001}
        expected={(round(x,4),round(y,4)) for x,y in f['points']}
        if actual!=expected:raise ValueError('目前地板形狀與確認平面不同；保留原件，請重新檢查')
    made=[]
    for patch in proposal['patches']:
        donor=by_source[patch['donor_id']]
        # Append disconnected faces to a new mesh, not to any original floor.
        vertices=[];faces=[]
        for tri in patch['triangles']:
            offset=len(vertices)
            if sum(tri[i][0]*tri[(i+1)%3][1]-tri[(i+1)%3][0]*tri[i][1] for i in range(3))<0:tri=list(reversed(tri))
            vertices.extend((x,y,z) for z in (-patch['height'],0) for x,y in tri)
            faces.extend(tuple(offset+i for i in face) for face in ((2,1,0),(3,4,5),(0,1,4,3),(1,2,5,4),(2,0,3,5)))
        mesh=bpy.data.meshes.new(patch['id']);mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new('floor-'+patch['id'],mesh);bpy.context.scene.collection.objects.link(obj)
        obj['floor_repair_id']=patch['id'];obj['studio_role']='floor';obj['source_entity_id']=patch['id']
        obj['room_id']=donor.get('room_id','interior');obj['assembly_id']=donor.get('assembly_id','floor')
        for mat in donor.data.materials:obj.data.materials.append(mat)
        # This path only accepts single-material sources, so new triangles cannot
        # silently choose a different material slot from their neighbour.
        if len(donor.data.materials)!=1:raise ValueError('鄰接地板含多種材質，請先指定補片材質')
        ensure_uv(obj);identify(obj,patch,donor);made.append(obj)
    return made


def verify_patches(proposal,objects):
    """Reject the conversion if emitted top faces do not cover the proposed seam."""
    by_id={o.get('floor_repair_id'):o for o in objects}
    if len(objects)!=len(proposal['patches']):raise ValueError('地板自動補齊未完整產生，停止交接')
    total=0
    for patch in proposal['patches']:
        obj=by_id.get(patch['id'])
        if obj is None:raise ValueError('地板自動補齊缺少對應元件，停止交接')
        top=[p for p in obj.data.polygons if p.normal.z>.99]
        area=sum(p.area for p in top)
        if abs(area-patch['area'])>max(.00001,patch['area']*.0001):
            raise ValueError('地板補齊後的實際覆蓋面積不符，停止交接')
        uv=obj.data.uv_layers.active
        if uv is None or len(obj.data.materials)!=1:raise ValueError('地板補片缺少材質或 UV，停止交接')
        total+=area
    return dict(status='repaired_and_verified',patch_count=len(objects),added_area=total)
