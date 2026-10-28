import test from 'node:test';
import assert from 'node:assert/strict';
import {fixtureLightingCanApply,fixtureLightingPending} from '../src/features/visualization/fixtureLightingState.ts';

test('only completed, unadopted results for the unchanged saved scene auto apply',()=>{
  const task={id:'one',status:'passed',base_revision:'base'};
  assert.equal(fixtureLightingCanApply(task,'base',false),true);
  for(const status of ['queued','running','stopping','stopped','interrupted','failed']){
    assert.equal(fixtureLightingCanApply({...task,status},'base',false),false);
  }
  assert.equal(fixtureLightingCanApply(task,'newer',false),false);
  assert.equal(fixtureLightingCanApply(task,'base',true),false);
  assert.equal(fixtureLightingCanApply({...task,adoption:{revision:'new'}},'base',false),false);
});
test('queued and stopping work stays pending; interrupted work allows a fresh operation',()=>{
  for(const status of ['queued','running','stopping'])assert.equal(fixtureLightingPending(status),true);
  for(const status of ['passed','failed','interrupted','stopped',undefined])assert.equal(fixtureLightingPending(status),false);
});
