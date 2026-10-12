import test from 'node:test';
import assert from 'node:assert/strict';
import {makeArea,addPlacedItem,isDecoration} from '../src/features/visualization/placementArea.ts';
test('drawing in either direction retains Blender XY footprint and support height',()=>{
 const a=makeArea([5,6],[2,4],.76),b=makeArea([2,4],[5,6],.76);
 assert.deepEqual(a,b);assert.deepEqual(a,{center:[3.5,5],size:[3,2],height:.76});
 assert.throws(()=>makeArea([NaN,0],[1,2]));
 assert.deepEqual(makeArea([0,0],[.240090666666,.25152355555],.75000001),{center:[.12,.126],size:[.24,.252],height:.75});
});
test('manual additions preserve originals, source needs and editor classification after replacement',()=>{
 const base={groups:[],objects:[],rooms:[],viewpoints:[]};const f={id:'new',name:'我的擺件',asset:'vase',parts:[{id:'part',name:'body'}]};
 const scene=addPlacedItem(base,f,[2,3,.76],'decor','glass vase','https://example.test/model','living');
 assert.equal(base.groups.length,0);assert.equal(scene.groups[0].design_prompt,'glass vase');
 assert.deepEqual(scene.groups[0].translation,[2,3,.76]);assert.equal(scene.objects[0].room_id,'living');
 scene.concept_furniture=[];scene.groups[0].method='blenderkit';assert.ok(isDecoration(scene,scene.groups[0]));
 assert.throws(()=>addPlacedItem(scene,f,[0,0,0],'decor','','',null));
});
