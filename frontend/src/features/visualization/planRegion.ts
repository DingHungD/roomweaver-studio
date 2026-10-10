import * as THREE from 'three';
import type {AssemblyRuntime} from './assemblyScene';
import type {Scene} from './api';

const outdoor=/(?:^|[-_\s])(exterior|outdoor|neighbor|neighbour|landscape|balcony|terrace|sky|terrain)(?:$|[-_\s])|窗外|鄰棟|室外|陽台|露台/i;
const floorName=/^floor(?:$|[-_\s])|^(地板|地坪)/i;

/** Editor-only envelope. Unknown models fall back to visible bounds, never delete geometry. */
export function planRegion(assembly:AssemblyRuntime,design:Scene,cutHeight=1.3){
  const boxes=new Map<string,THREE.Box3>(),hidden=new Set<string>();
  const footprint=new THREE.Box3();
  for(const spec of design.groups){
    const node=assembly.groups.get(spec.id);if(!node||spec.deleted)continue;
    const box=new THREE.Box3().setFromObject(node);if(box.isEmpty())continue;
    boxes.set(spec.id,box);
    if(outdoor.test(spec.name)){hidden.add(spec.id);continue;}
    if(floorName.test(spec.name))footprint.union(box);
  }
  const bounded=!footprint.isEmpty();
  // Include the perimeter wall thickness without admitting exterior set dressing.
  if(bounded){footprint.min.x-=.18;footprint.min.z-=.18;footprint.max.x+=.18;footprint.max.z+=.18;}
  const bounds=new THREE.Box3();
  for(const [id,box] of boxes){
    const outside=bounded&&(box.max.x<footprint.min.x||box.min.x>footprint.max.x||box.max.z<footprint.min.z||box.min.z>footprint.max.z);
    if(hidden.has(id)||outside||box.min.y>cutHeight){hidden.add(id);continue;}
    bounds.union(box);
  }
  if(bounded){bounds.min.x=footprint.min.x;bounds.max.x=footprint.max.x;bounds.min.z=footprint.min.z;bounds.max.z=footprint.max.z;}
  if(bounds.isEmpty())bounds.setFromCenterAndSize(new THREE.Vector3(),new THREE.Vector3(4,1,4));
  bounds.max.y=Math.min(bounds.max.y,cutHeight);
  const planes=bounded?[
    new THREE.Plane(new THREE.Vector3(1,0,0),-bounds.min.x),
    new THREE.Plane(new THREE.Vector3(-1,0,0),bounds.max.x),
    new THREE.Plane(new THREE.Vector3(0,0,1),-bounds.min.z),
    new THREE.Plane(new THREE.Vector3(0,0,-1),bounds.max.z),
  ]:[];
  return {bounds,hidden,planes,bounded};
}
