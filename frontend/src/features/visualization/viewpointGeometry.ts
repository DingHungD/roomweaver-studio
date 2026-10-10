import * as THREE from 'three';

/** Blender coordinates and camera angles shared by the plan and live preview. */
export function eyeVector(eye:readonly number[]){return new THREE.Vector3(eye[0],eye[2],-eye[1]);}
export function shotDirection(yaw:number,pitch:number){
  const y=THREE.MathUtils.degToRad(yaw),p=THREE.MathUtils.degToRad(pitch);
  return new THREE.Vector3(Math.cos(y)*Math.cos(p),Math.sin(p),-Math.sin(y)*Math.cos(p));
}
export function planPosition(camera:THREE.Camera,x:number,y:number,width:number,height:number):[number,number]|null{
  const ray=new THREE.Raycaster();
  camera.updateMatrixWorld();
  ray.setFromCamera(new THREE.Vector2(x/width*2-1,1-y/height*2),camera);
  const hit=ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0,1,0),0),new THREE.Vector3());
  return hit?[hit.x,-hit.z]:null;
}
