/** Opt-in local CPU/next-frame evidence, exposed on the canvas host (no telemetry). */
export function viewportProbe(host:HTMLElement){
 const enabled=new URLSearchParams(location.search).has('performance');
 const samples:Record<string,number[]>={};const origin=performance.now();
 let input=0,label='',last=0,first=true,frames=0,lastPhase='',phaseTime=0;
 const interactions:{label:string;wait:number;render:number;total:number}[]=[];
 const record=(key:string,value:number)=>{if(!enabled)return;(samples[key]??=[]).push(Math.round(value*100)/100);if(samples[key].length>240)samples[key].shift();};
 const begin=(event:Event)=>{const target=event.target as Element;if(host.closest('.space-editor')?.contains(target)||target?.closest?.('.edit-sections,.workspace-controls,.rail-toggle')){input=performance.now();label=target.closest('button,[role="tab"]')?.textContent?.trim()||target.getAttribute('aria-label')||event.type;}};
 if(enabled)for(const name of ['pointerdown','keydown','change','wheel'])document.addEventListener(name,begin,true);
 return {
  start(key:string){const t=performance.now();return()=>record(key,performance.now()-t);},
  frame(info:{calls:number;triangles:number},renderStarted:number,phase='idle'){
   if(!enabled)return;const now=performance.now();frames++;
   if(last)record('frameInterval',now-last);last=now;
   if(first){record('firstFrame',now-origin);first=false;}
   if(phase!=='idle'){record(phase+'CPU',now-renderStarted);record(phase+'Calls',info.calls);record(phase+'Triangles',info.triangles);if(lastPhase===phase)record(phase+'Interval',now-phaseTime);}
   lastPhase=phase;phaseTime=now;
   if(input){record('inputToFrame',now-input);interactions.push({label,wait:Math.round((renderStarted-input)*100)/100,render:Math.round((now-renderStarted)*100)/100,total:Math.round((now-input)*100)/100});if(interactions.length>100)interactions.shift();input=0;}
   host.dataset.performance=JSON.stringify({samples,interactions,frames,calls:info.calls,triangles:info.triangles,viewport:[host.clientWidth,host.clientHeight],visibility:document.visibilityState});
  },
  dispose(){if(enabled)for(const name of ['pointerdown','keydown','change','wheel'])document.removeEventListener(name,begin,true);},
 };
}
