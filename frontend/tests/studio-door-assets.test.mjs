import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {updateDoorPreview} from '../src/features/visualization/doorPreview.ts';
test('door asset preview preserves confirmed colour of unrelated leaf and keeps asset frame',()=>{
 const native=new THREE.Group(),target=new THREE.Group();
 for(const part of ['frame','leaf-0']){const mesh=new THREE.Mesh(new THREE.BoxGeometry(.1,2,.04),new THREE.MeshStandardMaterial({color:'#bca07b'}));mesh.userData={doorId:'d',doorPart:part};native.add(mesh);}
 native.updateMatrixWorld(true);
 const d={id:'d',points:[[0,0],[.9,0]],height:2.1,control:{assets:{frame:{bundle:'a'}},materials:{'leaf-0':{color:'#336699',roughness:.82}}}};
 updateDoorPreview(target,[d],native);
 assert.equal(target.children.length,2);
 assert.equal(target.children[0].material.color.getHexString(),'bca07b');
 assert.equal(target.children[1].material.color.getHexString(),'336699');
 assert.equal(target.children[1].material.roughness,.82);
 assert.equal(native.children[1].material.color.getHexString(),'bca07b');
 updateDoorPreview(target,[],native);assert.equal(target.children.length,0);
});
