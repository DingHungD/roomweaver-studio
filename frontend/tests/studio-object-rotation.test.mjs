import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {assemble,applyDesign} from '../src/features/visualization/assemblyScene.ts';
import {lightPosition,placeLight} from '../src/features/visualization/lightGeometry.ts';
import {lightRotation} from '../src/features/visualization/lightGeometry.ts';
import {lightDirection} from '../src/features/visualization/previewLighting.ts';

test('group rotation keeps its pivot, translates once and retains independent child meshes',()=>{
  const root=new THREE.Group();const mesh=new THREE.Mesh(new THREE.BoxGeometry(2,1,1));mesh.position.set(4,.5,-3);mesh.userData.studio_id='seat';root.add(mesh);
  const scene={groups:[{id:'chair',children:['seat'],translation:[2,1,0],rotation:90,rotation_pivot:[4,3,0],deleted:false}],objects:[{id:'seat',material:{}}]};
  const runtime=assemble(root,scene);applyDesign(runtime,scene);
  const center=new THREE.Box3().setFromObject(mesh).getCenter(new THREE.Vector3());
  assert.ok(center.distanceTo(new THREE.Vector3(6,.5,-4))<1e-9);
  const size=new THREE.Box3().setFromObject(mesh).getSize(new THREE.Vector3());assert.ok(Math.abs(size.z-2)<1e-9);
  applyDesign(runtime,scene);assert.ok(new THREE.Box3().setFromObject(mesh).getCenter(new THREE.Vector3()).distanceTo(center)<1e-9);
  assert.equal(runtime.parts.get('seat'),mesh);
});

test('bound light orbits the same pivot, inverse placement round-trips',()=>{
  const scene={groups:[{id:'lamp',translation:[2,1,0],rotation:90,rotation_pivot:[4,3,0]}]};
  const light={group_id:'lamp',position:[5,3,2]};
  const actual=lightPosition(light,scene);assert.ok(Math.hypot(...actual.map((x,i)=>x-[6,5,2][i]))<1e-9);
  const placed=placeLight(light,scene,[7,8,3]);assert.ok(Math.hypot(...lightPosition(placed,scene).map((x,i)=>x-[7,8,3][i]))<1e-9);
});

test('tilted light rotates in world yaw along with its fixture',()=>{
  const source={group_id:'lamp',rotation:[.4,.6,.2]};const scene={groups:[{id:'lamp',rotation:130}]};
  const before=lightDirection(source),after=lightDirection({...source,rotation:lightRotation(source,scene)});
  assert.ok(before.applyAxisAngle(new THREE.Vector3(0,1,0),130*Math.PI/180).distanceTo(after)<1e-9);
});
