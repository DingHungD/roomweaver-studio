import test from 'node:test';
import assert from 'node:assert/strict';
import {pendingExperienceDrafts} from '../src/features/visualization/semanticExperienceState.mjs';

test('valid adoption hides historical private duplicates without changing stored drafts',()=>{
 const drafts=[{id:'new',target_kind:'correction',target_id:'M1',confirmed:true},{id:'old',target_kind:'correction',target_id:'M1',confirmed:false},{id:'other',target_kind:'correction',target_id:'M2',confirmed:false}];
 const before=structuredClone(drafts);
 assert.deepEqual(pendingExperienceDrafts(drafts,{M1:['entry1']}),[drafts[2]]);
 assert.deepEqual(drafts,before);
});
test('changed or deactivated adoption restores the unconfirmed card',()=>{
 const draft={id:'private',target_kind:'correction',target_id:'M1',confirmed:false};
 assert.deepEqual(pendingExperienceDrafts([draft],{}),[draft]);
 assert.deepEqual(pendingExperienceDrafts([draft],{M1:[]}),[draft]);
});
test('different target kinds remain independent and newest private card wins',()=>{
 const drafts=[{id:'latest',target_kind:'correction',target_id:'same',confirmed:false},{id:'old',target_kind:'correction',target_id:'same',confirmed:false},{id:'object',target_kind:'object',target_id:'same',confirmed:false}];
 assert.deepEqual(pendingExperienceDrafts(drafts),[drafts[0],drafts[2]]);
 assert.deepEqual(pendingExperienceDrafts(drafts,{same:['entry1']}),[drafts[2]]);
});
