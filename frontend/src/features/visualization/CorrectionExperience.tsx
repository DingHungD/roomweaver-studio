import {useEffect,useState} from 'react';
import {api} from './api';
import {useProjectDraft} from './ProjectDraft';
import {pendingExperienceDrafts} from './semanticExperienceState.mjs';

type Draft={id:string;revision:string;review_id:string;automatic?:boolean;title:string;interpretation:string;mistake:string;reason:string;applies:string;exceptions:string;status:string;confirmed:boolean;target_id:string;target_kind?:'object'|'correction';box:number[];entry_id?:string;entry_revision?:string;entry_active?:boolean};
type Hit={id:string;title:string;interpretation:string;reason:string;applies:string;exceptions:string;scores:{score:number;geometry:number;image:number;annotations:number}};
type Search={hits:Hit[];elapsed_ms:number;examined:number;library_count:number};
type Entry={id:string;revision:string;title:string;interpretation:string;mistake:string;reason:string;applies:string;exceptions:string;active:boolean;confirmed_at:string;example_count:number};
export type ExperienceContext={refresh?:number;url:string;reviewId:string;sourceRevision:string;disabled:boolean;preparation?:{items:{target_id:string;status:string;title?:string;reason?:string}[]}|null};

export default function CorrectionExperience({context,target,kind='object'}:{context:ExperienceContext;target:string|null;kind?:'object'|'correction'}){
 const [entries,setEntries]=useState<Entry[]>([]),[entry,setEntry]=useState<Entry|null>(null),[total,setTotal]=useState(0);
 const [drafts,setDrafts]=useState<Draft[]>([]),[active,setActive]=useState<Draft|null>(null),[count,setCount]=useState(0),[agreed,setAgreed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[search,setSearch]=useState<Search|null>(null);
 const [adoptions,setAdoptions]=useState<Record<string,string[]>>({});
 const url=context.url+'/experience-drafts';
 const keys=['title','interpretation','mistake','reason','applies','exceptions'] as const;
 const saved=drafts.find(d=>d.id===active?.id),dirty=!!active&&!active.confirmed&&!!saved&&keys.some(k=>active[k]!==saved[k]);
 async function save(){if(!active)return;const result=await api<Draft>(url+'/'+active.id,'PUT',Object.fromEntries([['draft_revision',active.revision],...keys.map(k=>[k,active[k]])]));choose(result);await load();}
 useProjectDraft({label:'修正經驗草稿',dirty,blocked:busy,save});
 async function load(){const [data,catalog]=await Promise.all([api<{drafts:Draft[];library:{active:number};adoptions?:Record<string,string[]>}>(url),api<{entries:Entry[];total:number}>('/cad-experiences')]);setDrafts(data.drafts);setAdoptions(data.adoptions||{});setCount(data.library.active);setEntries(catalog.entries);setTotal(catalog.total);}
 useEffect(()=>{void load().catch(e=>setError(e.message));},[url,context.reviewId,context.refresh]);
 function choose(draft:Draft){setEntry(null);setActive({...draft});setAgreed(false);setSearch(null);setError('');}
 async function work(action:()=>Promise<void>){setBusy(true);setError('');try{await action();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function create(){if(dirty)await save();const draft=await api<Draft>(url,'POST',{base_revision:context.sourceRevision,review_id:context.reviewId,kind,target_id:target});choose(draft);await load();}
 async function confirm(){if(!active||!agreed)return;const result=await api<Draft>(url+'/'+active.id+'/confirm','POST',{draft_revision:active.revision,title:active.title,interpretation:active.interpretation,mistake:active.mistake,reason:active.reason,applies:active.applies,exceptions:active.exceptions,confirmed:true});choose(result);await load();}
 function update(key:'title'|'interpretation'|'mistake'|'reason'|'applies'|'exceptions',value:string){if(active){setActive({...active,[key]:value});setAgreed(false);}}
 const fields={title:'經驗名稱',interpretation:'正確判讀',mistake:'原本誤判',reason:'判斷理由',applies:'適用條件',exceptions:'不適用情況'};
 const pending:Draft[]=pendingExperienceDrafts(drafts,adoptions);
 return <section className="correction-experience experience-library" aria-label="經驗庫清單">
  {!active&&!entry?<><header><b>經驗項</b><small>{count} 已採用 · {pending.length} 待採用</small></header>
   <div className="experience-draft-list">{entries.map(e=><button key={e.id} type="button" onClick={()=>{setEntry(e);setError('');}}><b>{e.title}</b><small>{e.active?'已採用':'已停用'} · {e.example_count} 個來源案例</small></button>)}{pending.map(d=><button key={d.id} type="button" onClick={()=>choose(d)}><b>{d.title}</b><small>待採用</small></button>)}{!entries.length&&!pending.length&&<p>尚無經驗項。可在「修正項」選取已完成項目，批次整合入庫。</p>}</div>
   {entries.length<total&&<button type="button" disabled={busy} onClick={()=>void work(async()=>{const next=await api<{entries:Entry[];total:number}>('/cad-experiences?offset='+entries.length);setEntries([...entries,...next.entries]);})}>載入更多</button>}
   {target&&<button type="button" disabled={busy||context.disabled} onClick={()=>void work(create)}>整理目前物件為經驗</button>}
  </>:<><button type="button" className="semantic-back-to-list" onClick={()=>void work(async()=>{if(dirty)await save();setActive(null);setEntry(null);setSearch(null);})}>← 返回經驗項清單</button>
   {entry&&<article aria-label="經驗項詳細資料"><h3>{entry.title}</h3><small>{entry.active?'已採用':'已停用'} · {entry.example_count} 個來源案例</small><img alt={entry.title+'原圖局部'} src={'/api/studio/cad-experiences/'+entry.id+'/image'}/>{(['interpretation','mistake','reason','applies','exceptions'] as const).map(key=>entry[key]&&<div key={key}><b>{fields[key]}</b><p>{entry[key]}</p></div>)}{entry.active&&<button type="button" disabled={busy} onClick={()=>void work(async()=>{await api('/cad-experiences/'+entry.id+'/deactivate','POST',{revision:entry.revision});setEntry({...entry,active:false});await load();})}>停用此經驗</button>}</article>}
   {active&&<article aria-label="修正經驗待確認內容"><img alt="修正經驗的原圖局部" src={'/api/studio'+url+'/'+active.id+'/image'} loading="lazy"/>
    {(['title','interpretation','mistake','reason','applies','exceptions'] as const).map(key=><label key={key}>{fields[key]}<textarea aria-label={'經驗'+key} maxLength={key==='title'?120:key==='reason'?1500:key==='applies'||key==='exceptions'?1200:500} value={active[key]} disabled={active.confirmed||busy} onChange={e=>update(key,e.target.value)}/></label>)}
    {!active.confirmed&&<><button type="button" disabled={busy||!dirty} onClick={()=>void work(save)}>保存經驗草稿</button><label className="experience-confirm"><input type="checkbox" checked={agreed} disabled={busy||context.disabled} onChange={e=>setAgreed(e.target.checked)}/>我已核對此修正正確，允許其他專案參考</label><button type="button" className="primary" disabled={busy||context.disabled||!agreed||!active.interpretation.trim()||!active.reason.trim()||!active.applies.trim()} onClick={()=>void work(confirm)}>確認正確並加入經驗庫</button></>}
    {active.confirmed&&<p>{active.entry_active?'已確認入庫；設計未採用。':'此經驗已停用，歷史保留。'}</p>}
    <button type="button" disabled={busy} onClick={()=>void work(async()=>setSearch(await api<Search>(url+'/'+active.id+'/search')))}>比對已確認經驗</button>
    {search&&<details><summary>相似經驗（{search.hits.length}）</summary>{search.hits.map(hit=><article key={hit.id}><img alt={hit.title+'的局部參考圖'} loading="lazy" src={'/api/studio/cad-experiences/'+hit.id+'/image'}/><b>{hit.interpretation}</b><p>{hit.reason}</p><p>{hit.applies}</p><small>{hit.exceptions}</small></article>)}</details>}
   </article>}
  </>}
  {busy&&<p role="status">正在整理或比對…</p>}{error&&<p role="alert">{error}</p>}
 </section>;
}
