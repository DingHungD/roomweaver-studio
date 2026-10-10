import * as THREE from 'three';

/** Move on the world floor plane, independent of pitch; translation never rotates the view. */
export function moveWalkCamera(camera:THREE.Camera,forward:number,sideways:number,vertical:number,dt:number){
  const yaw=new THREE.Euler().setFromQuaternion(camera.quaternion,'YXZ').y;
  const direction=new THREE.Vector3(-Math.sin(yaw),0,-Math.cos(yaw)).multiplyScalar(forward);
  direction.addScaledVector(new THREE.Vector3(Math.cos(yaw),0,-Math.sin(yaw)),sideways);
  if(direction.lengthSq()>1)direction.normalize();
  camera.position.addScaledVector(direction,dt*2);
  camera.position.y+=vertical*dt*1.5;
}

/** Mouse look turns about world up and explicitly removes roll. */
export function lookWalkCamera(camera:THREE.Camera,dx:number,dy:number){
  const angles=new THREE.Euler().setFromQuaternion(camera.quaternion,'YXZ');
  angles.y-=dx*.004;angles.x=THREE.MathUtils.clamp(angles.x-dy*.004,-1.45,1.45);angles.z=0;
  camera.quaternion.setFromEuler(angles);
}
