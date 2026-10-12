import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {PlanFrameCache,supportsPlanLayer} from '../src/features/visualization/planFrameCache.ts';
import {pickMeshes} from '../src/features/visualization/viewportWork.ts';

function fixture(){
 const world=new THREE.Scene(),root=new THREE.Group(),caps=new THREE.Group(),helper=new THREE.Group();world.add(root,caps,helper);helper.visible=false;world.background=new THREE.Color('white');
 const a=new THREE.Group(),b=new THREE.Group();root.add(a,b);
 a.add(new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial()));b.add(new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial()));
 const camera=new THREE.OrthographicCamera(-5,5,5,-5,.1,50);camera.position.z=10;camera.updateMatrixWorld();
 let target=null,color=new THREE.Color('red'),alpha=.5;const calls=[];
 const renderer={autoClear:false,width:300,getDrawingBufferSize(v){return v.set(this.width,200);},getRenderTarget(){return target;},setRenderTarget(t){target=t;},getClearColor(c){return c.copy(color);},getClearAlpha(){return alpha;},setClearColor(c,a){color=new THREE.Color(c);alpha=a;},clearDepth(){},render(scene){calls.push({scene,target,meshes:pickMeshes(root).slice(),bg:world.background});}};
 return {world,root,caps,helper,a,b,camera,calls,renderer};
}
test('selection reuses the complete background; transforms redraw only the active layer',()=>{
 const f=fixture(),cache=new PlanFrameCache();const draw=(active)=>cache.draw(f.renderer,f.world,f.camera,f.root,f.helper,f.caps,active,1);
 draw();draw();assert.equal(f.calls.filter(c=>c.scene===f.world).length,1);
 draw(f.a);const scenes=f.calls.filter(c=>c.scene===f.world);assert.deepEqual(scenes.at(-2).meshes,[f.b.children[0]]);assert.deepEqual(scenes.at(-1).meshes,[f.a.children[0]]);
 f.calls.length=0;f.a.position.x=3;f.a.rotation.y=.4;draw(f.a);
 assert.equal(f.calls.filter(c=>c.scene===f.world).length,1);assert.deepEqual(f.calls[0].meshes,[f.a.children[0]]);
 assert.equal(f.a.visible,true);assert.equal(f.b.children[0].visible,true);assert.equal(f.world.background.getHexString(),'ffffff');assert.equal(f.renderer.autoClear,false);assert.equal(f.renderer.getRenderTarget(),null);cache.dispose();
});
test('camera, resize and revision invalidate the static image',()=>{
 const f=fixture(),cache=new PlanFrameCache();const draw=(rev=1)=>cache.draw(f.renderer,f.world,f.camera,f.root,f.helper,f.caps,undefined,rev);
 draw();f.camera.position.x=1;draw();f.renderer.width=500;draw();draw(2);
 assert.equal(f.calls.filter(c=>c.scene===f.world).length,4);cache.dispose();
});
test('failed layer drawing restores visibility and renderer state',()=>{
 const f=fixture(),cache=new PlanFrameCache();f.renderer.render=()=>{throw Error('GPU unavailable');};
 assert.throws(()=>cache.draw(f.renderer,f.world,f.camera,f.root,f.helper,f.caps,f.a,1));
 assert.equal(f.a.visible,true);assert.equal(f.renderer.getRenderTarget(),null);assert.equal(f.renderer.autoClear,false);assert.equal(f.renderer.getClearAlpha(),.5);cache.dispose();
});

test('shader preparation restores the original target even if compilation fails',async()=>{
 const f=fixture(),cache=new PlanFrameCache();f.renderer.compileAsync=async()=>{throw Error('compile failed');};
 await assert.rejects(cache.prepare(f.renderer,f.world,f.camera));assert.equal(f.renderer.getRenderTarget(),null);cache.dispose();
});
test('hidden meshes are excluded from picking and transparent objects use full rendering',()=>{
 const f=fixture();assert.equal(supportsPlanLayer(f.a),true);f.a.children[0].material.transparent=true;assert.equal(supportsPlanLayer(f.a),false);
 f.a.visible=false;assert.deepEqual(pickMeshes(f.root),[f.b.children[0]]);assert.ok(f.b.children[0].geometry.boundingBox);
});

test('transmission outside the moving footprint can stay cached; crossing it falls back',()=>{
 const f=fixture();f.b.children[0].material=new THREE.MeshPhysicalMaterial({transmission:1});f.b.position.x=5;f.root.updateMatrixWorld(true);
 assert.equal(supportsPlanLayer(f.root),false);assert.equal(supportsPlanLayer(f.root,f.a),true);
 f.a.position.x=5;f.root.updateMatrixWorld(true);assert.equal(supportsPlanLayer(f.root,f.a),false);
 assert.equal(supportsPlanLayer(f.root,f.b),false);f.b.visible=false;assert.equal(supportsPlanLayer(f.root,f.a),true);
});
