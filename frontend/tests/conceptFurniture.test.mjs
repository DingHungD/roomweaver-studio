import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {assemble,applyDesign} from '../src/features/visualization/assemblyScene.ts';
test('concept addition, translation, child material, removal and reload share one scene',()=>{
 const root=new THREE.Group();const original=new THREE.Mesh(new THREE.BoxGeometry(1,1,1));original.userData.studio_id='original';root.add(original);
 const scene={groups:[{id:'source',children:['original'],translation:[0,0,0]}],objects:[{id:'original',material:{color:null,roughness:.5}}],concept_furniture:[]};
 const runtime=assemble(root,scene);applyDesign(runtime,scene);
 const concept={id:'concept-test',name:'test chair',parts:[{id:'chair-seat',name:'seat',center:[0,0,.5],size:[.5,.5,.1]}]};
 scene.concept_furniture.push(concept);scene.groups.push({id:concept.id,children:['chair-seat'],translation:[2,3,0]});scene.objects.push({id:'chair-seat',material:{color:'#123456',roughness:.8}});
 applyDesign(runtime,scene);const mesh=runtime.parts.get('chair-seat');const center=new THREE.Box3().setFromObject(mesh).getCenter(new THREE.Vector3());assert.deepEqual(center.toArray(),[2,.5,-3]);assert.equal(mesh.material.color.getHexString(),'123456');
 applyDesign(runtime,scene);assert.equal(runtime.parts.get('chair-seat'),mesh);
 scene.groups[1].deleted=true;applyDesign(runtime,scene);assert.equal(runtime.groups.get(concept.id).visible,false);
 const reloaded=assemble(root.clone(),scene);applyDesign(reloaded,scene);assert.equal(reloaded.groups.get(concept.id).visible,false);
 scene.groups.pop();scene.objects.pop();scene.concept_furniture=[];applyDesign(runtime,scene);assert.equal(runtime.parts.has('chair-seat'),false);assert.ok(runtime.parts.has('original'));
});
