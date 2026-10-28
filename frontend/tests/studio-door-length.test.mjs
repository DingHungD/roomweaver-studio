import test from 'node:test';
import assert from 'node:assert/strict';
import {doorEndpoints,doorLines} from '../src/features/visualization/doorGeometry.ts';

test('AB assembly length gives instant centered preview without changing source endpoints or swing',()=>{
 for(const kind of ['single','double','sliding','frame','folding']){
  const door={points:[[3,4],[3,5]],height:2.1,control:{kind,assembly_width:.85,side:'positive',swing:'positive',hinge:'A'}};
  const before=JSON.stringify(door),[a,b]=doorEndpoints(door);
  assert.ok(Math.abs(Math.hypot(b[0]-a[0],b[1]-a[1])-.85)<1e-8);assert.deepEqual([(a[0]+b[0])/2,(a[1]+b[1])/2],[3,4.5]);
  assert.ok(doorLines(door).length);assert.equal(JSON.stringify(door),before);
 }
});
