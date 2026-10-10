import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {PlanDisplay,hideImportedLights} from '../src/features/visualization/planDisplay.ts';

test('plan keeps base-color maps and alpha but ignores light, emission and exposure',()=>{
  const map=new THREE.Texture(),alpha=new THREE.Texture();
  const original=new THREE.MeshStandardMaterial({color:'#557088',map,alphaMap:alpha,
    emissive:0xffffff,emissiveIntensity:500,transparent:true,opacity:.7,alphaTest:.3,side:THREE.DoubleSide});
  const mesh=new THREE.Mesh(new THREE.BoxGeometry(),original),root=new THREE.Group();root.add(mesh);
  const display=new PlanDisplay();display.apply(root,new Set());
  assert.ok(mesh.material instanceof THREE.MeshBasicMaterial);
  assert.equal(mesh.material.map,map);assert.equal(mesh.material.alphaMap,alpha);
  assert.ok(mesh.material.color.equals(original.color));assert.equal(mesh.material.toneMapped,false);
  assert.equal(mesh.material.opacity,.7);assert.equal(mesh.material.alphaTest,.3);assert.equal(mesh.material.side,THREE.DoubleSide);
  let disposed=0;map.addEventListener('dispose',()=>disposed++);original.addEventListener('dispose',()=>disposed++);
  display.restore();assert.equal(mesh.material,original);assert.equal(disposed,0);
});

test('contrast floor and multi-material furniture restore exactly across mode changes',()=>{
  const root=new THREE.Group(),map=new THREE.Texture();
  const originals=[new THREE.MeshStandardMaterial({map}),new THREE.MeshStandardMaterial({color:'#123456'})];
  const furniture=new THREE.Mesh(new THREE.BoxGeometry(),originals),floor=new THREE.Mesh(new THREE.PlaneGeometry(),originals[0]);root.add(furniture,floor);
  const display=new PlanDisplay();display.apply(root,new Set([floor]));
  assert.equal(floor.material.map,null);assert.equal(floor.material.color.getHexString(),'d4d9cc');
  assert.equal(furniture.material.length,2);assert.equal(furniture.material[0].map,map);
  display.apply(root,new Set());assert.equal(floor.material.map,map);
  display.restore();assert.equal(furniture.material,originals);assert.equal(floor.material,originals[0]);
  // A later adopted material must survive another round trip.
  const updated=new THREE.MeshStandardMaterial({color:'#ab6543'});furniture.material=updated;
  display.apply(root,new Set());display.restore();assert.equal(furniture.material,updated);
});

test('imported daylight is isolated without changing intensity, mesh visibility or editor lights',()=>{
  const root=new THREE.Group(),nested=new THREE.Group();root.add(nested);
  const sun=new THREE.DirectionalLight(0xffffff,1229),spot=new THREE.SpotLight(0xffffff,5978);
  const fixture=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial());nested.add(sun,spot,fixture);
  const editorLight=new THREE.HemisphereLight();hideImportedLights(root);
  assert.equal(sun.visible,false);assert.equal(spot.visible,false);assert.equal(sun.intensity,1229);
  assert.equal(fixture.visible,true);assert.equal(editorLight.visible,true);
});
