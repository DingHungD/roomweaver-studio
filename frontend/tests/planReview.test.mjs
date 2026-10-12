import test from 'node:test';
import assert from 'node:assert/strict';
import {displayPoint,sourcePoint,buildBlockers} from '../src/features/visualization/planReview.mjs';

test('source marks round-trip in either image orientation',()=>{
  for(const turned of [false,true]) for(const p of [[0,0],[1415,2000],[510.4,730.1]]) {
    const q=sourcePoint(displayPoint(p,2000,turned),2000,turned);
    q.forEach((v,i)=>assert.ok(Math.abs(v-p[i])<1e-9));
  }
  assert.deepEqual(displayPoint([100,200],2000,true),[1800,100]);
});
const ready={image:true,settings:{calibration:{confirmed:true},reviewed:['q']},questions:[{id:'q'}],dirty:false,calibrating:false,busy:'',confirmed:true,check:{status:'ready'}};
test('ready plan permits build, edits and active selection block it',()=>{
  assert.equal(buildBlockers(ready).length,0);
  assert.ok(buildBlockers({...ready,dirty:true}).some(r=>r.target==='plan-save'));
  assert.ok(buildBlockers({...ready,calibrating:true}).some(r=>r.target==='plan-scale'));
  assert.ok(buildBlockers({...ready,check:{status:'blocked'}}).some(r=>r.target==='plan-validation'));
});
test('answers and marks never substitute for explicit review or scale',()=>{
  const r=buildBlockers({...ready,settings:{reviewed:[],source_marks:[{}]},confirmed:false});
  assert.deepEqual(r.map(v=>v.target),['plan-scale','plan-questions','plan-consent']);
});
test('DXF does not require image calibration and unknown stale errors are not current',()=>{
  const r=buildBlockers({...ready,image:false,settings:{},dirty:true,check:{status:'blocked'}});
  assert.deepEqual(r.map(v=>v.target),['plan-save']);
});
