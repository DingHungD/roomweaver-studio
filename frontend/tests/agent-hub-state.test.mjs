import test from 'node:test';
import assert from 'node:assert/strict';
import {agentPanelKey,readAgentPanel,persistAgentPanel,createAgentPoller,canAdoptAgentCandidate} from '../src/features/visualization/agentHubState.ts';

const settle=()=>new Promise(resolve=>setImmediate(resolve));
function clocks(){
 const state={ticks:[],timeouts:[],cleared:[]};
 return {...state,interval(fn){state.ticks.push(fn);return 1;},clear(id){state.cleared.push(id);},deadline(fn){state.timeouts.push(fn);return 2;},cancel(){}};
}

test('panel starts collapsed, remembers tab and safely tolerates unavailable storage',()=>{
 assert.deepEqual(readAgentPanel(),{open:false,tab:'work'});
 assert.deepEqual(readAgentPanel({getItem:()=>'{broken'}),{open:false,tab:'work'});
 assert.deepEqual(readAgentPanel({getItem:()=>'null'}),{open:false,tab:'work'});
 const data={};const store={getItem:key=>data[key],setItem:(key,value)=>data[key]=value};
 persistAgentPanel(store,{open:true,tab:'settings'});
 assert.ok(data[agentPanelKey]);
 assert.deepEqual(readAgentPanel(store),{open:true,tab:'settings'});
 persistAgentPanel({setItem(){throw Error('denied');}},{open:false,tab:'work'});
});

test('one list poll stays active without overlapping slow requests',async()=>{
 const timer=clocks(),requests=[],received=[];
 const poller=createAgentPoller({...timer,page:()=>0,onTick(){},onError(){},onSnapshot:value=>received.push(value),fetchSnapshot:()=>new Promise(resolve=>requests.push(resolve))});
 assert.equal(requests.length,1);
 for(let i=0;i<4;i++)timer.ticks[0]();
 assert.equal(requests.length,1);
 requests[0]({active:[]});await settle();assert.equal(received.length,1);
 timer.ticks[0]();assert.equal(requests.length,2);
 poller.dispose();requests[1]({active:['late']});await settle();
 assert.equal(received.length,1);assert.deepEqual(timer.cleared,[1]);
});

test('changing page discards the old response and immediately reads the requested page',async()=>{
 const timer=clocks(),requests=[],received=[];let page=0;
 const poller=createAgentPoller({...timer,page:()=>page,onTick(){},onError(){},onSnapshot:value=>received.push(value),fetchSnapshot:(index,signal)=>new Promise((resolve,reject)=>{
  requests.push({index,resolve,signal});signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true});
 })});
 page=2;poller.refresh();await settle();
 assert.equal(requests[0].signal.aborted,true);assert.deepEqual(requests.map(r=>r.index),[0,2]);
 requests[1].resolve({page:2});await settle();assert.deepEqual(received,[{page:2}]);poller.dispose();
});

test('timeout and failed refresh retain the last good result',async()=>{
 const timer=clocks(),received=[],errors=[];let call=0;
 const poller=createAgentPoller({...timer,page:()=>0,onTick(){},onSnapshot:value=>received.push(value),onError:message=>errors.push(message),fetchSnapshot:(_page,signal)=>{
  if(call++===0)return Promise.resolve({active:['running']});
  return new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true}));
 }});
 await settle();timer.ticks[0]();timer.timeouts.at(-1)();await settle();
 assert.deepEqual(received,[{active:['running']}]);assert.match(errors[0],/逾時/);poller.dispose();
});

test('stale source or another project cannot adopt a candidate from shared Agent state',()=>{
 const entry={project:'case-a',revision:'rev-a',task:{status:'passed'}};
 assert.equal(canAdoptAgentCandidate(entry,'case-a','rev-a',false,false),true);
 for(const args of [['case-b','rev-a',false,false],['case-a','rev-b',false,false],['case-a','rev-a',true,false],['case-a','rev-a',false,true],['case-a',null,false,false]])
  assert.equal(canAdoptAgentCandidate(entry,...args),false);
 assert.equal(canAdoptAgentCandidate({...entry,task:{status:'running'}},'case-a','rev-a',false,false),false);
});
