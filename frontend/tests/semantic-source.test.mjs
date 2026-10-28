import test from 'node:test';
import assert from 'node:assert/strict';
import {sourceBox,sourcePoint,sourceWorld,questionView} from '../src/features/visualization/semanticSource.mjs';

test('source annotation follows negative CAD origins, Y-up coordinates and image padding',()=>{
 const view={width:1000,height:800,bounds:[-1,-2,9,6],scale:90,pad:40};
 assert.deepEqual(sourceBox(view,[1,2,3,4]),[220,220,180,180]);
 const focused=questionView(view,[1,2,3,4]);
 assert.ok(focused[0]<220 && focused[1]<220 && focused[2]>180);
 assert.deepEqual(questionView(view,null),[0,0,1000,800]);
 const image={width:400,height:300,bounds:[-2,-1,2,2],scale:100,pad:0};
 assert.deepEqual(sourceBox(image,[-2,-1,2,2]),[0,0,400,300]);
});

test('drawing answer points round-trip through the registered source view',()=>{
 for(const bounds of [[-10,-20,0,-12],[100,200,110,208]]){
  const view={width:1000,height:800,bounds,scale:90,pad:40};
  const point=[bounds[0]+2,bounds[1]+3];
  assert.deepEqual(sourceWorld(view,sourcePoint(view,point)),point);
 }
});
