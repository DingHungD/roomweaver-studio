import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {createPlanLighting} from '../src/features/visualization/planLighting.ts';
import {sectionGeometry,PlanCaps} from '../src/features/visualization/planCaps.ts';

function area(geometry){
  let sum=0;const p=geometry.getAttribute('position');
  for(let i=0;i<p.count;i+=3){const [a,b,c]=[0,1,2].map(j=>new THREE.Vector3().fromBufferAttribute(p,i+j));sum+=b.sub(a).cross(c.sub(a)).length()/2;}return sum;
}
test('neutral plan lighting is bounded and fits shifted buildings without changing total light',()=>{
  const rig=createPlanLighting(),bounds=new THREE.Box3(new THREE.Vector3(90,0,90),new THREE.Vector3(100,1.3,100));rig.fit(bounds);
  const lights=rig.root.children.filter(o=>o instanceof THREE.DirectionalLight);
  assert.equal(lights.length,4);assert.equal(lights.reduce((v,l)=>v+l.intensity,0),2.6);
  for(const light of lights){assert.equal(light.target.position.x,95);assert.equal(light.target.position.z,95);assert.equal(light.shadow.mapSize.x,1024);assert.ok(light.shadow.camera.far>light.position.y);}
  rig.dispose();assert.equal(rig.root.children.length,0);
});
test('wall sections follow rotated/translated geometry without altering the source mesh',()=>{
  const mesh=new THREE.Mesh(new THREE.BoxGeometry(4,3,.2));mesh.position.set(5,1,6);mesh.rotation.y=.6;mesh.updateMatrixWorld();
  const original=Array.from(mesh.geometry.getAttribute('position').array);
  const geometry=sectionGeometry(mesh,1.3);assert.ok(geometry);assert.ok(Math.abs(area(geometry)-.8)<1e-5);
  assert.deepEqual(Array.from(mesh.geometry.getAttribute('position').array),original);
  geometry.computeBoundingBox();assert.ok(Math.abs(geometry.boundingBox.getCenter(new THREE.Vector3()).x-5)<1e-5);
  assert.equal(sectionGeometry(mesh,10),null);
  assert.equal(sectionGeometry(new THREE.Mesh(new THREE.PlaneGeometry(4,3)),0),null);
});
test('horizontal sections keep holes open',()=>{
  const shape=new THREE.Shape();shape.moveTo(-2,-2);shape.lineTo(2,-2);shape.lineTo(2,2);shape.lineTo(-2,2);shape.closePath();
  const hole=new THREE.Path();hole.moveTo(-1,-1);hole.lineTo(-1,1);hole.lineTo(1,1);hole.lineTo(1,-1);hole.closePath();shape.holes.push(hole);
  const mesh=new THREE.Mesh(new THREE.ExtrudeGeometry(shape,{depth:2,bevelEnabled:false}));mesh.rotation.x=-Math.PI/2;mesh.updateMatrixWorld();
  const geometry=sectionGeometry(mesh,1);assert.ok(geometry);assert.ok(Math.abs(area(geometry)-12)<1e-5);
});
test('caps retain source picking identity and follow moves, hiding deleted walls',()=>{
  const root=new THREE.Group(),wall=new THREE.Group(),mesh=new THREE.Mesh(new THREE.BoxGeometry(4,3,.2));wall.add(mesh);root.add(wall);
  const assembly={root,groups:new Map([['wall',wall]])},scene={groups:[{id:'wall',name:'wall'}]},caps=new PlanCaps();
  caps.update(assembly,scene,[]);assert.equal(caps.root.children.length,1);assert.equal(caps.root.children[0].userData.planSource,mesh);
  wall.position.x=5;caps.update(assembly,scene,[]);assert.equal(caps.root.children.length,1);
  const cap=caps.root.children[0];cap.geometry.computeBoundingBox();assert.equal(cap.geometry.boundingBox.getCenter(new THREE.Vector3()).x,5);
  wall.visible=false;caps.update(assembly,scene,[]);assert.equal(cap.visible,false);caps.dispose();assert.equal(caps.root.children.length,0);
});
