import assert from 'node:assert/strict';
import { GalleryResources, highResolutionPolicy as policy, panoramaTextureBytes, LIMITS } from '../src/source-gallery/gallery-resources.js';
const baseline={standalone:true,width:1536,fine:true,maxTextureSize:16384,memory:8,failed:false,source:'/high.jpg',dimensions:[8192,4096]};
assert.equal(policy(baseline).automatic,true);
for(const override of [{memory:undefined},{memory:4},{standalone:false},{fine:false},{failed:true}]){
 const value=policy({...baseline,...override});assert.equal(value.automatic,false);assert.equal(value.manual,true);
}
assert.equal(policy({...baseline,maxTextureSize:4096}).manual,false);
assert.equal(policy({...baseline,width:390}).manual,false);
const resources=new GalleryResources();let resolveDecode,closed=0,active=0,maxActive=0,freshConsumed=false;
globalThis.fetch=async url=>({ok:true,blob:async()=>({url})});
globalThis.createImageBitmap=async blob=>{
 active++;maxActive=Math.max(maxActive,active);
 if(blob.url==='/old')await new Promise(resolve=>{resolveDecode=resolve;});active--;
 return {width:blob.url==='/old'?8192:4096,height:blob.url==='/old'?4096:2048,close(){closed++;}};
};
let valid=true;
const obsolete=resources.decode('/old',{high:true,dimensions:[8192,4096],current:()=>valid,consume:()=>assert.fail('Stale decode consumed')}).catch(e=>assert.equal(e.name,'AbortError'));
await new Promise(resolve=>setTimeout(resolve,0));
assert.equal(resources.state.cpuMiB,256);assert.equal(resources.state.decoding,1);
valid=false;resources.cancel();
assert.equal(resources.state.cpuMiB,256,'Uncancellable decode must retain its reservation');
const fresh=resources.decode('/new',{dimensions:[4096,2048],current:()=>true,consume:()=>{freshConsumed=true;}});
await new Promise(resolve=>setTimeout(resolve,0));
assert.equal(resources.state.cpuMiB,320,'Incoming 4K must fit while obsolete 8K decode remains reserved');
assert.equal(resources.state.decoding,1);assert.equal(freshConsumed,false);
resolveDecode();await Promise.all([obsolete,fresh]);
assert.equal(closed,2);assert.equal(freshConsumed,true);assert.equal(maxActive,1);assert.equal(resources.state.cpuMiB,0);assert.deepEqual(resources.state.jobs,[]);
let disposed=0;const texture={dispose(){disposed++;}};
resources.retain(texture,128*1024*1024);resources.clear();assert.equal(resources.state.gpuMiB,0);assert.equal(disposed,1);
// Both fallback and high textures, including complete mip chains, must fit together.
const baseBytes=panoramaTextureBytes(4096,2048), highBytes=panoramaTextureBytes(8192,4096);
assert.equal(baseBytes,44739244);assert.equal(highBytes,178956972);
assert.ok(baseBytes+highBytes<=LIMITS.gpu);
const base={dispose(){}},high={dispose(){}};
resources.retain(base,baseBytes);resources.retain(high,highBytes);
assert.throws(()=>resources.retain({dispose(){}},baseBytes),/GPU budget/);
resources.release(high);resources.retain({dispose(){}},baseBytes);resources.clear();
assert.equal(resources.state.gpuMiB,0);
console.log('PASS policy, 320 MiB stale decode, serial decode, 213.34 MiB mipmapped 4K + 8K, budget rejection and release');
