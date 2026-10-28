"""Conservative native geometry guards shared by finishing and door opening."""
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from realism_details import box


def bounds(objects):
    boxes=[box(o) for o in objects]
    return [Vector([fn(b[n][i] for b in boxes) for i in range(3)]) for n,fn in enumerate((min,max))]


class Obstacles:
    """Exact surface overlap after cheap bounds; conservative solid containment."""
    def __init__(self, excluded=()):
        bpy.context.view_layer.update()
        self.deps=bpy.context.evaluated_depsgraph_get()
        self.objects=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render and o not in excluded]
        self.boxes={o.name:box(o) for o in self.objects};self.trees={}

    def tree(self,obj):
        evaluated=obj.evaluated_get(self.deps);mesh=evaluated.to_mesh()
        try:return BVHTree.FromPolygons([obj.matrix_world@v.co for v in mesh.vertices],[list(p.vertices) for p in mesh.polygons])
        finally:evaluated.to_mesh_clear()

    def collisions(self,objects):
        bpy.context.view_layer.update();result=set()
        for obj in objects:
            lo,hi=box(obj);tree=None
            for other in self.objects:
                a,b=self.boxes[other.name]
                if any(min(hi[i],b[i])-max(lo[i],a[i])<.003 for i in range(3)):continue
                if tree is None:tree=self.tree(obj)
                if other.name not in self.trees:self.trees[other.name]=self.tree(other)
                ot=self.trees[other.name]
                if tree.overlap(ot):result.add(other.name);continue
                # Closed solid completely containing the object (no surface crossing).
                p=(lo+hi)/2;hit=ot.ray_cast(p,Vector((.871,.341,.354)).normalized())
                if hit[0] is not None and hit[1].dot(Vector((.871,.341,.354)))>0:result.add(other.name)
        return result

    def ray(self,origin,direction,distance):
        nearest=None
        for obj in self.objects:
            if obj.name not in self.trees:self.trees[obj.name]=self.tree(obj)
            hit=self.trees[obj.name].ray_cast(origin,direction,distance)
            if hit[0] is not None and (nearest is None or hit[3]<nearest[0]):nearest=(hit[3],obj,hit[0],hit[1])
        return nearest


def selected_roof_trees(design,by_id,floors,walls):
    owners={k:g for g in design['groups'] for k in g['children']}
    guard=Obstacles();roofs=[]
    for obj in guard.objects:
        if obj in floors or obj in walls or obj.get('studio_opening_complete') or obj.get('studio_refined_from') or obj.get('studio_fixture_detail'):continue
        group=owners.get(obj.get('studio_id'),{})
        label=(obj.name+' '+group.get('name','')).lower()
        if group and group.get('method')!='structural_ceiling' and not any(t in label for t in ('ceiling','天花')):continue
        if (group.get('asset_requirements') or {}).get('purpose')=='light' or '燈具' in label:continue
        roofs.append((obj,guard.tree(obj)))
    return roofs
