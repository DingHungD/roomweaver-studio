import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {objectStyle,modelOrigin,styleIndependentSceneKey} from '../src/features/visualization/objectStyles.ts';
import {objectSize} from '../src/features/visualization/objectSize.ts';

test('shared object style keeps explicit blank across reload, with legacy batch and import fallbacks',()=>{
 const group={id:'chair',design_prompt:'import brief'};
 assert.equal(objectStyle(group),'import brief');
 assert.equal(objectStyle(group,'batch supplement'),'batch supplement');
 assert.equal(objectStyle({...group,style_prompt:'new style'},'old batch'),'new style');
 assert.equal(objectStyle(JSON.parse(JSON.stringify({...group,style_prompt:''})),'old batch'),'');
 assert.equal(group.design_prompt,'import brief');
});
test('model origin does not invent an online or AI source for untraced imports',()=>{
 assert.equal(modelOrigin({method:'individual'}),'原始匯入模型');
 assert.match(modelOrigin({method:'concept'}),/工具建立/);
 assert.match(modelOrigin({generated_reference:{}}),/AI/);
 assert.match(modelOrigin({asset_reference:{status:'applied'}}),/BlenderKit/);
 assert.equal(modelOrigin({asset_reference:{status:'reference'}}),'原始匯入模型');
});
test('typing shared style reuses existing card previews; actual transforms and materials invalidate them',()=>{
 const scene={groups:[{id:'sofa',translation:[0,0,0]}],objects:[{material:{color:null}}]};
 const key=styleIndependentSceneKey(scene),next=structuredClone(scene);
 next.groups[0].style_prompt='new style';assert.equal(styleIndependentSceneKey(next),key);
 next.groups[0].translation[0]=1;assert.notEqual(styleIndependentSceneKey(next),key);
 next.groups[0].translation[0]=0;next.objects[0].material.color='#bbbbbb';assert.notEqual(styleIndependentSceneKey(next),key);
});
test('display dimensions follow model axes after translation and rotation without changing geometry',()=>{
 const group=new THREE.Group(),mesh=new THREE.Mesh(new THREE.BoxGeometry(1.8,.82,.85));group.add(mesh);
 group.position.set(6,3,8);group.rotation.y=Math.PI/2;group.updateMatrixWorld(true);
 const size=objectSize(group);size.forEach((v,i)=>assert.ok(Math.abs(v-[1.8,.85,.82][i])<1e-6));
 group.position.x+=7;group.rotation.y=.44;group.updateMatrixWorld(true);
 assert.deepEqual(objectSize(group),size);assert.equal(group.children[0],mesh);
});
