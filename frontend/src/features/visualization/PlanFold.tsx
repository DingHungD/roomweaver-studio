import {useState} from 'react';
import type {ReactNode} from 'react';

export default function PlanFold({title,status,initialOpen=false,children}:{title:string;status?:string;initialOpen?:boolean;children:ReactNode}){
  const [open,setOpen]=useState(initialOpen);
  return <details className="plan-fold" open={open} onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary>{title}<span>{status}</span></summary><div>{children}</div>
  </details>;
}
