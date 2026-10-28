import test from 'node:test';
import assert from 'node:assert/strict';
import {cadSourceTransform} from '../src/features/visualization/cadSourceProjection.mjs';
import {sourcePoint} from '../src/features/visualization/semanticSource.mjs';
const apply=(m,p)=>[m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]];
test('source CAD stays registered after unit conversion, offsets, Y flip and view changes',()=>{
 for(const factor of [1,.01,.001])for(const origin of [[0,0],[-40,35],[900,-1500]]){
  const view={bounds:[-2,-3,10,8],scale:90,pad:40,width:1160,height:1070};
  const matrix=[300,0,0,-300,400000,200000],transform=cadSourceTransform(matrix,view,origin,factor);
  for(const point of [[0,0],[-500,300],[1200,-400]]){
   const expected=sourcePoint(view,[point[0]*factor-origin[0],point[1]*factor-origin[1]]),actual=apply(transform,apply(matrix,point));
   assert.ok(Math.abs(expected[0]-actual[0])<1e-7&&Math.abs(expected[1]-actual[1])<1e-7);
  }
 }
 assert.throws(()=>cadSourceTransform([0,0,0,0,0,0],{},[0,0],1));
});
