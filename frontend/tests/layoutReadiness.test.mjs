import test from 'node:test';
import assert from 'node:assert/strict';
import {layoutBlockers} from '../src/features/visualization/layoutReadiness.mjs';
const ready={dirty:false,planStatus:'ready',busy:false,waiting:false,brief:'Two people need a home office.',needs:'Two desks',model:'test',width:.8};
test('missing brief and needs are explained even with a selected model',()=>{
  assert.deepEqual(layoutBlockers({...ready,brief:'',needs:''}).map(r=>r.target),['layout-brief-input','layout-needs-input']);
});
test('saved ready plan does not require the final 3D consent to propose a layout',()=>assert.deepEqual(layoutBlockers(ready),[]));
test('unsaved, invalid plan and stale context remain independent gates',()=>{
  assert.deepEqual(layoutBlockers({...ready,dirty:true,planStatus:'blocked',contextStale:true}).map(r=>r.target),['plan-save','plan-validation','layout-context']);
});
test('invalid route width, empty model and too many requirements cannot submit',()=>{
  assert.equal(layoutBlockers({...ready,width:NaN,model:'',needs:Array(26).fill('item').join('\n')}).length,3);
});
