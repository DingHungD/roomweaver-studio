import test from 'node:test';
import assert from 'node:assert/strict';
import {doorIncomplete,viewpointIncomplete} from '../src/features/visualization/editorDiagnostics.ts';
const door={id:'door-a',name:'入口',points:[[1,2],[2,2]],height:2.1};
const point={id:'point-a',name:'客廳',room_id:'living',eye:[3,4,1.6],shots:[]};
const scene={rooms:[{id:'living',name:'客廳'}],manual_doors:[door],door_controls:[{opening_id:'door-a',kind:'single',side:'positive',swing:'positive',hinge:'auto'}],viewpoints:[point]};
test('valid doors and panorama-only points have zero incomplete items',()=>{
 assert.deepEqual(doorIncomplete(scene,[door],[{id:door.id,opening:{state:'open'}}]),[]);
 assert.deepEqual(viewpointIncomplete(scene),[]);
});
test('door configuration and native collision findings share one exact opening locator, preserving dimensions',()=>{
 const s=structuredClone(scene);s.door_controls[0].kind='folding';s.door_controls[0].side=null;
 const before=JSON.stringify(s);
 const items=doorIncomplete(s,[door],[{id:door.id,opening:{state:'limited',source:'保留開向，門片碰牆'}}]);
 assert.equal(items.length,1);assert.match(items[0].reason,/開口方向/);assert.match(items[0].reason,/收折端/);assert.match(items[0].reason,/門片碰牆/);
 assert.equal(items[0].id,door.id);assert.equal(items[0].target.kind,'door');assert.deepEqual(items[0].target.position,[1.5,2,1.05]);assert.equal(JSON.stringify(s),before);
});
test('frame/sliding doors do not demand swing direction; deleted doors disappear without assigning their errors elsewhere',()=>{
 for(const kind of ['frame','sliding']){const s=structuredClone(scene);s.door_controls[0]={opening_id:door.id,kind,side:null,swing:'auto',hinge:'auto'};assert.equal(doorIncomplete(s,[door],[]).length,0);}
 const s=structuredClone(scene);s.door_controls[0].deleted=true;
 assert.deepEqual(doorIncomplete(s,[door],[],[{category:'door',target_id:door.id,reason:'old failure'}]),[]);
 const missing=doorIncomplete(s,[door],[],[{category:'door',target_id:null,reason:'任務逾時'}]);assert.equal(missing[0].available,false);
});
test('part failures select the actual door part, not an arbitrary furniture group',()=>{
 const items=doorIncomplete(scene,[door],[],[{category:'door',target_id:door.id,part:'leaf-0',reason:'門片下載失敗'}]);
 assert.equal(items[0].part,'leaf-0');assert.equal(items[0].target.kind,'door');
});
test('viewpoint issues preserve point and shot identities and disappear after parameter correction',()=>{
 const s=structuredClone(scene);s.viewpoints[0].shots=[{id:'bad',name:'方向二',yaw:0,pitch:0,lens:0}];
 const before=JSON.stringify(s),items=viewpointIncomplete(s);
 assert.equal(items.length,1);assert.equal(items[0].id,point.id);assert.equal(items[0].target.shotId,'bad');assert.deepEqual(items[0].target.position,point.eye);assert.equal(JSON.stringify(s),before);
 s.viewpoints[0].shots[0].lens=35;assert.equal(viewpointIncomplete(s).length,0);
 const review=viewpointIncomplete(scene,[{category:'viewpoint',target_id:point.id,reason:'家具被裁切',status:'取景待處理'}]);assert.equal(review[0].reason,'家具被裁切');
 assert.deepEqual(viewpointIncomplete(scene,[{category:'viewpoint',target_id:'deleted',reason:'舊問題'}]),[]);
});

test('point-level findings retain a failed shot locator and invalid coordinates remain editable without guessing a location',()=>{
 const s=structuredClone(scene);s.viewpoints[0].room_id='missing';s.viewpoints[0].shots=[{id:'bad',name:'方向二',yaw:0,pitch:0,lens:0}];
 assert.equal(viewpointIncomplete(s)[0].target.shotId,'bad');
 s.viewpoints[0].eye=[NaN,4,1.6];const item=viewpointIncomplete(s)[0];
 assert.equal(item.available,false);assert.equal(item.editable,true);assert.equal(item.target,undefined);
 const unbound=viewpointIncomplete(scene,[{category:'viewpoint',target_id:null,reason:'無法確定鏡位'}]);
 assert.equal(unbound.length,1);assert.equal(unbound[0].available,false);
});
