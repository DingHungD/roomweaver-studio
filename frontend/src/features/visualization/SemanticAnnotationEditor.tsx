import type {AnswerMark} from './SemanticSourceReview';
import type {CorrectionMode} from './SemanticCorrections';
export type AnnotationMode=CorrectionMode|'select';
const names={box:'方框',line:'線條',text:'文字',freehand:'圈畫'};
export default function SemanticAnnotationEditor({marks,onChange,selected,onSelect,mode,onMode,text,onText,disabled,onUndo,canUndo}:{marks:AnswerMark[];onChange:(m:AnswerMark[])=>void;selected:string|null;onSelect:(id:string|null)=>void;mode:AnnotationMode;onMode:(m:AnnotationMode)=>void;text:string;onText:(t:string)=>void;disabled:boolean;onUndo:()=>void;canUndo:boolean}){
 const active=marks.find(m=>m.id===selected);
 function patch(value:Partial<AnswerMark>){if(active)onChange(marks.map(m=>m.id===active.id?{...m,...value}:m));}
 return <section className="semantic-annotation-editor" aria-label="標註編輯">
  <div className="semantic-mark-tools" role="group" aria-label="修正草稿工具">{([['select','選取／移動'],['pan','移動圖面'],['box','方框'],['line','線條'],['text','文字']] as const).map(([m,label])=><button key={m} type="button" disabled={disabled&&m!=='pan'} aria-pressed={mode===m} onClick={()=>onMode(m)}>{label}</button>)}</div>
  {mode==='text'&&<label>圖上文字<input aria-label="圖上文字" value={text} maxLength={500} disabled={disabled} onChange={e=>onText(e.target.value)} placeholder="輸入後，點選圖上的位置"/></label>}
  {!!marks.length&&<><div className="semantic-annotation-list" aria-label="標註元素清單">{marks.map((m,i)=><button key={m.id} type="button" aria-pressed={selected===m.id} onClick={()=>{onSelect(m.id);onMode('select');}}>{i+1} · {names[m.kind]}{m.kind==='text'?` · ${m.text}`:''}</button>)}</div>
   {active&&<div className="semantic-annotation-properties"><b>選取的{names[active.kind]}</b>{active.kind==='text'&&<label>修改圖上文字<input aria-label="修改圖上文字" value={active.text||''} maxLength={500} disabled={disabled} onChange={e=>patch({text:e.target.value})}/></label>}<small>{active.kind==='text'?'拖曳文字可移動位置。':active.kind==='box'?'拖曳方框可移動；拖曳四角可調整範圍。':'拖曳線條可移動；拖曳端點可調整。'}</small><button type="button" disabled={disabled} onClick={()=>{onChange(marks.filter(m=>m.id!==active.id));onSelect(null);}}>刪除標註</button></div>}
   <button type="button" disabled={disabled||!canUndo} onClick={onUndo}>復原標註</button></>}
  {!marks.length&&canUndo&&<button type="button" disabled={disabled} onClick={onUndo}>復原標註</button>}
  {!marks.length&&<small>新增方框、線條或文字後，可點選並拖移編輯。</small>}
 </section>;
}
