import test from 'node:test';
import assert from 'node:assert/strict';
import {doorLines} from '../src/features/visualization/doorGeometry.ts';
test('door side and rotation give independent hinge; doubles mirror leaves',()=>{
 const d={points:[[0,0],[1,0]],control:{kind:'single',side:'positive',swing:'positive'}};
 assert.deepEqual(doorLines(d)[1],[[0,0],[0,1]]);
 d.control.swing='negative';assert.deepEqual(doorLines(d)[1],[[1,0],[1,1]]);
 d.control.kind='double';assert.deepEqual(doorLines(d)[3],[[1,0],[1,.5]]);
 for(const kind of [null,'frame','sliding']){d.control.kind=kind;assert.equal(doorLines(d).length,1);}
});

test('folding leaves retain two half-widths and mirror the opening side and stacking end',()=>{
 for(const hinge of ['A','B'])for(const side of ['positive','negative']){
  const lines=doorLines({height:2.1,points:[[0,0],[1.2,0]],control:{kind:'folding',hinge,side,swing:'auto'}});
  assert.equal(lines.length,3);
  for(const [a,b] of lines.slice(1))assert.ok(Math.abs(Math.hypot(a[0]-b[0],a[1]-b[1])-.554)<1e-9);
  assert.equal(lines[1][1][1]>0,side==='positive');
  assert.ok(hinge==='A'?lines[1][0][0]<.05:lines[1][0][0]>1.15);
  assert.ok(Math.abs(lines[2][1][1])<.01);
 }
});

test('native collision pose wins over ideal door direction, including stacked sliding leaves',()=>{
 const vertices=[[2,3,0],[3,3,0],[3,3.035,0],[2,3.035,0],[2,3,2],[3,3,2],[3,3.035,2],[2,3.035,2]];
 const d={points:[[0,0],[2,0]],height:2.1,control:{kind:'sliding'},pose:{opening:{state:'open'},preview_parts:[{part:'leaf-0',vertices},{part:'leaf-1',vertices:vertices.map(v=>[v[0],v[1]+.045,v[2]])}]}};
 const lines=doorLines(d);assert.equal(lines.length,3);assert.deepEqual(lines[1][0],[2,3]);assert.equal(lines[2][0][1],3.045);
 d.control.kind='single';d.pose.opening.state='limited';assert.deepEqual(doorLines(d),lines);
});
