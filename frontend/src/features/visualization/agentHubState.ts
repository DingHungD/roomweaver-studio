import type {AgentTab} from './agentHubContext';

export const agentPanelKey='roomweaver.agent-panel.v1';
export function readAgentPanel(storage?:Pick<Storage,'getItem'>){
 try{const value=JSON.parse(storage?.getItem(agentPanelKey)||'{}');return {open:value?.open===true,tab:(value?.tab==='settings'?'settings':'work') as AgentTab};}
 catch{return {open:false,tab:'work' as AgentTab};}
}
export function persistAgentPanel(storage:Pick<Storage,'setItem'>|undefined,state:{open:boolean;tab:AgentTab}){
 try{storage?.setItem(agentPanelKey,JSON.stringify(state));}catch{/* Unavailable storage never prevents using Agent. */}
}
export function canAdoptAgentCandidate(entry:{project:string;revision:string|null;task:{status:string}},project:string,revision:string|null,dirty:boolean,busy:boolean){
 return entry.project===project&&!!revision&&entry.revision===revision&&!dirty&&!busy&&entry.task.status==='passed';
}

/** One list subscription; page changes abort stale reads without parallel polls. */
export function createAgentPoller<T>({page,fetchSnapshot,onSnapshot,onError,onTick,interval=setInterval,clear=clearInterval,deadline=setTimeout,cancel=clearTimeout}:{
 page:()=>number;fetchSnapshot:(page:number,signal:AbortSignal)=>Promise<T>;onSnapshot:(value:T,page:number)=>void;onError:(message:string)=>void;onTick:()=>void;
 interval?:typeof setInterval;clear?:typeof clearInterval;deadline?:typeof setTimeout;cancel?:typeof clearTimeout;
}){
 let disposed=false,inFlight=false,queued=false,request:AbortController|null=null;
 async function poll(){
  if(disposed||inFlight)return;
  inFlight=true;const requestedPage=page();const current=new AbortController();request=current;
  let timedOut=false;
  const timeout=deadline(()=>{timedOut=true;current.abort();},10000);
  try{const value=await fetchSnapshot(requestedPage,current.signal);if(!disposed&&requestedPage===page()&&!current.signal.aborted)onSnapshot(value,requestedPage);}
  catch(e){if(!disposed&&requestedPage===page()&&(!current.signal.aborted||timedOut))onError(timedOut?'讀取工作狀態逾時':(e as Error).message);}
  finally{cancel(timeout);inFlight=false;if(request===current)request=null;if(queued&&!disposed){queued=false;void poll();}}
 }
 const timer=interval(()=>{onTick();void poll();},2000);
 void poll();
 return {refresh(){if(disposed)return;if(inFlight){queued=true;request?.abort();}else void poll();},dispose(){disposed=true;queued=false;clear(timer);request?.abort();}};
}
