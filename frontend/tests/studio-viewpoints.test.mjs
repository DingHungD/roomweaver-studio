import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {eyeVector,shotDirection,planPosition} from '../src/features/visualization/viewpointGeometry.ts';
import {confirmDesignRevision,renderReady} from '../src/features/visualization/studioFlow.ts';

test('point dragging round-trips Blender XY after plan pan, zoom and resize',()=>{
  for(const [width,height,zoom] of [[800,500,1],[450,700,2.3],[1600,700,.7]]){
    const camera=new THREE.OrthographicCamera(-8*width/height,8*width/height,8,-8,.01,200);
    camera.position.set(6,32,-4);camera.up.set(0,0,-1);camera.lookAt(6,0,-4);camera.zoom=zoom;camera.updateProjectionMatrix();camera.updateMatrixWorld();
    for(const [x,y] of [[2,3],[8,-2],[0,0]]){
      const p=eyeVector([x,y,0]).project(camera);
      const actual=planPosition(camera,(p.x+1)*width/2,(1-p.y)*height/2,width,height);
      assert.ok(Math.abs(actual[0]-x)<1e-8);assert.ok(Math.abs(actual[1]-y)<1e-8);
    }
  }
});
test('preview eye and yaw/pitch use the Blender render coordinate convention',()=>{
  assert.deepEqual(eyeVector([3,7,1.6]).toArray(),[3,1.6,-7]);
  assert.ok(shotDirection(0,0).distanceTo(new THREE.Vector3(1,0,0))<1e-8);
  assert.ok(shotDirection(90,0).distanceTo(new THREE.Vector3(0,0,-1))<1e-8);
  assert.ok(shotDirection(0,30).distanceTo(new THREE.Vector3(Math.sqrt(3)/2,.5,0))<1e-8);
});
test('merged confirmation advances both phases with the same saved revision',async()=>{
  const calls=[];await confirmDesignRevision('saved-v2',false,async(...args)=>calls.push(args));
  assert.deepEqual(calls,[['spaces','saved-v2'],['materials','saved-v2']]);
  calls.length=0;await confirmDesignRevision('saved-v3',true,async(...args)=>calls.push(args));
  assert.deepEqual(calls,[['spaces','saved-v3'],['materials','saved-v3'],['viewpoints','saved-v3']]);
});
test('failed confirmation stops before viewpoints and cannot open rendering',async()=>{
  const calls=[];await assert.rejects(confirmDesignRevision('v1',true,async phase=>{calls.push(phase);if(phase==='materials')throw new Error('revision conflict');}),/revision conflict/);
  assert.deepEqual(calls,['spaces','materials']);assert.equal(renderReady('v1',null,false),false);
});
test('render gate invalidates on unsaved edits or a new revision and restores on undo',()=>{
  assert.equal(renderReady(null,null,false),false);
  assert.equal(renderReady('v1','v1',false),true);
  assert.equal(renderReady('v1','v1',true),false);
  assert.equal(renderReady('v2','v1',false),false);
  assert.equal(renderReady('v1','v1',false),true);
});
