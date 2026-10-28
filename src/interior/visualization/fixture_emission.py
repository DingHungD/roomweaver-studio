"""Orient a flat ceiling fixture using measured emitting faces, not its name."""
import math
from mathutils import Matrix, Vector


def emission_strength(material):
    if not material or not material.use_nodes:
        return 0.
    nodes=material.node_tree.nodes
    outputs=[n for n in nodes if n.type in ('OUTPUT_MATERIAL','OUTPUT_LIGHT') and getattr(n,'is_active_output',True)]
    reachable=set()
    def visit(node):
        if node in reachable:return
        reachable.add(node)
        for socket in node.inputs:
            for link in socket.links:visit(link.from_node)
    for node in outputs:visit(node)
    values=[]
    for node in reachable:
        socket=node.inputs.get('Strength') if node.type=='EMISSION' else node.inputs.get('Emission Strength') if node.type=='BSDF_PRINCIPLED' else None
        if socket:
            # Texture-driven intensity needs different evidence; don't guess.
            if socket.is_linked:return None
            value=float(socket.default_value)
            if not math.isfinite(value):return None
            values.append(max(0,value))
    return sum(values)


def measure(meshes):
    total=0.;direction=Vector();count=0
    for obj in meshes:
        world=obj.matrix_world
        strengths=[emission_strength(m) for m in obj.data.materials]
        obj.data.calc_loop_triangles()
        for tri in obj.data.loop_triangles:
            strength=strengths[tri.material_index] if tri.material_index<len(strengths) else 0
            if strength is None:return dict(status='unknown',reason='發光強度由貼圖或節點控制，保留原方向')
            if strength<=0:continue
            a,b,c=[world@obj.data.vertices[i].co for i in tri.vertices]
            cross=(b-a).cross(c-a);weight=cross.length*.5*strength
            if weight<=1e-12:continue
            direction+=cross.normalized()*weight;total+=weight;count+=1
    if not count or total<=1e-12:return dict(status='unknown',reason='沒有可直接量測的發光面，保留原方向')
    return dict(status='measured',weighted_normal_z=direction.z/total,emitting_triangles=count,
                method='world_triangle_area_times_unlinked_emission_strength')


def orient(meshes,mode):
    before=measure(meshes)
    result=dict(before=before,corrected=False,rotation_x=0)
    if mode not in ('surface','recessed'):
        return dict(result,reason='吊燈可能有多個發光方向，保留原模型吊掛姿態')
    if before.get('weighted_normal_z',0)<.7:
        return dict(result,after=before,reason='主要發光面未明確朝上，保留原姿態')
    corners=[obj.matrix_world@Vector(c) for obj in meshes for c in obj.bound_box]
    lo=Vector([min(v[i] for v in corners) for i in range(3)]);hi=Vector([max(v[i] for v in corners) for i in range(3)])
    if hi.z-lo.z>min(hi.x-lo.x,hi.y-lo.y)*.6:
        return dict(result,after=before,reason='非扁平吸頂燈，不自動翻轉立體燈具')
    center=(lo+hi)*.5
    transform=Matrix.Translation(center)@Matrix.Rotation(math.pi,4,'X')@Matrix.Translation(-center)
    for obj in meshes:obj.matrix_world=transform@obj.matrix_world
    after=measure(meshes)
    if after.get('weighted_normal_z',0)>-.7:
        raise ValueError('燈具發光面翻轉後重驗未通過，保留原件')
    return dict(result,corrected=True,rotation_x=180,after=after,reason='主要發光面朝上，繞燈體中心翻轉後重新安裝；未更改尺寸或水平開向')
