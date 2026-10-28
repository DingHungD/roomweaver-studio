import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {StaticPreview,affineNormalShader} from '../src/features/visualization/staticPreview.ts';
import {PlanDisplay} from '../src/features/visualization/planDisplay.ts';

function fixture(matrices,material=new THREE.MeshStandardMaterial()){
 const root=new THREE.Group(),geometry=new THREE.BoxGeometry(1,.7,.5),groups=[],meshes=[];
 matrices.forEach((matrix,i)=>{const group=new THREE.Group();group.userData.group_id=String(i);root.add(group);const mesh=new THREE.Mesh(geometry,material);mesh.matrixAutoUpdate=false;mesh.matrix.copy(matrix);group.add(mesh);groups.push(group);meshes.push(mesh);});
 root.updateMatrixWorld(true);return {root,geometry,material,groups,meshes};
}
const translated=x=>new THREE.Matrix4().makeTranslation(x,0,0);
function previewPoints(preview){
 const result=[];preview.root.updateMatrixWorld(true);
 preview.root.traverse(o=>{if(!(o instanceof THREE.Mesh)||!o.visible)return;const count=o.isInstancedMesh?o.count:1;
  for(let i=0;i<count;i++){const matrix=o.isInstancedMesh?new THREE.Matrix4():o.matrixWorld;if(o.isInstancedMesh)o.getMatrixAt(i,matrix);
   const position=o.geometry.attributes.position;for(let j=0;j<position.count;j++)result.push(new THREE.Vector3().fromBufferAttribute(position,j).applyMatrix4(matrix).toArray().map(v=>Math.round(v*1e6)).join(','));}
 });return result.sort();
}
function sourcePoints(meshes){return meshes.flatMap(o=>Array.from({length:o.geometry.attributes.position.count},(_,i)=>new THREE.Vector3().fromBufferAttribute(o.geometry.attributes.position,i).applyMatrix4(o.matrixWorld).toArray().map(v=>Math.round(v*1e6)).join(','))).sort();}

test('repeated static meshes share display batches while source geometry and matrices remain unchanged',()=>{
 const f=fixture([translated(0),translated(2),translated(4)]),before=sourcePoints(f.meshes);
 const preview=new StaticPreview(f.root,1);preview.sync();
 assert.equal(preview.statistics().renderMeshes,1);assert.deepEqual(previewPoints(preview),before);
 assert.ok(f.meshes.every(m=>m.geometry===f.geometry&&m.material===f.material));
 f.groups[1].position.z=3;preview.sync(f.groups[1]);assert.deepEqual(previewPoints(preview),sourcePoints(f.meshes));
 f.groups[1].visible=false;preview.sync();assert.deepEqual(previewPoints(preview),sourcePoints([f.meshes[0],f.meshes[2]]));preview.dispose();
});

test('mirrored and sheared instances preserve vertices, winding and tangent handedness',()=>{
 const shear=new THREE.Matrix4().set(1,.3,0,1,0,1,0,0,0,0,1,0,0,0,0,1);
 const reflected=shear.clone().scale(new THREE.Vector3(-1,1,1));
 const f=fixture([shear,shear.clone().setPosition(3,0,0),reflected,reflected.clone().setPosition(6,0,0)]);
 const before=sourcePoints(f.meshes),indices=Array.from(f.geometry.index.array);
 f.geometry.setAttribute('tangent',new THREE.Float32BufferAttribute(Array.from({length:f.geometry.attributes.position.count},()=>[1,0,0,1]).flat(),4));
 const preview=new StaticPreview(f.root,1);preview.sync();assert.deepEqual(previewPoints(preview),before);
 assert.equal(preview.statistics().batches,2);
 assert.deepEqual(Array.from(f.geometry.index.array),indices);
 const mirrored=preview.root.children.find(b=>b.geometry!==f.geometry);assert.equal(mirrored.geometry.attributes.tangent.getW(0),-1);assert.equal(f.geometry.attributes.tangent.getW(0),1);
 for(const batch of preview.root.children){const m=new THREE.Matrix4();batch.getMatrixAt(0,m);assert.ok(m.determinant()>0);}
 assert.ok(affineNormalShader.includes('cross(im[1],im[2])'));
 const a=new THREE.Vector3(1,0,0),b=new THREE.Vector3(.3,1,0),c=new THREE.Vector3(0,0,1),normal=new THREE.Vector3(.2,.7,.3).normalize();
 const cofactor=new THREE.Matrix3().set(...new THREE.Vector3().crossVectors(b,c).toArray(),...new THREE.Vector3().crossVectors(c,a).toArray(),...new THREE.Vector3().crossVectors(a,b).toArray()).transpose();
 assert.ok(normal.clone().applyMatrix3(cofactor).normalize().distanceTo(normal.clone().applyMatrix3(new THREE.Matrix3().getNormalMatrix(shear)).normalize())<1e-6);
 preview.dispose();
});

