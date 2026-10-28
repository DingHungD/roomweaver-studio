import test from 'node:test';
import assert from 'node:assert/strict';
import {repairedItem} from '../src/features/visualization/repairEvidence.ts';
import {repairFailure} from '../src/features/visualization/repairEvidence.ts';

test('only verified adopted reference for the exact source task clears an unfinished object',()=>{
 const item={id:'lamp',task:'old-task',repair:{category:'lighting',batch_id:'batch'}};
 const scene={groups:[{id:'lamp',asset_reference:{task_id:'new-task',status:'applied'}}],objects:[]};
 const record={status:'completed',request:{target_id:'lamp',task_id:'old-task',batch_id:'batch'},proof:{group_id:'lamp',reference:{status:'applied',task_id:'new-task'}}};
 assert.equal(repairedItem(item,[record],scene),true);
 assert.equal(repairedItem(item,[{...record,status:'needs_attention'}],scene),false);
 assert.equal(repairedItem({...item,task:'different-failure'},[record],scene),false);
 scene.groups[0].asset_reference.task_id='user-alternative';assert.equal(repairedItem(item,[record],scene),false);
});

test('material proof cannot clear a surface whose material was reverted or only partly repaired',()=>{
 const item={id:'floor',task:'t',repair:{category:'furniture',batch_id:'b'}};
 const r={status:'completed',request:{target_id:'floor',task_id:'t',batch_id:'b'},proof:{group_id:'floor',materials:{one:{task_id:'new'},two:{task_id:'new'}}}};
 const scene={groups:[{id:'floor'}],objects:[{id:'one',material:{asset_reference:{task_id:'new'}}},{id:'two',material:{}}]};
 assert.equal(repairedItem(item,[r],scene),false);
 scene.objects[1].material.asset_reference={task_id:'new'};assert.equal(repairedItem(item,[r],scene),true);
});

test('failure details belong to this batch, not an unrelated or superseded repair',()=>{
 const item={id:'lamp',repair:{batch_id:'b'}};
 const failure={status:'needs_attention',request:{target_id:'lamp',batch_id:'b'},failure_details:[{stage:'安裝',reason:'發光面朝上'}]};
 assert.equal(repairFailure(item,[failure]).failure_details[0].reason,'發光面朝上');
 assert.equal(repairFailure(item,[{...failure,request:{target_id:'lamp',batch_id:'other'}}]),undefined);
 assert.equal(repairFailure(item,[{...failure,status:'completed'},failure]),undefined);
});
