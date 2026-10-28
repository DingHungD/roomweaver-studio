import {useState} from 'react';
export type CoverageItem={id:string;kind:string;label:string;box:[number,number,number,number];status:'matched'|'ignored'|'pending'|'question';reason:string;ask?:string;source_ids:string[];object_ids:string[]};
export type Coverage={version:string;items:CoverageItem[];counts:Record<string,number>;total:number;scope:string;reviews?:{round:number;accepted:boolean;error?:string|null}[]};
const names={matched:'已對應',ignored:'已說明忽略',pending:'待自動處理',question:'需確認'};
export default function SemanticCoveragePanel({coverage,onLocate}:{coverage?:Coverage;onLocate:(item:CoverageItem)=>void}){
 const [filter,setFilter]=useState('pending');if(!coverage)return null;
 const items=coverage.items.filter(i=>filter==='all'||i.status===filter);
 return <details className="semantic-coverage"><summary>來源候選檢查 · {coverage.counts.pending} 待處理 · {coverage.counts.question} 需確認</summary>
  <p>{coverage.total} 組：已對應 {coverage.counts.matched}、已說明忽略 {coverage.counts.ignored}。</p><small>{coverage.scope}</small>
  <label>查看狀態<select aria-label="來源候選狀態" value={filter} onChange={e=>setFilter(e.target.value)}>{Object.entries(names).map(([k,v])=><option key={k} value={k}>{v}（{coverage.counts[k]}）</option>)}<option value="all">全部（{coverage.total}）</option></select></label>
  <div className="semantic-coverage-items">{items.map(item=><button type="button" key={item.id} onClick={()=>onLocate(item)}><b>{item.label}</b><small>{names[item.status]} · {item.reason}</small>{item.ask&&<small>{item.ask}</small>}</button>)}{!items.length&&<p>這個狀態目前沒有項目。</p>}</div>
  {!!coverage.reviews?.length&&<small>已執行 {coverage.reviews.length} 批局部複核；未通過的提案保留待處理，未套用。</small>}
 </details>;
}
