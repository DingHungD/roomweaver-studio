import test from 'node:test';
import assert from 'node:assert/strict';
import {reviewStatus,taskStatus,continuationBody} from '../src/features/visualization/reviewDiagnosticState.mjs';
test('completed job is not a passed design check',()=>{assert.equal(taskStatus('passed'),'處理完成');assert.equal(reviewStatus('deferred'),'前置條件不足，尚未檢查');});
test('continuation binds baseline and never opts into inference or adoption',()=>{assert.deepEqual(continuationBody('p','r','model','op'),{base_revision:'p',base_review_id:'r',model:'model',operation_id:'op',mode:'review',handoff:false,use_object_recognition:false});});
