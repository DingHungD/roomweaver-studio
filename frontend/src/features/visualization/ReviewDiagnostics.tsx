import {reviewStatus} from './reviewDiagnosticState.mjs';
type Issue={id:string;message:string;object_ids:string[];source_ids:string[];box:[number,number,number,number]|null};
export type Diagnostics={version:string;checks:{id:string;label:string;status:'passed'|'failed'|'deferred';reason:string}[];groups:{id:string;title:string;status:string;reason:string;issues:Issue[]}[];boundary:{evidence_sufficient:boolean;user_confirmed:boolean}};
export default function ReviewDiagnostics({value,onLocate}:{value?:Diagnostics;onLocate:(issue:Issue)=>void}){
 if(!value)return null;
 return <details className="semantic-coverage"><summary>分項檢查與待辦 · {value.checks.filter(c=>c.status!=='passed').length} 項待處理</summary>
  <p>範圍證據：{value.boundary.evidence_sufficient?'已核對':'不足'} · 使用者確認：{value.boundary.user_confirmed?'已確認':'未確認'}</p>
  {value.checks.map(c=><p key={c.id}>{c.label}：{reviewStatus(c.status)}{c.reason&&` · ${c.reason}`}</p>)}
  {value.groups.map(g=><details key={g.id}><summary>{g.title} · {g.issues.length} 項關聯紀錄</summary><p>{g.reason}</p>{g.issues.map((i,n)=><div key={i.id+':'+n}><p>{i.message}</p>{!!i.object_ids.length&&<small>{i.object_ids.join('、')}</small>}{i.box&&<button type="button" onClick={()=>onLocate(i)}>定位原圖</button>}</div>)}</details>)}
 </details>;
}
