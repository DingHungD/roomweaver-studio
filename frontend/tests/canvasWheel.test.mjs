import test from 'node:test';
import assert from 'node:assert/strict';
import {bindCanvasWheel} from '../src/features/visualization/canvasWheel.mjs';

test('canvas wheel is non-passive, cancels page scrolling and cleans up',()=>{
  let listener,options,removed=false;const factors=[];
  const element={addEventListener(type,fn,opts){assert.equal(type,'wheel');listener=fn;options=opts;},removeEventListener(type,fn){assert.equal(type,'wheel');assert.equal(fn,listener);removed=true;}};
  const cleanup=bindCanvasWheel(element,f=>factors.push(f));
  let prevented=0,stopped=0;
  for(const deltaY of [-100,100,0])listener({deltaY,preventDefault(){prevented++;},stopPropagation(){stopped++;}});
  assert.equal(options.passive,false);assert.equal(prevented,3);assert.equal(stopped,3);
  assert.equal(factors.length,2);assert.ok(Math.abs(factors[0]*factors[1]-1)<1e-10);
  cleanup();assert.equal(removed,true);
});
