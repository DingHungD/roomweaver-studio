import test from 'node:test';
import assert from 'node:assert/strict';
import {changedQuestionIds} from '../src/features/visualization/semanticFeedback.mjs';

test('submit changed Q answers without resubmitting unrelated saved history',()=>{
 assert.deepEqual(changedQuestionIds({a:'changed',b:'saved',c:''},{},{a:'old',b:'saved'},{}),['a']);
 assert.deepEqual(changedQuestionIds({a:'saved',b:'saved'},{b:[{id:'new-mark'}]},{a:'saved',b:'saved'},{}),['b']);
 assert.deepEqual(changedQuestionIds({a:''},{a:[]},{a:'removed'},{}),[]);
});
