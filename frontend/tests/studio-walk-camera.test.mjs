import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {moveWalkCamera,lookWalkCamera} from '../src/features/visualization/walkCamera.ts';

test('strafing at every heading and pitch stays level and never changes viewing direction',()=>{
  for(const yaw of [0,.7,Math.PI,-2])for(const pitch of [-1.4,0,1.4]){
    const camera=new THREE.PerspectiveCamera();camera.position.set(2,1.6,3);camera.rotation.set(pitch,yaw,0,'YXZ');
    const original=camera.quaternion.clone(),start=camera.position.clone();
    moveWalkCamera(camera,0,1,0,.5);
    assert.equal(camera.position.y,1.6);assert.ok(camera.quaternion.equals(original));
    const delta=camera.position.clone().sub(start);
    assert.ok(delta.distanceTo(new THREE.Vector3(Math.cos(yaw),0,-Math.sin(yaw)))<1e-8);
    moveWalkCamera(camera,0,-1,0,.5);assert.ok(camera.position.distanceTo(start)<1e-8);
  }
});
test('forward and diagonal movement stay on floor and vertical motion is explicit',()=>{
  const camera=new THREE.PerspectiveCamera();camera.rotation.set(1.2,.8,0,'YXZ');camera.position.y=1.6;
  moveWalkCamera(camera,1,1,0,1);assert.equal(camera.position.y,1.6);assert.ok(Math.abs(Math.hypot(camera.position.x,camera.position.z)-2)<1e-8);
  moveWalkCamera(camera,0,0,1,1);assert.equal(camera.position.y,3.1);
});
test('repeated mouse look keeps zero roll and clamps pitch',()=>{
  const camera=new THREE.PerspectiveCamera();camera.rotation.set(.5,.3,.4,'YXZ');
  for(let i=0;i<100;i++){lookWalkCamera(camera,12,-20);const angles=new THREE.Euler().setFromQuaternion(camera.quaternion,'YXZ');assert.ok(Math.abs(angles.z)<1e-8);assert.ok(Math.abs(angles.x)<=1.450001);}
});
