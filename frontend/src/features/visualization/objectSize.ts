import * as THREE from 'three';
const cache=new WeakMap<THREE.Object3D,[number,number,number]>();
// Measure once in the assembly's axes; moving/rotating must not change W/D/H.
export function objectSize(group:THREE.Object3D):[number,number,number] {
  const previous=cache.get(group);if(previous)return previous;
  group.updateWorldMatrix(true,true);
  const inverse=group.matrixWorld.clone().invert(),bounds=new THREE.Box3();
  group.traverse(node=>{if(!(node instanceof THREE.Mesh))return;
    if(!node.geometry.boundingBox)node.geometry.computeBoundingBox();if(node.geometry.boundingBox)bounds.union(node.geometry.boundingBox.clone().applyMatrix4(new THREE.Matrix4().multiplyMatrices(inverse,node.matrixWorld)));
  });
  const size=bounds.getSize(new THREE.Vector3()),scale=group.getWorldScale(new THREE.Vector3());
  const value:[number,number,number]=[size.x*Math.abs(scale.x),size.z*Math.abs(scale.z),size.y*Math.abs(scale.y)];
  cache.set(group,value);return value;
}
