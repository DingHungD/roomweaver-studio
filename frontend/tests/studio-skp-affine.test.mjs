import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {assemble,applyDesign} from '../src/features/visualization/assemblyScene.ts';

test('regrouping and editing imported affine components preserves their world vertices',()=>{
 const root=new THREE.Group(),parent=new THREE.Group();root.position.set(23,0,-37);root.add(parent);
 parent.scale.set(2,1,.7);parent.rotation.y=.4;
 const part=new THREE.Mesh(new THREE.BoxGeometry(1,.6,.8),new THREE.MeshStandardMaterial());
 part.userData.studio_id='part';part.rotation.z=.6;part.position.set(.3,.4,.5);parent.add(part);root.updateMatrixWorld(true);
 const local=Array.from({length:part.geometry.attributes.position.count},(_,i)=>new THREE.Vector3().fromBufferAttribute(part.geometry.attributes.position,i));
 const before=local.map(v=>v.clone().applyMatrix4(part.matrixWorld));
 const design={objects:[{id:'part',material:{color:null,roughness:.5}}],groups:[{id:'g',children:['part'],translation:[0,0,0],deleted:false}]};
 const runtime=assemble(root,design);applyDesign(runtime,design);
 local.forEach((v,i)=>assert.ok(v.clone().applyMatrix4(part.matrixWorld).distanceTo(before[i])<1e-6));
 design.groups[0].translation=[1,2,0];applyDesign(runtime,design);
 local.forEach((v,i)=>assert.ok(v.clone().applyMatrix4(part.matrixWorld).distanceTo(before[i].clone().add(new THREE.Vector3(1,0,-2)))<1e-6));
});

test('moving parent and child meshes to separate editor groups retains both source transforms',()=>{
 const root=new THREE.Group();const parent=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial());
 parent.userData.studio_id='parent';parent.scale.set(2,1,.7);parent.rotation.y=.4;root.add(parent);
 const child=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial());child.userData.studio_id='child';child.rotation.z=.6;child.position.set(.3,.4,.5);parent.add(child);root.updateMatrixWorld(true);
 const expected=[parent.matrixWorld.clone(),child.matrixWorld.clone()];
 const design={objects:['parent','child'].map(id=>({id,material:{color:null,roughness:.5}})),groups:['parent','child'].map(id=>({id,children:[id],translation:[0,0,0],deleted:false}))};
 const runtime=assemble(root,design);applyDesign(runtime,design);
 [parent,child].forEach((part,i)=>part.matrixWorld.elements.forEach((v,j)=>assert.ok(Math.abs(v-expected[i].elements[j])<1e-6)));
});
