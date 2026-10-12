import test from 'node:test';
import assert from 'node:assert/strict';
import {mergeGroups} from '../src/features/visualization/mergeGroups.ts';
const scene=()=>({groups:[{id:'a',children:['bowl'],translation:[0,0,0]},{id:'b',children:['tank'],translation:[0,0,0]},{id:'c',children:['chair'],translation:[0,0,0]}],objects:[{id:'bowl'},{id:'tank'},{id:'chair'}],lighting_setup:{lights:[{group_id:'b'}]}});
test('UI merge preserves geometry and remaps bound light without changing original scene',()=>{
 const before=scene(),result=mergeGroups(before,'a',['b']);
 assert.deepEqual(result.groups[0].children,['bowl','tank']);
 assert.equal(result.groups.length,2);assert.deepEqual(result.objects,before.objects);
 assert.equal(result.lighting_setup.lights[0].group_id,'a');assert.equal(before.groups.length,3);
});
test('UI merge refuses incompatible transforms or adopted assets',()=>{
 const s=scene();s.groups[1].translation=[1,0,0];assert.throws(()=>mergeGroups(s,'a',['b']),/位移/);
 s.groups[1].translation=[0,0,0];s.groups[1].asset_reference={};assert.throws(()=>mergeGroups(s,'a',['b']),/來源/);
});
