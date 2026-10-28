import test from 'node:test';
import assert from 'node:assert/strict';
import {configurationScope,configurationName,lightDisplayName,scopedIncompleteItems} from '../src/features/visualization/configurationScope.ts';
const group=(id,name,extra={})=>({id,name,children:[id+'-part'],translation:[0,0,0],deleted:false,method:'concept',...extra});
const fixture=group('lamp','天花燈具 · 地板 · floor-floor13__surface',{editor_kind:'furniture'});
const floor=group('floor','地板',{method:'structural_floor'}),decor=group('vase','花瓶 · 桌子',{editor_kind:'decor'}),chair=group('chair','餐椅');
const light={id:'light',group_id:'lamp',name:fixture.name+' 光源'};
const scene={groups:[floor,fixture,decor,chair],objects:[],rooms:[],concept_furniture:[],lighting_setup:{lights:[light]}};
test('fixture identity takes precedence over the floor used to locate it and legacy furniture editor tags',()=>{
 assert.equal(configurationScope(scene,fixture),'lighting');assert.equal(configurationScope(scene,floor),'furniture');assert.equal(configurationScope(scene,decor),'decor');assert.equal(configurationScope(scene,chair),'furniture');
 assert.equal(configurationScope({...scene,lighting_setup:{lights:[]}},group('free','Standing lamp',{asset_requirements:{purpose:'floor_lamp'}})),'lighting');
});
test('each page receives only its own unfinished objects; missing objects remain explained and cannot be selected',()=>{
 const batch={status:'paused',items:scene.groups.map(g=>({task_id:g.id,group_id:g.id,name:g.name,placement:{status:'waiting'}}))};
 assert.deepEqual(scopedIncompleteItems(batch,scene,'furniture').map(i=>i.id),['floor','chair']);
 assert.deepEqual(scopedIncompleteItems(batch,scene,'lighting').map(i=>i.id),['lamp']);
 assert.deepEqual(scopedIncompleteItems(batch,scene,'decor').map(i=>i.id),['vase']);
 const missing={status:'failed',items:[{task_id:'x',group_id:'missing',name:'天花燈具 · 地板 · floor-2',placement:{status:'failed',error:'原物件已移除'}}]};
 assert.equal(scopedIncompleteItems(missing,scene,'lighting')[0].available,false);
});
test('legacy support IDs become fixture display labels without changing saved names, dimensions or custom labels',()=>{
 const before=JSON.stringify(scene);
 assert.equal(configurationName(scene,fixture),'天花燈具 01');assert.equal(lightDisplayName(scene,light),'天花燈具 01 光源');
 assert.equal(configurationName(scene,group('custom','客廳吊燈')),'客廳吊燈');
 assert.equal(lightDisplayName(scene,{...light,name:'閱讀燈'}),'閱讀燈');
 assert.equal(JSON.stringify(scene),before);
});