test('transparent meshes keep independent sorting and material edits rebatch only display copies',()=>{
 const f=fixture([translated(0),translated(2),translated(4)]),glass=new THREE.MeshStandardMaterial({transparent:true,opacity:.3});f.meshes[2].material=glass;
 const preview=new StaticPreview(f.root,1);preview.sync();assert.equal(preview.statistics().renderMeshes,2);
 const proxy=preview.root.children.find(o=>!o.isInstancedMesh);assert.equal(proxy.material,glass);
 f.material.transparent=true;preview.sync();assert.equal(preview.statistics().batches,0);
 f.material.transparent=false;preview.sync();assert.equal(preview.statistics().batches,1);
 f.meshes[0].material=new THREE.MeshStandardMaterial({color:'red'});preview.sync();assert.equal(preview.statistics().batches,0);
 assert.deepEqual(previewPoints(preview),sourcePoints(f.meshes));preview.dispose();
});

test('adding and removing concept groups updates the display without reloading imported geometry',()=>{
 const f=fixture([translated(0),translated(2)]),preview=new StaticPreview(f.root,1);preview.sync();
 const added=new THREE.Group();added.userData.concept='new';added.userData.group_id='new';const mesh=new THREE.Mesh(f.geometry,f.material);added.add(mesh);f.root.add(added);preview.sync();
 assert.equal(preview.statistics().sourceMeshes,3);assert.deepEqual(previewPoints(preview),sourcePoints([...f.meshes,mesh]));
 f.root.remove(added);preview.sync();assert.equal(preview.statistics().sourceMeshes,2);
 let disposed=0;f.geometry.addEventListener('dispose',()=>disposed++);f.material.addEventListener('dispose',()=>disposed++);preview.dispose();assert.equal(disposed,0);
});

test('cached plan materials do not trigger shader rebuilds when shared by many meshes',()=>{
 const f=fixture([translated(0),translated(2)]),display=new PlanDisplay(),plane=new THREE.Plane(new THREE.Vector3(0,-1,0),1.3);
 display.apply(f.root,new Set(),true,[plane]);const material=f.meshes[0].material,version=material.version;
 for(let i=0;i<5;i++){display.restore();display.apply(f.root,new Set(),true,[plane.clone()]);}
 assert.equal(material.version,version);assert.equal(f.meshes[1].material,material);
 display.restore();display.apply(f.root,new Set(),true,[]);assert.ok(material.version>version);display.dispose();
});

test('picking returns original meshes and invalidates moved group bounds',()=>{
 const f=fixture([translated(0),translated(2),translated(4)]),preview=new StaticPreview(f.root,1);preview.sync();
 const ray=new THREE.Raycaster(new THREE.Vector3(0,3,0),new THREE.Vector3(0,-1,0));
 const hits=preview.intersections(ray);assert.ok(hits.length);assert.ok(hits.every(h=>h.object===f.meshes[0]));
 f.groups[0].position.x=10;preview.sync(f.groups[0]);assert.equal(preview.intersections(ray).length,0);
 ray.ray.origin.x=10;assert.ok(preview.intersections(ray).every(h=>h.object===f.meshes[0]));
 f.groups[0].visible=false;preview.sync();assert.equal(preview.intersections(ray).length,0);preview.dispose();
});

test('display materials retain borrowed textures and follow uniform-only edits',()=>{
 const texture=new THREE.Texture(),f=fixture([translated(0),translated(2)]);f.material.map=texture;
 const preview=new StaticPreview(f.root,1);preview.sync();const displayed=preview.root.children[0].material;
 assert.notEqual(displayed,f.material);assert.equal(displayed.map,texture);
 f.material.color.set('red');f.material.roughness=.2;preview.sync();assert.equal(displayed.color.getHexString(),'ff0000');assert.equal(displayed.roughness,.2);
 const shader={vertexShader:'#include <defaultnormal_vertex>'};displayed.onBeforeCompile(shader,{});assert.ok(shader.vertexShader.includes('cross(im[1],im[2])'));
 let disposed=0;texture.addEventListener('dispose',()=>disposed++);preview.dispose();assert.equal(disposed,0);
});

test('small, animated or line-based imports retain the original rendering path',()=>{
 const f=fixture([translated(0),translated(2)]);assert.equal(new StaticPreview(f.root).enabled,false);
 f.meshes[0].morphTargetInfluences=[0];assert.equal(new StaticPreview(f.root,1).enabled,false);
 f.meshes[0].morphTargetInfluences=undefined;f.root.add(new THREE.InstancedMesh(f.geometry,f.material,2));assert.equal(new StaticPreview(f.root,1).enabled,false);
});
