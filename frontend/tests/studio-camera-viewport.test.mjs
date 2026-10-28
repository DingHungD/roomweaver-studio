import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {frameViewport,frameShotViewport} from '../src/features/visualization/cameraViewport.ts';

test('overlay-safe projection centers the target and preserves camera pose and zoom on collapse',()=>{
 for(const camera of [new THREE.OrthographicCamera(-10,10,8,-8,.1,1000),new THREE.PerspectiveCamera(55,1,.1,1000)]){
  camera.position.set(2,9,12);const target=new THREE.Vector3(2,0,0);camera.lookAt(target);camera.zoom=1.7;camera.updateMatrixWorld();
  const position=camera.position.clone(),rotation=camera.quaternion.clone();
  for(const insets of [{left:24,right:320,top:170,bottom:90},{left:24,right:24,top:50,bottom:90}]){
   const safe=frameViewport(camera,1200,800,insets);
   const p=target.clone().project(camera);
   assert.ok(Math.abs((p.x+1)*600-safe.x)<1e-6);
   assert.ok(Math.abs((1-p.y)*400-safe.y)<1e-6);
   assert.ok(camera.position.equals(position));assert.ok(camera.quaternion.equals(rotation));assert.equal(camera.zoom,1.7);
   const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2(p.x,p.y),camera);
   assert.ok(ray.ray.distanceToPoint(target)<1e-6,'picking follows shifted projection');
  }
 }
});

test('Blender sensor corners and vertical shift fit the visible preview without moving pose',()=>{
 for(const aspect of ['4:3','16:9'])for(const shift_y of [-.25,0,.12]){
  const camera=new THREE.PerspectiveCamera(55,1,.02,2000);camera.updateMatrixWorld();
  const ratio=aspect==='16:9'?16/9:4/3,lens=32;
  const frame=frameShotViewport(camera,1200,800,{left:24,right:24,top:350,bottom:90},{aspect,lens,shift_y});
  for(const x of [-1,1])for(const y of [-1,1]){
   const point=new THREE.Vector3(x*18/lens,y*18/ratio/lens+shift_y*36/lens,-1).project(camera);
   const px=(point.x+1)*600,py=(1-point.y)*400;
   assert.ok(Math.abs(px-(frame.left+(x+1)/2*frame.width))<1e-6);
   assert.ok(Math.abs(py-(frame.top+(1-y)/2*frame.height))<1e-6);
  }
  assert.deepEqual(camera.position.toArray(),[0,0,0]);
 }
});
