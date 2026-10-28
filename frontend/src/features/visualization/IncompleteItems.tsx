import {useIncompleteRepair,repairedItem} from './IncompleteRepair';
import type {Scene} from './api';
import {scopedIncompleteItems} from './configurationScope';
import type {ConfigurationScope} from './configurationScope';
import {useEffect,useMemo,useRef,useState} from 'react';
import type {ConfigurationRow,IncompleteItem} from './configurationIncomplete';
import {repairFailure} from './repairEvidence';
import type {RepairRecord} from './repairEvidence';
function FailureReasons({failure}:{failure?:RepairRecord}){
 if(!failure)return null;
 return <details className="incomplete-failure"><summary>上次修正未通過 · 查看逐項原因（{failure.failure_details?.length||1}）</summary><p>{failure.error}</p>{!!failure.failure_details?.length&&<ol>{failure.failure_details.map((d,i)=><li key={i}><b>{d.name||d.stage}</b><p>{d.reason}</p></li>)}</ol>}</details>;
}
export type IncompleteControls={incompleteSelected?:string;onIncomplete?:(items:IncompleteItem[])=>void;onLocateIncomplete?:(item:IncompleteItem)=>void};
export function IncompleteDetail({item}:{item?:IncompleteItem}){
 const repair=useIncompleteRepair();
 if(!item)return null;
 const failure=repairFailure(item,repair?.records||[]);
 return <aside className="incomplete-detail"><b>{item.name}</b><details><summary>{item.status} · 查看原因</summary><p>{item.reason}</p></details><FailureReasons failure={failure}/></aside>;
}
type ListProps=IncompleteControls & {items:IncompleteItem[];resetKey?:string;emptyMessage?:string;open?:boolean;onOpenChange?:(open:boolean)=>void};
export function IncompleteList({items,onIncomplete,onLocateIncomplete,incompleteSelected,open:controlledOpen,onOpenChange,resetKey,emptyMessage='此頁目前沒有未完成項目。'}:ListProps){
 const repair=useIncompleteRepair();
 const [localOpen,setLocalOpen]=useState(false);
 const open=controlledOpen??localOpen,setOpen=onOpenChange||setLocalOpen;
 const callback=useRef(onIncomplete);callback.current=onIncomplete;
 useEffect(()=>{callback.current?.(open?items:[]);return()=>callback.current?.([]);},[open,items]);
 useEffect(()=>{if(open)setOpen(false);},[resetKey]);
 return <div className="incomplete-control">
  <button aria-expanded={open} onClick={()=>setOpen(!open)}>查看未完成項目（{items.length}）</button>
  {open&&<section className="incomplete-panel" aria-label="未完成配置項目">
   <p>{items.length?'點選項目或圖上的編號框，定位並在右側編輯。':emptyMessage}</p>
   <div className="incomplete-list">{items.map((item,i)=>{
    const failure=repairFailure(item,repair?.records||[]);
    const available=item.available||item.editable;
    const active=repair?.running===item.id;
    const locate=()=>{if(available)onLocateIncomplete?.(item);};
    return <article className="incomplete-row" key={item.id} data-selected={incompleteSelected===item.id} data-locatable={!!available} onClick={locate}>
     <button className="incomplete-locate" aria-pressed={incompleteSelected===item.id} disabled={!available} onClick={e=>{e.stopPropagation();locate();}}>
      <b title={item.name}>{i+1}. {item.name}</b>
      <small>{item.status}{!item.available?' · 無可定位位置':''}</small>
      <span title={item.reason}>{item.reason}</span>
     </button>
     {repair&&available&&<div className="incomplete-actions">
      <button className="incomplete-repair" disabled={!!repair.running} onClick={e=>{e.stopPropagation();locate();void repair.repair(item);}}>{active?'Agent 修正中…':'Agent 依原因修正'}</button>
     </div>}
     <div onClick={e=>e.stopPropagation()}><FailureReasons failure={failure}/></div>
     {active&&<p className="incomplete-progress" role="status">{repair.records.find(r=>r.status==='running'&&r.request.target_id===item.id)?.phase||'正在核對修正證據'}</p>}
    </article>;
   })}</div>
   {repair?.running&&!items.some(i=>i.id===repair.running)&&<p role="status">{repair.records.find(r=>r.status==='running')?.phase||'正在核對修正證據'}</p>}
   {repair?.error&&<p role="alert">{repair.error}</p>}
  </section>}
 </div>;
}
export default function IncompleteItems({batch,scene,scope,...controls}:{batch:{id:string;status:string;items:ConfigurationRow[]}|null;scene:Scene;scope:ConfigurationScope;open?:boolean;onOpenChange?:(open:boolean)=>void}&IncompleteControls){
 const repair=useIncompleteRepair();
 const items=useMemo(()=>scopedIncompleteItems(batch,scene,scope).map(item=>({...item,repair:batch?{category:scope,batch_id:batch.id}:undefined})).filter(item=>!repairedItem(item,repair?.records||[],scene)),[batch,scene,scope,repair?.records]);
 return <IncompleteList {...controls} items={items} resetKey={batch?.id} emptyMessage={batch?'此頁目前沒有未完成項目。':'尚未有配置結果，請先執行一鍵配置。'}/>;
}
