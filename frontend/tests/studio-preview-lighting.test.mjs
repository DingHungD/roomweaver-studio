import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {areaSamples,buildPreview,clearPreview,lightDirection,previewSpecs} from '../src/features/visualization/previewLighting.ts';
const light={id:'lamp',name:'lamp',kind:'AREA',position:[2,3,2.5],rotation:[0,0,0],power:150,color:[1,.8,.6],size:1,angle:60,enabled:true,group_id:'fixture'};
const scene=()=>({groups:[{id:'fixture',translation:[1,2,0],deleted:false}],lighting_setup:{enabled:true,mode:'existing',lights:[structuredClone(light)]}});
test('preview emission follows Blender -Z and rotation in Y-up coordinates',()=>{
  assert.ok(lightDirection(light).distanceTo(new THREE.Vector3(0,-1,0))<1e-8);
  assert.ok(lightDirection({...light,rotation:[Math.PI/2,0,0]}).distanceTo(new THREE.Vector3(0,0,-1))<1e-8);
});
test('disabled setup, deleted fixtures, zero power and indoor sun emit no preview light',()=>{
  for(const mutate of [s=>s.lighting_setup.enabled=false,s=>s.groups[0].deleted=true,s=>s.lighting_setup.lights[0].enabled=false,s=>s.lighting_setup.lights[0].power=0,s=>{s.lighting_setup.mode='indoor';s.lighting_setup.lights[0].kind='SUN';}]){
    const s=scene();mutate(s);assert.equal(previewSpecs(s,'').length,0);
  }
});
test('live preview rebuild changes intensity and color without retaining duplicate lights',()=>{
  const s=scene(),root=new THREE.Group();buildPreview(root,s,'lamp');
  const before=root.children.find(o=>o instanceof THREE.SpotLight);const power=before.intensity;
  assert.deepEqual(before.position.toArray(),[3,2.5,-5]);
  s.lighting_setup.lights[0].power=300;s.lighting_setup.lights[0].color=[.2,.4,1];buildPreview(root,s,'lamp');
  const after=root.children.filter(o=>o instanceof THREE.SpotLight);assert.equal(after.length,1);assert.equal(after[0].intensity,power*2);assert.deepEqual(after[0].color.toArray(),[.2,.4,1]);
  clearPreview(root);assert.equal(root.children.length,0);
});
test('preview caps light and shadow budgets while prioritizing selected light',()=>{
  const s=scene();s.lighting_setup.lights=Array.from({length:30},(_,i)=>({...light,id:'light'+i}));
  assert.equal(previewSpecs(s,'light29')[0].id,'light29');assert.equal(previewSpecs(s,'light29').length,24);
  const root=new THREE.Group();buildPreview(root,s,'light29');assert.equal(root.children.filter(o=>o instanceof THREE.Light&&o.castShadow).length,4);clearPreview(root);
});

test('soft area samples follow source size and rotation and conserve total direct power',()=>{
  const s=scene(),root=new THREE.Group();buildPreview(root,s,'lamp',{soften:true,floorArea:80});
  const spots=root.children.filter(o=>o instanceof THREE.SpotLight);
  assert.equal(spots.length,4);assert.ok(Math.abs(spots.reduce((sum,l)=>sum+l.intensity,0)-light.power/(2*Math.PI))<1e-8);
  const center=spots.reduce((v,l)=>v.add(l.position),new THREE.Vector3()).divideScalar(4);
  assert.ok(center.distanceTo(new THREE.Vector3(3,2.5,-5))<1e-8);
  const wider=areaSamples({...light,size:2,rotation:[Math.PI/2,0,0]});
  assert.ok(wider.every(p=>Math.abs(p.z)<1e-8));assert.ok(Math.abs(wider[0].length()-Math.sqrt(.5))<1e-8);
  clearPreview(root);
});
test('soft fill scales with active power, remains bounded and disappears with disabled or black lights',()=>{
  const s=scene(),root=new THREE.Group(),build=()=>{buildPreview(root,s,'',{soften:true,floorArea:80});return root.children.find(o=>o.userData.indirectApproximation);};
  const initial=build().intensity;s.lighting_setup.lights[0].power*=2;assert.equal(build().intensity,initial*2);
  s.lighting_setup.lights[0].power=100000;assert.equal(build().intensity,.8);
  s.lighting_setup.lights[0].color=[0,0,0];assert.equal(build(),undefined);
  s.lighting_setup.lights[0].color=[1,1,1];s.lighting_setup.enabled=false;build();assert.equal(root.children.filter(o=>o instanceof THREE.Light).length,0);
  clearPreview(root);
});
test('soft mode has bounded sample/shadow budgets and switching back removes approximate fill',()=>{
  const s=scene(),root=new THREE.Group();s.lighting_setup.lights=Array.from({length:30},(_,i)=>({...light,id:'light'+i}));
  buildPreview(root,s,'light29',{soften:true});
  assert.equal(root.children.filter(o=>o instanceof THREE.SpotLight).length,30);
  assert.equal(root.children.filter(o=>o instanceof THREE.Light&&o.castShadow).length,8);
  assert.equal(root.children.filter(o=>o.userData.sourceId==='light29').length,4);
  buildPreview(root,s,'light29',{soften:false});assert.equal(root.children.some(o=>o.userData.indirectApproximation),false);
  assert.equal(root.children.filter(o=>o instanceof THREE.SpotLight).length,24);clearPreview(root);
});
