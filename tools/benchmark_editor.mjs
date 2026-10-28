/** Offline CPU benchmark of the real editor code; no browser/GPU or image decoding. */
import fs from 'node:fs/promises';
import path from 'node:path';
import * as THREE from '../frontend/node_modules/three/build/three.module.js';
import {GLTFLoader} from '../frontend/node_modules/three/examples/jsm/loaders/GLTFLoader.js';
import {assemble,applyDesign} from '../frontend/src/features/visualization/assemblyScene.ts';
import {PlanDisplay} from '../frontend/src/features/visualization/planDisplay.ts';
import {planRegion} from '../frontend/src/features/visualization/planRegion.ts';
import {pickMeshes} from '../frontend/src/features/visualization/viewportWork.ts';
import {StaticPreview} from '../frontend/src/features/visualization/staticPreview.ts';

const [glb,revision,output]=process.argv.slice(2);
if(!output)throw new Error('Usage: node tools/benchmark_editor.mjs model.glb revision.json output.json');
const source=await fs.readFile(glb),design=JSON.parse(await fs.readFile(revision,'utf8')).scene;
const loader=new GLTFLoader();
// CPU-only parsing: textures are counted but never decoded, downsampled or uploaded.
loader.register(()=>({name:'CPU_BENCH_TEXTURE',loadTexture:async()=>new THREE.Texture()}));
const begin=performance.now(),model=await loader.parseAsync(source.buffer.slice(source.byteOffset,source.byteOffset+source.byteLength),'');
const parseMS=performance.now()-begin;
let start=performance.now();const runtime=assemble(model.scene,design);const assembleMS=performance.now()-start;
const display=new PlanDisplay(),clip=[new THREE.Plane(new THREE.Vector3(0,-1,0),1.3)];
start=performance.now();const preview=new StaticPreview(model.scene);const batchBuildMS=performance.now()-start;
console.log('Prepared preview',preview.statistics());
const samples={applyDesign:[],planRegion:[],planMaterials:[],pickList:[],batchSync:[]};
let materials=[];
for(let i=0;i<8;i++){
 display.restore();start=performance.now();applyDesign(runtime,design);samples.applyDesign.push(performance.now()-start);
 start=performance.now();planRegion(runtime,design);samples.planRegion.push(performance.now()-start);
 start=performance.now();display.apply(model.scene,new Set(),true,clip);samples.planMaterials.push(performance.now()-start);
 start=performance.now();preview.sync();samples.batchSync.push(performance.now()-start);
 start=performance.now();const meshes=pickMeshes(model.scene);samples.pickList.push(performance.now()-start);
 if(i===0)materials=[...new Set(meshes.flatMap(m=>Array.isArray(m.material)?m.material:[m.material]))];
}
const summarize=values=>{const sorted=[...values.slice(1)].sort((a,b)=>a-b);return {median:sorted[Math.floor(sorted.length/2)],max:Math.max(...sorted),first:values[0]};};
const meshes=pickMeshes(model.scene),geometries=new Set(meshes.map(m=>m.geometry));
const center=new THREE.Box3().setFromObject(model.scene).getCenter(new THREE.Vector3());
const ray=new THREE.Raycaster(center.clone().add(new THREE.Vector3(0,10,0)),new THREE.Vector3(0,-1,0));
samples.rayBefore=[];samples.rayAfter=[];samples.moveOneGroup=[];
let beforeHits,afterHits;const group=runtime.groups.values().next().value;
for(let i=0;i<6;i++){
 start=performance.now();beforeHits=ray.intersectObjects(pickMeshes(model.scene),false);samples.rayBefore.push(performance.now()-start);
 start=performance.now();afterHits=preview.intersections(ray);samples.rayAfter.push(performance.now()-start);
 group.position.x+=.01;start=performance.now();preview.sync(group);samples.moveOneGroup.push(performance.now()-start);
}
if(beforeHits.length!==afterHits.length||beforeHits.some((h,i)=>h.object!==afterHits[i].object||Math.abs(h.distance-afterHits[i].distance)>1e-5))throw new Error('Pick results changed');
console.log('Constraints', {transparent:meshes.filter(m=>(Array.isArray(m.material)?m.material:[m.material]).some(x=>x.transparent)).length,reflected:meshes.filter(m=>m.matrixWorld.determinant()<0).length});
const result={kind:'CPU only; texture decode, WebGL, shadows and browser FPS are not measured',input:{glb:path.resolve(glb),revision:path.resolve(revision)},
 parseMS,assembleMS,meshes:meshes.length,uniqueGeometries:geometries.size,triangles:meshes.reduce((n,m)=>n+(m.geometry.index?.count||m.geometry.attributes.position.count)/3,0),
 groups:design.groups.length,batchBuildMS,batching:preview.statistics(),pickingHits:beforeHits.length,pickingMatches:true,previewMaterials:materials.length,materialVersionSum:materials.reduce((n,m)=>n+m.version,0),timing:Object.fromEntries(Object.entries(samples).map(([k,v])=>[k,summarize(v)]))};
await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(result,null,2));
console.log(JSON.stringify(result));preview.dispose();display.dispose();
