import test from 'node:test';
import assert from 'node:assert/strict';
import {syncAssetBatch} from '../src/features/visualization/syncAssetBatch.ts';
test('final model is accepted before terminal status unmounts polling',async()=>{
 let active=true;const seen=[];
 await syncAssetBatch({status:'review',placement_revision:'new'},()=>({revision:'old',dirty:false,onAccept:r=>seen.push(r.revision)}),async()=>({revision:'new',scene:{}}),()=>active,b=>{active=false;seen.push(b.status);});
 assert.deepEqual(seen,['new','review']);
});
test('edits made during a scene fetch cannot be overwritten',async()=>{
 let dirty=false;let resolve;const pending=new Promise(r=>resolve=r);let accepted=false,published=false;
 const task=syncAssetBatch({placement_revision:'new'},()=>({revision:'old',dirty,onAccept:()=>{accepted=true;}}),()=>pending,()=>true,()=>{published=true;});
 dirty=true;resolve({revision:'new',scene:{}});await task;
 assert.equal(accepted,false);assert.equal(published,true);
});
