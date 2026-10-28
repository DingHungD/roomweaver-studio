import {useEffect,useRef,useState} from 'react';
import {filterSemanticSelection,semanticCategoryKey,semanticSelectionGroups,toggleSemanticKeys} from './semanticLayerFilter.mjs';
import type {SemanticLayerItem} from './SemanticLayers';
export type DraftOption={id:string;label:string;title:string;markCount:number;hasText:boolean;located:boolean};
type QuestionOption={id:string;label:string;title:string;statusText?:string};
function GroupCheck({name,checked,mixed,onChange}:{name:string;checked:boolean;mixed:boolean;onChange:(checked:boolean)=>void}){
 const input=useRef<HTMLInputElement>(null);
 useEffect(()=>{if(input.current)input.current.indeterminate=mixed;},[mixed]);
 return <label><input ref={input} type="checkbox" checked={checked} aria-checked={mixed?'mixed':checked} onChange={e=>onChange(e.target.checked)}/>{name}</label>;
}
function AnnotationGroup({name,options,hidden,collapsed,onToggle,onVisibility,onSelect}:{name:string;options:QuestionOption[];hidden:Set<string>;collapsed:boolean;onToggle:()=>void;onVisibility:(id:string,visible:boolean)=>void;onSelect?:(id:string)=>void}){
 const count=options.filter(option=>!hidden.has(option.id)).length;
 return <div className="semantic-selection-group">
  <div className="semantic-selection-group-heading"><GroupCheck name={`${name} (${options.length})`} checked={options.length>0&&count===options.length} mixed={count>0&&count<options.length} onChange={checked=>options.forEach(option=>onVisibility(option.id,checked))}/><button type="button" aria-label={name+'子項目'} aria-expanded={!collapsed} onClick={onToggle}>{collapsed?'展開':'收合'}</button></div>
  <div className="semantic-selection-children" hidden={collapsed}>{options.length?options.map(option=><div key={option.id} className="semantic-legend-option"><input aria-label={'顯示 '+option.label+' '+option.title} type="checkbox" checked={!hidden.has(option.id)} onChange={e=>onVisibility(option.id,e.target.checked)}/>{onSelect?<button type="button" onClick={()=>{onVisibility(option.id,true);onSelect(option.id);}}>{option.label} · {option.title}{option.statusText&&<small>{option.statusText}</small>}</button>:<span>{option.label} · {option.title}</span>}</div>):<small>尚無修改項草稿。</small>}</div>
 </div>;
}
export default function SemanticLayerSelector({items,selection,onSelection,drafts,hiddenDrafts,onDraftVisibility,questions=[],onOriginal,onQuestionSelect,onDraftSelect,title='顯示類別'}:{items:SemanticLayerItem[];selection:string[]|null;onSelection:(s:string[]|null)=>void;drafts:DraftOption[];hiddenDrafts:Set<string>;onDraftVisibility:(id:string,visible:boolean)=>void;questions?:QuestionOption[];onOriginal?:()=>void;onQuestionSelect?:(id:string)=>void;onDraftSelect?:(id:string)=>void;title?:string}){
 const menu=useRef<HTMLDetailsElement>(null),trigger=useRef<HTMLElement>(null);
 const [expanded,setExpanded]=useState<Set<string>>(new Set());
 const isCollapsed=(id:string)=>!expanded.has(id);
 function toggle(id:string){setExpanded(current=>{const next=new Set(current);if(next.has(id))next.delete(id);else next.add(id);return next;});}
 const groups=semanticSelectionGroups(items),chosen=new Set((selection===null?filterSemanticSelection(items):filterSemanticSelection(items,selection)).map(semanticCategoryKey));
 const shownQuestions=questions.filter(q=>!hiddenDrafts.has(q.id)).length;
 const otherDrafts=drafts.filter(d=>!questions.some(q=>q.id===d.id));
 useEffect(()=>{
  function outside(e:PointerEvent){if(menu.current&&!menu.current.contains(e.target as Node))menu.current.open=false;}
  function escape(e:KeyboardEvent){if(e.key==='Escape'&&menu.current?.open){menu.current.open=false;trigger.current?.focus();}}
  document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);
  return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);};
 },[]);
 return <details ref={menu} className="semantic-selection-menu">
  <summary ref={trigger} aria-label="選擇顯示類別與修改項草稿">{title} <small>{chosen.size} 類{questions.length>0&&` · ${shownQuestions} 項疑點`} · {otherDrafts.filter(d=>!hiddenDrafts.has(d.id)).length} 份草稿</small><span aria-hidden="true">⌄</span></summary>
  <div className="semantic-selection-options" aria-label="多選顯示圖層">
   <div className="semantic-selection-actions"><button type="button" onClick={()=>onSelection([...new Set(items.map(semanticCategoryKey))])}>全選判讀</button><button type="button" onClick={()=>onSelection([])}>清除判讀</button>{onOriginal&&<button type="button" onClick={onOriginal}>僅看原圖</button>}</div>
   {questions.length>0&&<AnnotationGroup name="疑點紀錄（Q）" options={questions} hidden={hiddenDrafts} collapsed={isCollapsed('questions')} onToggle={()=>toggle('questions')} onVisibility={onDraftVisibility} onSelect={onQuestionSelect}/>}
   {groups.map(group=>{const keys=group.options.map(o=>o.key),count=keys.filter(k=>chosen.has(k)).length;return <div className="semantic-selection-group" key={group.id}>
    <div className="semantic-selection-group-heading"><GroupCheck name={group.name} checked={count===keys.length} mixed={count>0&&count<keys.length} onChange={checked=>onSelection(toggleSemanticKeys(items,selection,keys,checked))}/>{group.options.length>1&&<button type="button" aria-label={group.name+'子類別'} aria-expanded={!isCollapsed(group.id)} onClick={()=>toggle(group.id)}>{isCollapsed(group.id)?'展開':'收合'}</button>}</div>
    {group.options.length>1&&<div className="semantic-selection-children" hidden={isCollapsed(group.id)}>{group.options.map(option=><label key={option.key}><input type="checkbox" checked={chosen.has(option.key)} onChange={e=>onSelection(toggleSemanticKeys(items,selection,[option.key],e.target.checked))}/>{option.name}<small>{option.count}</small></label>)}</div>}
   </div>;})}
   <AnnotationGroup name="修改項草稿（M）" options={otherDrafts} hidden={hiddenDrafts} collapsed={isCollapsed('drafts')} onToggle={()=>toggle('drafts')} onVisibility={onDraftVisibility} onSelect={onDraftSelect}/>
  </div>
 </details>;
}
