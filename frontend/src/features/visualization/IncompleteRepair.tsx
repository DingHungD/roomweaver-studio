import {createContext,useContext,useEffect,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {api} from './api';
import type {Revision,Scene} from './api';
import type {IncompleteItem} from './configurationIncomplete';

import type {RepairRecord} from './repairEvidence';
import {repairFailure} from './repairEvidence';
export {repairedItem} from './repairEvidence';
const RepairContext=createContext<{records:RepairRecord[];running:string;repair:(item:IncompleteItem)=>Promise<void>;error:string}|null>(null);
export const useIncompleteRepair=()=>useContext(RepairContext);
export function IncompleteRepairProvider(props:{project:string;scene:Scene|null;revision:string|null;dirty:boolean;onSave:()=>Promise<string|null|undefined>;onAccept:(r:Revision)=>void;children:ReactNode}){
 const [records,setRecords]=useState<RepairRecord[]>([]),[running,setRunning]=useState(''),[error,setError]=useState('');
 const latest=useRef(props),lock=useRef(false);latest.current=props;
 useEffect(()=>setError(''),[props.revision]);
 useEffect(()=>{let live=true,inFlight=false,previous:RepairRecord[]=[];setRecords([]);setError('');
  async function refresh(){if(!props.project||inFlight||lock.current)return;inFlight=true;try{const r=await api<RepairRecord[]>(`/projects/${props.project}/editor-repairs`);if(!live)return;setRecords(r);
   if(r.some(x=>x.status==='completed'&&previous.some(old=>old.id===x.id&&old.status==='running'))&&!latest.current.dirty){const saved=await api<Revision>(`/projects/${props.project}/scene`);if(live&&saved.revision!==latest.current.revision)latest.current.onAccept(saved);}previous=r;
  }catch(e){if(live)setError('修正紀錄讀取失敗：'+(e as Error).message);}finally{inFlight=false;}}
  void refresh();const timer=setInterval(()=>void refresh(),2000);return()=>{live=false;clearInterval(timer);};},[props.project]);
 async function repair(item:IncompleteItem){
  if(lock.current)return;lock.current=true;setError('');setRunning(item.id);
  const project=props.project;
  try{
   const base=latest.current.dirty?await latest.current.onSave():latest.current.revision;if(!base)throw Error('請先保存設計');
   const category=item.target?.kind||item.repair?.category;if(!category)throw Error('沒有可追溯修正目標');
   const failure=repairFailure(item,records);
   const reason=[item.reason,...(failure?.failure_details?.map(d=>`${d.stage}：${d.reason}`)||[])].join('\n').slice(0,12000);
   let r=await api<RepairRecord>(`/projects/${project}/editor-repairs`,'POST',{base_revision:base,operation_id:crypto.randomUUID().replaceAll('-',''),category,target_id:item.id,task_id:item.task,batch_id:item.repair?.batch_id||null,shot_id:item.target?.shotId||null,part:item.part,reason});
   setRecords(old=>[r,...old.filter(x=>x.id!==r.id)]);
   while(r.status==='running'){
    await new Promise(resolve=>setTimeout(resolve,1000));
    r=await api<RepairRecord>(`/projects/${project}/editor-repairs/${r.id}`);
    if(latest.current.project!==project)return;
    setRecords(old=>[r,...old.filter(x=>x.id!==r.id)]);
   }
   if(r.status!=='completed')throw Error(r.error||r.phase);
   if(latest.current.dirty)throw Error('修正已完成；目前有未保存草稿，未覆蓋。請先保存或復原草稿，再重新開啟設計。');
   const saved=await api<Revision>(`/projects/${project}/scene`);
   if(latest.current.project===project){latest.current.onAccept(saved);document.dispatchEvent(new Event('studio-editor-repaired'));}
  }catch(e){setError((e as Error).message);}finally{lock.current=false;setRunning('');}
 }
 return <RepairContext.Provider value={{records,running:running||records.find(r=>r.status==='running')?.request.target_id||'',repair,error}}>{props.children}</RepairContext.Provider>;
}
