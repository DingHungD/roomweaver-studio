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

test('soft plan retains PBR maps, clips shadows and restores original emission and material',()=>{
  const original=new THREE.MeshPhysicalMaterial({color:'#7e9aab',map:new THREE.Texture(),normalMap:new THREE.Texture(),roughnessMap:new THREE.Texture(),metalnessMap:new THREE.Texture(),aoMap:new THREE.Texture(),roughness:.6,metalness:.2,clearcoat:.4,emissive:0xffffff,emissiveIntensity:500});
  const mesh=new THREE.Mesh(new THREE.BoxGeometry(),original),root=new THREE.Group();root.add(mesh);
  const planes=[new THREE.Plane(new THREE.Vector3(0,-1,0),1.3)],display=new PlanDisplay();display.apply(root,new Set(),true,planes);
  const preview=mesh.material;assert.ok(preview instanceof THREE.MeshPhysicalMaterial);
  for(const channel of ['map','normalMap','roughnessMap','metalnessMap','aoMap'])assert.equal(preview[channel],original[channel]);
  assert.equal(preview.roughness,.6);assert.equal(preview.clearcoat,.4);assert.equal(preview.emissiveIntensity,0);
  assert.equal(preview.clipShadows,true);assert.equal(preview.clippingPlanes,planes);
  assert.equal(original.emissiveIntensity,500);assert.equal(original.clippingPlanes,null);
  display.restore();assert.equal(mesh.material,original);
});

test('reselecting or switching views reuses preview materials and borrowed textures',()=>{
 const texture=new THREE.Texture(),source=new THREE.MeshStandardMaterial({map:texture});
 const root=new THREE.Group(),a=new THREE.Mesh(new THREE.BoxGeometry(),source),b=new THREE.Mesh(new THREE.BoxGeometry(),source);root.add(a,b);
 const display=new PlanDisplay();display.apply(root,new Set(),true,[]);const preview=a.material;
 assert.equal(a.material,b.material);
 let disposed=0,textureDisposed=0;preview.addEventListener('dispose',()=>disposed++);texture.addEventListener('dispose',()=>textureDisposed++);
 for(let i=0;i<20;i++){display.restore();assert.equal(a.material,source);display.apply(root,new Set(),true,[]);assert.equal(a.material,preview);}
 assert.equal(disposed,0);display.dispose();assert.equal(disposed,1);assert.equal(textureDisposed,0);assert.equal(a.material,source);
});

test('replaced source materials retire cached previews while keeping active variants',()=>{
 const root=new THREE.Group(),a=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial());root.add(a);
 const display=new PlanDisplay();display.apply(root,new Set(),true);const old=a.material;let disposed=0;old.addEventListener('dispose',()=>disposed++);
 display.restore();const replacement=new THREE.MeshStandardMaterial({color:'red'});a.material=replacement;
 display.apply(root,new Set(),true);assert.equal(disposed,1);assert.ok(a.material.color.equals(replacement.color));display.restore();assert.equal(a.material,replacement);
 display.dispose();assert.equal(disposed,1);
});

test('source shader version changes retire old previews without disposing textures',()=>{
 const texture=new THREE.Texture(),source=new THREE.MeshStandardMaterial({map:texture});
 const root=new THREE.Group(),mesh=new THREE.Mesh(new THREE.BoxGeometry(),source);root.add(mesh);const display=new PlanDisplay();
 let disposed=0,textureDisposed=0;texture.addEventListener('dispose',()=>textureDisposed++);
 for(let i=0;i<8;i++){display.apply(root,new Set(),true);mesh.material.addEventListener('dispose',()=>disposed++);display.restore();source.needsUpdate=true;}
 assert.equal(disposed,7);display.dispose();assert.equal(disposed,8);assert.equal(textureDisposed,0);
});
