import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {planRegion} from '../src/features/visualization/planRegion.ts';

function fixture(items){
  const root=new THREE.Group(),groups=new Map();
  const specs=items.map(([name,position,size])=>{
    const g=new THREE.Group();g.add(new THREE.Mesh(new THREE.BoxGeometry(...size)));g.position.set(...position);root.add(g);groups.set(name,g);
    return {id:name,name,deleted:false};
  });root.updateMatrixWorld(true);return [{root,groups},{groups:specs}];
}
test('plan frames interior floor and hides distant unnamed objects, balcony and ceiling without mutating model',()=>{
  const [assembly,design]=fixture([
    ['floor',[3.4,-.08,-2.9],[6.96,.16,5.96]],
    ['wall',[6.88,1.45,-2.9],[.16,2.9,5.8]],
    ['bed',[5.5,.4,-4.5],[1.5,.8,2]],
    ['neighbor',[-4,1,4],[.2,2,4]],['unlabelled-prop',[-10,.5,0],[1,1,1]],
    ['balcony',[-.5,0,-3],[1,.1,4]],['ceiling',[3.4,3,-2.9],[7,.2,6]],
  ]);
  const result=planRegion(assembly,design);
  assert.equal(result.bounded,true);assert.ok(result.bounds.getCenter(new THREE.Vector3()).distanceTo(new THREE.Vector3(3.4,.57,-2.9))<.001);
  assert.deepEqual([...result.hidden].sort(),['balcony','ceiling','neighbor','unlabelled-prop']);
  assert.ok(result.bounds.getSize(new THREE.Vector3()).x<7.4);
  assert.ok([...assembly.groups.values()].every(g=>g.visible));
  assert.ok(design.groups.every(g=>!g.deleted));
  assert.ok(result.planes.every(p=>p.distanceToPoint(new THREE.Vector3(3,0,-3))>0));
  assert.ok(result.planes.some(p=>p.distanceToPoint(new THREE.Vector3(-4,0,0))<0));
});
test('missing floor falls back to visible geometry, not an arbitrary assumed apartment size',()=>{
  const [assembly,design]=fixture([['table',[30,.5,-10],[2,1,2]],['neighbor',[0,0,0],[5,5,5]],['floorlamp',[32,1,-10],[.4,2,.4]]]);
  const result=planRegion(assembly,design);assert.equal(result.bounded,false);assert.equal(result.planes.length,0);
  assert.ok(result.bounds.min.x>=29);assert.equal(result.hidden.has('table'),false);assert.equal(result.hidden.has('floorlamp'),false);
});
test('deleted floor does not constrain framing and split room floors combine without relying on object order',()=>{
  const [assembly,design]=fixture([['floor-room2',[6,0,0],[4,.1,4]],['floor-room1',[2,0,0],[4,.1,4]],['table',[3,.4,0],[1,.8,1]]]);
  assert.ok(planRegion(assembly,design).bounds.getSize(new THREE.Vector3()).x>8);
  design.groups[0].deleted=true;design.groups[1].deleted=true;
  const result=planRegion(assembly,design);assert.equal(result.bounded,false);assert.ok(result.bounds.getSize(new THREE.Vector3()).x<=1);
});
