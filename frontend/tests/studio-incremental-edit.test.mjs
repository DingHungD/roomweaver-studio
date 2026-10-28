import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {assemble,applyDesign} from '../src/features/visualization/assemblyScene.ts';
import {PlanDisplay} from '../src/features/visualization/planDisplay.ts';

test('adopting render roughness keeps texture, source color and independent shared materials',()=>{
 const root=new THREE.Group(),map=new THREE.Texture(),original=new THREE.MeshStandardMaterial({color:'#ab9876',map,roughness:.3});
 const a=new THREE.Mesh(new THREE.BoxGeometry(),original),b=new THREE.Mesh(new THREE.BoxGeometry(),original);a.userData.studio_id='a';b.userData.studio_id='b';root.add(a,b);
 const design={groups:['a','b'].map(id=>({id,children:[id],translation:[0,0,0],deleted:false})),objects:['a','b'].map(id=>({id,material:{color:null,roughness:.5}}))};
 const runtime=assemble(root,design);applyDesign(runtime,design);const adjusted=structuredClone(design);adjusted.objects[0].material.render_roughness=.8;applyDesign(runtime,adjusted);
 assert.equal(a.material.map,map);assert.equal(a.material.color.getHexString(),'ab9876');assert.equal(a.material.roughness,.8);assert.equal(b.material,original);assert.equal(original.roughness,.3);
 applyDesign(runtime,design);assert.equal(a.material,original);
});

test('editing and undo preserve geometry, source textures and independent furniture transforms',()=>{
 const root=new THREE.Group(),map=new THREE.Texture(),normalMap=new THREE.Texture();
 const original=new THREE.MeshStandardMaterial({map,normalMap,roughness:.7}),a=new THREE.Mesh(new THREE.BoxGeometry(),original),b=new THREE.Mesh(new THREE.BoxGeometry(),original);
 a.userData.studio_id='a';b.userData.studio_id='b';b.position.x=3;root.add(a,b);
 const design={groups:['a','b'].map(id=>({id,children:[id],translation:[0,0,0],deleted:false})),objects:['a','b'].map(id=>({id,material:{}}))};
 const source=JSON.stringify(design),runtime=assemble(root,design);applyDesign(runtime,design);const geometry=a.geometry,other=runtime.groups.get('b').matrix.clone();
 const change=structuredClone(design);change.groups[0].translation=[2,1,0];change.groups[0].rotation=90;change.objects[0].material={color:'#ff0000',roughness:.2};applyDesign(runtime,change);
 assert.equal(a.geometry,geometry);assert.equal(a.material.map,map);assert.equal(a.material.normalMap,normalMap);assert.equal(b.material,original);assert.ok(runtime.groups.get('b').matrix.equals(other));assert.equal(original.roughness,.7);
 const adopted=a.material;change.objects[0].material.roughness=.6;applyDesign(runtime,change);assert.equal(a.material,adopted);assert.equal(a.material.roughness,.6);
 const display=new PlanDisplay();display.apply(root,new Set(),true);const preview=a.material;display.restore();change.objects[0].material.color='#00ff00';applyDesign(runtime,change);display.apply(root,new Set(),true);assert.equal(a.material,preview);assert.equal(a.material.color.getHexString(),'00ff00');display.restore();
 applyDesign(runtime,design);assert.equal(a.material,original);assert.equal(a.geometry,geometry);assert.ok(runtime.groups.get('a').position.distanceTo(runtime.bases.get('a'))<1e-8);assert.equal(JSON.stringify(design),source);display.dispose();
});
