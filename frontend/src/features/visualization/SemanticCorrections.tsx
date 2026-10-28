import type {ReactNode} from 'react';
import {correctionComplete,correctionCurrent,correctionSentence} from './semanticCorrectionState.mjs';
export type CorrectionMark={id:string;kind:'box'|'line'|'text';points:[number,number][];text:string};
export type CorrectionItem={id:string;title:string;comment:string;marks:CorrectionMark[];target_id?:string;target_kind?:'object'|'question'|'correction';mode?:'object'|'region'|null;target_domain?:'objects'|'plan'|null};
export type CorrectionOutcome={id:string;status:'corrected'|'no_change'|'needs_confirmation'|'unresolved';summary:string;preview_ready:boolean;item_snapshot?:CorrectionItem;current?:boolean;review_id?:string;mark_checks?:{mark_id:string;number:number;passed:boolean;errors:string[]}[]};
export type CorrectionProps={adoptions?:Record<string,string[]>;onExperienceBatch?:(ids:string[])=>void;canExperienceBatch?:boolean;items:CorrectionItem[];onChange:(items:CorrectionItem[])=>void;dirty:boolean;onSave:()=>Promise<boolean>;onBatch:(ids:string[])=>void;results:CorrectionOutcome[];resultsCurrent:boolean;previewVersion?:string;disabled:boolean;canBatch:boolean};
export type CorrectionMode='select'|'pan'|'box'|'line'|'text'|'freehand';
const labels={corrected:'已修正 · 待預覽',no_change:'已核對 · 無須修改',needs_confirmation:'需要確認',unresolved:'尚未完成'};
export default function SemanticCorrections({items,onChange,dirty,onSave,onBatch,results,resultsCurrent,disabled,canBatch,active,onActive,checked,onChecked,editor,detail=false,onBack,adoptions={},onExperienceBatch,canExperienceBatch=false}:CorrectionProps&{active:string|null;onActive:(id:string)=>void;checked:string[];onChecked:(ids:string[])=>void;editor:ReactNode;detail?:boolean;onBack:()=>void;listOpen:boolean;onListOpen:(open:boolean)=>void}){
 const item=items.find(i=>i.id===active),ready=checked.filter(id=>items.some(i=>i.id===id&&(i.comment.trim()||i.marks.length)));
 function update(patch:Partial<CorrectionItem>){if(item)onChange(items.map(i=>i.id===item.id?{...i,...patch}:i));}
 function add(){const id='cor-'+crypto.randomUUID().replaceAll('-','');onChange([...items,{id,title:`修正項 ${items.length+1}`,comment:'',marks:[],mode:'region'}]);onChecked([...checked,id]);onActive(id);}
 const complete=ready.every(id=>correctionComplete(items.find(i=>i.id===id),results.find(r=>r.id===id),resultsCurrent));
 return <section className="semantic-corrections" aria-label={detail?'修改項內容':'修改項清單'}>
  {!detail&&<><header><b>修改項 ({items.length})</b><span>{checked.length} 項已選</span></header>
  <div className="semantic-correction-list">{items.length?items.map((i,n)=>{const outcome=results.find(r=>r.id===i.id);return <article key={i.id} className={i.id===active?'active':''}>
   <div className="semantic-correction-row"><input type="checkbox" aria-label={`批次選取 ${i.title}`} checked={checked.includes(i.id)} disabled={disabled} onChange={e=>onChecked(e.target.checked?[...checked,i.id]:checked.filter(id=>id!==i.id))}/><button type="button" aria-pressed={active===i.id} onClick={()=>onActive(i.id)}><b>M{n+1} · {i.title}</b><small>{correctionSentence(i)}</small><span className="semantic-correction-state">{correctionComplete(i,outcome,resultsCurrent)?'已完成':'待完成'}</span><span className="semantic-correction-state">{adoptions[i.id]?.length?'已採用':'待採用'}</span></button></div>
  </article>;}):<p>將需要調整的位置標在原圖，並寫下你的意見。</p>}</div>
  <button type="button" disabled={disabled||items.length>=40} onClick={add}>＋修改項</button>
  </>}
  {detail&&item&&<article className="semantic-correction-editor" aria-label="修改項詳細編輯">
   <h3>M{items.indexOf(item)+1} · {item.title}</h3>
   <label>名稱<input aria-label="修改項名稱" value={item.title} maxLength={120} disabled={disabled} onChange={e=>update({title:e.target.value})}/></label>
   {editor}
   <label>修改意見<textarea aria-label="修正意見" value={item.comment} maxLength={3000} disabled={disabled} onChange={e=>update({comment:e.target.value})} placeholder="例如：框選處是衣櫃，請保留位置與已確認尺寸。"/></label>
   <div className="semantic-correction-actions"><button type="button" disabled={disabled} onClick={()=>{onChange(items.filter(i=>i.id!==item.id));onChecked(checked.filter(id=>id!==item.id));onBack();}}>刪除修改項</button></div>
   {results.filter(r=>r.id===item.id).map(outcome=><details key={outcome.id} className="semantic-correction-outcome"><summary>處理紀錄</summary><b>{correctionCurrent(item,outcome,resultsCurrent)?labels[outcome.status]:'草稿已修改 · 待重新處理'}</b><p>{outcome.summary}</p>{outcome.mark_checks?.map(check=><p key={check.mark_id}>標註 {check.number} · {check.passed?'已核對':check.errors.join('；')}</p>)}</details>)}
   <label>修正範圍<select aria-label="修正範圍" value={item.mode||'auto'} disabled={disabled} onChange={e=>update({mode:e.target.value==='auto'?null:e.target.value as 'object'|'region'})}>{!item.mode&&<option value="auto">依原物件／標註判定，縮小範圍優先</option>}<option value="region">僅標註範圍內</option>{item.target_kind==='object'&&item.target_id&&<option value="object">指定整件物件</option>}</select></label>
   <small>框外保持；線條範圍為兩側各 8 公分。純文字須先選取物件或畫範圍。僅明確要求的漏項可新增，請寫明種類及數量。</small>
   <small>{item.marks.length} 筆標註 · 僅保存意見，不更動原件</small>
  </article>}
  <div className="semantic-correction-actions"><button type="button" disabled={disabled||!dirty} onClick={async()=>{if(await onSave()&&detail)onBack();}}>保存修改草稿</button>{!detail&&<button type="button" className="primary" disabled={disabled||!canBatch||!ready.length||ready.length!==checked.length} onClick={()=>onBatch(ready)}>批次修改所選（{checked.length}）</button>}{!detail&&onExperienceBatch&&<button type="button" disabled={disabled||!canExperienceBatch||!ready.length||ready.length!==checked.length||!complete} onClick={()=>onExperienceBatch(ready)}>批次進入經驗庫（{checked.length}）</button>}</div>
  {!detail&&<>{checked.length!==ready.length&&<small>請為勾選的修正項填寫意見或圖上標註。</small>}{!canBatch&&<small>請先完成本版圖面判讀並保存平面設定。</small>}{!!checked.length&&!complete&&<small>所選項目須先完成修改，才能整理入經驗庫。</small>}</>}
 </section>;
}
