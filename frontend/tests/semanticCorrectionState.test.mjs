import test from 'node:test';
import assert from 'node:assert/strict';
import {correctionComplete,correctionHidden,correctionSentence} from '../src/features/visualization/semanticCorrectionState.mjs';
const item={id:'a',title:'Window',comment:'This is a window.\nKeep its position',marks:[]};
const result={id:'a',status:'corrected',preview_ready:true,item_snapshot:structuredClone(item)};
test('completion follows individual content, not added unrelated drafts',()=>{
 assert.equal(correctionComplete(item,result,false),true);
 assert.equal(correctionComplete({...item,comment:'Changed'},result,true),false);
 assert.equal(correctionComplete(item,{...result,preview_ready:false},true),false);
 assert.equal(correctionComplete(item,{...result,status:'unresolved'},true),false);
});
test('completed marks hide by default, explicit display and temporary editing work independently',()=>{
 const args=[[item,{...item,id:'b'}],[result],false,new Set(),new Set()];
 assert.deepEqual([...correctionHidden(...args)],['manual:a']);
 assert.deepEqual([...correctionHidden(...args,'manual:a')],[]);
 assert.deepEqual([...correctionHidden(...args.slice(0,4),new Set(['manual:a']))],[]);
 assert.deepEqual([...correctionHidden(...args)],['manual:a']);
});
test('list sentence is concise and detailed source remains untouched',()=>{
 assert.equal(correctionSentence(item),'This is a window.');
 assert.equal(correctionSentence({...item,comment:'',marks:[{}]}),'1 筆圖上標註');
 assert.equal(item.comment,'This is a window.\nKeep its position');
});
