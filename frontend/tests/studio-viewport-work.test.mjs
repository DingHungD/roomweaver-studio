import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {outlineGeometry,prepareTextures} from '../src/features/visualization/viewportWork.ts';
test('optional outlines bound complex mesh work without replacing source geometry',()=>{
 const source=new THREE.SphereGeometry(2,180,100);source.translate(3,4,5);
 const original=source.getAttribute('position').count;
 const outline=outlineGeometry(source);outline.computeBoundingBox();source.computeBoundingBox();
 assert.equal(source.getAttribute('position').count,original);assert.equal(outline.getAttribute('position').count,24);
 assert.ok(outline.boundingBox.min.distanceTo(source.boundingBox.min)<1e-5);
 assert.ok(outline.boundingBox.max.distanceTo(source.boundingBox.max)<1e-5);
});

test('texture preparation deduplicates borrowed maps and yields before upload',async()=>{
 const root=new THREE.Group(),texture=new THREE.Texture(),normal=new THREE.Texture();
 root.add(new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial({map:texture,normalMap:normal})),new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial({map:texture})));
 const uploads=[],progress=[];let yielded=0;
 const ready=await prepareTextures(root,t=>{assert.ok(yielded>0);uploads.push(t);},{cancelled:()=>false,progress:(n,total)=>progress.push([n,total]),yieldUI:async()=>{yielded++;}});
 assert.equal(ready,true);assert.deepEqual(uploads,[texture,normal]);assert.deepEqual(progress.at(-1),[2,2]);
});

test('leaving a loading model cancels uploads without touching its resources',async()=>{
 const root=new THREE.Group(),texture=new THREE.Texture();root.add(new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial({map:texture})));
 let cancelled=false,uploads=0;
 const ready=await prepareTextures(root,()=>uploads++,{cancelled:()=>cancelled,progress:()=>{},yieldUI:async()=>{cancelled=true;}});
 assert.equal(ready,false);assert.equal(uploads,0);
});
