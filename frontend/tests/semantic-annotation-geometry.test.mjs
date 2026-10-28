import test from 'node:test';
import assert from 'node:assert/strict';
import {annotationHandles,editAnnotation} from '../src/features/visualization/semanticAnnotationGeometry.mjs';
const view={width:1000,height:800,bounds:[-10,-6,0,2],pad:0,scale:100};
test('translation preserves source shape and clamps its entire extent, independent of display',()=>{
 const mark={id:'b',kind:'box',points:[[-8,-4],[-6,-2]],text:''},before=structuredClone(mark);
 const moved=editAnnotation(mark,[-7,-3],[-4,-1],null,view);
 assert.deepEqual(moved.points,[[-5,-2],[-3,0]]);assert.deepEqual(mark,before);
 const bounded=editAnnotation(mark,[-7,-3],[100,100],null,view);
 assert.deepEqual(bounded.points,[[-2,0],[0,2]]);
 assert.deepEqual(editAnnotation(mark,[-7,-3],[-100,-100],null,view).points,[[-10,-6],[-8,-4]]);
});
test('box corners resize against the opposite corner without zero sized drafts',()=>{
 const mark={id:'b',kind:'box',points:[[-6,-2],[-8,-4]]};
 assert.deepEqual(annotationHandles(mark),[[-8,-4],[-6,-4],[-6,-2],[-8,-2]]);
 assert.deepEqual(editAnnotation(mark,[-8,-4],[-9,-5],0,view).points,[[-6,-2],[-9,-5]]);
 assert.equal(editAnnotation(mark,[-8,-4],[-6,-2],0,view),mark);
});
test('line endpoints and old freehand points retain the other endpoint, text moves as a point',()=>{
 const line={id:'l',kind:'line',points:[[-8,-4],[-6,-2]]};
 assert.deepEqual(editAnnotation(line,[-6,-2],[-5,1],1,view).points,[[-8,-4],[-5,1]]);
 assert.equal(editAnnotation(line,[-6,-2],[-8,-4],1,view),line);
 const text={id:'t',kind:'text',points:[[-5,-2]],text:'門'};
 assert.deepEqual(editAnnotation(text,[-5,-2],[-3,0],null,view),{...text,points:[[-3,0]]});
 assert.deepEqual(annotationHandles(text),[]);
 const freehand={kind:'freehand',points:[[-8,-4],[-7,-4],[-6,-2]]};
 assert.deepEqual(editAnnotation(freehand,[-6,-2],[-5,0],1,view).points,[[-8,-4],[-7,-4],[-5,0]]);
});
test('drawing padding is respected in the source coordinate envelope',()=>{
 const mark={kind:'text',points:[[10,10]],text:'A'},padded={width:200,height:200,bounds:[10,10,11,11],pad:20,scale:100};
 assert.deepEqual(editAnnotation(mark,[10,10],[-100,100],null,padded).points,[[9.8,11.2]]);
});
