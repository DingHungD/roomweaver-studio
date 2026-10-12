import test from 'node:test';
import assert from 'node:assert/strict';
import {configureStaging} from '../src/features/visualization/configureStaging.ts';

function harness(automatic,items=[{id:'vase'}]){
 const calls=[];const proposal={id:'proposal',items,lights:[]};
 return {calls,flow:{automatic,save:async()=>{calls.push('save');return 'fresh';},
 propose:async revision=>{assert.equal(revision,'fresh');calls.push('propose');return proposal;},
 show:p=>{assert.equal(p,proposal);calls.push('show');},
 apply:async(p,revision)=>{assert.equal(p,proposal);assert.equal(revision,'fresh');calls.push('apply');return {revision:'adopted',batch:{id:'batch'}};},
 accept:r=>{assert.equal(r.revision,'adopted');calls.push('accept');}}};
}
test('one click saves, shows the proposal, applies and exposes the resulting batch',async()=>{
 const {calls,flow}=harness(true);await configureStaging(flow);
 assert.deepEqual(calls,['save','propose','show','apply','accept']);
});
test('preview and an empty suggestion never submit model replacement',async()=>{
 for(const [automatic,items] of [[false,[{id:'vase'}]],[true,[]]]){
  const {calls,flow}=harness(automatic,items);await configureStaging(flow);
  assert.deepEqual(calls,['save','propose','show']);
 }
});
test('failed or stale application keeps preview without adopting results',async()=>{
 const {calls,flow}=harness(true);flow.apply=async()=>{throw new Error('stale revision');};
 await assert.rejects(configureStaging(flow),/stale/);
 assert.deepEqual(calls,['save','propose','show']);
});
