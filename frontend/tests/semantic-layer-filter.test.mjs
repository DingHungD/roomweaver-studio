import test from 'node:test';
import assert from 'node:assert/strict';
import {filterSemanticItems,semanticCategories,semanticItemBox} from '../src/features/visualization/semanticLayerFilter.mjs';

test('semantic layer filters keep objects grouped, with furniture subclasses and separate notes',()=>{
 const items=[
  {id:'chair',layer:'furniture',category:'chair',status:'interpreted',points:[[2,3],[4,3],[4,5]]},
  {id:'cabinet',layer:'furniture',category:'cabinet',status:'interpreted'},
  {id:'track',layer:'lighting',category:'track',status:'interpreted'},
  {id:'note',layer:'lighting',category:'annotation',status:'annotation'},
  {id:'plant',layer:'decoration',category:'plant',status:'interpreted'},
 ];
 assert.equal(filterSemanticItems(items,'all').length,4);
 assert.deepEqual(filterSemanticItems(items,'furniture','chair').map(i=>i.id),['chair']);
 assert.deepEqual(semanticCategories(items,'lighting'),[{key:'track',name:'軌道燈',count:1},{key:'annotation',name:'原圖燈具註記',count:1}]);
 assert.deepEqual(semanticItemBox(items[0]),[2,3,4,5]);
 assert.equal(filterSemanticItems(items,'decoration').length,1);
 assert.equal(filterSemanticItems(items,'openings').length,0);
});
