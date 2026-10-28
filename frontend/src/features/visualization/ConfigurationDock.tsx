import {cloneElement,useState} from 'react';
import type {ReactElement,ReactNode} from 'react';

export default function ConfigurationDock({children,unfinished,onOpen,disabled=false,title}:{children?:ReactNode;unfinished?:ReactElement<{open?:boolean;onOpenChange?:(open:boolean)=>void}>;onOpen?:()=>void;disabled?:boolean;title?:string}){
 const [panel,setPanel]=useState<'settings'|'incomplete'|null>(null);
 const open=panel==='settings';
 return <div className={`configuration-dock ${unfinished?'has-incomplete':''}`}>
  <button className="configuration-toggle" title={title} disabled={disabled} aria-expanded={open} onClick={()=>{setPanel(open?null:'settings');if(!open)onOpen?.();}}>{open?'▾':'▸'} 一鍵配置設定</button>
  {unfinished&&cloneElement(unfinished,{open:panel==='incomplete',onOpenChange:value=>setPanel(value?'incomplete':null)})}
  {open&&<section className="configuration-body dock-settings" aria-label="一鍵配置設定">{children}</section>}
 </div>;
}
