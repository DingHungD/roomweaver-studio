import test from 'node:test';
import assert from 'node:assert/strict';
import {incompleteItems} from '../src/features/visualization/configurationIncomplete.ts';
const groups=[{id:'chair',deleted:false},{id:'lamp',deleted:false},{id:'removed',deleted:true}];
const row=(group_id,status,error='')=>({group_id,task_id:group_id,name:group_id,placement:{status,error}});
test('paused batches distinguish failed review from items not yet attempted; successful and kept objects are excluded',()=>{
 const items=incompleteItems({status:'paused',items:[row('chair','applying','需補看安裝面'),row('lamp','waiting'),row('done','installed'),row('keep','kept')]},groups);
 assert.equal(items.length,2);assert.equal(items[0].status,'需要處理');assert.equal(items[1].status,'等待繼續');assert.ok(items.every(i=>i.available));
});
test('sub-material failures share a group locator while missing/deleted identities cannot select a different object',()=>{
 const items=incompleteItems({status:'failed',items:[{...row('chair','needs_attention','貼圖未通過'),object_id:'seat'},{...row('chair','needs_attention','尺寸不合'),object_id:'leg'},row('removed','failed'),row('missing','failed')]},groups);
 assert.equal(items.length,3);assert.equal(items[0].part,null);assert.match(items[0].reason,/貼圖未通過\n尺寸不合/);assert.equal(items[1].available,false);assert.equal(items[2].available,false);
});
test('ongoing tasks and empty batches are not fabricated failures',()=>{
 assert.deepEqual(incompleteItems(null,groups),[]);
 const items=incompleteItems({status:'running',items:[row('lamp','waiting'),row('chair','generating')]},groups);
 assert.equal(items[0].status,'等待配置');assert.equal(items[1].status,'配置中');
});
