import test from 'node:test';
import assert from 'node:assert/strict';
import {filterSemanticSelection,semanticSelectionGroups,toggleSemanticKeys} from '../src/features/visualization/semanticLayerFilter.mjs';
import {semanticDraftLayers,draftCaptionLayouts} from '../src/features/visualization/semanticDraftLayers.mjs';

test('initial review hides floor surfaces, keeps floor lamps, and permits explicit floor visibility without changing data',()=>{
 const items=[{id:'surface',layer:'floors',category:'floor_surface',status:'interpreted'},
  {id:'lamp',layer:'lighting',category:'floor',status:'interpreted'},
  {id:'wall',layer:'walls',category:'wall',status:'interpreted'},
  {id:'note',layer:'lighting',category:'annotation',status:'annotation'}];
 const before=structuredClone(items);
 assert.deepEqual(filterSemanticSelection(items).map(i=>i.id),['lamp','wall']);
 let keys=toggleSemanticKeys(items,null,['walls:wall'],false);
 assert.deepEqual(filterSemanticSelection(items,keys).map(i=>i.id),['lamp']);
 keys=toggleSemanticKeys(items,keys,['floors:floor_surface'],true);
 assert.deepEqual(filterSemanticSelection(items,keys).map(i=>i.id),['surface','lamp']);
 assert.equal(semanticSelectionGroups(items).find(g=>g.id==='floors').options[0].count,1);
 assert.deepEqual(items,before);
});

test('multi-select unions types across layers without duplicating or confusing identical category names',()=>{
 const items=[{id:'wall',layer:'walls',category:'wall'},{id:'door',layer:'openings',category:'door'},{id:'window',layer:'openings',category:'window'},{id:'chair',layer:'furniture',category:'chair'},{id:'bin',layer:'other',category:'other'},{id:'equip',layer:'equipment',category:'other'},{id:'note',layer:'lighting',category:'annotation',status:'annotation'}];
 const original=structuredClone(items);
 assert.equal(filterSemanticSelection(items).length,6);
 let keys=toggleSemanticKeys(items,[],['walls:wall','openings:door','furniture:chair'],true);
 assert.deepEqual(filterSemanticSelection(items,keys).map(i=>i.id),['wall','door','chair']);
 keys=toggleSemanticKeys(items,keys,['openings:door','openings:window'],true);
 assert.equal(filterSemanticSelection(items,keys).length,4);
 keys=toggleSemanticKeys(items,keys,['openings:door'],false);
 assert.deepEqual(filterSemanticSelection(items,keys).map(i=>i.id),['wall','window','chair']);
 assert.deepEqual(filterSemanticSelection(items,[]),[]);
 assert.deepEqual(filterSemanticSelection(items,['other:other']).map(i=>i.id),['bin']);
 assert.equal(filterSemanticSelection(items,['lighting:annotation'])[0].id,'note');
 assert.equal(semanticSelectionGroups(items).find(g=>g.id==='openings').options.length,2);
 assert.deepEqual(items,original);
});
test('nearby draft captions separate visually while their source anchors and strokes stay fixed',()=>{
 const qs=[{id:'a',label:'Q1',box:[-1,0,1,2]},{id:'b',label:'Q2',box:[-1,0,1,2]}];
 const drafts=semanticDraftLayers(qs,{a:'第一個意見',b:'第二個意見'},{}),before=structuredClone(drafts);
 const layout=draftCaptionLayouts(drafts,{pad:10,scale:20,bounds:[-5,-5,5,5]},.7);
 assert.deepEqual(layout[0].anchor,layout[1].anchor);
 assert.ok(layout[1].y+layout[1].height<layout[0].y);
 assert.deepEqual(drafts,before);
});
test('Q draft layers use shared saved or unsaved answer records, with real source bounds and no invented objects',()=>{
 const qs=[{id:'q1',label:'Q1',title:'門型',box:[0,1,2,3]},{id:'q2',label:'Q2',title:'牆',box:null},{id:'empty',label:'Q3',box:[1,1,2,2]}];
 const marks={q2:[{id:'ab',kind:'line',points:[[-12,4],[-10,6]]}]};
 const draft=semanticDraftLayers(qs,{q1:'拉門'},marks);
 assert.deepEqual(draft.map(d=>d.id),['q1','q2']);
 assert.deepEqual(draft[0].box,[0,1,2,3]);assert.deepEqual(draft[1].box,[-12,4,-10,6]);
 assert.equal(draft[1].marks,marks.q2);
 assert.deepEqual(semanticDraftLayers(qs,{},{}),[]);
 const reopened=semanticDraftLayers(qs,JSON.parse(JSON.stringify({q1:'拉門'})),JSON.parse(JSON.stringify(marks)));
 assert.deepEqual(reopened,draft);
 assert.equal(semanticDraftLayers(qs,{q2:'缺位置'},{} )[0].box,null);
});
test('manual box line and text corrections share layers without mutating source or Q records',()=>{
 const manual=[{id:'cor-one',title:'門位置',comment:'請核對',marks:[{id:'b',kind:'box',points:[[4,2],[1,3]],text:''},{id:'l',kind:'line',points:[[0,0],[3,2]],text:''},{id:'t',kind:'text',points:[[-2,6]],text:'窗戶'}]},{id:'cor-empty',title:'草稿',comment:'',marks:[]}];
 const before=structuredClone(manual),q=[{id:'q1',label:'Q1',title:'門型',box:[0,0,1,1]}];
 const layers=semanticDraftLayers(q,{q1:'保留'}, {},manual);
 assert.deepEqual(layers.map(i=>i.id),['q1','manual:cor-one']);
 assert.deepEqual(layers[1].box,[-2,0,4,6]);
 assert.equal(layers[1].label,'M1');assert.equal(layers[1].marks,manual[0].marks);
 assert.deepEqual(manual,before);
 assert.deepEqual(semanticDraftLayers(q,{q1:'保留'},{},JSON.parse(JSON.stringify(manual))),layers);
});
