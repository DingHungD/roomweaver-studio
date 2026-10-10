import test from 'node:test';
import assert from 'node:assert/strict';
import {bindLight,lightPosition,placeLight} from '../src/features/visualization/lightGeometry.ts';

const scene={groups:[{id:'lamp',translation:[2,-3,1]},{id:'table',translation:[-2,1,0]}]};
const source={id:'source',group_id:null,position:[4,5,2.5]};
test('binding and rebinding preserve world position even for moved objects',()=>{
  const lamp=bindLight(source,scene,'lamp');
  assert.deepEqual(lamp.position,[2,8,1.5]);
  assert.deepEqual(lightPosition(lamp,scene),source.position);
  const table=bindLight(lamp,scene,'table');
  assert.deepEqual(lightPosition(table,scene),source.position);
  assert.deepEqual(bindLight(table,scene,null).position,source.position);
  assert.equal(source.group_id,null);
});
test('moving a fixture translates its light exactly once; independent lights stay still',()=>{
  const lamp=bindLight(source,scene,'lamp');
  const moved={groups:[{id:'lamp',translation:[3,-1,1.5]}]};
  assert.deepEqual(lightPosition(lamp,moved),[5,7,3]);
  assert.deepEqual(lightPosition(source,moved),source.position);
});
test('plan drag and numeric world coordinates round-trip with a binding',()=>{
  const lamp=bindLight(source,scene,'lamp');
  const dragged=placeLight(lamp,scene,[7,8,2.5]);
  assert.deepEqual(dragged.position,[5,11,1.5]);
  assert.deepEqual(lightPosition(dragged,scene),[7,8,2.5]);
  assert.deepEqual(lightPosition(bindLight(dragged,scene,null),scene),[7,8,2.5]);
});
