import {useEffect,useRef} from 'react';
import type {RefObject} from 'react';
import type {RenderIssue} from './renderPreflight';

export default function RenderPreflightDialog({issues,onClose,onNavigate,returnFocus}:{returnFocus:RefObject<HTMLButtonElement|null>;issues:RenderIssue[];onClose:()=>void;onNavigate:(step:number)=>void}){
  const dialog=useRef<HTMLDialogElement>(null);
  const heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null;
    dialog.current?.showModal();heading.current?.focus();
    return()=>{dialog.current?.close();(returnFocus.current||previous)?.focus();};
  },[returnFocus]);
  return <dialog className="render-preflight" ref={dialog} aria-labelledby="preflight-title" aria-describedby="preflight-description" onCancel={e=>{e.preventDefault();onClose();}}>
    <small>出圖前檢查</small>
    <h2 id="preflight-title" ref={heading} tabIndex={-1}>還有 {issues.length} 項待完成</h2>
    <p id="preflight-description">要前往補齊設定嗎？目前尚未建立出圖工作，草稿會保留。</p>
    <ul>{issues.map(issue=><li key={issue.id}><h3>{issue.title}</h3><p>{issue.detail}</p>{issues.length>1&&<button onClick={()=>onNavigate(issue.step)}>{issue.action} →</button>}</li>)}</ul>
    <div className="preflight-actions"><button onClick={onClose}>留在整合輸出</button><button className="primary" onClick={()=>onNavigate(issues[0].step)}>{issues[0].action} →</button></div>
  </dialog>;
}
