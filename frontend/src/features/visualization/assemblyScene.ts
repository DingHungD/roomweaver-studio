import * as THREE from 'three';
import type {Scene} from './api';
export type AssemblyRuntime={root:THREE.Object3D;groups:Map<string,THREE.Group>;parts:Map<string,THREE.Object3D>;bases:Map<string,THREE.Vector3>;materials:THREE.Material[]};
export function assemble(root:THREE.Object3D,design:Scene):AssemblyRuntime {
  root.updateMatrixWorld(true);
  const groups=new Map<string,THREE.Group>(),parts=new Map<string,THREE.Object3D>(),bases=new Map<string,THREE.Vector3>();
  root.traverse(o=>{if(o.userData.studio_id)parts.set(o.userData.studio_id,o);});
  for(const spec of design.groups||[]){
    const group=new THREE.Group();group.userData.group_id=spec.id;root.add(group);
    const bounds=new THREE.Box3();spec.children.forEach(id=>{const part=parts.get(id);if(part)bounds.expandByObject(part);});
    const center=bounds.isEmpty()?new THREE.Vector3():bounds.getCenter(new THREE.Vector3());
    group.position.copy(root.worldToLocal(center.clone()));group.updateMatrixWorld(true);
    spec.children.forEach(id=>{const part=parts.get(id);if(part)group.attach(part);});
    groups.set(spec.id,group);bases.set(spec.id,group.position.clone());
  }
  return {root,groups,parts,bases,materials:[]};
}
export function applyDesign(runtime:AssemblyRuntime,design:Scene){
  for(const group of design.groups||[]){const node=runtime.groups.get(group.id);if(!node)continue;
    const delta=new THREE.Vector3(group.translation[0],group.translation[2],-group.translation[1]);
    node.position.copy(runtime.bases.get(group.id)!).add(delta);node.visible=!group.deleted;
  }
  for(const spec of design.objects){const part=runtime.parts.get(spec.id);if(!part)continue;
    part.traverse(o=>{if(!(o instanceof THREE.Mesh))return;
      o.userData.originalMaterial??=o.material;
      const key=spec.material.color?`${spec.material.color}:${spec.material.roughness}`:'';
      if(o.userData.materialKey===key)return;
      if(o.userData.studioMaterial){o.userData.studioMaterial.dispose();o.userData.studioMaterial=null;}
      if(key){const m=new THREE.MeshStandardMaterial({color:spec.material.color!,roughness:spec.material.roughness});o.userData.studioMaterial=m;runtime.materials.push(m);o.material=m;}
      else o.material=o.userData.originalMaterial;
      o.userData.materialKey=key;
    });
  }
  runtime.root.updateMatrixWorld(true);
}
export function visible(object:THREE.Object3D):boolean {let o:THREE.Object3D|null=object;while(o){if(!o.visible)return false;o=o.parent;}return true;}
