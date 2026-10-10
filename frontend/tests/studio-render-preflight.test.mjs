import test from 'node:test';
import assert from 'node:assert/strict';
import {renderPreflight} from '../src/features/visualization/renderPreflight.ts';
const scene=()=>({model_id:'model',groups:[{id:'fixture',deleted:false}],objects:[],rooms:[],viewpoints:[{id:'view',shots:[]}],links:[],lighting:'existing'});
const report={status:'needs_probe',light_count:1,world_available:false,issues:[],missing_images:[],emissive_materials:[]};
const setup=()=>({enabled:true,mode:'indoor',lights:[{enabled:true,power:100,color:[1,1,1],kind:'AREA',group_id:'fixture'}]});
const check=(s,r=report)=>renderPreflight(s,'v1','v1',false,r);

test('confirmed panorama-only design with original materials can proceed; checking is read-only',()=>{
  const s=scene(),before=JSON.stringify(s);assert.deepEqual(check(s),[]);assert.equal(JSON.stringify(s),before);
});
test('unsaved or unconfirmed revision directs user to explicit design confirmation',()=>{
  for(const [confirmed,dirty] of [[null,false],['v0',false],['v1',true]]){
    const issues=renderPreflight(scene(),'v1',confirmed,dirty,report);
    assert.deepEqual(issues.map(i=>i.id),['confirmation']);assert.equal(issues[0].step,3);
  }
});
test('collects missing lamps, viewpoints and confirmation instead of returning first error',()=>{
  const s=scene();s.viewpoints=[];
  const issues=renderPreflight(s,'v1',null,false,{...report,status:'blocked',light_count:0,issues:['沒有光源']});
  assert.deepEqual(issues.map(i=>i.id),['lighting','viewpoints','confirmation']);
});
test('lighting cannot bypass missing texture files',()=>{
  const s=scene();s.lighting_setup=setup();
  const issues=check(s,{...report,status:'blocked',missing_images:['wood.png'],issues:['缺失貼圖']});
  assert.deepEqual(issues.map(i=>i.id),['textures']);assert.equal(issues[0].step,0);
});
test('ineffective custom lights are caught even when the original model had light',()=>{
  for(const mutate of [s=>s.lighting_setup.lights[0].enabled=false,s=>s.lighting_setup.lights[0].power=0,s=>s.lighting_setup.lights[0].color=[0,0,0],s=>s.groups[0].deleted=true,s=>s.lighting_setup.lights[0].kind='SUN']){
    const s=scene();s.lighting_setup=setup();mutate(s);assert.deepEqual(check(s).map(i=>i.id),['lighting']);
  }
});
test('day environment, preserved or restored World and emissive materials do not require extra lamps',()=>{
  const s=scene();s.lighting_setup={...setup(),lights:[],mode:'day'};assert.deepEqual(check(s),[]);
  s.lighting_setup.mode='existing';assert.deepEqual(check(s,{...report,world_available:true}),[]);
  s.lighting_setup.source_job_id='restored';assert.deepEqual(check(s),[]);
  s.lighting_setup.mode='indoor';assert.deepEqual(check(s,{...report,emissive_materials:['emitter']}),[]);
});
test('older imports without a report still reach Blender inspection when otherwise ready',()=>{
  const s=scene();assert.deepEqual(check(s,null),[]);
  s.lighting_setup={...setup(),lights:[]};assert.deepEqual(check(s,null),[]);
});
test('missing import or externally changed revision routes to import without discarding draft',()=>{
  assert.deepEqual(renderPreflight(null,null,null,false,null).map(i=>i.id),['import']);
  const s=scene(),before=JSON.stringify(s);
  const issues=renderPreflight(s,'v1','v1',true,report,'v2');
  assert.deepEqual(issues.map(i=>i.id),['revision']);assert.equal(JSON.stringify(s),before);
});
